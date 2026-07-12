"""
Import CSV bancaire (historique 2025) — Qonto & Revolut Business.

- Détection de format par les en-têtes (aucune config utilisateur).
- Revolut : montant importé = « Total amount » (frais inclus) — seule colonne
  qui chaîne avec « Balance » (vérifié 861/861 sur l'export réel 2025).
- Qonto : « Montant total (TTC) » signé, décimale virgule, séparateur ';'.
- Les montants sont des Decimal (jamais float).
"""

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from backend.db import models
from backend.logging_config import get_logger
from backend.services import backup as backup_service
from backend.services.banking import _mask_iban
from backend.services.categorize import categorize_transaction, get_or_create_uncategorized

logger = get_logger("CsvImport", "backend")


@dataclass
class ParsedRow:
    account_name: str
    iban: str
    currency: str
    external_id: str
    booked_date: date
    value_date: Optional[date]
    amount: Decimal
    description: str
    counterparty: str
    balance_after: Optional[Decimal] = None


_REVOLUT_COLS = {"Date completed (UTC)", "Total amount", "Account", "ID"}
_QONTO_COLS = {"Montant total (TTC)", "Identifiant de transaction", "IBAN du compte"}


def _header_cols(text: str) -> set[str]:
    first = text.splitlines()[0] if text.strip() else ""
    delim = ";" if first.count(";") > first.count(",") else ","
    return {c.strip().strip('"') for c in first.split(delim)}


def detect_format(text: str) -> str:
    cols = _header_cols(text)
    if _REVOLUT_COLS <= cols:
        return "revolut"
    if _QONTO_COLS <= cols:
        return "qonto"
    raise ValueError("Format CSV non reconnu (ni Revolut Business, ni Qonto)")


def _dec(s: str) -> Decimal:
    s = (s or "0").replace(" ", "").replace(" ", "").replace(" ", "")
    return Decimal((s.replace(",", ".")) or "0")


def parse_csv(text: str) -> list[ParsedRow]:
    fmt = detect_format(text)
    return _parse_revolut(text) if fmt == "revolut" else _parse_qonto(text)


def _parse_revolut(text: str) -> list[ParsedRow]:
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        completed = (r.get("Date completed (UTC)") or "").strip()
        if not completed:
            continue
        started = (r.get("Date started (UTC)") or "").strip()
        rows.append(
            ParsedRow(
                account_name=r["Account"].strip(),
                iban=(r.get("International account number") or "").strip(),
                currency=r["Payment currency"].strip(),
                external_id=r["ID"].strip(),
                booked_date=datetime.strptime(completed[:10], "%Y-%m-%d").date(),
                value_date=(
                    datetime.strptime(started[:10], "%Y-%m-%d").date()
                    if started else None
                ),
                amount=_dec(r["Total amount"]),
                description=(r.get("Description") or "").strip(),
                counterparty=(r.get("Beneficiary name") or "").strip(),
                balance_after=(
                    _dec(r["Balance"]) if (r.get("Balance") or "").strip() else None
                ),
            )
        )
    return rows


def _parse_qonto(text: str) -> list[ParsedRow]:
    rows = []
    for r in csv.DictReader(io.StringIO(text), delimiter=";"):
        op = (r.get("Date de l'opération (UTC)") or "").strip()
        if not op:
            continue
        rows.append(
            ParsedRow(
                account_name=(r.get("Nom du compte") or "").strip(),
                iban=(r.get("IBAN du compte") or "").strip(),
                currency=(r.get("Devise") or "EUR").strip(),
                external_id=r["Identifiant de transaction"].strip(),
                booked_date=datetime.strptime(op[:10], "%d-%m-%Y").date(),
                value_date=None,
                amount=_dec(r["Montant total (TTC)"]),
                description=(r.get("Référence") or "").strip(),
                counterparty=(r.get("Nom de la contrepartie") or "").strip(),
                balance_after=(
                    _dec(r["Solde"]) if (r.get("Solde") or "").strip() else None
                ),
            )
        )
    return rows


def _match_account(db: Session, row: ParsedRow) -> Optional[models.BankAccount]:
    if not row.iban:
        return None
    masked = _mask_iban(row.iban)
    return (
        db.query(models.BankAccount)
        .filter(
            models.BankAccount.iban_masked == masked,
            models.BankAccount.currency == row.currency,
        )
        .first()
    )


