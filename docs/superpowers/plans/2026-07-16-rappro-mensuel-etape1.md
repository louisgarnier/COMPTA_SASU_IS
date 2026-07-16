# Rapprochement mensuel officiel — Étape 1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rapprocher chaque mois le solde officiel de fin de mois (extrait des relevés Revolut/Qonto) au solde reconstitué par l'app, par compte, avec archivage du PDF de preuve.

**Architecture:** Extraction (texte PDF via pypdf / CSV Qonto) → proposition confirmée par l'utilisateur → écriture `monthly_balances` + archivage `balance_documents` (rattaché à la période) → service de tie-out mensuel (ancre d'ouverture `openings` + Σ mouvements jusqu'à fin de mois) → carte UI 12 mois sur la page Banques.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, SQLite, Decimal, pypdf ; Next.js 16, React 19, TypeScript, Tailwind v4. Back `:8001`, front `:3001`.

## Global Constraints

- Montants toujours en `Decimal`, jamais `float`. Comparaisons au centième (`Decimal("0.01")`).
- Aucune valeur métier en dur : les soldes viennent des relevés, jamais du code.
- L'extraction ne doit **jamais écrire** sans confirmation utilisateur (hybride) ; en cas de format inconnu, échouer proprement (proposition vide), pas de valeur fausse.
- Ne jamais logguer un solde complet ni un IBAN complet (conventions logging projet : `[Module] verbe: détail`, emojis 📥📤✅❌).
- Les transactions synchronisées restent la source des mouvements ; on ne réimporte rien (Étape 1).
- Git via `python3 scripts/git_ops.py` uniquement. Commits `[EPIC-8] type: description`. Branche `epic-8-rappro-mensuel-officiel`.
- PII : `docs/Doc_comptable/` gitignoré (fait) ; fichiers uploadés dans `data/balance_docs/` (déjà gitignoré via `data/`).
- Tests même session que le code. Back : `pytest` (fixtures SQLite en mémoire, cf. `backend/tests/test_fx_realized.py`). Front : `jest`/`@testing-library/react`.

---

### Task 1: Modèle `MonthlyBalance` + période sur `BalanceDocument` + dépendance pypdf

**Files:**
- Modify: `backend/db/models.py` (ajout classe `MonthlyBalance` ; 2 colonnes sur `BalanceDocument` ~ligne 382-396)
- Modify: `backend/requirements.txt` (ajout `pypdf`)
- Modify: `workflow/ADR.md` (consigner l'approbation pypdf)
- Test: `backend/tests/test_monthly_balance_model.py`

**Interfaces:**
- Produces: `models.MonthlyBalance(id, account_uid, year, month, balance: Decimal, currency, source_doc_id, confirmed_at, updated_at)` avec `UniqueConstraint("account_uid","year","month")` ; `models.BalanceDocument.period_year: Optional[int]`, `.period_month: Optional[int]`.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# backend/tests/test_monthly_balance_model.py
from decimal import Decimal
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from backend.db.base import Base
from backend.db import models


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", future=True,
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, future=True)()
    yield db
    db.close()


