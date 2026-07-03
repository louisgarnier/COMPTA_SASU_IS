"""
Tests du cycle de vie facture (Story ②, EPIC-5) : fusion forecast→Invoice,
règle anti-doublon dans le cashflow, transitions de statut & rapprochement.

- SQLite en mémoire (pattern test_forecast.py).
- Réf. today = 2026-07-03 : Jan–Juin écoulés, Juillet en cours, Août+ futurs.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db import models
from backend.db.base import Base
from backend.services import cashflow as cashflow_service
from backend.services import forecast as forecast_service
from backend.services import invoices as invoices_service

_TODAY = date(2026, 7, 3)


@pytest.fixture
def db():
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
    """Compte EUR + catégorie revenue + taux USD théorique 0.9 + client USD."""
    db.add(models.BankAccount(provider="revolut", account_uid="ACC", currency="EUR"))
    rev = models.Category(name="Ventes", type="revenue")
    db.add(rev)
    db.add(models.FxRate(currency="USD", rate=Decimal("0.9")))
    client = models.Client(
        code="SWIB", legal_name="Swib", currency="USD",
        default_hours_per_day=Decimal("8"), counterparty_match="SWIB",
    )
    db.add(client)
    db.commit()
    db.refresh(rev)
    db.refresh(client)
    return rev, client


def _rev_tx(db, cat_id, d, amount, currency, ext, counterparty=""):
    tx = models.Transaction(
        account_uid="ACC", external_id=ext, booked_date=d,
        amount=Decimal(str(amount)), currency=currency, kind="revenue",
        category_id=cat_id, counterparty=counterparty,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


# --------------------------------------------------------------------------- #
# Fusion : une prévision EST une facture status='forecast'                     #
# --------------------------------------------------------------------------- #


def test_upsert_forecast_creates_forecast_invoice(db):
    _, client = _base(db)
    forecast_service.upsert_inputs(db, [{
        "month": "2026-08", "client_id": client.id,
        "days": Decimal("10"), "rate": Decimal("100"), "fx_rate": Decimal("0.9"), "note": "x",
    }])

    invs = db.query(models.Invoice).all()
    assert len(invs) == 1
    inv = invs[0]
    assert inv.status == "forecast"
    assert inv.month == "2026-08"
    assert inv.currency == "USD"
    assert inv.amount == Decimal("1000.00")          # 10 × 100 (natif)
    assert inv.hours == Decimal("80.00")             # 10 j × 8 h/j
    assert inv.amount_eur_forecast == Decimal("900.00")  # 1000 × 0.9
    assert inv.number == "F-%d-2026-08" % client.id  # numéro provisoire

    # get_inputs round-trip → forme historique.
    rows = forecast_service.get_inputs(db, 2026)
    assert len(rows) == 1
    assert rows[0].days == Decimal("10")
    assert rows[0].fx_rate == Decimal("0.9")


def test_upsert_is_idempotent_on_month_client(db):
    _, client = _base(db)
    for days in ("10", "12"):
        forecast_service.upsert_inputs(db, [{
            "month": "2026-08", "client_id": client.id,
            "days": Decimal(days), "rate": Decimal("100"), "fx_rate": Decimal("0.9"), "note": "",
        }])
    invs = db.query(models.Invoice).filter(models.Invoice.status == "forecast").all()
    assert len(invs) == 1                       # upsert, pas d'accumulation
    assert invs[0].days == Decimal("12")


# --------------------------------------------------------------------------- #
# Anti-doublon : revenu compté une seule fois                                  #
# --------------------------------------------------------------------------- #


def test_paid_invoice_revenue_counted_once_in_cashflow(db):
    """Facture payée (juin) + sa transaction : le revenu du mois = 1× la tx."""
    rev, client = _base(db)
    tx = _rev_tx(db, rev.id, date(2026, 6, 10), "10000", "USD", "r-june", "SWIB CORP")
    # Facture réelle de juin, payée et rapprochée à la transaction.
    inv = models.Invoice(
        number="62", client_id=client.id, month="2026-06", currency="USD",
        amount=Decimal("10000"), amount_eur_forecast=Decimal("9000"),
        issue_date=date(2026, 6, 1), status="paid", paid_transaction_id=tx.id,
    )
    db.add(inv)
    tx.invoice_id = inv.id
    db.commit()

    by = {m["month"]: m for m in cashflow_service.monthly_cashflow(db, 2026, today=_TODAY)["months"]}
    # 10000 USD × 0.9 = 9000, compté 1× (via la transaction, PAS + la facture).
    assert by["2026-06"]["incoming_eur"] == Decimal("9000.00")


def test_forecast_invoice_counts_in_future_month_once(db):
    rev, client = _base(db)
    forecast_service.upsert_inputs(db, [{
        "month": "2026-08", "client_id": client.id,
        "days": Decimal("10"), "rate": Decimal("100"), "fx_rate": Decimal("0.9"), "note": "",
    }])
    by = {m["month"]: m for m in cashflow_service.monthly_cashflow(db, 2026, today=_TODAY)["months"]}
    aug = by["2026-08"]
    assert aug["is_forecast"] is True
    assert aug["incoming_eur"] == Decimal("900.00")   # 10 × 100 × 0.9, une seule source


def test_paid_forecast_invoice_drops_from_forecast_side(db):
    """Une facture prévisionnelle passée à 'paid' n'est plus comptée en prévision."""
    rev, client = _base(db)
    forecast_service.upsert_inputs(db, [{
        "month": "2026-08", "client_id": client.id,
        "days": Decimal("10"), "rate": Decimal("100"), "fx_rate": Decimal("0.9"), "note": "",
    }])
    inv = db.query(models.Invoice).one()
    inv.status = "paid"          # réalisée → sort du forecast
    db.commit()

    by = {m["month"]: m for m in cashflow_service.monthly_cashflow(db, 2026, today=_TODAY)["months"]}
    assert by["2026-08"]["incoming_eur"] == Decimal("0.00")   # plus de double compte


