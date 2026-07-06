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

import calendar
from dataclasses import dataclass
from datetime import date
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


@dataclass
class ForecastRow:
    """
    Vue « entrée de prévision » adossée à une facture `status='forecast'`.

    Porte le mode de facturation (`rate_unit` : 'day'/'hour'), les jours ET les
    heures (liés via h/jour du client), le montant natif et l'EUR (taux
    théorique). La donnée vit dans `invoices` (fusion, ADR-007).
    """

    id: int
    month: str
    client_id: int
    days: Decimal
    hours: Decimal
    rate: Decimal
    rate_unit: str
    amount: Decimal
    amount_eur: Decimal
    note: str
    client: Optional[models.Client] = None


def _forecast_number(month: str, client_id: int) -> str:
    """Numéro provisoire d'une facture prévisionnelle (unique par client × mois)."""
    return f"F-{client_id}-{month}"


def _to_row(inv: models.Invoice) -> ForecastRow:
    """Adapte une facture prévisionnelle en `ForecastRow`."""
    return ForecastRow(
        id=inv.id,
        month=inv.month,
        client_id=inv.client_id,
        days=inv.days,
        hours=inv.hours,
        rate=inv.rate,
        rate_unit=inv.rate_unit,
        amount=inv.amount,
        amount_eur=inv.amount_eur_forecast,
        note=inv.note,
        client=inv.client,
    )


def _q(value: Decimal) -> Decimal:
    """Quantifie un montant à 2 décimales (arrondi comptable)."""
    return Decimal(value).quantize(_CENTS)


def _months(year: int) -> list[str]:
    """Retourne les 12 clés mensuelles 'YYYY-01'..'YYYY-12'."""
    return [f"{year:04d}-{m:02d}" for m in range(1, 13)]


def get_inputs(db: Session, year: int) -> list[ForecastRow]:
    """
    Retourne les prévisions des 12 mois de `year` (factures `status='forecast'`).

    Forme historique (`ForecastRow`) pour compat route/cashflow.
    """
    months = _months(year)
    invoices = (
        db.query(models.Invoice)
        .filter(
            models.Invoice.status == "forecast",
            models.Invoice.month.in_(months),
        )
        .order_by(models.Invoice.month, models.Invoice.client_id)
        .all()
    )
    logger.info("📥 [Forecast] get_inputs: year=%d → %d ligne(s)", year, len(invoices))
    return [_to_row(inv) for inv in invoices]


def upsert_inputs(db: Session, items: Iterable[dict]) -> list[ForecastRow]:
    """
    Upsert des prévisions sur la clé (month, client_id) → factures `forecast`.

    Chaque item : {month, client_id, rate_unit:'day'|'hour', days?, hours?, rate, note}.
    - `rate_unit='day'` (TJM) : jours = source, heures = jours × h/j, montant = jours × taux.
    - `rate_unit='hour'` (THM) : heures = source (jours ⇄ heures liés), jours = heures ÷ h/j,
      montant = heures × taux.
    - EUR = montant × taux théorique (`fx_rates`) de la devise du client (ADR-006).
    Numéro provisoire `F-<client>-<month>`.
    """
    from backend.services.fx import load_rates, to_eur

    rates = load_rates(db)
    result: list[models.Invoice] = []
    for item in items:
        month = item["month"]
        client_id = item["client_id"]
        rate = Decimal(str(item.get("rate", 0)))
        note = item.get("note", "") or ""

        client = db.get(models.Client, client_id)
        hpd = Decimal(client.default_hours_per_day) if client else Decimal("8")
        if hpd <= 0:
            hpd = Decimal("8")
        currency = (client.currency if client else "EUR") or "EUR"
        rate_unit = (item.get("rate_unit") or (client.billing_mode if client else "day"))
        rate_unit = "hour" if rate_unit in ("hour", "thm") else "day"

        if rate_unit == "hour":
            hours = Decimal(str(item.get("hours", 0) or 0))
            days = (hours / hpd).quantize(_CENTS)
            amount = hours * rate
        else:
            days = Decimal(str(item.get("days", 0) or 0))
            hours = (days * hpd).quantize(_CENTS)
            amount = days * rate

        amount_eur = to_eur(amount, currency, rates)

        row = (
            db.query(models.Invoice)
            .filter(
                models.Invoice.status == "forecast",
                models.Invoice.month == month,
                models.Invoice.client_id == client_id,
            )
            .one_or_none()
        )
        values = {
            "days": _q(days),
            "hours_per_day": hpd,
            "hours": _q(hours),
            "rate": rate,
            "rate_unit": rate_unit,
            "currency": currency,
            "amount": _q(amount),
            "amount_eur_forecast": _q(amount_eur),
            "note": note,
        }
        if row is None:
            row = models.Invoice(
                number=_forecast_number(month, client_id),
                client_id=client_id,
                month=month,
                period_label=month,
                status="forecast",
                **values,
            )
            db.add(row)
        else:
            for field, value in values.items():
                setattr(row, field, value)
        result.append(row)

    db.commit()
    for row in result:
        db.refresh(row)
    logger.info("📤 [Forecast] upsert_inputs: %d prévision(s) ✅", len(result))
    return [_to_row(inv) for inv in result]


