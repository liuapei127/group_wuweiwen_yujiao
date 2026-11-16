from pathlib import Path
import ast
import json

import httpx
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.core.database import get_db
from app.modules.customer_service import router as cs_router, service
from app.modules.customer_service.capacity import CsChatCapacity
from app.modules.customer_service.models import CustomerChatSession
from app.modules.events.models import EventLecture, EventRegistration
from app.modules.visitor.models import VisitorAccount
from app.modules.visitor.router import require_visitor
from app.modules.visitor.service import VisitorPrincipal


def test_website_customer_booking_is_confirmed_and_scoped(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    for model in (VisitorAccount, CustomerChatSession, EventLecture, EventRegistration):
        model.__table__.create(engine)
    with Session(engine) as db:
        db.execute(text("""INSERT INTO visitor_account
            (id,username,name,contact,password_hash,created_at) VALUES
            (1,'alice','Alice','demo','unused','2026-01-01'),
            (2,'bob','Bob','demo','unused','2026-01-01')"""))
        db.execute(text("""INSERT INTO event_lecture
            (id,event_type,status,event_name,start_time,location,max_participants,current_participants,create_time)
            VALUES (11,'offline','upcoming','德国项目线下说明会','2099-11-20 12:00:00','广州',3,0,'2026-01-01')"""))
        db.commit()

    from datetime import datetime
    monkeypatch.setattr(service.events, "_event_now", lambda: datetime(2099, 11, 19))
    monkeypatch.setattr(service, "get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr(service, "get_cs_capacity", lambda: CsChatCapacity(2, 1, 100))

    def get_test_db():
        with Session(engine) as db:
            yield db

    app = FastAPI()
    from app.router_registry import register_routers
    register_routers(app)
    app.dependency_overrides[get_db] = get_test_db
    visitor = VisitorPrincipal(1, "token")
    app.dependency_overrides[require_visitor] = lambda: visitor

    with TestClient(app) as client:
        route = "/api/cs/visitor/chat"

        def send(query, session_id=None):
            fields = {"session_id": session_id} if session_id else {"start_session": True}
            return client.post(route, json={"query": query, **fields})

        guest = client.post("/api/cs/chat", json={"query": "确认报名", "start_session": True})
        assert "请先登录" in guest.json()["data"]["answer"]
        result = send("未来7天有哪些德国线下活动").json()["data"]
        assert "德国项目线下说明会" in result["answer"]
        sid = result["session_id"]
        assert "请先问" in send("确认报名", sid).json()["data"]["answer"]
        selected = send("第一场", sid).json()["data"]
        assert "确认报名" in selected["answer"]
        assert "reservation_changed" not in selected
        visitor = VisitorPrincipal(2, "other")
        assert send("确认报名", sid).status_code == 404
        visitor = VisitorPrincipal(1, "token")
        assert client.post("/api/cs/chat", json={"query": "确认报名", "session_id": sid}).status_code == 404
        assert send("确认报名", sid).json()["data"]["reservation_changed"]
        assert send("确认报名", sid).json()["data"]["reservation_changed"]
        assert "德国项目线下说明会" in send("我的预约", sid).json()["data"]["answer"]

    with Session(engine) as db:
        assert db.scalar(text("SELECT COUNT(*) FROM event_registration")) == 1
        assert db.scalar(text("SELECT current_participants FROM event_lecture WHERE id=11")) == 1
    engine.dispose()


def test_website_customer_dify_context_retries_an_expired_conversation(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    VisitorAccount.__table__.create(engine)
    CustomerChatSession.__table__.create(engine)

    def get_test_db():
        with Session(engine) as db:
            yield db

    requests = []
    settings = Settings(_env_file=None, cs_public_dify_api_key="test-key")
    monkeypatch.setattr(service, "get_settings", lambda: settings)
    monkeypatch.setattr(service, "get_cs_capacity", lambda: CsChatCapacity(2, 1, 20))
    client_class = httpx.AsyncClient

    def upstream(request):
        req = json.loads(request.content)
        requests.append(req)
        if req.get("conversation_id") == "expired":
            return httpx.Response(404, json={"code": "not_found"})
        return httpx.Response(200, json={"answer": "请以官方资料为准", "conversation_id": "expired" if len(requests) == 1 else "renewed"})

    monkeypatch.setattr(service.httpx, "AsyncClient", lambda **kwargs: client_class(
        transport=httpx.MockTransport(upstream), **kwargs
    ))
    app = FastAPI()
    app.include_router(cs_router.router)
    app.dependency_overrides[get_db] = get_test_db
    with TestClient(app) as client:
        url = "/api/cs/chat"
        first = client.post(url, json={"query": "留学签证需要什么材料", "start_session": True}).json()["data"]
        second = client.post(url, json={"query": "德国", "session_id": first["session_id"]}).json()["data"]
        assert second["session_id"] == first["session_id"]
        assert "conversation_id" not in second
    assert len(requests) == 3
    assert requests[1]["conversation_id"] == "expired"
    assert requests[2]["user"] == requests[0]["user"]
    assert "conversation_id" not in requests[2]
    assert "德国" in requests[2]["query"] and "签证" in requests[2]["query"]
    engine.dispose()


def test_delivered_customer_graph_retains_36_nodes_and_read_only_callbacks():
    path = Path(__file__).resolve().parents[2] / "docs/dify/local-integration/cs.yml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    nodes = doc["workflow"]["graph"]["nodes"]
    assert len(nodes) == 36
    assert len([n for n in nodes if n["data"]["type"] == "knowledge-retrieval"]) == 4
    for n in nodes:
        data = n["data"]
        if data["type"] == "code":
            ast.parse(data["code"])
        if data["type"] == "http-request":
            assert data["method"] == "get"
            assert data["authorization"]["type"] == "no-auth"
            assert "/api/cs/catalog/" in data["url"]
            assert data["retry_config"]["retry_enabled"] is False
