"""Regression checks for validation guards; never connect to a database."""
import subprocess
import sys
from pathlib import Path

import pytest
from scripts import local_ent_validation as validation

ROOT = Path(__file__).resolve().parents[2]


def test_default_comparison_preserves_zero_empty_case_and_spaces():
    assert validation.normalized_default(None) is None
    assert validation.normalized_default(0) == "0"
    assert validation.normalized_default("") == ""
    assert validation.normalized_default("A B") == "A B"
    assert validation.normalized_default("a b") != validation.normalized_default("A B")
    assert validation.normalized_default("CURRENT_TIMESTAMP()") == "current_timestamp"


def test_unparsed_standard_sql_refuses_audit(tmp_path, monkeypatch):
    standard = tmp_path / "invalid.sql"
    standard.write_text("-- no definitions", encoding="utf-8")
    monkeypatch.setattr(validation, "SQL_FILE", standard)
    with pytest.raises(RuntimeError, match="No standard CREATE TABLE"):
        validation.audit(None)


def test_optimized_python_refuses_seed_before_database_access():
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-O", "-m", "scripts.local_ent_validation", "--seed"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode != 0
    assert "Optimized Python disables validation assertions" in proc.stderr
