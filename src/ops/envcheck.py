"""
src/ops/envcheck.py — Pre-flight check: is this machine fit to run the nightly cycle?

  python -m src.ops.envcheck                 # human-readable report; exit 1 if anything blocks the run
  python -m src.ops.envcheck --json          # the same, for tools
  python -m src.ops.envcheck --write-golden  # record the model's expected outputs (do this once, after a freeze)

Blocking problems (exit 1) are things that would make the run fail or, worse, silently change its
decisions: a missing or too-old package, a model whose predictions differ from the frozen ones,
a damaged database. Warnings (exit 0) are worth knowing about but must not stop trading:
low memory or disk, a library version that differs from the lock file.

Imports are kept light on purpose (no shap, lightgbm or optuna): this runs every night before the
pipeline and must not itself use the scarce memory the pipeline needs.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
import shutil
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Dict, List, Optional

from config.settings import settings

ROOT = Path(__file__).resolve().parents[2]
CORE_IMPORTS = ["numpy", "pandas", "sklearn", "sqlalchemy", "joblib", "pydantic_settings", "pytz"]
GOLDEN_FILE = "active_model_golden.json"
GOLDEN_TOLERANCE = 1e-9
MIN_FREE_DISK_GB = 2.0
MIN_FREE_COMMIT_GB = 1.5


@dataclass
class Result:
    problems: List[str] = field(default_factory=list)   # block the run
    warnings: List[str] = field(default_factory=list)   # worth knowing, do not block
    info: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def text(self) -> str:
        lines = [f"[ OK ] {i}" for i in self.info]
        lines += [f"[WARN] {w}" for w in self.warnings]
        lines += [f"[FAIL] {p}" for p in self.problems]
        lines.append("ENVIRONMENT CHECK " + ("PASSED" if self.ok else "FAILED") +
                     (f" ({len(self.warnings)} warning(s))" if self.warnings else ""))
        return "\n".join(lines)


def _clean_lines(path: Path) -> List[str]:
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def check_python(res: Result) -> None:
    v = sys.version_info
    if v < (3, 10):
        res.problems.append(f"Python {v.major}.{v.minor} is too old; the project needs 3.11.")
    elif (v.major, v.minor) != (3, 11):
        res.warnings.append(f"Python {v.major}.{v.minor} is not the 3.11 the project was built on.")
    else:
        res.info.append(f"Python {v.major}.{v.minor}.{v.micro}")


def check_requirements(res: Result, req_file: Path) -> None:
    from packaging.requirements import Requirement

    bad = 0
    lines = _clean_lines(req_file)
    for line in lines:
        req = Requirement(line)
        if req.marker is not None and not req.marker.evaluate():
            continue
        try:
            installed = metadata.version(req.name)
        except metadata.PackageNotFoundError:
            res.problems.append(f"{req.name} is not installed (need {req.specifier or 'any version'}).")
            bad += 1
            continue
        if req.specifier and not req.specifier.contains(installed, prereleases=True):
            res.problems.append(f"{req.name} {installed} does not satisfy {req.specifier}.")
            bad += 1
    if not bad:
        res.info.append(f"All {len(lines)} required packages are installed at acceptable versions")


def check_imports(res: Result) -> None:
    failed = []
    for name in CORE_IMPORTS:
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001 - any import failure means the run would fail too
            failed.append(f"{name} ({type(exc).__name__}: {exc})")
    if failed:
        res.problems.append("Core packages cannot be imported: " + "; ".join(failed))
    else:
        res.info.append("Core packages import cleanly")
    for name in ("xgboost", "lightgbm", "shap", "yfinance", "vaderSentiment", "telegram", "apscheduler"):
        if importlib.util.find_spec(name) is None:
            res.problems.append(f"{name} is not installed.")


def check_lock(res: Result, lock_file: Path) -> None:
    if not lock_file.exists():
        res.warnings.append(f"{lock_file.name} not found, so versions cannot be compared with the tested set.")
        return
    drift = []
    for line in _clean_lines(lock_file):
        if "==" not in line:
            continue
        name, _, want = line.partition("==")
        try:
            have = metadata.version(name.strip())
        except metadata.PackageNotFoundError:
            drift.append(f"{name} missing")
            continue
        if have != want.strip():
            drift.append(f"{name} {have} (locked {want.strip()})")
    if drift:
        res.warnings.append(f"{len(drift)} package(s) differ from {lock_file.name}: " + "; ".join(drift[:6]) + (" ..." if len(drift) > 6 else ""))
    else:
        res.info.append(f"Package versions match {lock_file.name}")


def golden_inputs(features: List[str]):
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(42)
    return pd.DataFrame(rng.normal(size=(6, len(features))), columns=features)


def _predict_golden(model) -> List[float]:
    return [round(float(p), 12) for p in model.estimator.predict_proba(golden_inputs(list(model.features)))[:, 1]]


def check_model(res: Result, models_dir: Path) -> None:
    model_file = models_dir / "active_model.joblib"
    if not model_file.exists():
        res.problems.append(f"The active model file is missing: {model_file}")
        return
    digest = hashlib.sha256(model_file.read_bytes()).hexdigest()
    if settings.model_freeze_enabled and digest != settings.frozen_model_sha256:
        res.problems.append("The active model's hash differs from the frozen one: the pipeline will refuse to trade.")
        return
    res.info.append("Active model present" + (" and matches the freeze hash" if settings.model_freeze_enabled else ""))

    golden_path = models_dir / GOLDEN_FILE
    if not golden_path.exists():
        res.warnings.append(f"{GOLDEN_FILE} not found: run  python -m src.ops.envcheck --write-golden  once.")
        return
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    if golden.get("model_sha256") != digest:
        res.warnings.append("The golden file belongs to a different model; regenerate it with --write-golden.")
        return
    try:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # the version difference is reported below, in words
            from src.ml.evaluate import load_active_model

            model = load_active_model()
        got = _predict_golden(model)
    except Exception as exc:  # noqa: BLE001
        res.problems.append(f"The active model could not be loaded or used: {type(exc).__name__}: {exc}")
        return
    worst = max(abs(a - b) for a, b in zip(got, golden["expected"]))
    if len(got) != len(golden["expected"]) or worst > GOLDEN_TOLERANCE:
        res.problems.append(
            f"The model gives different predictions in this environment (largest difference {worst:.3g}). "
            "Trading decisions would change; fix the library versions before running.")
        return
    res.info.append(f"Model predictions reproduce the frozen ones (largest difference {worst:.1e})")
    import sklearn

    if sklearn.__version__ != golden.get("sklearn_version"):
        res.warnings.append(f"scikit-learn {sklearn.__version__} differs from {golden.get('sklearn_version')} used at the freeze.")


def write_golden(models_dir: Path) -> Path:
    model_file = models_dir / "active_model.joblib"
    digest = hashlib.sha256(model_file.read_bytes()).hexdigest()
    import sklearn
    from src.ml.evaluate import load_active_model

    model = load_active_model()
    data = {
        "model_sha256": digest,
        "sklearn_version": sklearn.__version__,
        "note": "Predictions of the frozen model on 6 fixed random inputs (seed 42). The pre-flight check compares against these.",
        "expected": _predict_golden(model),
    }
    path = models_dir / GOLDEN_FILE
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def check_database(res: Result) -> None:
    url = settings.db_url
    if not url.startswith("sqlite:///"):
        res.info.append("Database is not SQLite; file checks skipped")
        return
    db = Path(url[len("sqlite:///"):])
    if not db.exists():
        res.problems.append(f"The database file is missing: {db}")
        return
    try:
        con = sqlite3.connect(db, timeout=5)
        try:
            if con.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                res.problems.append("The database failed its integrity check. Restore the newest backup.")
                return
            con.execute("BEGIN IMMEDIATE")  # proves it can be written, then undoes it
            con.rollback()
        finally:
            con.close()
        res.info.append("Database opens, passes its integrity check and is writable")
    except sqlite3.OperationalError as exc:
        res.warnings.append(f"The database is busy or locked right now: {exc}")
    except sqlite3.DatabaseError as exc:
        res.problems.append(f"The database is damaged: {exc}. Restore the newest backup.")


def windows_free_commit_gb() -> Optional[float]:
    """Free virtual memory (RAM plus page file) on Windows; None elsewhere."""
    if sys.platform != "win32":
        return None
    import ctypes

    class MemStatus(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

    st = MemStatus()
    st.dwLength = ctypes.sizeof(MemStatus)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
    return st.ullAvailPageFile / 1e9


def check_resources(res: Result, path: Path = ROOT) -> None:
    free = shutil.disk_usage(path).free / 1e9
    (res.warnings if free < MIN_FREE_DISK_GB else res.info).append(f"Free disk space: {free:.1f} GB")
    commit = windows_free_commit_gb()
    if commit is not None:
        (res.warnings if commit < MIN_FREE_COMMIT_GB else res.info).append(
            f"Free virtual memory: {commit:.1f} GB" + (" (low: the run may fail with a MemoryError; close programs or enlarge the page file)" if commit < MIN_FREE_COMMIT_GB else ""))
    if not (ROOT / ".env").exists():
        res.warnings.append("No .env file: settings fall back to their defaults (no Telegram alerts).")


def run_checks(root: Path = ROOT) -> Result:
    res = Result()
    check_python(res)
    check_requirements(res, root / "requirements.txt")
    check_imports(res)
    check_lock(res, root / "requirements.lock.txt")
    if res.ok:  # the model and database checks need working packages
        check_model(res, Path(settings.data_models_dir))
        check_database(res)
    check_resources(res, root)
    return res


def _main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Check that this machine can run the nightly cycle.")
    p.add_argument("--json", action="store_true")
    p.add_argument("--write-golden", action="store_true")
    a = p.parse_args(argv)
    if a.write_golden:
        print("Wrote " + str(write_golden(Path(settings.data_models_dir))))
        return 0
    res = run_checks()
    print(json.dumps({**asdict(res), "ok": res.ok}, indent=2) if a.json else res.text())
    return 0 if res.ok else 1


if __name__ == "__main__":
    sys.exit(_main())
