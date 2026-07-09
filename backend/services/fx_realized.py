"""
Service FX réalisé LGC — taux de change RÉELLEMENT obtenu sur les encaissements
en devise, reconstitué à partir des conversions Revolut appariées.

Contexte métier : les factures USD/CAD sont encaissées en devise, puis converties
en EUR par Revolut — souvent **par lots** (une conversion couvre plusieurs
factures) et **en décalé**. Le taux théorique des Réglages ne reflète pas le taux
réellement obtenu (spread Revolut inclus). Ce service reconstitue le vrai EUR reçu.

Ancre : le solde en devise est **0 aujourd'hui** (tout a fini converti). En
allouant les encaissements aux conversions **à rebours** (du plus récent au plus
ancien), les conversions récentes s'apparient aux encaissements récents ; le
reliquat de conversions anciennes = cash d'un exercice antérieur (salaire /
dividendes) et n'est rattaché à aucune facture.

Appariement des 2 jambes d'une conversion (jambe devise négative + jambe EUR
positive) : par date d'opération puis rang de montant — gère le cas où USD et CAD
sont convertis le même jour.

Tous les montants sont des `Decimal`, jamais des float.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from collections import defaultdict

from sqlalchemy.orm import Session

from backend.db import models
from backend.logging_config import get_logger
from backend.services.fx import load_rates, rate_for

logger = get_logger("fx_realized", channel="backend")

_CENTS = Decimal("0.01")
_RATE = Decimal("0.000001")
_ZERO = Decimal("0")


def _q(v: Decimal) -> Decimal:
    return Decimal(v).quantize(_CENTS, rounding=ROUND_HALF_UP)


def _qr(v: Decimal) -> Decimal:
    return Decimal(v).quantize(_RATE, rounding=ROUND_HALF_UP)


def pair_conversions(db: Session) -> list[dict]:
    """
    Apparie les jambes des conversions en paires {currency, date, foreign, eur, rate}.

    Une conversion Revolut = une jambe devise (montant négatif) + une jambe EUR
    (montant positif), même date d'opération. Quand plusieurs devises sont
    converties le même jour, on apparie par **rang de montant** (plus grosse jambe
    devise ↔ plus grosse jambe EUR).
    """
    foreign_by_date: dict = defaultdict(list)
    eur_by_date: dict = defaultdict(list)
    for tx in db.query(models.Transaction).filter(models.Transaction.kind == "conversion").all():
        amt = Decimal(tx.amount or 0)
        cur = (tx.currency or "").upper()
        if cur == "EUR" and amt > 0:
            eur_by_date[tx.booked_date].append(tx)
        elif cur != "EUR" and amt < 0:
            foreign_by_date[tx.booked_date].append(tx)

    pairs: list[dict] = []
    for d, legs in foreign_by_date.items():
        eur_legs = eur_by_date.get(d, [])
        fs = sorted(legs, key=lambda t: abs(Decimal(t.amount)))
        es = sorted(eur_legs, key=lambda t: Decimal(t.amount))
        if len(fs) != len(es):
            logger.warning(
                "⚠️ [FXReal] appariement conversion incomplet le %s : %d jambe(s) devise vs %d EUR",
                d, len(fs), len(es),
            )
        for f, e in zip(fs, es):
            foreign = abs(Decimal(f.amount))
            eur = Decimal(e.amount)
            pairs.append({
                "currency": (f.currency or "").upper(),
                "date": d,
                "foreign": foreign,
                "eur": eur,
                "rate": (eur / foreign) if foreign else _ZERO,
                "foreign_tx_id": f.id,
                "eur_tx_id": e.id,
            })
    return pairs


def _allocate_currency(incomes: list[dict], convs: list[dict], theo_rate: Decimal) -> dict:
    """
    Alloue **à rebours** les encaissements d'une devise aux conversions.

    `incomes` : [{id, foreign, date}] ; `convs` : [{foreign, rate, date}].
    Renvoie {realized: {income_id: {eur, rate}}, leftover_foreign, uncovered_foreign}.

    Du plus récent au plus ancien : chaque encaissement consomme la devise des
    conversions les plus récentes disponibles. Ce qui reste de conversions après
    épuisement des encaissements = reliquat (exercice antérieur). Un encaissement
    qui n'a plus de conversion disponible retombe sur le taux théorique (non encore
    converti) et est compté en `uncovered_foreign`.
    """
    inc = sorted(incomes, key=lambda x: (x["date"], x["id"]), reverse=True)
    cv = sorted(convs, key=lambda x: (x["date"], x.get("foreign_tx_id", 0)), reverse=True)

    # File de « tranches » de conversion, la plus récente d'abord.
    slices = [[Decimal(c["foreign"]), Decimal(c["rate"]), c["date"]] for c in cv]
    realized: dict = {}
    uncovered = _ZERO
    for x in inc:
        rem = Decimal(x["foreign"])
        eur = _ZERO
        parts: list[dict] = []  # tranches (conversion, portion, taux) écoulant cette facture
        for s in slices:
            if rem <= 0:
                break
            avail, rate, cdate = s
            if avail <= 0:
                continue
            # Contrainte physique : une conversion ne peut écouler que des
            # encaissements ANTÉRIEURS ou égaux à sa date — sinon un paiement
            # de janvier N+1 « volerait » les conversions de N et décalerait
            # l'EUR réel des factures déjà payées (instabilité cross-year).
            if cdate is not None and x["date"] is not None and cdate < x["date"]:
                continue
            take = rem if rem < avail else avail
            eur += take * rate
            parts.append({"date": cdate, "foreign": _q(take), "rate": _qr(rate)})
            rem -= take
            s[0] -= take
        if rem > 0:
            # Plus de conversion disponible → repli théorique sur le reliquat.
            eur += rem * theo_rate
            parts.append({"date": None, "foreign": _q(rem), "rate": _qr(theo_rate)})
            uncovered += rem
        realized[x["id"]] = {
            "eur": _q(eur),
            "rate": _qr(eur / Decimal(x["foreign"])) if x["foreign"] else _ZERO,
            "parts": parts,
            "composite": len(parts) > 1,
        }
    leftover = sum((s[0] for s in slices if s[0] > 0), _ZERO)
    return {
        "realized": realized,
        "leftover_foreign": _q(leftover),
        "uncovered_foreign": _q(uncovered),
    }


def _compute_allocation(db: Session):
    """
    Cœur du calcul (lecture seule) partagé par `allocate` (écriture) et
    `fx_report` (affichage). Retourne (pairs, incomes_by_cur, tx_by_id,
    realized_all, by_currency) — realized_all: {tx_id: {eur, rate, parts, composite}}.
    """
    rates = load_rates(db)
    pairs = pair_conversions(db)
    convs_by_cur: dict = defaultdict(list)
    for p in pairs:
        convs_by_cur[p["currency"]].append(p)

    incomes_by_cur: dict = defaultdict(list)
    tx_by_id: dict = {}
    for tx in db.query(models.Transaction).filter(models.Transaction.kind == "revenue").all():
        cur = (tx.currency or "EUR").upper()
        if cur == "EUR" or Decimal(tx.amount or 0) <= 0:
            continue
        incomes_by_cur[cur].append({"id": tx.id, "foreign": Decimal(tx.amount), "date": tx.booked_date})
        tx_by_id[tx.id] = tx

    realized_all: dict = {}
    by_currency: dict = {}
    for cur, incomes in incomes_by_cur.items():
        convs = convs_by_cur.get(cur, [])
        theo = rate_for(rates, cur)
        alloc = _allocate_currency(incomes, convs, theo)
        realized_all.update(alloc["realized"])
        income_foreign = sum((Decimal(i["foreign"]) for i in incomes), _ZERO)
        conv_foreign = sum((Decimal(c["foreign"]) for c in convs), _ZERO)
        realized_eur = sum((r["eur"] for r in alloc["realized"].values()), _ZERO)
        by_currency[cur] = {
            "income_foreign": _q(income_foreign),
            "conv_foreign": _q(conv_foreign),
            "leftover_foreign": alloc["leftover_foreign"],
            "uncovered_foreign": alloc["uncovered_foreign"],
            "realized_eur": _q(realized_eur),
        }
    return pairs, incomes_by_cur, tx_by_id, realized_all, by_currency


def fx_report(db: Session) -> dict:
    """
    Rapport FX (lecture seule) pour le module « FX / Conversions » du dashboard.

    Trois blocs :
    - `conversions` : paires Revolut brutes (date, devise, montant sorti, EUR reçu,
      taux réel), triées par date.
    - `invoices` : par facture encaissée, le taux réellement appliqué et son détail
      (`composite`=True si à cheval sur 2+ conversions, `parts` = tranches pondérées).
    - `leftover` / `uncovered` : devise convertie au-delà des factures (cash 2025).
    - `totals` : convertis/reçus par devise.
    """
    pairs, _incomes, tx_by_id, realized_all, by_currency = _compute_allocation(db)

    # Nom de client par facture (via la transaction rattachée).
    inv_by_id = {i.id: i for i in db.query(models.Invoice).all()}
    cli_by_id = {c.id: c for c in db.query(models.Client).all()}

    conversions = sorted(
        (
            {
                "date": p["date"].isoformat() if p["date"] else None,
                "currency": p["currency"],
                "foreign": _q(p["foreign"]),
                "eur": _q(p["eur"]),
                "rate": _qr(p["rate"]),
            }
            for p in pairs
        ),
        key=lambda x: (x["date"] or "", x["currency"]),
    )

    invoices: list[dict] = []
    for tx_id, r in realized_all.items():
        tx = tx_by_id[tx_id]
        inv = inv_by_id.get(tx.invoice_id) if tx.invoice_id else None
        client = cli_by_id.get(inv.client_id) if inv else None
        invoices.append({
            "invoice_number": inv.number if inv else None,
            "month": inv.month if inv else None,
            "client_code": client.code if client else None,
            "currency": (tx.currency or "").upper(),
            "native": _q(Decimal(tx.amount or 0)),
            "date_received": tx.booked_date.isoformat() if tx.booked_date else None,
            "rate": r["rate"],
            "eur_received": r["eur"],
            "composite": r["composite"],
            "parts": [
                {
                    "date": pt["date"].isoformat() if pt["date"] else None,
                    "foreign": pt["foreign"],
                    "rate": pt["rate"],
                }
                for pt in r["parts"]
            ],
        })
    invoices.sort(key=lambda x: (x["month"] or "", x["currency"]))

    leftover = {c: v["leftover_foreign"] for c, v in by_currency.items()}
    uncovered = {c: v["uncovered_foreign"] for c, v in by_currency.items()}
    totals = {
        c: {
            "converted_foreign": v["conv_foreign"],
            "income_foreign": v["income_foreign"],
            "realized_eur": v["realized_eur"],
        }
        for c, v in by_currency.items()
    }
    return {
        "conversions": conversions,
        "invoices": invoices,
        "leftover": leftover,
        "uncovered": uncovered,
        "totals": totals,
    }


def allocate(db: Session, commit: bool = True) -> dict:
    """
    Reconstitue et fige le vrai EUR reçu sur chaque encaissement en devise, puis
    le propage aux factures payées (`amount_eur_received` + variance).

    Renvoie un résumé {by_currency: {cur: {income_foreign, conv_foreign,
    leftover_foreign, uncovered_foreign, realized_eur}}, invoices_updated}.
    """
    pairs, incomes_by_cur, tx_by_id, realized_all, by_currency = _compute_allocation(db)
    summary: dict = {"by_currency": by_currency, "invoices_updated": 0}

    # Fige le réel sur chaque transaction d'encaissement.
    for tx_id, r in realized_all.items():
        tx = tx_by_id[tx_id]
        tx.amount_eur = r["eur"]
        tx.fx_rate = r["rate"]

    # Propage aux factures payées reliées à ces transactions.
    updated = 0
    for inv in db.query(models.Invoice).filter(models.Invoice.status == "paid").all():
        tx = db.get(models.Transaction, inv.paid_transaction_id) if inv.paid_transaction_id else None
        if tx is None or tx.amount_eur is None:
            continue
        inv.amount_eur_received = Decimal(tx.amount_eur)
        forecast_eur = Decimal(inv.amount_eur_forecast or 0)
        inv.variance_eur = _q(Decimal(tx.amount_eur) - forecast_eur)
        updated += 1
    summary["invoices_updated"] = updated

    if commit:
        db.commit()
    logger.info(
        "📤 [FXReal] allocate: %d facture(s) mises à jour, devises=%s ✅",
        updated, list(summary["by_currency"].keys()),
    )
    return summary
