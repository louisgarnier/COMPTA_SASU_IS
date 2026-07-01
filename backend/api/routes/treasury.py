"""
Routes Trésorerie & Compte de résultat LGC.

- GET /api/treasury      → consolidation multi-comptes + placements (équiv. EUR).
- GET /api/pnl?year=YYYY → compte de résultat mensuel (année 2026 par défaut).

Le routeur n'a pas de préfixe : chaque route porte son chemin complet, afin
d'exposer exactement /api/treasury et /api/pnl.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db.base import get_db
from backend.logging_config import get_logger
from backend.services.pnl import monthly_pnl
from backend.services.treasury import consolidated_treasury

logger = get_logger("treasury_routes", channel="api")

router = APIRouter(tags=["treasury"])


# --- Schémas Trésorerie ---------------------------------------------------


class AccountOut(BaseModel):
    """Solde consolidé d'un compte bancaire."""

    account_uid: str
    name: str
    provider: str
    currency: str
    balance: Decimal


class TreasuryOut(BaseModel):
    """Trésorerie consolidée : comptes + équivalents EUR + placements."""

    accounts: list[AccountOut]
    bank_total_eur: Decimal
    investments_total_eur: Decimal
    total_eur: Decimal


# --- Schémas P&L ----------------------------------------------------------


class MonthPnl(BaseModel):
    """Ligne mensuelle du compte de résultat."""

    month: str
    revenue_eur: Decimal
    charges_eur: Decimal
    result_eur: Decimal


class PnlTotals(BaseModel):
    """Totaux annuels du compte de résultat."""

    revenue_eur: Decimal
    charges_eur: Decimal
    result_eur: Decimal


class PnlOut(BaseModel):
    """Compte de résultat mensuel d'un exercice."""

    year: int
    months: list[MonthPnl]
    totals: PnlTotals


# --- Routes ---------------------------------------------------------------


@router.get("/api/treasury", response_model=TreasuryOut)
def get_treasury(db: Session = Depends(get_db)) -> dict:
    """Retourne la trésorerie consolidée (tous comptes + placements)."""
    logger.info("📥 [Treasury] GET /api/treasury")
    return consolidated_treasury(db)


@router.get("/api/pnl", response_model=PnlOut)
def get_pnl(
    year: int = Query(default=2026, ge=2000, le=2100),
    db: Session = Depends(get_db),
) -> dict:
    """Retourne le compte de résultat mensuel de l'exercice demandé."""
    logger.info("📥 [PnL] GET /api/pnl?year=%s", year)
    return monthly_pnl(db, year)
