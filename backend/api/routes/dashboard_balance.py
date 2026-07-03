"""
Route Dashboard — Balance timeline.

- GET /api/dashboard/balance-timeline?year=YYYY
    → solde de trésorerie mensuel cumulé en EUR : passé reconstruit
      (opening + mouvements), futur projeté via la prévision.

Montants en `Decimal` (jamais float).
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db.base import get_db
from backend.logging_config import get_logger
from backend.services.treasury import balance_timeline

logger = get_logger("dashboard_routes", channel="api")

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


class MonthBalance(BaseModel):
    """Solde EUR de fin de mois (réel reconstruit ou projeté)."""

    month: str
    balance_eur: Decimal
    is_forecast: bool


class BalanceTimelineOut(BaseModel):
    """Déroulé mensuel du solde de trésorerie cumulé (EUR)."""

    year: int
    months: list[MonthBalance]
    current_balance_eur: Decimal
    projected_year_end_eur: Decimal


@router.get("/balance-timeline", response_model=BalanceTimelineOut)
def get_balance_timeline(
    year: int = Query(default=2026, ge=2000, le=2100),
    db: Session = Depends(get_db),
) -> dict:
    """Retourne le solde de trésorerie mensuel cumulé de l'exercice `year`."""
    logger.info("📥 [Dashboard] GET /api/dashboard/balance-timeline?year=%s", year)
    return balance_timeline(db, year)
