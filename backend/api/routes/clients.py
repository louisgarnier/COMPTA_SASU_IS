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
from sqlalchemy.exc import IntegrityError
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
    city: str
    state_region: str
    postal_code: str
    country: str
    contact_name: str
    email: str
    currency: str
    tjh: Decimal
    billing_mode: str
    default_hours_per_day: Decimal
    payment_terms_days: int
    pay_iban: str
    pay_bic: str
    pay_bank_name: str
    pay_bank_address: str
    counterparty_match: str


class ClientCreate(BaseModel):
    """Payload de création d'un client."""

    code: str
    legal_name: str
    address: str = ""
    city: str = ""
    state_region: str = ""
    postal_code: str = ""
    country: str = ""
    contact_name: str = ""
    email: str = ""
    currency: str = "USD"
    tjh: Decimal = Decimal("0")
    billing_mode: str = "tjm"
    default_hours_per_day: Decimal = Decimal("8")
    payment_terms_days: int = 60
    pay_iban: str = ""
    pay_bic: str = ""
    pay_bank_name: str = ""
    pay_bank_address: str = ""
    counterparty_match: str = ""


class ClientUpdate(BaseModel):
    """Payload de mise à jour partielle (tous champs optionnels)."""

    code: Optional[str] = None
    legal_name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state_region: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    contact_name: Optional[str] = None
    email: Optional[str] = None
    currency: Optional[str] = None
    tjh: Optional[Decimal] = None
    billing_mode: Optional[str] = None
    default_hours_per_day: Optional[Decimal] = None
    payment_terms_days: Optional[int] = None
    pay_iban: Optional[str] = None
    pay_bic: Optional[str] = None
    pay_bank_name: Optional[str] = None
    pay_bank_address: Optional[str] = None
    counterparty_match: Optional[str] = None


def _get_or_404(db: Session, client_id: int) -> models.Client:
    row = db.get(models.Client, client_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client introuvable")
    return row


def _require_code(code: str | None) -> None:
    """Un code vide/blanc est refusé (422) — évite les clients fantômes et la collision UNIQUE(code)."""
    if code is not None and not code.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Le code client est obligatoire",
        )


def _commit_or_409(db: Session, code: str | None) -> None:
    """Commit en traduisant la collision UNIQUE(code) en 409 propre (pas de 500 brut)."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Le code « {code} » est déjà utilisé par un autre client",
        )


@router.get("", response_model=list[ClientOut])
def list_clients(db: Session = Depends(get_db)) -> list[models.Client]:
    """Retourne tous les clients."""
    logger.info("📥 [Clients] list")
    return db.query(models.Client).order_by(models.Client.id).all()


@router.post("", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
def create_client(payload: ClientCreate, db: Session = Depends(get_db)) -> models.Client:
    """Crée un client."""
    _require_code(payload.code)
    row = models.Client(**payload.model_dump())
    db.add(row)
    _commit_or_409(db, payload.code)
    db.refresh(row)
    logger.info("📤 [Clients] create: %s ✅", row.code)
    return row


@router.get("/{client_id}", response_model=ClientOut)
def get_client(client_id: int, db: Session = Depends(get_db)) -> models.Client:
    """Retourne un client (404 si absent)."""
    logger.info("📥 [Clients] get: id=%d", client_id)
    return _get_or_404(db, client_id)


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client(client_id: int, db: Session = Depends(get_db)):
    """Supprime un client (404 si absent, 409 s'il a des factures/prévisions)."""
    row = _get_or_404(db, client_id)
    # Les prévisions sont désormais des factures `status='forecast'` (fusion),
    # donc couvertes par ce seul contrôle.
    has_invoices = (
        db.query(models.Invoice).filter(models.Invoice.client_id == client_id).first()
        is not None
    )
    if has_invoices:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Client lié à des factures/prévisions — impossible à supprimer",
        )
    db.delete(row)
    db.commit()
    logger.info("🗑️ [Clients] delete: id=%d ✅", client_id)


@router.patch("/{client_id}", response_model=ClientOut)
def update_client(
    client_id: int, payload: ClientUpdate, db: Session = Depends(get_db)
) -> models.Client:
    """Met à jour partiellement un client (404 si absent)."""
    row = _get_or_404(db, client_id)
    changes = payload.model_dump(exclude_unset=True)
    if "code" in changes:
        _require_code(changes["code"])
    for field, value in changes.items():
        setattr(row, field, value)
    _commit_or_409(db, changes.get("code", row.code))
    db.refresh(row)
    logger.info("📤 [Clients] update: id=%d (%d champ(s)) ✅", client_id, len(changes))
    return row


# --------------------------------------------------------------------------- #
# Repropagation du taux/mode aux prévisions futures (mois en cours inclus)
# --------------------------------------------------------------------------- #
class RepriceRow(BaseModel):
    """Une prévision affectée : ancien vs nouveau montant (natif + EUR)."""

    month: str
    quantity: Decimal
    unit: str
    old_amount: Decimal
    new_amount: Decimal
    old_amount_eur: Decimal
    new_amount_eur: Decimal


class RepricePreview(BaseModel):
    """Aperçu du recalcul des prévisions d'un client à son taux/mode courant."""

    from_month: str
    count: int
    currency: str
    rate: Decimal
    rate_unit: str
    rows: list[RepriceRow]
    total_old: Decimal
    total_new: Decimal
    total_old_eur: Decimal
    total_new_eur: Decimal


@router.get("/{client_id}/forecast-reprice-preview", response_model=RepricePreview)
def forecast_reprice_preview(
    client_id: int, db: Session = Depends(get_db)
) -> dict:
    """Aperçu (sans écriture) du recalcul des prévisions ≥ mois courant au taux/mode actuel."""
    _get_or_404(db, client_id)
    from backend.services import forecast

    logger.info("📥 [Clients] reprice preview: id=%d", client_id)
    return forecast.reprice_client_forecasts(db, client_id, apply=False)


@router.post("/{client_id}/forecast-reprice", response_model=RepricePreview)
def forecast_reprice_apply(client_id: int, db: Session = Depends(get_db)) -> dict:
    """Applique le recalcul des prévisions ≥ mois courant au taux/mode actuel du client."""
    _get_or_404(db, client_id)
    from backend.services import forecast

    result = forecast.reprice_client_forecasts(db, client_id, apply=True)
    logger.info("📤 [Clients] reprice apply: id=%d → %d prévision(s) ✅", client_id, result["count"])
    return result
