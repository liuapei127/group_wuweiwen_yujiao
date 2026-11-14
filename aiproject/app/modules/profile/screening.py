from dataclasses import dataclass

from .schemas import (
    Education,
    EducationStage,
    Project,
    ScreeningInput,
    ScreeningResult,
    ScreeningStatus,
)


@dataclass(frozen=True)
class ScreeningRule:
    education: tuple[Education, ...]
    education_stages: tuple[EducationStage, ...] = ()
    age_band: tuple[int, int | None] | None = None
    approximate_age: bool = False


_SG_EMPLOYMENT = ScreeningRule((Education.VOCATIONAL,), age_band=(17, None))
_RULES = {
    Project.SG_JUNIOR: ScreeningRule(
        (Education.JUNIOR,), (EducationStage.GRADUATED,), (14, 16), approximate_age=True
    ),
    Project.SG_SENIOR: ScreeningRule(
        (Education.SENIOR, Education.VOCATIONAL),
        (EducationStage.GRADUATED, EducationStage.SENIOR_YEAR_TWO),
        (16, 19),
        approximate_age=True,
    ),
    Project.SG_HOSPITALITY: _SG_EMPLOYMENT,
    Project.SG_AVIATION: _SG_EMPLOYMENT,
    Project.SG_TOP_UP: ScreeningRule((Education.COLLEGE,), (EducationStage.GRADUATED,)),
    Project.SG_MASTERS: ScreeningRule((Education.BACHELOR,), (EducationStage.GRADUATED,)),
    Project.DE_VOCATIONAL: ScreeningRule(
        (Education.SENIOR, Education.COLLEGE, Education.BACHELOR, Education.POSTGRADUATE),
        (EducationStage.GRADUATED,),
        (18, 35),
    ),
}


def screen_profile(profile: ScreeningInput) -> ScreeningResult:
    """根据申报信息做项目初筛，返回顾问可核对的缺项和依据。"""
    if profile.project is None:
        return ScreeningResult(
            project=None, status=ScreeningStatus.NEEDS_INFORMATION, missing_fields=("project",)
        )

    rule = _RULES[profile.project]
    missing_fields = []
    if profile.education is None:
        missing_fields.append("education")
    if rule.education_stages and profile.education_stage is None:
        missing_fields.append("education_stage")
    if rule.age_band and profile.age is None:
        missing_fields.append("age")
    if missing_fields:
        return ScreeningResult(
            project=profile.project,
            status=ScreeningStatus.NEEDS_INFORMATION,
            missing_fields=tuple(missing_fields),
        )

    vocational_equivalence = (
        profile.project == Project.DE_VOCATIONAL and profile.education == Education.VOCATIONAL
    )
    education_matches = profile.education in rule.education or vocational_equivalence
    stage_matches = not rule.education_stages or profile.education_stage in rule.education_stages
    if profile.education_stage == EducationStage.SENIOR_YEAR_TWO:
        stage_matches = profile.project == Project.SG_SENIOR and profile.education == Education.SENIOR
    if not education_matches or not stage_matches:
        return ScreeningResult(
            project=profile.project,
            status=ScreeningStatus.NOT_MATCHED,
            findings=("申报的学历或在读、毕业状态与该项目招生对象不符。",),
        )

    if rule.age_band and profile.age is not None:
        minimum, maximum = rule.age_band
        if profile.age < minimum or (maximum is not None and profile.age > maximum):
            if rule.approximate_age:
                return ScreeningResult(
                    project=profile.project,
                    status=ScreeningStatus.NEEDS_REVIEW,
                    findings=(f"申报年龄超出资料所列约 {minimum} 至 {maximum} 岁范围，请顾问核对。",),
                )
            return ScreeningResult(
                project=profile.project,
                status=ScreeningStatus.NOT_MATCHED,
                findings=("申报年龄不符合该项目的年龄条件。",),
            )

    if vocational_equivalence:
        return ScreeningResult(
            project=profile.project,
            status=ScreeningStatus.NEEDS_REVIEW,
            findings=("请核对该学历是否符合中德项目的高中及以上学历要求。",),
        )

    return ScreeningResult(
        project=profile.project,
        status=ScreeningStatus.POTENTIAL_MATCH,
        findings=("申报信息符合已核对的初筛条件，后续由顾问核实。",),
    )
