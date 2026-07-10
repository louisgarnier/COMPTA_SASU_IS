"""
Service Cashflow mensuel LGC — encaissements / décaissements par devise.

Vue trésorerie « flux » : pour chaque mois de l'exercice, l'argent qui ENTRE
(incoming) et qui SORT (outgoing), ventilé par devise (exprimé en EUR).

- Mois écoulés + mois en cours → RÉEL : produits/charges opérationnels des
  transactions, mêmes règles d'exclusion que le P&L (kinds/catégories non
  opérationnels ignorés).
- Mois futurs → PRÉVISION :
  - incoming : encaissements ATTENDUS depuis les factures non payées
    (`status ∈ {forecast, due}`), bucketisés sur la **date de paiement attendue**
    (facture `due` → `due_date` ; facture `forecast` → fin du mois de service +
    délai de paiement du client), groupés par devise du client (montant EUR).
  - outgoing : charges prévisionnelles du mois (moyenne des mois écoulés),
    agrégat EUR → bucket unique « EUR ».

Un euro porte deux dates : le cashflow le compte quand il est ENCAISSÉ (à 45j),
là où le P&L le compte quand il est GAGNÉ (mois travaillé). L'écart est normal.

`is_forecast` = mois strictement postérieur au mois courant (today).
Tous les montants en `Decimal` 2 décimales.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from backend.db import models
from backend.logging_config import get_logger
from backend.services import forecast as forecast_service
from backend.services.fx import load_rates
from backend.services.pnl import (
    _EXCLUDED_CATEGORY_TYPES,
    _EXCLUDED_KINDS,
    invoice_revenue_eur,
)
from backend.services.treasury import eur_amount, q2

logger = get_logger("cashflow", channel="api")

_ZERO = Decimal("0")
_DEFAULT_TERMS = 45

# Niveau de certitude (sélecteur dashboard) → statuts de factures projetés.
# realized : rien d'attendu (réel uniquement) ; engaged : factures ÉMISES ;
# forecast : émises + prévisions (+ charges projetées) — comportement historique.
SCOPES = ("realized", "engaged", "forecast")
_SCOPE_EXPECTED_STATUSES = {
    "realized": (),
    "engaged": ("due",),
    "forecast": ("forecast", "due"),
}


def _real_month_flows(db: Session, year: int) -> dict[int, dict]:
    """
    Flux réels par mois (1..12) depuis les transactions opérationnelles.

    Retourne {mois: {"in": {ccy: eur}, "out": {ccy: eur_positif}}} en appliquant
    les mêmes exclusions que le P&L (kinds/catégories non opérationnels).
    """
    rates = load_rates(db)
    cat_type = {c.id: c.type for c in db.query(models.Category).all()}
    # Exercice de la facture liée (vue fiscale : un encaissement 2026 d'une
    # facture 2025 est marqué `in_prior` pour pouvoir être exclu).
    inv_month = {
        i.id: i.month for i in db.query(models.Invoice.id, models.Invoice.month).all()
    }

    flows: dict[int, dict] = {
        m: {"in": {}, "out": {}, "in_prior": {}, "out_nonop": {}, "in_nonop": {}}
        for m in range(1, 13)
    }

    # Sorties NON opérationnelles (dividendes, IS payé, investissements) : de
    # vraies sorties de cash, exposées à part pour affichage optionnel — les
    # virements internes et conversions restent exclus (flux internes).
    _NONOP_TYPES = {"distribution", "internal", "investment", "is_payment"}

    for tx in db.query(models.Transaction).all():
        if tx.booked_date is None or tx.booked_date.year != year:
            continue
        ctype = cat_type.get(tx.category_id)
        if ctype in _NONOP_TYPES:
            amt_no = (
                Decimal(tx.amount_eur)
                if tx.amount_eur is not None
                else eur_amount(tx, rates)
            )
            cc = (tx.currency or "EUR").upper()
            if amt_no < 0:
                b = flows[tx.booked_date.month]["out_nonop"]
                b[cc] = b.get(cc, _ZERO) + (-amt_no)  # sorties en magnitude positive
            else:
                # Entrée non-op (remboursement de placement encaissé…) : même
                # bucket optionnel que les sorties, jamais dans l'opérationnel.
                b = flows[tx.booked_date.month]["in_nonop"]
                b[cc] = b.get(cc, _ZERO) + amt_no
            continue
        if (tx.kind or "") in _EXCLUDED_KINDS:
            continue
        if ctype in _EXCLUDED_CATEGORY_TYPES:
            continue

        month = tx.booked_date.month
        # EUR RÉELLEMENT encaissé : `tx.amount_eur` (figé par la conversion réelle
        # Revolut via fx_realized) prime ; repli sur le taux théorique s'il manque.
        amt = (
            Decimal(tx.amount_eur)
            if tx.amount_eur is not None
            else eur_amount(tx, rates)
        )
        ccy = (tx.currency or "EUR").upper()

        # Netting intégral (+ et −), aligné P&L : un remboursement (+) sur charge
        # réduit les sorties du mois ; un avoir client (−) réduit les entrées.
        is_revenue = (tx.kind or "") == "revenue" or ctype == "revenue"
        if is_revenue:
            bucket = flows[month]["in"]
            bucket[ccy] = bucket.get(ccy, _ZERO) + amt
            # Facture d'un exercice antérieur → marqué prior (vue fiscale).
            im = inv_month.get(tx.invoice_id) if tx.invoice_id else None
            if im and not im.startswith(f"{year:04d}"):
                p = flows[month]["in_prior"]
                p[ccy] = p.get(ccy, _ZERO) + amt
        elif ctype == "charge":
            bucket = flows[month]["out"]
            bucket[ccy] = bucket.get(ccy, _ZERO) + (-amt)  # sorties en positif, net

    return flows


def _expected_payment_date(inv: models.Invoice) -> Optional[date]:
    """
    Date d'encaissement ATTENDUE d'une facture non payée.

    - facture `due` (émise) → `due_date` (déjà = émission + délai client).
    - facture `forecast` (non émise) → dernier jour du mois de service +
      `client.payment_terms_days` (émission supposée en fin de mois travaillé).
    """
    if inv.due_date is not None:
        return inv.due_date
    if not inv.month:
        return None
    try:
        y, m = int(inv.month[:4]), int(inv.month[5:7])
    except (ValueError, IndexError):
        return None
    last_day = calendar.monthrange(y, m)[1]
    terms = _DEFAULT_TERMS
    if inv.client is not None and inv.client.payment_terms_days:
        terms = inv.client.payment_terms_days
    return date(y, m, last_day) + timedelta(days=terms)


def _expected_inflows(
    db: Session, year: int, statuses: tuple[str, ...] = ("forecast", "due")
) -> tuple[dict, dict, dict]:
    """
    Encaissements ATTENDUS, ventilés pour les deux vues (caisse / fiscale).

    Retourne (within, within_prior, overflow) :
    - within : {mois 'YYYY-MM' → {ccy: eur}} — date de paiement attendue dans `year` ;
    - within_prior : sous-ensemble de `within` dont la FACTURE est d'un exercice
      antérieur (exclu en vue fiscale) ;
    - overflow : {ccy: eur} — factures de l'exercice `year` attendues APRÈS le
      31/12 (ex. déc payée mi-février) : hors barres caisse, comptées en fiscal.
    Les factures `paid` sont exclues (leur cash est déjà dans le réel).
    """
    rates = load_rates(db)
    within: dict[str, dict] = {}
    within_prior: dict[str, dict] = {}
    overflow: dict[str, Decimal] = {}
    if not statuses:
        return within, within_prior, overflow
    invoices = (
        db.query(models.Invoice)
        .filter(models.Invoice.status.in_(statuses))
        .all()
    )
    for inv in invoices:
        pay_date = _expected_payment_date(inv)
        if pay_date is None:
            continue
        ccy = (
            (inv.client.currency if inv.client else None) or inv.currency or "EUR"
        ).upper()
        eur = invoice_revenue_eur(inv, rates)
        is_year_invoice = (inv.month or "").startswith(f"{year:04d}")
        if pay_date.year == year:
            key = f"{pay_date.year:04d}-{pay_date.month:02d}"
            bucket = within.setdefault(key, {})
            bucket[ccy] = bucket.get(ccy, _ZERO) + eur
            if not is_year_invoice:
                p = within_prior.setdefault(key, {})
                p[ccy] = p.get(ccy, _ZERO) + eur
        elif pay_date.year > year and is_year_invoice:
            overflow[ccy] = overflow.get(ccy, _ZERO) + eur
    return within, within_prior, overflow


def _overflow_real(db: Session, year: int) -> dict[str, Decimal]:
    """Encaissements RÉELS d'années suivantes pour des factures de `year`."""
    out: dict[str, Decimal] = {}
    for inv in db.query(models.Invoice).filter(models.Invoice.status == "paid").all():
        if not (inv.month or "").startswith(f"{year:04d}"):
            continue
        if inv.paid_date is None or inv.paid_date.year <= year:
            continue
        ccy = (
            (inv.client.currency if inv.client else None) or inv.currency or "EUR"
        ).upper()
        out[ccy] = out.get(ccy, _ZERO) + Decimal(inv.amount_eur_received or 0)
    return out


