"""
Routes Factures (table `invoices`).

- GET    /api/invoices              → liste (avec nom du client).
- POST   /api/invoices              → création (numérote + incrémente compteur).
- GET    /api/invoices/{id}         → détail (404 si absent).
- POST   /api/invoices/{id}/pdf     → génère le PDF, renvoie {pdf_path} (503 si moteur absent).
- GET    /api/invoices/{id}/download → renvoie le fichier PDF (le génère si absent).
- PATCH  /api/invoices/{id}         → met à jour le statut (draft|sent|paid).

Montants en `Decimal`. Le service porte la logique métier (numérotation, PDF,
rapprochement) ; ces routes ne font que valider / orchestrer.
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from typing import Optional

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
    paid_transaction_id: Optional[int] = None
    paid_date: Optional[date] = None
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
    """Payload de mise à jour partielle du statut."""

    status: Optional[str] = None


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
        filename=f"{invoice.number}.pdf",
    )


@router.patch("/{invoice_id}", response_model=InvoiceOut)
def update_invoice(
    invoice_id: int, payload: InvoiceUpdate, db: Session = Depends(get_db)
) -> InvoiceOut:
    """Met à jour le statut d'une facture (404 si absente)."""
    invoice = _get_or_404(db, invoice_id)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(invoice, field, value)
    db.commit()
    db.refresh(invoice)
    logger.info("📤 [Invoices] update: id=%d (%d champ(s)) ✅", invoice_id, len(changes))
    return _to_out(invoice)
