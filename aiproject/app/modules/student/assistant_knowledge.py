"""Reviewed public knowledge shared by the website, assistant and Dify external datasets."""
import hmac
import re

from app.core.config import get_settings
from app.core.exceptions import BusinessError
from app.shared.constants.study_policies import destination_labels
from . import repository

COUNTRIES = {"Germany": "德国", "Singapore": "新加坡"}
COUNTRY_WORDS = {"Germany": ("德国", "germany"), "Singapore": ("新加坡", "singapore")}


def explicit_country(text):
    text = str(text or "")
    selected = re.match(r"^(德国|新加坡|Germany|Singapore)[：:]", text, re.I)
    if selected:
        return "Germany" if selected.group(1).lower() in COUNTRY_WORDS["Germany"] else "Singapore"
    found = [country for country, words in COUNTRY_WORDS.items() if any(w in text.lower() for w in words)]
    return found[0] if len(found) == 1 else None


def country_for(query, profile, history=()):
    """A current explicit destination wins; an old comparison must not replace the profile."""
    if country := explicit_country(query):
        return country
    if all(any(word in query.lower() for word in words) for words in COUNTRY_WORDS.values()):
        return None
    resolved = resolve_question(query, history)
    if resolved["contextual"] and resolved["country"]:
        return resolved["country"]
    # Only an actual location statement/explicit country selection in this conversation
    # overrides the recorded destination. Merely asking about another country does not.
    for turn in reversed(history):
        content = turn.get("content", "")
        if turn.get("role") == "user" and re.search(r"(?:我(?:现在|目前|已经)?在|我(?:刚|已)?到|我(?:现在|目前)?住在|^(?:德国|新加坡|Germany|Singapore)[：:])", content, re.I):
            if country := explicit_country(content):
                return country
    if country := explicit_country(profile.get("abroad_country")):
        return country
    for turn in reversed(history):
        if turn.get("role") == "user" and (country := explicit_country(turn.get("content", ""))):
            return country
    return None


def _bigrams(text):
    clean = re.sub(r"[\W_]+", "", text.lower())
    common = {"什么", "怎么", "如何", "可以", "在哪", "哪里", "一下", "知道", "请问", "学生", "我想", "需要", "德国", "新加", "加坡"}
    return {clean[i:i+2] for i in range(len(clean)-1)} - common


# These cues route reviewed FAQ content, not diagnosis or personal business state.
_CATEGORY_CUES = (
    ("emergency", r"报警|警察|警方|被偷|消防|火警|急救|救护车|紧急求助|紧急号码|70999|(?<!\d)(?:110|112|999|995)(?!\d)"),
    ("medical", r"医院|医生|看病|就医|诊所|门诊|急诊|挂号|保险|报销|理赔|医保|不舒服|116117|医疗|转诊"),
    ("transport", r"地铁|mrt|公交|巴士|公共交通|u-bahn|s-bahn|车票|乘车|乘坐|换乘|进站|出站|打票|学期票|学生票|deutschlandticket|simplygo|交通卡|交通(?!事故|违章|违法|法规|处罚)|坐车|做地铁"),
    ("housing", r"租房|找房|宿舍|住宿|房东|房源|租金|冷租|暖租|押金|中介|cea|warmmiete|kaltmiete|看房"),
    ("arrival", r"入境|护照|学生准证|student.?s?\s*pass|sgac|arrival card|住址登记|bürgeramt|meldebehörde|房东确认|抵达|落地|行前|出发前|第一次去"),
    ("study", r"图书馆|借书|借阅|自习|学习|课程|作业|跟不上|录取|注册入学|迎新|international office|国际办公室"),
)


def _category(query):
    for category, pattern in _CATEGORY_CUES:
        if re.search(pattern, query, re.I):
            return category
    return None


