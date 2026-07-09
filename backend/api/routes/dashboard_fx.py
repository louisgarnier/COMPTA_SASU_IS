"""
Route Dashboard FX / Conversions — taux de change réel appliqué aux factures.

- GET /api/dashboard/fx-conversions
    → { conversions:[{date, currency, foreign, eur, rate}],
        invoices:[{invoice_number, month, client_code, currency, native,
                   date_received, rate, eur_received, composite, parts:[...]}],
        leftover:{ccy: foreign}, uncovered:{ccy: foreign},
        totals:{ccy:{converted_foreign, income_foreign, realized_eur}} }

Lecture seule (n'écrit rien) : reflète l'allocation FX réelle (cf. services/fx_realized).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.db.base import get_db
from backend.logging_config import get_logger
from backend.services import fx_realized

logger = get_logger("dashboard_fx", channel="api")

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/fx-conversions")
def get_fx_conversions(db: Session = Depends(get_db)) -> dict:
    """Rapport FX : conversions brutes + taux réel/composé par facture + reliquat."""
    logger.info("📥 [FX] get: rapport conversions")
    return fx_realized.fx_report(db)
