"""
Routes Clients (table `clients`).

- GET    /api/clients        → liste des clients.
- POST   /api/clients        → création.
- GET    /api/clients/{id}   → détail (404 si absent).
- PATCH  /api/clients/{id}   → mise à jour partielle (404 si absent).

TJH (tarif journalier) en `Decimal`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from backend.db import models
from backend.db.base import get_db
from backend.logging_config import get_logger

logger = get_logger("clients", channel="api")

router = APIRouter(prefix="/api/clients", tags=["clients"])


class ClientOut(BaseModel):
    """Représentation renvoyée d'un client."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    legal_name: str
    address: str
    currency: str
    tjh: Decimal
    pay_iban: str
    counterparty_match: str


class ClientCreate(BaseModel):
    """Payload de création d'un client."""

    code: str
    legal_name: str
    address: str = ""
    currency: str = "USD"
    tjh: Decimal = Decimal("0")
    pay_iban: str = ""
    counterparty_match: str = ""


class ClientUpdate(BaseModel):
    """Payload de mise à jour partielle (tous champs optionnels)."""

    code: Optional[str] = None
    legal_name: Optional[str] = None
    address: Optional[str] = None
    currency: Optional[str] = None
    tjh: Optional[Decimal] = None
    pay_iban: Optional[str] = None
    counterparty_match: Optional[str] = None


def _get_or_404(db: Session, client_id: int) -> models.Client:
    row = db.get(models.Client, client_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client introuvable")
    return row


@router.get("", response_model=list[ClientOut])
def list_clients(db: Session = Depends(get_db)) -> list[models.Client]:
    """Retourne tous les clients."""
    logger.info("📥 [Clients] list")
    return db.query(models.Client).order_by(models.Client.id).all()


@router.post("", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
def create_client(payload: ClientCreate, db: Session = Depends(get_db)) -> models.Client:
    """Crée un client."""
    row = models.Client(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info("📤 [Clients] create: %s ✅", row.code)
    return row


@router.get("/{client_id}", response_model=ClientOut)
def get_client(client_id: int, db: Session = Depends(get_db)) -> models.Client:
    """Retourne un client (404 si absent)."""
    logger.info("📥 [Clients] get: id=%d", client_id)
    return _get_or_404(db, client_id)


@router.patch("/{client_id}", response_model=ClientOut)
def update_client(
    client_id: int, payload: ClientUpdate, db: Session = Depends(get_db)
) -> models.Client:
    """Met à jour partiellement un client (404 si absent)."""
    row = _get_or_404(db, client_id)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    logger.info("📤 [Clients] update: id=%d (%d champ(s)) ✅", client_id, len(changes))
    return row
