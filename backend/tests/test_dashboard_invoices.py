"""
Tests Invoice Timeline (dashboard) — service `timeline` + route.

- SQLite en mémoire (même patron que test_invoices.py).
- Statuts dérivés : paid / overdue (due_date < today) / due (sinon).
- Buckets mensuels par mois d'émission (issue_date), 6 derniers mois jusqu'au
  mois courant, montants natifs convertis en EUR via taux théoriques FX.
- outstanding_eur = somme EUR des factures non payées.
- open : factures non payées triées par due_date, avec statut due|overdue.
- Route via FastAPI TestClient + dependency_overrides[get_db].
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.routes.dashboard_invoices import router as dashboard_router
from backend.db import models
from backend.db.base import Base, get_db
from backend.services import invoices as invoices_service

TODAY = date(2026, 7, 3)


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite:///:memory:", future=True,
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, future=True)()
    yield db
    db.close()


def _seed(db):
    """Client USD + taux USD=0.92, et 3 factures aux statuts dérivés distincts."""
    client = models.Client(code="SWIB", legal_name="Swib Corp", currency="USD")
    db.add(client)
    db.add(models.FxRate(currency="USD", rate=Decimal("0.92")))
    db.commit()
    db.refresh(client)

    # Payée, émise en mai 2026, montant 1000 USD → 920 EUR
    db.add(models.Invoice(
        number="100", client_id=client.id, currency="USD",
        amount=Decimal("1000"), issue_date=date(2026, 5, 10),
        due_date=date(2026, 6, 10), status="paid",
    ))
    # Envoyée, due dans le futur, émise en juin 2026, 2000 USD → 1840 EUR (due)
    db.add(models.Invoice(
        number="101", client_id=client.id, currency="USD",
        amount=Decimal("2000"), issue_date=date(2026, 6, 15),
        due_date=date(2026, 8, 1), status="sent",
    ))
    # Envoyée, due dans le passé, émise en juin 2026, 500 USD → 460 EUR (overdue)
    db.add(models.Invoice(
        number="102", client_id=client.id, currency="USD",
        amount=Decimal("500"), issue_date=date(2026, 6, 20),
        due_date=date(2026, 6, 30), status="sent",
    ))
    db.commit()
    return client


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #

def test_timeline_month_buckets(session):
    _seed(session)
    result = invoices_service.timeline(session, today=TODAY)

    months = {m["month"]: m for m in result["months"]}
    # 6 derniers mois jusqu'à 2026-07 inclus, chronologiques.
    assert [m["month"] for m in result["months"]] == [
        "2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07",
    ]

    # Mai : la facture payée (1000 USD → 920 EUR).
    assert months["2026-05"]["paid_eur"] == Decimal("920.00")
    assert months["2026-05"]["due_eur"] == Decimal("0.00")
    assert months["2026-05"]["overdue_eur"] == Decimal("0.00")

    # Juin : 2000 USD due (1840) + 500 USD overdue (460).
    assert months["2026-06"]["paid_eur"] == Decimal("0.00")
    assert months["2026-06"]["due_eur"] == Decimal("1840.00")
    assert months["2026-06"]["overdue_eur"] == Decimal("460.00")


def test_timeline_outstanding_and_open(session):
    _seed(session)
    result = invoices_service.timeline(session, today=TODAY)

    # outstanding = due (1840) + overdue (460) = 2300 EUR.
    assert result["outstanding_eur"] == Decimal("2300.00")
    assert result["open_count"] == 2

    open_by_number = {o["number"]: o for o in result["open"]}
    assert set(open_by_number) == {"101", "102"}

    o_overdue = open_by_number["102"]
    assert o_overdue["status"] == "overdue"
    assert o_overdue["client_code"] == "SWIB"
    assert o_overdue["currency"] == "USD"
    assert o_overdue["amount"] == Decimal("500.00")
    assert o_overdue["amount_eur"] == Decimal("460.00")

    o_due = open_by_number["101"]
    assert o_due["status"] == "due"
    assert o_due["amount_eur"] == Decimal("1840.00")

    # Trié par due_date : 102 (2026-06-30) avant 101 (2026-08-01).
    assert [o["number"] for o in result["open"]] == ["102", "101"]


# --------------------------------------------------------------------------- #
# Route
# --------------------------------------------------------------------------- #

@pytest.fixture()
def client(session):
    app = FastAPI()
    app.include_router(dashboard_router)
    app.dependency_overrides[get_db] = lambda: session
    _seed(session)
    return TestClient(app)


def test_route_invoice_timeline(client):
    resp = client.get("/api/dashboard/invoice-timeline")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["open_count"] == 2
    assert Decimal(str(body["outstanding_eur"])) == Decimal("2300.00")
    assert len(body["months"]) == 6
    numbers = {o["number"] for o in body["open"]}
    assert numbers == {"101", "102"}
