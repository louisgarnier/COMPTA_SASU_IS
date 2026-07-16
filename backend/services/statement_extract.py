"""
Extraction des soldes officiels depuis les relevés bancaires.

Deux sources :
- Revolut « Relevé des soldes » (texte extrait d'un PDF) → soldes de tous les comptes
  à une date de fin de mois.
- Qonto (CSV `;`) → solde de fin de mois du compte principal (colonne `Solde`).

Ne fait AUCUN accès base : pur parsing texte, testable en isolation. La confirmation
et l'écriture sont à la charge de l'appelant (route).
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date
from decimal import Decimal
from io import BytesIO
from typing import Optional

from sqlalchemy.orm import Session

from backend.db import models

_MONTHS_FR = {
    "janvier": 1,
    "février": 2,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "août": 8,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "décembre": 12,
    "decembre": 12,
}

# Un montant : symbole/suffixe de devise + nombre avec espaces (y c. insécables) comme
# séparateur de milliers et point décimal. Ex. « €11 626.90 », « $80 381.99 »,
# « 5 580.00 CAD », « £0.00 », « 3 000.000000 » (XRP).
_AMOUNT = r"([€$£]?)\s*([\d   ]+\.\d+)\s*([A-Z]{3})?"


def _to_decimal(raw: str) -> Decimal:
    """Nettoie un nombre FR (espaces/insécables) en Decimal."""
    cleaned = raw.replace(" ", "").replace(" ", "").replace(" ", "")
    return Decimal(cleaned)


def _currency(symbol: str, suffix: Optional[str]) -> Optional[str]:
    if suffix:
        return suffix.upper()
    return {"€": "EUR", "$": "USD", "£": "GBP"}.get(symbol)


def _parse_asof(text: str) -> Optional[date]:
    m = re.search(r"date du\s+(\d{1,2})\s+([A-Za-zéûoôàè]+)\s+(\d{4})", text)
    if not m:
        return None
    day, month_fr, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
    month = _MONTHS_FR.get(month_fr)
    return date(year, month, day) if month else None


def extract_revolut_balances(text: str) -> dict:
    """Extrait la date d'arrêté et un solde par compte du « Relevé des soldes »."""
    as_of = _parse_asof(text)
    lines = [ln.rstrip() for ln in text.splitlines()]
    balances: list[dict] = []

    name: Optional[str] = None
    currency: Optional[str] = None
    iban_last4: Optional[str] = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        dev = re.match(r"^Devise\s+([A-Z]{3})$", stripped)
        iban = re.match(r"^IBAN\s+(.+)$", stripped)
        if (
            re.match(
                r"^(Devise|IBAN|BIC|Type|Créé|Solde|Numéro|Code|Relevé|Informations)\b",
                stripped,
            )
            is None
            and stripped
            and re.search(_AMOUNT, stripped) is None
        ):
            # ligne « titre de compte » (Main, USD, Louis CAD, XRP, Hedging…)
            # — jamais une ligne de montant (ex. « €11 626.90 »), qui peut suivre
            # directement le solde d'un compte sans ligne titre intermédiaire.
            name = stripped
        if dev:
            currency = dev.group(1)
            iban_last4 = None
        elif iban:
            digits = re.sub(r"\D", "", iban.group(1))
            iban_last4 = digits[-4:] if len(digits) >= 4 else digits
        elif stripped == "Solde réglé":
            # le montant est sur une des lignes suivantes
            for nxt in lines[i + 1 : i + 3]:
                m = re.search(_AMOUNT, nxt.strip())
                if m:
                    cur = _currency(m.group(1), m.group(3)) or currency
                    balances.append(
                        {
                            "name": name,
                            "currency": cur,
                            "iban_last4": iban_last4,
                            "amount": _to_decimal(m.group(2)),
                        }
                    )
                    break
    return {"as_of": as_of, "balances": balances}


