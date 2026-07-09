"""
Service Soldes d'ouverture d'exercice LGC.

Le solde de chaque compte au 31/12 (repris du relevé officiel) devient le point
de départ de l'exercice suivant. Pure donnée saisie dans les Réglages — jamais
de valeur en dur dans le code.

Sémantique de la clé `OpeningBalance.year` : c'est l'exercice **ouvert**. Le solde
vaut au 01/01/`year`, soit la clôture au 31/12/`year`-1.

Colonne « Contrôle (vs mouvements) » : compare le solde saisi à l'ouverture
*implicite* reconstruite depuis le solde actuel — `solde actuel − Σ mouvements de
l'exercice`. Un écart révèle un flux manquant ou une dérive (arrondis FX). C'est
le tie-out que l'utilisateur boucle chaque année.
"""

from __future__ import annotations

from datetime import date as date_type
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from sqlalchemy.orm import Session

from backend.db import models
from backend.logging_config import get_logger
from backend.services.fx import load_rates, rate_for, to_eur

logger = get_logger("openings", channel="api")

_CENTS = Decimal("0.01")
_ZERO = Decimal("0")


def _q2(value: Decimal) -> Decimal:
    return Decimal(value).quantize(_CENTS, rounding=ROUND_HALF_UP)


def _accounts(db: Session) -> list[models.BankAccount]:
    return db.query(models.BankAccount).order_by(models.BankAccount.id).all()


def _entered(db: Session, year: int) -> dict[str, models.OpeningBalance]:
    """Soldes d'ouverture saisis pour l'exercice `year`, indexés par compte."""
    rows = (
        db.query(models.OpeningBalance)
        .filter(models.OpeningBalance.year == year)
        .all()
    )
    return {r.account_uid: r for r in rows}


def opening_anchor(
    db: Session, acc: models.BankAccount, target_year: int
) -> tuple[Optional[Decimal], Optional[date_type]]:
    """
    Ancre de reconstruction pour un compte à un exercice donné.

    Prend le relevé saisi le plus récent dont l'exercice ≤ `target_year` : son solde
    est l'ouverture, sa date d'ancrage le 01/01 de cet exercice. La reconstruction
    remonte ensuite depuis cette date (ouverture + Σ mouvements). À défaut de toute
    saisie, retombe sur l'ancien `acc.opening_balance` / `opening_balance_date`.
    """
    row = (
        db.query(models.OpeningBalance)
        .filter(
            models.OpeningBalance.account_uid == acc.account_uid,
            models.OpeningBalance.year <= target_year,
        )
        .order_by(models.OpeningBalance.year.desc())
        .first()
    )
    if row is not None:
        return Decimal(row.balance), date_type(row.year, 1, 1)
    # Repli legacy (aucune saisie annuelle) — compat rétro.
    if acc.opening_balance is not None:
        return Decimal(acc.opening_balance), acc.opening_balance_date
    return None, None


def _sum_tx_from(
    db: Session, account_uid: str, start: date_type, upto: date_type
) -> Decimal:
    """Σ des mouvements natifs du compte avec `start ≤ booked_date ≤ upto`."""
    txs = (
        db.query(models.Transaction)
        .filter(models.Transaction.account_uid == account_uid)
        .all()
    )
    total = _ZERO
    for t in txs:
        d = t.booked_date
        if d is None:
            continue
        if start <= d <= upto:
            total += Decimal(t.amount or 0)
    return total


