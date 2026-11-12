"""Settings 默认值与 app.main 对非法模式的拒绝（不读 .env 文件）。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[2]


def test_default_employee_identity_mode_is_blocked(monkeypatch):
    monkeypatch.delenv("EMPLOYEE_IDENTITY_MODE", raising=False)
    s = Settings(_env_file=None)
    assert s.employee_identity_mode == "blocked"


def test_main_rejects_unknown_employee_identity_mode(monkeypatch):
    monkeypatch.delenv("EMPLOYEE_IDENTITY_MODE", raising=False)
    proc = subprocess.run(
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
    assert proc.returncode != 0
    assert "unknown_xyz" in proc.stderr or "不支持" in proc.stderr
