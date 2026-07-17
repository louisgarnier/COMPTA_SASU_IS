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


def _settlement_date(t: models.Transaction):
    """Date de règlement d'une transaction = max(date comptable, date de valeur).

    C'est la date sur laquelle le relevé bancaire arrête ses soldes. `max` réconcilie
    les deux sources : synchro live (valeur APRÈS comptable → règlement = valeur) et
    import CSV (valeur AVANT comptable → règlement = comptable). Une seule date connue
    → on la prend ; pending (valeur nulle) → date comptable.
    """
    b, v = t.booked_date, t.value_date
    if b and v:
        return b if b >= v else v
    return b or v


def _sum_movements_settlement(db: Session, account_uid: str, start: date, upto: date) -> Decimal:
    """Σ des mouvements natifs sur [start, upto] par date de RÈGLEMENT (pas comptable).

    Spécifique au rapprochement mensuel : le relevé règle à la date de valeur, donc
    comparer à la date comptable créait des écarts de bord de mois qui s'inversaient
    le mois suivant. `sum_movements` (tréso/P&L) reste, lui, en date comptable.
    """
    txs = (
        db.query(models.Transaction)
        .filter(models.Transaction.account_uid == account_uid)
        .all()
    )
    total = Decimal("0")
    for t in txs:
        d = _settlement_date(t)
        if d is not None and start <= d <= upto:
            total += Decimal(t.amount or 0)
    return total


def reconstruct_balance(db: Session, account_uid: str, year: int, month: int) -> Decimal:
    """Solde reconstitué à fin de mois = ancre d'ouverture + Σ mouvements réglés jusque-là.

    Les mouvements sont comptés à leur date de RÈGLEMENT (cf. `_sum_movements_settlement`)
    pour coller à la convention du relevé bancaire.
    """
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
    movements = _sum_movements_settlement(db, account_uid, start, _month_end(year, month))
    return _q2(base + movements)


def _doc_short_name(doc: models.BalanceDocument) -> str:
    """Nom court d'un relevé archivé (banque) pour l'UI."""
    blob = f"{doc.label} {doc.filename}".lower()
    if "revolut" in blob:
        return "Revolut"
    if "qonto" in blob:
        return "Qonto"
    return (doc.label or doc.filename or "Relevé").split(" ")[0].capitalize()


def monthly_reconciliation(db: Session, year: int) -> dict:
    """Vue 12 mois : par compte, officiel vs reconstitué + statut ; totaux € + couverture."""
    rates = load_rates(db)
    accounts = db.query(models.BankAccount).order_by(models.BankAccount.id).all()
    year_balances = db.query(models.MonthlyBalance).filter(models.MonthlyBalance.year == year).all()
    officials = {(mb.account_uid, mb.month): mb for mb in year_balances}

    # relevés archivés liés à chaque mois (source_doc_id) → téléchargement / envoi
    doc_ids_by_month: dict[int, list[int]] = {}
    for mb in year_balances:
        if mb.source_doc_id:
            ids = doc_ids_by_month.setdefault(mb.month, [])
            if mb.source_doc_id not in ids:
                ids.append(mb.source_doc_id)
    all_doc_ids = {i for ids in doc_ids_by_month.values() for i in ids}
    docs_by_id = (
        {d.id: d for d in db.query(models.BalanceDocument)
         .filter(models.BalanceDocument.id.in_(all_doc_ids)).all()}
        if all_doc_ids else {}
    )
    months: list[dict] = []
    covered = 0
    for month in range(1, 13):
        per_account: list[dict] = []
        total_eur_official = Decimal("0")
        total_eur_diff = Decimal("0")
        any_official = False
        any_warn = False
        any_missing = False
        for acc in accounts:
            mb = officials.get((acc.account_uid, month))
            reconstructed = reconstruct_balance(db, acc.account_uid, year, month)
            official = Decimal(mb.balance) if mb is not None else None
            diff = _q2(official - reconstructed) if official is not None else None
            if official is not None:
                # solde officiel saisi (0,00 compris) → on rapproche
                any_official = True
                status = "ok" if abs(diff) < _CENTS else "warn"
                any_warn = any_warn or status == "warn"
                cur = (acc.currency or "EUR").upper()
                total_eur_official += to_eur(official, cur, rates)
                total_eur_diff += to_eur(diff, cur, rates)
            elif abs(reconstructed) >= _CENTS:
                # activité sur le compte mais aucun relevé saisi → il en manque un
                status = "missing"
                any_missing = True
            else:
                # poche vide ce mois-là (0 sans relevé) → rien à rapprocher
                status = "empty"
            per_account.append({
                "account_uid": acc.account_uid,
                "currency": (acc.currency or "EUR").upper(),
                "official": official,
                "reconstructed": reconstructed,
                "diff": diff,
                "status": status,
            })
        # priorité : écart (problème réel) > partiel (couverture incomplète) > ok.
        if not any_official:
            month_status = "missing"
        elif any_warn:
            month_status = "warn"
        elif any_missing:
            month_status = "partial"
        else:
            month_status = "ok"
        if any_official:
            covered += 1
        month_docs = [
            {"id": d.id, "name": _doc_short_name(d), "filename": d.filename}
            for did in doc_ids_by_month.get(month, [])
            if (d := docs_by_id.get(did)) is not None
        ]
        months.append({
            "month": month,
            "per_account": per_account,
            "total_eur_official": _q2(total_eur_official),
            "total_eur_diff": _q2(total_eur_diff),
            "status": month_status,
            "docs": month_docs,
        })
    return {"year": year, "months": months, "coverage": f"{covered}/12"}
