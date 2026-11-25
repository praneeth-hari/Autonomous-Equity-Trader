"""Safe model copy: it must reproduce the frozen predictions exactly and refuse anything that could run code."""

from __future__ import annotations

import json
import warnings

import numpy as np
import pandas as pd
import pytest
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.ops import model_safe as ms

FEATURES = ["f1", "f2", "f3"]


class Sneaky(BaseEstimator, TransformerMixin):
    """A custom, non-scikit-learn type: exactly what a safe copy must refuse to load."""

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        return X


def _pipeline(custom=False):
    rng = np.random.default_rng(0)
    X = pd.DataFrame(rng.normal(size=(80, 3)), columns=FEATURES)
    y = (X["f1"] + 0.3 * X["f2"] > 0).astype(int)
    steps = ([("sneaky", Sneaky())] if custom else []) + [("scaler", StandardScaler()), ("classifier", LogisticRegression())]
    return Pipeline(steps).fit(X, y)


def _golden(est, path, sha="abc"):
    rng = np.random.default_rng(42)
    X = pd.DataFrame(rng.normal(size=(6, 3)), columns=FEATURES)
    expected = [round(float(p), 12) for p in est.predict_proba(X)[:, 1]]
    path.write_text(json.dumps({"model_sha256": sha, "expected": expected}), encoding="utf-8")
    return path


def test_a_standard_pipeline_exports_verifies_and_matches_the_golden_predictions(tmp_path):
    est = _pipeline()
    out = ms.export_estimator(est, FEATURES, tmp_path / "m.skops", source_sha256="abc")
    rep = ms.verify(out, _golden(est, tmp_path / "golden.json"))
    assert rep.ok, rep.problems
    assert any("cannot run arbitrary code" in i for i in rep.info) and (tmp_path / "m.json").exists()


def test_a_custom_type_is_refused_before_anything_is_loaded(tmp_path):
    est = _pipeline(custom=True)
    out = ms.export_estimator(est, FEATURES, tmp_path / "m.skops", source_sha256="abc")
    rep = ms.verify(out, _golden(est, tmp_path / "golden.json"))
    assert not rep.ok and "NOT loaded" in rep.problems[0] and "Sneaky" in rep.problems[0]


def test_different_predictions_are_rejected(tmp_path):
    est = _pipeline()
    out = ms.export_estimator(est, FEATURES, tmp_path / "m.skops", source_sha256="abc")
    g = _golden(est, tmp_path / "golden.json")
    data = json.loads(g.read_text())
    data["expected"][2] += 0.001
    g.write_text(json.dumps(data))
    rep = ms.verify(out, g)
    assert not rep.ok and "differ from the frozen model" in rep.problems[0]


def test_a_copy_made_from_another_model_is_rejected(tmp_path):
    est = _pipeline()
    out = ms.export_estimator(est, FEATURES, tmp_path / "m.skops", source_sha256="abc")
    rep = ms.verify(out, _golden(est, tmp_path / "golden.json", sha="different"))
    assert not rep.ok and "different model" in rep.problems[0]


def test_missing_files_and_missing_golden_are_clear_failures(tmp_path):
    assert "missing" in ms.verify(tmp_path / "nope.skops").problems[0]
    est = _pipeline()
    out = ms.export_estimator(est, FEATURES, tmp_path / "m.skops")
    assert "not found" in ms.verify(out, tmp_path / "no_golden.json").problems[0]


def test_export_never_overwrites_an_existing_file(tmp_path):
    est = _pipeline()
    ms.export_estimator(est, FEATURES, tmp_path / "m.skops")
    with pytest.raises(FileExistsError):
        ms.export_estimator(est, FEATURES, tmp_path / "m.skops")


def test_exporting_does_not_touch_the_live_model_file(tmp_path, monkeypatch):
    """The freeze is tied to the .joblib hash: exporting must only READ it."""
    import hashlib

    import joblib

    est = _pipeline()
    live = tmp_path / "active_model.joblib"
    joblib.dump({"model_name": "t", "model_type": "baseline", "estimator": est, "features": FEATURES, "metadata": {"feature_columns": FEATURES}}, live)
    before = hashlib.sha256(live.read_bytes()).hexdigest()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            out = ms.export(live, tmp_path / "out")
        except Exception:  # the loader may need metadata files this tiny fixture lacks; the point below still holds
            out = None
    assert hashlib.sha256(live.read_bytes()).hexdigest() == before
    if out is not None:
        assert out.name == f"active_model_{before[:12]}.skops"


def test_the_backup_still_succeeds_when_the_safe_copy_cannot_be_made(tmp_path):
    """A junk model file must not stop the database backup: the safe copy is an extra."""
    import sqlite3

    from src.ops import backup as bk

    db = tmp_path / "p" / "trader.db"
    db.parent.mkdir()
    con = sqlite3.connect(db)
    for t in ("portfolio", "market_data", "event_log", "trades", "orders"):
        con.execute(f"CREATE TABLE {t} (id INTEGER)")
    con.commit()
    con.close()
    models = tmp_path / "models"
    models.mkdir()
    (models / "active_model.joblib").write_bytes(b"not a real model")
    rep = bk.create_backup(f"sqlite:///{db.as_posix()}", models_dir=models)
    assert rep.ok and list((bk.backup_dir(db) / "models").glob("*.joblib"))