def extract_qonto_month_end(csv_text: str, year: int, month: int) -> list[dict]:
    """Solde de fin de mois par compte = `Solde` de la dernière opération du mois.

    L'ordre chronologique intra-fichier est détecté (pas supposé) : les exports
    réels sont antichrono (plus récent en premier), mais on ne peut pas s'y fier
    aveuglément. Sur une date de clôture partagée par plusieurs lignes (date-only,
    pas d'heure), l'ordre du fichier sert de tie-break — même technique que
    `csv_import.analyze` (voir `antichrono` / `marker` là-bas) : en antichrono la
    1re ligne vue pour un jour donné est la plus récente, en chrono c'est la dernière.
    """
    rows = list(csv.DictReader(io.StringIO(csv_text), delimiter=";"))
    parsed: list[tuple[Optional[date], dict]] = []
    for row in rows:
        raw_date = (row.get("Date de la valeur (local)") or "").strip()
        m = re.match(r"^(\d{2})-(\d{2})-(\d{4})", raw_date)
        d = date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None
        parsed.append((d, row))

    dated = [d for d, _ in parsed if d is not None]
    antichrono = len(dated) >= 2 and dated[0] >= dated[-1]

    last_by_account: dict[str, dict] = {}
    for idx, (d, row) in enumerate(parsed):
        if d is None or d.year != year or d.month != month:
            continue
        iban = (row.get("IBAN du compte") or "").strip()
        key = iban or (row.get("Nom du compte") or "").strip()
        # tie-break du même jour par ordre du fichier (pas par date seule, qui
        # ne distingue pas les opérations du jour de clôture).
        marker = (d, -idx if antichrono else idx)
        prev = last_by_account.get(key)
        if prev is None or marker > prev["_marker"]:
            last_by_account[key] = {
                "account_name": (row.get("Nom du compte") or "").strip(),
                "iban_last4": iban[-4:] if len(iban) >= 4 else (iban or None),
                "currency": (row.get("Devise") or "EUR").strip().upper(),
                "amount": _to_decimal((row.get("Solde") or "0").replace(",", ".")),
                "_marker": marker,
            }
    return [{k: v for k, v in item.items() if k != "_marker"} for item in last_by_account.values()]


def pdf_to_text(data: bytes) -> str:
    """Extrait le texte d'un PDF (pypdf). Chaîne vide si illisible."""
    from pypdf import PdfReader

    try:
        reader = PdfReader(BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:  # PDF corrompu / chiffré → proposition vide en amont
        return ""


def _iban_tail(iban_masked: Optional[str]) -> Optional[str]:
    """4 derniers chiffres d'un IBAN masqué type « FR76****527 » (ou None)."""
    if not iban_masked:
        return None
    digits = re.sub(r"\D", "", iban_masked)
    return digits[-3:] if digits else None  # masqué → souvent 3 chiffres visibles


def map_to_accounts(db: Session, extracted: list[dict]) -> list[dict]:
    """Associe chaque solde extrait à un compte par (devise, fin d'IBAN) puis (devise, nom)."""
    accounts = db.query(models.BankAccount).all()
    results: list[dict] = []
    for item in extracted:
        cur = (item.get("currency") or "").upper()
        last4 = item.get("iban_last4")
        match = None
        # 1) devise + fin d'IBAN (le masqué ne montre que quelques chiffres → suffixe)
        if last4:
            for acc in accounts:
                tail = _iban_tail(acc.iban_masked)
                if (acc.currency or "").upper() == cur and tail and last4.endswith(tail):
                    match = acc
                    break
        # 2) repli : unique compte de cette devise
        if match is None:
            same = [a for a in accounts if (a.currency or "").upper() == cur]
            if len(same) == 1:
                match = same[0]
        results.append({
            "account_uid": match.account_uid if match else None,
            "currency": cur,
            "amount": item.get("amount"),
            "matched": match is not None,
            "hint": item.get("name") or "",
        })
    return results
