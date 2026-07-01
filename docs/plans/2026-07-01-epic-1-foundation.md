# EPIC-1 Foundation & Scaffold — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the template scaffold into the LGC foundation: a running FastAPI + Next.js app backed by a SQLAlchemy/SQLite database holding all domain entities, with logging and a seeded Settings record.

**Architecture:** Keep the existing FastAPI (`backend/`) + Next.js (`frontend/`) split. Replace the template's raw-SQL init with **SQLAlchemy 2.0** models + a single `create_all` bootstrap (Alembic deferred to the first real schema change, Epic 2+). All money is `Decimal`/`Numeric`. Local SQLite file at `data/lgc.db`.

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy 2.0, python-dotenv, pytest (backend). Next.js 16 / React 19 / Tailwind 4 (frontend). venv + pip (no uv on this machine).

## Global Constraints

- Python **3.10+** (machine has 3.10.2). Node 24.
- **Money is always `Decimal` / SQLAlchemy `Numeric(14,2)`** — never `float`.
- SQLite must run with `PRAGMA foreign_keys=ON` on every connection.
- **No secrets in code** — all via `.env` (gitignored); ship `.env.example`.
- **Never log PII/bank data in clear** — IBANs masked via `mask_iban()`; log transaction IDs only.
- Logging format: `[ModuleName] verb: detail`, emojis 📥📤✅❌⚠️🗄️🚀. Files `logs/backend_YYYY-MM-DD.log`, `logs/api_YYYY-MM-DD.log`.
- All git via `python3 scripts/git_ops.py`. Commit format: `[EPIC-1] type: short description`. Work on branch `epic-1-foundation` (never commit to `main` directly).
- Start date anchor for the whole product: **2026-01-01** (opening balances live on `bank_accounts`).

---

### Task 0: Branch + dependencies + env

**Files:**
- Modify: `backend/requirements.txt`
- Create: `.env.example`
- Modify: `.gitignore` (ensure `.env`, `data/`, `secrets/` ignored)

- [ ] **Step 1: Create the feature branch**

Run: `python3 scripts/git_ops.py branch epic-1-foundation`
Expected: switched to a new branch `epic-1-foundation`.

- [ ] **Step 2: Add backend dependencies**

Replace `backend/requirements.txt` with:

```
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
python-multipart>=0.0.6
pydantic>=2.0.0
python-dotenv>=1.0.0
SQLAlchemy>=2.0.0
httpx>=0.25.0
pytest>=7.4.0
pytest-cov>=4.1.0
```

- [ ] **Step 3: Install into the backend venv**

Run:
```bash
cd backend && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt && cd ..
```
Expected: SQLAlchemy + python-dotenv install successfully.

- [ ] **Step 4: Create `.env.example`**

```
# Database
DATABASE_URL=sqlite:///./data/lgc.db

# Logging
LOG_LEVEL=INFO

# Enable Banking (rempli à l'Epic 2 — laisser vide pour l'instant)
ENABLE_BANKING_APP_ID=
ENABLE_BANKING_PRIVATE_KEY_PATH=./secrets/eb_private.pem
ENABLE_BANKING_REDIRECT_URL=http://localhost:3000/banking/callback
```

- [ ] **Step 5: Ensure `.gitignore` covers secrets and data**

Confirm these lines exist in `.gitignore` (append any missing):
```
.env
data/
secrets/
backend/venv/
```

- [ ] **Step 6: Commit**

Run: `python3 scripts/git_ops.py commit "[EPIC-1] chore: branch, deps (SQLAlchemy), env template"`

---

### Task 1: Config module

**Files:**
- Create: `backend/config.py`
- Test: `backend/tests/test_config.py`

**Interfaces:**
- Produces: `settings` object with attributes `database_url: str`, `log_level: str`, `enable_banking_app_id: str`, `enable_banking_private_key_path: str`, `enable_banking_redirect_url: str`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_config.py
from backend.config import settings