def reprice_client_forecasts(
    db: Session,
    client_id: int,
    *,
    apply: bool = False,
    today: Optional[date] = None,
) -> dict:
    """
    Recalcule les prévisions (`status='forecast'`) d'un client aux **taux et mode
    actuels de sa fiche**, à partir du mois en cours inclus (mois ≥ aujourd'hui).

    La **quantité de travail est préservée** : en THM on garde les heures comme
    source (jours = heures ÷ h/j), en TJM on garde les jours (heures = jours × h/j).
    Un changement de mode reporte donc l'effort d'une unité à l'autre via h/j.
    Montant natif = quantité_source × taux ; EUR = montant × taux théorique (fx_rates).

    `apply=False` → aperçu (ancien vs nouveau, aucune écriture).
    `apply=True`  → écrit les nouvelles valeurs et commit.

    Retourne : {from_month, count, currency, rate, rate_unit, rows[], total_old,
    total_new, total_old_eur, total_new_eur}.
    """
    from backend.services.fx import load_rates, to_eur

    today = today or date.today()
    from_month = today.strftime("%Y-%m")

    client = db.get(models.Client, client_id)
    if client is None:
        return _empty_reprice(from_month)

    rate = Decimal(client.tjh or 0)
    rate_unit = "hour" if (client.billing_mode or "tjm") in ("hour", "thm") else "day"
    hpd = Decimal(client.default_hours_per_day or 8)
    if hpd <= 0:
        hpd = Decimal("8")
    currency = (client.currency or "EUR") or "EUR"
    rates = load_rates(db)

    invoices = (
        db.query(models.Invoice)
        .filter(
            models.Invoice.status == "forecast",
            models.Invoice.client_id == client_id,
            models.Invoice.month >= from_month,
        )
        .order_by(models.Invoice.month)
        .all()
    )

    rows: list[dict] = []
    total_old = total_new = total_old_eur = total_new_eur = _ZERO
    for inv in invoices:
        if rate_unit == "hour":
            hours = Decimal(inv.hours or 0)  # heures = source préservée
            days = (hours / hpd).quantize(_CENTS)
            new_amount = hours * rate
            quantity, unit_label = hours, "h"
        else:
            days = Decimal(inv.days or 0)  # jours = source préservée
            hours = (days * hpd).quantize(_CENTS)
            new_amount = days * rate
            quantity, unit_label = days, "j"
        new_amount = _q(new_amount)
        new_amount_eur = _q(to_eur(new_amount, currency, rates))
        old_amount = Decimal(inv.amount or 0)
        old_amount_eur = Decimal(inv.amount_eur_forecast or 0)

        rows.append(
            {
                "month": inv.month,
                "quantity": quantity,
                "unit": unit_label,
                "old_amount": old_amount,
                "new_amount": new_amount,
                "old_amount_eur": old_amount_eur,
                "new_amount_eur": new_amount_eur,
            }
        )
        total_old += old_amount
        total_new += new_amount
        total_old_eur += old_amount_eur
        total_new_eur += new_amount_eur

        if apply:
            inv.rate = rate
            inv.rate_unit = rate_unit
            inv.hours_per_day = hpd
            inv.currency = currency
            inv.days = _q(days)
            inv.hours = _q(hours)
            inv.amount = new_amount
            inv.amount_eur_forecast = new_amount_eur

    if apply:
        db.commit()
        logger.info(
            "📤 [Forecast] reprice client=%d: %d prévision(s) recalculée(s) ✅",
            client_id,
            len(rows),
        )

    return {
        "from_month": from_month,
        "count": len(rows),
        "currency": currency,
        "rate": rate,
        "rate_unit": rate_unit,
        "rows": rows,
        "total_old": _q(total_old),
        "total_new": _q(total_new),
        "total_old_eur": _q(total_old_eur),
        "total_new_eur": _q(total_new_eur),
    }


def _empty_reprice(from_month: str) -> dict:
    """Aperçu vide (client absent / aucune prévision future)."""
    return {
        "from_month": from_month,
        "count": 0,
        "currency": "EUR",
        "rate": _ZERO,
        "rate_unit": "day",
        "rows": [],
        "total_old": _ZERO,
        "total_new": _ZERO,
        "total_old_eur": _ZERO,
        "total_new_eur": _ZERO,
    }


