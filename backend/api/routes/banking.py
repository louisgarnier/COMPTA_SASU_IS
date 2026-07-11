"""
Routes Banking (Enable Banking) — préfixe `/api/banking`.

- GET  /api/banking/aspsps?country=FR → banques disponibles.
- POST /api/banking/connect            → démarre l'OAuth (authorization_url, state).
- POST /api/banking/sessions           → échange le code → comptes créés.
- GET  /api/banking/connections        → comptes bancaires connectés.
- POST /api/banking/sync               → synchronise les transactions.
- GET  /api/banking/status             → mode live/mock + message.

Le service (`backend.services.banking`) bascule automatiquement en mode MOCK
si les identifiants / la clé / pyjwt sont absents : l'app tourne sans réseau.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from backend.db.base import get_db
from backend.logging_config import get_logger
from backend.services import backup as backup_service
from backend.services import banking as banking_service

logger = get_logger("banking", channel="api")

router = APIRouter(prefix="/api/banking", tags=["banking"])


# ---------------------------------------------------------------------------
# Schémas Pydantic
# ---------------------------------------------------------------------------

class AspspOut(BaseModel):
    name: str
    country: str


class ConnectIn(BaseModel):
    aspsp_name: str
    country: str = "FR"


class ConnectOut(BaseModel):
    authorization_url: str
    state: str


class SessionIn(BaseModel):
    code: str
    state: Optional[str] = None


class AccountPreview(BaseModel):
    """Compte disponible (aperçu), avant rattachement."""

    account_uid: str
    provider: str
    currency: str
    iban_masked: str
    name: str


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: str
    account_uid: str
    currency: str
    iban_masked: str
    name: str
    balance: Decimal
    last_synced_at: Optional[datetime] = None


class SessionOut(BaseModel):
    """Retour de l'échange OAuth : comptes disponibles (non encore rattachés)."""

    session_id: str
    accounts: list[AccountPreview]


class SelectIn(BaseModel):
    """Comptes choisis par l'utilisateur à rattacher."""

    accounts: list[AccountPreview]


class SyncError(BaseModel):
    account_uid: str
    error: str


class SyncOut(BaseModel):
    accounts_synced: int
    accounts_total: int = 0
    transactions_added: int
    transactions_skipped: int
    transactions_categorized: int = 0
    invoices_reconciled: int = 0
    errors: list[SyncError] = []


class StatusOut(BaseModel):
    live: bool
    message: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/aspsps", response_model=list[AspspOut])
def get_aspsps(country: str = "FR") -> list[dict]:
    """Liste des banques disponibles pour un pays."""
    logger.info("📥 [Banking] GET /aspsps pays=%s", country)
    return banking_service.list_aspsps(country=country)


@router.post("/connect", response_model=ConnectOut)
def connect(payload: ConnectIn) -> dict:
    """Démarre l'autorisation OAuth pour une banque."""
    logger.info("📥 [Banking] POST /connect aspsp=%s", payload.aspsp_name)
    return banking_service.start_auth(payload.aspsp_name, country=payload.country)


@router.post("/sessions", response_model=SessionOut)
def create_session(payload: SessionIn, db: Session = Depends(get_db)) -> dict:
    """Échange le code contre la liste des comptes disponibles (non rattachés)."""
    logger.info("📥 [Banking] POST /sessions")
    return banking_service.create_session(db, payload.code, payload.state)


@router.post("/connections/select", response_model=list[AccountOut])
def select_accounts(payload: SelectIn, db: Session = Depends(get_db)):
    """Rattache les comptes choisis par l'utilisateur (persistés)."""
    logger.info("📥 [Banking] POST /connections/select (%d)", len(payload.accounts))
    return banking_service.select_accounts(
        db, [a.model_dump() for a in payload.accounts]
    )


@router.get("/connections", response_model=list[AccountOut])
def list_connections(db: Session = Depends(get_db)):
    """Comptes bancaires connectés."""
    from backend.db import models

    logger.info("📥 [Banking] GET /connections")
    return db.query(models.BankAccount).order_by(models.BankAccount.id).all()


@router.post("/sync", response_model=SyncOut)
def sync(db: Session = Depends(get_db)) -> dict:
    """Synchronise les transactions de tous les comptes (sauvegarde d'abord)."""
    logger.info("📥 [Banking] POST /sync")
    # Fail-closed : une synchro peut altérer les données (dédup, recatégo…) —
    # sans sauvegarde préalable, on ne synchronise pas.
    try:
        backup_service.create_backup(reason="sync")
    except Exception as exc:
        logger.error("❌ [Banking] sauvegarde impossible avant sync: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Sauvegarde de la base impossible, synchro annulée : {exc}",
        )
    return banking_service.sync(db)


@router.delete("/connections/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_connection(account_id: int, db: Session = Depends(get_db)):
    """Déconnecte un compte bancaire (404 s'il n'existe pas). Les transactions restent."""
    logger.info("📥 [Banking] DELETE /connections/%d", account_id)
    if not banking_service.disconnect_account(db, account_id):
        raise HTTPException(status_code=404, detail="Compte introuvable")


@router.get("/status", response_model=StatusOut)
def get_status() -> dict:
    """Mode courant (live/mock) et message explicatif."""
    logger.info("📥 [Banking] GET /status")
    return banking_service.status()
