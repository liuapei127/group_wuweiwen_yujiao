"""Student-facing dialogue decisions without business or alert side effects.

Only recent user words from the owned conversation carry a safety disclosure.
Official facts, public knowledge and executable task state remain elsewhere.
"""
import re
from .assistant_safety import high_risk_hits

_EMOTIONAL = re.compile(r"打压|欺负|霸凌|侮辱|威胁|难受|害怕|绝望|撑不住|受不了|委屈|孤立|不知道(?:该|能|要)?怎么办|帮帮我|救救我|不安全|没有人陪|没人陪")
_SUPPORT_REQUEST = re.compile(r"陪着?我|陪我|帮帮我|救救我|我(?:现在)?(?:该|能|要|应该)(?:怎么|如何)(?:办|做)|我不知道")
_SAFETY_CONTINUATION = re.compile(
    r"^(?:因为|就是|是因为|主要是|然后|可是|但是)|打压|欺负|霸凌|侮辱|威胁|难受|害怕|绝望|"
    r"不知道(?:该|能|要)?怎么办|没人|没有人|一个人|帮帮我|救救我|陪陪我|不敢|不安全|楼顶|天台|阳台|安全|家人|朋友")
_RESOLVED = re.compile(r"(?:我)?(?:现在|目前|已经|已|暂时)(?:感觉|觉得)?(?:很|比较)?安全(?:了|的)?|我在安全的地方|"
    r"(?:我)?(?:现在|已经|已)(?:和(?:朋友|家人|同学)在一起|有(?:朋友|家人|同学|人)陪(?:着我|我)?)")
_UNSAFE_STATUS = re.compile(r"不安全|没(?:有)?人陪|无人陪|没有.{0,6}(?:朋友|家人|同学).{0,4}(?:陪|一起)|还有危险|仍然危险|不想活|想死|想自杀")
_TOPIC_SWITCH = re.compile(r"换个话题|接下来.*(?:问|聊)")
_PROTECTED_FACTS = re.compile(r"我的|我是谁|我叫|叫我|记住|记忆|请假|投诉|反馈|申请|学籍|学校|院校|课程|老师|班主任|"
    r"考试|截止|留学|签证|准证|入境|护照|医院|看病|保险|药|诊断|法律|律师|报警|警察|账户|银行卡|租房")
_QUESTION = re.compile(r"是谁|什么是|是什么|谁是|首都|哪一年|哪年|为什么|为何|怎么|如何|哪里|哪儿|多少|区别|介绍|解释|[？?]")


def _resolved(text):
    # A negated or contradictory status must never close a safety conversation.
    return bool(_RESOLVED.search(text) and not _UNSAFE_STATUS.search(text))


def general_question(query):
    """Allow ordinary factual discussion without treating it as student business."""
    text = str(query or "").strip()
    self_state_question = re.search(r"我(?:现在|目前|已经|已)?(?:人|身)?在.{0,16}(?:吗|么|[？?])|我.{0,6}(?:入学|到达|抵达).{0,6}(?:吗|么|[？?])", text)
    return bool(_QUESTION.search(text) and not self_state_question and not _PROTECTED_FACTS.search(text)
                and not _EMOTIONAL.search(text) and not _SUPPORT_REQUEST.search(text) and not high_risk_hits(text))


def emotional_disclosure(query):
    return bool(_EMOTIONAL.search(query) or _SUPPORT_REQUEST.search(query))


def _self_disclosure(text):
    """A quote, hypothetical or explicit denial is not a personal risk statement."""
    value = re.sub(r"\s+", "", str(text or ""))
    if not high_risk_hits(value):
        return False
    if re.search(r"我(?:并不|不是|不会|不|没有)(?:真的)?(?:想|要|打算|准备|想过)?(?:自杀|自尽|轻生|跳楼|自残|割腕|伤害自己)", value):
        return False
    if re.search(r"^(?:我(?:的)?(?:朋友|同学|家人)|他|她|别人)(?:现在|很|也)?想(?:自杀|跳楼|死)|^(?:如果|假设)|(?:小说|电影|台词|文章|新闻).{0,8}(?:写|说|讲|提到|描述|出现)|(?:同学|朋友|别人|他|她|有人)说.{0,12}(?:自杀|跳楼|想死)", value):
        return False
    return True


