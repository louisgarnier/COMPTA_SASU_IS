"""
Tests du résumé P&L dashboard (service `pnl.summary` + route).

Équation FreeAgent : Revenus − Charges = Résultat ; Résultat − IS estimé =
Résultat net ; Résultat net + Report à nouveau = Distribuable.

- SQLite en mémoire (pattern test_forecast.py).
- Vérifie les invariants d'équation et la ventilation par devise.
- Route testée via FastAPI TestClient + dependency_overrides[get_db].
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.routes.dashboard_pnl import router as dashboard_router
from backend.db import models
from backend.db.base import Base, get_db
from backend.services import pnl as pnl_service


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    try:
        yield session
    finally:
        session.close()


_TODAY = date(2026, 7, 3)


def _seed(db) -> None:
    """Seed compte, catégories, transactions (revenue USD + charge EUR)."""
    db.add(models.BankAccount(provider="revolut", account_uid="ACC", currency="EUR"))
    rev_cat = models.Category(name="Prestations", type="revenue")
    chg_cat = models.Category(name="Frais", type="charge")
    db.add_all([rev_cat, chg_cat])
    # Taux théorique USD → EUR = 0.90 (sinon fallback 1).
    db.add(models.FxRate(currency="USD", rate=Decimal("0.90")))
    db.commit()
    db.refresh(rev_cat)
    db.refresh(chg_cat)

    # Revenu : 10000 USD → 9000 EUR.
    db.add(
        models.Transaction(
            account_uid="ACC", external_id="r1", booked_date=date(2026, 2, 10),
            amount=Decimal("10000"), currency="USD", kind="revenue",
            category_id=rev_cat.id,
        )
    )
    # Revenu EUR : 2000.
    db.add(
        models.Transaction(
            account_uid="ACC", external_id="r2", booked_date=date(2026, 3, 5),
            amount=Decimal("2000"), currency="EUR", kind="revenue",
            category_id=rev_cat.id,
        )
    )
    # Charge EUR : -500.
    db.add(
        models.Transaction(
            account_uid="ACC", external_id="c1", booked_date=date(2026, 1, 20),
            amount=Decimal("-500"), currency="EUR", kind="charge",
            category_id=chg_cat.id,
        )
    )
    db.commit()


# --------------------------------------------------------------------------- #
# Service : summary                                                           #
# --------------------------------------------------------------------------- #


def test_summary_equation_invariants(db_session):
    _seed(db_session)
    settings = models.Settings(id=1, retained_earnings_eur=Decimal("1500"))
    db_session.add(settings)
    db_session.commit()

    s = pnl_service.summary(db_session, 2026, today=_TODAY)

    # Revenus = 9000 (USD) + 2000 (EUR) = 11000 ; charges = 500 (positif).
    assert s["revenue_eur"] == Decimal("11000.00")
    assert s["charges_eur"] == Decimal("500.00")
    # Résultat = Revenus − Charges.
    assert s["result_eur"] == s["revenue_eur"] - s["charges_eur"]
    assert s["result_eur"] == Decimal("10500.00")
    # Résultat net = Résultat − IS estimé.
    assert s["net_result_eur"] == s["result_eur"] - s["is_estimate_eur"]
    # Distribuable = Résultat net + Report à nouveau.
    assert s["retained_earnings_eur"] == Decimal("1500.00")
    assert s["distributable_eur"] == s["net_result_eur"] + s["retained_earnings_eur"]


def test_summary_by_currency_present_with_positive_charges(db_session):
    _seed(db_session)
    s = pnl_service.summary(db_session, 2026, today=_TODAY)

    assert "by_currency" in s
    by = {row["currency"]: row for row in s["by_currency"]}
    assert "USD" in by
    assert "EUR" in by
    # USD : 10000 natif → 9000 EUR.
    assert by["USD"]["revenue_native"] == Decimal("10000.00")
    assert by["USD"]["revenue_eur"] == Decimal("9000.00")
    # EUR : charge 500 exposée en magnitude positive.
    assert by["EUR"]["charges_eur"] == Decimal("500.00")
    # Toutes les charges par devise sont positives (magnitude).
    for row in s["by_currency"]:
        assert row["charges_eur"] >= Decimal("0")


def test_summary_creates_settings_singleton_when_missing(db_session):
    _seed(db_session)
    # Aucun Settings pré-existant → report à nouveau par défaut 0.
    s = pnl_service.summary(db_session, 2026, today=_TODAY)
    assert s["retained_earnings_eur"] == Decimal("0.00")
    assert db_session.get(models.Settings, 1) is not None


# --------------------------------------------------------------------------- #
# Route : GET /api/dashboard/pnl-summary                                      #
# --------------------------------------------------------------------------- #


@pytest.fixture
def client_app(db_session):
    app = FastAPI()
    app.include_router(dashboard_router)
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def test_route_returns_summary(client_app, db_session):
    _seed(db_session)
    resp = client_app.get("/api/dashboard/pnl-summary", params={"year": 2026})
    assert resp.status_code == 200
    data = resp.json()
    assert data["revenue_eur"] == "11000.00"
    assert data["charges_eur"] == "500.00"
    assert data["result_eur"] == "10500.00"
    assert "by_currency" in data
    assert "distributable_eur" in data


def test_route_requires_year(client_app):
    resp = client_app.get("/api/dashboard/pnl-summary")
    assert resp.status_code == 422
