"""
Service Compte de résultat mensuel LGC (P&L opérationnel, comptabilité d'engagement).

Périmètre : produits & charges d'exploitation uniquement. On EXCLUT les flux
non opérationnels — kinds 'investment' | 'conversion' | 'transfer' | 'internal'
et toute transaction dont la catégorie est de type
'conversion' | 'transfer' | 'internal'.

Modèle « accrual » (revenu rattaché au mois TRAVAILLÉ, pas au mois payé) :
- Produits (revenue) : factures émises (`status ∈ {due, paid}`) rattachées à leur
  **mois de service** (`Invoice.month`) — le revenu est gagné quand la presta est
  livrée, indépendamment de l'encaissement (paiement à 45j). Filet anti-perte :
  les transactions de revenu NON rattachées à une facture (`invoice_id IS NULL`)
  comptent par `booked_date` (encaissement divers non facturé) ; celles rattachées
  sont exclues (déjà comptées côté facture) → pas de double comptage.
- Charges (charge)  : montants EUR négatifs de catégorie de type 'charge', par
  `booked_date` (base **cash** assumée — pas de facture fournisseur, NG5).
- Résultat = produits + charges (les charges sont déjà négatives).

Douze mois toujours présents (Jan..Déc), remplis à zéro.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from backend.db import models
from backend.logging_config import get_logger
from backend.services import forecast as forecast_service
from backend.services.fx import load_rates, to_eur
from backend.services.treasury import eur_amount, q2

logger = get_logger("pnl", channel="api")

_ZERO = Decimal("0")

# Flux exclus du résultat d'exploitation.
_EXCLUDED_KINDS = {"investment", "conversion", "transfer", "internal"}
_EXCLUDED_CATEGORY_TYPES = {"conversion", "transfer", "internal"}


def invoice_revenue_eur(inv: models.Invoice, rates: dict) -> Decimal:
    """
    Revenu EUR reconnu pour une facture émise (accrual).

    Priorité : montant réellement encaissé (`amount_eur_received`, FX réel) si la
    facture est payée ; sinon montant EUR prévisionnel (`amount_eur_forecast`, FX
    théorique) s'il est renseigné ; sinon conversion théorique du natif `amount`.
    """
    if inv.status == "paid" and inv.amount_eur_received is not None:
        return Decimal(inv.amount_eur_received)
    forecast_eur = Decimal(inv.amount_eur_forecast or 0)
    if forecast_eur > 0:
        return forecast_eur
    return to_eur(inv.amount, inv.currency, rates)


def monthly_pnl(db: Session, year: int) -> dict:
    """Agrège produits, charges et résultat par mois pour l'exercice `year`."""
    rates = load_rates(db)

    # Mapping catégorie -> type (pour éviter N requêtes de relation).
    cat_type = {
        c.id: c.type for c in db.query(models.Category).all()
    }

    # Accumulateurs indexés par mois (1..12).
    revenue = {m: _ZERO for m in range(1, 13)}
    charges = {m: _ZERO for m in range(1, 13)}
    # Produits ventilés par devise d'origine (équivalent EUR), par mois.
    revenue_ccy = {m: {} for m in range(1, 13)}
    # Montant natif cumulé par devise (ex: total en $US, en $CA).
    revenue_native = {}
    currencies: set[str] = set()
    # Charges ventilées par devise (EUR + natif, valeurs négatives).
    charges_eur_ccy = {}
    charges_native_ccy = {}
    charge_currencies: set[str] = set()

    # --- Produits (accrual) : factures émises rattachées au mois de service ---
    year_months = {f"{year:04d}-{m:02d}" for m in range(1, 13)}
    issued = (
        db.query(models.Invoice)
        .filter(models.Invoice.status.in_(("due", "paid")))
        .all()
    )
    for inv in issued:
        if inv.month not in year_months:
            continue
        month = int(inv.month[5:7])
        amt = invoice_revenue_eur(inv, rates)
        if amt <= 0:
            continue
        revenue[month] += amt
        ccy = (inv.currency or "EUR").upper()
        currencies.add(ccy)
        revenue_ccy[month][ccy] = revenue_ccy[month].get(ccy, _ZERO) + amt
        revenue_native[ccy] = revenue_native.get(ccy, _ZERO) + abs(
            Decimal(inv.amount or 0)
        )

    # --- Charges (cash) + filet « revenus non facturés » (invoice_id NULL) ----
    txs = db.query(models.Transaction).all()
    for tx in txs:
        if tx.booked_date is None or tx.booked_date.year != year:
            continue
        if (tx.kind or "") in _EXCLUDED_KINDS:
            continue
        ctype = cat_type.get(tx.category_id)
        if ctype in _EXCLUDED_CATEGORY_TYPES:
            continue

        month = tx.booked_date.month
        amt = eur_amount(tx, rates)

        is_revenue = (tx.kind or "") == "revenue" or ctype == "revenue"
        if is_revenue and amt > 0:
            # Rattachée à une facture → déjà comptée côté facture (accrual).
            if tx.invoice_id is not None:
                continue
            revenue[month] += amt
            ccy = (tx.currency or "EUR").upper()
            currencies.add(ccy)
            revenue_ccy[month][ccy] = revenue_ccy[month].get(ccy, _ZERO) + amt
            revenue_native[ccy] = revenue_native.get(ccy, _ZERO) + abs(
                Decimal(tx.amount or 0)
            )
        elif ctype == "charge" and amt < 0:
            charges[month] += amt
            cc = (tx.currency or "EUR").upper()
            charge_currencies.add(cc)
            charges_eur_ccy[cc] = charges_eur_ccy.get(cc, _ZERO) + amt
            charges_native_ccy[cc] = charges_native_ccy.get(cc, _ZERO) - abs(
                Decimal(tx.amount or 0)
            )

    ccy_order = sorted(currencies)
    charge_ccy_order = sorted(charge_currencies)
    months = []
    total_rev = _ZERO
    total_chg = _ZERO
    totals_by_ccy = {c: _ZERO for c in ccy_order}
    for m in range(1, 13):
        rev = revenue[m]
        chg = charges[m]
        total_rev += rev
        total_chg += chg
        by_ccy = {c: q2(revenue_ccy[m].get(c, _ZERO)) for c in ccy_order}
        for c in ccy_order:
            totals_by_ccy[c] += revenue_ccy[m].get(c, _ZERO)
        months.append(
            {
                "month": f"{year:04d}-{m:02d}",
                "revenue_eur": q2(rev),
                "charges_eur": q2(chg),
                "result_eur": q2(rev + chg),
                "revenue_by_currency": by_ccy,
            }
        )

    logger.info(
        "📤 [PnL] compute: année=%s, produits=%s charges=%s ✅",
        year,
        q2(total_rev),
        q2(total_chg),
    )
    return {
        "year": year,
        "currencies": ccy_order,
        "currencies_all": sorted(currencies | charge_currencies),
        "months": months,
        "totals": {
            "revenue_eur": q2(total_rev),
            "charges_eur": q2(total_chg),
            "result_eur": q2(total_rev + total_chg),
            "revenue_by_currency": {c: q2(totals_by_ccy[c]) for c in ccy_order},
            "revenue_native_by_currency": {
                c: q2(revenue_native.get(c, _ZERO)) for c in ccy_order
            },
            "charges_by_currency": {
                c: q2(charges_eur_ccy.get(c, _ZERO)) for c in charge_ccy_order
            },
            "charges_native_by_currency": {
                c: q2(charges_native_ccy.get(c, _ZERO)) for c in charge_ccy_order
            },
        },
    }