def _fiscal_nonop_flows(
    db: Session, year: int, scope: str, today: Optional[date] = None
) -> dict[str, dict]:
    """
    Flux non-op RATTACHÉS à l'exercice `year` (vue « Année fiscale »).

    Règle validée 2026-07-10 :
    - placements (catégorie type 'internal') : événements patrimoniaux datés →
      tous les flux de l'année, tels quels ;
    - distributions : imputation CHRONOLOGIQUE sur le pool des exercices
      antérieurs (`pnl.retained_earnings`, même chiffre que « Report à nouveau
      initial » du widget P&L, même scope) — seul l'EXCÉDENT au-delà du pool
      est un acompte sur l'exercice, affiché au mois du virement (un virement
      peut être à cheval) ;
    - IS payé : même modèle — pool = IS estimé de N-1 (0 si exercice pré-IS)
      − IS déjà payé avant l'exercice ; l'excédent = acomptes IS de N.

    Retourne {month_key: {"in": {ccy: eur}, "out": {ccy: eur_positif}}}.
    """
    from backend.services import pnl as pnl_service

    rates = load_rates(db)
    cat_type = {c.id: c.type for c in db.query(models.Category).all()}
    flows: dict[str, dict] = {
        f"{year:04d}-{m:02d}": {"in": {}, "out": {}} for m in range(1, 13)
    }

    def _eur(tx) -> Decimal:
        return (
            Decimal(tx.amount_eur) if tx.amount_eur is not None else eur_amount(tx, rates)
        )

    def _add(bucket: dict, tx, value: Decimal) -> None:
        cc = (tx.currency or "EUR").upper()
        bucket[cc] = bucket.get(cc, _ZERO) + value

    txs = sorted(
        (
            t
            for t in db.query(models.Transaction).all()
            if t.booked_date is not None and t.booked_date.year == year
        ),
        key=lambda t: (t.booked_date, t.id),
    )

    # Placements : tous les flux datés de l'exercice.
    for tx in txs:
        if cat_type.get(tx.category_id) != "internal":
            continue
        amt = _eur(tx)
        key = f"{year:04d}-{tx.booked_date.month:02d}"
        if amt < 0:
            _add(flows[key]["out"], tx, -amt)
        else:
            _add(flows[key]["in"], tx, amt)

    # Imputation FIFO d'une famille de flux sortants sur un pool antérieur :
    # l'excédent cumulé au-delà du pool appartient à l'exercice.
    def _fifo_excess(ctype: str, pool: Decimal) -> None:
        cum = _ZERO
        for tx in txs:
            if cat_type.get(tx.category_id) != ctype:
                continue
            amt = -_eur(tx)  # sorties en magnitude positive
            if amt <= 0:
                continue
            before = cum
            cum += amt
            excess = max(_ZERO, cum - pool) - max(_ZERO, before - pool)
            if excess > 0:
                key = f"{year:04d}-{tx.booked_date.month:02d}"
                _add(flows[key]["out"], tx, excess)

    pool_dist = max(
        _ZERO, Decimal(pnl_service.retained_earnings(db, year, today=today, scope=scope))
    )
    _fifo_excess("distribution", pool_dist)

    # Pool IS : dû au titre de N-1 (0 si pré-IS), net de ce qui a déjà été payé.
    is_due_prev = Decimal(
        pnl_service._scope_result(db, year - 1, scope, today=today)["is_estimate_eur"]
    )
    ispay_ids = {cid for cid, t in cat_type.items() if t == "is_payment"}
    paid_before = _ZERO
    if ispay_ids:
        for t in db.query(models.Transaction).all():
            if (
                t.category_id in ispay_ids
                and t.booked_date is not None
                and t.booked_date.year < year
            ):
                paid_before += -_eur(t)
    pool_is = max(_ZERO, is_due_prev - paid_before)
    _fifo_excess("is_payment", pool_is)

    return flows


