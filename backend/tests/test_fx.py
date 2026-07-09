"""
Tests des taux de change (routes /api/fx-rates + service fx).

- Ajout d'une devise pas encore en usage (reste visible dans la vue).
- Refus d'un taux ≤ 0 (422) — protège tous les agrégats EUR.
- Devise en usage sans taux → flag `missing`.
"""

from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.routes.fx import router as fx_router
from backend.db import models
from backend.db.base import Base, get_db


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:", future=True,
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, future=True)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session):
    app = FastAPI()
    app.include_router(fx_router)
    app.dependency_overrides[get_db] = lambda: (yield db_session)
    return TestClient(app)


def _tx(session, currency):
    session.add(models.BankAccount(provider="p", account_uid=f"a-{currency}", currency=currency))
    session.commit()


def test_currency_in_use_without_rate_is_missing(client, db_session):
    _tx(db_session, "GBP")
    rows = client.get("/api/fx-rates").json()
    gbp = next(r for r in rows if r["currency"] == "GBP")
    assert gbp["missing"] is True
    assert Decimal(str(gbp["rate"])) == Decimal("1")  # fallback à régler


def test_add_currency_not_in_use_persists_in_view(client, db_session):
    # Aucune tx GBP, mais on ajoute son taux → doit rester visible (union stored ∪ in-use).
    resp = client.put("/api/fx-rates", json={"rates": [{"currency": "GBP", "rate": "1.17"}]})
    assert resp.status_code == 200
    rows = client.get("/api/fx-rates").json()
    gbp = next(r for r in rows if r["currency"] == "GBP")
    assert gbp["missing"] is False
    assert Decimal(str(gbp["rate"])) == Decimal("1.17")


def test_rate_zero_or_negative_rejected(client):
    assert client.put("/api/fx-rates", json={"rates": [{"currency": "USD", "rate": "0"}]}).status_code == 422
    assert client.put("/api/fx-rates", json={"rates": [{"currency": "USD", "rate": "-0.5"}]}).status_code == 422


def test_rate_change_reprices_invoice_forecast_eur(client, db_session):
    """Changer le taux dans Réglages recale le « € (prév.) » de la facture."""
    db_session.add(models.Settings(id=1))
    db_session.add(models.Client(id=1, code="X", legal_name="X", currency="USD"))
    inv = models.Invoice(
        number="1", client_id=1, month="2026-05", currency="USD",
        amount=Decimal("1000"), amount_eur_forecast=Decimal("920"),
        fx_rate_forecast=Decimal("0.92"), status="due",
    )
    db_session.add(inv)
    db_session.commit()

    # Passe USD de 0.92 à 0.85 → le prévisionnel EUR doit suivre (1000 × 0.85).
    resp = client.put("/api/fx-rates", json={"rates": [{"currency": "USD", "rate": "0.85"}]})
    assert resp.status_code == 200
    db_session.refresh(inv)
    assert inv.amount_eur_forecast == Decimal("850.00")
    assert inv.fx_rate_forecast == Decimal("0.850000")
