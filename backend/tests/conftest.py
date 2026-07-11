"""
Fixtures globales des tests backend.

Isolation : la route POST /api/banking/sync sauvegarde la base AVANT de
synchroniser (services/backup.py). En test, source et destination sont
redirigées vers un répertoire temporaire — aucun test ne doit jamais
écrire dans le vrai data/ (ni lgc.db, ni backups/).
"""

import sqlite3

import pytest

from backend.services import backup as backup_service


@pytest.fixture(autouse=True)
def _backups_isolated(monkeypatch, tmp_path):
    src = tmp_path / "lgc.db"
    sqlite3.connect(src).close()  # base vide : suffisant pour être copiable
    monkeypatch.setattr(backup_service, "_default_db_path", lambda: src)
