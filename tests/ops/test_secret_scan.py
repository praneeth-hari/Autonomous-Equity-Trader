"""The secret scanner finds the kinds of secrets that matter, never prints them, and allows marked fakes."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.ops import secret_scan as ss

# Built from pieces so this file itself holds no complete secret-looking string.
TELEGRAM = "bot" + "8123456789" + ":" + "AAH" + "x" * 32
GOOGLE = "AI" + "za" + "A" * 35
PGURL = "postgresql://" + "postgres.abc" + ":" + "hunter2hunter2" + "@aws-0.pooler.supabase.com:5432/db"


@pytest.mark.parametrize("line, kind", [
    (f"url = 'https://api.telegram.org/{TELEGRAM}/getMe'", "Telegram"),
    (f"key = '{GOOGLE}'", "Google"),
    ("-----BEGIN " + "RSA PRIVATE KEY-----", "Private key"),
    (f"DATABASE_URL={PGURL}", "Database URL"),
    ("token=" + "ghp_" + "a" * 36, "GitHub"),
    ("AWS=" + "AKIA" + "A" * 16, "AWS"),
])
def test_real_looking_secrets_are_found(line, kind):
    hits = ss.scan_text("harmless\n" + line + "\nalso harmless")
    assert len(hits) == 1 and hits[0][0] == 2 and kind in hits[0][1]


@pytest.mark.parametrize("line", [
    "DATABASE_URL=postgresql://user:password@localhost/db",
    "DATABASE_URL=postgresql://user:***@host:5432/db",
    "DATABASE_URL=postgresql://<user>:<password>@host/db",
    "ratio = 12345:67890",
    "time 10:30:45 and 2026:11:25",
    "psycopg[binary]>=3.1.18",
])
def test_normal_text_and_placeholders_are_not_flagged(line):
    assert ss.scan_text(line) == []


def test_a_marked_fake_is_skipped():
    assert ss.scan_text(f"fake = '{GOOGLE}'  # {ss.ALLOW_MARKER}") == []


def test_findings_name_the_file_and_line_but_never_the_secret(tmp_path):
    f = tmp_path / "config.py"
    f.write_text(f"x = 1\nKEY = '{GOOGLE}'\n", encoding="utf-8")
    out = ss.scan_files([f], root=tmp_path)
    assert out == ["config.py:2: possible Google API key"]
    assert GOOGLE not in " ".join(out)


def _git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def test_scans_new_files_skips_ignored_and_catches_a_tracked_env_file(tmp_path):
    _git(tmp_path, "init", "-q")
    (tmp_path / ".gitignore").write_text("secret_ignored.txt\n", encoding="utf-8")
    (tmp_path / "secret_ignored.txt").write_text(GOOGLE, encoding="utf-8")
    (tmp_path / "new_file.py").write_text(f"k='{GOOGLE}'\n", encoding="utf-8")
    (tmp_path / ".env").write_text("A=1\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text("A=\n", encoding="utf-8")
    names = {p.name for p in ss.candidate_files(root=tmp_path)}
    assert "new_file.py" in names and "secret_ignored.txt" not in names
    _git(tmp_path, "add", "-f", ".env", ".env.example")
    assert ss.tracked_env_files(tmp_path) == [".env"]


def test_the_project_itself_is_clean():
    """Guards the repository on every test run, not just in CI."""
    assert ss.scan_files(ss.candidate_files()) == []
    assert ss.tracked_env_files() == []


def test_ci_workflow_and_local_gate_run_the_secret_scan_and_the_tests():
    root = Path(__file__).resolve().parents[2]
    ci = (root / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    gate = (root / "check_all.ps1").read_text(encoding="utf-8")
    for needle in ("src.ops.secret_scan", "pytest", "npm run build", "npm test"):
        assert needle in ci and needle in gate
