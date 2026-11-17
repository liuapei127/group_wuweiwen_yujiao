import asyncio

import pytest
from sqlalchemy import create_engine, insert, text, update
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.modules.customer_service import service
from app.modules.customer_service.capacity import CsChatCapacity
from app.modules.customer_service.models import CustomerChatSession
from app.modules.customer_service.schemas import PublicChatRequest
from app.modules.visitor.content_models import WebsiteSection, WebsiteSectionCard


_SINGAPORE_CARD = """新加坡升学项目。
高中毕业生可了解以下升学路径：
• 0.5/1+2 定向培养本科班
• 0.5/1+2+1 本硕连读

初中毕业生可了解以下路径：
• 2+2 新加坡定向培养本科班
• 2+2+1 本硕连读

专科毕业生：专升本
"""


@pytest.fixture
def directory(monkeypatch):
    monkeypatch.setattr(service, "get_settings", lambda: Settings(_env_file=None))
    capacity = CsChatCapacity(2, 1, 20)
    monkeypatch.setattr(service, "get_cs_capacity", lambda: capacity)

    async def no_upstream(*args, **kwargs):
        pytest.fail("The public catalog question should be handled locally")

    monkeypatch.setattr(service, "_request_answer", no_upstream)
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    for model in (WebsiteSection, WebsiteSectionCard, CustomerChatSession):
        model.__table__.create(engine)
    with engine.begin() as conn:
        conn.execute(text("""CREATE TABLE course_project (
            id INTEGER PRIMARY KEY, project_name TEXT, category TEXT, description TEXT,
            target_audience TEXT, duration TEXT, status INTEGER
        )"""))
        conn.execute(text("""INSERT INTO course_project VALUES
            (1, '德语学习', '语言类', '德语学习课程', '前往德国的学生', NULL, 1),
            (2, '已下架初中项目', '留学项目', '面向初中生', '初中毕业生', NULL, 0),
            (3, '德国方向项目', '留学项目', '曾收到初中毕业生咨询', '高中毕业生', NULL, 1),
            (4, '德国衔接项目', '留学项目', '公开路径', '不接受中职、初中毕业生', NULL, 1),
            (5, '新加坡专科衔接', '留学项目', '本科衔接', '专科毕业生', NULL, 1)
        """))
        conn.execute(insert(WebsiteSection).values(
            id=1, anchor="programs", title="留学项目", sort_order=0, published=True,
        ))
        conn.execute(insert(WebsiteSectionCard), [
            dict(id=1, section_id=1, title="新加坡国际本硕升学计划", content=_SINGAPORE_CARD, sort_order=0, published=True),
            dict(id=2, section_id=1, title="中德精英人才共建计划", content="面向德国的项目介绍。", sort_order=1, published=True),
            dict(id=3, section_id=1, title="未公开初中路径", content="初中毕业生：内部路径", sort_order=2, published=False),
        ])
    try:
        with Session(engine) as db:
            yield db
    finally:
        engine.dispose()


def _chat(db, query, **session):
    return asyncio.run(service.chat(PublicChatRequest(query=query, **session), "test", db))


@pytest.mark.parametrize(
    "question, expected, excluded",
    [
        ("我初中毕业适合什么项目", ("2+2 新加坡", "2+2+1"), ("0.5/1+2", "专升本", "内部路径", "德国方向项目", "德国衔接项目")),
        ("我想读本科，我初中毕业，有什么项目？", ("2+2 新加坡",), ("0.5/1+2", "专升本")),
        ("我高中毕业，想去新加坡升学，有什么项目？", ("0.5/1+2", "0.5/1+2+1"), ("2+2 新加坡", "专升本")),
        ("大专毕业适合什么项目？", ("专升本", "新加坡专科衔接"), ("0.5/1+2", "2+2 新加坡")),
        ("专科毕业适合什么项目？", ("专升本", "新加坡专科衔接"), ("0.5/1+2", "2+2 新加坡")),
    ],
)
def test_project_question_selects_only_published_matching_paths(directory, question, expected, excluded):
    rows = service.catalog_for_dify(directory, "recommendations", question)
    catalog = "\n".join(row["name"] + " " + row["summary"] for row in rows)
    answer = _chat(directory, question).answer
    for output in (catalog, answer):
        assert all(term in output for term in expected)
        assert not any(term in output for term in excluded)
    assert rows and all(row["matches_preferences"] for row in rows)


def test_unconfirmed_education_fallback_does_not_show_another_route(directory):
    directory.execute(update(WebsiteSectionCard).where(WebsiteSectionCard.id == 1).values(
        content="新加坡升学。\n高中毕业生：0.5/1+2 定向培养本科班。"
    ))
    directory.commit()
    no_destination = _chat(directory, "我初中毕业适合什么项目").answer
    assert "暂无面向初中学历的公开升学路径" in no_destination
    question = "我初中毕业想去新加坡有什么项目"
    rows = service.catalog_for_dify(directory, "recommendations", question)
    assert "新加坡国际本硕升学计划" in {row["name"] for row in rows}
    assert all(not row["matches_preferences"] for row in rows)
    assert all(row["summary"] == "" and row["target_audience"] is None for row in rows)
    answer = _chat(directory, question).answer
    assert "新加坡国际本硕升学计划" in answer
    assert "0.5/1+2" not in answer
    assert "暂未查到面向初中" in answer


@pytest.mark.parametrize("question", ["德语课程", "德语课", "德语课？"])
def test_language_course_and_project_correction_remain_distinct(directory, question):
    first = _chat(directory, question, start_session=True)
    assert first.session_id
    assert "德语学习" in first.answer and "中德精英人才共建计划" not in first.answer
    next_turn = _chat(directory, "这不是课程吗，我问的是项目", session_id=first.session_id)
    assert "中德精英人才共建计划" in next_turn.answer and "德语学习" not in next_turn.answer
