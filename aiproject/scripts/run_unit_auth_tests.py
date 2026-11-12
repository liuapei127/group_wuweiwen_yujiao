"""无 pytest 时直接执行隔离/配置单元检查，写入 runs 日志。"""
from __future__ import annotations

import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    lines: list[str] = [f"# unit auth tests {datetime.now(timezone.utc).astimezone().isoformat()}", ""]
    failed = 0

    def run(name: str, fn):
        nonlocal failed
        try:
            fn()
            lines.append(f"PASS {name}")
        except Exception as e:
            failed += 1
            lines.append(f"FAIL {name}: {e}")
            lines.append(traceback.format_exc())

    import os

    def test_default():
        os.environ.pop("EMPLOYEE_IDENTITY_MODE", None)
        from app.core.config import Settings

        assert Settings(_env_file=None).employee_identity_mode == "blocked"

    def test_isolation():
        from app.core.auth.dependencies import require_employee
        from app.main import app as main_app
        from tests.repro.factory import create_repro_app

        before = dict(main_app.dependency_overrides)
        repro = create_repro_app()
        assert repro is not main_app
        assert require_employee in repro.dependency_overrides
        assert main_app.dependency_overrides == before

    def test_unknown_main():
        import subprocess

        p = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                "-c",
                "import os; os.environ['EMPLOYEE_IDENTITY_MODE']='unknown_xyz'; import app.main",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=str(ROOT),
        )
        assert p.returncode != 0
        assert "unknown_xyz" in p.stderr
        assert "RuntimeError" in p.stderr

    run("default_blocked", test_default)
    run("independent_app_and_overrides", test_isolation)
    run("unknown_mode_expected_runtime_error", test_unknown_main)

    out = ROOT / "docs" / "回复Cursor" / "runs" / "unit-auth-tests.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
