"""
Tests du moteur de catégorisation + des routes Transactions.

- Service : seed → apply_rules (match & fallback), recategorize_all.
- Routes  : GET /api/transactions (filtres) et PATCH /api/transactions/{id}
  via TestClient + dependency_overrides[get_db] sur une base SQLite mémoire.
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.routes.categories import router as categories_router
from backend.api.routes.categories import rules_router
from backend.api.routes.transactions import router as transactions_router
from backend.db import models
from backend.db.base import Base, get_db
from backend.services.categorize import (
    UNCATEGORIZED_NAME,
    apply_rules,
    categorize_transaction,
    recategorize_all,
    seed_default_categories_and_rules,
)


@pytest.fixture
def db_session():
    """Session SQLite en mémoire, schéma créé, fermée en fin de test."""
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, future=True)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _account(session):
    acc = models.BankAccount(provider="revolut", account_uid="acc-1", currency="EUR")
    session.add(acc)
    session.commit()
    return acc


def _tx(session, **kwargs):
    defaults = dict(
        account_uid="acc-1",
        external_id="x",
        amount=Decimal("-10.00"),
        currency="EUR",
        counterparty="",
        description="",
        booked_date=date(2026, 1, 15),
    )
    defaults.update(kwargs)
    tx = models.Transaction(**defaults)
    session.add(tx)
    session.commit()
    return tx


def _category_id(session, name):
    return (
        session.query(models.Category)
        .filter(models.Category.name == name)
        .one()
        .id
    )


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #
def test_seed_creates_categories_and_rules(db_session):
    seed_default_categories_and_rules(db_session)
    assert db_session.query(models.Category).count() == 13
    assert db_session.query(models.CategoryRule).count() == 5


def test_seed_is_idempotent(db_session):
    seed_default_categories_and_rules(db_session)
    seed_default_categories_and_rules(db_session)
    assert db_session.query(models.Category).count() == 13
    assert db_session.query(models.CategoryRule).count() == 5


def test_apply_rules_counterparty_match(db_session):
    seed_default_categories_and_rules(db_session)
    _account(db_session)
    tx = _tx(db_session, external_id="1", counterparty="URSSAF PACA")
    assert apply_rules(db_session, tx) == _category_id(db_session, "URSSAF")


def test_apply_rules_is_case_insensitive_substring(db_session):
    seed_default_categories_and_rules(db_session)
    _account(db_session)
    tx = _tx(db_session, external_id="2", description="Paiement revolut**1234 conversion")
    assert apply_rules(db_session, tx) == _category_id(db_session, "Conversion FX")


def test_apply_rules_priority_first_match_wins(db_session):
    seed_default_categories_and_rules(db_session)
    _account(db_session)
    # counterparty matche URSSAF (prio 10) même si description contiendrait REVOLUT (prio 50).
    tx = _tx(
        db_session,
        external_id="3",
        counterparty="URSSAF IDF",
        description="virement REVOLUT",
    )
    assert apply_rules(db_session, tx) == _category_id(db_session, "URSSAF")


def test_apply_rules_no_match_returns_none(db_session):
    seed_default_categories_and_rules(db_session)
    _account(db_session)
    tx = _tx(db_session, external_id="4", counterparty="BOULANGERIE DUPONT")
    assert apply_rules(db_session, tx) is None


def test_categorize_transaction_fallback_to_uncategorized(db_session):
    seed_default_categories_and_rules(db_session)
    _account(db_session)
    tx = _tx(db_session, external_id="5", counterparty="INCONNU SARL")
    cid = categorize_transaction(db_session, tx)
    assert cid == _category_id(db_session, UNCATEGORIZED_NAME)
    assert tx.category_id == cid


def test_categorize_sets_kind_from_category_type(db_session):
    """La catégorisation dérive `kind` du type de catégorie (pour le filtre Type)."""
    seed_default_categories_and_rules(db_session)
    _account(db_session)
    # Charge (URSSAF) → kind 'charge'
    tx_charge = _tx(db_session, external_id="k1", counterparty="URSSAF PACA")
    categorize_transaction(db_session, tx_charge)
    assert tx_charge.kind == "charge"
    # Conversion (REVOLUT) → kind 'conversion'
    tx_conv = _tx(db_session, external_id="k2", description="paiement REVOLUT conversion")
    categorize_transaction(db_session, tx_conv)
    assert tx_conv.kind == "conversion"
    # Sans match (fourre-tout, type 'uncategorized') → kind 'other'
    tx_other = _tx(db_session, external_id="k3", counterparty="INCONNU")
    categorize_transaction(db_session, tx_other)
    assert tx_other.kind == "other"


def test_uncategorized_filter_matches_catchall_category(client, db_session):
    """Le filtre uncategorized=true trouve aussi les tx rangées dans la catégorie fourre-tout."""
    seed_default_categories_and_rules(db_session)
    _account(db_session)
    # Une tx sans match → catégorisée dans le fourre-tout (category_id non NULL).
    tx = _tx(db_session, external_id="catchall", counterparty="INCONNU SARL")
    categorize_transaction(db_session, tx)
    db_session.commit()
    assert tx.category_id is not None  # rangée dans le fourre-tout, pas NULL

    resp = client.get("/api/transactions", params={"uncategorized": "true"})
    assert resp.status_code == 200
    assert [t["external_id"] for t in resp.json()] == ["catchall"]


def test_kind_filter_returns_matching(client, db_session):
    """Le filtre kind renvoie les transactions du type demandé (dérivé de la catégorie)."""
    seed_default_categories_and_rules(db_session)
    _account(db_session)
    tx = _tx(db_session, external_id="charge1", counterparty="URSSAF PACA")
    categorize_transaction(db_session, tx)
    db_session.commit()
    resp = client.get("/api/transactions", params={"kind": "charge"})
    assert [t["external_id"] for t in resp.json()] == ["charge1"]
    assert client.get("/api/transactions", params={"kind": "revenue"}).json() == []


def test_disabled_rule_is_ignored(db_session):
    seed_default_categories_and_rules(db_session)
    _account(db_session)
    rule = (
        db_session.query(models.CategoryRule)
        .filter(models.CategoryRule.pattern == "URSSAF")
        .one()
    )
    rule.enabled = False
    db_session.commit()
    tx = _tx(db_session, external_id="6", counterparty="URSSAF PACA")
    assert apply_rules(db_session, tx) is None


def test_recategorize_all_counts_changes(db_session):
    seed_default_categories_and_rules(db_session)
    _account(db_session)
    _tx(db_session, external_id="a", counterparty="URSSAF PACA")
    _tx(db_session, external_id="b", counterparty="AG2R RETRAITE")
    _tx(db_session, external_id="c", counterparty="INCONNU")  # → fallback

    changed = recategorize_all(db_session)
    assert changed == 3  # les 3 passent de None à une catégorie

    # Rejouer sans modification ne compte rien.
    assert recategorize_all(db_session) == 0

    urssaf_id = _category_id(db_session, "URSSAF")
    tx_a = (
        db_session.query(models.Transaction)
        .filter(models.Transaction.external_id == "a")
        .one()
    )
    assert tx_a.category_id == urssaf_id


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@pytest.fixture
def client(db_session):
    """App FastAPI locale montant les routeurs du scope, get_db overridé."""
    app = FastAPI()
    app.include_router(transactions_router)
    app.include_router(categories_router)
    app.include_router(rules_router)

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)


def test_get_transactions_filters_and_category_name(client, db_session):
    seed_default_categories_and_rules(db_session)
    _account(db_session)
    urssaf_id = _category_id(db_session, "URSSAF")
    _tx(
        db_session,
        external_id="jan",
        counterparty="URSSAF",
        category_id=urssaf_id,
        booked_date=date(2026, 1, 10),
    )
    _tx(db_session, external_id="mar", counterparty="AUTRE", booked_date=date(2026, 3, 5))

    # Sans filtre : tri décroissant sur booked_date → mars d'abord.
    resp = client.get("/api/transactions")
    assert resp.status_code == 200
    body = resp.json()
    assert [t["external_id"] for t in body] == ["mar", "jan"]

    # Filtre catégorie → nom de catégorie renvoyé.
    resp = client.get("/api/transactions", params={"category_id": urssaf_id})
    body = resp.json()
    assert len(body) == 1
    assert body[0]["category_name"] == "URSSAF"

    # Filtre dates.
    resp = client.get(
        "/api/transactions",
        params={"date_from": "2026-02-01", "date_to": "2026-04-01"},
    )
    body = resp.json()
    assert [t["external_id"] for t in body] == ["mar"]

    # Filtre uncategorized (mars n'a pas de catégorie).
    resp = client.get("/api/transactions", params={"uncategorized": "true"})
    body = resp.json()
    assert [t["external_id"] for t in body] == ["mar"]


def test_patch_transaction_updates_and_404(client, db_session):
    seed_default_categories_and_rules(db_session)
    _account(db_session)
    repas_id = _category_id(db_session, "Repas")
    tx = _tx(db_session, external_id="patch", counterparty="RESTO")

    resp = client.patch(
        f"/api/transactions/{tx.id}",
        json={"category_id": repas_id, "kind": "charge"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["category_id"] == repas_id
    assert body["category_name"] == "Repas"
    assert body["kind"] == "charge"

    # 404 sur id inexistant.
    assert client.patch("/api/transactions/999999", json={"kind": "charge"}).status_code == 404
