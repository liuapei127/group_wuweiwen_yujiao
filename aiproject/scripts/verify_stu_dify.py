"""One-shot STU Dify + website assistant smoke (local)."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

API = "http://127.0.0.1:8000"
DIFY = "http://127.0.0.1:8090/v1/chat-messages"


def call(method: str, url: str, payload=None, headers=None):
    data = None if payload is None else json.dumps(payload).encode()
    hdr = {"Content-Type": "application/json"}
    if headers:
        hdr.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdr, method=method)
    with urllib.request.urlopen(req, timeout=90) as resp:
        return resp.status, json.loads(resp.read().decode())


def main() -> int:
    from app.core.config import get_settings

    settings = get_settings()
    key = settings.stu_dify_api_key.get_secret_value().strip()
    if not key:
        print("FAIL STU_DIFY_API_KEY empty")
        return 1
    print("OK key", key[:12] + "...")

    # Direct Dify
    st, body = call(
        "POST",
        DIFY,
        {
            "inputs": {"student_access_token": "", "history_json": "[]"},
            "query": "查进度",
            "user": "verify_stu_dify",
            "response_mode": "blocking",
        },
        {"Authorization": "Bearer " + key},
    )
    ans = (body.get("answer") or "") if isinstance(body, dict) else ""
    print("OK dify_direct" if st == 200 and ans else "FAIL dify_direct", ans[:80])
    if st != 200 or not ans:
        return 1

    # Website login + assistant through FastAPI (which may call Dify)
    _, login = call(
        "POST",
        API + "/api/v1/visitors/login",
        {"username": "stu_demo", "password": "StuDemo_123456"},
    )
    token = (login.get("data") or login).get("access_token")
    if not token:
        print("FAIL login")
        return 1
    wh = {"Authorization": "Bearer " + token}
    _, created = call("POST", API + "/api/v1/student/assistant/conversations", {}, wh)
    cid = (created.get("data") or {}).get("id")
    cases = [
        ("宿舍环境太差了", ("投诉", "建议", "咨询")),
        ("我想请假 肚子疼", ("补充", "日期", "交上", "病假")),
        ("3号到4号", ("交上", "换一组日期", "病假")),
    ]
    for query, needles in cases:
        _, resp = call(
            "POST",
            API + "/api/v1/student/assistant",
            {"query": query, "conversation_id": cid},
            wh,
        )
        data = resp.get("data") or {}
        answer = data.get("answer") or ""
        src = (data.get("data") or {}).get("source") if isinstance(data.get("data"), dict) else data.get("intent")
        ok = (
            any(n in answer for n in needles)
            and "我记得你之前提过" not in answer
            and "学生说：" not in answer
            and "什么吗" not in answer
        )
        print(("OK" if ok else "FAIL"), query, "src="+str(src), answer[:90])
        if not ok:
            return 1

    # Fresh thread for identity so an open leave slot cannot swallow the name.
    _, created2 = call("POST", API + "/api/v1/student/assistant/conversations", {}, wh)
    cid2 = (created2.get("data") or {}).get("id")
    for query, needles in [
        ("我叫小明", ("记住", "小明")),
        ("你还记得我叫什么吗", ("小明",)),
    ]:
        _, resp = call(
            "POST",
            API + "/api/v1/student/assistant",
            {"query": query, "conversation_id": cid2},
            wh,
        )
        data = resp.get("data") or {}
        answer = data.get("answer") or ""
        src = (data.get("data") or {}).get("source") if isinstance(data.get("data"), dict) else None
        ok = any(n in answer for n in needles) and "什么吗" not in answer
        print(("OK" if ok else "FAIL"), query, "src="+str(src), answer[:90])
        if not ok:
            return 1
    print("ALL_PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as exc:
        print("HTTP", exc.code, exc.read().decode()[:400])
        raise SystemExit(1)
