"""Backend-owned student workspace. Dify understands; backend validates and executes."""
import logging
from time import monotonic
import re
from datetime import datetime
from app.modules.feedback import service as feedback_service
from app.core.exceptions import BusinessError
from . import assistant_chat as legacy, assistant_context, assistant_dify, assistant_store, assistant_mem0
from . import assistant_tasks as tasks, assistant_workspace_repository as repo, service
from . import assistant_guidance as guidance, assistant_knowledge as knowledge, assistant_dialogue as dialogue
from . import assistant_safety_resources
from .assistant_intent import route
from .assistant_safety import high_risk_hits
from .schemas import AssistantUnderstanding
from .assistant_reply_stream import safe_context_reply, StudentReplyInterrupted

log = logging.getLogger(__name__)
CONFIRM = {"确认提交", "确认办理"}
CANCEL = {"取消", "取消办理", "取消草稿", "算了", "不请了", "不用了"}


def _pack(reply, intent="chat", **extra):
    return {"answer": reply, "reply": reply, "intent": intent, **extra}


def _clock_values(text):
    values = []
    inherited = None
    for period, hour, colon, minute, sec_colon, seconds, cn_minute in legacy._CLOCK_TOKEN_RE.findall(text):
        inherited = period or inherited
        value = legacy._clock(hour, minute or cn_minute, inherited)
        if value:
            values.append(value)
    return values


def fill_leave(text, previous, extracted):
    payload = dict(previous)
    issue = legacy._leave_time_issue(text)
    for word, value in (("病假", "sick"), ("事假", "personal"), ("紧急", "emergency")):
        if word in text:
            payload["leave_type"] = value
            break
    # Model fields may only copy an explicit current-user span. It cannot supply dates from memory.
    reason = extracted.get("reason", "")
    explicit = re.search(r"(?:事由|原因)[：:]?(.+)", text)
    if explicit:
        reason = explicit.group(1).strip()
    elif not reason:
        reason = next((w for w in ("身体不适", "家里有事", "发烧", "感冒", "看病", "肚子疼") if w in text), "")
    if reason and reason in text and reason not in legacy._REASON_STOPWORDS and reason not in {"病假", "事假", "紧急", "请假", "我要请假", "继续请假", "我要修改请假时间"}:
        payload["reason"] = reason[:4000]
    clocks = _clock_values(text)
    has_date = bool(legacy._DATE_RE.search(text) or legacy._CN_RANGE_RE.search(text) or
                    legacy._MD_RANGE_RE.search(text) or re.search(r"今天|明天|后天|\d{1,2}号", text))
    # A supplied new date invalidates old times; a time-only follow-up keeps previously supplied dates.
    if has_date:
        payload["_date_hint"] = text
        payload.pop("start_time", None)
        payload.pop("end_time", None)
    if issue:
        payload.pop("start_time", None)
        payload.pop("end_time", None)
        return payload, issue
    if len(clocks) >= 2 and (has_date or payload.get("_date_hint")):
        source = text if has_date else payload["_date_hint"]
        dates = legacy._CLOCK_TOKEN_RE.sub("", source)
        try:
            start, end = legacy._parse_leave_span(dates)
            if not (start and end):
                one_day = legacy._DATE_RE.search(dates)
                if one_day:
                    start = end = datetime.fromisoformat(one_day.group(1))
            if start and end:
                first_h, first_m = map(int, clocks[0].split(":"))
                last_h, last_m = map(int, clocks[1].split(":"))
                start = start.replace(hour=first_h, minute=first_m, second=0)
                end = end.replace(hour=last_h, minute=last_m, second=0)
                if start >= end:
                    payload.pop("start_time", None)
                    payload.pop("end_time", None)
                    return payload, "结束时间必须晚于开始时间，请重新提供起止时间。"
                payload["start_time"] = start.isoformat()
                payload["end_time"] = end.isoformat()
        except (ValueError, OverflowError):
            return payload, "日期无效，请重新提供真实的起止日期和时间。"
    return payload, None


