"""Sentence-gated visible model replies; actions and public facts remain server-owned."""
from __future__ import annotations

import re

from app.core.exceptions import BusinessError
from . import assistant_guidance
from .assistant_speak import model_text


_LOCATION = re.compile(r"(?:(?:刚|已经|已)(?:到|抵达)(?:了)?(?:德国|新加坡|国外|当地)|你(?:现在|目前|已经|已|正在|现在正在|目前正在)?(?:人|身)?在(?:德国|新加坡)(?:生活|学习|上学)?|你(?:已经|已)(?:到达|抵达|入学)|已经入学|已入学)")
_NO_STAGE = re.compile(r"还没|尚未|没有|并未|未曾|不是|不在|还在国内|没到")
_NUMBER = re.compile(r"\d+(?:[.:/-]\d+)*")
_URL = re.compile(
    r"(?:https?://|www\.)\S+|"
    r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+"
    r"(?:com|org|net|edu|gov|de|sg|io|invalid)(?=$|[^a-z0-9-])", re.I,
)
_PERSONAL_FACT = re.compile(r"你的(?:学校|院校|专业|班主任|学号|项目|班级)(?:是|为)|你(?:就读于|在.{1,20}就读)|你是.{1,32}(?:大学|学院|学校).{0,4}(?:学生|同学)")
_SIDE_EFFECT = re.compile(r"(?:已经|已)(?:为你|帮你)?(?:发出|安排|预约|登记|上报)|(?:我|也)(?:可以|能|会)(?:替你|为你|帮你|代你)?(?:提交|办理|预约|报警|拨打)")
_CONTACT = re.compile(
    r"(?:拨打|拨|电话|号码|热线|报警|(?<![a-z])(?:tel|call|phone)(?![a-z])).{0,12}(?:[\d零〇一二三四五六七八九幺][\s-]*){2,}", re.I,
)
_MEDICAL_ADVICE = re.compile(
    r"(?:建议|应该|可以|请).{0,8}(?:服用|吃药|用药)|"
    r"你(?:这是|患有|得了|患上).{0,12}(?:症|疾病|病症)|"
    r"(?:每天|每日|每次).{0,8}(?:片|粒|毫升|mg\b)", re.I,
)
_UNSUPPORTED_TOOL_PROMISE = re.compile(
    r"(?:我|我们|这边)(?:现在|正在|马上|立刻|稍后|接下来|待会儿|已经|已|会|可以|能|就|先|再|来|将){0,6}"
    r"(?:帮(?:助)?你|为你|替你|代你)?(?:联系|通知|转交|查询|查找|搜索|安排|拨打|报警)|"
    r"(?:我|我们|这边)(?:现在|正在|马上|立刻|稍后|接下来|待会儿|会|可以|能|就|先|再|来|将){0,6}"
    r"(?:帮(?:助)?你|为你|替你)?找.{0,20}(?:资源|电话|热线|机构|支持|帮助|信息|医院)", re.I,
)
_REASK_ALONE = re.compile(
    r"(?:你(?:的)?身边|你附近|现场).{0,8}有人.{0,12}(?:陪|一起).{0,4}(?:吗|么|[？?])|"
    r"你(?:现在|目前)?(?:是)?(?:独自|一个人).{0,3}(?:吗|么|[？?])|"
    r"有人在你身边.{0,3}(?:吗|么|[？?])"
)
_SAFETY_PLACE_CLAIM = re.compile(
    r"你(?:现在|目前|已经|已|正在|现在正在|目前正在)?(?:人|身)?(?:在|位于|身处)"
    r"(?P<place>德国|新加坡|纽约(?:市|州)?|美国|NewYork|Germany|Singapore|USA|UnitedStates)", re.I,
)


class StudentReplyInterrupted(BusinessError):
    """Recoverable failure carrying only already-checked, visible complete text.

    Callers may persist safe_partial and attach a notice. They must not replace
    it with a generic reply, nor append the rejected or unfinished upstream tail.
    An empty safe_partial means no content passed the gate for this request.
    """
    def __init__(self, *, safe_partial: str, reason_code: str):
        super().__init__(502, "学生助手回复未完成，请稍后重试")
        self.safe_partial = safe_partial
        self.reason_code = reason_code


