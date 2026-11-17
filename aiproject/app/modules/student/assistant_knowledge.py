"""Reviewed public knowledge shared by the website, assistant and Dify external datasets."""
import hmac
import re
from app.core.config import get_settings
from app.core.exceptions import BusinessError
from app.shared.constants.study_policies import destination_labels
from . import repository

COUNTRIES = {"Germany":"德国", "Singapore":"新加坡"}


def explicit_country(text):
    selected=re.match(r"^(德国|新加坡|Germany|Singapore)[：:]",text,re.I)
    if selected:
        return "Germany" if selected.group(1).lower() in ("德国","germany") else "Singapore"
    found = [country for country, words in (("Germany",("德国","germany")),("Singapore",("新加坡","singapore"))) if any(w in text.lower() for w in words)]
    return found[0] if len(found)==1 else None


def country_for(query, profile, history=()):
    direct = explicit_country(query)
    if direct:
        return direct
    if ("德国" in query and "新加坡" in query):
        return None
    for turn in reversed(history):
        if turn.get("role")=="user" and (country:=explicit_country(turn.get("content", ""))):
            return country
    raw = str(profile.get("abroad_country") or "")
    return explicit_country(raw)


def _bigrams(text):
    clean = re.sub(r"[\W_]+", "", text.lower())
    common={"什么","怎么","如何","可以","在哪","哪里","一下","知道","请问","学生","我想","需要","德国","新加","加坡"}
    return {clean[i:i+2] for i in range(len(clean)-1)} - common


def article_matches(row, query):
    haystack = row["title"] + " " + row["content"]
    if query.lower() in haystack.lower():
        return True
    for faq in (row.get("details") or {}).get("faqs", []):
        if any(key.lower() in query.lower() for key in faq.get("keywords", [])) or len(_bigrams(query) & _bigrams(faq["question"])) >= 2:
            return True
    return False


def retrieve(db, country, query, limit=3, threshold=0.2):
    if country not in COUNTRIES:
        return []
    rows=repository.iter_life_knowledge(db,destination_labels(country))
    records=[]
    query_lower=query.lower()
    for row in rows:
        details=row.get("details") or {}
        for index, faq in enumerate(details.get("faqs", [])):
            keywords=faq.get("keywords", [])
            hits=[key for key in keywords if key.lower() in query_lower]
            overlap=len(_bigrams(query)&_bigrams(faq["question"]))
            if not hits and overlap<2:
                continue
            rank=10*sum(min(len(key),6) for key in hits)+overlap
            score=min(0.99,0.4+len(hits)*0.09+overlap*0.015)
            if score<threshold:
                continue
            key=country+"/"+row["category"]+"/"+str(index)
            records.append({"key":key,"rank":rank,"score":score,"question":faq["question"],
                "answer":faq["answer"],"title":row["title"],"category":row["category"],
                "source_title":faq.get("source_title") or row.get("source_title"),
                "source_url":faq.get("source_url") or row.get("source_url"),
                "verified_at":str(row.get("verified_at") or ""),"country":country,
                "contacts":details.get("contacts",[])})
    records.sort(key=lambda record:record["rank"],reverse=True)
    return records[:limit]


def external_retrieval(db, body, token):
    configured=get_settings().stu_knowledge_token.get_secret_value()
    if not configured or not hmac.compare_digest(configured,token):
        raise BusinessError(401,"知识检索身份无效")
    if not body.knowledge_id or not body.query.strip():
        return {"records":[]}
    rows=retrieve(db,body.knowledge_id,body.query,body.retrieval_setting.top_k,body.retrieval_setting.score_threshold)
    return {"records":[{"title":row["question"],"content":f"知识编号：{row['key']}\n适用地区：{COUNTRIES[row['country']]}\n问题：{row['question']}\n答案：{row['answer']}\n来源：{row['source_title']} {row['source_url']}\n核对日期：{row['verified_at']}",
        "score":row["score"],"metadata":{"knowledge_key":row["key"],"country":row["country"],"source_url":row["source_url"]}} for row in rows]}


def answer(db, country, query, evidence_ids=()):
    if not country:
        return {"intent":"ask","reply":"我可以帮你查。你想了解德国还是新加坡的情况？", "choices":[
            {"label":"德国","query":"德国："+query},{"label":"新加坡","query":"新加坡："+query}]}
    rows=retrieve(db,country,query,3)
    if evidence_ids:
        picked=[row for row in rows if row["key"] in evidence_ids]
        if picked:
            rows=picked
    if not rows:
        return {"intent":"ask","reply":f"这部分{COUNTRIES[country]}资料我还没有查到可靠答案。你可以补充具体问题或城市，我再帮你缩小范围；也可以先浏览生活指南。",
            "choices":[{"label":"报警与紧急求助","query":COUNTRIES[country]+"报警和急救电话"},{"label":"交通出行","query":COUNTRIES[country]+"公共交通路线怎么查"}]}
    # Public facts come verbatim from the reviewed FAQ, never from an unsupported model claim.
    best=rows[0]
    return {"intent":"ask","reply":f"以下是{COUNTRIES[country]}的相关信息：\n\n"+best["answer"],"cards":[{
        "title":best["question"],"fields":[{"label":"适用地区","value":COUNTRIES[country]},
        {"label":"信息来源","value":best["source_title"]},{"label":"核对日期","value":best["verified_at"]}],
        "source_url":best["source_url"]}],"knowledge_keys":[best["key"]],
        "choices":[{"label":row["question"],"query":COUNTRIES[country]+"："+row["question"]} for row in rows[1:]]}
