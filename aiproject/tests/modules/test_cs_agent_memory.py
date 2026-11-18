import asyncio
import json
from datetime import datetime

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.core.database import get_db
from app.modules.consultant.customer_models import CustomerIdentity
from app.modules.consultant.customer_service import attach_pending_portrait
from app.modules.consultant.models import CrmLead, VisitorIntake
from app.modules.customer_service import router as cs_router
from app.modules.customer_service import mem0, service
from app.modules.customer_service.capacity import CsChatCapacity
from app.modules.customer_service.models import CsShortTurn, CsVisitorMemory, CsVisitorProfile, CustomerChatSession
from app.modules.customer_service.memory import compose_query
from app.modules.customer_service.schemas import ChatTurn
from app.modules.visitor.models import VisitorAccount
from app.modules.visitor.router import require_visitor
from app.modules.visitor.service import VisitorPrincipal


def _client(monkeypatch, engine, visitor_id=None):
    monkeypatch.setattr(service, "get_settings", lambda: Settings(_env_file=None, cs_public_dify_api_key="test-key"))
    monkeypatch.setattr(service, "get_cs_capacity", lambda: CsChatCapacity(2, 1, 20))
    client_class = httpx.AsyncClient

    def upstream(request):
        body = json.loads(request.content)
        return httpx.Response(200, json={"answer": body["query"], "conversation_id": "cs-1"})

    monkeypatch.setattr(service.httpx, "AsyncClient", lambda **kwargs: client_class(
        transport=httpx.MockTransport(upstream), **kwargs
    ))

    def get_test_db():
        with Session(engine) as db:
            yield db

    app = FastAPI()
    app.include_router(cs_router.router)
    app.dependency_overrides[get_db] = get_test_db
    if visitor_id is not None:
        app.dependency_overrides[require_visitor] = lambda: VisitorPrincipal(visitor_id, "token")
    return TestClient(app)


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    for model in (
        VisitorAccount, CustomerChatSession, CsShortTurn, CsVisitorProfile, CsVisitorMemory,
        CrmLead, VisitorIntake, CustomerIdentity,
    ):
        model.__table__.create(engine)
    return engine


def test_guest_memory_stays_inside_one_session(monkeypatch):
    engine = _engine()
    with _client(monkeypatch, engine) as client:
        first = client.post("/api/cs/chat", json={"query": "我叫陈晓", "start_session": True, "history": []}).json()["data"]
        sid = first["session_id"]
        recalled = client.post("/api/cs/chat", json={
            "query": "我叫什么", "session_id": sid, "history": [{"role": "user", "content": "我叫陈晓"}],
        }).json()["data"]
        assert recalled["answer"] == "这次咨询里你说你叫陈晓。"
        fresh = client.post("/api/cs/chat", json={"query": "我叫什么", "start_session": True}).json()["data"]
        assert fresh["answer"] == "这次咨询里还没有你的称呼。"
        assert fresh["session_id"] != sid
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(CsVisitorProfile)) == 0
        assert db.scalar(select(func.count()).select_from(CsVisitorMemory)) == 0
        assert db.scalar(select(func.count()).select_from(CsShortTurn)) == 0
        assert db.get(CustomerChatSession, sid).previous_query is None
        assert db.get(CustomerChatSession, sid).dify_conversation_id is None
    engine.dispose()


def _visitor_with_customer(db):
    now = datetime(2026, 1, 1)
    db.add(VisitorAccount(
        id=7, username="15900001111", name="未填写姓名", contact="15900001111",
        password_hash="unused", created_at=now,
    ))
    db.add(CrmLead(
        id=3, customer_name="未填写姓名", contact_info="15900001111", owner_employee_id=10,
        status="contacting", create_time=now, update_time=now,
    ))
    db.add(VisitorIntake(visitor_id=7, advisor_id=10, claimed_at=now, crm_lead_id=3))
    db.commit()


