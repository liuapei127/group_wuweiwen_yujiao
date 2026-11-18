"""Student -> staff -> source todo -> student result, with privacy at every read."""
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.auth.models import audit_log
from app.modules.feedback.models import student_feedback_ticket as tickets
from app.modules.student_admin.models import StudentAdminService
from app.modules.todo.models import notification_log, todo_item
from tests.integration.test_ent_portal_routes import isolated_portal
from tests.integration.test_teacher_business import auth, teacher_world


def submit(client, kind, body):
    reply = client.post('/api/v1/student/' + kind, json=body, headers=auth('101'))
    assert reply.status_code == 201, reply.text
    return reply.json()['data']


def leave(client):
    return submit(client, 'leaves', dict(leave_type='sick', reason='需要复查',
        start_time='2026-12-10T09:00:00', end_time='2026-12-10T11:00:00'))


@pytest.mark.parametrize('kind', ['complaint', 'suggestion'])
@pytest.mark.parametrize('legacy_category', ['learning', 'company'])
def test_manager_channel_is_private_even_for_stale_teacher_assignments(teacher_world, kind, legacy_category):
    client, engine = teacher_world
    ticket = submit(client, 'complaints', dict(category='company', ticket_type=kind, content='我要投诉班主任，主管保密核实内容'))
    tid = ticket['id']
    with Session(engine) as db:
        # Simulate a legacy bad assignment. Category restrictions must win over ownership.
        db.execute(tickets.update().where(tickets.c.id == tid).values(assignee_id=30, category=legacy_category))
        db.execute(todo_item.update().values(assignee_id=30))
        from app.shared.utils.time_util import now_naive
        db.execute(notification_log.insert().values(user_id=30, notification_type='todo_due',
            related_type='student_feedback_ticket', related_id=tid, title='主管保密核实内容',
            content='历史错误通知', channel='system', status='sent', create_time=now_naive()))
        db.commit()
    for path in ['/api/v1/enterprise/tickets', '/api/v1/enterprise/todos', '/api/v1/enterprise/notifications',
                 '/api/v1/teacher/students/21/records/complaints']:
        response = client.get(path, headers=auth('teacher'))
        assert response.status_code == 200, response.text
        assert '主管保密核实内容' not in response.text
        data = response.json()['data']
        assert (data.get('items', []) if isinstance(data, dict) else data) == []
    for suffix in ['', '/history']:
        response = client.get(f'/api/v1/enterprise/tickets/{tid}' + suffix, headers=auth('teacher'))
        assert response.status_code in (403, 404)
        assert '主管保密核实内容' not in response.text
    response = client.patch(f'/api/v1/enterprise/tickets/{tid}', headers=auth('teacher'),
                            json={'expected_status': 'pending', 'status': 'processing'})
    assert response.status_code == 403
    manager = client.get('/api/v1/enterprise/tickets', headers=auth('manager')).json()['data']
    assert manager[0]['id'] == tid and manager[0]['can_process'] is False
    repair = client.put(f'/api/v1/enterprise/ticket-routing/{tid}', headers=auth('manager'), json={
        'expected_status': 'pending', 'expected_category': legacy_category, 'expected_assignee_id': 30,
        'category': 'company', 'reason': '修复历史错误分派，交主管保密受理',
    })
    assert repair.status_code == 200, repair.text
    assert client.get(f'/api/v1/enterprise/tickets/{tid}', headers=auth('manager')).json()['data']['can_process'] is True


def test_explicit_class_teacher_complaint_goes_to_manager_and_cannot_be_downgraded(teacher_world):
    client, engine = teacher_world
    row = submit(client, 'complaints', dict(category='learning', content='我要投诉班主任的不当处理，请主管核实'))
    assert row['category'] == 'company' and row['assignee_id'] == 11
    url = f"/api/v1/enterprise/ticket-routing/{row['id']}"
    body = dict(expected_status='pending', expected_category='company', expected_assignee_id=11,
                category='learning', reason='错误转回')
    assert client.put(url, headers=auth('manager'), json=body).status_code == 409
    assert client.get('/api/v1/enterprise/tickets', headers=auth('teacher')).json()['data'] == []
    with Session(engine) as db:
        assert db.scalar(select(todo_item.c.assignee_id)) == 11


def test_complaint_resolution_closes_todo_notifies_student_and_keeps_audit(teacher_world):
    client, engine = teacher_world
    row = submit(client, 'complaints', dict(category='company', content='请主管核实合同服务'))
    url = f"/api/v1/enterprise/tickets/{row['id']}"
    assert client.patch(url, headers=auth('teacher'), json={'expected_status': 'pending', 'status': 'processing'}).status_code == 403
    for old, new, solution in [('pending', 'processing', None), ('processing', 'resolved', '已核实并提供解决方案')]:
        reply = client.patch(url, headers=auth('manager'), json={'expected_status': old, 'status': new, 'solution': solution})
        assert reply.status_code == 200, reply.text
        with Session(engine) as db:
            assert db.scalar(select(todo_item.c.status)) == ('in_progress' if new == 'processing' else 'done')
    stale = client.patch(url, headers=auth('manager'), json={'expected_status': 'processing', 'status': 'resolved', 'solution': '重复'})
    assert stale.status_code == 409
    results = client.get('/api/v1/student/complaints', headers=auth('101')).json()['data']
    assert results[0]['solution'] == '已核实并提供解决方案' and results[0]['status'] == 'resolved'
    notices = client.get('/api/v1/student/notifications', headers=auth('101')).json()['data']
    assert len(notices) == 1 and notices[0]['related_id'] == row['id']
    assert '已核实并提供解决方案' in str(notices[0]['related_details'])
    assert len(client.get(url + '/history', headers=auth('manager')).json()['data']) == 2
    with Session(engine) as db:
        assert db.scalar(select(todo_item.c.status)) == 'done'
        assert db.scalar(select(func.count()).select_from(notification_log)) == 1
    assert client.patch(url, headers=auth('manager'), json={'expected_status': 'resolved', 'status': 'closed'}).status_code == 200
    assert len(client.get('/api/v1/student/notifications', headers=auth('101')).json()['data']) == 2


