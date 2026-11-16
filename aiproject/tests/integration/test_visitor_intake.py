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
    permissions = frozenset({"visitor-intake:read", "visitor-intake:write", "crm:read"})
    actors = {"owner": EmployeePrincipal(10, permissions | {"crm:write"}), "other": EmployeePrincipal(20, permissions | {"crm:write"}),
              "ordinary": EmployeePrincipal(30),
              "admin": EmployeePrincipal(90, frozenset({"website-accounts:manage"}), role_code="admin")}

    def authenticate(self, token):
        if token not in actors:
            raise HTTPException(401, "登录无效")
        return actors[token]

    monkeypatch.setattr(auth_service.AuthService, "authenticate", authenticate)
    base = "/api/v1/consultant/visitor-intake"
    owner = {"Authorization": "Bearer owner"}
    other = {"Authorization": "Bearer other"}
    customers_url = "/api/v1/consultant/customers"
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
            assert client.get(case, headers=owner).json()["data"]["visitor_id"] == first
            assert client.get(case, headers=other).status_code == 404
            customers = client.get(customers_url, headers=owner).json()["data"]
            assert customers["total"] == 1
            assert customers["items"] == [
                {"id": first, "kind": "visitor", "customer_name": "first-visitor", "status": "pending_binding"},
            ]
            assert client.get(customers_url, headers=other).json()["data"]["total"] == 0
            assert client.get(customers_url, headers={"Authorization": "Bearer ordinary"}).status_code == 403
            assert client.get(customers_url, headers=owner, params={"status": "contacting"}).json()["data"]["total"] == 0
            filtered = client.get(customers_url, headers=owner, params={
                "keyword": "first", "status": "pending_binding",
            }).json()["data"]
            assert filtered["items"] == customers["items"]
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
            assert client.post(lead_path, headers=owner, json=lead_input).status_code == 409
            from app.modules.consultant import customer_service

            monkeypatch.setattr(customer_service.AuthRepository, "account", lambda self, **kwargs: {
                "user_type": "employee", "status": "normal", "role_status": 1, "role_id": 1,
            })
            monkeypatch.setattr(customer_service.AuthRepository, "permissions", lambda self, rid: {"crm:read", "crm:write"})
            bound = client.put(f"/api/v1/enterprise/website-accounts/{first}/customer",
                               headers={"Authorization": "Bearer admin"}, json={"create": True})
            assert bound.status_code == 200
            lead = client.post(lead_path, headers=owner, json=lead_input).json()["data"]
            assert lead["id"] == bound.json()["data"]["lead_id"]
            assert client.post(lead_path, headers=owner, json=lead_input).json()["data"]["id"] == lead["id"]
            assert client.get(base + "/assigned", headers=owner).json()["data"][0]["crm_lead_id"] == lead["id"]
            assert client.get(customers_url, headers=owner).json()["data"]["items"] == [
                {"id": lead["id"], "kind": "lead", "customer_name": "first-visitor", "status": "contacting"},
            ]
            new_call = {**call, "request_id": str(uuid4()), "notes": "后续回访"}
            assert client.post(case + "/calls", headers=owner, json=new_call).status_code == 200
            assert client.post(case + "/calls", headers=owner, json=new_call).status_code == 200

        with Session(engine) as db:
            lead_row = db.get(CrmLead, lead["id"])
            assert lead_row.customer_profile_id is None
            assert db.scalar(select(func.count()).select_from(CrmLead)) == 1
            assert db.scalar(select(func.count()).select_from(VisitorCall)) == 3
            assert db.scalar(select(func.count()).select_from(CrmFollowUp)) == 3
            assert db.scalar(select(func.count()).select_from(CustomerProfile)) == 3
            assert db.get(CustomerSource, source_one).raw_content == "original"
            assert db.get(CustomerSource, source_one).operator_id is None
    finally:
        engine.dispose()

