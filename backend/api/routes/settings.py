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
from pydantic import BaseModel, ConfigDict, Field
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
    email: str
    capital_eur: Decimal
    bank_name: str
    bank_bic: str
    bank_address: str
    is_low_rate: Decimal
    is_threshold: Decimal
    is_high_rate: Decimal
    retained_earnings_eur: Decimal
    is_start_year: Optional[int]
    invoice_legal_mention: Optional[str] = None
    next_invoice_number: int


class SettingsUpdate(BaseModel):
    """Champs modifiables (tous optionnels — mise à jour partielle), avec bornes métier.

    Note : les anciennes colonnes `default_fx_usd/cad` ont été supprimées du modèle —
    la source unique des taux de change est la table `fx_rates` (voir /api/fx-rates).
    """

    company_name: Optional[str] = None
    siret: Optional[str] = Field(default=None, pattern=r"^(\d{14})?$")  # vide ou 14 chiffres
    naf: Optional[str] = None
    tva_intracom: Optional[str] = None
    address: Optional[str] = None
    email: Optional[str] = None
    capital_eur: Optional[Decimal] = Field(default=None, ge=0)
    bank_name: Optional[str] = None
    bank_bic: Optional[str] = None
    bank_address: Optional[str] = None
    is_low_rate: Optional[Decimal] = Field(default=None, ge=0, le=1)  # taux ∈ [0,1]
    is_threshold: Optional[Decimal] = Field(default=None, ge=0)
    is_high_rate: Optional[Decimal] = Field(default=None, ge=0, le=1)
    retained_earnings_eur: Optional[Decimal] = None  # peut être négatif (report déficitaire)
    invoice_legal_mention: Optional[str] = None
    is_start_year: Optional[int] = Field(default=None, ge=2000, le=2100)
    next_invoice_number: Optional[int] = Field(default=None, ge=1)


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
