"""Backups: consistent, verified, pruned safely, and restorable. Uses small throwaway databases."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.ops import backup as bk


def _make_db(path: Path, snapshots=("2026-09-28", "2026-09-29"), extra_tables=()):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE portfolio (id INTEGER PRIMARY KEY, run_date TEXT, total_value REAL)")
    con.execute("CREATE TABLE market_data (id INTEGER PRIMARY KEY, ticker TEXT)")
    con.execute("CREATE TABLE event_log (id INTEGER PRIMARY KEY, message TEXT)")
    con.execute("CREATE TABLE trades (id INTEGER PRIMARY KEY)")
    con.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY)")
    for t in extra_tables:
        con.execute(f'CREATE TABLE "{t}" (id INTEGER PRIMARY KEY)')
    con.executemany("INSERT INTO portfolio(run_date,total_value) VALUES (?,?)", [(d, 10000.0) for d in snapshots])
    con.executemany("INSERT INTO market_data(ticker) VALUES (?)", [("AAPL",), ("MSFT",), ("SPY",)])
    con.execute("INSERT INTO event_log(message) VALUES ('hello')")
    con.commit()
    con.close()


@pytest.fixture()
def world(tmp_path):
    db = tmp_path / "processed" / "trader.db"
    db.parent.mkdir()
    _make_db(db)
    models = tmp_path / "models"
    models.mkdir()
    (models / "active_model.joblib").write_bytes(b"frozen-model-bytes")
    (models / "active_model_metadata.json").write_text("{}", encoding="utf-8")
    return {"db": db, "url": f"sqlite:///{db.as_posix()}", "models": models}


def test_create_makes_a_verified_copy_with_the_same_rows(world):
    rep = bk.create_backup(world["url"], models_dir=world["models"], now=datetime(2026, 11, 25, 3, 30, 0))
    assert rep.ok and rep.path.name == "trader_20261125_033000.db"
    assert rep.tables == {"event_log": 1, "market_data": 3, "orders": 0, "portfolio": 2, "trades": 0}
    assert rep.latest_snapshot == "2026-09-29"


def test_backup_is_independent_of_later_changes_to_the_live_database(world):
    rep = bk.create_backup(world["url"], models_dir=world["models"])
    con = sqlite3.connect(world["db"])
    con.execute("DELETE FROM portfolio")
    con.commit()
    con.close()
    assert bk.verify_backup(rep.path).tables["portfolio"] == 2


def test_backup_still_works_while_another_connection_holds_a_write_transaction(world):
    writer = sqlite3.connect(world["db"])
    writer.execute("BEGIN")
    writer.execute("INSERT INTO event_log(message) VALUES ('uncommitted')")
    try:
        rep = bk.create_backup(world["url"], models_dir=world["models"])
    finally:
        writer.rollback()
        writer.close()
    assert rep.ok and rep.tables["event_log"] == 1  # the uncommitted row is not in the copy


def test_verify_rejects_a_corrupted_backup(world):
    rep = bk.create_backup(world["url"], models_dir=world["models"])
    data = bytearray(rep.path.read_bytes())
    data[len(data) // 2: len(data) // 2 + 4096] = b"\x00" * 4096
    rep.path.write_bytes(bytes(data))
    assert bk.verify_backup(rep.path).ok is False


def test_verify_requires_every_live_table(world):
    rep = bk.create_backup(world["url"], models_dir=world["models"])
    con = sqlite3.connect(world["db"])
    con.execute("CREATE TABLE new_table (id INTEGER)")
    con.commit()
    con.close()
    check = bk.verify_backup(rep.path, world["db"])
    assert check.ok is False and "new_table" in " ".join(check.problems)


def test_a_failed_verification_raises_and_never_counts_as_a_backup(world, monkeypatch):
    real = bk.verify_backup
    monkeypatch.setattr(bk, "verify_backup", lambda p, live=None: bk.Report(ok=False, path=p, problems=["forced"]))
    with pytest.raises(bk.BackupError):
        bk.create_backup(world["url"], models_dir=world["models"])
    monkeypatch.setattr(bk, "verify_backup", real)
    assert bk.list_backups(world["db"]) == []  # the bad file is renamed out of the counted set


def test_pruning_keeps_only_the_newest_and_never_touches_manual_copies(world):
    d = bk.backup_dir(world["db"])
    d.mkdir(exist_ok=True)
    manual = d / "trader_pre_backfill_20260926_002425.db"
    manual.write_bytes(b"mine")
    start = datetime(2026, 11, 1, 3, 30)
    for i in range(5):
        bk.create_backup(world["url"], keep=3, now=start + timedelta(days=i), models_dir=world["models"])
    names = [p.name for p in bk.list_backups(world["db"])]
    assert names == ["trader_20261103_033000.db", "trader_20261104_033000.db", "trader_20261105_033000.db"]
    assert manual.exists()


def test_model_is_saved_once_per_distinct_hash(world):
    bk.create_backup(world["url"], models_dir=world["models"], now=datetime(2026, 11, 1, 3, 0))
    bk.create_backup(world["url"], models_dir=world["models"], now=datetime(2026, 11, 2, 3, 0))
    saved = list((bk.backup_dir(world["db"]) / "models").glob("active_model_*.joblib"))
    assert len(saved) == 1
    (world["models"] / "active_model.joblib").write_bytes(b"a different model")
    bk.create_backup(world["url"], models_dir=world["models"], now=datetime(2026, 11, 3, 3, 0))
    assert len(list((bk.backup_dir(world["db"]) / "models").glob("active_model_*.joblib"))) == 2


def test_restore_test_reads_the_data_back(world):
    bk.create_backup(world["url"], models_dir=world["models"])
    rep = bk.restore_test(db_url=world["url"])
    assert rep.ok and rep.latest_snapshot == "2026-09-29" and rep.tables["market_data"] == 3


def test_restore_test_fails_clearly_when_there_is_no_backup(world):
    rep = bk.restore_test(db_url=world["url"])
    assert rep.ok is False and "no backup" in rep.problems[0].lower()


def test_non_sqlite_databases_are_refused_with_a_clear_message():
    with pytest.raises(bk.BackupError, match="SQLite"):
        bk.sqlite_path("postgresql://user:pw@host/db")


def test_missing_database_is_an_error_not_an_empty_backup(tmp_path):
    with pytest.raises(bk.BackupError, match="not found"):
        bk.create_backup(f"sqlite:///{(tmp_path / 'nope.db').as_posix()}")


# ── Second copy (BACKUP_MIRROR_DIR) ─────────────────────────────────────────────

def test_mirror_gets_a_verified_copy_with_the_same_rows(world, tmp_path):
    rep = bk.create_backup(world["url"], models_dir=world["models"])
    m = bk.mirror_backup(rep.path, tmp_path / "mirror")
    assert m.ok and m.path == tmp_path / "mirror" / rep.path.name
    assert m.tables == rep.tables
    assert not list((tmp_path / "mirror").glob("*.partial"))


def test_mirror_prunes_by_count_and_never_touches_other_files(world, tmp_path):
    mirror = tmp_path / "mirror"
    mirror.mkdir()
    (mirror / "my_own_copy.db").write_bytes(b"keep me")
    t0 = datetime(2026, 11, 1, 3, 30)
    for i in range(4):
        rep = bk.create_backup(world["url"], now=t0 + timedelta(days=i), models_dir=world["models"])
        assert bk.mirror_backup(rep.path, mirror, keep=2).ok
    names = sorted(p.name for p in mirror.iterdir())
    assert names == ["my_own_copy.db", "trader_20261103_033000.db", "trader_20261104_033000.db"]


def test_mirror_refuses_the_backup_folder_itself(world):
    rep = bk.create_backup(world["url"], models_dir=world["models"])
    m = bk.mirror_backup(rep.path, rep.path.parent)
    assert not m.ok and "another drive" in m.problems[0]


def test_a_corrupt_mirror_copy_is_never_kept_under_a_backup_name(world, tmp_path, monkeypatch):
    rep = bk.create_backup(world["url"], models_dir=world["models"])
    monkeypatch.setattr(bk.shutil, "copy2", lambda src, dst: Path(dst).write_bytes(b"not a database"))
    m = bk.mirror_backup(rep.path, tmp_path / "mirror")
    assert not m.ok and "failed verification" in m.problems[0]
    assert list((tmp_path / "mirror").iterdir()) == []


def test_cli_alerts_when_the_mirror_fails_but_keeps_the_primary_backup(world, tmp_path, monkeypatch):
    blocker = tmp_path / "not_a_folder"
    blocker.write_text("a file where the mirror folder should be", encoding="utf-8")
    monkeypatch.setattr(bk.settings, "db_url", world["url"])
    monkeypatch.setattr(bk.settings, "data_models_dir", str(world["models"]))
    monkeypatch.setattr(bk.settings, "backup_mirror_dir", str(blocker))
    assert bk._main(["create"]) == 1                      # non-zero, so run_trader.bat sends the backup alert
    assert len(bk.list_backups(world["db"])) == 1         # the primary backup still exists and counts


def test_cli_without_a_mirror_behaves_as_before(world, monkeypatch):
    monkeypatch.setattr(bk.settings, "db_url", world["url"])
    monkeypatch.setattr(bk.settings, "data_models_dir", str(world["models"]))
    monkeypatch.setattr(bk.settings, "backup_mirror_dir", "")
    assert bk._main(["create"]) == 0
