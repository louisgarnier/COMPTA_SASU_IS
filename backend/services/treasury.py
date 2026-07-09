"""
Service Trésorerie LGC — consolidation multi-comptes + équivalent EUR.

Règles monnaie (architecture) :
- Tout montant en `Decimal`, jamais float.
- Équivalent EUR d'une transaction : on privilégie `amount_eur` s'il est
  renseigné ; sinon `amount` si la devise est déjà EUR ; sinon `amount * fx_rate`
  si un taux figé existe ; sinon conversion via les taux par défaut de Settings.
"""

from __future__ import annotations

import calendar
from datetime import date as date_type
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from sqlalchemy.orm import Session

from backend.db import models
from backend.logging_config import get_logger
from backend.services.fx import load_rates, rate_for, to_eur

logger = get_logger("treasury", channel="api")

_CENTS = Decimal("0.01")
_RATE = Decimal("0.000001")
_ZERO = Decimal("0")


def q2(value: Decimal) -> Decimal:
    """Quantifie un montant monétaire à 2 décimales (arrondi commercial)."""
    return Decimal(value).quantize(_CENTS, rounding=ROUND_HALF_UP)


def _get_settings(db: Session) -> models.Settings:
    """Retourne le singleton Settings (id=1), un objet par défaut si absent."""
    row = db.get(models.Settings, 1)
    return row if row is not None else models.Settings(id=1)


def eur_amount(tx: models.Transaction, rates: dict) -> Decimal:
    """
    Équivalent EUR d'une transaction via le taux théorique des Réglages.

    Modèle : montant natif × taux(devise). EUR = 1. Aucun taux « réalisé » figé
    par transaction — la conversion suit toujours le taux courant des Réglages.
    """
    return to_eur(tx.amount, tx.currency, rates)


def _account_transactions(
    db: Session,
    acc: models.BankAccount,
    as_of: Optional[date_type] = None,
    since: Optional[date_type] = None,
) -> list[models.Transaction]:
    """
    Transactions du compte, filtrées à partir de `since` (ou de la date d'ouverture
    legacy à défaut) et jusqu'à `as_of` inclus si fourni (solde à une date donnée).
    """
    txs = (
        db.query(models.Transaction)
        .filter(models.Transaction.account_uid == acc.account_uid)
        .all()
    )
    lower = since if since is not None else acc.opening_balance_date
    if lower is not None:
        txs = [t for t in txs if t.booked_date is None or t.booked_date >= lower]
    if as_of is not None:
        txs = [t for t in txs if t.booked_date is None or t.booked_date <= as_of]
    return txs


def _reconstruct_balance(
    db: Session, acc: models.BankAccount, as_of: Optional[date_type]
) -> Decimal:
    """
    Solde reconstruit = ouverture d'exercice (relevé saisi) + Σ mouvements depuis
    le 1er janvier de l'exercice ancré, jusqu'à `as_of` inclus.

    L'ancre annuelle (`openings.opening_anchor`) reprend le relevé de clôture le plus
    récent pour corriger la dérive ; à défaut de toute saisie, retombe sur l'ancien
    `acc.opening_balance` depuis `opening_balance_date`.
    """
    from backend.services import openings as openings_service

    target_year = as_of.year if as_of is not None else date_type.today().year
    anchor_balance, anchor_date = openings_service.opening_anchor(db, acc, target_year)
    txs = _account_transactions(db, acc, as_of=as_of, since=anchor_date)
    tx_sum = sum((Decimal(t.amount or 0) for t in txs), _ZERO)
    return Decimal(anchor_balance or 0) + tx_sum


