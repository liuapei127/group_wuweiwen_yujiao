from typing import Literal

from pydantic import BaseModel, HttpUrl


class PolicyResource(BaseModel):
    title: str
    description: str
    publisher: str
    url: HttpUrl


class StudentPolicies(BaseModel):
    country: Literal["Singapore", "Germany"] | None
    resources: tuple[PolicyResource, ...] = ()


_COUNTRIES: dict[str, Literal["Singapore", "Germany"]] = {
    "singapore": "Singapore",
    "新加坡": "Singapore",
    "germany": "Germany",
    "德国": "Germany",
}

_RESOURCES: dict[str, tuple[PolicyResource, ...]] = {
    "Singapore": (
        PolicyResource(
            title="新加坡学生准证",
            description="按院校类型查阅学生准证的申请、续办和办理手续。",
            publisher="新加坡移民与关卡局（ICA）",
            url="https://www.ica.gov.sg/information-and-e-services/long-term-visit-and-study/student-s-pass",
        ),
    ),
    "Germany": (
        PolicyResource(
            title="德国职业培训签证",
            description="查看双元制及其他职业培训的签证要求与申请入口。",
            publisher="德国联邦政府门户 Make it in Germany",
            url="https://www.make-it-in-germany.com/en/visa-recognition/visa-types/training",
        ),
        PolicyResource(
            title="德国高校入学条件",
            description="查询学历认可、院校入学和语言要求。",
            publisher="德国学术交流中心（DAAD）",
            url="https://www.daad.de/en/studying-in-germany/requirements/overview/",
        ),
        PolicyResource(
            title="德国签证与长期居留",
            description="查看德国驻华使领馆发布的留学和职业培训签证资料。",
            publisher="德国驻华使领馆",
            url="https://china.diplo.de/cn-zh/service/visa-einreise/nationales-visum-1345434",
        ),
    ),
}


def study_policies(destination: str | None) -> StudentPolicies:
    country = _COUNTRIES.get(destination.strip().casefold()) if destination else None
    return StudentPolicies(country=country, resources=_RESOURCES[country] if country else ())


def destination_labels(country: str) -> tuple[str, ...]:
    return tuple(label for label, normalized in _COUNTRIES.items() if normalized == country)
