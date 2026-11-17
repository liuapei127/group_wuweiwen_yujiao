"""Bulk dataset for local V11 full-system testing — realistic names, mobiles and copy.

Tracks inserted row IDs in logs/qa-v11-seed-ids.json for --reset; nothing user-facing is tagged QA.
Only loopback MySQL."""
from __future__ import annotations

import argparse
import json
import random
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from app.core.config import get_settings
from app.core.security.credentials import utc_now

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "logs" / "qa-v11-seed-summary.json"
IDS_PATH = ROOT / "logs" / "qa-v11-seed-ids.json"

# Legacy markers from an earlier script revision (still purged on --reset).
LEGACY_LEAD_CHANNEL = "qa_v11_bulk"
LEGACY_CONTENT_PREFIX = "【QA-V11】"

SURNAMES = (
    "王", "李", "张", "刘", "陈", "杨", "赵", "黄", "周", "吴", "徐", "孙", "胡", "朱", "高", "林", "何", "郭", "马", "罗",
)
GIVEN = (
    "伟", "芳", "娜", "敏", "静", "丽", "强", "磊", "军", "洋", "勇", "艳", "杰", "娟", "涛", "明", "超", "秀英", "建华", "志强",
    "婷婷", "浩然", "子涵", "雨桐", "梓轩", "欣怡", "宇航", "佳琪", "博文", "思涵",
)
MOBILE_PREFIXES = (
    "130", "131", "132", "133", "134", "135", "136", "137", "138", "139",
    "150", "151", "152", "153", "155", "156", "157", "158", "159",
    "166", "167", "171", "172", "173", "175", "176", "177", "178",
    "180", "181", "182", "183", "184", "185", "186", "187", "188", "189",
)
SCHOOLS = (
    "慕尼黑工业大学", "亚琛应用技术大学", "新加坡管理学院", "悉尼科技大学",
    "曼彻斯特大学", "纽约州立大学", "北京外国语大学", "华东师范大学",
)
STATUSES = ("new", "contacting", "qualified", "signed", "lost")
STATUS_WEIGHTS = (30, 25, 20, 15, 10)
COUNTRIES = ("德国", "新加坡", "英国", "美国", "澳大利亚")
EDUCATIONS = ("初中", "高中", "大专", "本科", "硕士")
CHANNELS = ("官网", "转介绍", "教育展", "合作渠道", "老生推荐")
PROJECTS = ("预科", "语言班", "本硕", "硕士")
EMOTION_TAGS = ("平稳", "焦虑", "低落", "积极", "压力")
TRIGGER_REASONS = ("学习压力增大", "生活适应困难", "人际关系紧张", "情绪低落", "考试焦虑")
REPORT_TYPES = ("customer_ops", "complaint_weekly", "psych_weekly", "daily_summary", "weekly_summary")
REPORT_TYPE_TITLE = {
    "customer_ops": "客户经营周报",
    "complaint_weekly": "投诉周报",
    "psych_weekly": "心理健康周报",
    "daily_summary": "员工日报汇总",
    "weekly_summary": "员工周报汇总",
}
FOLLOW_UP_LINES = (
    "电话沟通顺利，客户计划下周到店面谈。",
    "微信已发送项目资料，客户表示需要和家里商量。",
    "已确认意向国家，下一步安排语言测评。",
    "客户暂时观望，约定两周后再回访。",
)
COMPLAINT_LEARNING = (
    "希望能把周末补课调整到工作日晚间，最近行程冲突较多。",
    "语言课进度略快，希望老师适当放慢节奏并增加练习讲评。",
    "线上作业反馈不够及时，希望班主任能督促任课老师当日回复。",
)
COMPLAINT_COMPANY = (
    "前台接待等待时间偏长，建议优化预约到店时段。",
    "咨询联络间隔较长，希望固定对接顾问并及时回电。",
    "合同条款讲解希望更细致，最好提供书面说明留存。",
)
PSYCH_NOTES = (
    "自述近期失眠，对学习节奏有焦虑，已建议规律作息。",
    "与同班同学交流减少，情绪偏低落，需持续关注。",
    "考试周压力上升，情绪整体平稳，继续观察。",
    "适应境外生活较好，情绪积极。",
)


