"""Pre-flight check: blocks on what would break or silently change trading, only warns on the rest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.ops import envcheck as ec


def _req(tmp_path, text):
    f = tmp_path / "requirements.txt"
    f.write_text(text, encoding="utf-8")
    return f


def test_satisfied_requirements_pass_and_comments_extras_and_markers_are_handled(tmp_path):
    f = _req(tmp_path, "# a comment\npandas>=1.0\nsqlalchemy[asyncio]>=1.0    # trailing comment\nnot-a-real-pkg-xyz>=1 ; sys_platform == 'nonexistent-os'\n")
    res = ec.Result()
    ec.check_requirements(res, f)
    assert res.ok, res.problems


def test_missing_and_too_old_packages_block(tmp_path):
    f = _req(tmp_path, "definitely-not-installed-pkg>=1.0\npandas>=999\n")
    res = ec.Result()
    ec.check_requirements(res, f)
    text = " ".join(res.problems)
    assert not res.ok and "definitely-not-installed-pkg is not installed" in text and "pandas" in text and ">=999" in text


def test_lock_drift_is_only_a_warning(tmp_path):
    lock = tmp_path / "requirements.lock.txt"
    lock.write_text("# header\npandas==0.0.1\nnot-installed-xyz==1.0\n", encoding="utf-8")
    res = ec.Result()
    ec.check_lock(res, lock)
    assert res.ok and any("pandas" in w and "not-installed-xyz" in w for w in res.warnings)


def test_missing_lock_file_warns(tmp_path):
    res = ec.Result()
    ec.check_lock(res, tmp_path / "nope.txt")
    assert res.ok and res.warnings


@pytest.fixture()
def model_world(tmp_path, monkeypatch):
    models = tmp_path / "models"
    models.mkdir()
    (models / "active_model.joblib").write_bytes(b"model-bytes")
    digest = hashlib.sha256(b"model-bytes").hexdigest()
    monkeypatch.setattr(ec.settings, "model_freeze_enabled", True)
    monkeypatch.setattr(ec.settings, "frozen_model_sha256", digest)
    monkeypatch.setattr(ec, "_predict_golden", lambda m: [0.1, 0.2, 0.3])
    import src.ml.evaluate as ev

    monkeypatch.setattr(ev, "load_active_model", lambda *a, **k: object())
    return SimpleNamespace(dir=models, digest=digest)


def _golden(w, expected, sk=None):
    import sklearn

    (w.dir / ec.GOLDEN_FILE).write_text(json.dumps({"model_sha256": w.digest, "sklearn_version": sk or sklearn.__version__, "expected": expected}), encoding="utf-8")


def test_model_that_reproduces_its_golden_predictions_passes(model_world):
    _golden(model_world, [0.1, 0.2, 0.3])
    res = ec.Result()
    ec.check_model(res, model_world.dir)
    assert res.ok and not res.warnings and any("reproduce" in i for i in res.info)


def test_changed_predictions_block_the_run(model_world):
    _golden(model_world, [0.1, 0.2, 0.31])
    res = ec.Result()
    ec.check_model(res, model_world.dir)
    assert not res.ok and "different predictions" in res.problems[0]


def test_sklearn_version_difference_warns_but_does_not_block_when_predictions_match(model_world):
    _golden(model_world, [0.1, 0.2, 0.3], sk="0.0.1")
    res = ec.Result()
    ec.check_model(res, model_world.dir)
    assert res.ok and any("differs" in w for w in res.warnings)


def test_missing_model_and_hash_mismatch_block(model_world, monkeypatch):
    res = ec.Result()
    ec.check_model(res, model_world.dir.parent / "empty")
    assert not res.ok
    monkeypatch.setattr(ec.settings, "frozen_model_sha256", "0" * 64)
    res = ec.Result()
    ec.check_model(res, model_world.dir)
    assert not res.ok and "hash differs" in res.problems[0]


def test_missing_golden_file_only_warns(model_world):
    res = ec.Result()
    ec.check_model(res, model_world.dir)
    assert res.ok and any(ec.GOLDEN_FILE in w for w in res.warnings)


def test_database_checks(tmp_path, monkeypatch):
    import sqlite3

    good = tmp_path / "ok.db"
    sqlite3.connect(good).execute("CREATE TABLE t (id INTEGER)").connection.commit()
    monkeypatch.setattr(ec.settings, "db_url", f"sqlite:///{good.as_posix()}")
    res = ec.Result()
    ec.check_database(res)
    assert res.ok and any("writable" in i for i in res.info)

    bad = tmp_path / "bad.db"
    bad.write_bytes(b"this is not a sqlite database at all" * 200)
    monkeypatch.setattr(ec.settings, "db_url", f"sqlite:///{bad.as_posix()}")
    res = ec.Result()
    ec.check_database(res)
    assert not res.ok

    monkeypatch.setattr(ec.settings, "db_url", f"sqlite:///{(tmp_path / 'missing.db').as_posix()}")
    res = ec.Result()
    ec.check_database(res)
    assert not res.ok and "missing" in res.problems[0]


def test_low_disk_and_memory_warn_but_never_block(monkeypatch, tmp_path):
    monkeypatch.setattr(ec.shutil, "disk_usage", lambda p: SimpleNamespace(free=int(0.5e9)))
    monkeypatch.setattr(ec, "windows_free_commit_gb", lambda: 0.4)
    res = ec.Result()
    ec.check_resources(res, tmp_path)
    assert res.ok and any("disk" in w.lower() for w in res.warnings) and any("MemoryError" in w for w in res.warnings)


def test_exit_code_follows_blocking_problems_only(monkeypatch, capsys):
    monkeypatch.setattr(ec, "run_checks", lambda: ec.Result(warnings=["just a warning"]))
    assert ec._main([]) == 0
    monkeypatch.setattr(ec, "run_checks", lambda: ec.Result(problems=["broken"]))
    assert ec._main([]) == 1
    assert "FAILED" in capsys.readouterr().out


def test_this_machine_passes_its_own_preflight():
    """Smoke test on the real environment: the check must not block the project's own setup."""
    res = ec.run_checks()
    assert res.ok, res.problems