def _topics(query, category):
    """Return specific facets before general ones; several facets may be requested."""
    patterns = {
        "medical": (("after_hours", r"晚上|夜间|周末|关闭|值班|116117"), ("language", r"英语|英文|不会德语|语言"),
                    ("specialist", r"专科|转诊|referral"), ("prepare", r"带什么|准备什么|材料|证件"),
                    ("insurance", r"保险|医保|报销|理赔|费用|免费|补贴"), ("appointment", r"急诊还是|预约门诊"),
                    ("routine", r"医院|看病|看医生|就医|不舒服|诊所|挂号")),
        "transport": (("fare_problem", r"多扣|扣费|退款|不同卡|不匹配|没刷到"),
                      ("payment", r"注册|下载|账号|app|银行卡|刷卡|支付|付钱|付款|买票|购票|钱包|余额"), ("ticket_scope", r"deutschlandticket|德国票|全国票|\bice\b|\bic\b|\bec\b"),
                      ("student", r"学生票|学期票|优惠"), ("validation", r"打票|激活|验票|闸机|纸质票"),
                      ("tap", r"进出站|同一张|换手机|上下车|同一卡"),
                      ("ride_bus", r"公交|巴士|下车铃|上车|下车"),
                      ("ride", r"怎么坐|怎样坐|坐地铁|做地铁|坐公交|坐巴士|搭地铁|搭公交|搭巴士|第一次|乘车|乘坐"),
                      ("payment", r"银行卡|刷卡|支付|付钱|付款|买票|购票|准备什么|带什么|需要什么|钱包|余额"),
                      ("route", r"路线|换乘|出发|目的地|怎么去|从.+到")),
        "housing": (("agent_check", r"中介身份|核实|cea|电话号码|注册编号"), ("safety", r"诈骗|催|没看房|先交|视频|证件照片|可信"),
                    ("costs", r"冷租|暖租|warmmiete|kaltmiete|水电"), ("contract", r"合同|签约|租金|押金"),
                    ("eligibility", r"所有学生|其他学校|nus"), ("temporary", r"临时|短租|过渡|没找到"),
                    ("application", r"申请|材料|窗口"), ("overview", r"住宿|租房|找房|宿舍")),
        "arrival": (("registration_proof", r"租约|住址证明|入住确认|wohnungsgeber"),
                    ("registration_documents", r"登记.*材料|材料.*登记|登记地点|房东确认"),
                    ("registration", r"住址登记|登记住址|两周|bürgeramt|meldebehörde"),
                    ("student_pass_eligibility", r"全日制|夜间课程|周末课程"), ("student_pass", r"学生准证|student.?s?\s*pass"),
                    ("arrival_documents", r"入境材料|旅行证件|提交成功|还要带"),
                    ("arrival_card", r"入境卡|sgac|arrival card|收费|三天"),
                    ("school_contact", r"学校哪个部门|联系学校|国际办公室"), ("arrival_checklist", r"行前|准备|抵达|到达|落地|第一次|安排")),
        "study": (("seat", r"座位|占座|订座"), ("membership", r"会员|借书|免费|借阅"), ("visit", r"开放时间|几点|设施|地址|到访"),
                  ("library", r"图书馆|自习|学习空间"), ("contact", r"邮件|发信|联系老师|咨询老师"),
                  ("deadlines", r"截止|申请时间|注册时间|逾期"), ("enrolment", r"注册|录取|迎新|报到|入学"),
                  ("learning_support", r"学习|语言|课程|跟不上|作业"), ("support", r"手续|适应|国际办公室")),
        "emergency": (("silent_police", r"不安全通话|不方便说话|不能打电话|短信|70999"),
                      ("call_details", r"说什么|怎么描述|地址|地点|邮编|拨打"),
                      ("crime_info", r"线索|举报|警方热线|1800"), ("non_emergency", r"非紧急|普通就医|一般看病"),
                      ("after_hours", r"116117|值班|周末|夜间|晚上"), ("overview", r"区分|区别|报警还是|紧急号码"),
                      ("police", r"报警|警察|警方|被偷|999|110"), ("ambulance", r"救护车|急救|消防|火警|995|112")),
    }
    found = list(dict.fromkeys(topic for topic, pattern in patterns.get(category, ()) if re.search(pattern, query, re.I)))
    if category == "transport" and re.search(r"怎么坐|怎样坐|第一次|乘坐|乘车", query):
        primary = "ride_bus" if re.search(r"公交|巴士", query) and not re.search(r"地铁|mrt|u-bahn|s-bahn", query, re.I) else "ride"
        found = [primary, *(topic for topic in found if topic != primary)]
    if category == "transport" and not found and re.search(r"交通|出行|乘车", query):
        # General orientation has a reviewed comprehensive entry in both destinations.
        # This does not broaden unknown fares/routes into invented facts.
        found = ["ride"]
    return found



