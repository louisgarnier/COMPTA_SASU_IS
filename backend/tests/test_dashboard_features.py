"""Tests des évolutions dashboard : P&L par devise, tréso à une date, justificatifs."""

from datetime import date
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.base import Base, get_db
from backend.db import models
from backend.services.pnl import monthly_pnl
from backend.services.treasury import consolidated_treasury


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)


def _seed_treasury(db):
    # Taux FX théoriques (source unique de conversion EUR).
    db.add(models.FxRate(currency="USD", rate=Decimal("0.92")))
    db.add(models.FxRate(currency="CAD", rate=Decimal("0.68")))
    db.add(models.BankAccount(
        provider="revolut", account_uid="usd", currency="USD",
        opening_balance=Decimal("0"), opening_balance_date=date(2026, 1, 1)))
    db.add(models.BankAccount(
        provider="revolut", account_uid="eur", currency="EUR",
        opening_balance=Decimal("1000"), opening_balance_date=date(2026, 1, 1)))
    # Revenus février : USD 1000 × 0.92 = 920 €, CAD 1000 × 0.68 = 680 €
    db.add(models.Transaction(
        account_uid="usd", external_id="us1", booked_date=date(2026, 2, 5),
        amount=Decimal("1000"), currency="USD", kind="revenue"))
    db.add(models.Transaction(
        account_uid="eur", external_id="ca1", booked_date=date(2026, 2, 8),
        amount=Decimal("1000"), currency="CAD", kind="revenue"))
    # Une transaction en mars (pour le test as_of)
    db.add(models.Transaction(
        account_uid="eur", external_id="mar1", booked_date=date(2026, 3, 3),
        amount=Decimal("500"), currency="EUR", kind="revenue",
        amount_eur=Decimal("500")))
    db.commit()


def test_pnl_revenue_by_currency(session_factory):
    db = session_factory()
    _seed_treasury(db)
    res = monthly_pnl(db, 2026)
    assert set(res["currencies"]) == {"USD", "CAD", "EUR"}
    feb = next(m for m in res["months"] if m["month"] == "2026-02")
    assert feb["revenue_by_currency"]["USD"] == Decimal("920.00")
    assert feb["revenue_by_currency"]["CAD"] == Decimal("680.00")
    assert res["totals"]["revenue_by_currency"]["USD"] == Decimal("920.00")


def test_treasury_as_of_excludes_later_transactions(session_factory):
    db = session_factory()
    _seed_treasury(db)
    # Sans date : inclut la transaction de mars.
    full = consolidated_treasury(db)
    eur_full = next(a for a in full["accounts"] if a["account_uid"] == "eur")
    # Au 28/02 : exclut la transaction de mars (500).
    at_feb = consolidated_treasury(db, as_of=date(2026, 2, 28))
    eur_feb = next(a for a in at_feb["accounts"] if a["account_uid"] == "eur")
    assert at_feb["as_of"] == "2026-02-28"
    assert eur_full["balance"] - eur_feb["balance"] == Decimal("500.00")


def test_balance_docs_upload_list_download_delete(session_factory, tmp_path, monkeypatch):
    from backend.api.routes import balance_docs as bd

    monkeypatch.setattr(bd, "DOCS_DIR", tmp_path)

    app = FastAPI()
    app.include_router(bd.router)
    Session = session_factory

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    pdf = b"%PDF-1.4 fake pdf bytes"
    r = client.post(
        "/api/balance-docs",
        files={"file": ("releve.pdf", pdf, "application/pdf")},
        data={"account_uid": "eur", "label": "Solde juin", "doc_date": "2026-06-30"},
    )
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["filename"] == "releve.pdf"
    assert doc["account_uid"] == "eur"

    lst = client.get("/api/balance-docs").json()
    assert len(lst) == 1

    dl = client.get(f"/api/balance-docs/{doc['id']}/download")
    assert dl.status_code == 200
    assert dl.content == pdf

    dele = client.delete(f"/api/balance-docs/{doc['id']}")
    assert dele.status_code == 204
    assert client.get("/api/balance-docs").json() == []


def test_fx_rates_view_and_update(session_factory):
    from backend.api.routes import fx as fxr

    db = session_factory()
    _seed_treasury(db)  # USD + CAD présents, taux 0.92 / 0.68
    db.close()

    app = FastAPI()
    app.include_router(fxr.router)
    Session = session_factory
    app.dependency_overrides[get_db] = lambda: (yield Session())
    client = TestClient(app)

    rows = client.get("/api/fx-rates").json()
    by = {r["currency"]: r for r in rows}
    # Devises en usage listées (EUR exclu), avec leur taux, non manquantes.
    assert set(by) == {"USD", "CAD"}
    assert by["USD"]["rate"] == "0.920000"
    assert by["USD"]["missing"] is False

    # Mise à jour d'un taux.
    upd = client.put("/api/fx-rates", json={"rates": [{"currency": "USD", "rate": "0.95"}]})
    assert upd.status_code == 200
    usd = {r["currency"]: r for r in upd.json()}["USD"]
    assert usd["rate"] == "0.950000"


def test_fx_missing_rate_flagged(session_factory):
    from backend.services.fx import rates_view

    db = session_factory()
    # Une transaction en JPY sans taux → doit apparaître 'missing'.
    db.add(models.BankAccount(provider="revolut", account_uid="jpy", currency="JPY"))
    db.commit()
    view = {r["currency"]: r for r in rates_view(db)}
    assert view["JPY"]["missing"] is True


def test_balance_docs_rejects_bad_type(session_factory, tmp_path, monkeypatch):
    from backend.api.routes import balance_docs as bd

    monkeypatch.setattr(bd, "DOCS_DIR", tmp_path)
    app = FastAPI()
    app.include_router(bd.router)
    Session = session_factory
    app.dependency_overrides[get_db] = lambda: (yield Session())
    client = TestClient(app)
    r = client.post(
        "/api/balance-docs",
        files={"file": ("x.exe", b"MZ", "application/x-msdownload")},
    )
    assert r.status_code == 415
