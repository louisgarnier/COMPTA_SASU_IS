"""
Route dashboard « D'où vient ma trésorerie ? » (pont ouverture → banque).

- GET /api/dashboard/treasury-bridge?year=YYYY → treasury.treasury_bridge.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.api.query_utils import parse_as_of
from backend.db.base import get_db
from backend.logging_config import get_logger
from backend.services.treasury import treasury_bridge

logger = get_logger("dashboard_bridge", channel="api")

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/treasury-bridge")
def get_treasury_bridge(
    as_of: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """Pont de trésorerie à la date `as_of` (défaut : aujourd'hui) — datetime tolérée."""
    parsed = parse_as_of(as_of)
    logger.info("📥 [Bridge] get: as_of=%s", parsed or "aujourd'hui")
    return treasury_bridge(db, as_of=parsed)
