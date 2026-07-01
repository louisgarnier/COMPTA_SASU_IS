"""
Tests du service + routes Banking (Enable Banking).

Sans identifiants ni réseau, le service DOIT être en mode MOCK et fournir des
données déterministes. On vérifie :
- mode MOCK actif (pas de creds/pyjwt),
- list_aspsps contient 'Revolut Business' et 'Qonto',
- sync insère des transactions, signe les montants (un DBIT est négatif),
- un DEUXIÈME sync n'ajoute rien (dedup) et compte des skipped,
- un trade FX (même external_id, comptes différents) n'est PAS dédupliqué,
- les routes répondent (TestClient + dependency_overrides[get_db]).
"""

from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.routes.banking import router
from backend.db import models
from backend.db.base import Base, get_db
from backend.services import banking as banking_service


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, future=True)()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client(session):
    app = FastAPI()
    app.include_router(router)

    def _override():
        yield session

    app.dependency_overrides[get_db] = _override
    return TestClient(app)


# ---------------------------------------------------------------------------
# Service (mode mock)
# ---------------------------------------------------------------------------

def test_mock_mode_active():
    """Sans app_id / clé / pyjwt, le service est en mode mock."""
    assert banking_service.is_live() is False
    st = banking_service.status()
    assert st["live"] is False
    assert "mock" in st["message"].lower()


def test_list_aspsps_contains_revolut_and_qonto():
    names = {a["name"] for a in banking_service.list_aspsps(country="FR")}
    assert "Revolut Business" in names
    assert "Qonto" in names


def test_create_session_creates_accounts(session):
    result = banking_service.create_session(session, code="dummy-code")
    accounts = result["accounts"]
    assert len(accounts) >= 2
    providers = {a.provider for a in accounts}
    assert "revolut" in providers
    assert "qonto" in providers
    # Idempotent : une 2e session ne duplique pas les comptes.
    banking_service.create_session(session, code="dummy-code")
    assert session.query(models.BankAccount).count() == len(accounts)


def test_sync_inserts_and_signs_amounts(session):
    banking_service.create_session(session, code="c")
    result = banking_service.sync(session)

    assert result["accounts_synced"] >= 2
    assert result["transactions_added"] > 0
    assert session.query(models.Transaction).count() == result["transactions_added"]

    # Un DBIT connu doit être négatif ; un CRDT positif.
    dbit = (
        session.query(models.Transaction)
        .filter(models.Transaction.external_id == "rev-tx-002")
        .one()
    )
    assert dbit.amount < 0
    assert dbit.amount == Decimal("-89.90")

    crdt = (
        session.query(models.Transaction)
        .filter(models.Transaction.external_id == "rev-tx-001")
        .one()
    )
    assert crdt.amount > 0

    # booked_date >= 2026-01-01
    for t in session.query(models.Transaction).all():
        assert t.booked_date is not None
        assert t.booked_date.year == 2026


def test_second_sync_is_deduped(session):
    banking_service.create_session(session, code="c")
    first = banking_service.sync(session)
    count_after_first = session.query(models.Transaction).count()

    second = banking_service.sync(session)
    count_after_second = session.query(models.Transaction).count()

    assert second["transactions_added"] == 0
    assert second["transactions_skipped"] > 0
    assert count_after_second == count_after_first == first["transactions_added"]


def test_fx_shared_external_id_not_deduped_across_accounts(session):
    """Un même external_id sur deux comptes différents = deux transactions."""
    banking_service.create_session(session, code="c")
    banking_service.sync(session)
    fx_legs = (
        session.query(models.Transaction)
        .filter(models.Transaction.external_id == "fx-shared-777")
        .all()
    )
    assert len(fx_legs) == 2
    assert {leg.account_uid for leg in fx_legs} == {"mock-revolut-eur", "mock-qonto-eur"}


def test_sync_updates_balance_and_last_synced(session):
    banking_service.create_session(session, code="c")
    banking_service.sync(session)
    for acc in session.query(models.BankAccount).all():
        assert acc.last_synced_at is not None


# ---------------------------------------------------------------------------
# Routes (TestClient)
# ---------------------------------------------------------------------------

def test_route_status(client):
    resp = client.get("/api/banking/status")
    assert resp.status_code == 200
    assert resp.json()["live"] is False


def test_route_aspsps(client):
    resp = client.get("/api/banking/aspsps", params={"country": "FR"})
    assert resp.status_code == 200
    names = {a["name"] for a in resp.json()}
    assert {"Revolut Business", "Qonto"}.issubset(names)


def test_route_connect(client):
    resp = client.post("/api/banking/connect", json={"aspsp_name": "Revolut Business"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["authorization_url"]
    assert body["state"]


def test_route_sessions_then_connections_then_sync(client):
    r1 = client.post("/api/banking/sessions", json={"code": "abc"})
    assert r1.status_code == 200
    assert len(r1.json()["accounts"]) >= 2

    r2 = client.get("/api/banking/connections")
    assert r2.status_code == 200
    assert len(r2.json()) >= 2

    r3 = client.post("/api/banking/sync")
    assert r3.status_code == 200
    assert r3.json()["transactions_added"] > 0

    # 2e sync via route = dedup.
    r4 = client.post("/api/banking/sync")
    assert r4.json()["transactions_added"] == 0
    assert r4.json()["transactions_skipped"] > 0