class SeedRegistry:
    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, list[int]] = {}
        if path.is_file():
            self.data = json.loads(path.read_text(encoding="utf-8"))

    def add(self, key: str, row_id: int) -> None:
        self.data.setdefault(key, []).append(int(row_id))

    def save(self) -> None:
        self.path.parent.mkdir(exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def count(self, key: str) -> int:
        return len(self.data.get(key, []))


class RealisticData:
    def __init__(self, conn, seed: int):
        self._rng = random.Random(seed)
        self._used_names: set[str] = set()
        self._used_mobiles: set[str] = set()
        existing = conn.scalars(text("SELECT contact_info FROM crm_lead WHERE contact_info IS NOT NULL")).all()
        self._used_mobiles.update(str(m) for m in existing if m)

    def name(self) -> str:
        for _ in range(200):
            candidate = self._rng.choice(SURNAMES) + self._rng.choice(GIVEN)
            if candidate not in self._used_names:
                self._used_names.add(candidate)
                return candidate
        return self._rng.choice(SURNAMES) + self._rng.choice(GIVEN) + str(self._rng.randint(1, 9))

    def mobile(self) -> str:
        for _ in range(500):
            prefix = self._rng.choice(MOBILE_PREFIXES)
            suffix = f"{self._rng.randint(0, 99999999):08d}"
            phone = prefix + suffix
            if phone not in self._used_mobiles:
                self._used_mobiles.add(phone)
                return phone
        raise RuntimeError("Unable to allocate unique mobile number")


def _engine():
    settings = get_settings()
    if settings.db_host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("Only local MySQL is allowed")
    return create_engine(
        URL.create(
            "mysql+pymysql",
            username=settings.db_user,
            password=settings.db_password,
            host=settings.db_host,
            port=settings.db_port,
            database=settings.db_name,
        )
    ), settings


def _staff_ids(conn) -> dict[str, int]:
    rows = conn.execute(
        text(
            "SELECT username, id FROM sys_user WHERE username IN "
            "('19900001101','19900001102','19900001103','19900001104') AND status='normal'"
        )
    ).all()
    by_user = {row.username: int(row.id) for row in rows}
    missing = [u for u in ("19900001101", "19900001102", "19900001103", "19900001104") if u not in by_user]
    if missing:
        raise SystemExit(f"Missing demo staff accounts: {', '.join(missing)}")
    return {
        "admin": by_user["19900001101"],
        "advisor": by_user["19900001102"],
        "manager": by_user["19900001103"],
        "teacher": by_user["19900001104"],
    }


def _active_students(conn) -> list[dict]:
    rows = conn.execute(
        text(
            """
            SELECT si.user_id AS student_id, COALESCE(ce.class_id, 0) AS class_id,
                   COALESCE(si.class_teacher_id, pc.teacher_id) AS teacher_id
            FROM student_info si
            LEFT JOIN student_class_enrollment ce ON ce.student_id = si.user_id
            LEFT JOIN project_class pc ON pc.id = ce.class_id
            WHERE si.status = 'active'
            ORDER BY si.user_id
            LIMIT 80
            """
        )
    ).mappings()
    return [dict(row) for row in rows]


def _delete_ids(conn, table: str, column: str, ids: list[int]) -> None:
    if not ids:
        return
    chunk = ",".join(str(i) for i in ids)
    conn.execute(text(f"DELETE FROM {table} WHERE {column} IN ({chunk})"))


def _purge_registry(conn, registry: SeedRegistry) -> None:
    leads = registry.data.get("leads", [])
    if leads:
        lid = ",".join(str(i) for i in leads)
        conn.execute(text(f"DELETE FROM crm_lead_status_event WHERE lead_id IN ({lid})"))
    _delete_ids(conn, "crm_follow_up", "id", registry.data.get("follow_ups", []))
    _delete_ids(conn, "customer_profile", "id", registry.data.get("profiles", []))
    _delete_ids(conn, "crm_lead", "id", leads)
    tickets = registry.data.get("tickets", [])
    if tickets:
        targets = ",".join(f"'{t}'" for t in tickets)
        conn.execute(text(f"DELETE FROM ent_auth_audit WHERE target IN ({targets})"))
    _delete_ids(conn, "student_feedback_ticket", "id", tickets)
    _delete_ids(conn, "ent_auth_audit", "id", registry.data.get("audits", []))
    _delete_ids(conn, "report_generation", "id", registry.data.get("archives", []))
    _delete_ids(conn, "employee_daily_report", "id", registry.data.get("daily_reports", []))
    for row in registry.data.get("weekly_rows", []):
        conn.execute(
            text("DELETE FROM employee_weekly_submission WHERE employee_id=:e AND week_start=:w"),
            {"e": row["employee_id"], "w": row["week_start"]},
        )
    _delete_ids(conn, "application_progress", "id", registry.data.get("application_progress", []))
    _delete_ids(conn, "academic_deadline", "id", registry.data.get("academic_deadline", []))
    _delete_ids(conn, "student_psych_alert", "id", registry.data.get("psych_alerts", []))
    _delete_ids(conn, "student_psych_record", "id", registry.data.get("psych_records", []))


def _purge_legacy(conn) -> None:
    lead_ids = conn.scalars(
        text("SELECT id FROM crm_lead WHERE source_channel = :m OR customer_name LIKE 'QA客户%'"),
        {"m": LEGACY_LEAD_CHANNEL},
    ).all()
    if lead_ids:
        ids = ",".join(str(i) for i in lead_ids)
        conn.execute(text(f"DELETE FROM crm_lead_status_event WHERE lead_id IN ({ids})"))
        conn.execute(text(f"DELETE FROM customer_profile WHERE lead_id IN ({ids})"))
        conn.execute(text(f"DELETE FROM crm_follow_up WHERE lead_id IN ({ids})"))
        conn.execute(text(f"DELETE FROM crm_lead WHERE id IN ({ids})"))
    for pattern in (f"{LEGACY_CONTENT_PREFIX}%", "【QA-V11】%"):
        conn.execute(text("DELETE FROM employee_daily_report WHERE content LIKE :p"), {"p": pattern})
        conn.execute(text("DELETE FROM employee_weekly_submission WHERE content LIKE :p"), {"p": pattern})
        ticket_ids = conn.scalars(
            text("SELECT id FROM student_feedback_ticket WHERE content LIKE :p"), {"p": pattern}
        ).all()
        if ticket_ids:
            targets = ",".join(f"'{t}'" for t in ticket_ids)
            conn.execute(text(f"DELETE FROM ent_auth_audit WHERE target IN ({targets})"))
            id_list = ",".join(str(t) for t in ticket_ids)
            conn.execute(text(f"DELETE FROM student_feedback_ticket WHERE id IN ({id_list})"))
    conn.execute(
        text("DELETE FROM report_generation WHERE report_title LIKE :p"),
        {"p": f"{LEGACY_CONTENT_PREFIX}%"},
    )
    conn.execute(text("DELETE FROM student_psych_record WHERE interaction_content LIKE :p"), {"p": f"{LEGACY_CONTENT_PREFIX}%"})


def _purge_qa(conn, reset_registry: bool) -> None:
    if reset_registry and IDS_PATH.is_file():
        registry = SeedRegistry(IDS_PATH)
        _purge_registry(conn, registry)
        IDS_PATH.unlink(missing_ok=True)
    _purge_legacy(conn)


def _status_chain(rng: random.Random, final: str) -> list[str]:
    order = ["new", "contacting", "qualified", "signed"]
    if final == "lost":
        base = rng.choice([["new", "contacting"], ["new", "contacting", "qualified"]])
        return base + ["lost"]
    if final == "signed":
        return order
    idx = order.index(final) if final in order else 0
    return order[: idx + 1]


def seed_leads(conn, staff: dict[str, int], target: int, now: datetime, registry: SeedRegistry, gen: RealisticData) -> int:
    existing = registry.count("leads")
    need = max(0, target - existing)
    if not need:
        return 0
    rng = gen._rng
    created = 0
    match_reasons = (
        "语言基础达标，与预科项目匹配度较高。",
        "学历背景符合新加坡本硕路径，需补充作品集。",
        "目标国家明确，建议先安排测评再签约。",
    )
    for _ in range(need):
        final = rng.choices(STATUSES, weights=STATUS_WEIGHTS, k=1)[0]
        name = gen.name()
        created_at = now - timedelta(days=rng.randint(0, 380))
        last_contact = created_at + timedelta(days=rng.randint(0, 45)) if final != "new" else None
        row = conn.execute(
            text(
                """
                INSERT INTO crm_lead (
                    customer_name, contact_info, gender, age, education_level, intended_country,
                    intended_major, intended_project, source_channel, status, owner_employee_id,
                    last_contact_time, remark, create_time, update_time
                ) VALUES (
                    :name, :contact, :gender, :age, :edu, :country, :major, :project, :channel,
                    :status, :owner, :last_contact, :remark, :created, :updated
                )
                """
            ),
            {
                "name": name,
                "contact": gen.mobile(),
                "gender": rng.choice(("M", "F", "U")),
                "age": rng.randint(16, 42),
                "edu": rng.choice(EDUCATIONS),
                "country": rng.choice(COUNTRIES),
                "major": rng.choice(("计算机科学", "国际商务", "机械工程", "新闻传播", "教育学")),
                "project": rng.choice(PROJECTS),
                "channel": rng.choice(CHANNELS),
                "status": final,
                "owner": staff["advisor"],
                "last_contact": last_contact,
                "remark": rng.choice(("首次咨询", "展会意向", "朋友推荐", None)),
                "created": created_at,
                "updated": last_contact or created_at,
            },
        )
        lead_id = int(row.lastrowid)
        registry.add("leads", lead_id)
        event_at = created_at
        for status in _status_chain(rng, final):
            conn.execute(
                text(
                    "INSERT INTO crm_lead_status_event (lead_id, status, occurred_at) "
                    "VALUES (:lid, :st, :ts)"
                ),
                {"lid": lead_id, "st": status, "ts": event_at},
            )
            event_at += timedelta(days=rng.randint(1, 10))
        score = Decimal(str(rng.randint(45, 96)))
        prow = conn.execute(
            text(
                """
                INSERT INTO customer_profile (
                    customer_name, lead_id, match_result, matched_product, match_score,
                    match_reason, create_time, update_time
                ) VALUES (
                    :name, :lid, 'matched', :product, :score, :reason, :created, :updated
                )
                """
            ),
            {
                "name": name,
                "lid": lead_id,
                "product": rng.choice(PROJECTS),
                "score": score,
                "reason": rng.choice(match_reasons),
                "created": created_at,
                "updated": created_at,
            },
        )
        registry.add("profiles", int(prow.lastrowid))
        if rng.random() < 0.35:
            frow = conn.execute(
                text(
                    """
                    INSERT INTO crm_follow_up (lead_id, employee_id, follow_type, content, create_time)
                    VALUES (:lid, :emp, 'phone', :body, :ts)
                    """
                ),
                {
                    "lid": lead_id,
                    "emp": staff["advisor"],
                    "body": rng.choice(FOLLOW_UP_LINES),
                    "ts": last_contact or created_at,
                },
            )
            registry.add("follow_ups", int(frow.lastrowid))
        created += 1
    return created


def seed_wellbeing(
    conn,
    students: list[dict],
    anchor: date,
    now: datetime,
    weeks: int,
    registry: SeedRegistry,
    gen: RealisticData,
) -> dict[str, int]:
    counts = {"consent": 0, "checkin": 0, "record": 0, "alert": 0}
    if not students:
        return counts
    rng = gen._rng
    emotion_choices = ("good", "fair", "poor", "poor", "high")
    for row in students:
        sid = int(row["student_id"])
        teacher = int(row["teacher_id"] or 0) or None
        if not conn.scalar(text("SELECT 1 FROM report_wellbeing_consent WHERE student_id=:s"), {"s": sid}):
            conn.execute(
                text(
                    "INSERT INTO report_wellbeing_consent (student_id, granted, version, updated_at) "
                    "VALUES (:s, 1, 'v1', :ts)"
                ),
                {"s": sid, "ts": now},
            )
            counts["consent"] += 1
        for week in range(weeks):
            monday = anchor - timedelta(days=7 * week)
            for offset in range(7):
                day = monday + timedelta(days=offset)
                emotion = rng.choice(emotion_choices)
                conn.execute(
                    text(
                        """
                        INSERT INTO report_wellbeing_checkin (student_id, day, emotion, stress, updated_at)
                        VALUES (:s, :d, :e, 'light', :ts)
                        ON DUPLICATE KEY UPDATE emotion=VALUES(emotion), updated_at=VALUES(updated_at)
                        """
                    ),
                    {"s": sid, "d": day, "e": emotion, "ts": now},
                )
                counts["checkin"] += 1
                rrow = conn.execute(
                    text(
                        """
                        INSERT INTO student_psych_record (
                            student_id, emotion_tag, emotion_score, interaction_content, record_date, create_time
                        ) VALUES (:s, :tag, :score, :body, :d, :ts)
                        """
                    ),
                    {
                        "s": sid,
                        "tag": rng.choice(EMOTION_TAGS),
                        "score": rng.randint(35, 92),
                        "body": rng.choice(PSYCH_NOTES),
                        "d": day,
                        "ts": now,
                    },
                )
                registry.add("psych_records", int(rrow.lastrowid))
                counts["record"] += 1
        if rng.random() < 0.4:
            arow = conn.execute(
                text(
                    """
                    INSERT INTO student_psych_alert (
                        student_id, trigger_reason, risk_level, status, teacher_id, create_time, update_time
                    ) VALUES (:s, :reason, :risk, :status, :t, :c, :u)
                    """
                ),
                {
                    "s": sid,
                    "reason": rng.choice(TRIGGER_REASONS),
                    "risk": rng.choice(("low", "medium", "high")),
                    "status": rng.choice(("pending", "following", "resolved")),
                    "t": teacher,
                    "c": now - timedelta(days=rng.randint(0, 10)),
                    "u": now,
                },
            )
            registry.add("psych_alerts", int(arow.lastrowid))
            counts["alert"] += 1
    return counts


def seed_complaints(
    conn, students: list[dict], staff: dict[str, int], count: int, now: datetime, registry: SeedRegistry, gen: RealisticData
) -> int:
    if not students or count <= 0:
        return 0
    rng = gen._rng
    created = 0
    for _ in range(count):
        student = rng.choice(students)
        created_time = now - timedelta(days=rng.randint(5, 90), hours=rng.randint(0, 12))
        assignee = staff["teacher"] if rng.random() < 0.7 else staff["manager"]
        status = rng.choice(("pending", "processing", "resolved", "resolved"))
        cat = rng.choice(("learning", "company"))
        content = rng.choice(COMPLAINT_LEARNING if cat == "learning" else COMPLAINT_COMPANY)
        row = conn.execute(
            text(
                """
                INSERT INTO student_feedback_ticket (
                    student_id, ticket_type, category, content, status, priority, assignee_id,
                    is_notified, create_time, update_time
                ) VALUES (
                    :sid, 'complaint', :cat, :content, :status, 'medium', :assignee, 0, :created, :updated
                )
                """
            ),
            {
                "sid": int(student["student_id"]),
                "cat": cat,
                "content": content,
                "status": status,
                "assignee": assignee,
                "created": created_time,
                "updated": created_time + timedelta(hours=rng.randint(4, 72)),
            },
        )
        ticket_id = int(row.lastrowid)
        registry.add("tickets", ticket_id)
        if status in ("processing", "resolved"):
            t1 = created_time + timedelta(hours=rng.randint(2, 24))
            arow = conn.execute(
                text(
                    """
                    INSERT INTO ent_auth_audit (actor_id, action, target, details, create_time)
                    VALUES (:actor, 'ticket_processed', :target, :details, :ts)
                    """
                ),
                {
                    "actor": assignee,
                    "target": str(ticket_id),
                    "details": json.dumps(
                        {"previous_status": "pending", "status": "processing"}, ensure_ascii=False
                    ),
                    "ts": t1,
                },
            )
            registry.add("audits", int(arow.lastrowid))
        if status == "resolved":
            t2 = created_time + timedelta(hours=rng.randint(24, 120))
            arow = conn.execute(
                text(
                    """
                    INSERT INTO ent_auth_audit (actor_id, action, target, details, create_time)
                    VALUES (:actor, 'ticket_processed', :target, :details, :ts)
                    """
                ),
                {
                    "actor": assignee,
                    "target": str(ticket_id),
                    "details": json.dumps(
                        {
                            "previous_status": "processing",
                            "status": "resolved",
                            "solution": "已与学生及授课老师沟通，给出调整方案并记录在案。",
                        },
                        ensure_ascii=False,
                    ),
                    "ts": t2,
                },
            )
            registry.add("audits", int(arow.lastrowid))
        created += 1
    return created


def seed_employee_reports(
    conn, staff: dict[str, int], days: int, weeks: int, now: datetime, registry: SeedRegistry, gen: RealisticData
) -> dict[str, int]:
    counts = {"daily": 0, "weekly": 0}
    rng = gen._rng
    daily_lines = (
        "今日回访意向客户 4 位，整理资料 2 份，协调班主任跟进 1 次。",
        "完成活动邀约确认，更新 CRM 跟进记录 6 条。",
        "陪同客户测评，补充研判意见并同步项目经理。",
    )
    for emp in (staff["advisor"], staff["teacher"], staff["manager"]):
        for day_offset in range(days):
            report_date = now.date() - timedelta(days=day_offset)
            existing = conn.scalar(
                text(
                    "SELECT id FROM employee_daily_report WHERE employee_id=:e AND report_date=:d"
                ),
                {"e": emp, "d": report_date},
            )
            if existing:
                continue
            drow = conn.execute(
                text(
                    """
                    INSERT INTO employee_daily_report (
                        employee_id, report_date, content, status, create_time
                    ) VALUES (:emp, :d, :content, 'submitted', :ts)
                    """
                ),
                {
                    "emp": emp,
                    "d": report_date,
                    "content": rng.choice(daily_lines),
                    "ts": datetime.combine(report_date, datetime.min.time()) + timedelta(hours=9),
                },
            )
            registry.add("daily_reports", int(drow.lastrowid))
            counts["daily"] += 1
        for week in range(weeks):
            week_start = now.date() - timedelta(days=now.weekday() + 7 * week)
            if conn.scalar(
                text("SELECT 1 FROM employee_weekly_submission WHERE employee_id=:e AND week_start=:w"),
                {"e": emp, "w": week_start},
            ):
                continue
            conn.execute(
                text(
                    """
                    INSERT INTO employee_weekly_submission (
                        employee_id, week_start, content, key_progress, risks, next_plan, submitted_at
                    ) VALUES (:emp, :ws, :content, :kp, :rk, :np, :ts)
                    """
                ),
                {
                    "emp": emp,
                    "ws": week_start,
                    "content": f"本周完成客户跟进与教学协同，周期 {week_start.isoformat()} 起。",
                    "kp": "重点意向客户 2 组进入资料核验阶段。",
                    "rk": "部分客户决策周期拉长，需加强家校沟通。",
                    "np": "下周安排德语测评与新加坡路径说明会。",
                    "ts": datetime.combine(week_start, datetime.min.time()) + timedelta(days=5, hours=10),
                },
            )
            registry.data.setdefault("weekly_rows", []).append(
                {"employee_id": emp, "week_start": week_start.isoformat()}
            )
            counts["weekly"] += 1
    return counts


def seed_archives(conn, staff: dict[str, int], per_type: int, anchor: date, registry: SeedRegistry) -> int:
    created = 0
    for kind in REPORT_TYPES:
        label = REPORT_TYPE_TITLE[kind]
        for page in range(per_type):
            period_end = anchor - timedelta(days=7 * page)
            period_start = period_end - timedelta(days=6 if kind == "psych_weekly" else 0)
            title = f"{label}（{period_start.isoformat()} 至 {period_end.isoformat()}）"
            row = conn.execute(
                text(
                    """
                    INSERT INTO report_generation (
                        report_type, report_title, report_content, period_start, period_end,
                        generated_by, status, create_time
                    ) VALUES (
                        :kind, :title, :payload, :ps, :pe, :by, 'completed', :created
                    )
                    """
                ),
                {
                    "kind": kind,
                    "title": title,
                    "payload": json.dumps(
                        {"summary": "周期统计归档", "report_kind": kind}, ensure_ascii=False
                    ),
                    "ps": period_start,
                    "pe": period_end,
                    "by": staff["manager"],
                    "created": datetime.combine(period_end, datetime.min.time()) + timedelta(hours=18),
                },
            )
            registry.add("archives", int(row.lastrowid))
            created += 1
    return created


def seed_project_health_samples(
    conn, students: list[dict], staff: dict[str, int], now: datetime, registry: SeedRegistry, gen: RealisticData
) -> int:
    if not students:
        return 0
    rng = gen._rng
    touched = 0
    for row in students[: min(25, len(students))]:
        sid = int(row["student_id"])
        teacher = int(row["teacher_id"] or staff["teacher"])
        school = rng.choice(SCHOOLS)
        if rng.random() < 0.25:
            prow = conn.execute(
                text(
                    """
                    INSERT INTO application_progress (
                        student_id, target_school, stage, deadline, next_action, handler_id, create_time, update_time
                    ) VALUES (
                        :sid, :school, 'under_review', :deadline, '补充语言成绩', :handler, :c, :u
                    )
                    """
                ),
                {
                    "sid": sid,
                    "school": school,
                    "deadline": (now.date() - timedelta(days=rng.randint(3, 20))),
                    "handler": teacher,
                    "c": now,
                    "u": now,
                },
            )
            registry.add("application_progress", int(prow.lastrowid))
            touched += 1
        if rng.random() < 0.2:
            drow = conn.execute(
                text(
                    """
                    INSERT INTO academic_deadline (
                        student_id, deadline_type, study_stage, title, deadline, status, create_time, update_time
                    ) VALUES (
                        :sid, 'exam', 'language', :title, :deadline, 'missed', :c, :u
                    )
                    """
                ),
                {
                    "sid": sid,
                    "title": "德语 B1 模拟考试",
                    "deadline": now - timedelta(days=rng.randint(1, 15)),
                    "c": now,
                    "u": now,
                },
            )
            registry.add("academic_deadline", int(drow.lastrowid))
            touched += 1
    return touched


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", required=True)
    parser.add_argument("--reset", action="store_true", help="Remove prior seeded rows (registry + legacy fake tags)")
    parser.add_argument("--leads", type=int, default=250, help="Target lead count tracked in registry")
    parser.add_argument("--complaints", type=int, default=60)
    parser.add_argument("--archive-per-type", type=int, default=8)
    parser.add_argument("--wellbeing-weeks", type=int, default=8)
    parser.add_argument("--employee-report-days", type=int, default=28)
    args = parser.parse_args()

    engine, settings = _engine()
    now = utc_now()
    anchor = now.date()
    registry = SeedRegistry(IDS_PATH)
    summary: dict = {"database": settings.db_name, "at": now.isoformat(), "data_style": "realistic"}

    with engine.begin() as conn:
        if args.reset:
            _purge_qa(conn, reset_registry=True)
            registry = SeedRegistry(IDS_PATH)
            summary["reset"] = True
        else:
            _purge_legacy(conn)
        staff = _staff_ids(conn)
        students = _active_students(conn)
        gen = RealisticData(conn, 20261117)
        summary["staff"] = staff
        summary["active_students"] = len(students)
        summary["leads_added"] = seed_leads(conn, staff, max(args.leads, 1), now, registry, gen)
        summary["wellbeing"] = seed_wellbeing(
            conn, students, anchor, now, max(args.wellbeing_weeks, 1), registry, gen
        )
        summary["complaints_added"] = seed_complaints(
            conn, students, staff, max(args.complaints, 0), now, registry, gen
        )
        summary["employee_reports"] = seed_employee_reports(
            conn, staff, max(args.employee_report_days, 1), 8, now, registry, gen
        )
        summary["archives_added"] = seed_archives(conn, staff, max(args.archive_per_type, 1), anchor, registry)
        summary["project_health_touched"] = seed_project_health_samples(
            conn, students, staff, now, registry, gen
        )
        summary["seeded_lead_total"] = registry.count("leads")

    registry.save()
    SUMMARY.parent.mkdir(exist_ok=True)
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"ID registry: {IDS_PATH}")
    print(f"Summary: {SUMMARY}")


if __name__ == "__main__":
    main()