def test_config_has_defaults():
    assert settings.database_url.startswith("sqlite")
    assert settings.log_level in {"DEBUG", "INFO", "WARNING", "ERROR"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: backend.config`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/config.py
"""Central configuration loaded from environment / .env."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/lgc.db")
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
    enable_banking_app_id: str = os.getenv("ENABLE_BANKING_APP_ID", "")
    enable_banking_private_key_path: str = os.getenv(
        "ENABLE_BANKING_PRIVATE_KEY_PATH", "./secrets/eb_private.pem"
    )
    enable_banking_redirect_url: str = os.getenv(
        "ENABLE_BANKING_REDIRECT_URL", "http://localhost:3000/banking/callback"
    )


settings = Settings()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

Run: `python3 scripts/git_ops.py commit "[EPIC-1] feat: config module from env"`

---

### Task 2: Logging foundation + PII masking

**Files:**
- Create: `backend/logging_config.py`
- Test: `backend/tests/test_logging.py`

**Interfaces:**
- Produces: `get_logger(module: str) -> logging.Logger` (writes to `logs/backend_YYYY-MM-DD.log`), and `mask_iban(value: str) -> str` (keeps first 4 + last 4, masks middle).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_logging.py
from backend.logging_config import get_logger, mask_iban

def test_mask_iban_hides_middle():
    assert mask_iban("FR7628233000014550298993527") == "FR76…3527"

def test_mask_iban_short_value():
    assert mask_iban("AB12") == "****"

def test_get_logger_returns_named_logger():
    log = get_logger("Test")
    assert log.name == "Test"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_logging.py -v`
Expected: FAIL with `ModuleNotFoundError: backend.logging_config`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/logging_config.py
"""Logging setup: [Module] verb: detail, file per day, PII masking."""
import logging
from datetime import date
from pathlib import Path
from backend.config import settings

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

_FMT = "%(asctime)s [%(name)s] %(message)s"


def mask_iban(value: str) -> str:
    """Keep first 4 and last 4 chars, mask the rest. Short values fully masked."""
    if not value or len(value) < 10:
        return "****"
    return f"{value[:4]}…{value[-4:]}"


def get_logger(module: str) -> logging.Logger:
    logger = logging.getLogger(module)
    if logger.handlers:
        return logger
    logger.setLevel(settings.log_level)
    fh = logging.FileHandler(LOG_DIR / f"backend_{date.today().isoformat()}.log")
    fh.setFormatter(logging.Formatter(_FMT))
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter(_FMT))
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_logging.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

Run: `python3 scripts/git_ops.py commit "[EPIC-1] feat: logging foundation with IBAN masking"`

---

### Task 3: Database engine & session

**Files:**
- Create: `backend/db/__init__.py`
- Create: `backend/db/base.py`
- Create: `backend/db/session.py`
- Test: `backend/tests/test_db_session.py`

**Interfaces:**
- Produces: `Base` (DeclarativeBase), `engine`, `SessionLocal` (sessionmaker), `get_session()` generator. FK pragma enabled on every SQLite connection.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_db_session.py
from sqlalchemy import text
from backend.db.session import engine

def test_foreign_keys_pragma_on():
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_db_session.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/db/base.py
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass
```

```python
# backend/db/session.py
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from backend.config import settings

# Ensure ./data exists for the sqlite file
Path(__file__).parent.parent.parent.joinpath("data").mkdir(exist_ok=True)

engine = create_engine(
    settings.database_url, connect_args={"check_same_thread": False}
)

