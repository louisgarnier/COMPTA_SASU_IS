"""
Route Dashboard — Invoice Timeline.

- GET /api/dashboard/invoice-timeline → montants mensuels empilés
  (payé / dû / en retard) + liste des factures ouvertes (non payées).

La logique métier vit dans `services.invoices.timeline` ; cette route ne fait
qu'orchestrer. Montants en `Decimal`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.db.base import get_db
from backend.logging_config import get_logger
from backend.services import invoices as invoices_service

logger = get_logger("dashboard", channel="api")

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/invoice-timeline")
def invoice_timeline(db: Session = Depends(get_db)) -> dict:
    """Retourne la timeline de facturation (buckets mensuels + factures ouvertes)."""
    logger.info("📥 [Dashboard] invoice-timeline")
    result = invoices_service.timeline(db)
    logger.info(
        "📤 [Dashboard] invoice-timeline: outstanding=%s open=%d ✅",
        result["outstanding_eur"], result["open_count"],
    )
    return result
