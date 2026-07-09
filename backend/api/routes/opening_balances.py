"""
Routes Soldes d'ouverture d'exercice.

- GET  /api/opening-balances/years        → exercices disponibles (sélecteur).
- GET  /api/opening-balances?year=YYYY     → une ligne par compte + tie-out.
- PUT  /api/opening-balances?year=YYYY     → upsert des soldes saisis.

Aucune valeur en dur : les soldes sont saisis par l'utilisateur et vivent en base.
Montants en `Decimal` (jamais float).
"""

from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.db.base import get_db
from backend.logging_config import get_logger
from backend.services import openings as openings_service

logger = get_logger("opening_balances", channel="api")

router = APIRouter(prefix="/api/opening-balances", tags=["opening-balances"])


class OpeningItem(BaseModel):
    """Une saisie de solde d'ouverture pour un compte."""

    account_uid: str
    balance: Decimal


class OpeningsUpdate(BaseModel):
    """Payload d'upsert : la liste des soldes saisis pour l'exercice."""

    items: list[OpeningItem] = Field(default_factory=list)


def _current_year() -> int:
    return date_type.today().year


@router.get("/years")
def get_years(db: Session = Depends(get_db)) -> dict:
    """Exercices disponibles pour le sélecteur (saisis + exercice courant)."""
    logger.info("📥 [Openings] get years")
    return {"years": openings_service.list_years(db)}


@router.get("")
def get_openings(
    year: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """Soldes d'ouverture de l'exercice + contrôle vs mouvements + tie-out."""
    y = year if year is not None else _current_year()
    logger.info("📥 [Openings] get: exercice=%d", y)
    return openings_service.get_openings(db, y)


@router.put("")
def put_openings(
    payload: OpeningsUpdate,
    year: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """Upsert des soldes d'ouverture de l'exercice et retourne la vue à jour."""
    y = year if year is not None else _current_year()
    items = [it.model_dump() for it in payload.items]
    logger.info("📥 [Openings] put: exercice=%d, %d saisie(s)", y, len(items))
    return openings_service.set_openings(db, y, items)