_CONCISE = re.compile(r"一句话|简短|简洁|精简|简要|简单说|简单一点|简单点|短一点|短点|太长|别说这么多|不要这么多|不要这么长|少一点")
_DETAILED = re.compile(r"详细|展开|每一步|完整步骤|具体流程|具体一点|具体点|再讲讲|再说说")
_CONTEXT_BREAK = re.compile(r"请假|投诉|反馈|申请进度|我的(?:学籍|资料|老师)|查.*进度|你好|谢谢|再见|想家|心情|难过|焦虑|故事|天气|记住|我叫|我的名字|我更?喜欢|我不喜欢")
_FOLLOWUP = re.compile(r"注册|支付|付钱|付款|刷卡|买票|购票|带什么|准备什么|材料|证件|费用|多少钱|免费|怎么去|路线|换乘|怎么坐|怎样坐|打票|激活|纸质票|手机|同一张|周末|晚上|预约|转诊|保险|报销|押金|看房|资格|截止|几点")


def _subject(text, category):
    if category == "transport":
        bus = bool(re.search(r"公交|巴士|(?<![a-z])bus(?![a-z])", text, re.I))
        rail = bool(re.search(r"地铁|mrt|u-bahn|s-bahn|轨道", text, re.I))
        return "公交和地铁" if bus and rail else "公交" if bus else "地铁" if rail else "公共交通"
    return {"medical": "就医", "housing": "租房", "arrival": "入境与到达手续",
            "study": "图书馆" if "图书馆" in text or "借书" in text else "学习与入学",
            "emergency": "紧急求助"}.get(category, "")


def resolve_question(query, history=()):
    """Resolve an elliptical public question from recent student words, never model inventions.

    Explicit new domains win. A business/social turn terminates the old public topic.
    This does not establish actual location, official status or business permission.
    """
    text = str(query or "").strip()
    category = _category(text)
    result = {"query": text, "contextual": False, "category": category,
              "subject": _subject(text, category), "country": explicit_country(text),
              "concise": bool(_CONCISE.search(text)), "detailed": bool(_DETAILED.search(text))}
    if _CONTEXT_BREAK.search(text):
        return result
    if category:
        # A linked new subject keeps the country; an independent question uses
        # the recorded destination rather than an incidental older comparison.
        if not result["country"] and re.match(r"^(?:那|那么|这里|当地|同样|那边|在这里|在当地|还有)", text):
            for turn in reversed(history):
                if turn.get("role") != "user":
                    continue
                previous = str(turn.get("content") or "").strip()
                if _CONTEXT_BREAK.search(previous):
                    break
                if linked_country := explicit_country(previous):
                    result.update(query=COUNTRIES[linked_country] + "：" + text,
                                  contextual=True, country=linked_country)
                    break
                if _category(previous) or _FOLLOWUP.search(previous) or _CONCISE.search(previous) or _DETAILED.search(previous):
                    continue
                break
        return result
    country_switch = bool(re.fullmatch(r"(?:那|那么)?(?:德国|新加坡|Germany|Singapore)(?:呢|怎么样)?[？?。!！\s]*", text, re.I))
    if not (_FOLLOWUP.search(text) or result["concise"] or result["detailed"] or country_switch):
        return result
    recent_facet = ""
    recent_country = None
    for turn in reversed(history):
        if turn.get("role") != "user":
            continue
        previous = str(turn.get("content") or "").strip()
        if _CONTEXT_BREAK.search(previous):
            break
        previous_category = _category(previous)
        if previous_category:
            subject = _subject(previous, previous_category)
            country = result["country"] or recent_country or explicit_country(previous)
            prefix = (COUNTRIES[country] if country else "") + subject
            # Format-only/country-only follow-ups preserve the last actual question.
            follow = recent_facet or previous if result["concise"] or result["detailed"] or country_switch else text
            follow = re.sub(r"德国|新加坡|Germany|Singapore", "", follow, flags=re.I)
            result.update(query=prefix + "：" + follow[:400], contextual=True,
                          category=previous_category, subject=subject, country=country)
            return result
        if _FOLLOWUP.search(previous) or _CONCISE.search(previous) or _DETAILED.search(previous):
            # A country may be selected inside an elliptical facet question,
            # e.g. "德国怎么付钱", before the older transport anchor is found.
            recent_country = recent_country or explicit_country(previous)
            if not recent_facet and _FOLLOWUP.search(previous):
                recent_facet = previous
            continue
        if re.fullmatch(r"(?:那|那么)?(?:德国|新加坡|Germany|Singapore)(?:呢|怎么样)?[：:？?。!！\s]*", previous, re.I):
            recent_country = recent_country or explicit_country(previous)
            continue
        break
    return result


