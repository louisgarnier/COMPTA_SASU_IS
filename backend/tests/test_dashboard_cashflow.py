"""
Tests du domaine Cashflow (encaissements/décaissements mensuels par devise).

- SQLite en mémoire (pattern test_forecast.py).
- Passé/mois en cours → réel (transactions). Futur → prévision (forecast).
- Réf. today = 2026-07-03 : Jan–Juin écoulés, Juillet en cours, Août+ futurs.
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

from backend.api.routes.dashboard_cashflow import router as cashflow_router
from backend.db import models
from backend.db.base import Base, get_db
from backend.services import cashflow as cashflow_service
from backend.services import forecast as forecast_service

_TODAY = date(2026, 7, 3)  # Jan–Juin écoulés, Juil en cours, Août+ futurs


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


def _base(db):
    """Compte + catégories + taux USD théorique 0.9."""
    db.add(models.BankAccount(provider="revolut", account_uid="ACC", currency="EUR"))
    rev = models.Category(name="Ventes", type="revenue")
    chg = models.Category(name="Charges", type="charge")
    db.add_all([rev, chg])
    db.add(models.FxRate(currency="USD", rate=Decimal("0.9")))
    db.commit()
    db.refresh(rev)
    db.refresh(chg)
    return rev, chg


def _tx(db, cat_id, d, amount, currency, kind, ext):
    db.add(
        models.Transaction(
            account_uid="ACC",
            external_id=ext,
            booked_date=d,
            amount=Decimal(str(amount)),
            currency=currency,
            kind=kind,
            category_id=cat_id,
        )
    )
    db.commit()


def _by_month(result):
    return {m["month"]: m for m in result["months"]}


# --------------------------------------------------------------------------- #
# Service : mois passés = réel par devise                                      #
# --------------------------------------------------------------------------- #


def test_past_months_real_incoming_outgoing_by_currency(db_session):
    rev, chg = _base(db_session)
    # Janvier : encaissements EUR 1000 + USD 2000 (→ 1800 EUR).
    _tx(db_session, rev.id, date(2026, 1, 10), "1000", "EUR", "revenue", "r1")
    _tx(db_session, rev.id, date(2026, 1, 20), "2000", "USD", "revenue", "r2")
    # Février : décaissements EUR -300 + USD -100 (→ 90 EUR magnitude).
    _tx(db_session, chg.id, date(2026, 2, 5), "-300", "EUR", "charge", "c1")
    _tx(db_session, chg.id, date(2026, 2, 15), "-100", "USD", "charge", "c2")

    result = cashflow_service.monthly_cashflow(db_session, 2026, today=_TODAY)
    by = _by_month(result)

    jan = by["2026-01"]
    assert jan["is_forecast"] is False
    assert jan["incoming_by_ccy"] == {"EUR": Decimal("1000.00"), "USD": Decimal("1800.00")}
    assert jan["incoming_eur"] == Decimal("2800.00")
    assert jan["outgoing_by_ccy"] == {}
    assert jan["outgoing_eur"] == Decimal("0.00")

    feb = by["2026-02"]
    assert feb["is_forecast"] is False
    assert feb["outgoing_by_ccy"] == {"EUR": Decimal("300.00"), "USD": Decimal("90.00")}
    assert feb["outgoing_eur"] == Decimal("390.00")
    assert feb["incoming_by_ccy"] == {}


def test_totals_sum_over_year(db_session):
    rev, chg = _base(db_session)
    _tx(db_session, rev.id, date(2026, 1, 10), "1000", "EUR", "revenue", "r1")
    _tx(db_session, chg.id, date(2026, 2, 5), "-300", "EUR", "charge", "c1")

    result = cashflow_service.monthly_cashflow(db_session, 2026, today=_TODAY)
    totals = result["totals"]
    # Incoming : 1000 réel (Jan), aucune prévision → 1000.
    assert totals["incoming_eur"] == Decimal("1000.00")
    # Outgoing : 300 réel (Fév) + charges prévisionnelles des 5 mois futurs
    # (Août–Déc) à la moyenne des 6 mois écoulés = 300/6 = 50 → 5 × 50 = 250.
    assert totals["outgoing_eur"] == Decimal("550.00")
    assert totals["net_eur"] == Decimal("450.00")


# --------------------------------------------------------------------------- #
# Service : mois futurs = prévision                                           #
# --------------------------------------------------------------------------- #


def test_future_incoming_bucketed_on_expected_payment_date(db_session):
    """
    L'encaissement d'une prévision de septembre à 45j tombe en NOVEMBRE
    (fin sept + 45j ≈ 14 nov), pas en septembre → cœur du modèle accrual/cash.
    """
    rev, chg = _base(db_session)
    # Charges écoulées → moyenne mensuelle des 6 mois = 600/6 = 100.
    _tx(db_session, chg.id, date(2026, 1, 20), "-600", "EUR", "charge", "c1")

    client = models.Client(
        code="SWIB", legal_name="SWIB", currency="USD", payment_terms_days=45
    )
    db_session.add(client)
    db_session.commit()
    db_session.refresh(client)
    forecast_service.upsert_inputs(
        db_session,
        [{"month": "2026-09", "client_id": client.id, "days": Decimal("10"),
          "rate": Decimal("500"), "fx_rate": Decimal("0.9"), "note": ""}],
    )

    by = _by_month(cashflow_service.monthly_cashflow(db_session, 2026, today=_TODAY))

    # Septembre (mois travaillé) : AUCUN encaissement — l'argent n'arrive pas encore.
    sep = by["2026-09"]
    assert sep["is_forecast"] is True
    assert sep["incoming_by_ccy"] == {}
    # Charges prévisionnelles futures = moyenne des mois écoulés, bucket EUR.
    assert sep["outgoing_by_ccy"] == {"EUR": Decimal("100.00")}

    # Novembre : le cash de la presta de septembre (10 × 500 × 0.9 = 4500 USD-EUR).
    nov = by["2026-11"]
    assert nov["incoming_by_ccy"] == {"USD": Decimal("4500.00")}
    assert nov["incoming_eur"] == Decimal("4500.00")


def test_due_invoice_bucketed_on_due_date(db_session):
    """Une facture émise (`due`) apparaît au cashflow le mois de son `due_date`."""
    _base(db_session)
    client = models.Client(
        code="NWH", legal_name="NWH", currency="EUR", payment_terms_days=45
    )
    db_session.add(client)
    db_session.commit()
    db_session.refresh(client)
    # Émise, non payée : service août, échéance 2026-10-01 → cash en octobre.
    db_session.add(models.Invoice(
        number="100", client_id=client.id, month="2026-08", status="due",
        currency="EUR", amount=Decimal("3000"),
        issue_date=date(2026, 8, 18), due_date=date(2026, 10, 1),
    ))
    db_session.commit()

    by = _by_month(cashflow_service.monthly_cashflow(db_session, 2026, today=_TODAY))
    assert by["2026-10"]["incoming_by_ccy"] == {"EUR": Decimal("3000.00")}
    assert by["2026-08"]["incoming_by_ccy"] == {}


# --------------------------------------------------------------------------- #
# Route : GET /api/dashboard/cashflow                                         #
# --------------------------------------------------------------------------- #


@pytest.fixture
def client_app(db_session):
    app = FastAPI()
    app.include_router(cashflow_router)
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def test_route_get_cashflow(client_app, db_session):
    rev, _chg = _base(db_session)
    _tx(db_session, rev.id, date(2026, 1, 10), "1000", "EUR", "revenue", "r1")

    resp = client_app.get("/api/dashboard/cashflow", params={"year": 2026})
    assert resp.status_code == 200
    data = resp.json()
    assert data["year"] == 2026
    assert len(data["months"]) == 12
    jan = {m["month"]: m for m in data["months"]}["2026-01"]
    assert jan["incoming_by_ccy"] == {"EUR": "1000.00"}
    assert data["totals"]["incoming_eur"] == "1000.00"
