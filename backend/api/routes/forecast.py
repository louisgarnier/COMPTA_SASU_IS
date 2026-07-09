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
from pydantic import BaseModel, Field as PydField, ConfigDict
from sqlalchemy.orm import Session

from backend.db.base import get_db
from backend.logging_config import get_logger
from backend.services import forecast as forecast_service

logger = get_logger("forecast", channel="api")

router = APIRouter(prefix="/api/forecast", tags=["forecast"])


class ForecastInputOut(BaseModel):
    """Entrée de prévision renvoyée (facturation TJM/THM)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    month: str = PydField(pattern=r"^\d{4}-\d{2}$")
    client_id: int
    days: Decimal
    hours: Decimal
    rate: Decimal
    rate_unit: str
    amount: Decimal
    amount_eur: Decimal
    note: str
    status: str = "forecast"
    number: str = ""


class ForecastInputIn(BaseModel):
    """
    Entrée de prévision fournie (upsert sur month + client_id).

    `rate_unit='day'` → `days` pilote ; `rate_unit='hour'` → `hours` pilote.
    Le FX vient des Réglages (taux théorique), plus de fx_rate saisi.
    """

    month: str = PydField(pattern=r"^\d{4}-\d{2}$")
    client_id: int
    rate_unit: str = "day"
    days: Decimal = Decimal("0")
    hours: Decimal = Decimal("0")
    rate: Decimal = Decimal("0")
    note: str = ""


class ForecastUpsert(BaseModel):
    """Payload PUT : année + liste d'entrées à upserter."""

    year: int
    inputs: list[ForecastInputIn] = []
    starting_cash_eur: Decimal = Decimal("0")
    issue: bool = False  # mode « créer une facture dans le passé »


def _build_response(
    db: Session,
    year: int,
    starting_cash_eur: Decimal,
    include_issued: bool = False,
) -> dict:
    """Assemble la réponse commune GET/PUT : inputs + projection + IS."""
    inputs = forecast_service.get_inputs(db, year, include_issued=include_issued)
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
    include_issued: bool = Query(False),
    db: Session = Depends(get_db),
) -> dict:
    """Retourne les entrées, la projection et l'estimation IS pour `year`."""
    logger.info("📥 [Forecast] get: year=%d issued=%s", year, include_issued)
    return _build_response(db, year, starting_cash_eur, include_issued=include_issued)


@router.put("")
def put_forecast(payload: ForecastUpsert, db: Session = Depends(get_db)) -> dict:
    """Upsert les entrées fournies puis retourne la même forme que GET.

    `issue=True` émet directement en `due` les entrées des mois passés (mode
    « créer une facture dans le passé ») ; la réponse inclut alors les factures
    émises pour que la grille les reflète.
    """
    logger.info(
        "📥 [Forecast] put: year=%d (%d entrée(s), issue=%s)",
        payload.year, len(payload.inputs), payload.issue,
    )
    forecast_service.upsert_inputs(
        db, [item.model_dump() for item in payload.inputs], issue=payload.issue
    )
    return _build_response(
        db, payload.year, payload.starting_cash_eur, include_issued=payload.issue
    )


@router.delete("/{client_id}/{month}", status_code=204)
def delete_forecast_input(
    client_id: int, month: str, db: Session = Depends(get_db)
):
    """Supprime la prévision d'un client pour un mois (facture `forecast`)."""
    logger.info("📥 [Forecast] delete: client=%d mois=%s", client_id, month)
    forecast_service.delete_input(db, client_id, month)
