"""
Service Factures LGC — numérotation, rendu HTML/PDF, rapprochement paiements.

Règles métier :
- Numérotation : `Settings.next_invoice_number` (entier), formaté en chaîne.
  L'incrément n'a lieu QUE lors de la création effective d'une facture.
- Montant : `amount = hours * rate` (toujours en `Decimal`, jamais float).
- PDF : WeasyPrint dépend de libs système (pango/cairo). Import PARESSEUX,
  gardé par try/except → HTTPException(503) si indisponible. Les tests ne
  doivent jamais dépendre de WeasyPrint (on teste le HTML séparément).
- Rapprochement : on relie une facture non payée ('draft'/'sent') à une
  transaction bancaire de revenu dont le montant matche (tolérance) et dont la
  contrepartie/description contient le `counterparty_match` du client.

Détermination : `create_invoice` accepte `issue_date` (défaut = aujourd'hui si
None) pour rester déterministe en test.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db import models
from backend.logging_config import get_logger

logger = get_logger("invoices", channel="backend")

# Racine projet (…/compta_sasu) : base.py utilise parents[2], on fait pareil.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
_INVOICES_DIR = _PROJECT_ROOT / "data" / "invoices"

# Tolérance de rapprochement montant (valeur absolue, même devise).
_RECONCILE_TOLERANCE = Decimal("0.01")

_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


def _get_settings(db: Session) -> models.Settings:
    """Retourne la ligne Settings singleton (id=1), en la créant si absente."""
    row = db.get(models.Settings, 1)
    if row is None:
        row = models.Settings(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)
        logger.info("🗄️ [Invoices] settings: ligne singleton créée")
    return row


def next_number(db: Session) -> str:
    """
    Retourne le prochain numéro de facture (chaîne) SANS incrémenter.

    Lecture seule : sert à l'affichage / prévisualisation.
    """
    settings = _get_settings(db)
    return str(settings.next_invoice_number)


def create_invoice(db: Session, data: dict, issue_date: Optional[date] = None) -> models.Invoice:
    """
    Crée une facture 'draft' et incrémente le compteur de numérotation.

    `data` attend : client_id, period_label, period_start, period_end,
    hours, rate, currency. `amount = hours * rate`. `issue_date` défaut =
    aujourd'hui si None (passé explicitement en test pour le déterminisme).
    """
    settings = _get_settings(db)

    hours = Decimal(str(data.get("hours", "0")))
    rate = Decimal(str(data.get("rate", "0")))
    amount = hours * rate

    number = str(settings.next_invoice_number)
    if issue_date is None:
        issue_date = date.today()

    invoice = models.Invoice(
        number=number,
        client_id=data["client_id"],
        period_label=data.get("period_label", ""),
        period_start=data.get("period_start"),
        period_end=data.get("period_end"),
        hours=hours,
        rate=rate,
        currency=data.get("currency", "USD"),
        amount=amount,
        issue_date=issue_date,
        status="draft",
    )
    db.add(invoice)

    # Incrément du compteur seulement maintenant (création effective).
    settings.next_invoice_number = settings.next_invoice_number + 1

    db.commit()
    db.refresh(invoice)
    logger.info(
        "📤 [Invoices] create: n°%s client=%d montant=%s %s ✅",
        number, invoice.client_id, amount, invoice.currency,
    )
    return invoice


def render_html(db: Session, invoice: models.Invoice) -> str:
    """
    Rend le HTML de la facture (Jinja2) avec infos société + client.

    Retourne une chaîne HTML. Aucune dépendance système (testable seul).
    """
    settings = _get_settings(db)
    client = db.get(models.Client, invoice.client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client de la facture introuvable")

    template = _jinja_env.get_template("invoice.html")
    html = template.render(company=settings, client=client, invoice=invoice)
    logger.info("📤 [Invoices] render_html: n°%s ✅", invoice.number)
    return html


def generate_pdf(db: Session, invoice: models.Invoice) -> str:
    """
    Génère le PDF de la facture via WeasyPrint (import paresseux).

    Sauvegarde dans data/invoices/<number>.pdf, pose `invoice.pdf_path`, commit,
    retourne le chemin. Lève HTTPException(503) si WeasyPrint indisponible.
    """
    try:
        from weasyprint import HTML  # import paresseux : libs système requises
    except (ImportError, OSError) as exc:
        logger.error("❌ [Invoices] generate_pdf: moteur PDF indisponible (%s)", exc)
        raise HTTPException(
            status_code=503,
            detail="PDF engine indisponible (installer pango/cairo: brew install pango)",
        ) from exc

    html = render_html(db, invoice)

    _INVOICES_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = _INVOICES_DIR / f"{invoice.number}.pdf"
    HTML(string=html).write_pdf(str(pdf_path))

    invoice.pdf_path = str(pdf_path)
    db.commit()
    db.refresh(invoice)
    logger.info("📤 [Invoices] generate_pdf: n°%s → %s ✅", invoice.number, pdf_path)
    return str(pdf_path)


def _amount_matches(tx: models.Transaction, target: Decimal) -> bool:
    """Vrai si le montant de la transaction (EUR sinon brut) matche à tolérance près."""
    tx_amount = tx.amount_eur if tx.amount_eur is not None else tx.amount
    if tx_amount is None:
        return False
    return abs(abs(tx_amount) - abs(target)) <= _RECONCILE_TOLERANCE


def reconcile_payments(db: Session) -> int:
    """
    Rapproche les factures non payées avec des transactions de revenu.

    Pour chaque facture 'draft'/'sent' non déjà réglée, cherche une transaction
    de revenu (kind='revenue' ou montant positif) dont le montant matche (à
    tolérance) et dont la contrepartie/description contient le
    `counterparty_match` du client, non déjà rattachée à une autre facture.
    Relie (paid_transaction_id, status='paid', transaction.invoice_id).
    Retourne le nombre de factures rapprochées.
    """
    invoices = (
        db.execute(
            select(models.Invoice)
            .where(models.Invoice.status.in_(("draft", "sent")))
            .where(models.Invoice.paid_transaction_id.is_(None))
            .order_by(models.Invoice.id.asc())
        )
        .scalars()
        .all()
    )

    reconciled = 0
    for invoice in invoices:
        client = db.get(models.Client, invoice.client_id)
        match_token = (client.counterparty_match or "").strip().lower() if client else ""

        candidates = (
            db.execute(
                select(models.Transaction)
                .where(models.Transaction.invoice_id.is_(None))
                .order_by(models.Transaction.id.asc())
            )
            .scalars()
            .all()
        )

        for tx in candidates:
            is_revenue = tx.kind == "revenue" or (tx.amount is not None and tx.amount > 0)
            if not is_revenue:
                continue
            if not _amount_matches(tx, invoice.amount):
                continue
            if match_token:
                haystack = f"{tx.counterparty or ''} {tx.description or ''}".lower()
                if match_token not in haystack:
                    continue

            invoice.paid_transaction_id = tx.id
            invoice.status = "paid"
            tx.invoice_id = invoice.id
            reconciled += 1
            logger.info(
                "✅ [Invoices] reconcile: facture n°%s ↔ tx#%d (%s)",
                invoice.number, tx.id, invoice.amount,
            )
            break

    db.commit()
    logger.info("📤 [Invoices] reconcile_payments: %d facture(s) rapprochée(s) ✅", reconciled)
    return reconciled