def test_shared_customer_profile_import_and_screening(isolated_portal, monkeypatch):
    app, engine = isolated_portal("trusted_jwt")
    from app.modules.consultant import customer_service
    from app.modules.profile.dify_workflow import ReviewPreview
    from app.modules.visitor import router as visitor_router

    monkeypatch.setattr(visitor_router, "_AUTH_CAPACITY", visitor_router.CsChatCapacity(4, 2, 10))

    permissions = frozenset({"visitor-intake:read", "visitor-intake:write", "crm:read", "crm:write"})
    actor = EmployeePrincipal(10, permissions)
    other = EmployeePrincipal(20, permissions)
    manager = EmployeePrincipal(90, frozenset({"website-accounts:manage", "crm:write"}), role_code="admin")
    actors = {"owner": actor, "other": other, "admin": manager}
    monkeypatch.setattr(auth_service.AuthService, "authenticate", lambda self, token: actors[token])
    monkeypatch.setattr(customer_service.AuthRepository, "account", lambda repo, **kwargs: {
        "user_type": "employee", "status": "normal", "role_status": 1, "role_id": 1,
    })
    monkeypatch.setattr(customer_service.AuthRepository, "permissions", lambda repo, role: permissions)
    ai_calls = []

    def advice(text):
        ai_calls.append(text)
        return ReviewPreview(
            match_result="建议调整方向",
            match_reason="结论：建议调整方向。沟通时可以这样说：请问您的德语基础？还缺这些资料：无。下一步先问：确认专业方向。",
        )

    monkeypatch.setattr(customer_service, "review_text", advice)
    base = "/api/v1/consultant/visitor-intake"
    accounts = "/api/v1/enterprise/website-accounts"
    public = "/api/v1/visitors/customer-profile"
    owner, unassigned, admin = ({"Authorization": "Bearer " + k} for k in actors)

    try:
        with TestClient(app) as client:
            def register(k, phone):
                response = client.post("/api/v1/visitors/register", json={
                    "username": phone, "password": "Test!9876", "name": k, "nickname": k[0],
                })
                assert response.status_code == 201
                return {"Authorization": "Bearer " + response.json()["data"]["access_token"]}

            phone_one, phone_two = "13900004025", "13900004026"
            one, two = register("林晓宁", phone_one), register("陈明远", phone_two)
            visitors = client.get(base + "/pending", headers=owner).json()["data"]
            first, second = (visitor["visitor_id"] for visitor in visitors)
            for visitor in (first, second):
                assert client.post(f"{base}/{visitor}/claim", headers=owner).json()["data"]["crm_lead_id"] is None
            assert client.get(public, headers=one).status_code == 409
            assert client.post("/api/v1/consultant/leads", headers=owner, json={"customer_name": "违规建档"}).status_code == 403
            assert client.put(f"{accounts}/{first}/customer", headers=owner, json={"create": True}).status_code == 403

            def bind(visitor, name, phone):
                bound = client.put(f"{accounts}/{visitor}/customer", headers=admin, json={"create": True})
                assert bound.status_code == 200, bound.text
                lid = bound.json()["data"]["lead_id"]
                identity = f"{accounts}/customers/{lid}/identity"
                assert client.put(identity, headers=admin, json={"name": name, "mobile": phone, "confirmed": True}).status_code == 200
                return lid

            lid = bind(first, "林晓宁", phone_one)
            bind(second, "陈明远", phone_two)
            detail = "/api/v1/consultant/leads/" + str(lid)
            profile_url = detail + "/profile"
            def current():
                return client.get(profile_url, headers=owner).json()["data"]

            assert client.get(profile_url, headers=unassigned).status_code == 404
            assert client.get(detail, headers=owner).json()["data"]["lead"]["status"] == "contacting"
            starting = current()
            assert client.get(public, headers=one).json()["data"]["version"] == starting["version"]
            assert client.patch(profile_url, headers=owner, json={
                "expected_version": starting["version"], "intended_project": "de_vocational", "education_level": "senior_secondary",
            }).status_code == 200
            assert client.patch(public, headers=one, json={
                "expected_version": starting["version"], "age": 31,
            }).status_code == 409
            assert client.patch(public, headers=one, json={
                "expected_version": current()["version"], "contact_info": "官网补录联系邮箱",
            }).status_code == 200
            fields = current()
            assert fields["contact_info"] == "官网补录联系邮箱"
            assert fields["readiness"]["missing_fields"] == ["education_stage", "age"]
            missing = client.post(detail + "/screening", headers=owner, json={"expected_version": fields["version"]})
            assert missing.json()["data"] == {"ready": False, "missing_fields": ["education_stage", "age"]}
            assert not ai_calls

            def upload(base_url, headers, content, filename="学习经历.txt"):
                return client.post(base_url + "/imports/preview", headers=headers, files={"file": (filename, content.encode())})

            assert upload(detail, owner, f"本人手机号：{phone_one}\n年龄：22", "林晓宁.txt").status_code == 422
            assert upload(detail, owner, f"姓名：陈明远\n本人手机号：{phone_two}\n年龄：22").status_code == 422
            assert upload(detail, owner, f"姓名：陈明远\n本人手机号：{phone_one}\n年龄：22").status_code == 422
            assert upload(detail, owner, f"姓名：林晓宁\n本人手机号：{phone_one}\n姓名：陈明远\n年龄：22").status_code == 422
            assert upload(public, two, f"姓名：林晓宁\n本人手机号：{phone_one}\n年龄：22").status_code == 422
            duplicate_header = f"姓名,本人姓名,本人手机号,年龄\n陈明远,林晓宁,{phone_one},22"
            assert upload(detail, owner, duplicate_header, "混合资料.csv").status_code == 422
            assert current()["age"] is None

            document = f"姓名：林晓宁\n本人手机号：{phone_one}\n年龄：22\n毕业状态：已毕业"
            good = upload(detail, owner, document)
            assert good.status_code == 200, good.text
            preview = good.json()["data"]
            assert preview["matches"] == ["姓名", "本人手机号"]
            assert current()["age"] is None
            payload = {"preview_id": preview["preview_id"], "expected_version": preview["version"], "fields": ["age", "education_stage"]}
            assert client.post(public + "/imports/confirm", headers=one, json=payload).status_code == 404
            assert client.post(detail + "/imports/confirm", headers=owner, json={**payload, "fields": ["customer_name"]}).status_code == 422
            assert client.post(detail + "/imports/confirm", headers=owner, json=payload).status_code == 200

            synced = client.get(public, headers=one).json()["data"]
            assert synced["age"] == 22 and synced["education_stage"] == "graduated"
            assert "screening" not in synced and "status" not in synced
            result = client.post(detail + "/screening", headers=owner, json={"expected_version": current()["version"]}).json()["data"]
            assert result["screening"]["result"]["status"] == "potential_match"
            assert result["screening"]["ai"]["talk_track"]
            assert len(ai_calls) == 1

            visitor_upload = upload(public, one, f"姓名：林晓宁\n本人手机号：{phone_one}\n意向专业：机械")
            draft = visitor_upload.json()["data"]
            assert client.post(public + "/imports/confirm", headers=one, json={
                "preview_id": draft["preview_id"], "expected_version": draft["version"], "fields": ["intended_major"],
            }).status_code == 200
            latest = current()
            assert latest["intended_major"] == "机械" and latest["screening"]["stale"]
            assert client.patch(public, headers=one, json={"expected_version": latest["version"], "status": "signed"}).status_code == 422

            with Session(engine) as db:
                assert db.scalar(select(func.count()).select_from(CrmLead)) == 2
                imported = db.scalar(select(CustomerSource).where(CustomerSource.lead_id == lid, CustomerSource.operator_id == 10))
                assert imported.file_content == document.encode()
    finally:
        engine.dispose()
