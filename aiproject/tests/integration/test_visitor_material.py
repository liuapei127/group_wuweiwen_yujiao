from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.consultant.models import CrmLead
from app.modules.profile.models import CustomerProfile, CustomerSource, VisitorMaterial
from tests.integration.test_ent_portal_routes import isolated_portal


def test_visitor_can_submit_partial_material_and_only_read_own_progress(isolated_portal):
    app, engine = isolated_portal("trusted_jwt")
    url = "/api/v1/visitor/materials"
    file_content = b"file retained before parsing"
    try:
        with TestClient(app) as client:
            assert client.get(url).status_code == 401

            def login(username):
                response = client.post("/api/v1/visitors/register", json={
                    "username": username, "password": "test-password",
                    "name": "游客", "contact": "contact",
                })
                assert response.status_code == 201
                return {"Authorization": "Bearer " + response.json()["data"]["access_token"]}

            own = login("own-material")
            other = login("other-material")
            assert client.post(url, headers=own, data={"raw_content": "  "}).status_code == 422
            assert client.post(url, headers=own, files={"file": ("file.exe", b"x")}).status_code == 422
            uploaded = client.post(url, headers=own, files={"file": ("scan.pdf", file_content)})
            assert uploaded.status_code == 201
            data = uploaded.json()["data"]
            source_id = data["source_id"]
            assert data["file_name"] == "scan.pdf"
            assert data["status"] == "received"

            text_only = client.post(url, headers=own, data={"raw_content": "只知道学历"})
            assert text_only.status_code == 201
            assert client.get(url, headers=other).json()["data"] == []
            assert client.get(f"{url}/{source_id}", headers=other).status_code == 404
            assert client.get(f"{url}/{source_id}", headers=own).json()["data"] == data
            page = client.get(url, headers=own, params={"limit": 1}).json()["data"]
            assert page == [text_only.json()["data"]]
            assert client.get(url, headers=own, params={"before_id": page[0]["source_id"]}).json()["data"] == [data]

        with Session(engine) as db:
            assert db.get(VisitorMaterial, source_id).file_content == file_content
            assert db.get(CustomerSource, source_id).operator_id is None
            assert db.scalar(select(func.count()).select_from(CrmLead)) == 0
            assert db.scalar(select(func.count()).select_from(CustomerProfile)) == 0
            db.add(CustomerProfile(source_id=source_id, background_info={
                "screening": {"status": "needs_information", "findings": ["internal review"]}
            }))
            db.commit()
        with TestClient(app) as client:
            progress = client.get(f"{url}/{source_id}", headers=own)
            assert progress.json()["data"]["status"] == "needs_information"
            assert "internal review" not in progress.text
    finally:
        engine.dispose()
