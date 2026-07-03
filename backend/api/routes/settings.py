"""
Routes Paramètres société (table singleton `settings`, id=1).

- GET  /api/settings → retourne la ligne unique (la crée avec les valeurs par
  défaut du modèle si elle n'existe pas encore).
- PUT  /api/settings → met à jour les champs fournis et retourne la ligne.

Montants et taux manipulés en `Decimal` (jamais float).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from backend.db import models
from backend.db.base import get_db
from backend.logging_config import get_logger

logger = get_logger("settings", channel="api")

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsOut(BaseModel):
    """Représentation renvoyée d'un enregistrement Settings."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    company_name: str
    siret: str
    naf: str
    tva_intracom: str
    address: str
    is_low_rate: Decimal
    is_threshold: Decimal
    is_high_rate: Decimal
    retained_earnings_eur: Decimal
    next_invoice_number: int
    default_fx_usd: Decimal
    default_fx_cad: Decimal


class SettingsUpdate(BaseModel):
    """Champs modifiables (tous optionnels — mise à jour partielle)."""

    company_name: Optional[str] = None
    siret: Optional[str] = None
    naf: Optional[str] = None
    tva_intracom: Optional[str] = None
    address: Optional[str] = None
    is_low_rate: Optional[Decimal] = None
    is_threshold: Optional[Decimal] = None
    is_high_rate: Optional[Decimal] = None
    retained_earnings_eur: Optional[Decimal] = None
    next_invoice_number: Optional[int] = None
    default_fx_usd: Optional[Decimal] = None
    default_fx_cad: Optional[Decimal] = None


def _get_or_create_singleton(db: Session) -> models.Settings:
    """Retourne la ligne id=1, en la créant avec les défauts si absente."""
    row = db.get(models.Settings, 1)
    if row is None:
        row = models.Settings(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)
        logger.info("🗄️ [Settings] create: singleton id=1 initialisé")
    return row


@router.get("", response_model=SettingsOut)
def get_settings(db: Session = Depends(get_db)) -> models.Settings:
    """Retourne les paramètres société (crée la ligne si nécessaire)."""
    logger.info("📥 [Settings] get: singleton")
    return _get_or_create_singleton(db)


@router.put("", response_model=SettingsOut)
def update_settings(
    payload: SettingsUpdate, db: Session = Depends(get_db)
) -> models.Settings:
    """Met à jour les champs fournis du singleton et le retourne."""
    row = _get_or_create_singleton(db)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    logger.info("📤 [Settings] update: %d champ(s) ✅", len(changes))
    return row
