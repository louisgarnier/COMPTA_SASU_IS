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
    s = (s or "0").replace(" ", "").replace(" ", "").replace(",", ".")
    return Decimal(s or "0")


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
            )
        )
    return rows
