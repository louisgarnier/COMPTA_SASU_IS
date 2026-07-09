"""
Routes Factures (table `invoices`).

- GET    /api/invoices              → liste (avec nom du client).
- POST   /api/invoices              → création (numérote + incrémente compteur).
- GET    /api/invoices/{id}         → détail (404 si absent).
- POST   /api/invoices/{id}/pdf     → génère le PDF, renvoie {pdf_path} (503 si moteur absent).
- GET    /api/invoices/{id}/download → renvoie le fichier PDF (le génère si absent).
- PATCH  /api/invoices/{id}         → n° éditable ; statut VERROUILLÉ (409 —
  le cycle passe par generate/reconcile/unreconcile/rollback/delete).

Montants en `Decimal`. Le service porte la logique métier (numérotation, PDF,
rapprochement) ; ces routes ne font que valider / orchestrer.
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from backend.db import models
from backend.db.base import get_db
from backend.logging_config import get_logger
from backend.services import invoices as invoices_service

logger = get_logger("invoices", channel="api")

router = APIRouter(prefix="/api/invoices", tags=["invoices"])


class InvoiceOut(BaseModel):
    """Représentation renvoyée d'une facture (avec nom du client)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    client_id: int
    client_name: Optional[str] = None
    month: str
    period_label: str
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    days: Decimal
    hours: Decimal
    rate: Decimal
    rate_unit: str
    currency: str
    amount: Decimal
    amount_eur_forecast: Decimal
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    status: str
    sent_date: Optional[date] = None
    paid_transaction_id: Optional[int] = None
    paid_date: Optional[date] = None
    amount_received: Optional[Decimal] = None
    amount_eur_received: Optional[Decimal] = None
    variance_eur: Optional[Decimal] = None
    pdf_path: str


class InvoiceCreate(BaseModel):
    """Payload de création d'une facture."""

    client_id: int
    period_label: str = ""
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    hours: Decimal = Decimal("0")
    rate: Decimal = Decimal("0")
    currency: str = "USD"
    issue_date: Optional[date] = None


class InvoiceUpdate(BaseModel):
    """Payload de mise à jour partielle (statut enum validé, n° éditable).

    `sent_date` : indicateur « envoyée au client » — un simple marqueur de
    suivi (posable/effaçable), PAS une transition de statut. L'immutabilité
    complète post-envoi (avoir obligatoire) reste hors périmètre v1.
    """

    status: Optional[Literal["forecast", "due", "paid"]] = None
    number: Optional[str] = None
    sent_date: Optional[date] = None


def _to_out(invoice: models.Invoice) -> InvoiceOut:
    """Sérialise une facture en ajoutant le nom du client (relation)."""
    out = InvoiceOut.model_validate(invoice)
    if invoice.client is not None:
        out.client_name = invoice.client.legal_name
    return out


