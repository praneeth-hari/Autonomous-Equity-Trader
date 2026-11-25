"""
src/ops/model_safe.py — A safe-format copy of the frozen model (skops), verified against the frozen predictions.

  python -m src.ops.model_safe export     # write models/backups/models/active_model_<hash>.skops (+ a .json sidecar)
  python -m src.ops.model_safe verify     # check the newest safe copy

Why: the live model is a joblib/pickle file, and loading a pickle can run arbitrary code. That is acceptable
for a file you made yourself, but it is the wrong format to keep for years, to share, or to restore from a
backup you have not looked at. A skops file cannot run code on load: it lists every non-standard type it
needs, and loading refuses anything not on the allow-list.

What this does NOT do: replace the live model. The freeze is tied to the .joblib file's hash
(V1_FREEZE_REPORT.md), so the pipeline keeps loading that file. To switch the live model to skops later
is a deliberate change that ends the freeze: export, verify here, then follow section 3 of the freeze report.

A safe copy only counts once it passes: no untrusted types, and predictions identical to the golden
predictions recorded at the freeze (data/models/active_model_golden.json).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from config.settings import settings

logger = logging.getLogger(__name__)

ALLOWED_UNTRUSTED: set = set()  # nothing outside scikit-learn's and numpy's standard types may be loaded
TOLERANCE = 1e-9


@dataclass
class Report:
    ok: bool
    problems: List[str] = field(default_factory=list)
    info: List[str] = field(default_factory=list)

    def text(self) -> str:
        return "\n".join([f"[ OK ] {i}" for i in self.info] + [f"[FAIL] {p}" for p in self.problems] + ["SAFE COPY " + ("VERIFIED" if self.ok else "REJECTED")])


def default_out_dir() -> Path:
    db = settings.db_url
    base = Path(db[len("sqlite:///"):]).parent if db.startswith("sqlite:///") else Path(settings.data_models_dir).parent
    return base / "backups" / "models"


def export_estimator(estimator: Any, features: List[str], out_path: Path, source_sha256: str = "") -> Path:
    """Write the estimator in skops format plus a small JSON sidecar. Overwrites nothing that exists."""
    import skops
    import skops.io as sio
    import sklearn

    out_path = Path(out_path)
    if out_path.exists():
        raise FileExistsError(f"Refusing to overwrite {out_path.name}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sio.dump(estimator, out_path)
    sidecar = {
        "source_sha256": source_sha256, "features": list(features), "sklearn_version": sklearn.__version__,
        "skops_version": skops.__version__, "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    out_path.with_suffix(".json").write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
    return out_path


def export(model_file: Optional[Path] = None, out_dir: Optional[Path] = None) -> Path:
    """Make the safe copy of the active model. The joblib file is only read, never changed."""
    from src.ml.evaluate import load_model

    model_file = Path(model_file or Path(settings.data_models_dir) / "active_model.joblib")
    digest = hashlib.sha256(model_file.read_bytes()).hexdigest()
    out = Path(out_dir or default_out_dir()) / f"active_model_{digest[:12]}.skops"
    if out.exists():
        return out  # already made for this exact model
    model = load_model(model_file)  # trusted: it is your own frozen file; this is the loader the pipeline uses
    return export_estimator(model.estimator, list(model.features), out, digest)


def verify(skops_file: Path, golden_file: Optional[Path] = None) -> Report:
    """Check a safe copy: it needs no untrusted types and must reproduce the golden predictions exactly."""
    import numpy as np
    import pandas as pd
    import skops.io as sio

    rep = Report(ok=False)
    skops_file = Path(skops_file)
    side = skops_file.with_suffix(".json")
    if not skops_file.exists() or not side.exists():
        rep.problems.append("The safe copy or its .json sidecar is missing.")
        return rep
    meta = json.loads(side.read_text(encoding="utf-8"))

    untrusted = set(sio.get_untrusted_types(file=skops_file))
    extra = sorted(untrusted - ALLOWED_UNTRUSTED)
    if extra:
        rep.problems.append("The file needs types that are not on the allow-list, so it was NOT loaded: " + ", ".join(extra))
        return rep
    rep.info.append("Needs no types beyond scikit-learn and numpy: loading it cannot run arbitrary code")

    golden_file = Path(golden_file or Path(settings.data_models_dir) / "active_model_golden.json")
    if not golden_file.exists():
        rep.problems.append(f"{golden_file.name} not found: run  python -m src.ops.envcheck --write-golden  first.")
        return rep
    golden = json.loads(golden_file.read_text(encoding="utf-8"))
    if meta.get("source_sha256") and golden.get("model_sha256") and meta["source_sha256"] != golden["model_sha256"]:
        rep.problems.append("This safe copy was made from a different model than the one the golden predictions describe.")
        return rep

    est = sio.load(skops_file, trusted=[])
    rng = np.random.default_rng(42)
    X = pd.DataFrame(rng.normal(size=(6, len(meta["features"]))), columns=meta["features"])
    got = [round(float(p), 12) for p in est.predict_proba(X)[:, 1]]
    worst = max(abs(a - b) for a, b in zip(got, golden["expected"]))
    if len(got) != len(golden["expected"]) or worst > TOLERANCE:
        rep.problems.append(f"Predictions differ from the frozen model (largest difference {worst:.3g}).")
        return rep
    rep.info.append(f"Predictions reproduce the frozen model exactly (largest difference {worst:.1e})")
    rep.ok = True
    return rep


def newest(out_dir: Optional[Path] = None) -> Optional[Path]:
    files = sorted(Path(out_dir or default_out_dir()).glob("active_model_*.skops"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def _main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Make and check a safe-format copy of the frozen model.")
    p.add_argument("action", choices=["export", "verify"])
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if a.action == "export":
        path = export()
        print(f"Safe copy: {path}")
        rep = verify(path)
    else:
        path = newest()
        if path is None:
            print("No safe copy yet. Run:  python -m src.ops.model_safe export")
            return 1
        rep = verify(path)
    print(rep.text())
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(_main())
