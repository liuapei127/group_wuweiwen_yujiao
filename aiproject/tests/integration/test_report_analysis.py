from datetime import datetime
import json

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import EmployeePrincipal
from app.modules.auth import service as auth_service
from app.modules.auth.models import audit_log
from app.modules.consultant.models import CrmLead
from app.modules.feedback.models import student_feedback_ticket
from app.modules.statistics import service
from app.modules.student_admin.models import SysUser
from tests.integration.test_ent_portal_routes import isolated_portal


def test_report_analysis_uses_organization_scope_and_recorded_audit(isolated_portal, monkeypatch):
    app, engine = isolated_portal("trusted_jwt")
    monkeypatch.setattr(service, "get_settings", lambda: Settings(_env_file=None, employee_identity_mode="trusted_jwt"))
    principal = EmployeePrincipal(10, frozenset({"reports:operations:read"}), role_code="manager")
    monkeypatch.setattr(auth_service.AuthService, "authenticate", lambda self, token: principal)
    with Session(engine) as db:
        db.execute(text("CREATE TABLE report_status_history_start (id INTEGER PRIMARY KEY, start_day DATE)"))
        db.add_all([SysUser(id=i, real_name=str(i), department=department, user_type="employee")
                    for i, department in ((10, "A"), (11, "A"), (12, "B"))])
        for i, owner, day in ((1, 11, datetime(2026,11,10,8)), (2,11,datetime(2026,11,3,8)),
                              (3,12,datetime(2026,11,10,8)), (4,11,datetime(2025,11,10,8))):
            db.add(CrmLead(id=i, customer_name=str(i), owner_employee_id=owner, status="signed",
                           intended_country="新加坡", education_level="高中", create_time=day, update_time=day))
        db.execute(student_feedback_ticket.insert(), [
            {"id":i,"student_id":21,"assignee_id":owner,"ticket_type":"complaint","status":"resolved",
             "content":"测试","priority":"medium","is_notified":0,
             "create_time":datetime(2026,11,10,8),"update_time":datetime(2026,11,10,19)}
            for i,owner in ((1,11),(2,12))])
        db.execute(audit_log.insert(), [
            {"actor_id":11,"target":str(i),"action":"ticket_processed","details":json.dumps({"status":status}),
             "create_time":datetime(2026,11,10,hour)}
            for i in (1,2) for status,hour in (("processing",2),("resolved",11))])
        db.commit()
    with TestClient(app) as client:
        params={"start":"2026-11-09","end":"2026-11-15"}
        headers={"Authorization":"Bearer manager"}
        root="/api/v1/reporting/board/"
        assert client.get(root+"customers/analysis",params=params).status_code==401
        response=client.get(root+"customers/analysis",params=params,headers=headers)
        assert response.status_code==200, response.text
        result=response.json()["data"]
        assert result["comparisons"]["previous"]["count"]==1
        assert result["comparisons"]["year_ago"]["percent"]==0
        assert result["groups"]["intended_country"]==[
            {"label":"新加坡","count":1,"signed":1,"signed_percent":100}]
        response=client.get(root+"complaints/analysis",params=params,headers=headers)
        assert response.status_code==200, response.text
        assert response.json()["data"]["first_response"]=={"samples":1,"average_hours":2}
        assert response.json()["data"]["resolution"]=={"samples":1,"average_hours":11}
        from app.modules.profile.models import CustomerProfile
        from app.modules.statistics.analysis_models import ReportRules
        with Session(engine) as db:
            db.get(CrmLead,1).age=18
            db.add(CustomerProfile(lead_id=1,match_score=90))
            db.add(ReportRules(id=1,version=1,settings={"high_value_match_score":80},updated_by=10,
                              updated_at=datetime(2026,11,17)))
            db.commit()
        response=client.get(root+"customers/intelligence",params=params,headers=headers)
        assert response.status_code==200, response.text
        intelligence=response.json()["data"]
        assert intelligence["cluster_samples"]==1
        assert intelligence["clusters"][0]["average_age"]==18
        assert intelligence["clusters"][0]["average_match_score"]==90
        assert intelligence["high_value"]["count"]==1
        assert intelligence["high_value"]["countries"]=={"新加坡":1}
    engine.dispose()
