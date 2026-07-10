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
    # Banque d'origine (dérivée du compte : 'qonto' | 'revolut') + nom du compte.
    provider: Optional[str] = None
    account_name: Optional[str] = None
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


def _accounts_map(db: Session) -> dict[str, tuple[str, str]]:
    """Index account_uid → (provider, nom du compte) pour la banque d'origine."""
    return {
        a.account_uid: (a.provider, a.name or a.provider)
        for a in db.query(models.BankAccount).all()
    }


def _to_out(
    tx: models.Transaction,
    accounts: Optional[dict[str, tuple[str, str]]] = None,
) -> TransactionOut:
    """Sérialise une transaction en injectant catégorie et banque d'origine."""
    out = TransactionOut.model_validate(tx)
    out.category_name = tx.category.name if tx.category is not None else None
    if accounts is not None:
        prov = accounts.get(tx.account_uid)
        if prov:
            out.provider, out.account_name = prov
    return out


@router.get("/export")
def export_transactions_csv(
    year: int = Query(..., ge=2000, le=2100),
    db: Session = Depends(get_db),
):
    """
    Export CSV d'un exercice pour l'expert-comptable (clôture).

    Colonnes : date;description;contrepartie;categorie;type;devise;montant;
    montant_eur;compte — montant EUR = réel (`amount_eur`) sinon théorique.
    Séparateur `;` (Excel FR), champs échappés (csv.QUOTE_MINIMAL).
    """
    import csv
    import io

    from fastapi.responses import StreamingResponse

    from backend.services.fx import load_rates, to_eur

    rates = load_rates(db)
    cats = {c.id: c.name for c in db.query(models.Category).all()}
    accounts = {a.account_uid: (a.name or a.provider) for a in db.query(models.BankAccount).all()}

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(["date", "description", "contrepartie", "categorie", "type",
                     "devise", "montant", "montant_eur", "compte"])
    rows = (
        db.query(models.Transaction)
        .order_by(models.Transaction.booked_date, models.Transaction.id)
        .all()
    )
    n = 0
    for t in rows:
        if t.booked_date is None or t.booked_date.year != year:
            continue
        eur_v = (
            t.amount_eur
            if t.amount_eur is not None
            else to_eur(t.amount, t.currency, rates)
        )
        writer.writerow([
            t.booked_date.isoformat(), t.description or "", t.counterparty or "",
            cats.get(t.category_id, ""), t.kind or "", t.currency,
            f"{t.amount:.2f}", f"{eur_v:.2f}", accounts.get(t.account_uid, t.account_uid),
        ])
        n += 1
    logger.info("📤 [Transactions] export CSV: exercice=%d, %d ligne(s) ✅", year, n)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="transactions_{year}.csv"'},
    )


@router.get("", response_model=list[TransactionOut])
def list_transactions(
    db: Session = Depends(get_db),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    category_id: Optional[int] = Query(None),
    kind: Optional[str] = Query(None),
    uncategorized: Optional[bool] = Query(None),
    bridge: Optional[str] = Query(None),
    as_of: Optional[str] = Query(None),
) -> list[TransactionOut]:
    """Liste les transactions selon les filtres, triées par date d'opération décroissante.

    `bridge=<clé>` : filtre « vue trésorerie » — les transactions d'une ligne du
    pont (charges, received_current/prior, other_revenue, cat:<nom>, residual =
    conversions FX). MÊME logique de classement que le widget (`bridge_key_for_tx`)
    → le total de la liste égale la ligne du pont. Période : année de `as_of`
    (défaut aujourd'hui) jusqu'à `as_of` inclus.
    """
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

    if bridge:
        from backend.api.query_utils import parse_as_of
        from backend.services.treasury import bridge_key_for_tx

        ref = parse_as_of(as_of) or date.today()
        year = ref.year
        cats = {c.id: c for c in db.query(models.Category).all()}
        inv_month = {
            i.id: i.month
            for i in db.query(models.Invoice.id, models.Invoice.month).all()
        }
        rows = [
            t
            for t in rows
            if t.booked_date is not None
            and t.booked_date.year == year
            and t.booked_date <= ref
            and bridge_key_for_tx(t, cats, inv_month.get(t.invoice_id), year) == bridge
        ]

    logger.info("📤 [Transactions] list: %d résultat(s)", len(rows))
    accounts = _accounts_map(db)
    return [_to_out(tx, accounts) for tx in rows]


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
    accounts = _accounts_map(db)
    return [_to_out(tx, accounts) for tx in rows]


class LinkConversionIn(BaseModel):
    """Lien manuel crédit devise ↔ conversion EUR (filet de secours NG8)."""

    conversion_tx_id: int


@router.post("/{transaction_id}/link-conversion", response_model=TransactionOut)
def link_conversion(
    transaction_id: int,
    payload: LinkConversionIn,
    db: Session = Depends(get_db),
) -> TransactionOut:
    """
    Lie manuellement un encaissement en devise à sa conversion EUR.

    Filet de secours quand l'appariement automatique Revolut échoue (NG8) :
    pose `linked_conversion_id`, calcule `amount_eur` réel et le `fx_rate`
    implicite sur le crédit (cf. treasury.link_fx_conversion).
    """
    from backend.services.treasury import link_fx_conversion

    credit = db.get(models.Transaction, transaction_id)
    if credit is None:
        raise HTTPException(status_code=404, detail="Transaction introuvable")
    if (credit.currency or "EUR").upper() == "EUR":
        raise HTTPException(status_code=422, detail="Le crédit doit être en devise (non EUR)")
    if credit.amount is None or credit.amount <= 0:
        raise HTTPException(status_code=422, detail="Le lien s'applique à un encaissement (montant > 0)")
    conversion = db.get(models.Transaction, payload.conversion_tx_id)
    if conversion is None:
        raise HTTPException(status_code=404, detail="Conversion introuvable")
    if conversion.kind != "conversion":
        raise HTTPException(status_code=422, detail="La transaction cible n'est pas une conversion FX")

    updated = link_fx_conversion(db, transaction_id, payload.conversion_tx_id)
    logger.info(
        "📤 [Transactions] link_conversion: tx#%d ← conv#%d ✅",
        transaction_id, payload.conversion_tx_id,
    )
    return _to_out(updated, _accounts_map(db))


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
    return _to_out(tx, _accounts_map(db))