def get_openings(db: Session, year: int, today: Optional[date_type] = None) -> dict:
    """
    Vue « Soldes d'ouverture » pour l'exercice `year`.

    Une ligne par compte bancaire : devise, solde saisi (ou None), et le Contrôle
    (ouverture implicite reconstruite = solde actuel − Σ mouvements de l'exercice ;
    écart signalé s'il diffère de la saisie). Fournit aussi le tie-out agrégé EUR.
    """
    if today is None:
        today = date_type.today()
    rates = load_rates(db)
    entered = _entered(db, year)
    year_start = date_type(year, 1, 1)

    rows: list[dict] = []
    total_entered_eur = _ZERO
    total_current_eur = _ZERO
    for acc in _accounts(db):
        cur = (acc.currency or "EUR").upper()
        ob = entered.get(acc.account_uid)
        entered_val = Decimal(ob.balance) if ob is not None else None

        # Solde actuel de référence pour le contrôle : solde synchronisé du provider.
        current_native = Decimal(acc.balance or 0)
        # Ouverture implicite = solde actuel − mouvements de l'exercice jusqu'à ce jour.
        movements = _sum_tx_from(db, acc.account_uid, year_start, today)
        implied = current_native - movements

        control: Optional[dict] = None
        if entered_val is not None:
            diff = _q2(entered_val - implied)
            control = {
                "implied": _q2(implied),
                "movements": _q2(movements),
                "diff": diff,
                "status": "ok" if abs(diff) < _CENTS else "warn",
            }
            total_entered_eur += to_eur(entered_val, cur, rates)
        total_current_eur += to_eur(current_native, cur, rates)

        rows.append(
            {
                "account_uid": acc.account_uid,
                "name": acc.name,
                "provider": acc.provider,
                "currency": cur,
                "balance": _q2(entered_val) if entered_val is not None else None,
                "current_balance": _q2(current_native),
                "rate": rate_for(rates, cur),
                "control": control,
            }
        )

    tie = {
        "opening_eur": _q2(total_entered_eur),
        "current_eur": _q2(total_current_eur),
        # Bouclé si au moins une saisie et diff agrégée sous le seuil de matérialité (1 €).
        "reconciles": any(r["control"] for r in rows),
    }
    logger.info("📤 [Openings] get: exercice=%d, %d compte(s) ✅", year, len(rows))
    return {"year": year, "accounts": rows, "tie_out": tie}


def list_years(db: Session, today: Optional[date_type] = None) -> list[int]:
    """Exercices disponibles pour le sélecteur : ceux saisis + l'exercice courant."""
    if today is None:
        today = date_type.today()
    years = {
        y for (y,) in db.query(models.OpeningBalance.year).distinct().all()
    }
    years.add(today.year)
    return sorted(years)


def set_openings(
    db: Session,
    year: int,
    items: list[dict],
    today: Optional[date_type] = None,
) -> dict:
    """
    Upsert des soldes d'ouverture de l'exercice `year` (pure donnée).

    `items` : liste de {account_uid, balance}. Met aussi à jour l'ancre legacy
    `BankAccount.opening_balance` / `opening_balance_date` du compte à partir du
    relevé le plus récent ≤ année courante, pour que la reconstruction tréso en
    bénéficie sans dépendre du chemin OpeningBalance.
    """
    if today is None:
        today = date_type.today()
    valid_uids = {a.account_uid for a in _accounts(db)}
    saved = 0
    for it in items:
        uid = it.get("account_uid")
        if uid not in valid_uids:
            continue
        balance = Decimal(str(it.get("balance", "0")))
        row = (
            db.query(models.OpeningBalance)
            .filter(
                models.OpeningBalance.account_uid == uid,
                models.OpeningBalance.year == year,
            )
            .one_or_none()
        )
        if row is None:
            row = models.OpeningBalance(account_uid=uid, year=year, balance=balance)
            db.add(row)
        else:
            row.balance = balance
        saved += 1
    db.commit()

    # Réaligne l'ancre legacy de chaque compte sur son relevé le plus récent ≤ courant.
    for acc in _accounts(db):
        bal, anchor_date = opening_anchor(db, acc, today.year)
        if bal is not None and anchor_date is not None:
            acc.opening_balance = _q2(bal)
            acc.opening_balance_date = anchor_date
    db.commit()

    logger.info("🗄️ [Openings] set: exercice=%d, %d solde(s) ✅", year, saved)
    return get_openings(db, year, today=today)
