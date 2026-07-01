"""
Service FX LGC — taux de change théoriques (source unique de conversion EUR).

Modèle : tout reste en devise native ; **seuls les agrégats EUR** (total tréso,
P&L, IS) appliquent un taux théorique éditable dans les Réglages. EUR = 1.
Les devises à régler = celles réellement présentes dans les transactions/comptes ;
une devise en usage sans taux est signalée « manquante » (fallback = 1).
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from backend.db import models
from backend.logging_config import get_logger

logger = get_logger("fx", channel="api")

_ONE = Decimal("1")

# Taux d'amorçage raisonnables (éditables ensuite dans les Réglages).
_DEFAULT_SEED = {"USD": Decimal("0.92"), "CAD": Decimal("0.68")}


def load_rates(db: Session) -> dict[str, Decimal]:
    """Charge tous les taux en mémoire : {devise: taux}. EUR toujours = 1."""
    rates: dict[str, Decimal] = {"EUR": _ONE}
    for r in db.query(models.FxRate).all():
        rates[(r.currency or "").upper()] = Decimal(r.rate)
    return rates


def rate_for(rates: dict[str, Decimal], currency: str) -> Decimal:
    """Taux devise → EUR depuis la map (EUR=1 ; inconnu → 1, à régler)."""
    cur = (currency or "EUR").upper()
    if cur == "EUR":
        return _ONE
    return rates.get(cur, _ONE)


def to_eur(amount, currency: str, rates: dict[str, Decimal]) -> Decimal:
    """Convertit un montant natif en EUR via le taux théorique."""
    return Decimal(amount or 0) * rate_for(rates, currency)


def currencies_in_use(db: Session) -> list[str]:
    """Devises distinctes présentes dans les transactions et comptes (hors EUR)."""
    found: set[str] = set()
    for (c,) in db.query(models.Transaction.currency).distinct():
        if c:
            found.add(c.upper())
    for (c,) in db.query(models.BankAccount.currency).distinct():
        if c:
            found.add(c.upper())
    found.discard("EUR")
    return sorted(found)


def ensure_seed_rates(db: Session) -> None:
    """Amorce les taux par défaut (USD/CAD) s'ils n'existent pas encore."""
    existing = {r.currency.upper() for r in db.query(models.FxRate).all()}
    for cur, val in _DEFAULT_SEED.items():
        if cur not in existing:
            db.add(models.FxRate(currency=cur, rate=val))
    db.commit()


def rates_view(db: Session) -> list[dict]:
    """
    Vue pour les Réglages : une entrée par devise EN USAGE (hors EUR), avec son
    taux s'il existe, et un flag `missing` si aucun taux n'est renseigné.
    """
    rates = load_rates(db)
    out = []
    for cur in currencies_in_use(db):
        has = cur in rates
        out.append(
            {
                "currency": cur,
                "rate": rates.get(cur, _ONE),
                "missing": not has,
            }
        )
    return out
