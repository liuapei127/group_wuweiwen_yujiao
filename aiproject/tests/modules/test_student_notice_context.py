from datetime import datetime
import json

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.database import Base
from app.modules.feedback.models import student_feedback_ticket
from app.modules.student import notifications, service
from app.modules.student.models import AcademicDeadline
from app.modules.student_admin.models import StudentAdminService
from app.modules.todo.models import notification_log


def test_old_notifications_identify_the_source_without_exposing_another_student():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[notification_log, StudentAdminService.__table__,
                                            student_feedback_ticket, AcademicDeadline.__table__])
    now = datetime(2026, 11, 16, 12)
    with Session(engine) as db:
        db.add_all([
            StudentAdminService(id=1, student_id=7, service_type="leave", leave_type="sick",
                                start_time=datetime(2026, 11, 20, 9), end_time=datetime(2026, 11, 20, 18),
                                reason="身体不适", status="approved", approval_comment="注意休息",
                                approval_time=now, create_time=now, update_time=now),
            StudentAdminService(id=2, student_id=8, service_type="leave", leave_type="personal",
                                reason="另一学生的私密原因", status="pending", create_time=now, update_time=now),
        ])
        db.execute(student_feedback_ticket.insert().values(
            id=10, student_id=7, ticket_type="complaint", category="learning", title="宿舍维修未处理",
            content="已经报修两次", status="resolved", priority="medium", solution="安排次日维修",
            is_notified=0, create_time=now, update_time=now,
        ))
        notifications.save_student_result(db, 7, "student_admin_service", 1, "approved", "请假审批结果", "你的请假申请已通过。")
        notifications.save_student_result(db, 7, "student_feedback_ticket", 10, "resolved", "投诉处理结果", "你的投诉已处理。")
        notifications.save_student_result(db, 7, "student_admin_service", 2, "pending", "错误关联", "旧通知")
        notifications.save_student_result(db, 8, "student_admin_service", 2, "pending", "他人的通知", "不应显示")
        db.commit()
        rows = notifications.student_results(db, 7, None, 20)
        assert len(rows) == 3
        leave = next(row for row in rows if row["related_id"] == 1)
        assert "病假" in leave["related_summary"] and "2026-11-20 09:00" in leave["related_summary"]
        assert "身体不适" in leave["related_summary"]
        fields = {field["label"]: field["value"] for field in leave["related_details"]["fields"]}
        assert fields["审批意见"] == "注意休息"
        complaint = next(row for row in rows if row["related_id"] == 10)
        assert complaint["related_summary"] == "宿舍维修未处理"
        assert any(field["value"] == "安排次日维修" for field in complaint["related_details"]["fields"])
        forged = next(row for row in rows if row["related_id"] == 2)
        assert forged["related_summary"] is None and forged["related_details"] is None
        assert "另一学生的私密原因" not in json.dumps(rows, ensure_ascii=False, default=str)
    engine.dispose()


def test_academic_profile_uses_student_records_without_a_crm_link():
    engine = create_engine("sqlite://")
    with Session(engine) as db:
        db.execute(text("CREATE TABLE sys_user (id INTEGER PRIMARY KEY, real_name TEXT, user_type TEXT, status TEXT)"))
        db.execute(text("CREATE TABLE student_info (user_id INTEGER, class_teacher_id INTEGER, student_no TEXT, school TEXT, major TEXT, abroad_country TEXT)"))
        db.execute(text("CREATE TABLE student_class_enrollment (student_id INTEGER, class_id INTEGER)"))
        db.execute(text("CREATE TABLE project_class (id INTEGER, project_id INTEGER, name TEXT)"))
        db.execute(text("CREATE TABLE course_project (id INTEGER, project_name TEXT)"))
        db.execute(text("INSERT INTO sys_user VALUES (7,'本人学籍姓名','student','normal'),(8,'另一学生','student','normal'),(30,'王老师','employee','normal')"))
        db.execute(text("INSERT INTO student_info VALUES (7,30,'STU007','已就读院校','计算机','Germany'),(8,30,'STU008','其他院校','其他专业','Singapore')"))
        profile = service.academic_profile(db, 7)
        assert profile == {"student_name": "本人学籍姓名", "student_no": "STU007", "school": "已就读院校",
                           "major": "计算机", "abroad_country": "Germany", "class_teacher": "王老师",
                           "class_id": None, "class_name": None, "project_id": None, "project_name": None}
        db.execute(text("INSERT INTO course_project VALUES (1, '德国升学项目')"))
        db.execute(text("INSERT INTO project_class VALUES (10, 1, '预科一班'), (11, 1, '预科二班')"))
        db.execute(text("INSERT INTO student_class_enrollment VALUES (7, 10), (8, 11)"))
        profile = service.academic_profile(db, 7)
        assert profile["project_name"] == "德国升学项目" and profile["class_name"] == "预科一班"
        db.execute(text("UPDATE student_class_enrollment SET class_id=11 WHERE student_id=7"))
        assert service.academic_profile(db, 7)["class_name"] == "预科二班"
    engine.dispose()
