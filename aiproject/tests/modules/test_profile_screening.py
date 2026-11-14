import pytest

from app.modules.profile.schemas import Education, EducationStage, Project, ScreeningInput, ScreeningStatus
from app.modules.profile.screening import screen_profile


def test_partial_intake_can_be_screened_again_after_adviser_supplies_age():
    initial = ScreeningInput(project=Project.SG_HOSPITALITY, education=Education.VOCATIONAL)

    pending = screen_profile(initial)
    completed = screen_profile(initial.model_copy(update={"age": 17}))

    assert pending.status == ScreeningStatus.NEEDS_INFORMATION
    assert pending.missing_fields == ("age",)
    assert completed.status == ScreeningStatus.POTENTIAL_MATCH
    assert completed.missing_fields == ()


@pytest.mark.parametrize(
    ("project", "education", "age", "expected"),
    [
        (Project.SG_JUNIOR, Education.JUNIOR, 17, ScreeningStatus.NEEDS_REVIEW),
        (Project.SG_AVIATION, Education.VOCATIONAL, 16, ScreeningStatus.NOT_MATCHED),
        (Project.SG_AVIATION, Education.VOCATIONAL, 17, ScreeningStatus.POTENTIAL_MATCH),
        (Project.DE_VOCATIONAL, Education.SENIOR, 18, ScreeningStatus.POTENTIAL_MATCH),
        (Project.DE_VOCATIONAL, Education.SENIOR, 35, ScreeningStatus.POTENTIAL_MATCH),
        (Project.DE_VOCATIONAL, Education.VOCATIONAL, 20, ScreeningStatus.NEEDS_REVIEW),
        (Project.DE_VOCATIONAL, Education.VOCATIONAL, 36, ScreeningStatus.NOT_MATCHED),
    ],
)
def test_project_specific_age_and_education_rules(project, education, age, expected):
    profile = ScreeningInput(
        project=project, education=education, education_stage=EducationStage.GRADUATED, age=age
    )

    assert screen_profile(profile).status == expected


def test_singapore_top_up_requires_completed_college():
    profile = ScreeningInput(project=Project.SG_TOP_UP, education=Education.COLLEGE)

    assert screen_profile(profile).missing_fields == ("education_stage",)
    assert screen_profile(
        profile.model_copy(update={"education_stage": EducationStage.ENROLLED})
    ).status == ScreeningStatus.NOT_MATCHED
