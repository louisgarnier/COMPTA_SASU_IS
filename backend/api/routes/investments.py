"""
Routes Placements (table `investments`, exposée sous /api/manual-assets).

- GET    /api/manual-assets          → liste des placements.
- POST   /api/manual-assets          → création.
- GET    /api/manual-assets/summary  → totaux ouverture / courant + plus-value.
- PATCH  /api/manual-assets/{id}     → mise à jour partielle (404 si absent).
- DELETE /api/manual-assets/{id}     → suppression (404 si absent).

Les apports de l'année (kind='investment') proviennent des transactions et ne
sont pas gérés ici. Toutes les valeurs monétaires sont des `Decimal`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from backend.db import models
from backend.db.base import get_db
from backend.logging_config import get_logger

logger = get_logger("investments", channel="api")

router = APIRouter(prefix="/api/manual-assets", tags=["investments"])


class InvestmentOut(BaseModel):
    """Représentation renvoyée d'un placement."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    type: str
    currency: str
    opening_value: Decimal
    opening_value_eur: Decimal
    current_value: Decimal
    current_value_eur: Decimal
    as_of_date: Optional[date] = None
    note: str


class InvestmentCreate(BaseModel):
    """Payload de création d'un placement."""

    label: str
    type: str
    currency: str = "EUR"
    opening_value: Decimal = Decimal("0")
    opening_value_eur: Decimal = Decimal("0")
    current_value: Decimal = Decimal("0")
    current_value_eur: Decimal = Decimal("0")
    as_of_date: Optional[date] = None
    note: str = ""


class InvestmentUpdate(BaseModel):
    """Payload de mise à jour partielle (tous champs optionnels)."""

    label: Optional[str] = None
    type: Optional[str] = None
    currency: Optional[str] = None
    opening_value: Optional[Decimal] = None
    opening_value_eur: Optional[Decimal] = None
    current_value: Optional[Decimal] = None
    current_value_eur: Optional[Decimal] = None
    as_of_date: Optional[date] = None
    note: Optional[str] = None


class InvestmentSummary(BaseModel):
    """Totaux agrégés du portefeuille de placements (en EUR)."""

    total_opening_value_eur: Decimal
    total_current_value_eur: Decimal
    gain_eur: Decimal


def _get_or_404(db: Session, investment_id: int) -> models.Investment:
    row = db.get(models.Investment, investment_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Placement introuvable"
        )
    return row


@router.get("", response_model=list[InvestmentOut])
def list_investments(db: Session = Depends(get_db)) -> list[models.Investment]:
    """Retourne tous les placements."""
    logger.info("📥 [Investments] list")
    return db.query(models.Investment).order_by(models.Investment.id).all()


@router.post("", response_model=InvestmentOut, status_code=status.HTTP_201_CREATED)
def create_investment(
    payload: InvestmentCreate, db: Session = Depends(get_db)
) -> models.Investment:
    """Crée un placement."""
    row = models.Investment(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info("📤 [Investments] create: %s ✅", row.label)
    return row


@router.get("/summary", response_model=InvestmentSummary)
def investments_summary(db: Session = Depends(get_db)) -> InvestmentSummary:
    """Retourne les totaux ouverture / courant et la plus-value (EUR)."""
    rows = db.query(models.Investment).all()
    total_opening = sum((r.opening_value_eur for r in rows), Decimal("0"))
    total_current = sum((r.current_value_eur for r in rows), Decimal("0"))
    gain = total_current - total_opening
    logger.info("📤 [Investments] summary: gain=%s EUR", gain)
    return InvestmentSummary(
        total_opening_value_eur=total_opening,
        total_current_value_eur=total_current,
        gain_eur=gain,
    )


@router.patch("/{investment_id}", response_model=InvestmentOut)
def update_investment(
    investment_id: int, payload: InvestmentUpdate, db: Session = Depends(get_db)
) -> models.Investment:
    """Met à jour partiellement un placement (404 si absent)."""
    row = _get_or_404(db, investment_id)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    logger.info(
        "📤 [Investments] update: id=%d (%d champ(s)) ✅", investment_id, len(changes)
    )
    return row


@router.delete("/{investment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_investment(investment_id: int, db: Session = Depends(get_db)):
    """Supprime un placement (404 si absent)."""
    row = _get_or_404(db, investment_id)
    db.delete(row)
    db.commit()
    logger.info("📤 [Investments] delete: id=%d ✅", investment_id)