def monthly_cashflow(
    db: Session, year: int, today: Optional[date] = None, scope: str = "forecast"
) -> dict:
    """
    Encaissements/décaissements par mois et par devise pour l'exercice `year`.

    `scope` (sélecteur de certitude du dashboard) :
    - 'realized' : réel uniquement — aucun encaissement attendu, aucune charge
      projetée (le futur est éteint) ;
    - 'engaged'  : + échéances des factures ÉMISES (dues), sans charges projetées ;
    - 'forecast' : + prévisions saisies + charges projetées (défaut, historique).
    """
    if today is None:
        today = date.today()
    if scope not in SCOPES:
        scope = "forecast"
    current = (today.year, today.month)

    real = _real_month_flows(db, year)
    forecast_in, forecast_in_prior, overflow_expected = _expected_inflows(
        db, year, statuses=_SCOPE_EXPECTED_STATUSES[scope]
    )
    overflow_real = _overflow_real(db, year)
    if scope == "forecast":
        projection = forecast_service.project(db, year, today=today)
        forecast_charge = {
            m["month"]: m["charges_forecast_eur"] for m in projection["months"]
        }
    else:
        forecast_charge = {}

    # Remboursements de placements ATTENDUS (scope prévisionnel) : le cash
    # revient en banque au mois d'échéance. Placements ouverts uniquement, et
    # jamais dans le passé (une échéance dépassée sans clôture = pas encaissé).
    # Vue fiscale : flux non-op rattachés à l'exercice (placements datés +
    # excédents dividendes/IS au-delà des pools antérieurs).
    fiscal_nonop = _fiscal_nonop_flows(db, year, scope, today=today)

    redemption_in: dict[str, Decimal] = {}
    if scope == "forecast":
        for inv in db.query(models.Investment).all():
            if (
                inv.closed_date is None
                and inv.expected_value_eur is not None
                and (inv.expected_month or "")[:4] == f"{year:04d}"
            ):
                em = inv.expected_month
                if (int(em[:4]), int(em[5:7])) >= current:
                    redemption_in[em] = redemption_in.get(em, _ZERO) + Decimal(
                        inv.expected_value_eur
                    )

    months = []
    total_in = _ZERO
    total_out = _ZERO

    for m in range(1, 13):
        key = f"{year:04d}-{m:02d}"
        pos = (year, m)
        is_forecast = pos > current
        # Part ATTENDUE (non encaissée) exposée séparément : le front l'affiche
        # pâle et l'exclut du « Réel » — couleur pleine = argent en banque.
        expected: dict = {}
        # Parts liées à des factures d'exercices ANTÉRIEURS (vue fiscale les retire).
        prior_real: dict = {}
        prior_expected: dict = dict(forecast_in_prior.get(key, {}))
        out_forecast = _ZERO

        if is_forecast:
            # Futur strict : tout prévisionnel.
            incoming = dict(forecast_in.get(key, {}))
            expected = dict(incoming)
            chg = Decimal(forecast_charge.get(key, _ZERO))
            outgoing = {"EUR": chg} if chg > 0 else {}
            out_forecast = chg if chg > 0 else _ZERO
        elif pos == current:
            # Mois en cours : réel DÉJÀ encaissé + attendu RESTANT (factures non
            # encore payées dont l'échéance tombe ce mois). Côté sorties, réel
            # engagé + prorata des jours restants (charges_forecast = restant seul).
            incoming = dict(real[m]["in"])
            prior_real = dict(real[m]["in_prior"])
            for c, v in forecast_in.get(key, {}).items():
                incoming[c] = incoming.get(c, _ZERO) + v
                expected[c] = expected.get(c, _ZERO) + v

            outgoing = dict(real[m]["out"])
            chg = Decimal(forecast_charge.get(key, _ZERO))
            if chg > 0:
                outgoing["EUR"] = outgoing.get("EUR", _ZERO) + chg
                out_forecast = chg
        else:
            # Passé : réel uniquement.
            incoming = dict(real[m]["in"])
            prior_real = dict(real[m]["in_prior"])
            outgoing = dict(real[m]["out"])
            prior_expected = {}

        nonop = (
            {c: q2(v) for c, v in sorted(real[m]["out_nonop"].items())}
            if not is_forecast
            else {}
        )
        # Entrées non-op : réelles (remboursements encaissés) + ATTENDUES
        # (échéance de placement, scope prévisionnel) — symétriques des sorties
        # non-op : la sortie initiale vers le placement était non-op, son retour
        # aussi. Hors totaux opérationnels, affichage via le même toggle.
        nonop_in: dict = {} if is_forecast else dict(real[m]["in_nonop"])
        red = redemption_in.get(key)
        if red:
            nonop_in["EUR"] = nonop_in.get("EUR", _ZERO) + red
        nonop_in = {c: q2(v) for c, v in sorted(nonop_in.items())}
        # Variante fiscale des non-op (le remboursement attendu est un flux de
        # placement de l'exercice : présent dans les deux vues).
        fno = fiscal_nonop.get(key, {"in": {}, "out": {}})
        fno_in = dict(fno["in"])
        if red:
            fno_in["EUR"] = fno_in.get("EUR", _ZERO) + red
        fno_in = {c: q2(v) for c, v in sorted(fno_in.items())}
        fno_out = {c: q2(v) for c, v in sorted(fno["out"].items())}
        incoming = {c: q2(v) for c, v in sorted(incoming.items())}
        outgoing = {c: q2(v) for c, v in sorted(outgoing.items())}
        expected = {c: q2(v) for c, v in sorted(expected.items())}
        prior_real = {c: q2(v) for c, v in sorted(prior_real.items())}
        prior_expected = {c: q2(v) for c, v in sorted(prior_expected.items())}
        incoming_eur = q2(sum(incoming.values(), _ZERO))
        outgoing_eur = q2(sum(outgoing.values(), _ZERO))
        total_in += incoming_eur
        total_out += outgoing_eur

        months.append(
            {
                "month": key,
                "incoming_by_ccy": incoming,
                "outgoing_by_ccy": outgoing,
                "incoming_eur": incoming_eur,
                "outgoing_eur": outgoing_eur,
                "incoming_expected_by_ccy": expected,
                "incoming_expected_eur": q2(sum(expected.values(), _ZERO)),
                "outgoing_forecast_eur": q2(out_forecast),
                # Vue fiscale : parts à retirer (factures d'exercices antérieurs).
                "incoming_prior_by_ccy": prior_real,
                "incoming_prior_expected_by_ccy": prior_expected,
                # Flux non opérationnels (dividendes/IS/investissements).
                "incoming_nonop_by_ccy": nonop_in,
                "incoming_nonop_eur": q2(sum(nonop_in.values(), _ZERO)),
                "outgoing_nonop_by_ccy": nonop,
                # Variante « année fiscale » : rattachés à l'exercice.
                "incoming_nonop_fiscal_by_ccy": fno_in,
                "incoming_nonop_fiscal_eur": q2(sum(fno_in.values(), _ZERO)),
                "outgoing_nonop_fiscal_by_ccy": fno_out,
                "outgoing_nonop_fiscal_eur": q2(sum(fno_out.values(), _ZERO)),
                "outgoing_nonop_eur": q2(sum(nonop.values(), _ZERO)),
                "is_forecast": is_forecast,
            }
        )

    logger.info(
        "📤 [Cashflow] compute: année=%s entrées=%s sorties=%s ✅",
        year,
        q2(total_in),
        q2(total_out),
    )
    return {
        "year": year,
        "months": months,
        "totals": {
            "incoming_eur": q2(total_in),
            "outgoing_eur": q2(total_out),
            "net_eur": q2(total_in - total_out),
        },
        # Débordement fiscal : factures de l'exercice encaissées / attendues
        # APRÈS le 31/12 (ex. déc payée mi-février N+1). Hors vue caisse.
        "overflow": {
            "expected_by_ccy": {c: q2(v) for c, v in sorted(overflow_expected.items())},
            "real_by_ccy": {c: q2(v) for c, v in sorted(overflow_real.items())},
        },
    }
