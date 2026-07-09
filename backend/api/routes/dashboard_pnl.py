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


@router.get("/pnl-detail")
def get_pnl_detail(
    year: int = Query(...),
    db: Session = Depends(get_db),
) -> dict:
    """Détail annuel (clôture) : mensuel + charges par catégorie × mois."""
    logger.info("📥 [Dashboard] pnl-detail: year=%d", year)
    return pnl_service.annual_detail(db, year)


@router.get("/pnl-summary")
def get_pnl_summary(
    year: int = Query(...),
    scope: str = Query(default="engaged", pattern="^(realized|engaged|forecast)$"),
    db: Session = Depends(get_db),
) -> dict:
    """Résumé P&L de l'exercice — `scope` = niveau de certitude du dashboard."""
    logger.info("📥 [Dashboard] pnl-summary: year=%d scope=%s", year, scope)
    return pnl_service.summary(db, year, scope=scope)
