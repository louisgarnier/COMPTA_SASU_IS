"""
Tests Story ⑤ : rapprochement manuel facture ↔ transaction + variance forecast/réel.

- SQLite en mémoire (pattern test_invoices.py).
- manual_reconcile : fige paiement (date, montant, FX réel) + variance EUR.
- unreconcile : repasse `due`, libère la transaction, efface les champs.
- reconcile_candidates : revenus non rattachés, triés par proximité de montant.
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db import models
from backend.db.base import Base
from backend.services import invoices as invoices_service


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


def _setup(db):
    db.add(models.Settings(id=1, next_invoice_number=62))
    client = models.Client(code="SWIB", legal_name="Swib", currency="USD",
                           counterparty_match="SWIB")
    db.add(client)
    db.add(models.BankAccount(provider="revolut", account_uid="ACC", currency="USD"))
    db.commit()
    db.refresh(client)
    return client


def _due_invoice(db, client, *, forecast_eur="9000"):
    inv = models.Invoice(
        number="62", client_id=client.id, month="2026-05", currency="USD",
        amount=Decimal("10050"), amount_eur_forecast=Decimal(forecast_eur),
        issue_date=date(2026, 6, 1), due_date=date(2026, 8, 1), status="due",
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


def _tx(db, ext, amount, ccy="USD", eur=None, cp="SWIB LTD", d=date(2026, 6, 12)):
    tx = models.Transaction(
        account_uid="ACC", external_id=ext, booked_date=d,
        amount=Decimal(str(amount)), currency=ccy, kind="revenue",
        counterparty=cp, fx_rate=Decimal("0.90"),
        amount_eur=Decimal(str(eur)) if eur is not None else None,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


def test_manual_reconcile_sets_payment_and_variance(db):
    client = _setup(db)
    inv = _due_invoice(db, client, forecast_eur="9000")
    tx = _tx(db, "t1", "10050", eur="9045")

    out = invoices_service.manual_reconcile(db, inv.id, tx.id)

    assert out.status == "paid"
    assert out.paid_transaction_id == tx.id
    assert out.paid_date == date(2026, 6, 12)
    assert out.amount_received == Decimal("10050.00")
    assert out.amount_eur_received == Decimal("9045.00")
    assert out.variance_eur == Decimal("45.00")     # 9045 − 9000
    db.refresh(tx)
    assert tx.invoice_id == inv.id


def test_manual_reconcile_rejects_forecast_and_linked_tx(db):
    client = _setup(db)
    # Facture prévisionnelle → refus (générer d'abord).
    fc = models.Invoice(number="F-1-2026-05", client_id=client.id, month="2026-05",
                        currency="USD", amount=Decimal("100"), status="forecast")
    db.add(fc)
    db.commit()
    db.refresh(fc)
    tx = _tx(db, "t1", "100")
    with pytest.raises(HTTPException):
        invoices_service.manual_reconcile(db, fc.id, tx.id)

    # Transaction déjà rattachée à une autre facture → refus.
    inv1 = _due_invoice(db, client)
    inv2 = models.Invoice(number="63", client_id=client.id, month="2026-06",
                          currency="USD", amount=Decimal("10050"), status="due")
    db.add(inv2)
    db.commit()
    db.refresh(inv2)
    tx2 = _tx(db, "t2", "10050", eur="9045")
    invoices_service.manual_reconcile(db, inv1.id, tx2.id)
    with pytest.raises(HTTPException):
        invoices_service.manual_reconcile(db, inv2.id, tx2.id)


def test_unreconcile_reverts_to_due(db):
    client = _setup(db)
    inv = _due_invoice(db, client)
    tx = _tx(db, "t1", "10050", eur="9045")
    invoices_service.manual_reconcile(db, inv.id, tx.id)

    out = invoices_service.unreconcile(db, inv.id)

    assert out.status == "due"
    assert out.paid_transaction_id is None
    assert out.amount_received is None
    assert out.variance_eur is None
    db.refresh(tx)
    assert tx.invoice_id is None


def test_delete_invoice_removes_row(db):
    client = _setup(db)
    inv = _due_invoice(db, client)

    invoices_service.delete_invoice(db, inv.id)

    assert db.get(models.Invoice, inv.id) is None


def test_delete_reconciled_invoice_releases_transaction(db):
    client = _setup(db)
    inv = _due_invoice(db, client)
    tx = _tx(db, "t1", "10050", eur="9045")
    invoices_service.manual_reconcile(db, inv.id, tx.id)
    db.refresh(tx)
    assert tx.invoice_id == inv.id

    invoices_service.delete_invoice(db, inv.id)

    assert db.get(models.Invoice, inv.id) is None
    db.refresh(tx)
    assert tx.invoice_id is None            # transaction libérée


def test_delete_missing_invoice_raises_404(db):
    _setup(db)
    with pytest.raises(HTTPException) as exc:
        invoices_service.delete_invoice(db, 9999)
    assert exc.value.status_code == 404


def test_reconcile_candidates_sorted_by_amount_proximity(db):
    client = _setup(db)
    inv = _due_invoice(db, client)          # amount 10050 USD
    other = models.Invoice(number="63", client_id=client.id, month="2026-06",
                           currency="USD", amount=Decimal("10050"), status="due")
    db.add(other)
    db.commit()
    db.refresh(other)
    far = _tx(db, "far", "500")
    close = _tx(db, "close", "10050")
    linked = _tx(db, "linked", "10050")
    linked.invoice_id = other.id            # déjà rattachée → exclue
    db.commit()

    cands = invoices_service.reconcile_candidates(db, inv.id)
    ids = [t.external_id for t in cands]
    assert ids[0] == "close"                # la plus proche en premier
    assert "far" in ids
    assert "linked" not in ids              # exclue (déjà rattachée)
