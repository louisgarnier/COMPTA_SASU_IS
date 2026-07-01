"""
Service Compte de résultat mensuel LGC (P&L opérationnel).

Périmètre : produits & charges d'exploitation uniquement. On EXCLUT les flux
non opérationnels — kinds 'investment' | 'conversion' | 'transfer' | 'internal'
et toute transaction dont la catégorie est de type
'conversion' | 'transfer' | 'internal'.

- Produits (revenue) : montants EUR positifs de kind 'revenue' ou de catégorie
  de type 'revenue'.
- Charges (charge)  : montants EUR négatifs de catégorie de type 'charge'.
- Résultat = produits + charges (les charges sont déjà négatives).

Douze mois toujours présents (Jan..Déc), remplis à zéro.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from backend.db import models
from backend.logging_config import get_logger
from backend.services.treasury import _get_settings, eur_amount, q2

logger = get_logger("pnl", channel="api")

_ZERO = Decimal("0")

# Flux exclus du résultat d'exploitation.
_EXCLUDED_KINDS = {"investment", "conversion", "transfer", "internal"}
_EXCLUDED_CATEGORY_TYPES = {"conversion", "transfer", "internal"}


def monthly_pnl(db: Session, year: int) -> dict:
    """Agrège produits, charges et résultat par mois pour l'exercice `year`."""
    settings = _get_settings(db)

    # Mapping catégorie -> type (pour éviter N requêtes de relation).
    cat_type = {
        c.id: c.type for c in db.query(models.Category).all()
    }

    # Accumulateurs indexés par mois (1..12).
    revenue = {m: _ZERO for m in range(1, 13)}
    charges = {m: _ZERO for m in range(1, 13)}
    # Produits ventilés par devise d'origine (équivalent EUR), par mois.
    revenue_ccy = {m: {} for m in range(1, 13)}
    # Montant natif cumulé par devise (ex: total en $US, en $CA).
    revenue_native = {}
    currencies: set[str] = set()
    # Charges ventilées par devise (EUR + natif, valeurs négatives).
    charges_eur_ccy = {}
    charges_native_ccy = {}
    charge_currencies: set[str] = set()

    txs = db.query(models.Transaction).all()
    for tx in txs:
        if tx.booked_date is None or tx.booked_date.year != year:
            continue
        if (tx.kind or "") in _EXCLUDED_KINDS:
            continue
        ctype = cat_type.get(tx.category_id)
        if ctype in _EXCLUDED_CATEGORY_TYPES:
            continue

        month = tx.booked_date.month
        amt = eur_amount(tx, settings)

        is_revenue = (tx.kind or "") == "revenue" or ctype == "revenue"
        if is_revenue and amt > 0:
            revenue[month] += amt
            ccy = (tx.currency or "EUR").upper()
            currencies.add(ccy)
            revenue_ccy[month][ccy] = revenue_ccy[month].get(ccy, _ZERO) + amt
            revenue_native[ccy] = revenue_native.get(ccy, _ZERO) + abs(
                Decimal(tx.amount or 0)
            )
        elif ctype == "charge" and amt < 0:
            charges[month] += amt
            cc = (tx.currency or "EUR").upper()
            charge_currencies.add(cc)
            charges_eur_ccy[cc] = charges_eur_ccy.get(cc, _ZERO) + amt
            charges_native_ccy[cc] = charges_native_ccy.get(cc, _ZERO) - abs(
                Decimal(tx.amount or 0)
            )

    ccy_order = sorted(currencies)
    charge_ccy_order = sorted(charge_currencies)
    months = []
    total_rev = _ZERO
    total_chg = _ZERO
    totals_by_ccy = {c: _ZERO for c in ccy_order}
    for m in range(1, 13):
        rev = revenue[m]
        chg = charges[m]
        total_rev += rev
        total_chg += chg
        by_ccy = {c: q2(revenue_ccy[m].get(c, _ZERO)) for c in ccy_order}
        for c in ccy_order:
            totals_by_ccy[c] += revenue_ccy[m].get(c, _ZERO)
        months.append(
            {
                "month": f"{year:04d}-{m:02d}",
                "revenue_eur": q2(rev),
                "charges_eur": q2(chg),
                "result_eur": q2(rev + chg),
                "revenue_by_currency": by_ccy,
            }
        )

    logger.info(
        "📤 [PnL] compute: année=%s, produits=%s charges=%s ✅",
        year,
        q2(total_rev),
        q2(total_chg),
    )
    return {
        "year": year,
        "currencies": ccy_order,
        "currencies_all": sorted(currencies | charge_currencies),
        "months": months,
        "totals": {
            "revenue_eur": q2(total_rev),
            "charges_eur": q2(total_chg),
            "result_eur": q2(total_rev + total_chg),
            "revenue_by_currency": {c: q2(totals_by_ccy[c]) for c in ccy_order},
            "revenue_native_by_currency": {
                c: q2(revenue_native.get(c, _ZERO)) for c in ccy_order
            },
            "charges_by_currency": {
                c: q2(charges_eur_ccy.get(c, _ZERO)) for c in charge_ccy_order
            },
            "charges_native_by_currency": {
                c: q2(charges_native_ccy.get(c, _ZERO)) for c in charge_ccy_order
            },
        },
    }