def consolidated_treasury(db: Session, as_of: Optional[date_type] = None) -> dict:
    """
    Consolide la trésorerie de tous les comptes bancaires + placements.

    Solde d'un compte :
    - **vue courante** (`as_of` None) d'un compte **synchronisé** → solde réel
      renvoyé par le provider (`acc.balance`), source de vérité ;
    - sinon (historique `as_of`, ou compte jamais synchronisé/mock) →
      reconstruction `opening_balance + Σ transactions` depuis la date
      d'ouverture, jusqu'à `as_of` inclus si fourni.
    L'équivalent EUR d'un compte non-EUR applique le taux théorique des Réglages.
    """
    rates = load_rates(db)
    accounts = db.query(models.BankAccount).order_by(models.BankAccount.id).all()

    # « Vue courante » = pas de date, ou date demandée ≥ aujourd'hui : on montre le
    # solde réel synchronisé. Une date passée déclenche la reconstruction historique.
    is_current = as_of is None or as_of >= date_type.today()

    out_accounts: list[dict] = []
    bank_total_eur = _ZERO
    native_by_ccy: dict[str, Decimal] = {}
    for acc in accounts:
        cur = (acc.currency or "EUR").upper()
        synced = acc.last_synced_at is not None and acc.balance is not None
        if is_current and synced:
            # Solde réel du provider (ne dépend pas d'un solde d'ouverture saisi).
            balance = Decimal(acc.balance)
        else:
            # Reconstruction : ouverture d'exercice ancrée + Σ mouvements.
            balance = _reconstruct_balance(db, acc, as_of)

        # On agrège d'abord en natif par devise (jamais d'addition inter-devises).
        native_by_ccy[cur] = native_by_ccy.get(cur, _ZERO) + balance

        eur_balance = to_eur(balance, cur, rates)
        bank_total_eur += eur_balance
        out_accounts.append(
            {
                "account_uid": acc.account_uid,
                "name": acc.name,
                "provider": acc.provider,
                "currency": acc.currency,
                "balance": q2(balance),
                "rate": rate_for(rates, cur),
                "balance_eur": q2(eur_balance),
            }
        )

    # Ventilation par devise : solde natif → taux → équivalent EUR.
    by_currency = [
        {
            "currency": cur,
            "balance_native": q2(native_by_ccy[cur]),
            "rate": rate_for(rates, cur),
            "balance_eur": q2(to_eur(native_by_ccy[cur], cur, rates)),
            "missing_rate": cur != "EUR" and cur not in rates,
        }
        for cur in sorted(native_by_ccy)
    ]

    investments = db.query(models.Investment).all()
    investments_total_eur = sum(
        (Decimal(inv.current_value_eur or 0) for inv in investments), _ZERO
    )
    total_eur = bank_total_eur + investments_total_eur

    logger.info(
        "📤 [Treasury] consolidate: %d compte(s), total=%s EUR ✅",
        len(out_accounts),
        q2(total_eur),
    )
    return {
        "as_of": as_of.isoformat() if as_of is not None else None,
        "accounts": out_accounts,
        "by_currency": by_currency,
        "bank_total_eur": q2(bank_total_eur),
        "investments_total_eur": q2(investments_total_eur),
        "total_eur": q2(total_eur),
    }


def _bank_movements_eur(
    db: Session,
    accounts: list[models.BankAccount],
    rates: dict,
    after: date_type,
    upto: date_type,
) -> Decimal:
    """
    Σ des mouvements en EUR (tous comptes) avec `after < booked_date <= upto`.

    Sert à remonter le solde à rebours depuis le solde réel actuel.
    """
    total = _ZERO
    for acc in accounts:
        cur = (acc.currency or "EUR").upper()
        for t in _account_transactions(db, acc, as_of=upto):
            if t.booked_date and t.booked_date > after:
                total += to_eur(Decimal(t.amount or 0), cur, rates)
    return total


