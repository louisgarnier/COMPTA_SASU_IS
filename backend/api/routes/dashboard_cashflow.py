"""
Route Dashboard Cashflow — encaissements/décaissements mensuels par devise.

- GET /api/dashboard/cashflow?year=2026
    → { year, months:[{month, incoming_by_ccy, outgoing_by_ccy,
        incoming_eur, outgoing_eur, is_forecast}], totals:{...} }

Passé/mois en cours = réel ; futur = prévision. Montants en `Decimal`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.db.base import get_db
from backend.logging_config import get_logger
from backend.services import cashflow as cashflow_service

logger = get_logger("dashboard_cashflow", channel="api")

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/cashflow")
def get_cashflow(
    year: int = Query(...),
    scope: str = Query(default="forecast", pattern="^(realized|engaged|forecast)$"),
    db: Session = Depends(get_db),
) -> dict:
    """Flux mensuels par devise — `scope` = niveau de certitude du dashboard."""
    logger.info("📥 [Cashflow] get: year=%d scope=%s", year, scope)
    return cashflow_service.monthly_cashflow(db, year, scope=scope)
