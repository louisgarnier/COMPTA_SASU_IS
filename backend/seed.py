"""
Seed de données de démonstration LGC (2026, mono-utilisateur).

Idempotent : ne fait rien si des comptes bancaires existent déjà, sauf --reset.
Usage :
    backend/venv/bin/python -m backend.seed            # seed si vide
    backend/venv/bin/python -m backend.seed --reset    # vide puis reseed
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from decimal import Decimal

from backend.db.base import SessionLocal, init_db
from backend.db import models
from backend.services.categorize import (
    recategorize_all,
    seed_default_categories_and_rules,
)

D = Decimal


def _reset(db):
    for m in (
        models.Transaction, models.Invoice, models.ForecastInput,
        models.Investment, models.CategoryRule, models.Category,
        models.BankAccount, models.Client, models.Settings,
    ):
        db.query(m).delete()
    db.commit()


def _settings(db):
    s = db.get(models.Settings, 1)
    if not s:
        s = models.Settings(id=1)
        db.add(s)
    s.company_name = "LGC Consulting SASU"
    s.siret = "900 123 456 00012"
    s.naf = "6202A"
    s.tva_intracom = "FR12900123456"
    s.address = "12 rue de la Tréso, 75002 Paris"
    s.is_low_rate = D("0.15")
    s.is_threshold = D("42500")
    s.is_high_rate = D("0.25")
    s.next_invoice_number = 62
    s.default_fx_usd = D("0.92")
    s.default_fx_cad = D("0.68")
    db.commit()


def _clients(db):
    swib = models.Client(
        code="SWIB", legal_name="Swib Inc.", address="500 Market St, San Francisco, CA",
        currency="USD", tjh=D("650"), pay_iban="", counterparty_match="SWIB",
    )
    nwh = models.Client(
        code="NWH", legal_name="Northwind Health Ltd.", address="200 King St W, Toronto, ON",
        currency="CAD", tjh=D("800"), pay_iban="", counterparty_match="NORTHWIND",
    )
    db.add_all([swib, nwh])
    db.commit()
    return swib, nwh


def _accounts(db):
    accs = [
        models.BankAccount(
            provider="revolut", account_uid="rev-eur-main", currency="EUR",
            iban_masked="FR76****EUR1", name="Revolut Business EUR",
            balance=D("0"), opening_balance=D("18500"), opening_balance_date=date(2026, 1, 1),
        ),
        models.BankAccount(
            provider="revolut", account_uid="rev-usd", currency="USD",
            iban_masked="FR76****USD9", name="Revolut USD",
            balance=D("0"), opening_balance=D("4200"), opening_balance_date=date(2026, 1, 1),
        ),
        models.BankAccount(
            provider="qonto", account_uid="qonto-eur", currency="EUR",
            iban_masked="FR76****QON7", name="Qonto Courant EUR",
            balance=D("0"), opening_balance=D("9000"), opening_balance_date=date(2026, 1, 1),
        ),
    ]
    db.add_all(accs)
    db.commit()
    return accs


def _tx(account_uid, ext, d, amount, currency, desc, cp, kind, amount_eur, fx=None):
    return models.Transaction(
        account_uid=account_uid, external_id=ext, booked_date=d, value_date=d,
        amount=D(str(amount)), currency=currency, description=desc, counterparty=cp,
        kind=kind, fx_rate=D(str(fx)) if fx else None,
        amount_eur=D(str(amount_eur)) if amount_eur is not None else None,
        raw_json="{}", created_at=datetime(2026, 1, 1, 12, 0, 0),
    )


def _transactions(db):
    txs = []
    # Revenus clients mensuels (USD/CAD) Jan–Juin, convertis en EUR
    for m in range(1, 7):
        txs.append(_tx("rev-usd", f"swib-{m}", date(2026, m, 5), 9750, "USD",
                       f"SWIB INV 2026-0{m}", "SWIB INC", "revenue", round(9750 * 0.92, 2), 0.92))
        txs.append(_tx("rev-eur-main", f"nwh-{m}", date(2026, m, 8), round(12800 * 0.68, 2), "EUR",
                       f"NORTHWIND PAYMENT 0{m}", "NORTHWIND HEALTH", "revenue", round(12800 * 0.68, 2)))
    # Charges récurrentes
    for m in range(1, 7):
        txs.append(_tx("qonto-eur", f"urssaf-{m}", date(2026, m, 15), -1850, "EUR",
                       "PRELEVEMENT URSSAF", "URSSAF PACA", "charge", -1850))
        txs.append(_tx("qonto-eur", f"ag2r-{m}", date(2026, m, 15), -420, "EUR",
                       "COTISATION RETRAITE", "AG2R LA MONDIALE", "charge", -420))
        txs.append(_tx("rev-eur-main", f"tools-{m}", date(2026, m, 3), -89.90, "EUR",
                       "SUBSCRIPTION SAAS", "NOTION LABS", "charge", -89.90))
        txs.append(_tx("rev-eur-main", f"meal-{m}", date(2026, m, 20), -34.50, "EUR",
                       "RESTAURANT", "LE BISTROT", "charge", -34.50))
    # Impôts (trimestriel)
    txs.append(_tx("qonto-eur", "dgfip-1", date(2026, 3, 15), -3100, "EUR",
                   "ACOMPTE IS", "DGFIP", "charge", -3100))
    # Prélèvement GoCardless
    txs.append(_tx("qonto-eur", "gc-1", date(2026, 2, 10), -240, "EUR",
                   "PRLV GOCARDLESS", "GOCARDLESS", "charge", -240))
    # Frais bancaires
    txs.append(_tx("rev-eur-main", "fee-1", date(2026, 4, 1), -12, "EUR",
                   "MONTHLY FEE", "REVOLUT", "charge", -12))
    # Conversion FX (USD -> EUR)
    txs.append(_tx("rev-usd", "conv-usd-1", date(2026, 4, 6), -9000, "USD",
                   "REVOLUT EXCHANGE USD->EUR", "REVOLUT", "conversion", -8280, 0.92))
    txs.append(_tx("rev-eur-main", "conv-eur-1", date(2026, 4, 6), 8280, "EUR",
                   "REVOLUT EXCHANGE USD->EUR", "REVOLUT", "conversion", 8280))
    # Virement vers placement (investissement)
    txs.append(_tx("rev-eur-main", "invest-1", date(2026, 2, 1), -5000, "EUR",
                   "VIREMENT PLACEMENT CRYPTO", "KRAKEN", "investment", -5000))
    db.add_all(txs)
    db.commit()


def _investments(db):
    db.add(models.Investment(
        label="Portefeuille crypto (Kraken)", type="crypto", currency="EUR",
        opening_value=D("8000"), opening_value_eur=D("8000"),
        current_value=D("11500"), current_value_eur=D("11500"),
        as_of_date=date(2026, 6, 30), note="BTC/ETH — apport année 5000€",
    ))
    db.commit()


def _invoices(db, swib, nwh):
    inv1 = models.Invoice(
        number="62", client_id=swib.id, period_label="Janvier 2026",
        period_start=date(2026, 1, 1), period_end=date(2026, 1, 31),
        hours=D("15"), rate=D("650"), currency="USD", amount=D("9750"),
        issue_date=date(2026, 2, 1), due_date=date(2026, 2, 28), status="paid",
    )
    inv2 = models.Invoice(
        number="63", client_id=nwh.id, period_label="Février 2026",
        period_start=date(2026, 2, 1), period_end=date(2026, 2, 28),
        hours=D("16"), rate=D("800"), currency="CAD", amount=D("12800"),
        issue_date=date(2026, 3, 1), due_date=date(2026, 3, 31), status="sent",
    )
    db.add_all([inv1, inv2])
    # prochaine facture = 64
    s = db.get(models.Settings, 1)
    s.next_invoice_number = 64
    db.commit()


def _forecast(db, swib, nwh):
    rows = []
    for m in range(7, 13):  # Juil–Déc projection
        rows.append(models.ForecastInput(
            month=f"2026-{m:02d}", client_id=swib.id,
            days=D("15"), rate=D("650"), fx_rate=D("0.92"), note=""))
        rows.append(models.ForecastInput(
            month=f"2026-{m:02d}", client_id=nwh.id,
            days=D("16"), rate=D("800"), fx_rate=D("0.68"), note=""))
    db.add_all(rows)
    db.commit()


def main(reset: bool = False):
    init_db()
    db = SessionLocal()
    try:
        if reset:
            _reset(db)
        if db.query(models.BankAccount).count() > 0:
            print("⏭️  Données déjà présentes — seed ignoré (utilise --reset pour réinitialiser).")
            return
        seed_default_categories_and_rules(db)
        db.commit()
        _settings(db)
        swib, nwh = _clients(db)
        _accounts(db)
        _transactions(db)
        _investments(db)
        _invoices(db, swib, nwh)
        _forecast(db, swib, nwh)
        changed = recategorize_all(db)
        db.commit()
        print(f"✅ Seed terminé : {db.query(models.Transaction).count()} transactions "
              f"({changed} catégorisées), {db.query(models.Invoice).count()} factures, "
              f"{db.query(models.BankAccount).count()} comptes.")
    finally:
        db.close()


if __name__ == "__main__":
    main(reset="--reset" in sys.argv)