def _charges_by_date(db: Session, year: int) -> list[tuple[date, Decimal]]:
    """
    Charges opérationnelles réelles de `year` : liste (date, montant_eur_positif).

    Charge opérationnelle = transaction dont la catégorie est de type 'charge'
    et dont le `kind` n'est pas dans {investment, conversion, transfer}.
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
    out: list[tuple[date, Decimal]] = []
    for txn, _category in rows:
        if txn.booked_date.year != year:
            continue
        eur = to_eur(txn.amount, txn.currency, rates)  # taux théorique Réglages
        out.append((txn.booked_date, abs(eur)))
    return out


def _charge_forecast(
    db: Session, year: int, today: date
) -> tuple[dict[str, Decimal], set[str]]:
    """
    Calcule les charges par mois de `year` selon la position vs `today` :

    - mois écoulé (avant le mois courant) → charges RÉELLES du mois.
    - mois en cours → réel déjà passé (dates < today) + prorata des jours
      restants sur la moyenne mensuelle : moyenne × (jours restants / jours du mois).
    - mois futur → moyenne des mois écoulés = total charges réelles des mois
      écoulés / nombre de mois écoulés.

    Retourne un dict 'YYYY-MM' → {actual, forecast, is_forecast} :
    - actual   : charges réelles (montant déjà engagé).
    - forecast : charges prévisionnelles (prorata mois en cours / moyenne futur).
    - is_forecast : True dès qu'une composante prévisionnelle intervient.
    Le total du mois = actual + forecast.
    """
    rows = _charges_by_date(db, year)
    current = (today.year, today.month)

    actual_by_month: dict[str, Decimal] = {}
    current_before_today = _ZERO
    for d, eur in rows:
        key = d.isoformat()[:7]
        actual_by_month[key] = actual_by_month.get(key, _ZERO) + eur
        if (d.year, d.month) == current and d < today:
            current_before_today += eur

    # Moyenne = total réel des mois écoulés (strictement avant le mois courant)
    # de `year`, divisé par le nombre de mois écoulés.
    elapsed = [m for m in range(1, 13) if (year, m) < current]
    if elapsed:
        elapsed_total = sum(
            actual_by_month.get(f"{year:04d}-{m:02d}", _ZERO) for m in elapsed
        )
        avg = Decimal(elapsed_total) / Decimal(len(elapsed))
    else:
        avg = _ZERO

    out: dict[str, dict] = {}
    for m in range(1, 13):
        key = f"{year:04d}-{m:02d}"
        pos = (year, m)
        if pos < current:  # écoulé → 100 % réel
            out[key] = {
                "actual": actual_by_month.get(key, _ZERO),
                "forecast": _ZERO,
                "is_forecast": False,
            }
        elif pos == current:  # en cours → réel passé + prorata restant
            days_in_month = calendar.monthrange(year, m)[1]
            remaining = days_in_month - today.day + 1  # today inclus dans le reste
            prorata = avg * Decimal(remaining) / Decimal(days_in_month)
            out[key] = {
                "actual": current_before_today,
                "forecast": prorata,
                "is_forecast": True,
            }
        else:  # futur → 100 % prévision (moyenne)
            out[key] = {"actual": _ZERO, "forecast": avg, "is_forecast": True}
    return out


def project(
    db: Session,
    year: int,
    starting_cash_eur: Decimal = Decimal("0"),
    today: Optional[date] = None,
) -> dict:
    """
    Construit le déroulé de trésorerie projeté sur les 12 mois de `year`.

    - revenue_eur : somme (days × rate × fx_rate) des entrées du mois.
    - charges_eur : réel pour les mois écoulés, réel+prorata pour le mois en
      cours, moyenne des mois écoulés pour les mois futurs (cf. _charge_forecast).
    - net_eur : revenue - charges.
    - cumulative_cash_eur : trésorerie de départ + cumul des nets.
    - is_forecast : True si le mois comporte une composante prévisionnelle.
    """
    if today is None:
        today = date.today()

    inputs = get_inputs(db, year)
    revenue_by_month: dict[str, Decimal] = {}
    for row in inputs:
        revenue_by_month[row.month] = revenue_by_month.get(row.month, _ZERO) + Decimal(
            row.amount_eur
        )

    charges_by_month = _charge_forecast(db, year, today)

    starting = Decimal(str(starting_cash_eur))
    running = starting
    months_out: list[dict] = []
    total_revenue = _ZERO
    total_charges = _ZERO

    for month in _months(year):
        revenue = revenue_by_month.get(month, _ZERO)
        split = charges_by_month[month]
        charges = split["actual"] + split["forecast"]
        net = revenue - charges
        running = running + net
        total_revenue += revenue
        total_charges += charges
        months_out.append(
            {
                "month": month,
                "revenue_eur": _q(revenue),
                "charges_eur": _q(charges),
                "charges_actual_eur": _q(split["actual"]),
                "charges_forecast_eur": _q(split["forecast"]),
                "net_eur": _q(net),
                "cumulative_cash_eur": _q(running),
                "is_forecast": split["is_forecast"],
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
    db: Session,
    year: int,
    base_override: Optional[Decimal] = None,
    today: Optional[date] = None,
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
        projection = project(db, year, today=today)
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