_URGENT_HELP = re.compile(r"(?:哪里|哪儿|附近|当地|这里).{0,12}(?:求助|急救|紧急|医院|帮助)|(?:该|能|可以|要|应该).{0,6}(?:联系谁|找谁|求助)|(?:联系|找)谁|(?:紧急|马上|立即).{0,8}(?:求助|帮助|医院|救护|急救)")
_ACK = re.compile(r"^(?:好(?:的|吧)?|嗯(?:嗯)?|知道了|明白了|谢谢(?:你)?|可以|行|是的|对|然后呢)[。！!，,\s]*$")
_ALONE = re.compile(r"我(?:现在|目前)?(?:是|就|只有|还是|仍是)?一个人|我(?:现在|目前)?独自|(?:身边)?没(?:有)?人(?:陪|在)?|无人陪")
_ACCOMPANIED = re.compile(r"我(?:现在|目前)?不是一个人|(?:朋友|家人|同学|室友|工作人员|保安|老师)(?:已经|现在|正|在)?(?:来了|在我身边|在身边|陪着?我|和我在一起)|我(?:已经|现在|目前)?和(?:朋友|家人|同学|室友|工作人员|保安|老师)(?:在)?一起")
_PHYSICAL_SAFE = re.compile(r"我(?:现在|目前|已经|已|暂时)?(?:感觉|觉得)?(?:很|比较)?安全(?:了|的)?(?=$|[，,。！!；;\s])|我(?:已经|现在)?在安全(?:的)?地方|(?:已经|已)(?:离开|远离)(?:了)?(?:楼顶|天台|阳台|危险位置)")
_PHYSICAL_UNSAFE = re.compile(r"不安全|安全不了|安全不下来|(?:不能|无法|没法|不敢)保证.{0,10}安全|还有危险|仍然危险|我(?:现在|目前)?(?:还)?在(?:楼顶|天台|阳台)|还没(?:有)?离开(?:楼顶|天台|危险)")
_LOCATION_CLAUSE = re.compile(r"^(?:我(?:现在|目前|此刻)?(?:人|身)?|现在|目前)(?:正)?在\s*([^，,。！？?；;]{1,40})$")
_LOCATION_ALIASES = ((r"纽约|new york|nyc", "US", "New York", "纽约"),
                     (r"美国|united states|\busa?\b", "US", None, "美国"),
                     (r"德国|germany", "Germany", None, "德国"),
                     (r"新加坡|singapore", "Singapore", None, "新加坡"))


def _location_update(text):
    """Return (new current-location statement, mapped self-report or None).

    Academic destination, plans and questions cannot establish a current location.
    A newer explicit denial clears an older self-report instead of silently using it.
    """
    changed, location = False, None
    for part in re.split(r"[，,。；;]", str(text or "")):
        part = part.strip()
        if not part or re.search(r"[？?]|是否|是不是|吗$|么$", part):
            continue
        if re.match(r"我(?:现在|目前)?(?:已经|已)?(?:不在|离开|离境|回国)", part):
            changed, location = True, None
            continue
        match = _LOCATION_CLAUSE.fullmatch(part)
        if not match:
            continue
        place = match.group(1).strip()
        if (re.fullmatch(r"安全(?:的)?地方|危险位置|楼顶|天台|阳台|这里|那里|家里|宿舍|学校|朋友|家人", place)
                or re.search(r"申请|研究|考虑|查看|资料|准备|计划", place)):
            continue
        changed = True
        location = {"country": None, "city": None, "label": place[:80], "evidence": part[:120]}
        for pattern, country, city, label in _LOCATION_ALIASES:
            if re.match(pattern, place, re.I):
                location = {"country": country, "city": city, "label": label, "evidence": part[:120]}
                break
    return changed, location


def _safety_continuation(text):
    # An explicit new task/topic must not be captured by a historical crisis.
    if _TOPIC_SWITCH.search(text):
        return False
    if _URGENT_HELP.search(text) or re.search(r"我.{0,12}安全(?:吗|么|[？?])", text):
        return True
    if general_question(text):
        return False
    if re.search(r"请假|病假|事假|事由[:：]|原因[:：]|正式投诉|我要投诉|我的申请|我的学籍|我的学校|公交|地铁|车票", text):
        return False
    return bool(_SAFETY_CONTINUATION.search(text) or _SUPPORT_REQUEST.search(text)
                or _ALONE.search(text) or _ACCOMPANIED.search(text) or _ACK.fullmatch(text)
                or _location_update(text)[0] or _PHYSICAL_SAFE.search(text))