def fill_feedback(text, previous, extracted):
    payload = dict(previous)
    if "投诉" in text:
        payload["ticket_type"] = "complaint"
    elif "建议" in text:
        payload["ticket_type"] = "suggestion"
    if any(k in text for k in ("学习相关", "学习类", "课程", "教学", "老师", "班主任")):
        payload["category"] = "learning"
    elif any(k in text for k in ("公司相关", "公司类", "公司", "合同", "收费", "顾问服务")):
        payload["category"] = "company"
    content = extracted.get("content", "")
    explicit = re.search(r"(?:内容|具体情况)[：:](.+)", text)
    if explicit:
        content = explicit.group(1).strip()
    if previous.get("content") and not explicit and any(word in text for word in ("改成", "改为", "换成")) and "内容" not in text:
        content = ""
    if not content and not previous.get("content") and legacy._has_substance(text):
        content = text
    if content and content in text and len(content) >= (2 if explicit else 8):
        payload["content"] = content[:10000]
    return payload


def local_understanding(text, task):
    intent=route(text.replace("请个假", "请假"))["intent"]
    fields={}
    if intent=="psych" and not high_risk_hits(text):
        intent="support"
    if intent=="feedback" and not task and not guidance.explicit_feedback(text) and not any(w in text for w in ("我的投诉","投诉状态","投诉处理","反馈状态")):
        intent="support"
    if guidance.explicit_feedback(text):
        intent="feedback"
    if legacy._academic_question(text) or any(w in text for w in ("我的资料","我的学籍","我的信息","我是谁")):
        intent="profile"
    if re.search(r"我(?:现在|目前)?(?:在哪(?:里|儿)?留学|(?:去|在)(?:哪个|什么)国家留学)|我的留学(?:国家|去向|地区)", text):
        intent="profile"
    if re.search(r"我.*(?:在哪里|在哪儿|到哪一步|什么阶段|到哪个阶段)",text) and intent!="profile":
        intent="location" if "哪里" in text or "哪儿" in text else "progress"
    if re.search(r"我(?:现在|目前|已经|已)?(?:人|身)?在.{0,16}(?:吗|么|[？?])", text):
        intent="location"
    if re.search(r"我.{0,6}(?:入学|到达|抵达).{0,6}(?:吗|么|[？?])", text):
        intent="profile"
    if any(w in text for w in ("报警","警察","救护车","火警","急救电话","入境卡","SGAC","学生准证","图书馆","交通","地铁","公交","乘车","车票","买票","住宿申请","银行卡乘车","租房","看病","医院")) and intent not in ("leave_create","feedback"):
        intent="ask"
    if re.search(r"(?<![A-Za-z])(?:mrt|u-bahn|s-bahn)(?![A-Za-z])", text, re.I) and intent not in ("leave_create", "feedback"):
        intent="ask"
    if any(w in text for w in ("先聊聊","想聊聊","暂不反馈","一起梳理","不确定反馈分类","先了解解决办法")):
        intent="support"
    if text in CANCEL or text in ("先不办了","取消本次办理") or re.search(r"(?:不想|不打算|先不|不再)(?:再)?(?:投诉|反馈|请(?:个)?假)(?:了|啦)?[。！!]*$",text.strip()):
        intent="cancel"
    if text in CONFIRM:
        intent="confirm"
    if intent in ("other","chat") and any(word in text for word in ("想家","想回家","孤单","说说话","倾诉","聊聊","有点累","累了","生活有些累")):
        intent="support"
    if intent in ("other", "chat", "ask") and dialogue.general_question(text) and not knowledge.resolve_question(text).get("category"):
        return AssistantUnderstanding(intent="chat",fields={})
    if task and task.kind=="leave" and (text.startswith(("事由：","原因：")) or (guidance.for_task(task.kind,task.payload,task.status) or {}).get("field")=="reason" and intent=="ask" and not re.search(r"怎么|哪里|如何|什么|[？?]",text)):
        intent="leave_create"
        fields["reason"]=text.split("：",1)[-1]
    if intent=="other":
        intent="chat"
        if task and text not in legacy._REASON_STOPWORDS:
            guide=guidance.for_task(task.kind,task.payload,task.status) or {}
            if task.kind=="leave" and (legacy._looks_like_leave_slot(text) or legacy._CLOCK_TOKEN_RE.search(text) or legacy._DATE_RE.search(text) or re.search(r"今天|明天|后天|事由|原因|身体不适|家里有事|发烧|感冒|肚子疼",text)):
                intent="leave_create"
            elif task.kind=="leave" and guide.get("field")=="reason" and not re.search(r"你好|谢谢|再见|故事|天气|什么|怎么|[？?]",text):
                intent="leave_create"
                fields["reason"]=text
            elif task.kind=="feedback" and (legacy._has_substance(text) or text in ("学习相关","公司相关","正式投诉","提建议","建议") or text.startswith("内容：")):
                intent="feedback"
    return AssistantUnderstanding(intent=intent,fields=fields)


