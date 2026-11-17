import json

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import Settings
from app.core.exceptions import BusinessError
from app.modules.customer_service import service
from app.modules.customer_service.capacity import CsChatCapacity
from app.router_registry import register_routers
from tests.integration.test_ent_portal_routes import isolated_portal


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


def test_public_chat_explains_course_and_project_fees_without_dify(monkeypatch):
    monkeypatch.setattr(service, "get_settings", lambda: Settings(_env_file=None, cs_public_dify_api_key=""))
    monkeypatch.setattr(service, "get_cs_capacity", lambda: CsChatCapacity(2, 1, 10))
    app = FastAPI()
    register_routers(app)
    with TestClient(app) as client:
        for question in ("德语课程需要收费吗", "新加坡项目多少钱", "课程是免费的吗"):
            response = client.post("/api/cs/chat", json={"query": question})
            assert response.status_code == 200
            assert response.json()["data"]["answer"] == "粤教的课程免费，项目费用在签约时按合同约定收取。"
    assert service._catalog_fee_answer("那多少钱", "推荐新加坡项目").answer == "粤教的课程免费，项目费用在签约时按合同约定收取。"
    assert service._catalog_fee_answer("海外学校学费多少钱", "推荐新加坡项目") is None


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


def test_public_chat_stream_uses_catalog_when_dify_times_out(monkeypatch):
    settings = Settings(_env_file=None, cs_public_dify_api_key="test-key")
    monkeypatch.setattr(service, "get_settings", lambda: settings)
    capacity = CsChatCapacity(2, 1, 10)
    monkeypatch.setattr(service, "get_cs_capacity", lambda: capacity)
    monkeypatch.setattr(service, "_session_turn", lambda db, sid, visitor_id, query: (
        "known-session", None, query, None
    ))

    async def unavailable(*args, **kwargs):
        raise BusinessError(502, "咨询助手暂不可用") from httpx.ReadTimeout("test timeout")

    monkeypatch.setattr(service, "_request_answer", unavailable)
    calls = []

    def catalog(db, query):
        calls.append(query)
        return [{"name": "新加坡国际本硕升学计划", "summary": "项目说明", "matches_preferences": False}]

    monkeypatch.setattr(service, "recommendations", catalog)
    app = FastAPI()
    register_routers(app)
    question = "我是高中生，想去新加坡留学，有什么项目"
    with TestClient(app) as client:
        project = client.post(
            "/api/cs/chat", headers={"Accept": "text/event-stream"},
            json={"query": question, "start_session": True},
        )
        policy = client.post(
            "/api/cs/chat", headers={"Accept": "text/event-stream"},
            json={"query": "新加坡留学签证怎么申请", "start_session": True},
        )

    assert project.status_code == policy.status_code == 200
    assert project.headers["content-type"].startswith("text/event-stream")
    assert "新加坡国际本硕升学计划" in project.text
    assert "当前资料无法确认你的申请资格" in project.text
    assert "known-session" in project.text
    assert "新加坡国际本硕升学计划" not in policy.text
    assert "在线咨询暂时不可用" in policy.text
    assert calls == [question]


def test_catalog_discovery_preserves_published_destination_when_education_is_unconfirmed(isolated_portal, monkeypatch):
    app, engine = isolated_portal()
    monkeypatch.setattr(service, "get_cs_capacity", lambda: CsChatCapacity(2, 1, 10))

    async def upstream(*args, **kwargs):
        raise AssertionError("A catalog lookup should use the published local data")

    monkeypatch.setattr(service, "_request_answer", upstream)
    with engine.begin() as conn:
        conn.execute(text("""CREATE TABLE course_project (
            id INTEGER PRIMARY KEY, project_name TEXT, category TEXT, description TEXT,
            target_audience TEXT, duration TEXT, status INTEGER
        )"""))
        conn.execute(text("""INSERT INTO course_project VALUES
            (1, '联调新加坡项目', '本地测试', '高中生样例', NULL, NULL, 1),
            (2, '下架新加坡项目', NULL, '高中生项目', NULL, NULL, 0)
        """))
        conn.execute(text("INSERT INTO website_section VALUES (1, 'programs', '留学项目', 0, 1)"))
        conn.execute(text("""INSERT INTO website_section_card
            (id, section_id, title, content, sort_order, published) VALUES
            (1, 1, '新加坡国际本硕升学计划', '提供面向不同学历阶段的升学路径。', 0, 1),
            (2, 1, '中德精英人才共建计划', '面向德国升学，包含高中生路径。', 1, 1),
            (3, 1, '新加坡项目草稿', '高中生可了解。', 2, 0)
        """))

    question = "我高中毕业，想去新加坡升学，有什么项目？ 客服助手查不到新加坡项目"
    with TestClient(app) as client:
        catalog = client.get("/api/cs/catalog/recommendations", params={"query": question})
        assert catalog.status_code == 200
        projects = catalog.json()["data"]
        assert [row["name"] for row in projects] == ["新加坡国际本硕升学计划"]
        assert projects[0]["matches_preferences"] is False

        reply = client.post("/api/cs/chat", json={"query": question, "start_session": True})
        assert reply.status_code == 200
        data = reply.json()["data"]
        assert "新加坡国际本硕升学计划" in data["answer"]
        assert "当前资料无法确认你的申请资格" in data["answer"]
        assert "德国" not in data["answer"]
        assert "联调" not in data["answer"]
        assert data["session_id"]

        with engine.begin() as conn:
            conn.execute(text("UPDATE website_section_card SET content = :content WHERE id = 1"), {
                "content": "高中毕业生可了解 0.5/1+2 定向培养本科班和 0.5/1+2+1 本硕连读。"
            })
        detailed = client.post("/api/cs/chat", json={"query": question, "session_id": data["session_id"]})
        assert detailed.status_code == 200
        answer = detailed.json()["data"]["answer"]
        assert "0.5/1+2 定向培养本科班" in answer
        assert "0.5/1+2+1 本硕连读" in answer
        assert "请登录" not in answer
    engine.dispose()


