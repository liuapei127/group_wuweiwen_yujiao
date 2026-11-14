import json

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.modules.customer_service import service
from app.modules.customer_service.capacity import CsChatCapacity
from app.router_registry import register_routers


def test_public_chat_uses_anonymous_server_identity(monkeypatch):
    settings = Settings(_env_file=None, employee_identity_mode="blocked", cs_public_dify_api_key="test-key")
    monkeypatch.setattr(service, "get_settings", lambda: settings)
    monkeypatch.setattr(service, "get_cs_capacity", lambda: CsChatCapacity(2, 1, 10))
    calls = []

    def reply(request):
        calls.append((request, json.loads(request.content)))
        return httpx.Response(200, json={"answer": "公开项目介绍"})

    client_cls = httpx.AsyncClient
    monkeypatch.setattr(service.httpx, "AsyncClient", lambda **kwargs: client_cls(
        transport=httpx.MockTransport(reply), **kwargs
    ))
    app = FastAPI()
    register_routers(app)
    with TestClient(app) as client:
        url = "/api/cs/chat"
        assert client.post(url, json={"query": "   "}).status_code == 422
        assert client.post(url, json={"query": "课程", "conversation_id": "other"}).status_code == 422
        first = client.post(url, json={"query": "  课程  "}, headers={"Authorization": "Bearer local-token"})
        second = client.post(url, json={"query": "课程"})
        assert first.json()["data"] == second.json()["data"] == {"answer": "公开项目介绍"}

    request, body = calls[0]
    assert request.url.path.endswith("/chat-messages")
    assert request.headers["Authorization"] == "Bearer test-key"
    assert body["query"] == "课程" and body["inputs"] == {}
    assert "conversation_id" not in body
    assert body["user"] != calls[1][1]["user"]


def test_public_chat_checks_service_configuration(monkeypatch):
    monkeypatch.setattr(service, "get_settings", lambda: Settings(_env_file=None, cs_public_dify_api_key=""))
    app = FastAPI()
    register_routers(app)
    with TestClient(app) as client:
        assert client.post("/api/cs/chat", json={"query": "课程"}).status_code == 503


def test_public_chat_enforces_capacity_and_hides_upstream_details(monkeypatch):
    settings = Settings(_env_file=None, cs_public_dify_api_key="test-key")
    monkeypatch.setattr(service, "get_settings", lambda: settings)
    capacity = CsChatCapacity(1, 1, 1)
    monkeypatch.setattr(service, "get_cs_capacity", lambda: capacity)
    calls = []

    def reply(request):
        calls.append(request)
        return httpx.Response(500, text="internal service details")

    client_cls = httpx.AsyncClient
    monkeypatch.setattr(service.httpx, "AsyncClient", lambda **kwargs: client_cls(
        transport=httpx.MockTransport(reply), **kwargs
    ))
    app = FastAPI()
    register_routers(app)
    with TestClient(app) as client:
        url = "/api/cs/chat"
        upstream_error = client.post(url, json={"query": "课程"}, headers={"X-Forwarded-For": "192.0.2.1"})
        limited = client.post(url, json={"query": "课程"}, headers={"X-Forwarded-For": "192.0.2.2"})
        assert upstream_error.status_code == 502
        assert "internal service details" not in upstream_error.text
        assert limited.status_code == 429
    assert len(calls) == 1
