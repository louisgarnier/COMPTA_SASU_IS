"""
Routes Taux de change (FX) LGC.

Les devises listées = celles réellement présentes dans les transactions/comptes
(hors EUR). Chaque devise a un taux théorique éditable → EUR. Une devise en usage
sans taux est signalée `missing` (« à renseigner »).

- GET /api/fx-rates → liste { currency, rate, missing } des devises en usage
- PUT /api/fx-rates → met à jour/insère les taux fournis
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db import models
from backend.db.base import get_db
from backend.logging_config import get_logger
from backend.services.fx import rates_view

logger = get_logger("fx_routes", channel="api")

router = APIRouter(prefix="/api/fx-rates", tags=["fx"])


class FxRateOut(BaseModel):
    currency: str
    rate: Decimal
    missing: bool


class FxRateIn(BaseModel):
    currency: str
    rate: Decimal


class FxRatesUpdate(BaseModel):
    rates: list[FxRateIn]


@router.get("", response_model=list[FxRateOut])
def get_rates(db: Session = Depends(get_db)) -> list[dict]:
    """Taux des devises en usage (avec flag `missing`)."""
    logger.info("📥 [Fx] GET /api/fx-rates")
    return rates_view(db)


@router.put("", response_model=list[FxRateOut])
def put_rates(payload: FxRatesUpdate, db: Session = Depends(get_db)) -> list[dict]:
    """Upsert des taux fournis (EUR ignoré : toujours 1)."""
    for item in payload.rates:
        cur = item.currency.upper()
        if cur == "EUR":
            continue
        row = db.get(models.FxRate, cur)
        if row is None:
            db.add(models.FxRate(currency=cur, rate=Decimal(item.rate)))
        else:
            row.rate = Decimal(item.rate)
    db.commit()
    logger.info("📤 [Fx] PUT /api/fx-rates: %d taux mis à jour ✅", len(payload.rates))
    return rates_view(db)
