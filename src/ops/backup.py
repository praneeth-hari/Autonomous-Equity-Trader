"""
src/ops/backup.py — Consistent backups of the trading database and the frozen model.

  python -m src.ops.backup create        # back up now (and verify it)
  python -m src.ops.backup verify        # check the newest backup
  python -m src.ops.backup restore-test  # restore the newest backup into a temp folder and read it back
  python -m src.ops.backup list

Design (see the project rules):
  * The SQLite online backup API gives a consistent copy even while another process is writing.
  * A backup only counts once it has passed `PRAGMA integrity_check` and holds every table the live
    database has. A backup nobody has tested is a hope, not a backup.
  * The live database and model are never modified. Old backups are pruned by count; files that do
    not follow this module's naming (your own manual copies) are never touched.
  * Failures raise or return a failed report and trigger an alert from the nightly batch file.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import re
import shutil
import sqlite3
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from config.settings import settings

logger = logging.getLogger(__name__)

BACKUP_RE = re.compile(r"^trader_(\d{8})_(\d{6})\.db$")
DEFAULT_KEEP = 14


class BackupError(RuntimeError):
    """A backup could not be made or did not pass verification."""


@dataclass
class Report:
    ok: bool
    path: Optional[Path] = None
    problems: List[str] = field(default_factory=list)
    tables: Dict[str, int] = field(default_factory=dict)
    latest_snapshot: Optional[str] = None

    def summary(self) -> str:
        head = "OK" if self.ok else "FAILED"
        rows = sum(self.tables.values())
        tail = f" | {len(self.tables)} tables, {rows} rows | latest snapshot {self.latest_snapshot}" if self.ok else ""
        return f"{head}: {self.path.name if self.path else '-'}{tail}" + ("".join(f"\n  - {p}" for p in self.problems))


def sqlite_path(db_url: Optional[str] = None) -> Path:
    url = db_url or settings.db_url
    if not url.startswith("sqlite:///"):
        raise BackupError("Backups cover the local SQLite database only. Your DATABASE_URL is not SQLite.")
    return Path(url[len("sqlite:///"):])


def backup_dir(db_file: Path) -> Path:
    return db_file.parent / "backups"


def _table_counts(con: sqlite3.Connection) -> Dict[str, int]:
    names = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    return {n: int(con.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0]) for n in sorted(names)}


def _latest_snapshot(con: sqlite3.Connection) -> Optional[str]:
    try:
        row = con.execute("SELECT MAX(run_date) FROM portfolio").fetchone()
        return row[0] if row else None
    except sqlite3.Error:
        return None


def list_backups(db_file: Path) -> List[Path]:
    d = backup_dir(db_file)
    if not d.exists():
        return []
    return sorted((p for p in d.iterdir() if BACKUP_RE.match(p.name)), key=lambda p: p.name)


def verify_backup(backup: Path, live: Optional[Path] = None) -> Report:
    """Integrity-check a backup; if the live DB is given, it must contain every live table."""
    rep = Report(ok=False, path=backup)
    if not backup.exists():
        rep.problems.append("Backup file does not exist.")
        return rep
    try:
        con = sqlite3.connect(f"file:{backup.as_posix()}?mode=ro", uri=True)
        try:
            check = con.execute("PRAGMA integrity_check").fetchone()[0]
            if check != "ok":
                rep.problems.append(f"Integrity check failed: {check}")
            rep.tables = _table_counts(con)
            rep.latest_snapshot = _latest_snapshot(con)
        finally:
            con.close()
        if live is not None and live.exists():
            lc = sqlite3.connect(f"file:{live.as_posix()}?mode=ro", uri=True)
            try:
                missing = sorted(set(_table_counts(lc)) - set(rep.tables))
            finally:
                lc.close()
            if missing:
                rep.problems.append("Backup is missing tables: " + ", ".join(missing))
    except sqlite3.Error as exc:
        rep.problems.append(f"Could not read the backup: {exc}")
    rep.ok = not rep.problems
    return rep


def backup_model(db_file: Path, models_dir: Optional[Path] = None) -> Optional[Path]:
    """Keep a copy of the active model named by its hash, once per distinct model."""
    models = Path(models_dir or settings.data_models_dir)
    src = models / "active_model.joblib"
    if not src.exists():
        return None
    digest = hashlib.sha256(src.read_bytes()).hexdigest()
    dest_dir = backup_dir(db_file) / "models"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"active_model_{digest[:12]}.joblib"
    if not dest.exists():
        shutil.copy2(src, dest)
        meta = models / "active_model_metadata.json"
        if meta.exists():
            shutil.copy2(meta, dest_dir / f"active_model_{digest[:12]}_metadata.json")
    # Also keep a safe-format (skops) copy beside it. Best effort: the joblib backup above is what counts, and a
    # problem here must never fail the backup. Verify it any time with:  python -m src.ops.model_safe verify
    try:
        from src.ops import model_safe

        model_safe.export(src, dest_dir)
    except Exception as exc:  # noqa: BLE001
        logger.warning("SAFE_MODEL_COPY_SKIPPED: %s", type(exc).__name__)
    return dest


def prune(db_file: Path, keep: int = DEFAULT_KEEP) -> List[Path]:
    old = list_backups(db_file)[:-keep] if keep > 0 else []
    for p in old:
        try:
            p.unlink()
        except OSError as exc:
            logger.warning("BACKUP_PRUNE_FAILED %s: %s", p.name, exc)
    return old


def create_backup(db_url: Optional[str] = None, keep: int = DEFAULT_KEEP, now: Optional[datetime] = None,
                  models_dir: Optional[Path] = None) -> Report:
    """Make, verify and register a backup. Raises BackupError if it cannot be trusted."""
    live = sqlite_path(db_url)
    if not live.exists():
        raise BackupError(f"Database not found: {live}")
    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    dest_dir = backup_dir(live)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"trader_{stamp}.db"
    if dest.exists():
        raise BackupError(f"Refusing to overwrite an existing backup: {dest.name}")

    src = sqlite3.connect(f"file:{live.as_posix()}?mode=ro", uri=True)
    out = sqlite3.connect(dest)
    try:
        src.backup(out)  # consistent even if another process is writing
    except sqlite3.Error as exc:
        out.close()
        src.close()
        dest.unlink(missing_ok=True)
        raise BackupError(f"Backup copy failed: {exc}") from exc
    out.close()
    src.close()

    rep = verify_backup(dest, live)
    if not rep.ok:
        bad = dest.with_suffix(".db.FAILED")
        dest.replace(bad)  # keep the evidence, but it no longer matches the naming that counts as a backup
        rep.path = bad
        raise BackupError("New backup failed verification: " + "; ".join(rep.problems))

    backup_model(live, models_dir)
    pruned = prune(live, keep)
    logger.info("BACKUP_OK %s (%d tables) pruned=%d", dest.name, len(rep.tables), len(pruned))
    return rep


def restore_test(backup: Optional[Path] = None, db_url: Optional[str] = None) -> Report:
    """Restore a backup into a temporary folder and read the data back, as a real restore would."""
    live = sqlite_path(db_url)
    backup = backup or (list_backups(live) or [None])[-1]
    if backup is None:
        return Report(ok=False, problems=["There is no backup to test."])
    with tempfile.TemporaryDirectory(prefix="restore_test_") as tmp:
        restored = Path(tmp) / "trader_restored.db"
        shutil.copy2(backup, restored)
        rep = verify_backup(restored)
        rep.path = backup
        if rep.ok:
            for table in ("portfolio", "market_data", "event_log", "trades", "orders"):
                if table not in rep.tables:
                    rep.problems.append(f"Restored database has no '{table}' table.")
        rep.ok = not rep.problems
        return rep


def _main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Back up and check the trading database.")
    p.add_argument("action", choices=["create", "verify", "restore-test", "list"])
    p.add_argument("--keep", type=int, default=DEFAULT_KEEP)
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        live = sqlite_path()
        if a.action == "create":
            print("Backup " + create_backup(keep=a.keep).summary())
            return 0
        if a.action == "list":
            for b in list_backups(live):
                print(f"{b.name}  {b.stat().st_size / 1e6:.1f} MB")
            return 0
        rep = restore_test() if a.action == "restore-test" else verify_backup((list_backups(live) or [None])[-1] or live / "missing", live)
        print(("Restore test " if a.action == "restore-test" else "Verify ") + rep.summary())
        return 0 if rep.ok else 1
    except BackupError as exc:
        print(f"BACKUP FAILED: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(_main())
