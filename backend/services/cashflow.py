"""
Service Cashflow mensuel LGC — encaissements / décaissements par devise.

Vue trésorerie « flux » : pour chaque mois de l'exercice, l'argent qui ENTRE
(incoming) et qui SORT (outgoing), ventilé par devise (exprimé en EUR).

- Mois écoulés + mois en cours → RÉEL : produits/charges opérationnels des
  transactions, mêmes règles d'exclusion que le P&L (kinds/catégories non
  opérationnels ignorés).
- Mois futurs → PRÉVISION :
  - incoming : entrées de prévision (jours × TJH × fx) groupées par devise du
    client (montant déjà exprimé en EUR).
  - outgoing : charges prévisionnelles du mois (moyenne des mois écoulés),
    agrégat EUR → bucket unique « EUR ».

`is_forecast` = mois strictement postérieur au mois courant (today).
Tous les montants en `Decimal` 2 décimales.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from backend.db import models
from backend.logging_config import get_logger
from backend.services import forecast as forecast_service
from backend.services.fx import load_rates
from backend.services.pnl import _EXCLUDED_CATEGORY_TYPES, _EXCLUDED_KINDS
from backend.services.treasury import eur_amount, q2

logger = get_logger("cashflow", channel="api")

_ZERO = Decimal("0")


def _real_month_flows(db: Session, year: int) -> dict[int, dict]:
    """
    Flux réels par mois (1..12) depuis les transactions opérationnelles.

    Retourne {mois: {"in": {ccy: eur}, "out": {ccy: eur_positif}}} en appliquant
    les mêmes exclusions que le P&L (kinds/catégories non opérationnels).
    """
    rates = load_rates(db)
    cat_type = {c.id: c.type for c in db.query(models.Category).all()}

    flows: dict[int, dict] = {
        m: {"in": {}, "out": {}} for m in range(1, 13)
    }

    for tx in db.query(models.Transaction).all():
        if tx.booked_date is None or tx.booked_date.year != year:
            continue
        if (tx.kind or "") in _EXCLUDED_KINDS:
            continue
        ctype = cat_type.get(tx.category_id)
        if ctype in _EXCLUDED_CATEGORY_TYPES:
            continue

        month = tx.booked_date.month
        amt = eur_amount(tx, rates)
        ccy = (tx.currency or "EUR").upper()

        is_revenue = (tx.kind or "") == "revenue" or ctype == "revenue"
        if is_revenue and amt > 0:
            bucket = flows[month]["in"]
            bucket[ccy] = bucket.get(ccy, _ZERO) + amt
        elif ctype == "charge" and amt < 0:
            bucket = flows[month]["out"]
            bucket[ccy] = bucket.get(ccy, _ZERO) + (-amt)  # magnitude positive

    return flows


def _forecast_incoming(db: Session, year: int) -> dict[str, dict]:
    """
    Encaissements prévisionnels par mois ('YYYY-MM') → {ccy: eur}.

    (jours × TJH × fx) groupé par devise du client (déjà exprimé en EUR).
    """
    out: dict[str, dict] = {}
    for row in forecast_service.get_inputs(db, year):
        amount = Decimal(row.days) * Decimal(row.rate) * Decimal(row.fx_rate)
        ccy = ((row.client.currency if row.client else None) or "EUR").upper()
        bucket = out.setdefault(row.month, {})
        bucket[ccy] = bucket.get(ccy, _ZERO) + amount
    return out


def monthly_cashflow(db: Session, year: int, today: Optional[date] = None) -> dict:
    """Encaissements/décaissements par mois et par devise pour l'exercice `year`."""
    if today is None:
        today = date.today()
    current = (today.year, today.month)

    real = _real_month_flows(db, year)
    forecast_in = _forecast_incoming(db, year)
    projection = forecast_service.project(db, year, today=today)
    forecast_charge = {m["month"]: m["charges_forecast_eur"] for m in projection["months"]}

    months = []
    total_in = _ZERO
    total_out = _ZERO

    for m in range(1, 13):
        key = f"{year:04d}-{m:02d}"
        is_forecast = (year, m) > current

        if is_forecast:
            incoming = dict(forecast_in.get(key, {}))
            chg = Decimal(forecast_charge.get(key, _ZERO))
            outgoing = {"EUR": chg} if chg > 0 else {}
        else:
            incoming = dict(real[m]["in"])
            outgoing = dict(real[m]["out"])

        incoming = {c: q2(v) for c, v in sorted(incoming.items())}
        outgoing = {c: q2(v) for c, v in sorted(outgoing.items())}
        incoming_eur = q2(sum(incoming.values(), _ZERO))
        outgoing_eur = q2(sum(outgoing.values(), _ZERO))
        total_in += incoming_eur
        total_out += outgoing_eur

        months.append(
            {
                "month": key,
                "incoming_by_ccy": incoming,
                "outgoing_by_ccy": outgoing,
                "incoming_eur": incoming_eur,
                "outgoing_eur": outgoing_eur,
                "is_forecast": is_forecast,
            }
        )

    logger.info(
        "📤 [Cashflow] compute: année=%s entrées=%s sorties=%s ✅",
        year,
        q2(total_in),
        q2(total_out),
    )
    return {
        "year": year,
        "months": months,
        "totals": {
            "incoming_eur": q2(total_in),
            "outgoing_eur": q2(total_out),
            "net_eur": q2(total_in - total_out),
        },
    }
