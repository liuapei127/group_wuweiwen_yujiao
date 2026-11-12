"""复现 app 不得污染 app.main 的 dependency_overrides。"""
from app.core.auth.dependencies import require_employee
from app.main import app as main_app
from tests.repro.factory import create_repro_app


def test_repro_factory_does_not_touch_main_overrides():
    before = dict(main_app.dependency_overrides)
    repro = create_repro_app()
    assert require_employee in repro.dependency_overrides
    assert main_app.dependency_overrides == before
