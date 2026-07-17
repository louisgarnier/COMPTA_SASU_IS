"""
Routes Rapprochement mensuel officiel.

- POST /api/monthly-balances/extract        → proposition extraite (n'écrit RIEN)
- PUT  /api/monthly-balances?year=&month=   → upsert des soldes validés
- GET  /api/monthly-balances/reconciliation?year=  → vue 12 mois + tie-out
"""

from __future__ import annotations

import io
import zipfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.db import models
from backend.db.base import get_db
from backend.logging_config import get_logger
from backend.services import monthly_reconcile, statement_extract

logger = get_logger("monthly_balances", channel="api")

router = APIRouter(prefix="/api/monthly-balances", tags=["monthly-balances"])


class MonthlyItem(BaseModel):
    account_uid: str
    balance: Decimal


class MonthlyUpsert(BaseModel):
    items: list[MonthlyItem] = Field(default_factory=list)
    doc_id: Optional[int] = None


@router.post("/extract")
async def extract(
    file: UploadFile = File(...),
    provider: str = Form(...),
    year: int = Form(...),
    month: int = Form(...),
    db: Session = Depends(get_db),
) -> dict:
    """Extrait une proposition de soldes de fin de mois. N'écrit rien en base."""
    data = await file.read()
    if provider == "qonto":
        # Qonto : relevé mensuel PDF (solde de clôture) ou export CSV d'opérations.
        # Détection par magic bytes — le PDF est le format naturel côté utilisateur.
        if data[:4] == b"%PDF":
            extracted = statement_extract.extract_qonto_pdf_month_end(statement_extract.pdf_to_text(data))
        else:
            extracted = statement_extract.extract_qonto_month_end(data.decode("utf-8", "ignore"), year, month)
        mapped = statement_extract.map_to_accounts(db, [
            {"name": e["account_name"], "currency": e["currency"],
             "iban_last4": e["iban_last4"], "amount": e["amount"]} for e in extracted
        ])
    else:  # revolut (PDF)
        text = statement_extract.pdf_to_text(data)
        parsed = statement_extract.extract_revolut_balances(text)
        mapped = statement_extract.map_to_accounts(db, parsed["balances"])
    logger.info("📥 [MonthlyBalances] extract: %s %d-%02d → %d solde(s)",
                provider, year, month, len(mapped))
    return {"proposal": [
        {"account_uid": m["account_uid"], "currency": m["currency"],
         "amount": str(m["amount"]) if m["amount"] is not None else None,
         "matched": m["matched"], "hint": m["hint"]}
        for m in mapped
    ]}


@router.put("")
def upsert(payload: MonthlyUpsert, year: int = Query(...), month: int = Query(...),
           db: Session = Depends(get_db)) -> dict:
    """Upsert des soldes officiels validés pour (year, month)."""
    for it in payload.items:
        acc = (db.query(models.BankAccount)
               .filter(models.BankAccount.account_uid == it.account_uid).first())
        if acc is None:
            raise HTTPException(status_code=404, detail=f"Compte inconnu: {it.account_uid}")
        row = (db.query(models.MonthlyBalance)
               .filter(models.MonthlyBalance.account_uid == it.account_uid,
                       models.MonthlyBalance.year == year,
                       models.MonthlyBalance.month == month).first())
        if row is None:
            row = models.MonthlyBalance(account_uid=it.account_uid, year=year, month=month,
                                        currency=(acc.currency or "EUR").upper())
            db.add(row)
        row.balance = it.balance
        row.confirmed_at = datetime.utcnow()
        if payload.doc_id is not None:
            row.source_doc_id = payload.doc_id
    db.commit()
    logger.info("📤 [MonthlyBalances] upsert: %d-%02d, %d compte(s) ✅", year, month, len(payload.items))
    return monthly_reconcile.monthly_reconciliation(db, year)


@router.get("/reconciliation")
def reconciliation(year: int = Query(...), db: Session = Depends(get_db)) -> dict:
    """Vue 12 mois : officiel vs reconstitué + statut + couverture."""
    return monthly_reconcile.monthly_reconciliation(db, year)


@router.get("/docs-archive")
def docs_archive(ids: str = Query(..., description="ids de relevés séparés par virgule"),
                 db: Session = Depends(get_db)) -> StreamingResponse:
    """ZIP des relevés archivés (justificatifs) demandés — pour téléchargement groupé."""
    id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()]
    if not id_list:
        raise HTTPException(status_code=400, detail="Aucun relevé demandé")
    buf = io.BytesIO()
    used: set[str] = set()
    added = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for did in id_list:
            doc = db.get(models.BalanceDocument, did)
            if doc is None or not Path(doc.file_path).exists():
                continue
            # dossier par période pour éviter les collisions de noms
            folder = (f"{doc.period_year}-{doc.period_month:02d}/"
                      if doc.period_year and doc.period_month else "")
            arc = f"{folder}{doc.filename}"
            n = 1
            while arc in used:  # garde-fou anti-collision
                arc = f"{folder}{n}_{doc.filename}"
                n += 1
            used.add(arc)
            zf.write(doc.file_path, arcname=arc)
            added += 1
    if added == 0:
        raise HTTPException(status_code=404, detail="Relevés introuvables")
    buf.seek(0)
    logger.info("📤 [MonthlyBalances] docs-archive: %d relevé(s) → ZIP", added)
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="releves.zip"'},
    )
