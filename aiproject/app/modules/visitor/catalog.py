from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import BigInteger, Integer, Numeric, String, Text, column, insert, or_, select, table, update
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError

_courses = table(
    "course_project", column("id", BigInteger), column("project_name", String),
    column("category", String), column("description", Text), column("target_audience", String),
    column("duration", String), column("price", Numeric), column("status", Integer),
)


class CourseOut(BaseModel):
    id: int
    project_name: str
    category: str | None
    description: str | None
    target_audience: str | None
    duration: str | None
    price: Decimal | None = None


class CoursePage(BaseModel):
    items: list[CourseOut]
    next_after_id: int | None


class CourseWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    project_name: str = Field(min_length=1, max_length=255)
    category: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=10000)
    target_audience: str | None = Field(default=None, max_length=255)
    duration: str | None = Field(default=None, max_length=64)
    price: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2, deprecated=True)
    status: Literal[0, 1] = 0


class StaffCourse(CourseOut):
    status: Literal[0, 1]


class StaffCoursePage(BaseModel):
    items: list[StaffCourse]
    next_after_id: int | None


_catalog_fields = [_courses.c[name] for name in CourseOut.model_fields if name != "price"]


def _catalog_rows(db: Session, keyword: str, after_id: int, limit: int, *, public: bool):
    fields = _catalog_fields if public else [*_catalog_fields, _courses.c.status]
    stmt = select(*fields).where(_courses.c.id > after_id)
    if public:
        stmt = stmt.where(_courses.c.status == 1)
    if keyword:
        stmt = stmt.where(or_(
            _courses.c.project_name.contains(keyword, autoescape=True),
            _courses.c.category.contains(keyword, autoescape=True),
        ))
    rows = db.execute(stmt.order_by(_courses.c.id).limit(limit + 1)).mappings().all()
    return rows[:limit], rows[limit - 1]["id"] if len(rows) > limit else None


def list_courses(db: Session, keyword: str, after_id: int, limit: int) -> CoursePage:
    rows, next_id = _catalog_rows(db, keyword, after_id, limit, public=True)
    return CoursePage(items=[CourseOut.model_validate(row) for row in rows], next_after_id=next_id)


def matching_courses(db: Session, terms: list[str], limit: int = 5, *,
                     kind: Literal["project", "course"] | None = None) -> list[CourseOut]:
    stmt = select(*_catalog_fields).where(
        _courses.c.status == 1,
        or_(_courses.c.category.is_(None), _courses.c.category != "本地测试"),
    )
    category = _courses.c.category
    course = or_(category.contains("课程"), category.in_(("语言", "语言类")))
    project = or_(category.contains("项目"), category.in_(("留学", "留学类", "升学", "升学类")))
    if kind == "project":
        stmt = stmt.where(project, ~course)
    elif kind == "course":
        stmt = stmt.where(course)
    for term in terms:
        stmt = stmt.where(or_(*(
            field.contains(term, autoescape=True)
            for field in (_courses.c.project_name, _courses.c.category,
                          _courses.c.target_audience, _courses.c.description)
        )))
    return [CourseOut.model_validate(row) for row in
            db.execute(stmt.order_by(_courses.c.id).limit(limit)).mappings()]


def staff_courses(db: Session, keyword: str, after_id: int, limit: int) -> StaffCoursePage:
    rows, next_id = _catalog_rows(db, keyword, after_id, limit, public=False)
    return StaffCoursePage(items=[StaffCourse.model_validate(row) for row in rows], next_after_id=next_id)


def save_course(db: Session, payload: CourseWrite, course_id: int | None = None) -> StaffCourse:
    values = payload.model_dump(exclude={"price"})
    values["price"] = None
    try:
        if course_id is None:
            course_id = db.execute(insert(_courses).values(**values)).lastrowid
        else:
            stmt = select(_courses.c.id).where(_courses.c.id == course_id).with_for_update()
            if db.scalar(stmt) is None:
                raise BusinessError(404, "课程不存在")
            db.execute(update(_courses).where(_courses.c.id == course_id).values(**values))
        row = db.execute(select(*_catalog_fields, _courses.c.status).where(
            _courses.c.id == course_id,
        )).mappings().one()
        result = StaffCourse.model_validate(row)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return result