def _needs_field_understanding(understanding, query):
    """Only substantive business text needs bounded model-assisted extraction."""
    if understanding.intent not in ("leave_create", "feedback"):
        return False
    menu = re.sub(r"[。！!？?\s]", "", query).replace("请个假", "请假")
    return menu not in {"请假", "我要请假", "我想请假", "病假", "事假", "紧急事由",
                        "我要投诉", "我想投诉", "投诉", "我要反馈", "提建议", "建议",
                        "学习相关", "公司相关", "正式投诉"}


async def run_turn(db, *, student_id, query, conversation_id, use_dify, on_text=None, **_):
    generation_deadline=monotonic()+15
    cid=conversation_id
    if cid and assistant_store.get_conversation(db,student_id,cid) is None:
        raise BusinessError(404,"对话不存在")
    if not cid:
        cid=assistant_store.create_conversation(db,student_id,query[:28])["id"]
    history=assistant_store.recent_turns(db,cid,limit=20)
    current=repo.latest_task(db,student_id,cid,active=True)
    expected=(current.id,current.version) if current else None
    old_payload=dict(current.payload) if current else {}
    kind=current.kind if current else None
    understanding=local_understanding(query,current)
    context=assistant_context.snapshot(db,student_id)
    task_context=tasks.view(current)
    resolved=knowledge.resolve_question(query, history)
    if resolved.get("category") and understanding.intent in ("chat", "ask"):
        understanding.intent="ask"
    country_query=resolved["query"] if resolved.get("contextual") else query
    country=knowledge.country_for(country_query,context["profile"],history)
    memories=assistant_mem0.search_memories(db,student_id=student_id,query=query,limit=5)
    db.commit()
    source="local"
    safety_state=dialogue.safety_context(query, history)
    direct_risk=bool(high_risk_hits(query))
    explicit_task=bool(re.search(r"请假|病假|事假|事由[:：]|原因[:：]", query))
    safety_followup=(safety_state["active"] and not direct_risk
                     and understanding.intent not in ("confirm", "cancel")
                     and not explicit_task and not guidance.explicit_feedback(query))
    safety_active=direct_risk or safety_followup
    initial_prefix=dialogue.safety_initial_prefix(query, history, context=safety_state) if safety_active else ""
    if initial_prefix and on_text:
        on_text(initial_prefix)
    general=understanding.intent in ("chat", "ask") and not resolved.get("category") and dialogue.general_question(query)
    if high_risk_hits(query):
        # Preserve the existing alert writer exactly once for a current direct disclosure.
        result=legacy.handle_chat(db,student_id=student_id,message=query,history=history,memory_notes=memories,generate_reply=False)
        result["reply"]=dialogue.safety_reply(query, history, context=safety_state)
    elif safety_followup:
        # A historical disclosure affects support only; never replay its alert side effect.
        result=_pack(dialogue.safety_reply(query, history, followup=True, context=safety_state), "support")
    else:
        if use_dify and _needs_field_understanding(understanding, query):
            try:
                model=await assistant_dify.understand(query=query,history=history,context=context,task=task_context,
                    memories=memories,user_key=assistant_mem0.user_key(student_id),country=country or "",
                    stream_plan=True, overall_timeout=5)
                if understanding.intent=="chat" and model.intent not in ("confirm","cancel","psych"):
                    understanding=model
                else:
                    understanding.fields={**understanding.fields,**model.fields}
                    understanding.reply=model.reply
                    understanding.search_query=model.search_query
                    understanding.evidence_ids=model.evidence_ids
                source="dify"
            except BusinessError:
                log.warning("Student Dify unavailable; using reviewed knowledge and guided fallback")
                source="local_fallback"
        intent=understanding.intent
        if general:
            intent="general"
        elif intent in ("chat", "ask") and dialogue.emotional_disclosure(query):
            intent="support"
        # Soft dissatisfaction never authorizes a feedback workflow, even if the model routes it there.
        if intent=="feedback" and not current and not guidance.explicit_feedback(query) and not any(w in query for w in ("我的投诉","投诉状态","投诉处理","反馈状态")):
            intent="support"
        if intent=="leave_create" and kind!="leave" and not re.search(r"请(?:个)?假|病假|事假|紧急事由",query):
            intent="support"
        if intent in ("confirm","cancel"):
            if query not in CONFIRM and intent=="confirm":
                result=_pack("需要你核对待提交的信息后，再点击确认提交。")
            elif not expected:
                result=_pack("目前没有正在办理的事项。我们可以继续聊，也可以开始一件新的事情。")
            else:
                decision=tasks.decide(db,student_id,expected[0],expected[1],cancel=intent=="cancel")
                result=_pack("好，这次先不提交了。" if intent=="cancel" else "已经提交，接下来等待负责人员处理。", "task_result",task=decision)
        elif intent=="progress":
            result=assistant_context.progress_result(context,query)
        elif intent=="profile":
            profile=context["profile"]
            result=_pack("这是当前账号关联的学籍资料。未登记的部分可以请老师核对补充。","profile",cards=[
                {"title":"我的学籍","fields":[{"label":label,"value":str(profile.get(key) or "未登记")} for key,label in
                (("student_name","姓名"),("student_no","学号"),("school","院校"),("major","专业"),("project_name","所属项目"),("class_name","当前班级"),("class_teacher","班主任"),("abroad_country","留学去向"))]}])
        elif intent=="location":
            result=_pack("我没有实时定位信息。学籍里的留学去向和院校申请可以查询；如果想找附近的生活服务，可以告诉我你当前所在的国家和城市。","location")
        elif intent=="feedback" and any(w in query for w in ("我的投诉","投诉处理","反馈处理","投诉状态","反馈状态")):
            rows=feedback_service.student_complaints(db,student_id,None,10)
            labels={"pending":"待处理","processing":"处理中","resolved":"已解决","closed":"已关闭"}
            result=_pack("最近的反馈记录如下。" if rows else "暂时没有查到你的反馈记录。","feedback_query",cards=[{"title":"反馈 #"+str(row.id),"fields":[{"label":"内容","value":row.content},{"label":"状态","value":labels.get(row.status,row.status)},{"label":"处理结果","value":row.solution or "尚未登记"}]} for row in rows])
        elif intent=="leave_query":
            result=legacy._leave_query(db,student_id)
        elif intent=="deadline":
            result=legacy._deadline(db,student_id)
        elif intent=="general":
            result=_pack(dialogue.general_fallback())
        elif intent=="ask":
            search=query+" "+understanding.search_query
            result=knowledge.answer(db,country,search,understanding.evidence_ids, original_query=query, history=history)
            source="reviewed_knowledge"
        elif intent in ("leave_create","feedback"):
            new_kind="leave" if intent=="leave_create" else "feedback"
            previous=old_payload if kind==new_kind else {}
            if new_kind=="leave":
                payload,issue=fill_leave(query,previous,understanding.fields)
            else:
                payload,issue=fill_feedback(query,previous,understanding.fields),None
                if not payload.get("content") and guidance.explicit_feedback(query):
                    # Only this conversation's student words; never long-term memories or assistant guesses.
                    for turn in reversed(history):
                        text=turn.get("content", "")
                        if turn.get("role")=="user" and len(text)>=8 and any(w in text for w in ("环境","卫生","噪音","迟到","态度","收费","合同","设施")):
                            payload["_context"]=text.split("，我想先聊",1)[0]
                            break
            if "修改请假时间" in query:
                payload.pop("start_time",None)
                payload.pop("end_time",None)
            if "修改反馈内容" in query:
                payload.pop("content",None)
            draft=tasks.save_draft(db,student_id,cid,new_kind,payload,expected)
            guide=draft.get("guide") or {}
            result=_pack(issue or guide.get("question") or "我们继续核对一下。",intent,task=draft)
        elif intent in ("support","psych"):
            result=guidance.support(query,history,current)
            model_reply=safe_context_reply(understanding.reply, query, history)
            # Reply may be conversational; choices and executable actions remain server-owned.
            if model_reply:
                result["reply"]=model_reply
        else:
            if re.search(r"记得我.*(?:叫|名字)|我叫(?:啥|什么)",query):
                name=legacy._name_from_memory_list(memories)
                reply=(f"你之前告诉我，希望叫你{name}。这是聊天中记下的称呼，学籍资料可以另外核对。" if name else "我还没有记下你希望使用的称呼。你可以告诉我怎么称呼你。")
            else:
                reply=safe_context_reply(understanding.reply, query, history)
                if not reply:
                    name=legacy._heard_name(query)
                    reply=f"你好，{name}，很高兴认识你。今天想聊点什么？" if name else "你好呀，我在。留学生活里的问题、最近的烦恼，或者需要办理的事情，都可以和我说。"
            result=_pack(reply)
    if safety_active:
        cards=assistant_safety_resources.cards_for(safety_state)
        if cards:
            result["cards"]=cards
        safety_state["verified_resources_available"]=bool(cards)
    answer=result.get("reply") or result.get("answer") or ""
    kind=result.get("intent", "chat")
    # Public knowledge is already reviewed and organized for this exact question.
    # Return it directly; never pay a second model call to recite or fake-stream it.
    # Ordinary dialogue has one read-only visible generation call, no planning.
    name_question=bool(re.search(r"记得我.*(?:叫|名字)|我叫(?:啥|什么)", query))
    visible_model = use_dify and (safety_active or not name_question and kind in ("support", "chat"))
    if visible_model:
        db.commit()
        emit=on_text or (lambda _text: None)
        reviewed_fallback=answer
        remaining=max(0.001,generation_deadline-monotonic())
        safety_options={"safety_context":safety_state,"initial_prefix":initial_prefix} if safety_active else {}
        try:
            answer=await assistant_dify.stream_reply(
                query=query,context=context,history=history,memories=memories,
                user_key=assistant_mem0.user_key(student_id),country=country or "",
                reviewed_reply=answer,kind="safety_support" if safety_active else "general" if general else kind,on_text=emit,
                first_content_timeout=min(12,remaining),overall_timeout=remaining,**safety_options)
            source="dify"
        except StudentReplyInterrupted as exc:
            # Only the stream gate can certify this prefix. Keep exactly what was shown.
            has_model_text=bool(exc.safe_partial and exc.safe_partial != initial_prefix)
            source="dify_partial" if has_model_text else "local_safety_fallback" if safety_active else "local_fallback"
            if has_model_text:
                answer=exc.safe_partial
                result["reply_notice"]="回复中断，以上内容已保留"
            elif safety_active:
                # Only reviewed local text may extend an already-emitted safety seed.
                answer=reviewed_fallback
                result["reply_notice"]="补充回复暂未完成，先按以上步骤寻求现实中的支持。"
                emit(answer)
            else:
                answer=dialogue.general_fallback() if general else "这次回复未能完成，请稍后重试。"
                result["reply_notice"]="回复中断，请重试"
                emit(answer)
            log.warning("Student reply interrupted: %s", exc.reason_code)
        except BusinessError:
            log.warning("Student visible generation unavailable")
            source="local_safety_fallback" if safety_active else "local_fallback"
            answer=reviewed_fallback if safety_active else dialogue.general_fallback() if general else "这次回复未能完成，请稍后重试。"
            result["reply_notice"]="补充回复暂未完成，先按以上步骤寻求现实中的支持。" if safety_active else "回复中断，请重试"
            emit(answer)
    elif on_text:
        on_text(answer)
    if result.get("cards") and kind in ("progress", "profile", "feedback_query", "leave_query", "deadline"):
        result["facts_kind"]="student_record"
    presentation={key:result[key] for key in ("intent","choices","cards","knowledge_keys","facts_kind","reply_notice") if key in result}
    try:
        assistant_store.append_turn(db,student_id=student_id,conversation_id=cid,user_text=query,assistant_text=answer,
            title_hint=query[:28],presentation=presentation)
    except Exception:
        db.rollback()
        log.exception("Student transcript save failed; durable business receipt retained")
        result["history_warning"]="对话记录保存失败；办理结果可在对应栏目核对"
    try:
        if not safety_active:
            assistant_mem0.remember_turn(db,student_id=student_id,user_text=query,assistant_text=answer,conversation_id=cid)
    except Exception:
        db.rollback()
        log.exception("Student self-reported memory save failed")
    result.update(answer=answer,reply=answer,conversation_id=cid,source=source)
    if "task" not in result:
        result["task"]=tasks.view(repo.latest_task(db,student_id,cid))
    return result


def knowledge_result(db,student_id,query):
    context=assistant_context.snapshot(db,student_id)
    return knowledge.answer(db,knowledge.country_for(query,context["profile"]),query)
