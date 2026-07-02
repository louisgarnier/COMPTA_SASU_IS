"""
Service Trésorerie LGC — consolidation multi-comptes + équivalent EUR.

Règles monnaie (architecture) :
- Tout montant en `Decimal`, jamais float.
- Équivalent EUR d'une transaction : on privilégie `amount_eur` s'il est
  renseigné ; sinon `amount` si la devise est déjà EUR ; sinon `amount * fx_rate`
  si un taux figé existe ; sinon conversion via les taux par défaut de Settings.
"""

from __future__ import annotations

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
) -> list[models.Transaction]:
    """
    Transactions du compte, filtrées à partir de la date d'ouverture si fixée,
    et jusqu'à `as_of` inclus si fourni (solde à une date donnée).
    """
    txs = (
        db.query(models.Transaction)
        .filter(models.Transaction.account_uid == acc.account_uid)
        .all()
    )
    if acc.opening_balance_date is not None:
        txs = [
            t
            for t in txs
            if t.booked_date is None or t.booked_date >= acc.opening_balance_date
        ]
    if as_of is not None:
        txs = [t for t in txs if t.booked_date is None or t.booked_date <= as_of]
    return txs


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
            # Reconstruction : ouverture + Σ mouvements (historique ou non synchro).
            txs = _account_transactions(db, acc, as_of=as_of)
            tx_sum = sum((Decimal(t.amount or 0) for t in txs), _ZERO)
            balance = Decimal(acc.opening_balance or 0) + tx_sum

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
