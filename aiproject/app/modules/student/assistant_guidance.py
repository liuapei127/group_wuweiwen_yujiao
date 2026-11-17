"""Small, explicit next steps for students. No business side effects."""

def for_task(kind, payload, status):
    if status not in ("collecting", "awaiting_confirmation"):
        return None
    if status=="awaiting_confirmation":
        return {"kind":"review","question":"请核对这些信息，确认后我再帮你提交。","step":4,"total":4}
    if kind=="leave":
        if not payload.get("leave_type"):
            return {"kind":"choice","question":"可以的，你这次想请哪一种假？","step":1,"total":4,"choices":[
                {"label":"病假","description":"身体不适或需要就医","query":"病假"},
                {"label":"事假","description":"个人事务需要处理","query":"事假"},
                {"label":"紧急事由","description":"突发事情需要请假","query":"紧急事由请假"}]}
        if not payload.get("start_time") or not payload.get("end_time"):
            return {"kind":"datetime","question":"准备从什么时候请到什么时候？","step":2,"total":4,
                    "hint":"请选择开始和结束时间（北京时间），也可以直接在下方告诉我。"}
        return {"kind":"text","question":"这次请假是因为什么呢？简单说明就好。","step":3,"total":4,"field":"reason","placeholder":"例如：需要去医院复查"}
    if not payload.get("ticket_type"):
        return {"kind":"choice","question":"你希望用哪种方式反馈这件事？","step":1,"total":4,"choices":[
            {"label":"正式投诉","description":"希望按投诉流程处理","query":"正式投诉"},
            {"label":"提出建议","description":"希望提出改进意见","query":"提建议"}]}
    if not payload.get("category"):
        return {"kind":"choice","question":"这件事主要和哪方面有关？","step":2,"total":4,"choices":[
            {"label":"课程与学习","description":"课程、教学或学习管理","query":"学习相关"},
            {"label":"公司服务","description":"合同、收费或顾问服务","query":"公司相关"},
            {"label":"我不确定","description":"先一起梳理，不急着选","query":"不确定反馈分类，先帮我分析"}]}
    return {"kind":"text","question":"可以说说具体发生了什么吗？涉及的时间和情况有助于后续核对。","step":3,"total":4,"field":"content","suggested_text":payload.get("_context", ""),"placeholder":"说说发生的事情，以及你希望如何改进"}


def explicit_feedback(text):
    import re
    if re.search(r"(?:不(?:是)?(?:想|要|用|打算|希望|准备|需要)|暂不|先不).{0,6}(?:投诉|反馈|建议)",text):
        return False
    return bool(re.search(r"(?:我要|我想|希望|决定|请帮我|帮我准备|帮我提交|我想要)(?:正式)?(?:投诉|反馈|提建议)|^(?:正式投诉|提建议|建议)$",text))


def support(text, history=(), task=None):
    choices=[]
    if "不确定反馈分类" in text:
        return {"reply":"我们先分清这件事。课程、教学和学习管理属于学习相关；合同、收费或顾问服务属于公司服务。如果仍不确定，可以具体说说涉及谁、发生了什么，再决定是否反馈。",
            "intent":"support","choices":[{"label":"课程与学习","query":"学习相关"},{"label":"公司服务","query":"公司相关"}] if task else []}
    if any(word in text for word in ("环境","卫生","噪音","太吵","宿舍","设施")):
        reply="具体是哪方面最影响你，卫生、噪音还是设施？你可以先说说，我们一起看看有什么办法。"
        choices=[{"label":"卫生情况","query":"主要是卫生情况，我想先聊聊解决办法"},{"label":"噪音影响","query":"主要是噪音影响，我想先聊聊解决办法"},{"label":"设施问题","query":"主要是设施问题，我想先聊聊解决办法"}]
        if any(word in text for word in ("主要是","卫生情况","噪音影响","设施问题")):
            reply="可以先把影响你的时间、地点和具体情况记下来，方便判断问题是否反复发生。再查学校或住宿方公布的管理渠道，说明影响并询问可行的改进办法。你希望先一起梳理，还是准备一份反馈？"
            choices=[{"label":"先一起梳理","query":"先一起梳理这件事，暂不反馈"},{"label":"帮我准备反馈","query":"帮我准备反馈"}]
    elif any(word in text for word in ("想家","孤单","孤独","回家")):
        reply="在外面生活，有时会特别想念熟悉的人和地方。最近是遇到了具体的事情，还是单纯很想家？你愿意的话可以慢慢说。"
        choices=[{"label":"我想聊聊","query":"我只是想家了，想聊聊"},{"label":"一起想点办法","query":"想家时可以试试哪些日常小办法"}]
        if "办法" in text:
            reply="可以先试一件负担很小的事：和熟悉的人约个方便的聊天时间，或给今天安排一件熟悉、喜欢的小事。你不用一下子适应所有变化。哪一种对你更容易做到？"
            choices=[]
    elif any(word in text for word in ("压力","焦虑","烦","难过","跟不上","累")):
        reply="最近是什么让你最有压力，课程、生活安排，还是与人相处？我们可以先挑一件最困扰你的事情，慢慢理清楚。"
        choices=[{"label":"课程与学习","query":"最近课程跟不上，想一起想办法"},{"label":"生活适应","query":"最近适应生活有些累，想聊聊"}]
    else:
        reply="我在听。你可以先说说发生了什么，以及你现在最希望得到哪种帮助；可以一起想办法，也可以先聊一聊。"
    return {"reply":reply,"intent":"support","choices":choices}


def safe_social_reply(reply):
    import re
    if not reply or re.search(r"(?:已经|已)(?:帮你|为你)?(?:联系|通知|提交|转交|批准)|(?:我|也)(?:可以|能|会)(?:帮你|为你|代你)?(?:联系|通知|转交|呼叫)|https?://|(?<!\d)\d{5,}(?!\d)|(?:电话|地址)(?:是|为)[：:]?|你患有|你这是抑郁症|我诊断|建议服用|毫克",reply):
        return None
    return reply