@event.listens_for(engine, "connect")
def _fk_pragma(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

```python
# backend/db/__init__.py
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_db_session.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

Run: `python3 scripts/git_ops.py commit "[EPIC-1] feat: SQLAlchemy engine + session with FK pragma"`

---

### Task 4: Domain models (all entities)

**Files:**
- Create: `backend/db/models.py`
- Test: `backend/tests/test_models.py`

**Interfaces:**
- Produces the ORM classes used by every later epic: `Settings`, `Client`, `BankAccount`, `Category`, `CategoryRule`, `Transaction`, `Invoice`, `Investment`, `ForecastInput`. Money columns use `Numeric(14, 2)`. `Transaction.kind` ∈ {revenue, charge, conversion, transfer, investment, other}.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_models.py
from decimal import Decimal
from datetime import date
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, event
from backend.db.base import Base
from backend.db import models

def _mem_session():
    eng = create_engine("sqlite://")
    @event.listens_for(eng, "connect")
    def _fk(c, _):
        c.cursor().execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()

def test_create_all_entities_and_relationship():
    s = _mem_session()
    client = models.Client(code="SWIB", legal_name="JPSB Consulting Inc",
                           currency="USD", tjh=Decimal("120.00"))
    s.add(client); s.commit()
    inv = models.Invoice(number=62, client_id=client.id, period_label="Jan 2026",
                         hours=Decimal("152"), rate=Decimal("120.00"),
                         currency="USD", amount=Decimal("18240.00"),
                         issue_date=date(2026, 2, 6), due_date=date(2026, 4, 6),
                         status="draft")
    s.add(inv); s.commit()
    assert client.invoices[0].number == 62
    assert isinstance(inv.amount, Decimal)

def test_bank_account_has_opening_balance():
    s = _mem_session()
    acc = models.BankAccount(provider="revolut", account_uid="uid-1", currency="EUR",
                             opening_balance=Decimal("24.38"), opening_balance_date=date(2026,1,1))
    s.add(acc); s.commit()
    assert acc.opening_balance == Decimal("24.38")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_models.py -v`
Expected: FAIL (models not defined).

- [ ] **Step 3: Write minimal implementation**

```python
# backend/db/models.py
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import String, Numeric, Integer, Date, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.db.base import Base

Money = Numeric(14, 2)


class Settings(Base):
    __tablename__ = "settings"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    company_name: Mapped[str] = mapped_column(String, default="SASU LGC")
    siret: Mapped[str] = mapped_column(String, default="")
    naf: Mapped[str] = mapped_column(String, default="6202A")
    tva_intracom: Mapped[str] = mapped_column(String, default="")
    address: Mapped[str] = mapped_column(String, default="")
    is_low_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.15"))
    is_threshold: Mapped[Decimal] = mapped_column(Money, default=Decimal("42500.00"))
    is_high_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.25"))
    next_invoice_number: Mapped[int] = mapped_column(Integer, default=62)
    default_fx_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("1.15"))
    default_fx_cad: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("1.61"))


class Client(Base):
    __tablename__ = "clients"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String, unique=True)  # SWIB | NWH
    legal_name: Mapped[str] = mapped_column(String)
    address: Mapped[str] = mapped_column(String, default="")
    currency: Mapped[str] = mapped_column(String)           # USD | CAD
    tjh: Mapped[Decimal] = mapped_column(Money)
    pay_iban: Mapped[str] = mapped_column(String, default="")
    counterparty_match: Mapped[str] = mapped_column(String, default="")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="client")


class BankAccount(Base):
    __tablename__ = "bank_accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String)           # revolut | qonto
    account_uid: Mapped[str] = mapped_column(String, unique=True)
    currency: Mapped[str] = mapped_column(String)
    iban_masked: Mapped[str] = mapped_column(String, default="")
    name: Mapped[str] = mapped_column(String, default="")
    balance: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    opening_balance: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    opening_balance_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    type: Mapped[str] = mapped_column(String)  # revenue|charge|conversion|transfer|investment|internal|uncategorized
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"), nullable=True)
    is_system: Mapped[bool] = mapped_column(default=False)


class CategoryRule(Base):
    __tablename__ = "category_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    match_field: Mapped[str] = mapped_column(String)   # counterparty | description
    pattern: Mapped[str] = mapped_column(String)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    priority: Mapped[int] = mapped_column(Integer, default=100)
    enabled: Mapped[bool] = mapped_column(default=True)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = ()  # composite unique added below
    id: Mapped[int] = mapped_column(primary_key=True)
    account_uid: Mapped[str] = mapped_column(ForeignKey("bank_accounts.account_uid"))
    external_id: Mapped[str] = mapped_column(String)
    booked_date: Mapped[date] = mapped_column(Date)
    value_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String, default="")
    counterparty: Mapped[str] = mapped_column(String, default="")
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String, default="other")
    fx_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), nullable=True)
    amount_eur: Mapped[Optional[Decimal]] = mapped_column(Money, nullable=True)
    linked_conversion_id: Mapped[Optional[int]] = mapped_column(ForeignKey("transactions.id"), nullable=True)
    invoice_id: Mapped[Optional[int]] = mapped_column(ForeignKey("invoices.id"), nullable=True)
    raw_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


from sqlalchemy import UniqueConstraint
Transaction.__table_args__ = (
    UniqueConstraint("account_uid", "external_id", name="uq_txn_account_external"),
)


class Invoice(Base):
    __tablename__ = "invoices"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[int] = mapped_column(Integer, unique=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    period_label: Mapped[str] = mapped_column(String)
    period_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    hours: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    rate: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String)
    amount: Mapped[Decimal] = mapped_column(Money)
    issue_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String, default="draft")  # draft|sent|paid
    paid_transaction_id: Mapped[Optional[int]] = mapped_column(ForeignKey("transactions.id"), nullable=True)
    pdf_path: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    client: Mapped["Client"] = relationship(back_populates="invoices")


class Investment(Base):
    __tablename__ = "investments"
    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)       # crypto|bourse|placement|autre
    currency: Mapped[str] = mapped_column(String, default="EUR")
    opening_value: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    opening_value_eur: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    current_value: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    current_value_eur: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    as_of_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    note: Mapped[str] = mapped_column(String, default="")


class ForecastInput(Base):
    __tablename__ = "forecast_inputs"
    id: Mapped[int] = mapped_column(primary_key=True)
    month: Mapped[str] = mapped_column(String)      # YYYY-MM
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    days: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    rate: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    fx_rate: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("1"))
    note: Mapped[str] = mapped_column(String, default="")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_models.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

Run: `python3 scripts/git_ops.py commit "[EPIC-1] feat: all domain ORM models"`

---

### Task 5: DB bootstrap wired into app startup

**Files:**
- Create: `backend/db/init_db.py`
- Modify: `backend/api/main.py` (replace `init_database` import/call; update title; add DB check to `/health`)
- Modify: `backend/database/connection.py` — leave file but STOP calling it from main (legacy; will be removed in a later cleanup). Do not delete yet.
- Test: `backend/tests/test_health.py`

**Interfaces:**
- Consumes: `Base` (Task 3), all models (Task 4), `SessionLocal` (Task 3).
- Produces: `init_db()` that runs `Base.metadata.create_all(engine)` and seeds a singleton `Settings` row if absent.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_health.py
from fastapi.testclient import TestClient
from backend.api.main import app

def test_health_reports_db_ok():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"
    assert r.json()["database"] == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_health.py -v`
Expected: FAIL (`database` key missing).

- [ ] **Step 3: Write the implementation**

```python
# backend/db/init_db.py
from backend.db.base import Base
from backend.db.session import engine, SessionLocal
from backend.db import models
from backend.logging_config import get_logger

log = get_logger("DB")

def init_db() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as s:
        if s.get(models.Settings, 1) is None:
            s.add(models.Settings(id=1))
            s.commit()
            log.info("🗄️ seed: default Settings row created")
    log.info("🚀 startup: database ready")
```

Then edit `backend/api/main.py`:
- Replace line `from backend.database.connection import init_database` with `from backend.db.init_db import init_db`.
- In `lifespan`, replace `init_database()` with `init_db()`.
- Change `title="API Template"` → `title="LGC Compta API"`.
- Replace the `/health` handler with:

```python
@app.get("/health")
async def health():
    """Health check + DB connectivity."""
    from sqlalchemy import text
    from backend.db.session import engine
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db = "ok"
    except Exception:
        db = "error"
    return {"status": "healthy", "database": db}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_health.py -v`
Expected: PASS.

- [ ] **Step 5: Run the FULL backend suite (guard against template test breakage)**

Run: `cd backend && source venv/bin/activate && python -m pytest -v`
Expected: all pass. If `tests/test_database.py` (legacy template) fails because it referenced the old example schema, update it to assert `init_db()` creates the `settings` table instead, or mark it obsolete — do NOT leave it red.

- [ ] **Step 6: Commit**

Run: `python3 scripts/git_ops.py commit "[EPIC-1] feat: SQLAlchemy bootstrap + DB-aware health"`

---

### Task 6: Settings API (read + update)

**Files:**
- Create: `backend/api/routes/settings.py`
- Create: `backend/api/schemas.py`
- Modify: `backend/api/main.py` (include the settings router)
- Test: `backend/tests/test_settings_api.py`

**Interfaces:**
- Consumes: `get_session` (Task 3), `models.Settings` (Task 4).
- Produces: `GET /api/settings` → current settings JSON; `PUT /api/settings` → updates and returns them. Pydantic `SettingsOut` / `SettingsUpdate` (all fields optional on update).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_settings_api.py
from fastapi.testclient import TestClient
from backend.api.main import app
from backend.db.init_db import init_db

def setup_module(_):
    init_db()

def test_get_settings_returns_seed():
    c = TestClient(app)
    r = c.get("/api/settings")
    assert r.status_code == 200
    assert r.json()["next_invoice_number"] == 62

def test_put_settings_updates_siret():
    c = TestClient(app)
    r = c.put("/api/settings", json={"siret": "89218975400013"})
    assert r.status_code == 200
    assert r.json()["siret"] == "89218975400013"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_settings_api.py -v`
Expected: FAIL (404 — route not registered).

- [ ] **Step 3: Write the implementation**

```python
# backend/api/schemas.py
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel

class SettingsOut(BaseModel):
    company_name: str
    siret: str
    naf: str
    tva_intracom: str
    address: str
    is_low_rate: Decimal
    is_threshold: Decimal
    is_high_rate: Decimal
    next_invoice_number: int
    default_fx_usd: Decimal
    default_fx_cad: Decimal
    class Config:
        from_attributes = True

class SettingsUpdate(BaseModel):
    company_name: Optional[str] = None
    siret: Optional[str] = None
    naf: Optional[str] = None
    tva_intracom: Optional[str] = None
    address: Optional[str] = None
    is_low_rate: Optional[Decimal] = None
    is_threshold: Optional[Decimal] = None
    is_high_rate: Optional[Decimal] = None
    next_invoice_number: Optional[int] = None
    default_fx_usd: Optional[Decimal] = None
    default_fx_cad: Optional[Decimal] = None
```

```python
# backend/api/routes/settings.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.db.session import get_session
from backend.db import models
from backend.api.schemas import SettingsOut, SettingsUpdate

router = APIRouter()

@router.get("/settings", response_model=SettingsOut)
def get_settings(db: Session = Depends(get_session)):
    row = db.get(models.Settings, 1)
    if row is None:
        raise HTTPException(404, "Settings not initialised")
    return row

@router.put("/settings", response_model=SettingsOut)
def update_settings(payload: SettingsUpdate, db: Session = Depends(get_session)):
    row = db.get(models.Settings, 1)
    if row is None:
        raise HTTPException(404, "Settings not initialised")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row
```

In `backend/api/main.py`, add after CORS setup:
```python
from backend.api.routes import settings as settings_route
app.include_router(settings_route.router, prefix="/api", tags=["settings"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_settings_api.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

Run: `python3 scripts/git_ops.py commit "[EPIC-1] feat: settings read/update API"`

---

### Task 7: Frontend shell — LGC placeholder home

> UI is intentionally minimal here (foundation only). The real screens (dashboard, transactions, forecast, invoices) are designed via the **ui-mockup skill** starting Epic 2. This task only rebrands the template home and confirms front↔back wiring.

**Files:**
- Modify: `frontend/app/page.tsx`
- Modify: `frontend/app/layout.tsx` (title/metadata → "LGC Compta")
- Test: `frontend/__tests__/home.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/__tests__/home.test.tsx
import { render, screen } from '@testing-library/react';
import HomePage from '../app/page';

test('shows LGC heading', () => {
  render(<HomePage />);
  expect(screen.getByText(/LGC Compta/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- home.test.tsx`
Expected: FAIL (text not found — page still says "Template Project").

- [ ] **Step 3: Update the home page**

Replace the `<h1>` and intro paragraph in `frontend/app/page.tsx`:
```tsx
<h1 className="text-4xl font-bold text-gray-900 dark:text-gray-100 mb-4">
  LGC Compta
</h1>
<p className="text-lg text-gray-600 dark:text-gray-400 mb-8">
  Pilotage tréso, forecast & facturation de la SASU LGC.
</p>
```
Remove the blue "BEST_PRACTICES" reminder box (template artifact). Keep the "API Status" card.

In `frontend/app/layout.tsx`, set the exported `metadata.title` to `"LGC Compta"`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- home.test.tsx`
Expected: PASS.

- [ ] **Step 5: Manual smoke — both services boot and talk**

Run backend: `cd backend && source venv/bin/activate && uvicorn api.main:app --reload --port 8000`
Run frontend (new shell): `cd frontend && npm run dev`
Open `http://localhost:3000` → heading "LGC Compta", API Status shows `healthy`.
Check `curl http://localhost:8000/api/settings` → returns seeded settings (next_invoice_number 62).

- [ ] **Step 6: Commit**

Run: `python3 scripts/git_ops.py commit "[EPIC-1] feat: rebrand frontend shell to LGC + wire settings smoke"`

---

## Definition of Done (Epic 1)
- `pytest` green (config, logging, db session, models, health, settings) + frontend home test green.
- `uvicorn` boots, `create_all` builds all tables in `data/lgc.db`, Settings seeded (n° facture 62).
- `/health` returns `{status: healthy, database: ok}`; `/api/settings` GET/PUT works.
- Frontend shows "LGC Compta" and reads backend health.
- No secrets committed; `.env.example` present; IBAN masking helper covered by a test.

## Self-Review (done at write time)
- **Spec coverage:** S1.1 (Task 0/5/7 scaffold+boot) · S1.2 (Task 3/4 DB+models, incl. opening_balance & investments per amendment) · S1.3 (Task 2 logging+PII) · S1.4 (Task 6 settings + seed). ✅
- **Placeholders:** none — every step has real code/commands.
- **Type consistency:** `init_db()`, `get_session`, `SessionLocal`, `Base`, `mask_iban()`, `settings` used identically across tasks. Money = `Numeric(14,2)`/`Decimal` throughout.
- **Deferred (documented):** Alembic (introduced at first schema migration, Epic 2+); legacy `backend/database/` removed in a later cleanup, not deleted now.