def balance_timeline(
    db: Session, year: int, today: Optional[date_type] = None, scope: str = "forecast"
) -> dict:
    """
    Déroulé mensuel du solde de trésorerie cumulé en EUR sur `year`.

    - Ancrage : le solde COURANT = vrai solde consolidé actuel
      `consolidated_treasury(as_of=today)["bank_total_eur"]` (solde synchronisé du
      provider si dispo) — même source que le KPI « Trésorerie ». La ligne finit
      donc exactement sur le vrai solde.
    - Mois passés (< mois courant) : solde de fin de mois reconstruit À REBOURS =
      solde actuel − Σ mouvements postérieurs à la fin de ce mois. Trajectoire
      continue qui aboutit au solde réel. is_forecast=False.
    - Mois futurs (> mois courant) : solde actuel + cumul des nets du CASHFLOW
      (`cashflow.monthly_cashflow`, même source que le graphe — encaissements à
      leur date attendue), filtrés par `scope` (realized/engaged/forecast).
      is_forecast=True. Année entièrement future : la base enjambe la fin de
      chaque exercice intermédiaire.

    Retour : {year, months:[{month, balance_eur, is_forecast}],
              current_balance_eur, projected_year_end_eur}. Montants 2 décimales.
    """
    if today is None:
        today = date_type.today()

    rates = load_rates(db)
    accounts = db.query(models.BankAccount).order_by(models.BankAccount.id).all()
    current = (today.year, today.month)

    # Ancre = vrai solde actuel (synchronisé si dispo), source de vérité du KPI.
    current_real = Decimal(consolidated_treasury(db, as_of=today)["bank_total_eur"])

    # Nets futurs par mois : on cumule le net du **cashflow** (mêmes encaissements
    # attendus que le graphe Cashflow : factures ouvertes à leur date de paiement),
    # et non le net de `forecast.project` (basé sur le mois de prestation) — sinon la
    # ligne de solde et le cashflow racontent deux futurs incompatibles.
    from backend.services import cashflow as cashflow_service

    cf = cashflow_service.monthly_cashflow(db, year, today=today, scope=scope)
    net_by_month = {
        m["month"]: Decimal(m["incoming_eur"]) - Decimal(m["outgoing_eur"])
        for m in cf["months"]
    }

    months_out: list[dict] = []
    running = current_real  # base pour les mois futurs (≈ fin du mois courant)
    # Année(s) entièrement future(s) : enjamber la fin de l'exercice courant —
    # la base = solde actuel + Σ nets des mois restants de chaque année
    # intermédiaire (sinon les encaissements d'août-déc N seraient perdus).
    if (year, 1) > current:
        for y in range(today.year, year):
            cf_y = cashflow_service.monthly_cashflow(db, y, today=today, scope=scope)
            for m_y in cf_y["months"]:
                ym = int(m_y["month"][:4]), int(m_y["month"][5:7])
                if ym > current:
                    running += Decimal(m_y["incoming_eur"]) - Decimal(m_y["outgoing_eur"])
    for m in range(1, 13):
        key = f"{year:04d}-{m:02d}"
        pos = (year, m)
        last_day = calendar.monthrange(year, m)[1]
        month_end = date_type(year, m, last_day)

        if pos < current:
            # Rebours : solde réel actuel − mouvements postérieurs à ce mois.
            balance = current_real - _bank_movements_eur(
                db, accounts, rates, after=month_end, upto=today
            )
            is_forecast = False
        elif pos == current:
            balance = current_real
            is_forecast = False
        else:
            running = running + net_by_month.get(key, _ZERO)
            balance = running
            is_forecast = True

        months_out.append(
            {"month": key, "balance_eur": q2(balance), "is_forecast": is_forecast}
        )

    current_balance_eur = current_real
    projected_year_end_eur = months_out[-1]["balance_eur"]

    logger.info(
        "📤 [Treasury] balance_timeline: year=%d courant=%s fin=%s ✅",
        year,
        q2(current_balance_eur),
        projected_year_end_eur,
    )
    return {
        "year": year,
        "months": months_out,
        "current_balance_eur": q2(current_balance_eur),
        "projected_year_end_eur": projected_year_end_eur,
    }


