"""
Service prévision (forecast) LGC — projection de trésorerie & estimation IS.

- Entrées mensuelles : jours × TJH × fx par client (table `forecast_inputs`).
- Projection : revenu projeté par mois, charges opérationnelles moyennes,
  déroulé de trésorerie cumulée.
- Estimation IS : base imposable = résultat projeté + plus-values latentes
  positives sur placements, barème à deux taux (Settings).

Tous les montants sont manipulés en `Decimal`, jamais en float.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from backend.db import models
from backend.logging_config import get_logger

logger = get_logger("forecast", channel="backend")

_CENTS = Decimal("0.01")
_ZERO = Decimal("0")

# Types de mouvements exclus des charges opérationnelles.
_EXCLUDED_KINDS = {"investment", "conversion", "transfer"}


def _q(value: Decimal) -> Decimal:
    """Quantifie un montant à 2 décimales (arrondi comptable)."""
    return Decimal(value).quantize(_CENTS)


def _months(year: int) -> list[str]:
    """Retourne les 12 clés mensuelles 'YYYY-01'..'YYYY-12'."""
    return [f"{year:04d}-{m:02d}" for m in range(1, 13)]


def get_inputs(db: Session, year: int) -> list[models.ForecastInput]:
    """Retourne les entrées de prévision des 12 mois de `year`, triées."""
    months = _months(year)
    rows = (
        db.query(models.ForecastInput)
        .filter(models.ForecastInput.month.in_(months))
        .order_by(models.ForecastInput.month, models.ForecastInput.client_id)
        .all()
    )
    logger.info("📥 [Forecast] get_inputs: year=%d → %d ligne(s)", year, len(rows))
    return rows


def upsert_inputs(db: Session, items: Iterable[dict]) -> list[models.ForecastInput]:
    """
    Upsert des entrées de prévision sur la clé (month, client_id).

    Chaque item : {month:'YYYY-MM', client_id, days, rate, fx_rate, note}.
    Retourne les lignes persistées (créées ou mises à jour).
    """
    result: list[models.ForecastInput] = []
    for item in items:
        month = item["month"]
        client_id = item["client_id"]
        row = (
            db.query(models.ForecastInput)
            .filter(
                models.ForecastInput.month == month,
                models.ForecastInput.client_id == client_id,
            )
            .one_or_none()
        )
        values = {
            "days": Decimal(str(item.get("days", 0))),
            "rate": Decimal(str(item.get("rate", 0))),
            "fx_rate": Decimal(str(item.get("fx_rate", 1))),
            "note": item.get("note", "") or "",
        }
        if row is None:
            row = models.ForecastInput(month=month, client_id=client_id, **values)
            db.add(row)
        else:
            for field, value in values.items():
                setattr(row, field, value)
        result.append(row)

    db.commit()
    for row in result:
        db.refresh(row)
    logger.info("📤 [Forecast] upsert_inputs: %d ligne(s) ✅", len(result))
    return result


def _avg_monthly_charges(db: Session, year: int) -> Decimal:
    """
    Moyenne des charges opérationnelles mensuelles sur les mois disposant de
    données cette année.

    Charge opérationnelle = transaction dont la catégorie est de type 'charge'
    et dont le `kind` n'est pas dans {investment, conversion, transfer}.
    Retourne un montant positif (à retrancher), 0 si aucune donnée.
    """
    rows = (
        db.query(models.Transaction, models.Category)
        .join(models.Category, models.Transaction.category_id == models.Category.id)
        .filter(
            models.Category.type == "charge",
            ~models.Transaction.kind.in_(_EXCLUDED_KINDS),
            models.Transaction.booked_date.isnot(None),
        )
        .all()
    )

    from backend.services.fx import load_rates, to_eur

    rates = load_rates(db)
    per_month: dict[str, Decimal] = {}
    prefix = f"{year:04d}-"
    for txn, _category in rows:
        key = txn.booked_date.isoformat()[:7]  # 'YYYY-MM'
        if not key.startswith(prefix):
            continue
        eur = to_eur(txn.amount, txn.currency, rates)  # taux théorique Réglages
        per_month[key] = per_month.get(key, _ZERO) + abs(eur)

    if not per_month:
        return _ZERO

    total = sum(per_month.values(), _ZERO)
    return Decimal(total) / Decimal(len(per_month))


def project(
    db: Session, year: int, starting_cash_eur: Decimal = Decimal("0")
) -> dict:
    """
    Construit le déroulé de trésorerie projeté sur les 12 mois de `year`.

    - revenue_eur : somme (days × rate × fx_rate) des entrées du mois.
    - charges_eur : charges opérationnelles mensuelles moyennes (constantes).
    - net_eur : revenue - charges.
    - cumulative_cash_eur : trésorerie de départ + cumul des nets.
    """
    inputs = get_inputs(db, year)
    revenue_by_month: dict[str, Decimal] = {}
    for row in inputs:
        amount = Decimal(row.days) * Decimal(row.rate) * Decimal(row.fx_rate)
        revenue_by_month[row.month] = revenue_by_month.get(row.month, _ZERO) + amount

    avg_charges = _avg_monthly_charges(db, year)

    starting = Decimal(str(starting_cash_eur))
    running = starting
    months_out: list[dict] = []
    total_revenue = _ZERO
    total_charges = _ZERO

    for month in _months(year):
        revenue = revenue_by_month.get(month, _ZERO)
        charges = avg_charges
        net = revenue - charges
        running = running + net
        total_revenue += revenue
        total_charges += charges
        months_out.append(
            {
                "month": month,
                "revenue_eur": _q(revenue),
                "charges_eur": _q(charges),
                "net_eur": _q(net),
                "cumulative_cash_eur": _q(running),
            }
        )

    logger.info(
        "📤 [Forecast] project: year=%d revenu=%s charges=%s ✅",
        year,
        _q(total_revenue),
        _q(total_charges),
    )
    return {
        "year": year,
        "months": months_out,
        "totals": {
            "revenue_eur": _q(total_revenue),
            "charges_eur": _q(total_charges),
        },
    }


def _investment_gain(db: Session) -> Decimal:
    """Somme des plus-values latentes positives sur placements (EUR)."""
    gain = _ZERO
    for inv in db.query(models.Investment).all():
        delta = Decimal(inv.current_value_eur) - Decimal(inv.opening_value_eur)
        if delta > 0:
            gain += delta
    return gain


def _get_settings(db: Session) -> models.Settings:
    """Retourne le singleton Settings (le crée avec les défauts si absent)."""
    row = db.get(models.Settings, 1)
    if row is None:
        row = models.Settings(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def estimate_is(
    db: Session, year: int, base_override: Optional[Decimal] = None
) -> dict:
    """
    Estime l'impôt sur les sociétés (IS) pour `year`.

    Base imposable = (revenu projeté annuel - charges projetées annuelles)
    + plus-values latentes positives sur placements. Si `base_override` est
    fourni, il remplace la base calculée.

    Barème (Settings) : is_low_rate jusqu'à is_threshold, is_high_rate au-delà.
    """
    settings = _get_settings(db)

    if base_override is not None:
        base = Decimal(str(base_override))
    else:
        projection = project(db, year)
        result = projection["totals"]["revenue_eur"] - projection["totals"]["charges_eur"]
        base = result + _investment_gain(db)

    threshold = Decimal(settings.is_threshold)
    low_rate = Decimal(settings.is_low_rate)
    high_rate = Decimal(settings.is_high_rate)

    low_part = min(base, threshold) if base > 0 else _ZERO
    high_part = max(_ZERO, base - threshold)

    is_low = low_part * low_rate
    is_high = high_part * high_rate
    is_total = is_low + is_high

    logger.info(
        "📤 [Forecast] estimate_is: year=%d base=%s total=%s ✅",
        year,
        _q(base),
        _q(is_total),
    )
    return {
        "base_eur": _q(base),
        "threshold_eur": _q(threshold),
        "low_rate": low_rate,
        "high_rate": high_rate,
        "is_low_eur": _q(is_low),
        "is_high_eur": _q(is_high),
        "is_total_eur": _q(is_total),
    }