def article_matches(row, query):
    haystack = row["title"] + " " + row["content"]
    if query.lower() in haystack.lower():
        return True
    return any(any(key.lower() in query.lower() for key in faq.get("keywords", []))
               or len(_bigrams(query) & _bigrams(faq["question"])) >= 2
               for faq in (row.get("details") or {}).get("faqs", []))


def retrieve(db, country, query, limit=3, threshold=0.2, *, intent_query=None):
    if country not in COUNTRIES:
        return []
    # A model may expand search terms, but may not replace what the student asked.
    intent = intent_query if intent_query is not None else query
    category = _category(intent)
    topics = _topics(intent, category)
    query_lower = query.lower()
    records = []
    for row in repository.iter_life_knowledge(db, destination_labels(country)):
        details = row.get("details") or {}
        for index, faq in enumerate(details.get("faqs", [])):
            exact = re.sub(r"[\W_]+", "", intent.lower()) == re.sub(r"[\W_]+", "", faq["question"].lower())
            # Exact reviewed questions remain retrievable even where vocabulary spans domains.
            if category and row["category"] != category and not exact:
                continue
            hits = [key for key in faq.get("keywords", []) if key.lower() in query_lower]
            intent_hits = [key for key in faq.get("keywords", []) if key.lower() in intent.lower()]
            overlap = len(_bigrams(intent) & _bigrams(faq["question"]))
            topic = faq.get("topic", "")
            topic_match = topic in topics
            if not exact and not intent_hits and overlap < 2 and not topic_match:
                continue
            rank = (1000 if exact else 0) + 10 * sum(min(len(key), 6) for key in intent_hits) + overlap
            # Topic match dominates incidental words, e.g. hospital versus an appended insurance term.
            if topic_match:
                rank += max(100, 400 - 100 * topics.index(topic))
            rank += min(20, sum(min(len(key), 6) for key in hits))
            # The comprehensive entry is preferred to the short legacy entry for the same topic.
            if index == 3 and topic in ("ride", "routine", "arrival_checklist"):
                rank += 12
            score = min(0.99, 0.4 + len(intent_hits) * 0.09 + overlap * 0.015 + (0.2 if topic_match else 0))
            if score < threshold:
                continue
            records.append({"key": country + "/" + row["category"] + "/" + str(index), "rank": rank,
                "score": score, "question": faq["question"], "answer": faq["answer"],
                "short_answer": faq.get("short_answer") or faq["answer"], "title": row["title"],
                "category": row["category"], "topic": topic, "scope": faq.get("scope") or details.get("scope"),
                "source_title": faq.get("source_title") or row.get("source_title"),
                "source_url": faq.get("source_url") or row.get("source_url"),
                "verified_at": str(row.get("verified_at") or ""), "country": country,
                "contacts": details.get("contacts", [])})
    records.sort(key=lambda record: record["rank"], reverse=True)
    return records[:limit]


