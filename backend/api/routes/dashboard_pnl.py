"""
Route Dashboard — résumé P&L (équation façon FreeAgent).

- GET /api/dashboard/pnl-summary?year=2026
    → Revenus, Charges, Résultat, IS estimé, Résultat net, Report à nouveau,
      Distribuable, et ventilation par devise.

Tous les montants en `Decimal` (jamais float).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.db.base import get_db
from backend.logging_config import get_logger
from backend.services import pnl as pnl_service

logger = get_logger("dashboard_pnl", channel="api")

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/pnl-summary")
def get_pnl_summary(
    year: int = Query(...),
    db: Session = Depends(get_db),
) -> dict:
    """Retourne le résumé P&L (équation) pour l'exercice `year`."""
    logger.info("📥 [Dashboard] pnl-summary: year=%d", year)
    return pnl_service.summary(db, year)
