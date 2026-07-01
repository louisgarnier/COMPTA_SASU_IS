"""
Routes Prévision (forecast) — projection de trésorerie & estimation IS.

- GET /api/forecast?year=2026&starting_cash_eur=...
    → { inputs:[...], projection:{...}, is:{...} }
- PUT /api/forecast
    body { year, inputs:[{month, client_id, days, rate, fx_rate, note}] }
    → upsert des entrées puis même forme que GET.

Tous les montants en `Decimal` (jamais float).
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from backend.db.base import get_db
from backend.logging_config import get_logger
from backend.services import forecast as forecast_service

logger = get_logger("forecast", channel="api")

router = APIRouter(prefix="/api/forecast", tags=["forecast"])


class ForecastInputOut(BaseModel):
    """Entrée de prévision renvoyée."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    month: str
    client_id: int
    days: Decimal
    rate: Decimal
    fx_rate: Decimal
    note: str


class ForecastInputIn(BaseModel):
    """Entrée de prévision fournie (upsert sur month + client_id)."""

    month: str
    client_id: int
    days: Decimal = Decimal("0")
    rate: Decimal = Decimal("0")
    fx_rate: Decimal = Decimal("1")
    note: str = ""


class ForecastUpsert(BaseModel):
    """Payload PUT : année + liste d'entrées à upserter."""

    year: int
    inputs: list[ForecastInputIn] = []
    starting_cash_eur: Decimal = Decimal("0")


def _build_response(db: Session, year: int, starting_cash_eur: Decimal) -> dict:
    """Assemble la réponse commune GET/PUT : inputs + projection + IS."""
    inputs = forecast_service.get_inputs(db, year)
    projection = forecast_service.project(db, year, starting_cash_eur=starting_cash_eur)
    is_estimate = forecast_service.estimate_is(db, year)
    return {
        "inputs": [ForecastInputOut.model_validate(row) for row in inputs],
        "projection": projection,
        "is": is_estimate,
    }


@router.get("")
def get_forecast(
    year: int = Query(...),
    starting_cash_eur: Decimal = Query(Decimal("0")),
    db: Session = Depends(get_db),
) -> dict:
    """Retourne les entrées, la projection et l'estimation IS pour `year`."""
    logger.info("📥 [Forecast] get: year=%d", year)
    return _build_response(db, year, starting_cash_eur)


@router.put("")
def put_forecast(payload: ForecastUpsert, db: Session = Depends(get_db)) -> dict:
    """Upsert les entrées fournies puis retourne la même forme que GET."""
    logger.info(
        "📥 [Forecast] put: year=%d (%d entrée(s))", payload.year, len(payload.inputs)
    )
    forecast_service.upsert_inputs(
        db, [item.model_dump() for item in payload.inputs]
    )
    return _build_response(db, payload.year, payload.starting_cash_eur)