def test_catalog_followup_rechecks_requested_type_and_country(isolated_portal, monkeypatch):
    app, engine = isolated_portal()
    monkeypatch.setattr(service, "get_cs_capacity", lambda: CsChatCapacity(2, 1, 20))

    async def upstream(*args, **kwargs):
        raise AssertionError("A catalog correction should use published records directly")

    monkeypatch.setattr(service, "_request_answer", upstream)
    with engine.begin() as conn:
        conn.execute(text("""CREATE TABLE course_project (
            id INTEGER PRIMARY KEY, project_name TEXT, category TEXT, description TEXT,
            target_audience TEXT, duration TEXT, status INTEGER
        )"""))
        conn.execute(text("""INSERT INTO course_project VALUES
            (1, '德语学习', '语言类', '学习德语', '前往德国学生', NULL, 1),
            (2, '德国项目配套写作', '项目配套课程', '写作练习', NULL, NULL, 1),
            (3, '德国工程项目', '留学项目', '工程方向介绍', NULL, NULL, 1),
            (4, '已下架德国项目', '留学项目', '历史资料', NULL, NULL, 0),
            (5, '德国资料', NULL, '通用介绍', NULL, NULL, 1)
        """))
        conn.execute(text("INSERT INTO website_section VALUES (1, 'programs', '留学项目', 0, 1)"))
        conn.execute(text("""INSERT INTO website_section_card
            (id, section_id, title, content, sort_order, published) VALUES
            (1, 1, '中德精英人才共建计划', '面向德国的双元制职业培训。', 0, 1),
            (2, 1, '新加坡国际本硕升学计划', '新加坡升学项目。', 1, 1)
        """))
    with TestClient(app) as client:
        endpoint = "/api/cs/chat"
        catalog = client.get("/api/cs/catalog/recommendations", params={"query": "德国项目"})
        assert [row["name"] for row in catalog.json()["data"]] == ["德国工程项目", "中德精英人才共建计划"]

        initial = client.post(endpoint, json={"query": "德语课程", "start_session": True}).json()["data"]
        assert "德语学习" in initial["answer"]
        assert "中德精英人才共建计划" not in initial["answer"]
        session = {"session_id": initial["session_id"]}
        corrected = client.post(endpoint, json={**session, "query": "这不是课程吗，我问的是项目"}).json()["data"]
        assert "中德精英人才共建计划" in corrected["answer"]
        assert "德语学习" not in corrected["answer"]
        assert "新加坡" not in corrected["answer"]
        assert "价格" not in corrected["answer"]

        courses = client.post(endpoint, json={**session, "query": "课程呢？"}).json()["data"]
        assert "德语学习" in courses["answer"]
        assert "中德精英人才共建计划" not in courses["answer"]
        course_list = client.post(endpoint, json={**session, "query": "德国项目有哪些课程？"}).json()["data"]
        assert "德国课程" in course_list["answer"] and "德语学习" in course_list["answer"]
        changed = client.post(endpoint, json={**session, "query": "新加坡项目"}).json()["data"]
        assert "新加坡国际本硕升学计划" in changed["answer"]
        assert "中德精英人才共建计划" not in changed["answer"]
        fee = client.post(endpoint, json={**session, "query": "那多少钱？"}).json()["data"]
        assert fee["answer"] == "粤教的课程免费，项目费用在签约时按合同约定收取。"
    engine.dispose()