def _get_settings(db: Session) -> models.Settings:
    """Retourne le singleton Settings (id=1), le crée avec les défauts si absent."""
    row = db.get(models.Settings, 1)
    if row is None:
        row = models.Settings(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def summary(db: Session, year: int, today=None) -> dict:
    """
    Résumé P&L pour le dashboard (équation façon FreeAgent).

    Revenus − Charges = Résultat ; Résultat − IS estimé = Résultat net ;
    Résultat net + Report à nouveau = Distribuable. Toutes les charges sont
    exposées en **magnitude positive** (l'équation retranche les charges).

    Tous les montants sont des `Decimal` quantifiés à 2 décimales.
    """
    pnl = monthly_pnl(db, year)
    totals = pnl["totals"]

    revenue_eur = q2(totals["revenue_eur"])
    # monthly_pnl stocke les charges en négatif → magnitude positive ici.
    charges_eur = q2(abs(totals["charges_eur"]))
    result_eur = q2(revenue_eur - charges_eur)

    # IS estimé sur le résultat RÉALISÉ (P&L "live"), pas sur la base forecast :
    # sinon un exercice bénéficiaire afficherait un IS nul tant qu'aucun revenu
    # prévisionnel n'est saisi. base_override = résultat P&L de l'année.
    is_estimate_eur = q2(
        forecast_service.estimate_is(
            db, year, base_override=result_eur, today=today
        )["is_total_eur"]
    )
    net_result_eur = q2(result_eur - is_estimate_eur)

    settings = _get_settings(db)
    retained_earnings_eur = q2(Decimal(settings.retained_earnings_eur or 0))
    distributable_eur = q2(net_result_eur + retained_earnings_eur)

    rev_ccy = totals["revenue_by_currency"]
    rev_native_ccy = totals["revenue_native_by_currency"]
    chg_ccy = totals["charges_by_currency"]
    currencies = sorted(set(rev_ccy) | set(chg_ccy))
    by_currency = [
        {
            "currency": c,
            "revenue_native": q2(rev_native_ccy.get(c, _ZERO)),
            "revenue_eur": q2(rev_ccy.get(c, _ZERO)),
            "charges_eur": q2(abs(chg_ccy.get(c, _ZERO))),
        }
        for c in currencies
    ]

    logger.info(
        "📤 [PnL] summary: année=%s résultat=%s net=%s distribuable=%s ✅",
        year,
        result_eur,
        net_result_eur,
        distributable_eur,
    )
    return {
        "year": year,
        "revenue_eur": revenue_eur,
        "charges_eur": charges_eur,
        "result_eur": result_eur,
        "is_estimate_eur": is_estimate_eur,
        "net_result_eur": net_result_eur,
        "retained_earnings_eur": retained_earnings_eur,
        "distributable_eur": distributable_eur,
        "by_currency": by_currency,
    }