def bridge_key_for_tx(
    tx: models.Transaction,
    cats: dict[int, models.Category],
    invoice_month: Optional[str],
    year: int,
) -> Optional[str]:
    """
    Classe une transaction dans une ligne du pont de trésorerie.

    LOGIQUE UNIQUE partagée par `treasury_bridge` (montants) et le filtre
    `bridge=` de l'API transactions (listes) — garantit que le total de la
    liste filtrée égale la ligne du pont.

    Clés : 'residual' (conversions FX), 'charges', 'received_current'/'received_prior'
    (revenu rattaché à une facture, selon l'exercice de la facture),
    'other_revenue' (revenu sans facture), 'cat:<nom>' (transfer/internal/
    investment, groupé par nom de catégorie), 'cat:À catégoriser'.
    """
    kind = tx.kind or ""
    cat = cats.get(tx.category_id)
    ctype = cat.type if cat else None
    if kind == "conversion" or ctype == "conversion":
        return "residual"
    if ctype == "charge":
        return "charges"
    if kind == "revenue" or ctype == "revenue":
        if tx.invoice_id is not None:
            if (invoice_month or "").startswith(f"{year:04d}"):
                return "received_current"
            return "received_prior"
        return "other_revenue"
    if ctype in ("transfer", "internal", "investment", "distribution", "is_payment") or kind in (
        "transfer",
        "investment",
    ):
        return f"cat:{cat.name}" if cat else "cat:Transferts divers"
    if ctype == "uncategorized" or cat is None:
        return "cat:À catégoriser"
    return None


def treasury_bridge(
    db: Session,
    as_of: Optional[date_type] = None,
    today: Optional[date_type] = None,
) -> dict:
    """
    Pont « D'où vient ma trésorerie ? » : ouverture d'exercice → banque actuelle.

    Entièrement dynamique (recalculé depuis les transactions à chaque appel) :
    - `received_current` / `received_prior` : EUR réel encaissé dans l'exercice,
      ventilé factures de l'exercice vs exercices antérieurs (accrual ≠ caisse).
    - `other_revenue` : revenus SANS facture (ex. indemnité client). Les
      remboursements (+) sur catégories charge restent DANS les charges nettes.
    - `charges` : charges nettes (tous signes), EUR réel si connu sinon théorique.
    - lignes `cat:<nom>` : catégories transfer/internal/investment groupées par
      NOM de catégorie (aucun nom en dur) — dividendes, placements, virements.
    - `residual_eur` : bouclage exact par différence (spread FX réel, résidu
      d'ouverture, écarts de valorisation). ⚠ `residual_warning` si > 2 % du
      solde — un gros résiduel = probablement un flux mal catégorisé.
    - `due_pending_eur` : factures émises non payées (dans le P&L, pas en banque).

    `as_of` (défaut aujourd'hui) : le pont ENTIER se recalcule à cette date —
    flux jusqu'à `as_of` inclus, banque reconstruite à `as_of`, factures
    encaissées/dues à cette date. L'exercice = l'année de `as_of`.
    """
    if today is None:
        today = date_type.today()
    if as_of is None:
        as_of = today
    year = as_of.year
    rates = load_rates(db)
    from backend.services import openings as openings_service

    bank_today = Decimal(consolidated_treasury(db, as_of=as_of)["bank_total_eur"])
    opening = Decimal(
        openings_service.get_openings(db, year, today=today)["tie_out"]["opening_eur"]
    )
    cats = {c.id: c for c in db.query(models.Category).all()}

    def eurv(t: models.Transaction) -> Decimal:
        if t.amount_eur is not None:
            return Decimal(t.amount_eur)
        return to_eur(Decimal(t.amount or 0), (t.currency or "EUR").upper(), rates)

    # Encaissements jusqu'à `as_of`, ventilés par exercice de la facture ;
    # dues = émises à cette date et non (encore) payées à cette date.
    received_current = _ZERO
    received_prior = _ZERO
    due_pending = _ZERO
    for inv in db.query(models.Invoice).all():
        paid_at = inv.paid_date if inv.status == "paid" else None
        # Sans date d'émission (cas limite), une `due` est réputée émise « maintenant ».
        issued_at = inv.issue_date or today
        if (
            inv.status in ("due", "paid")
            and issued_at <= as_of
            and (paid_at is None or paid_at > as_of)
        ):
            due_pending += Decimal(inv.amount_eur_forecast or 0)
        if paid_at is None or paid_at > as_of or paid_at.year != year:
            continue
        eur = Decimal(inv.amount_eur_received or 0)
        if (inv.month or "").startswith(f"{year:04d}"):
            received_current += eur
        else:
            received_prior += eur

    other_revenue = _ZERO
    charges = _ZERO
    by_cat: dict[str, Decimal] = {}
    inv_month = {
        i.id: i.month for i in db.query(models.Invoice.id, models.Invoice.month).all()
    }
    for t in db.query(models.Transaction).all():
        if t.booked_date is None or t.booked_date.year != year or t.booked_date > as_of:
            continue
        key = bridge_key_for_tx(t, cats, inv_month.get(t.invoice_id), year)
        if key == "charges":
            charges += eurv(t)  # tous signes : remboursements déduits ici
        elif key == "other_revenue":
            other_revenue += eurv(t)
        elif key is not None and key.startswith("cat:"):
            name = key[4:]
            by_cat[name] = by_cat.get(name, _ZERO) + eurv(t)
        # 'residual' (conversions) et 'received_*' (portés par les factures) : skip.

    lines = [
        {"key": "received_prior", "label": f"Encaissé — factures < {year}",
         "amount_eur": q2(received_prior)},
        {"key": "received_current", "label": f"Encaissé — factures {year}",
         "amount_eur": q2(received_current)},
        {"key": "other_revenue", "label": "Autres revenus (non facturés)",
         "amount_eur": q2(other_revenue)},
        {"key": "charges", "label": "Charges (nettes)", "amount_eur": q2(charges)},
    ]
    for name in sorted(by_cat, key=lambda n: by_cat[n]):
        lines.append({"key": f"cat:{name}", "label": name, "amount_eur": q2(by_cat[name])})
    lines = [l for l in lines if Decimal(l["amount_eur"]) != 0
             or l["key"] in ("received_current", "charges")]

    identified = sum(Decimal(l["amount_eur"]) for l in lines)
    residual = q2(bank_today - opening - identified)
    # Seuil rapporté au VOLUME de flux identifiés (pas au solde) : le spread FX
    # réel (~0,5-1 % des conversions) est normal ; au-delà de 2 % du volume,
    # un flux est probablement mal catégorisé.
    volume = sum(abs(Decimal(l["amount_eur"])) for l in lines)
    base = max(volume, abs(bank_today), Decimal("1"))
    residual_warning = bool(abs(residual) / base > Decimal("0.02"))

    logger.info(
        "📤 [Treasury] bridge: year=%d ouverture=%s banque=%s résiduel=%s ✅",
        year, q2(opening), q2(bank_today), residual,
    )
    return {
        "year": year,
        "as_of": as_of.isoformat(),
        "opening_eur": q2(opening),
        "lines": lines,
        "residual_eur": residual,
        "residual_warning": residual_warning,
        "bank_today_eur": q2(bank_today),
        "due_pending_eur": q2(due_pending),
    }


