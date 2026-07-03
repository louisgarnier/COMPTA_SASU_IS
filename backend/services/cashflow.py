"""
Service Cashflow mensuel LGC — encaissements / décaissements par devise.

Vue trésorerie « flux » : pour chaque mois de l'exercice, l'argent qui ENTRE
(incoming) et qui SORT (outgoing), ventilé par devise (exprimé en EUR).

- Mois écoulés + mois en cours → RÉEL : produits/charges opérationnels des
  transactions, mêmes règles d'exclusion que le P&L (kinds/catégories non
  opérationnels ignorés).
- Mois futurs → PRÉVISION :
  - incoming : encaissements ATTENDUS depuis les factures non payées
    (`status ∈ {forecast, due}`), bucketisés sur la **date de paiement attendue**
    (facture `due` → `due_date` ; facture `forecast` → fin du mois de service +
    délai de paiement du client), groupés par devise du client (montant EUR).
  - outgoing : charges prévisionnelles du mois (moyenne des mois écoulés),
    agrégat EUR → bucket unique « EUR ».

Un euro porte deux dates : le cashflow le compte quand il est ENCAISSÉ (à 45j),
là où le P&L le compte quand il est GAGNÉ (mois travaillé). L'écart est normal.

`is_forecast` = mois strictement postérieur au mois courant (today).
Tous les montants en `Decimal` 2 décimales.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from backend.db import models
from backend.logging_config import get_logger
from backend.services import forecast as forecast_service
from backend.services.fx import load_rates
from backend.services.pnl import (
    _EXCLUDED_CATEGORY_TYPES,
    _EXCLUDED_KINDS,
    invoice_revenue_eur,
)
from backend.services.treasury import eur_amount, q2

logger = get_logger("cashflow", channel="api")

_ZERO = Decimal("0")
_DEFAULT_TERMS = 60


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


def _expected_payment_date(inv: models.Invoice) -> Optional[date]:
    """
    Date d'encaissement ATTENDUE d'une facture non payée.

    - facture `due` (émise) → `due_date` (déjà = émission + délai client).
    - facture `forecast` (non émise) → dernier jour du mois de service +
      `client.payment_terms_days` (émission supposée en fin de mois travaillé).
    """
    if inv.due_date is not None:
        return inv.due_date
    if not inv.month:
        return None
    try:
        y, m = int(inv.month[:4]), int(inv.month[5:7])
    except (ValueError, IndexError):
        return None
    last_day = calendar.monthrange(y, m)[1]
    terms = _DEFAULT_TERMS
    if inv.client is not None and inv.client.payment_terms_days:
        terms = inv.client.payment_terms_days
    return date(y, m, last_day) + timedelta(days=terms)


def _expected_inflows(db: Session, year: int) -> dict[str, dict]:
    """
    Encaissements ATTENDUS par mois ('YYYY-MM') → {ccy: eur}.

    Factures non payées (`status ∈ {forecast, due}`) bucketisées sur leur date de
    paiement attendue (cf. `_expected_payment_date`), montant EUR groupé par devise
    du client. Les factures `paid` sont exclues (leur cash est déjà dans le réel).
    """
    rates = load_rates(db)
    out: dict[str, dict] = {}
    invoices = (
        db.query(models.Invoice)
        .filter(models.Invoice.status.in_(("forecast", "due")))
        .all()
    )
    for inv in invoices:
        pay_date = _expected_payment_date(inv)
        if pay_date is None or pay_date.year != year:
            continue
        key = f"{pay_date.year:04d}-{pay_date.month:02d}"
        ccy = (
            (inv.client.currency if inv.client else None) or inv.currency or "EUR"
        ).upper()
        bucket = out.setdefault(key, {})
        bucket[ccy] = bucket.get(ccy, _ZERO) + invoice_revenue_eur(inv, rates)
    return out


def monthly_cashflow(db: Session, year: int, today: Optional[date] = None) -> dict:
    """Encaissements/décaissements par mois et par devise pour l'exercice `year`."""
    if today is None:
        today = date.today()
    current = (today.year, today.month)

    real = _real_month_flows(db, year)
    forecast_in = _expected_inflows(db, year)
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