def external_retrieval(db, body, token):
    configured = get_settings().stu_knowledge_token.get_secret_value()
    if not configured or not hmac.compare_digest(configured, token):
        raise BusinessError(401, "知识检索身份无效")
    if not body.knowledge_id or not body.query.strip():
        return {"records": []}
    rows = retrieve(db, body.knowledge_id, body.query, body.retrieval_setting.top_k, body.retrieval_setting.score_threshold)
    return {"records": [{"title": row["question"],
        "content": f"知识编号：{row['key']}\n适用地区：{COUNTRIES[row['country']]}\n问题：{row['question']}\n答案：{row['answer']}\n来源：{row['source_title']} {row['source_url']}\n核对日期：{row['verified_at']}",
        "score": row["score"], "metadata": {"knowledge_key": row["key"], "country": row["country"], "source_url": row["source_url"]}} for row in rows]}


def answer(db, country, query, evidence_ids=(), *, original_query=None, history=()):
    if country not in COUNTRIES:
        return {"intent": "ask", "reply": "我可以帮你查。你想了解德国还是新加坡的情况？", "choices": [
            {"label": "德国", "query": "德国：" + (original_query or query)}, {"label": "新加坡", "query": "新加坡：" + (original_query or query)}]}
    original = original_query if original_query is not None else query
    resolved = resolve_question(original, history)
    intent = resolved["query"]
    rows = retrieve(db, country, intent + " " + query, 8, intent_query=intent)
    if not rows:
        if not resolved["category"] and (_FOLLOWUP.search(original) or resolved["concise"] or resolved["detailed"]):
            return {"intent": "ask", "reply": "你指的是哪件事呢？告诉我正在了解的内容，我再接着回答。", "choices": []}
        return {"intent": "ask", "reply": f"这部分{COUNTRIES[country]}资料我还没有查到可靠答案。你可以补充具体问题，我再帮你缩小范围。",
                "choices": []}
    if evidence_ids:
        tied = [row for row in rows if row["rank"] == rows[0]["rank"] and row["key"] in evidence_ids]
        if tied:
            rows.remove(tied[0])
            rows.insert(0, tied[0])
    selected = [rows[0]]
    # Generic "how to ride" and "bus" are one request, not two transport objects.
    # Only distinct, explicitly requested objects add another reviewed response.
    both_transport = (rows[0]["category"] == "transport" and re.search(r"公交|巴士", intent)
                      and re.search(r"地铁|mrt|u-bahn|s-bahn", intent, re.I)
                      and re.search(r"分别|和|以及|还有|都|、", intent)
                      and re.search(r"怎么坐|怎样坐|乘坐|乘车", intent))
    both_emergency = (rows[0]["category"] == "emergency" and re.search(r"报警|警察|警方", intent)
                      and re.search(r"急救|救护|消防|火警", intent))
    if not resolved["concise"] and (both_transport or both_emergency):
        requested = {"ride_bus", "ride"} if both_transport else {"police", "ambulance"}
        for row in rows[1:]:
            if row["topic"] in requested and row["topic"] not in {item["topic"] for item in selected}:
                selected.append(row)
            if len(selected) == 2:
                break
    content_key = "answer" if resolved["detailed"] else "short_answer"
    parts = [row[content_key] for row in selected]
    if resolved["concise"]:
        # The curated short form retains conditions; do not truncate arbitrary facts.
        parts = [re.sub(r"[。！？]\s*(?=.)", "；", parts[0]).replace("\n", "").strip()]
    reply = "\n\n".join(parts)
    sources = list({row["source_url"]: {"title": row["source_title"], "url": row["source_url"]} for row in selected}.values())
    main = selected[0]
    card = {"title": main["question"], "fields": [
        {"label": "适用地区", "value": COUNTRIES[country]},
        {"label": "信息来源", "value": main["source_title"]},
        {"label": "核对日期", "value": main["verified_at"]}],
        "source_url": main["source_url"], "sources": sources}
    # A detail request is an optional continuation, never additional unsolicited prose.
    detail_query = COUNTRIES[country] + "：" + main["question"] + "，请详细说明"
    return {"intent": "ask", "facts_kind": "public_knowledge", "reply": reply, "cards": [card],
            "knowledge_keys": [row["key"] for row in selected],
            "choices": [] if resolved["detailed"] else [{"label": "查看详细步骤", "query": detail_query}]}
