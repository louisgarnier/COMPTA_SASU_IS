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
        elif ctype == "charge" and amt < 0:
            charges[month] += amt

    months = []
    total_rev = _ZERO
    total_chg = _ZERO
    for m in range(1, 13):
        rev = revenue[m]
        chg = charges[m]
        total_rev += rev
        total_chg += chg
        months.append(
            {
                "month": f"{year:04d}-{m:02d}",
                "revenue_eur": q2(rev),
                "charges_eur": q2(chg),
                "result_eur": q2(rev + chg),
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
        "months": months,
        "totals": {
            "revenue_eur": q2(total_rev),
            "charges_eur": q2(total_chg),
            "result_eur": q2(total_rev + total_chg),
        },
    }