def analyze(db: Session, text: str, year: int = 2025) -> dict:
    bank = detect_format(text)
    rows = parse_csv(text)

    existing = {
        (t.account_uid, t.external_id)
        for t in db.query(models.Transaction.account_uid, models.Transaction.external_id)
    }

    accounts: dict[str, dict] = {}
    match_cache: dict[tuple[str, str], Optional[models.BankAccount]] = {}
    importable = out_of_period = duplicates = skipped_no_account = 0
    warnings: list[str] = []
    sample: list[dict] = []

    # Ordre chronologique intra-fichier : les deux exports réels sont
    # antichrono (plus récent en premier), mais on détecte plutôt que de
    # le supposer — sert de tie-break pour les tx du même jour.
    dated = [r.booked_date for r in rows]
    antichrono = len(dated) >= 2 and dated[0] >= dated[-1]

    for idx, row in enumerate(rows):
        key = (row.iban, row.currency)
        if key not in match_cache:
            match_cache[key] = _match_account(db, row)
        account = match_cache[key]

        acc = accounts.setdefault(row.account_name + "|" + row.currency, {
            "csv_name": row.account_name,
            "iban_masked": _mask_iban(row.iban),
            "currency": row.currency,
            "tx_count": 0,
            "matched": account is not None,
            "account_id": account.id if account else None,
            "account_name": account.name if account else None,
            "opening_balance": None,
            "closing_balance": None,
            "_first": None, "_last": None,  # (date, ext_id, balance_after, amount)
        })
        acc["tx_count"] += 1

        # bornes chrono pour les soldes calculés — tie-break par ordre du
        # fichier (pas external_id, arbitraire) pour les tx du même jour.
        marker = (row.booked_date, -idx if antichrono else idx)
        if row.balance_after is not None:
            if acc["_first"] is None or marker < acc["_first"][0]:
                acc["_first"] = (marker, row.balance_after - row.amount)
            if acc["_last"] is None or marker > acc["_last"][0]:
                acc["_last"] = (marker, row.balance_after)

        if account is None:
            skipped_no_account += 1
            continue
        if row.booked_date.year != year:
            out_of_period += 1
            continue
        dedup_key = (account.account_uid, row.external_id)
        if dedup_key in existing:
            duplicates += 1
            continue
        existing.add(dedup_key)
        importable += 1
        if len(sample) < 5:
            sample.append({
                "date": row.booked_date.isoformat(),
                "description": row.description or row.counterparty,
                "amount": str(row.amount),
                "currency": row.currency,
                "account": row.account_name,
            })

    for acc in accounts.values():
        if acc["_first"]:
            acc["opening_balance"] = str(acc["_first"][1])
        if acc["_last"]:
            acc["closing_balance"] = str(acc["_last"][1])
        del acc["_first"], acc["_last"]
        if not acc["matched"]:
            label = acc["iban_masked"] or acc["csv_name"]
            warnings.append(
                f"Compte « {acc['csv_name']} » ({label}, {acc['currency']}) : "
                f"aucun compte correspondant — {acc['tx_count']} ligne(s) écartée(s)"
            )

    dates = [r.booked_date for r in rows]
    return {
        "bank": bank,
        "rows_read": len(rows),
        "period": {
            "min": min(dates).isoformat() if dates else None,
            "max": max(dates).isoformat() if dates else None,
        },
        "importable": importable,
        "out_of_period": out_of_period,
        "duplicates": duplicates,
        "skipped_no_account": skipped_no_account,
        "accounts": list(accounts.values()),
        "sample": sample,
        "warnings": warnings,
    }


def execute(db: Session, text: str, year: int = 2025) -> dict:
    """Importe les lignes du périmètre. Backup AVANT toute écriture (fail-closed)."""
    backup_file = backup_service.create_backup(reason="import")

    bank = detect_format(text)
    rows = parse_csv(text)
    existing = {
        (t.account_uid, t.external_id)
        for t in db.query(models.Transaction.account_uid, models.Transaction.external_id)
    }
    match_cache: dict[tuple[str, str], Optional[models.BankAccount]] = {}
    inserted = duplicates = out_of_period = skipped_no_account = categorized = 0
    touched: set[str] = set()
    new_txs: list[models.Transaction] = []

    for row in rows:
        key = (row.iban, row.currency)
        if key not in match_cache:
            match_cache[key] = _match_account(db, row)
        account = match_cache[key]
        if account is None:
            skipped_no_account += 1
            continue
        if row.booked_date.year != year:
            out_of_period += 1
            continue
        dedup_key = (account.account_uid, row.external_id)
        if dedup_key in existing:
            duplicates += 1
            continue
        existing.add(dedup_key)
        tx = models.Transaction(
            account_uid=account.account_uid,
            external_id=row.external_id,
            booked_date=row.booked_date,
            value_date=row.value_date,
            amount=row.amount,
            currency=row.currency,
            description=row.description,
            counterparty=row.counterparty,
            raw_json="",
        )
        db.add(tx)
        new_txs.append(tx)
        touched.add(account.account_uid)
        inserted += 1

    db.flush()
    uncategorized_id = get_or_create_uncategorized(db).id
    for tx in new_txs:
        if categorize_transaction(db, tx) != uncategorized_id:
            categorized += 1
    db.commit()

    logger.info(
        "📤 [CsvImport] execute(%s, %d): %d insérées, %d doublons, %d hors période ✅",
        bank, year, inserted, duplicates, out_of_period,
    )
    return {
        "bank": bank,
        "inserted": inserted,
        "duplicates": duplicates,
        "out_of_period": out_of_period,
        "skipped_no_account": skipped_no_account,
        "categorized": categorized,
        "backup_file": backup_file.name,
        "accounts_touched": len(touched),
        "warnings": [],
    }
