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
from pydantic import BaseModel, ConfigDict, Field as PydField
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
    expected_value: Optional[Decimal] = None
    expected_value_eur: Optional[Decimal] = None
    expected_month: Optional[str] = None
    closed_date: Optional[date] = None
    closed_transaction_id: Optional[int] = None
    realized_gain_eur: Optional[Decimal] = None


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
    expected_value: Optional[Decimal] = None
    expected_value_eur: Optional[Decimal] = None
    expected_month: Optional[str] = PydField(default=None, pattern=r"^\d{4}-\d{2}$")


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
    expected_value: Optional[Decimal] = None
    expected_value_eur: Optional[Decimal] = None
    expected_month: Optional[str] = PydField(default=None, pattern=r"^\d{4}-\d{2}$")


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


# --------------------------------------------------------------------------- #
# Clôture / rapprochement placement ↔ encaissement réel (gain réalisé)
# --------------------------------------------------------------------------- #
class ReconcileIn(BaseModel):
    """Rapprochement du remboursement d'un placement à une transaction."""

    transaction_id: int


def _tx_eur(db: Session, tx: models.Transaction) -> Decimal:
    """EUR réel d'une transaction : `amount_eur` sinon natif × taux théorique."""
    from backend.services.fx import load_rates, to_eur

    if tx.amount_eur is not None:
        return Decimal(tx.amount_eur)
    if (tx.currency or "EUR").upper() == "EUR":
        return Decimal(tx.amount or 0)
    return to_eur(Decimal(tx.amount or 0), tx.currency, load_rates(db))


@router.get("/{investment_id}/candidates")
def redemption_candidates(investment_id: int, db: Session = Depends(get_db)) -> list[dict]:
    """
    Encaissements candidats au rapprochement du remboursement : transactions
    positives, sans facture liée, ne clôturant pas déjà un autre placement —
    triées par proximité au montant attendu (sinon à l'investi), 20 max.
    """
    inv = _get_or_404(db, investment_id)
    target = Decimal(
        inv.expected_value_eur
        if inv.expected_value_eur is not None
        else inv.opening_value_eur or 0
    )
    used = {
        i.closed_transaction_id
        for i in db.query(models.Investment).all()
        if i.closed_transaction_id is not None
    }
    rows = [
        t
        for t in db.query(models.Transaction).all()
        if t.amount is not None
        and t.amount > 0
        and t.invoice_id is None
        and t.id not in used
    ]
    rows.sort(key=lambda t: abs(_tx_eur(db, t) - target))
    out = [
        {
            "id": t.id,
            "booked_date": t.booked_date.isoformat() if t.booked_date else None,
            "description": t.description,
            "counterparty": t.counterparty,
            "amount": str(t.amount),
            "currency": t.currency,
            "amount_eur": str(_tx_eur(db, t)),
        }
        for t in rows[:20]
    ]
    logger.info("📤 [Investments] candidates: id=%d, %d candidat(s)", investment_id, len(out))
    return out


@router.post("/{investment_id}/reconcile", response_model=InvestmentOut)
def reconcile_investment(
    investment_id: int, payload: ReconcileIn, db: Session = Depends(get_db)
) -> models.Investment:
    """
    Clôture le placement sur un encaissement réel : gain réalisé = EUR encaissé
    − investi (signé, une perte est déductible) → P&L réalisé + base IS.

    La transaction est basculée en flux interne (catégorie « Investissement »
    si présente, kind='investment') : le gain vit sur le placement, jamais en
    double dans les revenus catégorisés.
    """
    inv = _get_or_404(db, investment_id)
    if inv.closed_date is not None:
        raise HTTPException(status_code=409, detail="Placement déjà clôturé")
    tx = db.get(models.Transaction, payload.transaction_id)
    if tx is None:
        raise HTTPException(status_code=404, detail="Transaction introuvable")
    if tx.amount is None or tx.amount <= 0:
        raise HTTPException(status_code=422, detail="Le remboursement doit être un encaissement (montant > 0)")
    if tx.invoice_id is not None:
        raise HTTPException(status_code=409, detail="Transaction déjà rapprochée d'une facture")
    clash = (
        db.query(models.Investment)
        .filter(models.Investment.closed_transaction_id == payload.transaction_id)
        .first()
    )
    if clash is not None:
        raise HTTPException(status_code=409, detail=f"Transaction déjà liée au placement « {clash.label} »")

    received_eur = _tx_eur(db, tx)
    inv.closed_transaction_id = tx.id
    inv.closed_date = tx.booked_date or date.today()
    inv.realized_gain_eur = received_eur - Decimal(inv.opening_value_eur or 0)
    # Flux interne : la part capital ne doit jamais compter en revenu.
    internal_cat = (
        db.query(models.Category)
        .filter(models.Category.type == "internal")
        .order_by(models.Category.id)
        .first()
    )
    if internal_cat is not None:
        tx.category_id = internal_cat.id
    tx.kind = "investment"
    db.commit()
    db.refresh(inv)
    logger.info(
        "📤 [Investments] reconcile: id=%d ← tx#%d, gain réalisé=%s EUR ✅",
        investment_id, tx.id, inv.realized_gain_eur,
    )
    return inv


@router.post("/{investment_id}/unreconcile", response_model=InvestmentOut)
def unreconcile_investment(
    investment_id: int, db: Session = Depends(get_db)
) -> models.Investment:
    """Annule la clôture (la transaction garde sa catégorie interne)."""
    inv = _get_or_404(db, investment_id)
    if inv.closed_date is None:
        raise HTTPException(status_code=409, detail="Placement non clôturé")
    inv.closed_transaction_id = None
    inv.closed_date = None
    inv.realized_gain_eur = None
    db.commit()
    db.refresh(inv)
    logger.info("📤 [Investments] unreconcile: id=%d ✅", investment_id)
    return inv