def test_monthly_balance_unique_per_account_year_month(session):
    session.add(models.MonthlyBalance(account_uid="acc1", year=2025, month=2,
                                      balance=Decimal("100.00"), currency="EUR"))
    session.commit()
    session.add(models.MonthlyBalance(account_uid="acc1", year=2025, month=2,
                                      balance=Decimal("200.00"), currency="EUR"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_balance_document_has_period_columns(session):
    doc = models.BalanceDocument(label="relevé", filename="f.pdf", file_path="/x",
                                 content_type="application/pdf", size_bytes=1,
                                 period_year=2025, period_month=12)
    session.add(doc)
    session.commit()
    session.refresh(doc)
    assert doc.period_year == 2025
    assert doc.period_month == 12
```

- [ ] **Step 2: Lancer le test → échec**

Run: `cd /Users/louisgarnier/Claude/compta_sasu && python3 -m pytest backend/tests/test_monthly_balance_model.py -v`
Expected: FAIL — `AttributeError: module 'backend.db.models' has no attribute 'MonthlyBalance'`.

- [ ] **Step 3: Implémenter le modèle**

Dans `backend/db/models.py`, ajouter après la classe `BalanceDocument` les 2 colonnes de période à `BalanceDocument` (juste après `uploaded_at`) :

```python
    period_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    period_month: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
```

Et une nouvelle classe (vérifier que `UniqueConstraint` est importé depuis `sqlalchemy` en tête de fichier ; sinon l'ajouter à l'import existant) :

```python
class MonthlyBalance(Base):
    """Solde officiel de fin de mois d'un compte, repris d'un relevé et validé."""

    __tablename__ = "monthly_balances"
    __table_args__ = (UniqueConstraint("account_uid", "year", "month", name="uq_monthly_balance"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_uid: Mapped[str] = mapped_column(String, index=True)
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    balance: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String, default="EUR")
    source_doc_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("balance_documents.id"), nullable=True
    )
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 4: Lancer le test → succès**

Run: `python3 -m pytest backend/tests/test_monthly_balance_model.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Déclarer pypdf + ADR**

Ajouter à `backend/requirements.txt` :
```
pypdf>=4.0.0
```
Installer : `python3 -m pip install "pypdf>=4.0.0"` (Expected: `Successfully installed pypdf-…` ou `already satisfied`).
Ajouter à la fin de `workflow/ADR.md` :
```markdown
## ADR-01X — pypdf pour lire les relevés de soldes PDF (2026-07-16)
Décision : ajouter `pypdf` (MIT, pur Python, aucune dépendance système) pour extraire
le texte des « Relevés des soldes » Revolut (auto-extraction des soldes mensuels).
Approuvé par l'utilisateur. Alternative écartée : saisie manuelle des soldes Revolut.
```

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-8] feat: modèle MonthlyBalance + période BalanceDocument + dépendance pypdf" backend/db/models.py backend/tests/test_monthly_balance_model.py backend/requirements.txt workflow/ADR.md
```

---

### Task 2: Extraction des soldes Revolut (« Relevé des soldes »)

**Files:**
- Create: `backend/services/statement_extract.py`
- Test: `backend/tests/test_statement_extract.py`

**Interfaces:**
- Produces: `extract_revolut_balances(text: str) -> dict` retournant `{"as_of": Optional[date], "balances": list[dict]}` où chaque solde = `{"name": str, "currency": str, "iban_last4": Optional[str], "amount": Decimal}`.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# backend/tests/test_statement_extract.py
from decimal import Decimal
from datetime import date
from backend.services import statement_extract as se

# Texte linéarisé représentatif d'un « Relevé des soldes » Revolut (extrait réel anonymisé).
REVOLUT_TEXT = """Relevé des soldes
Relevé généré le 23 mars 2026
Informations en date du 31 décembre 2025 (UTC)
Main
Devise EUR
Type International
IBAN FR76 2823 3000 0145 5029 8993 527
Solde réglé
€11 626.90
Main
Devise USD
IBAN FR76 2823 3000 0145 5029 8993 527
Solde réglé
$80 381.99
USD
Devise USD
IBAN FR76 2823 3000 0112 7112 9737 484
Solde réglé
$40 320.00
Louis CAD
Devise CAD
IBAN FR76 2823 3000 0145 5029 8993 527
Solde réglé
5 580.00 CAD
XRP
Devise XRP
Solde réglé
3 000.000000
"""


def test_revolut_as_of_date():
    out = se.extract_revolut_balances(REVOLUT_TEXT)
    assert out["as_of"] == date(2025, 12, 31)


def test_revolut_balances_by_account():
    out = se.extract_revolut_balances(REVOLUT_TEXT)
    by = {(b["currency"], b["iban_last4"]): b["amount"] for b in out["balances"]}
    assert by[("EUR", "3527")] == Decimal("11626.90")
    assert by[("USD", "3527")] == Decimal("80381.99")
    assert by[("USD", "7484")] == Decimal("40320.00")
    assert by[("CAD", "3527")] == Decimal("5580.00")
    # XRP : pas d'IBAN → clé (XRP, None), montant à 6 décimales
    xrp = [b for b in out["balances"] if b["currency"] == "XRP"][0]
    assert xrp["amount"] == Decimal("3000.000000")
    assert xrp["iban_last4"] is None
```

- [ ] **Step 2: Lancer le test → échec**

Run: `python3 -m pytest backend/tests/test_statement_extract.py -v`
Expected: FAIL — `ModuleNotFoundError` / `AttributeError: ... extract_revolut_balances`.

- [ ] **Step 3: Implémenter le parseur**

```python
# backend/services/statement_extract.py
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

import re
from datetime import date
from decimal import Decimal
from typing import Optional

_MONTHS_FR = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10,
    "novembre": 11, "décembre": 12, "decembre": 12,
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
    lines = [l.rstrip() for l in text.splitlines()]
    balances: list[dict] = []

    name: Optional[str] = None
    currency: Optional[str] = None
    iban_last4: Optional[str] = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        dev = re.match(r"^Devise\s+([A-Z]{3})$", stripped)
        iban = re.match(r"^IBAN\s+([\d ]+)$", stripped)
        if re.match(r"^(Devise|IBAN|BIC|Type|Créé|Solde|Numéro|Code|Relevé|Informations)\b",
                    stripped) is None and stripped:
            # ligne « titre de compte » (Main, USD, Louis CAD, XRP, Hedging…)
            name = stripped
        if dev:
            currency = dev.group(1)
            iban_last4 = None
        elif iban:
            digits = iban.group(1).replace(" ", "")
            iban_last4 = digits[-4:] if len(digits) >= 4 else digits
        elif stripped == "Solde réglé":
            # le montant est sur une des lignes suivantes
            for nxt in lines[i + 1 : i + 3]:
                m = re.search(_AMOUNT, nxt.strip())
                if m:
                    cur = _currency(m.group(1), m.group(3)) or currency
                    balances.append({
                        "name": name,
                        "currency": cur,
                        "iban_last4": iban_last4,
                        "amount": _to_decimal(m.group(2)),
                    })
                    break
    return {"as_of": as_of, "balances": balances}
```

- [ ] **Step 4: Lancer le test → succès**

Run: `python3 -m pytest backend/tests/test_statement_extract.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-8] feat: extraction des soldes Revolut (Relevé des soldes)" backend/services/statement_extract.py backend/tests/test_statement_extract.py
```

---

### Task 3: Extraction du solde de fin de mois Qonto (CSV)

**Files:**
- Modify: `backend/services/statement_extract.py`
- Test: `backend/tests/test_statement_extract.py` (ajout)

**Interfaces:**
- Produces: `extract_qonto_month_end(csv_text: str, year: int, month: int) -> list[dict]` → un élément par compte : `{"account_name": str, "iban_last4": Optional[str], "currency": str, "amount": Decimal}` (solde de la dernière opération du mois).

- [ ] **Step 1: Écrire le test qui échoue**

```python
# à ajouter dans backend/tests/test_statement_extract.py
QONTO_CSV = (
    "Statut;Date de la valeur (local);Montant total (TTC);Débit;Crédit;Solde;Devise;"
    "Nom du compte;IBAN du compte\n"
    "Exécuté;15-02-2025;1000,00;;1000,00;5000,00;EUR;Compte principal;FR7616958000011078824351453\n"
    "Exécuté;27-02-2025;-200,00;200,00;;4800,00;EUR;Compte principal;FR7616958000011078824351453\n"
    "Exécuté;03-03-2025;-50,00;50,00;;4750,00;EUR;Compte principal;FR7616958000011078824351453\n"
)


def test_qonto_month_end_takes_last_solde_of_month():
    out = se.extract_qonto_month_end(QONTO_CSV, 2025, 2)
    assert len(out) == 1
    assert out[0]["currency"] == "EUR"
    assert out[0]["iban_last4"] == "1453"
    assert out[0]["amount"] == Decimal("4800.00")  # solde du 27/02, dernière op de févr


def test_qonto_month_end_empty_when_no_op():
    assert se.extract_qonto_month_end(QONTO_CSV, 2025, 1) == []
```

- [ ] **Step 2: Lancer le test → échec**

Run: `python3 -m pytest backend/tests/test_statement_extract.py::test_qonto_month_end_takes_last_solde_of_month -v`
Expected: FAIL — `AttributeError: ... extract_qonto_month_end`.

- [ ] **Step 3: Implémenter**

Ajouter à `backend/services/statement_extract.py` (imports `csv`, `io` en tête) :

```python
import csv
import io


def extract_qonto_month_end(csv_text: str, year: int, month: int) -> list[dict]:
    """Solde de fin de mois par compte = `Solde` de la dernière opération du mois."""
    reader = csv.DictReader(io.StringIO(csv_text), delimiter=";")
    last_by_account: dict[str, dict] = {}
    for row in reader:
        raw_date = (row.get("Date de la valeur (local)") or "").strip()
        m = re.match(r"^(\d{2})-(\d{2})-(\d{4})", raw_date)
        if not m:
            continue
        d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        if d.year != year or d.month != month:
            continue
        iban = (row.get("IBAN du compte") or "").strip()
        key = iban or (row.get("Nom du compte") or "").strip()
        # dernière opération du mois = on écrase, l'ordre du fichier est chronologique décroissant
        # ou croissant selon l'export → on garde la date max.
        prev = last_by_account.get(key)
        if prev is None or d >= prev["_date"]:
            last_by_account[key] = {
                "account_name": (row.get("Nom du compte") or "").strip(),
                "iban_last4": iban[-4:] if len(iban) >= 4 else (iban or None),
                "currency": (row.get("Devise") or "EUR").strip().upper(),
                "amount": _to_decimal((row.get("Solde") or "0").replace(",", ".")),
                "_date": d,
            }
    return [{k: v for k, v in item.items() if k != "_date"} for item in last_by_account.values()]
```

> Note DRY : `_to_decimal` gère déjà les espaces ; on remplace la virgule décimale FR de Qonto par un point avant de l'appeler.

- [ ] **Step 4: Lancer le test → succès**

Run: `python3 -m pytest backend/tests/test_statement_extract.py -v`
Expected: PASS (tous, dont les 2 nouveaux).

- [ ] **Step 5: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-8] feat: extraction du solde de fin de mois Qonto (CSV)" backend/services/statement_extract.py backend/tests/test_statement_extract.py
```

---

### Task 4: PDF→texte (pypdf) + mapping relevé → compte bancaire

**Files:**
- Modify: `backend/services/statement_extract.py`
- Test: `backend/tests/test_statement_extract.py` (ajout)

**Interfaces:**
- Produces: `pdf_to_text(data: bytes) -> str` ; `map_to_accounts(db, extracted: list[dict]) -> list[dict]` où chaque sortie = `{"account_uid": Optional[str], "currency": str, "amount": Decimal, "matched": bool, "hint": str}`. Mapping par `(currency, iban_last4)` puis repli `(currency, nom)`.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# à ajouter dans backend/tests/test_statement_extract.py
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from backend.db.base import Base
from backend.db import models


def _db():
    engine = create_engine("sqlite:///:memory:", future=True,
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, future=True)()
    db.add_all([
        models.BankAccount(provider="revolut", account_uid="u-eur", currency="EUR",
                           iban_masked="FR76****527", name="LGC"),
        models.BankAccount(provider="revolut", account_uid="u-usd-main", currency="USD",
                           iban_masked="FR76****527", name="LGC"),
        models.BankAccount(provider="revolut", account_uid="u-usd-2", currency="USD",
                           iban_masked="FR76****484", name="LGC"),
    ])
    db.commit()
    return db


def test_map_by_currency_and_iban_last4():
    db = _db()
    extracted = [
        {"name": "Main", "currency": "USD", "iban_last4": "3527", "amount": Decimal("80381.99")},
        {"name": "USD", "currency": "USD", "iban_last4": "7484", "amount": Decimal("40320.00")},
    ]
    out = {r["account_uid"]: r for r in se.map_to_accounts(db, extracted)}
    # iban_masked se termine par 527 → last4 "3527" doit matcher "…527"
    assert out["u-usd-main"]["amount"] == Decimal("80381.99")
    assert out["u-usd-2"]["amount"] == Decimal("40320.00")
    assert all(r["matched"] for r in out.values())


def test_map_unmatched_currency_flagged():
    db = _db()
    extracted = [{"name": "XRP", "currency": "XRP", "iban_last4": None, "amount": Decimal("3000")}]
    out = se.map_to_accounts(db, extracted)
    assert out[0]["matched"] is False
    assert out[0]["account_uid"] is None
```

- [ ] **Step 2: Lancer le test → échec**

Run: `python3 -m pytest backend/tests/test_statement_extract.py::test_map_by_currency_and_iban_last4 -v`
Expected: FAIL — `AttributeError: ... map_to_accounts`.

- [ ] **Step 3: Implémenter**

Ajouter à `backend/services/statement_extract.py` :

```python
from io import BytesIO

from sqlalchemy.orm import Session

from backend.db import models


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
```

> Note : l'IBAN en base est **masqué** (`FR76****527`, ~3 chiffres visibles) alors que le relevé donne les 4 derniers. On matche par suffixe (`last4.endswith(tail)`) pour rester robuste aux deux longueurs.

- [ ] **Step 4: Lancer le test → succès**

Run: `python3 -m pytest backend/tests/test_statement_extract.py -v`
Expected: PASS (tous).

- [ ] **Step 5: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-8] feat: PDF→texte (pypdf) + mapping relevé→compte par devise/IBAN" backend/services/statement_extract.py backend/tests/test_statement_extract.py
```

---

### Task 5: Reconstruction et tie-out mensuel

**Files:**
- Modify: `backend/services/openings.py` (exposer un helper public de somme de mouvements)
- Create: `backend/services/monthly_reconcile.py`
- Test: `backend/tests/test_monthly_reconcile.py`

**Interfaces:**
- Consumes: `openings.opening_anchor(db, acc, target_year) -> tuple[Optional[Decimal], Optional[date]]`, `openings.sum_movements(db, account_uid, start, upto) -> Decimal` (nouveau, wrap public de `_sum_tx_from`), `fx.load_rates`, `fx.to_eur`.
- Produces: `reconstruct_balance(db, account_uid, year, month) -> Decimal` ; `monthly_reconciliation(db, year) -> dict` (structure §Step 3).

- [ ] **Step 1: Écrire le test qui échoue**

```python
# backend/tests/test_monthly_reconcile.py
from decimal import Decimal
from datetime import date
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from backend.db.base import Base
from backend.db import models
from backend.services import monthly_reconcile as mr


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", future=True,
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, future=True)()
    db.add(models.Settings(id=1))
    db.add(models.FxRate(currency="USD", rate=Decimal("0.92")))
    db.add(models.BankAccount(provider="revolut", account_uid="acc", currency="EUR",
                              iban_masked="FR76****527", name="LGC", balance=Decimal("0")))
    # Ancre d'ouverture 2025 = 1000 au 01/01/2025
    db.add(models.OpeningBalance(account_uid="acc", year=2025, balance=Decimal("1000"), note=""))
    db.commit()
    yield db
    db.close()


def _tx(db, d, amount):
    db.add(models.Transaction(account_uid="acc", external_id=f"t{d}{amount}", booked_date=d,
                              amount=Decimal(amount), currency="EUR", kind="revenue"))
    db.commit()


def test_reconstruct_is_anchor_plus_movements_to_month_end(session):
    _tx(session, date(2025, 1, 10), "500")    # janv
    _tx(session, date(2025, 2, 5), "-200")     # févr
    _tx(session, date(2025, 3, 1), "999")      # mars (hors fin févr)
    # fin février = 1000 + 500 - 200 = 1300
    assert mr.reconstruct_balance(session, "acc", 2025, 2) == Decimal("1300.00")


def test_missing_fee_makes_month_warn(session):
    # solde officiel de fin janvier = 1450 (une commission de 50 a été prélevée en vrai)
    _tx(session, date(2025, 1, 10), "500")     # l'app ne voit QUE +500 → reconstruit 1500
    session.add(models.MonthlyBalance(account_uid="acc", year=2025, month=1,
                                      balance=Decimal("1450.00"), currency="EUR",
                                      confirmed_at=None))
    session.commit()
    view = mr.monthly_reconciliation(session, 2025)
    jan = view["months"][0]
    acc = jan["per_account"][0]
    assert acc["official"] == Decimal("1450.00")
    assert acc["reconstructed"] == Decimal("1500.00")
    assert acc["diff"] == Decimal("-50.00")   # officiel - reconstruit → frais manquant
    assert acc["status"] == "warn"
    assert jan["status"] == "warn"


def test_month_without_official_is_missing(session):
    view = mr.monthly_reconciliation(session, 2025)
    assert view["months"][5]["status"] == "missing"   # juin, aucune saisie
```

- [ ] **Step 2: Lancer le test → échec**

Run: `python3 -m pytest backend/tests/test_monthly_reconcile.py -v`
Expected: FAIL — `ModuleNotFoundError: backend.services.monthly_reconcile`.

- [ ] **Step 3: Implémenter**

D'abord, exposer un helper public dans `backend/services/openings.py` (juste après `_sum_tx_from`) — DRY, réutilise le privé existant :

```python
def sum_movements(db: Session, account_uid: str, start: date_type, upto: date_type) -> Decimal:
    """Σ des mouvements natifs d'un compte sur [start, upto] (wrap public)."""
    return _sum_tx_from(db, account_uid, start, upto)
```

Puis créer `backend/services/monthly_reconcile.py` :

```python
"""
Rapprochement mensuel : solde officiel de fin de mois (saisi depuis un relevé) vs
solde reconstitué par l'app (ancre d'ouverture d'exercice + Σ mouvements jusqu'à la
fin du mois). Un écart révèle un frais/mouvement manquant sur ce compte, ce mois-là.
"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from sqlalchemy.orm import Session

from backend.db import models
from backend.services import openings
from backend.services.fx import load_rates, to_eur

_CENTS = Decimal("0.01")


def _q2(v: Decimal) -> Decimal:
    return Decimal(v).quantize(_CENTS, rounding=ROUND_HALF_UP)


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def reconstruct_balance(db: Session, account_uid: str, year: int, month: int) -> Decimal:
    """Solde reconstitué à la fin du mois = ancre d'ouverture + Σ mouvements jusque-là."""
    acc = (
        db.query(models.BankAccount)
        .filter(models.BankAccount.account_uid == account_uid)
        .first()
    )
    if acc is None:
        return Decimal("0.00")
    anchor, anchor_date = openings.opening_anchor(db, acc, year)
    base = anchor if anchor is not None else Decimal("0")
    start = anchor_date or date(year, 1, 1)
    movements = openings.sum_movements(db, account_uid, start, _month_end(year, month))
    return _q2(base + movements)


def monthly_reconciliation(db: Session, year: int) -> dict:
    """Vue 12 mois : par compte, officiel vs reconstitué + statut ; totaux € + couverture."""
    rates = load_rates(db)
    accounts = db.query(models.BankAccount).order_by(models.BankAccount.id).all()
    officials = {
        (mb.account_uid, mb.month): mb
        for mb in db.query(models.MonthlyBalance).filter(models.MonthlyBalance.year == year).all()
    }
    months: list[dict] = []
    covered = 0
    for month in range(1, 13):
        per_account: list[dict] = []
        total_eur_official = Decimal("0")
        total_eur_diff = Decimal("0")
        any_official = False
        any_warn = False
        for acc in accounts:
            mb = officials.get((acc.account_uid, month))
            reconstructed = reconstruct_balance(db, acc.account_uid, year, month)
            official = Decimal(mb.balance) if mb is not None else None
            diff = _q2(official - reconstructed) if official is not None else None
            status = "missing"
            if official is not None:
                any_official = True
                status = "ok" if abs(diff) < _CENTS else "warn"
                any_warn = any_warn or status == "warn"
                cur = (acc.currency or "EUR").upper()
                total_eur_official += to_eur(official, cur, rates)
                total_eur_diff += to_eur(diff, cur, rates)
            per_account.append({
                "account_uid": acc.account_uid,
                "currency": (acc.currency or "EUR").upper(),
                "official": official,
                "reconstructed": reconstructed,
                "diff": diff,
                "status": status,
            })
        month_status = "missing" if not any_official else ("warn" if any_warn else "ok")
        if any_official:
            covered += 1
        months.append({
            "month": month,
            "per_account": per_account,
            "total_eur_official": _q2(total_eur_official),
            "total_eur_diff": _q2(total_eur_diff),
            "status": month_status,
        })
    return {"year": year, "months": months, "coverage": f"{covered}/12"}
```

- [ ] **Step 4: Lancer le test → succès**

Run: `python3 -m pytest backend/tests/test_monthly_reconcile.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-8] feat: reconstruction et tie-out mensuel (openings.sum_movements + monthly_reconcile)" backend/services/openings.py backend/services/monthly_reconcile.py backend/tests/test_monthly_reconcile.py
```

---

### Task 6: Routes API `/api/monthly-balances` + période sur l'upload de justificatif

**Files:**
- Create: `backend/api/routes/monthly_balances.py`
- Modify: `backend/api/main.py` (import + `include_router`)
- Modify: `backend/api/routes/balance_docs.py` (accepter `period_year`/`period_month` au `POST`)
- Test: `backend/tests/test_monthly_balances_api.py`

**Interfaces:**
- Consumes: `statement_extract.pdf_to_text/extract_revolut_balances/extract_qonto_month_end/map_to_accounts`, `monthly_reconcile.monthly_reconciliation`.
- Produces routes : `POST /api/monthly-balances/extract` (multipart `file`,`provider`,`year`,`month`) → proposition (n'écrit rien) ; `PUT /api/monthly-balances?year=&month=` (JSON) → upsert `MonthlyBalance` ; `GET /api/monthly-balances/reconciliation?year=` → vue.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# backend/tests/test_monthly_balances_api.py
from decimal import Decimal
from datetime import date
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from backend.db.base import Base, get_db
from backend.db import models
from backend.api.main import app


@pytest.fixture()
def client():
    engine = create_engine("sqlite:///:memory:", future=True,
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, future=True)
    db = TestingSession()
    db.add(models.Settings(id=1))
    db.add(models.BankAccount(provider="revolut", account_uid="acc", currency="EUR",
                              iban_masked="FR76****527", name="LGC", balance=Decimal("0")))
    db.add(models.OpeningBalance(account_uid="acc", year=2025, balance=Decimal("1000"), note=""))
    db.commit()

    def _override():
        s = TestingSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_put_then_reconciliation(client):
    r = client.put("/api/monthly-balances?year=2025&month=1",
                   json={"items": [{"account_uid": "acc", "balance": "1000.00"}]})
    assert r.status_code == 200
    view = client.get("/api/monthly-balances/reconciliation?year=2025").json()
    jan = view["months"][0]
    assert jan["status"] == "ok"           # officiel 1000 == reconstruit 1000
    assert view["coverage"] == "1/12"


def test_extract_does_not_write(client):
    csv_text = ("Statut;Date de la valeur (local);Solde;Devise;Nom du compte;IBAN du compte\n"
                "Exécuté;15-01-2025;1000,00;EUR;Compte principal;FR7616958000011078824351453\n")
    r = client.post("/api/monthly-balances/extract",
                    data={"provider": "qonto", "year": "2025", "month": "1"},
                    files={"file": ("q.csv", csv_text, "text/csv")})
    assert r.status_code == 200
    assert r.json()["proposal"]  # renvoie une proposition
    # rien n'a été écrit : la reconciliation reste sans officiel
    view = client.get("/api/monthly-balances/reconciliation?year=2025").json()
    assert view["coverage"] == "0/12"
```

- [ ] **Step 2: Lancer le test → échec**

Run: `python3 -m pytest backend/tests/test_monthly_balances_api.py -v`
Expected: FAIL — 404 sur les routes (non montées).

- [ ] **Step 3: Implémenter la route**

```python
# backend/api/routes/monthly_balances.py
"""
Routes Rapprochement mensuel officiel.

- POST /api/monthly-balances/extract        → proposition extraite (n'écrit RIEN)
- PUT  /api/monthly-balances?year=&month=   → upsert des soldes validés
- GET  /api/monthly-balances/reconciliation?year=  → vue 12 mois + tie-out
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.db import models
from backend.db.base import get_db
from backend.logging_config import get_logger
from backend.services import monthly_reconcile, statement_extract

logger = get_logger("monthly_balances", channel="api")

router = APIRouter(prefix="/api/monthly-balances", tags=["monthly-balances"])


class MonthlyItem(BaseModel):
    account_uid: str
    balance: Decimal


class MonthlyUpsert(BaseModel):
    items: list[MonthlyItem] = Field(default_factory=list)
    doc_id: Optional[int] = None


@router.post("/extract")
async def extract(
    file: UploadFile = File(...),
    provider: str = Form(...),
    year: int = Form(...),
    month: int = Form(...),
    db: Session = Depends(get_db),
) -> dict:
    """Extrait une proposition de soldes de fin de mois. N'écrit rien en base."""
    data = await file.read()
    if provider == "qonto":
        extracted = statement_extract.extract_qonto_month_end(data.decode("utf-8", "ignore"), year, month)
        mapped = statement_extract.map_to_accounts(db, [
            {"name": e["account_name"], "currency": e["currency"],
             "iban_last4": e["iban_last4"], "amount": e["amount"]} for e in extracted
        ])
    else:  # revolut (PDF)
        text = statement_extract.pdf_to_text(data)
        parsed = statement_extract.extract_revolut_balances(text)
        mapped = statement_extract.map_to_accounts(db, parsed["balances"])
    logger.info("📥 [MonthlyBalances] extract: %s %d-%02d → %d solde(s)",
                provider, year, month, len(mapped))
    return {"proposal": [
        {"account_uid": m["account_uid"], "currency": m["currency"],
         "amount": str(m["amount"]) if m["amount"] is not None else None,
         "matched": m["matched"], "hint": m["hint"]}
        for m in mapped
    ]}


@router.put("")
def upsert(payload: MonthlyUpsert, year: int = Query(...), month: int = Query(...),
           db: Session = Depends(get_db)) -> dict:
    """Upsert des soldes officiels validés pour (year, month)."""
    for it in payload.items:
        acc = (db.query(models.BankAccount)
               .filter(models.BankAccount.account_uid == it.account_uid).first())
        if acc is None:
            raise HTTPException(status_code=404, detail=f"Compte inconnu: {it.account_uid}")
        row = (db.query(models.MonthlyBalance)
               .filter(models.MonthlyBalance.account_uid == it.account_uid,
                       models.MonthlyBalance.year == year,
                       models.MonthlyBalance.month == month).first())
        if row is None:
            row = models.MonthlyBalance(account_uid=it.account_uid, year=year, month=month,
                                        currency=(acc.currency or "EUR").upper())
            db.add(row)
        row.balance = it.balance
        row.confirmed_at = datetime.utcnow()
        if payload.doc_id is not None:
            row.source_doc_id = payload.doc_id
    db.commit()
    logger.info("📤 [MonthlyBalances] upsert: %d-%02d, %d compte(s) ✅", year, month, len(payload.items))
    return monthly_reconcile.monthly_reconciliation(db, year)


@router.get("/reconciliation")
def reconciliation(year: int = Query(...), db: Session = Depends(get_db)) -> dict:
    """Vue 12 mois : officiel vs reconstitué + statut + couverture."""
    return monthly_reconcile.monthly_reconciliation(db, year)
```

Monter la route dans `backend/api/main.py` : ajouter l'import avec les autres (`from backend.api.routes import monthly_balances as monthly_balances_routes`) et, près des autres `include_router`, `app.include_router(monthly_balances_routes.router)`.

Enrichir `backend/api/routes/balance_docs.py` — dans `upload_doc`, ajouter les deux `Form` et les poser sur le modèle :
```python
    period_year: Optional[int] = Form(default=None),
    period_month: Optional[int] = Form(default=None),
```
et à la construction du `BalanceDocument`, ajouter `period_year=period_year, period_month=period_month,`.

- [ ] **Step 4: Lancer le test → succès**

Run: `python3 -m pytest backend/tests/test_monthly_balances_api.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Lancer toute la suite back (non-régression)**

Run: `python3 -m pytest backend/ -q`
Expected: tout vert (les tests existants + les nouveaux).

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-8] feat: routes /api/monthly-balances (extract/PUT/reconciliation) + période sur balance-docs" backend/api/routes/monthly_balances.py backend/api/main.py backend/api/routes/balance_docs.py backend/tests/test_monthly_balances_api.py
```

---

### Task 7: UI — carte « Rapprochement mensuel » sur la page Banques

**Files:**
- Modify: `frontend/src/api/client.ts` (ajout `monthlyBalancesAPI` + types)
- Create: `frontend/src/components/MonthlyReconcileCard.tsx`
- Modify: `frontend/app/banking/page.tsx` (rendre `<MonthlyReconcileCard />`)
- Test: `frontend/__tests__/monthly-reconcile.test.tsx`

**Interfaces:**
- Consumes: `GET /api/monthly-balances/reconciliation?year=`, `POST /api/monthly-balances/extract`, `PUT /api/monthly-balances`. Structure `reconciliation` = `{ year, coverage, months: [{ month, status, total_eur_official, total_eur_diff, per_account: [{account_uid, currency, official, reconstructed, diff, status}] }] }`.

- [ ] **Step 1: Écrire le test qui échoue**

```tsx
// frontend/__tests__/monthly-reconcile.test.tsx
import { render, screen, fireEvent } from '@testing-library/react';
import { MonthlyReconcileCard } from '@/components/MonthlyReconcileCard';

jest.mock('next/navigation', () => ({ usePathname: () => '/banking' }));
jest.mock('@/api/client', () => ({
  monthlyBalancesAPI: {
    reconciliation: jest.fn().mockResolvedValue({
      year: 2025, coverage: '1/12',
      months: [
        { month: 1, status: 'warn', total_eur_official: '1450.00', total_eur_diff: '-50.00',
          per_account: [{ account_uid: 'acc', currency: 'EUR', official: '1450.00',
                          reconstructed: '1500.00', diff: '-50.00', status: 'warn' }] },
        ...Array.from({ length: 11 }, (_, i) => ({
          month: i + 2, status: 'missing', total_eur_official: '0.00', total_eur_diff: '0.00',
          per_account: [],
        })),
      ],
    }),
  },
}));

test('affiche les 12 mois, la couverture, et déplie le détail par compte', async () => {
  render(<MonthlyReconcileCard year={2025} />);
  expect(await screen.findByText('1/12')).toBeInTheDocument();
  // le mois de janvier est en écart
  const janv = await screen.findByText(/Janv/i);
  fireEvent.click(janv);
  expect(await screen.findByText(/−50,00|−50\.00|-50/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Lancer le test → échec**

Run: `cd /Users/louisgarnier/Claude/compta_sasu/frontend && npx jest monthly-reconcile -t "affiche les 12 mois"`
Expected: FAIL — module `@/components/MonthlyReconcileCard` introuvable.

- [ ] **Step 3: Ajouter le client API**

Dans `frontend/src/api/client.ts`, ajouter (près de `balanceDocsAPI`) :

```typescript
export type MonthlyAccountRow = {
  account_uid: string; currency: string;
  official: string | null; reconstructed: string; diff: string | null; status: string;
};
export type MonthlyMonth = {
  month: number; status: 'ok' | 'warn' | 'missing';
  total_eur_official: string; total_eur_diff: string; per_account: MonthlyAccountRow[];
};
export type MonthlyReconView = { year: number; coverage: string; months: MonthlyMonth[] };

export const monthlyBalancesAPI = {
  reconciliation: (year: number): Promise<MonthlyReconView> =>
    apiFetch(`/api/monthly-balances/reconciliation?year=${year}`),
  extract: (form: FormData) =>
    fetch(`${API_BASE_URL}/api/monthly-balances/extract`, { method: 'POST', body: form })
      .then((r) => r.json()),
  confirm: (year: number, month: number, items: { account_uid: string; balance: string }[],
            docId?: number) =>
    apiFetch(`/api/monthly-balances?year=${year}&month=${month}`, {
      method: 'PUT',
      body: JSON.stringify({ items, doc_id: docId ?? null }),
    }),
};
```

> `apiFetch` est le helper interne existant du fichier (cf. les autres `*API`). S'il porte un autre nom, réutiliser exactement celui déjà employé par `openingsAPI`.

- [ ] **Step 4: Créer le composant**

```tsx
// frontend/src/components/MonthlyReconcileCard.tsx
'use client';

import { useEffect, useState } from 'react';
import { monthlyBalancesAPI, type MonthlyReconView } from '@/api/client';
import { Card, Badge } from '@/components/ui';
import { eur } from '@/lib/format';

const MOIS = ['Janv', 'Févr', 'Mars', 'Avr', 'Mai', 'Juin', 'Juil', 'Août', 'Sept', 'Oct', 'Nov', 'Déc'];

const badgeFor = (s: string) =>
  s === 'ok' ? <Badge tone="success">✓ ok</Badge>
  : s === 'warn' ? <Badge tone="warn">⚠ écart</Badge>
  : <Badge tone="muted">manquant</Badge>;

export function MonthlyReconcileCard({ year }: { year: number }) {
  const [view, setView] = useState<MonthlyReconView | null>(null);
  const [open, setOpen] = useState<number | null>(null);

  useEffect(() => {
    monthlyBalancesAPI.reconciliation(year).then(setView).catch(() => setView(null));
  }, [year]);

  if (!view) return <Card><p className="text-sm text-gray-500">Chargement…</p></Card>;

  return (
    <Card>
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold">Rapprochement mensuel officiel</h3>
        <span className="text-sm text-gray-500">Couverture <strong>{view.coverage}</strong> mois</span>
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-gray-500 bg-gray-50">
            <th className="py-2 px-3">Fin de mois</th>
            <th className="py-2 px-3 text-right">Solde officiel (€)</th>
            <th className="py-2 px-3 text-right">Écart</th>
            <th className="py-2 px-3">Statut</th>
          </tr>
        </thead>
        <tbody>
          {view.months.map((m) => (
            <>
              <tr key={m.month} className="border-t cursor-pointer"
                  onClick={() => setOpen(open === m.month ? null : m.month)}>
                <td className="py-2 px-3">{MOIS[m.month - 1]} {view.year}</td>
                <td className="py-2 px-3 text-right tabular-nums">
                  {m.status === 'missing' ? '—' : eur(m.total_eur_official)}
                </td>
                <td className="py-2 px-3 text-right tabular-nums">
                  {m.status === 'missing' ? '—' : eur(m.total_eur_diff)}
                </td>
                <td className="py-2 px-3">{badgeFor(m.status)}</td>
              </tr>
              {open === m.month && m.per_account.length > 0 && (
                <tr key={`${m.month}-d`} className="bg-gray-50">
                  <td colSpan={4} className="px-3 pb-3">
                    <table className="w-full text-xs">
                      <tbody>
                        {m.per_account.map((a) => (
                          <tr key={a.account_uid} className="border-t">
                            <td className="py-1">{a.currency}</td>
                            <td className="py-1 text-right tabular-nums">{a.official ?? '—'}</td>
                            <td className="py-1 text-right tabular-nums">{a.reconstructed}</td>
                            <td className="py-1 text-right tabular-nums">{a.diff ?? '—'}</td>
                            <td className="py-1">{badgeFor(a.status)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </td>
                </tr>
              )}
            </>
          ))}
        </tbody>
      </table>
    </Card>
  );
}
```

> `Badge` tones : réutiliser les tons existants de `@/components/ui` (`success`/`warn`/`muted` ou équivalents réellement présents — vérifier la signature du composant `Badge` avant de coder, adapter les noms de tons si besoin). `eur()` de `@/lib/format` formate une string/number en euros FR.

- [ ] **Step 5: Monter le composant sur la page Banques**

Dans `frontend/app/banking/page.tsx` : importer `import { MonthlyReconcileCard } from '@/components/MonthlyReconcileCard';` et le rendre dans la colonne principale (près de la carte des soldes), avec l'année courante : `<MonthlyReconcileCard year={new Date().getFullYear()} />`.

- [ ] **Step 6: Lancer le test → succès**

Run: `cd frontend && npx jest monthly-reconcile`
Expected: PASS.

- [ ] **Step 7: Lancer la suite front (non-régression) + build**

Run: `cd frontend && npx jest && npx tsc --noEmit`
Expected: tout vert, tsc clean.

- [ ] **Step 8: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-8] feat: carte Rapprochement mensuel sur la page Banques + client monthlyBalancesAPI" frontend/src/api/client.ts frontend/src/components/MonthlyReconcileCard.tsx frontend/app/banking/page.tsx frontend/__tests__/monthly-reconcile.test.tsx
```

---

### Task 8: Flux de dépôt → confirmation (ingestion hybride)

**Files:**
- Modify: `frontend/src/components/MonthlyReconcileCard.tsx` (bandeau dépôt + modale de confirmation)
- Test: `frontend/__tests__/monthly-reconcile.test.tsx` (ajout)

**Interfaces:**
- Consumes: `monthlyBalancesAPI.extract(FormData)` → `{ proposal: [{account_uid, currency, amount, matched, hint}] }` ; `monthlyBalancesAPI.confirm(year, month, items, docId?)`.

- [ ] **Step 1: Écrire le test qui échoue**

```tsx
// à ajouter dans frontend/__tests__/monthly-reconcile.test.tsx
test('dépôt d’un relevé → propose des soldes → confirmation les enregistre', async () => {
  const { monthlyBalancesAPI } = require('@/api/client');
  monthlyBalancesAPI.extract = jest.fn().mockResolvedValue({
    proposal: [{ account_uid: 'acc', currency: 'EUR', amount: '11626.90', matched: true, hint: 'Main' }],
  });
  monthlyBalancesAPI.confirm = jest.fn().mockResolvedValue({ year: 2025, coverage: '2/12', months: [] });

  render(<MonthlyReconcileCard year={2025} />);
  const drop = await screen.findByLabelText(/Déposer un relevé/i);
  fireEvent.change(drop, { target: { files: [new File(['x'], 'r.pdf', { type: 'application/pdf' })] } });
  // la proposition apparaît, on valide
  expect(await screen.findByText(/11 626,90|11626.90/)).toBeInTheDocument();
  fireEvent.click(await screen.findByRole('button', { name: /Valider/i }));
  expect(monthlyBalancesAPI.confirm).toHaveBeenCalled();
});
```

- [ ] **Step 2: Lancer le test → échec**

Run: `cd frontend && npx jest monthly-reconcile -t "dépôt d’un relevé"`
Expected: FAIL — pas de champ « Déposer un relevé ».

- [ ] **Step 3: Implémenter le bandeau + la modale**

Dans `MonthlyReconcileCard.tsx`, ajouter au-dessus du tableau un bandeau avec un `<input type="file" aria-label="Déposer un relevé" />` (+ un sélecteur `provider` revolut/qonto et le mois), un état `proposal`, l'appel `extract`, une petite modale listant les soldes proposés éditables, et un bouton « Valider les N soldes » qui appelle `confirm(year, month, items, docId?)` puis rafraîchit la vue (`reconciliation`). Détail minimal :

```tsx
  const [proposal, setProposal] = useState<null | { account_uid: string; currency: string; amount: string }[]>(null);
  const [month, setMonth] = useState(12);
  const [provider, setProvider] = useState<'revolut' | 'qonto'>('revolut');

  const onDrop = async (files: FileList | null) => {
    if (!files?.[0]) return;
    const fd = new FormData();
    fd.append('file', files[0]);
    fd.append('provider', provider);
    fd.append('year', String(year));
    fd.append('month', String(month));
    const res = await monthlyBalancesAPI.extract(fd);
    setProposal(res.proposal.filter((p: any) => p.account_uid));
  };

  const validate = async () => {
    if (!proposal) return;
    const items = proposal.map((p) => ({ account_uid: p.account_uid, balance: p.amount }));
    const updated = await monthlyBalancesAPI.confirm(year, month, items);
    setProposal(null);
    setView(updated);
  };
```

Bandeau (au-dessus du `<table>`), avec le compteur déjà présent, et rendu conditionnel de la modale quand `proposal` non nul (liste `proposal.map(...)` + bouton « Valider les {proposal.length} soldes »). Les montants s'affichent via `eur()`/`money()` selon la devise.

- [ ] **Step 4: Lancer le test → succès**

Run: `cd frontend && npx jest monthly-reconcile`
Expected: PASS (tous).

- [ ] **Step 5: Vérif manuelle bout-en-bout (self-test)**

Lancer l'app (`make dev` ; ports back `:8001` / front `:3001`). Sur la page Banques : déposer `docs/Doc_comptable/2025/statement-of-balances_31-Dec-2025 (1).pdf` (provider Revolut, mois 12) → vérifier que les 5-6 soldes extraits correspondent (Main EUR 11 626,90 · Main USD 80 381,99 · USD 40 320 · CAD 5 580 · XRP 3 000) → valider → la ligne Déc passe ✅/⚠️. Coller le résultat (capture ou soldes lus) comme preuve.

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-8] feat: ingestion hybride — dépôt d'un relevé → extraction → confirmation" frontend/src/components/MonthlyReconcileCard.tsx frontend/__tests__/monthly-reconcile.test.tsx
```

---

### Task 9: Docs de clôture (build-log, codebase)

**Files:**
- Modify: `docs/project/config/build-log.md`
- Modify: `docs/project/config/codebase.md`

- [ ] **Step 1: Mettre à jour build-log.md**

Ajouter une entrée datée 2026-07-16 : EPIC-8 Étape 1 — rapprochement mensuel officiel (modèle `monthly_balances`, extraction Revolut/Qonto via pypdf, tie-out mensuel, carte Banques), avec les invariants vérifiés (nb de tests back/front verts, extraction Déc 2025 validée).

- [ ] **Step 2: Mettre à jour codebase.md**

Documenter les nouveaux modules : `services/statement_extract.py`, `services/monthly_reconcile.py`, route `monthly_balances.py`, composant `MonthlyReconcileCard.tsx`, `monthlyBalancesAPI`, table `monthly_balances`, colonnes `period_year/period_month`.

- [ ] **Step 3: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-8] docs: build-log + codebase — rapprochement mensuel officiel (étape 1)" docs/project/config/build-log.md docs/project/config/codebase.md
```

---

## Self-Review (fait)

**Spec coverage :** §4 modèle → Task 1 ; §5 extraction (Revolut/Qonto/mapping/hybride) → Tasks 2-4, 6, 8 ; §6 tie-out → Task 5 ; §7 API → Task 6 ; §8 UI → Tasks 7-8 ; §9 PII → `.gitignore` déjà fait + `data/` ignoré ; §10 tests → chaque task en TDD. Étape 2 (§11) hors périmètre, non planifiée (voulu).

**Placeholder scan :** aucun TBD/TODO ; chaque step de code montre le code. Deux points « vérifier la signature existante avant de coder » (helper `apiFetch`, tons de `Badge`) sont des garde-fous d'intégration, pas des placeholders — la valeur par défaut y est donnée.

**Type consistency :** `monthly_reconciliation` renvoie la même structure consommée par `MonthlyReconview` (front) et par les tests API. `map_to_accounts` consomme la sortie de `extract_revolut_balances` (`name/currency/iban_last4/amount`) — cohérent. `sum_movements` (public) ajouté en Task 5 et consommé au même endroit.

**Risque connu :** robustesse du parseur Revolut selon la linéarisation réelle de pypdf — atténué par l'étape de confirmation obligatoire (Task 8, Step 5 valide sur le vrai PDF) et le repli « proposition vide » si le format diffère.