def test_leave_approval_is_audited_once_and_processed_record_remains_accessible(teacher_world):
    client, engine = teacher_world
    row = leave(client)
    url = f"/api/v1/student-admin/leaves/{row['id']}"
    assert client.post(url + '/approve', headers=auth('other'), json={'decision': 'approved'}).status_code == 403
    assert client.post(url + '/approve', headers=auth('teacher'), json={'decision': 'rejected', 'approval_comment': '  '}).status_code == 422
    assert client.post(url + '/approve', headers=auth('teacher'), json={'decision': 'approved', 'student_id': 22}).status_code == 422
    decision = {'decision': 'rejected', 'approval_comment': '需补充本次复查时间，请重新申请'}
    response = client.post(url + '/approve', headers=auth('teacher'), json=decision)
    assert response.status_code == 200, response.text
    assert client.post(url + '/approve', headers=auth('teacher'), json=decision).status_code == 409
    assert client.get('/api/v1/student-admin/leaves?status=pending', headers=auth('teacher')).json()['data'] == []
    assert client.get('/api/v1/student-admin/leaves?status=rejected', headers=auth('teacher')).json()['data'][0]['id'] == row['id']
    assert client.get('/api/v1/student-admin/leaves?status=rejected', headers=auth('other')).json()['data'] == []
    history = client.get(url + '/history', headers=auth('teacher')).json()['data']
    assert len(history) == 1 and history[0]['actor_id'] == 30
    assert client.get(url + '/history', headers=auth('other')).status_code == 404
    notices = client.get('/api/v1/student/notifications', headers=auth('101')).json()['data']
    assert len(notices) == 1 and '需补充本次复查时间' in str(notices[0]['related_details'])
    with Session(engine) as db:
        assert db.scalar(select(todo_item.c.status)) == 'done'
        assert db.scalar(select(func.count()).select_from(audit_log).where(audit_log.c.action == 'leave_approved')) == 1


@pytest.mark.parametrize('kind', ['leaves', 'complaints'])
def test_business_todo_cannot_bypass_approval_or_feedback(teacher_world, kind):
    client, engine = teacher_world
    row = leave(client) if kind == 'leaves' else submit(client, kind, dict(category='learning', content='请核实课程安排'))
    todos = client.get('/api/v1/enterprise/todos', headers=auth('teacher')).json()['data']
    assert len(todos) == 1
    for status in ['in_progress', 'done', 'cancelled']:
        response = client.patch('/api/v1/enterprise/todos/' + str(todos[0]['id']), headers=auth('teacher'),
                                json={'expected_status': 'pending', 'status': status})
        assert response.status_code == 409
    with Session(engine) as db:
        assert db.scalar(select(todo_item.c.status)) == 'pending'
        state = db.get(StudentAdminService, row['id']).status if kind == 'leaves' else db.scalar(select(tickets.c.status))
        assert state == 'pending'
        assert db.scalar(select(func.count()).select_from(notification_log)) == 0


def test_approval_notification_failure_rolls_back_entire_decision(teacher_world, monkeypatch):
    from app.modules.student_admin import service
    client, engine = teacher_world
    row = leave(client)
    def fail(*args, **kwargs):
        raise RuntimeError('notification unavailable')
    monkeypatch.setattr(service, 'save_student_result', fail)
    with pytest.raises(RuntimeError, match='notification unavailable'):
        client.post(f"/api/v1/student-admin/leaves/{row['id']}/approve", headers=auth('teacher'), json={'decision': 'approved'})
    with Session(engine) as db:
        assert db.get(StudentAdminService, row['id']).status == 'pending'
        assert db.scalar(select(todo_item.c.status)) == 'pending'
        assert db.scalar(select(func.count()).select_from(audit_log).where(audit_log.c.action == 'leave_approved')) == 0


def test_employee_assistant_redacts_rerouted_ticket_history_and_model_context(teacher_world):
    from app.ai.assistant.service import AssistantService
    from app.ai.assistant.schemas import MessageInput
    from app.core.security import EmployeePrincipal
    client, engine = teacher_world
    row = submit(client, 'complaints', dict(category='learning', content='改派后需要保密的原反馈'))
    principal = EmployeePrincipal(30, frozenset({'ai:use', 'tickets:read'}), role_code='team_leader')
    seen=[]
    class Extractor:
        def extract(self, text, pending, history, **kwargs):
            seen.extend(history)
            return '{"intent":"chat","params":{},"reply":"可以继续说说。"}'
    with Session(engine) as db:
        svc=AssistantService(db, extractor=Extractor())
        cid=svc.repo.create(30, '工单查询')
        nonce=svc.repo.reserve(cid,30,0)
        assert svc.repo.finish(cid,30,1,nonce,'','查询工单','改派后需要保密的原反馈',{
            'action':'tickets','http_status':200,'feedback_ticket_ids':[row['id']],
        })
        db.commit()
        assert svc.detail(cid,principal)['messages'][-1]['content']=='改派后需要保密的原反馈'
        db.execute(tickets.update().where(tickets.c.id==row['id']).values(category='company',assignee_id=11))
        db.commit()
        assert '当前不可查看' in svc.detail(cid,principal)['messages'][-1]['content']
        svc.send(cid,MessageInput(text='请继续分析刚才那个问题',expected_version=1),principal,'test')
        assert '改派后需要保密的原反馈' not in str(seen)
