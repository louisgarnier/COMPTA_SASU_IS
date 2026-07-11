"""
Tests du service Backup (sauvegarde automatique de la base SQLite).

Politique :
- `create_backup` produit une copie SQLite cohérente (API backup, pas un cp)
  nommée `lgc_YYYYMMDD_HHMMSS_<reason>.db` dans `data/backups/`.
- `prune_backups` : garde toutes les sauvegardes du jour, une seule (la
  première) pour chaque jour passé, supprime au-delà de 30 jours.
- La route POST /api/banking/sync sauvegarde AVANT de synchroniser et
  refuse de synchroniser si la sauvegarde échoue (fail-closed).
"""

import re
import sqlite3
from datetime import date, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.base import Base, get_db
from backend.services import backup as backup_service


def _make_source_db(path):
    """Crée une petite base SQLite réelle avec une ligne témoin."""
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE probe (id INTEGER PRIMARY KEY, label TEXT)")
    conn.execute("INSERT INTO probe (label) VALUES ('témoin')")
    conn.commit()
    conn.close()


# ---------------------------------------------------------------- create


def test_create_backup_creates_valid_sqlite_copy(tmp_path):
    src = tmp_path / "lgc.db"
    _make_source_db(src)
    dest_dir = tmp_path / "backups"

    result = backup_service.create_backup(src=src, dest_dir=dest_dir, reason="sync")

    assert result.exists()
    assert result.parent == dest_dir
    copy = sqlite3.connect(result)
    rows = copy.execute("SELECT label FROM probe").fetchall()
    copy.close()
    assert rows == [("témoin",)]


def test_create_backup_filename_has_timestamp_and_reason(tmp_path):
    src = tmp_path / "lgc.db"
    _make_source_db(src)

    result = backup_service.create_backup(
        src=src, dest_dir=tmp_path / "backups", reason="sync"
    )

    assert re.fullmatch(r"lgc_\d{8}_\d{6}_sync\.db", result.name)


def test_create_backup_missing_source_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        backup_service.create_backup(
            src=tmp_path / "absent.db", dest_dir=tmp_path / "backups"
        )


# ----------------------------------------------------------------- prune


def _touch_backup(dest_dir, day, hhmmss, reason="sync"):
    name = f"lgc_{day.strftime('%Y%m%d')}_{hhmmss}_{reason}.db"
    p = dest_dir / name
    p.write_bytes(b"x")
    return p


def test_prune_keeps_all_backups_of_today(tmp_path):
    today = date(2026, 7, 11)
    a = _touch_backup(tmp_path, today, "080000")
    b = _touch_backup(tmp_path, today, "120000")

    backup_service.prune_backups(tmp_path, today=today)

    assert a.exists() and b.exists()


def test_prune_keeps_only_first_backup_of_past_days(tmp_path):
    today = date(2026, 7, 11)
    yesterday = today - timedelta(days=1)
    first = _touch_backup(tmp_path, yesterday, "080000")
    second = _touch_backup(tmp_path, yesterday, "120000")

    backup_service.prune_backups(tmp_path, today=today)

    assert first.exists()
    assert not second.exists()


def test_prune_deletes_backups_older_than_retention(tmp_path):
    today = date(2026, 7, 11)
    old = _touch_backup(tmp_path, today - timedelta(days=31), "080000")
    kept = _touch_backup(tmp_path, today - timedelta(days=29), "080000")

    backup_service.prune_backups(tmp_path, today=today)

    assert not old.exists()
    assert kept.exists()


def test_prune_ignores_unrelated_files(tmp_path):
    today = date(2026, 7, 11)
    stranger = tmp_path / "notes.txt"
    stranger.write_text("ne pas toucher")

    backup_service.prune_backups(tmp_path, today=today)

    assert stranger.exists()


# ------------------------------------------------------------ route sync


@pytest.fixture()
def client():
    from backend.api.routes.banking import router

    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, future=True)

    app = FastAPI()
    app.include_router(router)

    def _get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    return TestClient(app, raise_server_exceptions=False)


def test_sync_route_backs_up_before_syncing(client, monkeypatch, tmp_path):
    from backend.api.routes import banking as banking_routes

    calls = []
    monkeypatch.setattr(
        banking_routes.backup_service,
        "create_backup",
        lambda **kw: calls.append("backup") or tmp_path / "fake.db",
    )
    monkeypatch.setattr(
        banking_routes.banking_service,
        "sync",
        lambda db: calls.append("sync")
        or {
            "accounts_synced": 0,
            "transactions_added": 0,
            "transactions_skipped": 0,
        },
    )

    resp = client.post("/api/banking/sync")

    assert resp.status_code == 200
    assert calls == ["backup", "sync"]


def test_sync_route_fails_closed_if_backup_fails(client, monkeypatch):
    from backend.api.routes import banking as banking_routes

    def _boom(**kw):
        raise OSError("disque plein")

    calls = []
    monkeypatch.setattr(banking_routes.backup_service, "create_backup", _boom)
    monkeypatch.setattr(
        banking_routes.banking_service,
        "sync",
        lambda db: calls.append("sync"),
    )

    resp = client.post("/api/banking/sync")

    assert resp.status_code == 500
    assert "sauvegarde" in resp.json()["detail"].lower()
    assert calls == []  # la synchro n'a PAS tourné