# --------------------------------------------------------------------------- #
# Rapprochement : remplit les champs de paiement réel + variance              #
# --------------------------------------------------------------------------- #


def test_reconcile_fills_payment_fields_and_variance(db):
    rev, client = _base(db)
    # Transaction réelle : 10050 USD encaissés, EUR réel 9045 (fx réel 0.90).
    tx = _rev_tx(db, rev.id, date(2026, 6, 12), "10050", "USD", "r1", "SWIB LTD")
    tx.fx_rate = Decimal("0.90")
    tx.amount_eur = Decimal("9045")
    # Facture 'due' générée, prévision EUR 9000.
    inv = models.Invoice(
        number="62", client_id=client.id, month="2026-06", currency="USD",
        amount=Decimal("10050"), amount_eur_forecast=Decimal("9000"),
        issue_date=date(2026, 6, 1), due_date=date(2026, 8, 1), status="due",
    )
    db.add(inv)
    db.commit()

    n = invoices_service.reconcile_payments(db)
    assert n == 1
    db.refresh(inv)
    assert inv.status == "paid"
    assert inv.paid_transaction_id == tx.id
    assert inv.paid_date == date(2026, 6, 12)
    assert inv.amount_received == Decimal("10050.00")
    assert inv.amount_eur_received == Decimal("9045.00")
    assert inv.variance_eur == Decimal("45.00")     # 9045 − 9000


def test_forecast_invoice_excluded_from_outstanding_timeline(db):
    _, client = _base(db)
    forecast_service.upsert_inputs(db, [{
        "month": "2026-08", "client_id": client.id,
        "days": Decimal("10"), "rate": Decimal("100"), "fx_rate": Decimal("0.9"), "note": "",
    }])
    result = invoices_service.timeline(db, today=_TODAY)
    assert result["open_count"] == 0                # prévisionnel ≠ dû
    assert result["outstanding_eur"] == Decimal("0.00")
