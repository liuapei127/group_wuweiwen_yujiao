from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import EmployeePrincipal
from app.modules.auth import service as auth_service
from app.modules.consultant.models import CrmFollowUp, CrmLead, VisitorCall
from app.modules.profile.models import CustomerProfile, CustomerSource
from tests.integration.test_ent_portal_routes import isolated_portal


def test_visitor_intake_preserves_sources_and_isolates_advisors(isolated_portal, monkeypatch):
    app, engine = isolated_portal("trusted_jwt")
    permissions = frozenset({"visitor-intake:read", "visitor-intake:write"})
    actors = {"owner": EmployeePrincipal(10, permissions | {"crm:write"}), "other": EmployeePrincipal(20, permissions | {"crm:write"}),
              "ordinary": EmployeePrincipal(30)}

    def authenticate(self, token):
        if token not in actors:
            raise HTTPException(401, "登录无效")
        return actors[token]

    monkeypatch.setattr(auth_service.AuthService, "authenticate", authenticate)
    base = "/api/v1/consultant/visitor-intake"
    owner = {"Authorization": "Bearer owner"}
    other = {"Authorization": "Bearer other"}
    material_url = "/api/v1/visitor/materials"
    try:
        with TestClient(app) as client:
            def register(name, phone):
                r = client.post("/api/v1/visitors/register", json={
                    "username": phone, "password": "test-password",
                    "name": name, "contact": "private-contact",
                })
                assert r.status_code == 201
                return {"Authorization": "Bearer " + r.json()["data"]["access_token"]}

            one, two = register("first-visitor", "13900001005"), register("second-visitor", "13900001006")
            assert client.get(base + "/pending", headers=one).status_code == 401
            assert client.get(base + "/pending", headers={"Authorization": "Bearer ordinary"}).status_code == 403

            def upload(headers, value):
                r = client.post(material_url, headers=headers, data={"raw_content": value},
                                files={"file": ("source.txt", value.encode())})
                assert r.status_code == 201
                return r.json()["data"]["source_id"]

            source_one, source_two = upload(one, "original"), upload(two, "other original")
            pending = client.get(base + "/pending", headers=owner).json()["data"]
            assert len(pending) == 2 and set(pending[0]) == {"visitor_id", "registered_at"}
            first, second = (entry["visitor_id"] for entry in pending)
            case = f"{base}/{first}"
            assert client.get(case + "/materials", headers=owner).status_code == 404
            assert client.post(case + "/claim", headers=owner).json()["data"]["contact"] == "private-contact"
            assert client.post(case + "/claim", headers=owner).status_code == 200
            assert client.post(case + "/claim", headers=other).status_code == 409
            assert client.get(base + "/assigned", headers=other).json()["data"] == []
            assert [entry["visitor_id"] for entry in client.get(base + "/pending", headers=other).json()["data"]] == [second]
            assert client.get(case + "/materials", headers=other).status_code == 404
            assert client.get(case + f"/materials/{source_two}", headers=owner).status_code == 404
            attachment_url = case + f"/materials/{source_one}/attachment"
            assert client.get(attachment_url, headers=other).status_code == 404
            attachment = client.get(attachment_url, headers=owner)
            assert attachment.content == b"original"
            assert attachment.headers["Content-Disposition"].startswith("attachment")

            endpoint = case + "/screening"
            assert client.post(endpoint, json={}, headers=owner).status_code == 409
            call = {"request_id": str(uuid4()), "notes": "确认需要补录年龄"}
            saved = client.post(case + "/calls", json=call, headers=owner).json()["data"]
            assert saved["advisor_id"] == 10
            assert client.post(case + "/calls", json=call, headers=owner).json()["data"] == saved
            assert client.post(case + "/calls", json={**call, "notes": "另一条"}, headers=owner).status_code == 409
            assert client.post(case + "/calls", json={**call, "request_id": str(uuid4())}, headers=owner).status_code == 200
            assert len(client.get(case + "/calls", headers=owner).json()["data"]) == 2

            assert client.post(endpoint, params={"source_id": source_two}, json={}, headers=owner).status_code == 404
            response = client.post(endpoint, params={"source_id": source_one}, headers=owner,
                                   json={"project": "sg_hospitality", "education": "vocational_secondary"})
            assert response.json()["data"]["screening"]["status"] == "needs_information"
            assert client.get(f"{material_url}/{source_one}", headers=one).json()["data"]["status"] == "needs_information"
            lead_path = case + "/lead"
            lead_input = {"source_id": source_one, "customer_name": "访客", "contact_info": "电话", "remark": "回访确认意向"}
            assert client.post(lead_path, headers=owner, json=lead_input).status_code == 409
            assert client.post(lead_path, headers=other, json=lead_input).status_code == 404
            assert client.post(lead_path, headers=owner, json={**lead_input, "source_id": source_two}).status_code == 404
            final = client.post(endpoint, params={"source_id": source_one}, json={"age": 18}, headers=owner)
            assert final.json()["data"]["screening"]["status"] == "potential_match"
            assert client.get(f"{material_url}/{source_one}", headers=one).json()["data"]["status"] == "reviewed"
            manual = client.post(endpoint, headers=owner, json={"project": "sg_hospitality", "age": 18,
                                                                "education": "vocational_secondary"})
            manual_id = manual.json()["data"]["source_id"]
            assert manual_id not in {source_one, source_two}
            stored = client.get(endpoint, headers=owner).json()["data"]
            assert stored["source_id"] == manual_id
            assert stored["screening_input"]["age"] == 18
            owned_material = client.get(case + f"/materials/{source_one}", headers=owner).json()["data"]
            assert owned_material["screening_input"]["education"] == "vocational_secondary"
            assert client.get(f"{material_url}/{manual_id}", headers=one).status_code == 404
            with Session(engine) as db:
                assert db.scalar(select(func.count()).select_from(CrmLead)) == 0
            lead = client.post(lead_path, headers=owner, json=lead_input).json()["data"]
            assert lead["intended_country"] == "Singapore"
            assert client.post(lead_path, headers=owner, json=lead_input).json()["data"]["id"] == lead["id"]
            assert client.get(base + "/assigned", headers=owner).json()["data"][0]["crm_lead_id"] == lead["id"]
            new_call = {**call, "request_id": str(uuid4()), "notes": "后续回访"}
            assert client.post(case + "/calls", headers=owner, json=new_call).status_code == 200
            assert client.post(case + "/calls", headers=owner, json=new_call).status_code == 200

        with Session(engine) as db:
            lead_row = db.get(CrmLead, lead["id"])
            assert lead_row.customer_profile_id is not None
            assert db.scalar(select(func.count()).select_from(CrmLead)) == 1
            assert db.scalar(select(func.count()).select_from(VisitorCall)) == 3
            assert db.scalar(select(func.count()).select_from(CrmFollowUp)) == 3
            assert db.scalar(select(func.count()).select_from(CustomerProfile)) == 3
            assert db.get(CustomerSource, source_one).raw_content == "original"
            assert db.get(CustomerSource, source_one).operator_id is None
    finally:
        engine.dispose()
