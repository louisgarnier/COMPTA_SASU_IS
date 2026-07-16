"""
Rapprochement mensuel : solde officiel de fin de mois (saisi depuis un relevé) vs
solde reconstitué par l'app (ancre d'ouverture d'exercice + Σ mouvements jusqu'à la
fin du mois). Un écart révèle un frais/mouvement manquant sur ce compte, ce mois-là.
"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from sqlalchemy.orm import Session

from backend.db import models
from backend.services import openings
from backend.services.fx import load_rates, to_eur

_CENTS = Decimal("0.01")


def _q2(v: Decimal) -> Decimal:
    return Decimal(v).quantize(_CENTS, rounding=ROUND_HALF_UP)


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def reconstruct_balance(db: Session, account_uid: str, year: int, month: int) -> Decimal:
    """Solde reconstitué à la fin du mois = ancre d'ouverture + Σ mouvements jusque-là."""
    acc = (
        db.query(models.BankAccount)
        .filter(models.BankAccount.account_uid == account_uid)
        .first()
    )
    if acc is None:
        return Decimal("0.00")
    anchor, anchor_date = openings.opening_anchor(db, acc, year)
    base = anchor if anchor is not None else Decimal("0")
    start = anchor_date or date(year, 1, 1)
    movements = openings.sum_movements(db, account_uid, start, _month_end(year, month))
    return _q2(base + movements)


def monthly_reconciliation(db: Session, year: int) -> dict:
    """Vue 12 mois : par compte, officiel vs reconstitué + statut ; totaux € + couverture."""
    rates = load_rates(db)
    accounts = db.query(models.BankAccount).order_by(models.BankAccount.id).all()
    officials = {
        (mb.account_uid, mb.month): mb
        for mb in db.query(models.MonthlyBalance).filter(models.MonthlyBalance.year == year).all()
    }
    months: list[dict] = []
    covered = 0
    for month in range(1, 13):
        per_account: list[dict] = []
        total_eur_official = Decimal("0")
        total_eur_diff = Decimal("0")
        any_official = False
        any_warn = False
        for acc in accounts:
            mb = officials.get((acc.account_uid, month))
            reconstructed = reconstruct_balance(db, acc.account_uid, year, month)
            official = Decimal(mb.balance) if mb is not None else None
            diff = _q2(official - reconstructed) if official is not None else None
            status = "missing"
            if official is not None:
                any_official = True
                status = "ok" if abs(diff) < _CENTS else "warn"
                any_warn = any_warn or status == "warn"
                cur = (acc.currency or "EUR").upper()
                total_eur_official += to_eur(official, cur, rates)
                total_eur_diff += to_eur(diff, cur, rates)
            per_account.append({
                "account_uid": acc.account_uid,
                "currency": (acc.currency or "EUR").upper(),
                "official": official,
                "reconstructed": reconstructed,
                "diff": diff,
                "status": status,
            })
        month_status = "missing" if not any_official else ("warn" if any_warn else "ok")
        if any_official:
            covered += 1
        months.append({
            "month": month,
            "per_account": per_account,
            "total_eur_official": _q2(total_eur_official),
            "total_eur_diff": _q2(total_eur_diff),
            "status": month_status,
        })
    return {"year": year, "months": months, "coverage": f"{covered}/12"}