def _student_words(query, history):
    return [query, *(turn.get("content", "") for turn in reversed(history) if turn.get("role") == "user")]


def _statement_text(text):
    # A student asking "have I enrolled?" has not reported that they enrolled.
    # Keep separate affirmative clauses in mixed statement/question messages.
    return "。".join(part for part in re.split(r"[，,；;。]", text)
                    if not re.search(r"[?？]|是否|是不是|(?:吗|么|呢)$", part))


def _stage_supported(claim, query, history):
    words = [re.sub(r"\s+", "", text) for text in _student_words(query, history)]
    if "入学" in claim:
        for text in words:
            if "入学" not in text:
                continue
            if _NO_STAGE.search(text):
                return False
            statement = _statement_text(text)
            if "入学" not in statement:
                return False
            if re.search(r"我(?:已经|已|刚)(?:正式)?入学", statement):
                return True
        return False
    country = "德国" if "德国" in claim else "新加坡" if "新加坡" in claim else None
    if not country:
        return False
    for text in words:
        if re.search(r"我(?:现在|目前)?(?:还|仍|依然)?在国内|我(?:还没|尚未|没有|并未)(?:出国|离境|到国外)", text):
            return False
        if country in text and _NO_STAGE.search(text):
            return False
        statement = _statement_text(text)
        if country in text and country not in statement:
            return False
        report = re.search(r"我(?:最近)?(?:现在|目前|已经|已|刚)?(?:在|到|到达|抵达)(?:了)?(德国|新加坡)", statement)
        if report and not _NO_STAGE.search(text):
            if report.group(1) != country:
                return False
            return not claim.startswith("刚") or bool(re.search(r"我(?:最近)?刚(?:到|抵达)(?:了)?" + country, statement))
    return False


def _safety_place_supported(place, safety_context):
    """Only the current conversation's parsed self-report establishes location."""
    location = safety_context.get("self_reported_location")
    if isinstance(location, dict):
        label = str(location.get("label") or "")
        city = str(location.get("city") or "")
        country = location.get("country")
    else:
        # Compatibility with isolated callers; production supplies a typed dict.
        label, city, country = str(location or ""), "", None
    normal = re.sub(r"\s+", "", label + " " + city).lower()
    if country is None:
        country = ("US" if re.search(r"纽约|newyork|美国|usa|unitedstates", normal) else
                   "Germany" if re.search(r"德国|germany", normal) else
                   "Singapore" if re.search(r"新加坡|singapore", normal) else None)
    place = place.lower()
    if place.startswith("纽约") or place == "newyork":
        return country == "US" and bool(re.search(r"纽约|newyork", normal))
    if place in ("美国", "usa", "unitedstates"):
        return country == "US"
    if place in ("德国", "germany"):
        return country == "Germany"
    if place in ("新加坡", "singapore"):
        return country == "Singapore"
    return False


def _supported_stage(claim, query, history, safety_context=None):
    if safety_context is not None and not re.search(r"刚|抵达|到达|入学", claim):
        place = _SAFETY_PLACE_CLAIM.search(claim)
        if place:
            return _safety_place_supported(place.group("place"), safety_context)
    return _stage_supported(claim, query, history)


def safe_context_reply(reply, query, history, safety_context=None):
    """A target country cannot become a claim about the student's actual stage."""
    # Line breaks and spacing must not split a contact number or prescription
    # into individually harmless fragments of the same cumulative reply.
    facts_text = re.sub(r"\s+", "", reply)
    if (not assistant_guidance.safe_social_reply(facts_text) or _PERSONAL_FACT.search(facts_text)
            or _SIDE_EFFECT.search(facts_text) or _CONTACT.search(facts_text)
            or _URL.search(facts_text) or _MEDICAL_ADVICE.search(facts_text)):
        return None
    if safety_context is not None and _UNSUPPORTED_TOOL_PROMISE.search(facts_text):
        return None
    if any(not _supported_stage(match.group(), query, history, safety_context) for match in _LOCATION.finditer(facts_text)):
        return None
    if safety_context is not None and any(not _safety_place_supported(match.group("place"), safety_context)
                                         for match in _SAFETY_PLACE_CLAIM.finditer(facts_text)):
        return None
    return reply


