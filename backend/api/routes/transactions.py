"""
Routes Transactions.

- GET  /api/transactions       → liste filtrable (dates, catégorie, kind,
  uncategorized), triée par booked_date décroissant, avec le nom de catégorie.
- PATCH /api/transactions/{id} → mise à jour partielle (category_id, kind,
  linked_conversion_id, invoice_id). 404 si absente.

Montants manipulés en `Decimal` (jamais float).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.db import models
from backend.db.base import get_db
from backend.logging_config import get_logger
from backend.services.categorize import kind_for_category_type

logger = get_logger("transactions", channel="api")

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


class TransactionOut(BaseModel):
    """Représentation renvoyée d'une transaction (avec nom de catégorie)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    account_uid: str
    external_id: str
    booked_date: Optional[date]
    value_date: Optional[date]
    amount: Decimal
    currency: str
    description: str
    counterparty: str
    category_id: Optional[int]
    category_name: Optional[str] = None
    kind: str
    fx_rate: Optional[Decimal]
    amount_eur: Optional[Decimal]
    linked_conversion_id: Optional[int]
    invoice_id: Optional[int]
    created_at: Optional[datetime]


class TransactionUpdate(BaseModel):
    """Champs modifiables d'une transaction (tous optionnels)."""

    category_id: Optional[int] = None
    kind: Optional[str] = None
    linked_conversion_id: Optional[int] = None
    invoice_id: Optional[int] = None


class BulkCategorizeIn(BaseModel):
    """Recatégorisation groupée : applique une catégorie à plusieurs transactions."""

    ids: list[int]
    category_id: Optional[int] = None  # None = repasse en « À catégoriser »


def _kind_for_category(db: Session, category_id: Optional[int]) -> str:
    """Dérive le `kind` d'une transaction depuis sa (nouvelle) catégorie."""
    if category_id is None:
        return "other"
    cat = db.get(models.Category, category_id)
    return kind_for_category_type(cat.type if cat else None)


def _to_out(tx: models.Transaction) -> TransactionOut:
    """Sérialise une transaction en injectant le nom de sa catégorie."""
    out = TransactionOut.model_validate(tx)
    out.category_name = tx.category.name if tx.category is not None else None
    return out


@router.get("", response_model=list[TransactionOut])
def list_transactions(
    db: Session = Depends(get_db),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    category_id: Optional[int] = Query(None),
    kind: Optional[str] = Query(None),
    uncategorized: Optional[bool] = Query(None),
) -> list[TransactionOut]:
    """Liste les transactions selon les filtres, triées par date d'opération décroissante."""
    stmt = select(models.Transaction)
    if date_from is not None:
        stmt = stmt.where(models.Transaction.booked_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(models.Transaction.booked_date <= date_to)
    if category_id is not None:
        stmt = stmt.where(models.Transaction.category_id == category_id)
    if kind is not None:
        stmt = stmt.where(models.Transaction.kind == kind)
    if uncategorized:
        # Non catégorisée = sans catégorie OU rangée dans le fourre-tout (type 'uncategorized').
        uncat_ids = select(models.Category.id).where(
            models.Category.type == "uncategorized"
        )
        stmt = stmt.where(
            or_(
                models.Transaction.category_id.is_(None),
                models.Transaction.category_id.in_(uncat_ids),
            )
        )
    stmt = stmt.order_by(models.Transaction.booked_date.desc(), models.Transaction.id.desc())

    rows = db.execute(stmt).scalars().all()
    logger.info("📤 [Transactions] list: %d résultat(s)", len(rows))
    return [_to_out(tx) for tx in rows]


@router.post("/bulk-categorize", response_model=list[TransactionOut])
def bulk_categorize(
    payload: BulkCategorizeIn, db: Session = Depends(get_db)
) -> list[TransactionOut]:
    """Applique une catégorie à un lot de transactions (met aussi à jour `kind`)."""
    if not payload.ids:
        return []
    if payload.category_id is not None and db.get(models.Category, payload.category_id) is None:
        raise HTTPException(status_code=404, detail="Catégorie introuvable")

    kind = _kind_for_category(db, payload.category_id)
    rows = (
        db.execute(
            select(models.Transaction).where(models.Transaction.id.in_(payload.ids))
        )
        .scalars()
        .all()
    )
    for tx in rows:
        tx.category_id = payload.category_id
        tx.kind = kind
    db.commit()
    for tx in rows:
        db.refresh(tx)
    logger.info("📤 [Transactions] bulk_categorize: %d transaction(s) ✅", len(rows))
    return [_to_out(tx) for tx in rows]


@router.patch("/{transaction_id}", response_model=TransactionOut)
def update_transaction(
    transaction_id: int,
    payload: TransactionUpdate,
    db: Session = Depends(get_db),
) -> TransactionOut:
    """Met à jour partiellement une transaction ; 404 si elle n'existe pas."""
    tx = db.get(models.Transaction, transaction_id)
    if tx is None:
        logger.warning("❌ [Transactions] update: id=%s introuvable", transaction_id)
        raise HTTPException(status_code=404, detail="Transaction introuvable")

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(tx, field, value)
    # Changer la catégorie sans préciser le kind → on le redérive (cohérence du
    # filtre « Type »), sinon un reclassement manuel laissait un kind périmé.
    if "category_id" in changes and "kind" not in changes:
        tx.kind = _kind_for_category(db, tx.category_id)
    db.commit()
    db.refresh(tx)
    logger.info("📤 [Transactions] update: id=%s, %d champ(s) ✅", transaction_id, len(changes))
    return _to_out(tx)
