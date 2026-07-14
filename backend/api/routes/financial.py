"""
Routes État financier.

- GET/PUT /api/accountant-statement/{year} : compte de résultat VALIDÉ du
  comptable, saisi/stocké par exercice (jamais en dur).
- GET /api/financial-statement?year= : CdR de l'app (calculé) en face du
  comptable + pont de réconciliation qui se ferme au centime.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from backend.db import models
from backend.db.base import get_db
from backend.logging_config import get_logger
from backend.services import pnl as pnl_service

logger = get_logger("financial", channel="api")

router = APIRouter(prefix="/api", tags=["financial"])

_Q = Decimal("0.01")


class AccountantStatementIn(BaseModel):
    """Chiffres du compte de résultat validé (tous optionnels, défaut 0)."""

    production_vendue: Decimal = Decimal("0")
    charges_exploitation: Decimal = Decimal("0")
    resultat_exploitation: Decimal = Decimal("0")
    produits_financiers: Decimal = Decimal("0")
    charges_financieres: Decimal = Decimal("0")
    resultat_financier: Decimal = Decimal("0")
    dotations_amortissements: Decimal = Decimal("0")
    provision_change: Decimal = Decimal("0")
    is_amount: Decimal = Decimal("0")
    resultat_net: Decimal = Decimal("0")
    note: str = ""


class AccountantStatementOut(AccountantStatementIn):
    model_config = ConfigDict(from_attributes=True)

    year: int


@router.get("/accountant-statement/{year}", response_model=AccountantStatementOut)
def get_accountant_statement(year: int, db: Session = Depends(get_db)) -> models.AccountantStatement:
    row = db.get(models.AccountantStatement, year)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aucun compte de résultat comptable pour cet exercice")
    return row


@router.put("/accountant-statement/{year}", response_model=AccountantStatementOut)
def upsert_accountant_statement(
    year: int, payload: AccountantStatementIn, db: Session = Depends(get_db)
) -> models.AccountantStatement:
    """Enregistre (ou remplace) les chiffres comptable d'un exercice."""
    row = db.get(models.AccountantStatement, year)
    if row is None:
        row = models.AccountantStatement(year=year)
        db.add(row)
    for field, value in payload.model_dump().items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    logger.info("📤 [Financial] upsert accountant-statement: année=%d ✅", year)
    return row


@router.get("/financial-statement")
def financial_statement(year: int, db: Session = Depends(get_db)) -> dict:
    """
    Compte de résultat de l'app (calculé) + comptable (stocké) + pont de
    réconciliation. Le pont se ferme : résidu = app − dotations − provision −
    comptable ; ses postes somment exactement au résultat net comptable.
    """
    core = pnl_service.summary(db, year)
    detail = pnl_service.annual_detail(db, year)
    revenue = Decimal(core["revenue_eur"])
    charges = Decimal(core["charges_eur"])
    fin_income = Decimal(core["financial_income_eur"])
    is_est = Decimal(core["is_estimate_eur"])
    net = Decimal(core["net_result_eur"])
    # Résultat d'exploitation = produits − charges (avant financier / IS).
    resultat_exploitation = revenue - charges
    app_side = {
        "production_vendue": revenue,
        "charges_exploitation": charges,
        "charges_by_poste": [
            {"poste": c["category"], "montant": _q(Decimal(c["total_eur"]))}
            for c in detail.get("charges_by_category", [])
        ],
        "resultat_exploitation": resultat_exploitation,
        "produits_financiers": fin_income,
        "is_estimate": is_est,
        "resultat_net": net,
        # Rétro-compat : ancien champ « resultat » = résultat net.
        "resultat": net,
    }
    app_result = net

    row = db.get(models.AccountantStatement, year)
    accountant: Optional[dict] = None
    bridge: list[dict] = []
    if row is not None:
        accountant = {
            "production_vendue": Decimal(row.production_vendue),
            "charges_exploitation": Decimal(row.charges_exploitation),
            "resultat_exploitation": Decimal(row.resultat_exploitation),
            "produits_financiers": Decimal(row.produits_financiers),
            "charges_financieres": Decimal(row.charges_financieres),
            "resultat_financier": Decimal(row.resultat_financier),
            "dotations_amortissements": Decimal(row.dotations_amortissements),
            "provision_change": Decimal(row.provision_change),
            "is_amount": Decimal(row.is_amount),
            "resultat_net": Decimal(row.resultat_net),
            "note": row.note,
        }
        dot = accountant["dotations_amortissements"]
        prov = accountant["provision_change"]
        acc_result = accountant["resultat_net"]
        residual = app_result - dot - prov - acc_result
        bridge = [
            {"label": "Résultat net — App", "amount": _q(app_result), "anchor": True},
            {"label": "− Dotations aux amortissements", "amount": _q(-dot)},
            {"label": "− Provision pour perte de change", "amount": _q(-prov)},
            {"label": "− Écarts de classement charges + méthode FX", "amount": _q(-residual)},
            {"label": "Résultat net — Comptable", "amount": _q(acc_result), "anchor": True},
        ]

    app_out = {
        k: (_q(v) if isinstance(v, Decimal) else v) for k, v in app_side.items()
    }
    return {
        "year": year,
        "is_regime": core["is_regime"],
        "app": app_out,
        "accountant": {k: (_q(v) if isinstance(v, Decimal) else v) for k, v in accountant.items()} if accountant else None,
        "bridge": bridge,
    }


def _q(d: Decimal) -> Decimal:
    return Decimal(d).quantize(_Q)