def safety_context(query, history=()):
    """Read bounded, owned-conversation user statements; never long-term memory.

    The workspace verifies conversation ownership before supplying history. No
    assistant claim, quoted statement, academic destination or model output is
    promoted to a student fact by this helper.
    """
    state = {"active": False, "current_disclosure": False,
             "source": "current_conversation_user_statements", "alone": None,
             "safety": "unknown", "self_reported_location": None,
             "teacher_issue": False, "latest_user_message": str(query or ""),
             "recent_user_statements": [], "current_change": None}
    words = [str(turn.get("content") or "") for turn in history if turn.get("role") == "user"]
    words.append(str(query or ""))
    location_candidate=None
    for index, text in enumerate(words):
        current = index == len(words) - 1
        direct = _self_disclosure(text)
        location_changed, candidate_update = _location_update(text)
        if location_changed:
            location_candidate = candidate_update
        if not direct and (not state["active"] or not _safety_continuation(text)):
            state.update(active=False, alone=None, safety="unknown", self_reported_location=None,
                         teacher_issue=False, recent_user_statements=[], current_change=None)
            continue
        if direct:
            # A renewed disclosure cannot inherit an earlier claim of recovery.
            if state["safety"] == "safe":
                state["alone"] = None
                state["teacher_issue"] = False
                state["recent_user_statements"] = []
            state["safety"] = "unknown"
            state["active"] = True
            state["self_reported_location"] = location_candidate
        previous_alone, previous_safety = state["alone"], state["safety"]
        state["recent_user_statements"].append(text[:2000])
        state["recent_user_statements"] = state["recent_user_statements"][-10:]
        if _ACCOMPANIED.search(text):
            state["alone"] = False
        elif _ALONE.search(text):
            state["alone"] = True
        if _PHYSICAL_UNSAFE.search(text):
            state["safety"] = "unsafe"
        elif _PHYSICAL_SAFE.search(text):
            state["safety"] = "safe"
        changed, location = _location_update(text)
        if changed:
            state["self_reported_location"] = location
        if re.search(r"班主任.{0,12}(?:打压|欺负|威胁|侮辱)|(?:打压|欺负|威胁|侮辱).{0,12}班主任", text):
            state["teacher_issue"] = True
        if current:
            state["current_disclosure"] = direct
            state["current_change"] = ("risk" if direct else
                "unsafe" if state["safety"] == "unsafe" and previous_safety != "unsafe" else
                "alone" if state["alone"] is True and previous_alone is not True else
                "location" if changed else "ack" if _ACK.fullmatch(text) else None)
    return state


def crisis_followup(query, history):
    state = safety_context(query, history)
    return bool(state["active"] and not state["current_disclosure"])


def safety_initial_prefix(query, history=(), *, context=None):
    """Only new imminent-risk facts need an immediate reviewed safety preface."""
    state = context if context is not None else safety_context(query, history)
    if state.get("current_change") == "risk":
        return "我很担心你现在的安全。请先远离高处等危险位置，到有人在的安全地方。"
    if state.get("current_change") == "unsafe":
        return "你说现在还不安全，请先远离危险位置，去有工作人员或其他人在的安全地方。"
    if state.get("current_change") == "alone":
        return "你说现在一个人，我们先让你得到现实中的陪伴。请到有工作人员或其他人在的安全地方。"
    return ""


def safety_reply(query, history=(), *, followup=False, context=None):
    """A contextual reviewed fallback, never a claim that contact/search occurred."""
    state = context if context is not None else safety_context(query, history)
    prefix = safety_initial_prefix(query, history, context=state)
    location = state.get("self_reported_location")
    where = "你说现在在" + str(location["label"]) + "。" if location and state.get("current_change") == "location" else ""
    if not state.get("current_disclosure") and state.get("safety") == "safe" and state.get("alone") is False:
        return "谢谢你告诉我，你说已经到了安全地方，也有人陪伴。让对方继续陪你一会儿；如果愿意，我们可以慢慢聊刚才让你难受的事。"
    if state.get("alone") is False:
        return prefix + where + "你说现在有人陪着你，让对方先不要离开，我们先确保你处在安全的地方。你现在已经离开危险的位置了吗？"
    contact = "家人、朋友或其他信任的老师" if state.get("teacher_issue") else "家人、朋友或现场工作人员"
    if state.get("alone") is True:
        return prefix + where + "先联系一位你信任的" + contact + "，请对方陪着你；如果暂时联系不上，就去有工作人员值守的安全地方。你现在能联系到谁？"
    if state.get("safety") == "safe" and not state.get("current_disclosure"):
        return "你说已经到了安全的地方，可以先留在那里。现在能联系到谁来陪伴你？"
    if state.get("teacher_issue"):
        return prefix + "你提到与班主任相处的困扰，我在认真听。可以先联系家人、朋友或其他信任的老师陪伴你。你现在在安全的地方吗？"
    if _ACK.fullmatch(str(query or "")):
        return "好，我们先做刚才那一小步：到有人在的安全地方，请一个可信任的人或现场工作人员陪着你。现在能联系到谁？"
    return prefix + where + "先联系一位你信任的人陪伴你；如果无法保证自身安全，请就近找工作人员帮助联系当地紧急服务。你现在在安全的地方吗？"


def general_fallback():
    return "这次没能完成这个问题的回答，请稍后重试。"
