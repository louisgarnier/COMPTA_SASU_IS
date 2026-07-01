"""
Routes Justificatifs de solde LGC.

Téléversement de relevés officiels (PDF/image) rattachés à un compte, stockés
localement dans `data/balance_docs/`, listables et re-téléchargeables.

- GET    /api/balance-docs                 → liste (filtrable par account_uid)
- POST   /api/balance-docs                 → upload (multipart: file + méta)
- GET    /api/balance-docs/{id}/download   → télécharge le fichier
- DELETE /api/balance-docs/{id}            → supprime la ligne + le fichier
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from backend.db import models
from backend.db.base import get_db
from backend.logging_config import get_logger

logger = get_logger("balance_docs", channel="api")

router = APIRouter(prefix="/api/balance-docs", tags=["balance-docs"])

DOCS_DIR = Path(__file__).resolve().parents[2] / "data" / "balance_docs"
DOCS_DIR.mkdir(parents=True, exist_ok=True)

_ALLOWED = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
}
_MAX_BYTES = 20 * 1024 * 1024  # 20 Mo


def _safe_name(name: str) -> str:
    """Nettoie un nom de fichier pour le stockage (pas de traversal)."""
    base = Path(name or "document").name
    return re.sub(r"[^A-Za-z0-9._-]", "_", base)[:120] or "document"


class BalanceDocOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_uid: Optional[str] = None
    label: str
    doc_date: Optional[date] = None
    filename: str
    content_type: str
    size_bytes: int


@router.get("", response_model=list[BalanceDocOut])
def list_docs(
    account_uid: Optional[str] = None, db: Session = Depends(get_db)
) -> list[models.BalanceDocument]:
    """Liste les justificatifs, filtrés par compte si fourni."""
    q = db.query(models.BalanceDocument)
    if account_uid:
        q = q.filter(models.BalanceDocument.account_uid == account_uid)
    return q.order_by(models.BalanceDocument.uploaded_at.desc()).all()


@router.post("", response_model=BalanceDocOut, status_code=201)
async def upload_doc(
    file: UploadFile = File(...),
    account_uid: Optional[str] = Form(default=None),
    label: str = Form(default=""),
    doc_date: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
) -> models.BalanceDocument:
    """Téléverse un justificatif (PDF/image) et le stocke localement."""
    content_type = (file.content_type or "").lower()
    if content_type not in _ALLOWED:
        raise HTTPException(
            status_code=415,
            detail=f"Type non supporté ({content_type}). PDF ou image attendus.",
        )

    data = await file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="Fichier trop volumineux (max 20 Mo).")

    parsed_date: Optional[date] = None
    if doc_date:
        try:
            parsed_date = date.fromisoformat(doc_date)
        except ValueError:
            parsed_date = None

    doc = models.BalanceDocument(
        account_uid=account_uid or None,
        label=label or "",
        doc_date=parsed_date,
        filename=_safe_name(file.filename or "document"),
        file_path="",
        content_type=content_type,
        size_bytes=len(data),
    )
    db.add(doc)
    db.flush()  # obtient l'id

    stored = DOCS_DIR / f"{doc.id}_{doc.filename}"
    stored.write_bytes(data)
    doc.file_path = str(stored)
    db.commit()
    db.refresh(doc)
    logger.info(
        "📥 [BalanceDocs] upload: #%s %s (%d octets) ✅",
        doc.id,
        doc.filename,
        doc.size_bytes,
    )
    return doc


@router.get("/{doc_id}/download")
def download_doc(doc_id: int, db: Session = Depends(get_db)) -> FileResponse:
    """Télécharge le fichier d'un justificatif."""
    doc = db.get(models.BalanceDocument, doc_id)
    if doc is None or not Path(doc.file_path).exists():
        raise HTTPException(status_code=404, detail="Justificatif introuvable")
    return FileResponse(
        doc.file_path,
        media_type=doc.content_type or "application/octet-stream",
        filename=doc.filename,
    )


@router.delete("/{doc_id}", status_code=204)
def delete_doc(doc_id: int, db: Session = Depends(get_db)) -> None:
    """Supprime un justificatif (ligne + fichier local)."""
    doc = db.get(models.BalanceDocument, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Justificatif introuvable")
    try:
        Path(doc.file_path).unlink(missing_ok=True)
    except OSError:
        pass
    db.delete(doc)
    db.commit()
    logger.info("🗑️ [BalanceDocs] delete: #%s ✅", doc_id)