def test_logged_in_visitor_writes_the_customer_portrait(monkeypatch):
    engine = _engine()
    with Session(engine) as db:
        _visitor_with_customer(db)
    with _client(monkeypatch, engine, visitor_id=7) as client:
        client.post("/api/cs/visitor/chat", json={
            "query": "我叫黄思涵，本科已毕业，想了解新加坡项目", "start_session": True,
        })
        later = client.post("/api/cs/visitor/chat", json={"query": "我叫什么", "start_session": True}).json()["data"]
        assert later["answer"] == "你叫黄思涵。"
        followed = client.post("/api/cs/visitor/chat", json={
            "query": "那个项目还要准备什么", "session_id": later["session_id"],
        }).json()["data"]
    assert "用户画像" in followed["answer"]
    assert "黄思涵" in followed["answer"]
    assert "本科" in followed["answer"]
    with Session(engine) as db:
        lead = db.get(CrmLead, 3)
        account = db.get(VisitorAccount, 7)
        assert account.name == "黄思涵"
        assert lead.customer_name == "黄思涵"
        assert lead.education_level == "bachelor"
        assert lead.education_stage == "graduated"
        assert lead.portrait["overseas_intent"] == "关注新加坡"
        assert "15900001111" not in json.dumps(lead.portrait, ensure_ascii=False)
        assert db.get(CsVisitorProfile, 7) is None
    engine.dispose()


def test_portrait_waits_for_the_same_customer_record(monkeypatch):
    engine = _engine()
    now = datetime(2026, 1, 1)
    with Session(engine) as db:
        db.execute(text("""INSERT INTO visitor_account
            (id,username,name,contact,password_hash,created_at)
            VALUES (7,'15900001111','未填写姓名','15900001111','unused','2026-01-01')"""))
        db.commit()
    with _client(monkeypatch, engine, visitor_id=7) as client:
        client.post("/api/cs/visitor/chat", json={
            "query": "我叫黄思涵，本科已毕业，家庭收入中等", "start_session": True,
        })
    with Session(engine) as db:
        staged = db.get(CsVisitorProfile, 7)
        assert staged.display_name == "黄思涵"
        assert staged.attributes["education_level"] == "bachelor"
        assert staged.attributes["family_finance"]
        lead = CrmLead(
            id=3, customer_name="未填写姓名", contact_info="15900001111", owner_employee_id=10,
            status="contacting", create_time=now, update_time=now,
        )
        db.add(lead)
        db.flush()
        account = db.get(VisitorAccount, 7)
        attach_pending_portrait(db, 7, lead, account)
        db.commit()
        assert db.get(CsVisitorProfile, 7) is None
        assert lead.customer_name == "黄思涵"
        assert lead.education_level == "bachelor"
        assert lead.portrait["family_finance"]
    engine.dispose()


def test_mem0_only_supplies_current_facts_for_the_authenticated_account(monkeypatch):
    monkeypatch.setattr(mem0, "_api_key", lambda: "test-key")
    client_class = httpx.AsyncClient
    calls = []

    def upstream(request):
        payload = json.loads(request.content)
        calls.append((request.url.path, payload))
        if request.url.path.endswith("add/"):
            return httpx.Response(200, json={"status": "SUCCEEDED"})
        fingerprint = payload["metadata"]["portrait"]
        return httpx.Response(200, json={"results": [
            {"user_id": payload["filters"]["user_id"], "metadata": {"portrait": "old"}, "memory": "德语：A1"},
            {"user_id": "other", "metadata": {"portrait": fingerprint}, "memory": "德语：A2"},
        ]})

    monkeypatch.setattr(mem0.httpx, "AsyncClient", lambda **kwargs: client_class(
        transport=httpx.MockTransport(upstream), **kwargs
    ))
    assert asyncio.run(mem0.current_memory(7, "- 德语：A2", "要准备什么")) == ""
    assert calls[0][1]["filters"]["user_id"].endswith(":7")
    assert calls[1][1]["messages"] == [{"role": "user", "content": "德语：A2"}]
    assert calls[1][1]["infer"] is False


