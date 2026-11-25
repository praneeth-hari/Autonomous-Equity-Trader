"""Lint and dependency hygiene are part of the gate, so they are tested like everything else."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _run(*args):
    return subprocess.run([sys.executable, "-m", *args], cwd=ROOT, capture_output=True, text=True)


def test_the_project_has_no_real_bugs_according_to_ruff():
    if _run("ruff", "--version").returncode != 0:
        pytest.skip("ruff is not installed (pip install -r requirements-dev.txt)")
    res = _run("ruff", "check", "--output-format", "concise")
    assert res.returncode == 0, res.stdout[-1500:]


def test_ruff_blocks_only_on_the_real_bug_rules():
    cfg = (ROOT / "ruff.toml").read_text(encoding="utf-8")
    for rule in ('"E9"', '"F63"', '"F7"', '"F82"'):
        assert rule in cfg
    assert '"F401"' not in cfg  # unused imports are deliberately not enforced on the frozen code


def test_gate_and_ci_run_lint_audit_and_gitleaks():
    gate = (ROOT / "check_all.ps1").read_text(encoding="utf-8")
    ci = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    for needle in ("ruff check", "pip_audit"):
        assert needle in gate and needle in ci
    assert "gitleaks" in gate and "gitleaks/gitleaks-action" in ci


def test_gitleaks_config_extends_the_default_rules_and_only_allows_known_fake_files():
    cfg = (ROOT / ".gitleaks.toml").read_text(encoding="utf-8")
    assert "useDefault = true" in cfg
    allowed = [ln.strip() for ln in cfg.splitlines() if ln.strip().startswith("'''")]
    assert allowed and all(("tests/" in a or "docs/" in a) for a in allowed)  # never application code
    for a in allowed:
        assert (ROOT / a.strip("',").replace("\.", ".")).exists(), f"allow-listed file no longer exists: {a}"


def test_dev_tools_are_kept_out_of_the_runtime_requirements():
    run = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    dev = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    assert "ruff" not in run and "pip-audit" not in run and "ruff" in dev and "pip-audit" in dev


@pytest.mark.skipif(shutil.which("gitleaks") is None, reason="gitleaks is not installed locally (it runs in CI)")
def test_gitleaks_finds_nothing_when_installed():
    res = subprocess.run(["gitleaks", "detect", "--no-banner", "--config", ".gitleaks.toml"], cwd=ROOT, capture_output=True, text=True)
    assert res.returncode == 0, res.stdout[-1500:] + res.stderr[-500:]


def test_gate_and_ci_run_the_browser_tests_and_they_cannot_reach_real_servers():
    gate = (ROOT / "check_all.ps1").read_text(encoding="utf-8")
    ci = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    assert "npm run e2e" in gate and "npm run e2e" in ci and "playwright install" in ci
    fx = (ROOT / "web" / "e2e" / "fixtures.ts").read_text(encoding="utf-8")
    assert "auto: true" in fx, "the mock API must be installed for every test, or a test could hit a real server"
    assert "route.abort()" in fx, "requests to anything that is not local must be blocked"