def _get_or_404(db: Session, invoice_id: int) -> models.Invoice:
    row = db.get(models.Invoice, invoice_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Facture introuvable")
    return row


@router.get("", response_model=list[InvoiceOut])
def list_invoices(db: Session = Depends(get_db)) -> list[InvoiceOut]:
    """Retourne toutes les factures (avec nom du client)."""
    logger.info("📥 [Invoices] list")
    rows = db.query(models.Invoice).order_by(models.Invoice.id).all()
    return [_to_out(row) for row in rows]


@router.post("", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED)
def create_invoice(payload: InvoiceCreate, db: Session = Depends(get_db)) -> InvoiceOut:
    """Crée une facture (numérote et incrémente le compteur)."""
    if db.get(models.Client, payload.client_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client introuvable")
    data = payload.model_dump(exclude={"issue_date"})
    invoice = invoices_service.create_invoice(db, data, issue_date=payload.issue_date)
    logger.info("📤 [Invoices] create: n°%s ✅", invoice.number)
    return _to_out(invoice)


@router.get("/{invoice_id}", response_model=InvoiceOut)
def get_invoice(invoice_id: int, db: Session = Depends(get_db)) -> InvoiceOut:
    """Retourne une facture (404 si absente)."""
    logger.info("📥 [Invoices] get: id=%d", invoice_id)
    return _to_out(_get_or_404(db, invoice_id))


class TxCandidate(BaseModel):
    """Transaction candidate au rapprochement manuel."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    booked_date: Optional[date] = None
    amount: Decimal
    currency: str
    counterparty: str
    description: str
    amount_eur: Optional[Decimal] = None


class ReconcileIn(BaseModel):
    """Payload de rapprochement manuel."""

    transaction_id: int


@router.get("/{invoice_id}/candidates", response_model=list[TxCandidate])
def reconcile_candidates(invoice_id: int, db: Session = Depends(get_db)) -> list[models.Transaction]:
    """Transactions candidates (revenus non rattachés), les plus proches d'abord."""
    return invoices_service.reconcile_candidates(db, invoice_id)


@router.post("/{invoice_id}/reconcile", response_model=InvoiceOut)
def reconcile_route(
    invoice_id: int, payload: ReconcileIn, db: Session = Depends(get_db)
) -> InvoiceOut:
    """Rapproche manuellement la facture avec la transaction choisie."""
    invoice = invoices_service.manual_reconcile(db, invoice_id, payload.transaction_id)
    return _to_out(invoice)


@router.post("/{invoice_id}/unreconcile", response_model=InvoiceOut)
def unreconcile_route(invoice_id: int, db: Session = Depends(get_db)) -> InvoiceOut:
    """Annule le rapprochement (repasse la facture à « À encaisser »)."""
    invoice = invoices_service.unreconcile(db, invoice_id)
    return _to_out(invoice)


@router.post("/{invoice_id}/rollback", response_model=InvoiceOut)
def rollback_route(invoice_id: int, db: Session = Depends(get_db)) -> InvoiceOut:
    """Repasse une facture émise (due) en prévision — dernier numéro uniquement."""
    invoice = invoices_service.rollback_to_forecast(db, invoice_id)
    return _to_out(invoice)


@router.post("/{invoice_id}/generate", response_model=InvoiceOut)
def generate_invoice_route(invoice_id: int, db: Session = Depends(get_db)) -> InvoiceOut:
    """Génère la facture (forecast → due) : numéro réel, dates, désignation."""
    invoice = invoices_service.generate_invoice(db, invoice_id)
    logger.info("📤 [Invoices] generate: n°%s ✅", invoice.number)
    return _to_out(invoice)


@router.get("/{invoice_id}/print", response_class=HTMLResponse)
def print_invoice(invoice_id: int, db: Session = Depends(get_db)) -> HTMLResponse:
    """Renvoie la facture en HTML imprimable (Cmd+P → PDF côté navigateur)."""
    invoice = _get_or_404(db, invoice_id)
    html = invoices_service.render_html(db, invoice)
    logger.info("📤 [Invoices] print: n°%s ✅", invoice.number)
    return HTMLResponse(content=html)


@router.post("/{invoice_id}/pdf")
def generate_invoice_pdf(invoice_id: int, db: Session = Depends(get_db)) -> dict:
    """Génère le PDF de la facture et renvoie son chemin (503 si moteur absent)."""
    invoice = _get_or_404(db, invoice_id)
    pdf_path = invoices_service.generate_pdf(db, invoice)
    logger.info("📤 [Invoices] pdf: n°%s ✅", invoice.number)
    return {"pdf_path": pdf_path}


@router.get("/{invoice_id}/download")
def download_invoice_pdf(invoice_id: int, db: Session = Depends(get_db)) -> FileResponse:
    """Renvoie le fichier PDF de la facture (le génère s'il n'existe pas encore)."""
    invoice = _get_or_404(db, invoice_id)
    if not invoice.pdf_path or not os.path.exists(invoice.pdf_path):
        invoices_service.generate_pdf(db, invoice)
    if not invoice.pdf_path or not os.path.exists(invoice.pdf_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PDF introuvable")
    logger.info("📤 [Invoices] download: n°%s ✅", invoice.number)
    return FileResponse(
        invoice.pdf_path,
        media_type="application/pdf",
        filename=os.path.basename(invoice.pdf_path),  # Invoice_June_2026_SWIB_LG.pdf
    )


@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_invoice_route(invoice_id: int, db: Session = Depends(get_db)):
    """Supprime une facture (libère la transaction liée si rapprochée)."""
    invoices_service.delete_invoice(db, invoice_id)
    logger.info("🗑️ [Invoices] delete: id=%d ✅", invoice_id)


@router.patch("/{invoice_id}", response_model=InvoiceOut)
def update_invoice(
    invoice_id: int, payload: InvoiceUpdate, db: Session = Depends(get_db)
) -> InvoiceOut:
    """Met à jour une facture (404 si absente) — n° éditable, statut verrouillé.

    Machine à états gardée : AUCUNE transition de statut par PATCH. Le cycle de
    vie passe par les actions dédiées — generate (forecast→due), reconcile
    (due→paid), unreconcile (paid→due), delete. Un PATCH due→forecast
    dé-numéroterait silencieusement une facture émise (trou de séquence) ;
    forecast→due poserait un statut émis sans numéro réel ni dates.
    """
    invoice = _get_or_404(db, invoice_id)
    changes = payload.model_dump(exclude_unset=True)
    new_status = changes.get("status")
    if new_status is not None and new_status != invoice.status:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Statut non modifiable directement — utiliser générer / "
                "rapprocher / annuler le rapprochement / supprimer"
            ),
        )
    # N° de facture : correction manuelle, unicité contrôlée (numérotation légale).
    new_number = changes.get("number")
    if new_number is not None:
        new_number = new_number.strip()
        if not new_number:
            raise HTTPException(status_code=422, detail="N° de facture vide")
        clash = (
            db.query(models.Invoice)
            .filter(models.Invoice.number == new_number, models.Invoice.id != invoice_id)
            .first()
        )
        if clash is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"N° {new_number} déjà utilisé",
            )
        changes["number"] = new_number
    # Marqueur « envoyée » : uniquement sur facture émise (une prévision n'a
    # rien à envoyer). Effacement (null explicite) toujours permis.
    if changes.get("sent_date") is not None and invoice.status == "forecast":
        raise HTTPException(
            status_code=422,
            detail="Une prévision ne peut pas être marquée envoyée — générer la facture d'abord",
        )
    for field, value in changes.items():
        setattr(invoice, field, value)
    db.commit()
    db.refresh(invoice)
    logger.info("📤 [Invoices] update: id=%d (%d champ(s)) ✅", invoice_id, len(changes))
    return _to_out(invoice)