def test_age_recall_reads_the_latest_portrait_without_dify(monkeypatch):
    engine = _engine()
    with Session(engine) as db:
        _visitor_with_customer(db)
        db.get(CrmLead, 3).age = 27
        db.add(VisitorAccount(id=8, username='15900001112', name='另一位', contact='15900001112',
            password_hash='unused', created_at=datetime(2026, 1, 1)))
        db.add(CsVisitorProfile(visitor_id=8, attributes={'age': 19}, summary='', updated_at=datetime(2026, 1, 1)))
        db.commit()

    def forbidden(*args, **kwargs):
        raise AssertionError('Age recall called Dify')

    monkeypatch.setattr(service, '_request_answer', forbidden)
    with _client(monkeypatch, engine, visitor_id=7) as client:
        response = client.post('/api/cs/visitor/chat', json={
            'query': '我多少岁', 'start_session': True,
            'history': [{'role': 'user', 'content': '我19岁'}],
        })
        assert response.status_code == 200
        assert response.json()['data']['answer'] == '资料中记录你27岁。'
        with Session(engine) as db:
            db.get(CrmLead, 3).age = 28
            db.commit()
        assert client.post('/api/cs/visitor/chat', json={'query': '我的年龄是多少？'}).json()['data']['answer'] == '资料中记录你28岁。'
        assert client.post('/api/cs/visitor/chat', json={'query': '你还记得我多大了吗？'}).json()['data']['answer'] == '资料中记录你28岁。'
        with Session(engine) as db:
            db.get(CrmLead, 3).age = None
            db.commit()
        assert client.post('/api/cs/visitor/chat', json={'query': '我多大了'}).json()['data']['answer'] == '你的资料中还没有记录年龄，你今年多少岁？'
        client.app.dependency_overrides[require_visitor] = lambda: VisitorPrincipal(8, 'token')
        assert client.post('/api/cs/visitor/chat', json={'query': '我多少岁', 'start_session': True}).json()['data']['answer'] == '资料中记录你19岁。'
    engine.dispose()


def test_guest_age_recall_uses_only_the_browser_user_history(monkeypatch):
    engine = _engine()

    def forbidden(*args, **kwargs):
        raise AssertionError('Age recall called Dify')

    monkeypatch.setattr(service, '_request_answer', forbidden)
    with _client(monkeypatch, engine) as client:
        response = client.post('/api/cs/chat', json={
            'query': '我今年几岁？', 'start_session': True,
            'history': [{'role': 'user', 'content': '我今年19岁'}, {'role': 'assistant', 'content': '你30岁'}],
        })
        assert response.json()['data']['answer'] == '这次咨询里你说你19岁。'
        fresh = client.post('/api/cs/chat', json={'query': '我多少岁', 'start_session': True})
        assert fresh.json()['data']['answer'] == '这次咨询里还没有记下你的年龄，你今年多少岁？'
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(CsVisitorProfile)) == 0
        assert db.scalar(select(func.count()).select_from(CsVisitorMemory)) == 0
    engine.dispose()


def test_registered_chat_passes_recent_user_and_assistant_turns_without_writing_them_to_the_portrait(monkeypatch):
    engine = _engine()
    with Session(engine) as db:
        _visitor_with_customer(db)
        db.get(CrmLead, 3).age = 27
        db.commit()
    with _client(monkeypatch, engine, visitor_id=7) as client:
        first = client.post('/api/cs/visitor/chat', json={'query': '我多少岁', 'start_session': True}).json()['data']
        assert first['answer'] == '资料中记录你27岁。'
        history = [
            {'role': 'user', 'content': '假设我今年19岁，只是举例，联系电话15900001111'},
            {'role': 'assistant', 'content': first['answer']},
        ]
        reply = client.post('/api/cs/visitor/chat', json={
            'query': '接着刚才的例子说', 'session_id': first['session_id'], 'history': history,
        }).json()['data']
        assert '浏览器近期对话' in reply['answer']
        assert '假设我今年19岁' in reply['answer'] and first['answer'] in reply['answer']
        assert '15900001111' not in reply['answer']
        # A retry after the server session expires can reconstruct context from the browser.
        restored = client.post('/api/cs/visitor/chat', json={
            'query': '接着刚才的例子说', 'start_session': True, 'history': history,
        }).json()['data']
        assert first['answer'] in restored['answer']
        assert restored['session_id'] != first['session_id']
    with Session(engine) as db:
        assert db.get(CrmLead, 3).age == 27
        assert db.get(CustomerChatSession, first['session_id']).dify_conversation_id == 'cs-1'
    engine.dispose()


def test_large_portrait_does_not_hide_the_most_recent_conversation():
    history = [ChatTurn(role='user' if index % 2 == 0 else 'assistant', content=f'第{index}条：' + '内容' * 240)
               for index in range(8)]
    output = compose_query('继续说', history, '【用户画像】\n' + '画像事实' * 1200)
    assert len(output) <= 4000
    assert history[-1].content in output
    assert history[-2].content in output
    assert output.endswith('当前问题：继续说')
