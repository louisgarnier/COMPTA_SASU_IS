"""
Service Trésorerie LGC — consolidation multi-comptes + équivalent EUR.

Règles monnaie (architecture) :
- Tout montant en `Decimal`, jamais float.
- Équivalent EUR d'une transaction : on privilégie `amount_eur` s'il est
  renseigné ; sinon `amount` si la devise est déjà EUR ; sinon `amount * fx_rate`
  si un taux figé existe ; sinon conversion via les taux par défaut de Settings.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from backend.db import models
from backend.logging_config import get_logger

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


def _default_fx(currency: str, settings: models.Settings) -> Decimal:
    """Taux par défaut devise → EUR issu de Settings (1 si inconnu)."""
    cur = (currency or "").upper()
    if cur == "EUR":
        return Decimal("1")
    if cur == "USD":
        return Decimal(settings.default_fx_usd or "0")
    if cur == "CAD":
        return Decimal(settings.default_fx_cad or "0")
    return Decimal("1")


def _convert_to_eur(amount: Decimal, currency: str, settings: models.Settings) -> Decimal:
    """Convertit un montant depuis sa devise vers EUR via les taux par défaut."""
    amount = Decimal(amount or 0)
    if (currency or "").upper() == "EUR":
        return amount
    return amount * _default_fx(currency, settings)


def eur_amount(tx: models.Transaction, settings: models.Settings) -> Decimal:
    """
    Équivalent EUR d'une transaction.

    Priorité : amount_eur → (EUR : amount) → amount*fx_rate → conversion défaut.
    """
    if tx.amount_eur is not None:
        return Decimal(tx.amount_eur)
    amount = Decimal(tx.amount or 0)
    if (tx.currency or "").upper() == "EUR":
        return amount
    if tx.fx_rate is not None:
        return amount * Decimal(tx.fx_rate)
    return _convert_to_eur(amount, tx.currency, settings)


def _account_transactions(db: Session, acc: models.BankAccount) -> list[models.Transaction]:
    """Transactions du compte, filtrées à partir de la date d'ouverture si fixée."""
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
    return txs


def consolidated_treasury(db: Session) -> dict:
    """
    Consolide la trésorerie de tous les comptes bancaires + placements.

    Solde d'un compte = opening_balance + Σ transactions (depuis la date
    d'ouverture si renseignée). L'équivalent EUR d'un compte non-EUR agrège
    l'ouverture convertie (taux défaut) + Σ des équivalents EUR des transactions.
    """
    settings = _get_settings(db)
    accounts = db.query(models.BankAccount).order_by(models.BankAccount.id).all()

    out_accounts: list[dict] = []
    bank_total_eur = _ZERO
    for acc in accounts:
        txs = _account_transactions(db, acc)
        tx_sum = sum((Decimal(t.amount or 0) for t in txs), _ZERO)
        balance = Decimal(acc.opening_balance or 0) + tx_sum

        if (acc.currency or "").upper() == "EUR":
            eur_balance = balance
        else:
            opening_eur = _convert_to_eur(
                Decimal(acc.opening_balance or 0), acc.currency, settings
            )
            eur_tx_sum = sum((eur_amount(t, settings) for t in txs), _ZERO)
            eur_balance = opening_eur + eur_tx_sum

        bank_total_eur += eur_balance
        out_accounts.append(
            {
                "account_uid": acc.account_uid,
                "name": acc.name,
                "provider": acc.provider,
                "currency": acc.currency,
                "balance": q2(balance),
            }
        )

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
        "accounts": out_accounts,
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
