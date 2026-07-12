"""
Routes Import CSV — préfixe `/api/import`.

- POST /api/import/preview → analyse sans écriture (dry-run).
- POST /api/import/execute → backup + insertion (périmètre année cible).

Le front envoie le CONTENU du fichier (FileReader) en JSON — pas de multipart.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.db.base import get_db
from backend.logging_config import get_logger
from backend.services import csv_import

logger = get_logger("imports", channel="api")

router = APIRouter(prefix="/api/import", tags=["import"])


class ImportIn(BaseModel):
    content: str = Field(min_length=1)
    year: int = 2025


@router.post("/preview")
def preview(body: ImportIn, db: Session = Depends(get_db)) -> dict:
    logger.info("📥 [Import] POST /preview (%d caractères)", len(body.content))
    try:
        return csv_import.analyze(db, body.content, year=body.year)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/execute")
def execute(body: ImportIn, db: Session = Depends(get_db)) -> dict:
    logger.info("📥 [Import] POST /execute (%d caractères)", len(body.content))
    try:
        return csv_import.execute(db, body.content, year=body.year)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
