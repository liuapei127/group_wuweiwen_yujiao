from fastapi.testclient import TestClient

from app.core.security import EmployeePrincipal, require_employee
from tests.integration.test_ent_portal_routes import isolated_portal


def test_website_content_editing_and_publication(isolated_portal):
    app, engine = isolated_portal("trusted_jwt")
    endpoint = "/api/v1/enterprise/website-content"
    public = "/api/v1/website/sections"
    try:
        with TestClient(app) as client:
            assert client.get(endpoint).status_code == 401
            app.dependency_overrides[require_employee] = lambda: EmployeePrincipal(
                1, frozenset({"website-content:manage"}), role_code="employee",
            )
            assert client.get(endpoint).status_code == 403
            assert client.post(endpoint, json={"title": "栏目", "sort_order": 10, "published": True}).status_code == 403

            app.dependency_overrides[require_employee] = lambda: EmployeePrincipal(
                2, frozenset({"website-content:manage"}), role_code="admin",
            )
            section = {"title": "  留学项目  ", "sort_order": 20, "published": False}
            published = client.post(endpoint, json={**section, "title": "关于粤教", "sort_order": 10, "published": True})
            draft = client.post(endpoint, json=section)
            assert published.status_code == draft.status_code == 201
            section_id = draft.json()["data"]["id"]
            section_path = endpoint + f"/{section_id}"
            card = {"title": "新加坡", "content": "第一段\n第二段 <b>纯文本</b>", "sort_order": 20, "published": True}
            created = client.post(section_path + "/cards", json=card)
            assert created.status_code == 201
            card_id = created.json()["data"]["id"]
            assert client.post(section_path + "/cards", json={**card, "title": " "}).status_code == 422
            assert client.post(section_path + "/cards", json={**card, "title": "未发布", "published": False}).status_code == 201
            assert [item["title"] for item in client.get(public).json()["data"]] == ["关于粤教"]

            response = client.put(section_path, json={**section, "sort_order": 1, "published": True})
            assert response.status_code == 200
            first = client.get(public).json()["data"][0]
            assert first["title"] == "留学项目" and first["anchor"] == f"section-{section_id}"
            assert first["cards"] == [{"id": card_id, "title": "新加坡", "content": card["content"]}]
            assert "published" not in first
            assert len(client.get(endpoint).json()["data"][0]["cards"]) == 2

            wrong_section = published.json()["data"]["id"]
            assert client.put(endpoint + f"/{wrong_section}/cards/{card_id}", json=card).status_code == 404
            assert client.put(section_path + f"/cards/{card_id}", json={**card, "published": False}).status_code == 200
            assert client.get(public).json()["data"][0]["cards"] == []
    finally:
        engine.dispose()