def _compact(text):
    return re.sub(r"\s+", "", text)


class ReplyGate:
    """Emit complete, checked upstream sentences while the request is still running.

    Knowledge output must remain a prefix of the reviewed answer. The gate
    checks every complete sentence before publishing it. Already visible text
    is monotonic: a later rejection or upstream rewrite cannot retract it.
    General public questions permit ordinary numbers; student facts, contacts,
    medical advice and all reviewed knowledge still use their stricter guards.
    """
    def __init__(self, *, kind, reviewed_reply, query, history, on_text,
                 safety_context=None, initial_prefix=""):
        self.kind = kind
        self.reviewed_reply = reviewed_reply
        self.query = query
        self.history = history
        self.on_text = on_text
        # This argument is supplied only by backend orchestration, never parsed
        # from model output. It does not authorize facts in the generated tail.
        self.initial_prefix = initial_prefix
        self.safety_context = safety_context or {}
        self.visible = initial_prefix
        self.generated_visible = ""
        self._echoing_prefix = False

    def _check(self, text):
        if not text:
            return
        if text.lstrip().startswith(("{", "[", "```")) or "\"intent\"" in text or "\"reply\"" in text:
            raise BusinessError(502, "回复格式需要重新整理")
        safety = self.safety_context if self.kind == "safety_support" else None
        for match in _LOCATION.finditer(_compact(text)):
            if not _supported_stage(match.group(), self.query, self.history, safety):
                raise BusinessError(502, "回复包含未经确认的学生阶段")
        if self.kind == "ask":
            reviewed = _compact(self.reviewed_reply)
            if not reviewed.startswith(_compact(text)):
                raise BusinessError(502, "回复包含未经核实的知识内容")
        else:
            if not safe_context_reply(text, self.query, self.history, safety):
                raise BusinessError(502, "回复需要核对事实")
            if (self.kind == "safety_support" and isinstance(self.safety_context.get("alone"), bool)
                    and _REASK_ALONE.search(_compact(text))):
                raise BusinessError(502, "回复重复询问已经明确的陪伴情况")
            facts = " ".join(_student_words(self.query, self.history))
            if self.kind != "general" and any(number not in facts for number in _NUMBER.findall(text)):
                raise BusinessError(502, "交流回复包含未经核实的信息")

    def _require_extension(self, text):
        if self.generated_visible and not text.startswith(self.generated_visible):
            raise BusinessError(502, "回复不能改写已经展示的内容")

    def _continuation(self, text):
        if not self.initial_prefix:
            return text
        # Some providers echo the exact instruction prefix. Remove that exact
        # echo once; partial echoes are withheld, not shown as a second prefix.
        if text and self.initial_prefix.startswith(text):
            return ""
        if text.startswith(self.initial_prefix):
            self._echoing_prefix = True
            return text[len(self.initial_prefix):].lstrip()
        if self._echoing_prefix:
            raise BusinessError(502, "回复不能改写安全提示")
        return text

    def accept(self, raw):
        if not isinstance(raw, str):
            raise BusinessError(502, "学生助手回复格式无效")
        clean = self._continuation(model_text(raw))
        if raw.lstrip().startswith(("{", "[", "```")):
            self._check(raw)
        self._require_extension(clean)
        # Check each new complete sentence, even when several arrive in a chunk.
        # The bad sentence and any incomplete trailing text never reach on_text.
        for match in re.finditer(r"[。！？\n]", clean):
            if match.end() <= len(self.generated_visible):
                continue
            checked = clean[:match.end()]
            self._check(checked)
            self.generated_visible = checked
            self.visible = self.initial_prefix + checked
            self.on_text(self.visible)

    def finish(self, raw):
        if not isinstance(raw, str):
            raise BusinessError(502, "学生助手回复格式无效")
        text = self._continuation(model_text(raw))
        if not text:
            raise BusinessError(502, "学生助手未返回有效答复")
        self._require_extension(text)
        self._check(text)
        if self.kind == "ask" and _compact(text) != _compact(self.reviewed_reply):
            raise BusinessError(502, "知识回复未完整保留已核实步骤")
        if text != self.generated_visible:
            self.generated_visible = text
            self.visible = self.initial_prefix + text
            self.on_text(self.visible)
        return self.visible