def link_fx_conversion(
    db: Session, credit_tx_id: int, conversion_tx_id: int
) -> models.Transaction:
    """
    Lie un crédit en devise à sa conversion EUR appariée.

    Renseigne `linked_conversion_id`, puis calcule `amount_eur` (montant EUR reçu
    lors de la conversion) et `fx_rate` implicite = |EUR| / |montant crédit|.
    Retourne la transaction crédit mise à jour.
    """
    credit = db.get(models.Transaction, credit_tx_id)
    conversion = db.get(models.Transaction, conversion_tx_id)
    if credit is None or conversion is None:
        raise ValueError("credit_tx_id ou conversion_tx_id introuvable")

    conv_eur = (
        Decimal(conversion.amount_eur)
        if conversion.amount_eur is not None
        else Decimal(conversion.amount or 0)
    )

    credit.linked_conversion_id = conversion.id
    credit.amount_eur = q2(abs(conv_eur).copy_sign(Decimal(credit.amount or 0)))

    credit_amount = Decimal(credit.amount or 0)
    if credit_amount != 0:
        rate = (abs(conv_eur) / abs(credit_amount)).quantize(
            _RATE, rounding=ROUND_HALF_UP
        )
        credit.fx_rate = rate

    db.commit()
    db.refresh(credit)
    logger.info(
        "📤 [Treasury] link_fx: tx#%s ← conversion#%s, fx=%s ✅",
        credit.id,
        conversion.id,
        credit.fx_rate,
    )
    return credit
