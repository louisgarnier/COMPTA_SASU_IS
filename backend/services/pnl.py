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

Niveaux de certitude (`scope`) : realized (payées seules, EUR réel) /
engaged (+ émises, défaut) / forecast (+ prévisions, charges projetées,
IS projeté) — `_scope_result` est partagé par `summary` (affichage) et
`retained_earnings` (chaînage du RAN) pour garantir leur cohérence.
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
_EXCLUDED_CATEGORY_TYPES = {"conversion", "transfer", "internal", "distribution", "is_payment"}


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


def monthly_pnl(
    db: Session, year: int, statuses: tuple[str, ...] = ("due", "paid")
) -> dict:
    """
    Agrège produits, charges et résultat par mois pour l'exercice `year`.

    `statuses` : statuts de factures reconnus en produits (sélecteur de
    certitude — realized ('paid',) / engaged ('due','paid') / forecast
    ('forecast','due','paid')).
    """
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
        .filter(models.Invoice.status.in_(statuses))
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
        # EUR réel (`amount_eur`, figé par l'allocation FX) prioritaire ;
        # repli théorique sinon — aligné sur le cashflow et le pont tréso.
        amt = (
            Decimal(tx.amount_eur)
            if tx.amount_eur is not None
            else eur_amount(tx, rates)
        )

        # Netting intégral (+ et −) : un remboursement (+) sur une catégorie
        # charge vient en DÉDUCTION des charges (avoir fournisseur) ; un avoir
        # client (−) en déduction du CA. Les montants sont sommés SIGNÉS.
        is_revenue = (tx.kind or "") == "revenue" or ctype == "revenue"
        if is_revenue:
            # Rattachée à une facture → déjà comptée côté facture (accrual).
            if tx.invoice_id is not None:
                continue
            revenue[month] += amt
            ccy = (tx.currency or "EUR").upper()
            currencies.add(ccy)
            revenue_ccy[month][ccy] = revenue_ccy[month].get(ccy, _ZERO) + amt
            revenue_native[ccy] = revenue_native.get(ccy, _ZERO) + Decimal(
                tx.amount or 0
            )
        elif ctype == "charge":
            charges[month] += amt
            cc = (tx.currency or "EUR").upper()
            charge_currencies.add(cc)
            charges_eur_ccy[cc] = charges_eur_ccy.get(cc, _ZERO) + amt
            charges_native_ccy[cc] = charges_native_ccy.get(cc, _ZERO) + Decimal(
                tx.amount or 0
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


def annual_detail(db: Session, year: int) -> dict:
    """
    Détail annuel pour la clôture (page P&L imprimable) :
    - `months` : produits/charges/résultat mensuels (= monthly_pnl, engagé) ;
    - `charges_by_category` : une ligne par catégorie de type charge ayant des
      mouvements — total EUR net (magnitude positive) + ventilation 12 mois.
    Somme des lignes == total charges du P&L (même valorisation : EUR réel
    prioritaire, netting des remboursements).
    """
    pnl = monthly_pnl(db, year)
    rates = load_rates(db)
    cats = {c.id: c for c in db.query(models.Category).all()}

    by_cat: dict[str, list[Decimal]] = {}
    for tx in db.query(models.Transaction).all():
        if tx.booked_date is None or tx.booked_date.year != year:
            continue
        if (tx.kind or "") in _EXCLUDED_KINDS:
            continue
        cat = cats.get(tx.category_id)
        if cat is None or cat.type != "charge":
            continue
        amt = (
            Decimal(tx.amount_eur)
            if tx.amount_eur is not None
            else eur_amount(tx, rates)
        )
        row = by_cat.setdefault(cat.name, [_ZERO] * 12)
        row[tx.booked_date.month - 1] += -amt  # magnitude positive, net

    charges_by_category = [
        {
            "category": name,
            "by_month": [q2(v) for v in months],
            "total_eur": q2(sum(months, _ZERO)),
        }
        for name, months in sorted(by_cat.items(), key=lambda kv: -sum(kv[1], _ZERO))
    ]
    logger.info(
        "📤 [PnL] annual_detail: année=%s, %d catégorie(s) de charges ✅",
        year, len(charges_by_category),
    )
    return {
        "year": year,
        "months": pnl["months"],
        "totals": pnl["totals"],
        "charges_by_category": charges_by_category,
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


def _activity_years(db: Session) -> set[int]:
    """Exercices ayant de l'activité (factures ou transactions)."""
    years: set[int] = set()
    for (m,) in db.query(models.Invoice.month).all():
        if m and len(m) >= 4 and m[:4].isdigit():
            years.add(int(m[:4]))
    for (d,) in db.query(models.Transaction.booked_date).all():
        if d is not None:
            years.add(d.year)
    return years


def _distributions_before(db: Session, year: int, rates: dict) -> Decimal:
    """
    Σ des distributions (dividendes/salaire dirigeant) versées AVANT `year`,
    en magnitude positive. Une distribution = transaction sortante dont la
    catégorie est de type 'distribution' (marquage par l'utilisateur dans
    Catégories — aucun nom en dur).
    """
    dist_ids = {
        c.id for c in db.query(models.Category).all() if c.type == "distribution"
    }
    if not dist_ids:
        return _ZERO
    total = _ZERO
    for tx in db.query(models.Transaction).all():
        if tx.category_id not in dist_ids or tx.booked_date is None:
            continue
        if tx.booked_date.year >= year:
            continue
        amt = (
            Decimal(tx.amount_eur)
            if tx.amount_eur is not None
            else eur_amount(tx, rates)
        )
        total += -amt  # sorties négatives → magnitude positive
    return total


_SCOPE_STATUSES = {
    "realized": ("paid",),
    "engaged": ("due", "paid"),
    "forecast": ("forecast", "due", "paid"),
}


def _scope_result(db: Session, year: int, scope: str, today=None) -> dict:
    """
    Cœur de calcul PARTAGÉ par `summary` (affichage) et `retained_earnings`
    (chaînage) — garantie structurelle : le net affiché pour un exercice dans
    un cran == le net chaîné dans le RAN de l'exercice suivant, même cran.

    Retourne {revenue_eur, charges_eur, result_eur, is_estimate_eur,
    net_result_eur, pre_is, pnl} (montants q2, charges en magnitude positive).
    """
    if scope not in _SCOPE_STATUSES:
        scope = "engaged"
    pnl = monthly_pnl(db, year, statuses=_SCOPE_STATUSES[scope])
    totals = pnl["totals"]
    revenue_eur = q2(totals["revenue_eur"])
    charges_eur = q2(abs(totals["charges_eur"]))
    if scope == "forecast":
        # Charges réelles + PROJETÉES — même source que la page Heures & jours.
        projection = forecast_service.project(db, year, today=today)
        charges_eur = q2(Decimal(str(projection["totals"]["charges_eur"])))
    result_eur = q2(revenue_eur - charges_eur)

    settings = _get_settings(db)
    pre_is = settings.is_start_year is not None and year < settings.is_start_year
    if pre_is:
        is_estimate_eur = q2(_ZERO)
    elif scope == "forecast":
        # IS PROJETÉ fin d'exercice (base projection + PV latentes).
        is_estimate_eur = q2(
            forecast_service.estimate_is(db, year, today=today)["is_total_eur"]
        )
    else:
        is_estimate_eur = q2(
            forecast_service.estimate_is(
                db, year, base_override=result_eur, today=today
            )["is_total_eur"]
        )
    return {
        "revenue_eur": revenue_eur,
        "charges_eur": charges_eur,
        "result_eur": result_eur,
        "is_estimate_eur": is_estimate_eur,
        "net_result_eur": q2(result_eur - is_estimate_eur),
        "pre_is": pre_is,
        "pnl": pnl,
    }


def retained_earnings(
    db: Session, year: int, today=None, scope: str = "engaged"
) -> Decimal:
    """
    Report à nouveau AUTOMATIQUE de l'exercice `year` :

    base initiale (Settings — poche pré-IS) + Σ résultats nets des exercices
    IS antérieurs − Σ distributions versées. Le net de chaque exercice est
    calculé AU MÊME niveau de certitude (`scope`) que la vue courante : chaque
    cran (réalisé / engagé / prévisionnel) est un monde auto-cohérent —
    RAN(N+1, cran) == restant distribuable affiché en N dans ce cran.
    """
    settings = _get_settings(db)
    base = Decimal(settings.retained_earnings_eur or 0)
    rates = load_rates(db)

    # Régime IS à partir de `is_start_year` : les exercices antérieurs (ère IR)
    # ne génèrent PAS de report à nouveau — leur stock est dans la poche `base`.
    is_start = settings.is_start_year or 0

    chained = _ZERO
    for y in sorted(y for y in _activity_years(db) if is_start <= y < year):
        chained += _scope_result(db, y, scope, today=today)["net_result_eur"]

    return q2(base + chained - _distributions_before(db, year, rates))


def summary(db: Session, year: int, today=None, scope: str = "engaged") -> dict:
    """
    Résumé P&L pour le dashboard (équation façon FreeAgent).

    Revenus − Charges = Résultat ; Résultat − IS estimé = Résultat net ;
    Résultat net + Report à nouveau = Distribuable. Le report à nouveau est
    CALCULÉ (résultats nets des exercices antérieurs − distributions versées),
    la valeur des Réglages n'étant que la base initiale pré-historique.
    Toutes les charges sont exposées en **magnitude positive**.

    `scope` (sélecteur de certitude) :
    - 'realized' : factures PAYÉES uniquement (EUR réel) + charges réelles ;
    - 'engaged'  : + factures émises (défaut, comportement historique) ;
    - 'forecast' : + prévisions saisies, charges réelles + PROJETÉES, IS
      projeté fin d'exercice — mêmes chiffres que la page « Heures & jours ».
    """
    if scope not in _SCOPE_STATUSES:
        scope = "engaged"
    core = _scope_result(db, year, scope, today=today)
    pnl = core["pnl"]
    totals = pnl["totals"]
    revenue_eur = core["revenue_eur"]
    charges_eur = core["charges_eur"]
    result_eur = core["result_eur"]
    is_estimate_eur = core["is_estimate_eur"]
    net_result_eur = core["net_result_eur"]
    pre_is = core["pre_is"]

    # Le report à nouveau est un concept de l'ère IS : pour un exercice IR,
    # on affiche 0 (le stock de l'époque vit dans la poche initiale, hors P&L).
    retained_earnings_eur = (
        q2(_ZERO) if pre_is else retained_earnings(db, year, today=today, scope=scope)
    )
    distributable_eur = q2(net_result_eur + retained_earnings_eur)
    # Distributions DÉJÀ versées pendant l'exercice (acomptes sur dividendes…) :
    # le distribuable brut ne les retranche pas, on expose donc le « reste ».
    rates = load_rates(db)
    distributed_this_year = q2(
        _distributions_before(db, year + 1, rates) - _distributions_before(db, year, rates)
    )
    remaining_distributable = q2(distributable_eur - distributed_this_year)
    # IS effectivement PAYÉ dans l'exercice (catégorie type 'is_payment') —
    # suivi à part : déjà provisionné dans le net, jamais une charge.
    is_paid = _ZERO
    ispay_ids = {c.id for c in db.query(models.Category).all() if c.type == "is_payment"}
    if ispay_ids:
        for tx in db.query(models.Transaction).all():
            if tx.category_id in ispay_ids and tx.booked_date and tx.booked_date.year == year:
                amt = Decimal(tx.amount_eur) if tx.amount_eur is not None else eur_amount(tx, rates)
                is_paid += -amt
    is_paid = q2(is_paid)

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
        "scope": scope,
        "is_regime": "IR" if pre_is else "IS",
        "revenue_eur": revenue_eur,
        "charges_eur": charges_eur,
        "result_eur": result_eur,
        "is_estimate_eur": is_estimate_eur,
        "net_result_eur": net_result_eur,
        "retained_earnings_eur": retained_earnings_eur,
        "distributable_eur": distributable_eur,
        "distributed_this_year_eur": distributed_this_year,
        "is_paid_eur": is_paid,
        "remaining_distributable_eur": remaining_distributable,
        "by_currency": by_currency,
    }
