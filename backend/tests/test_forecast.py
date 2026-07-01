"""
Tests du domaine Prévision : service (projection + IS) et routes.

- SQLite en mémoire (pattern test_db.py).
- Vérifie revenu projeté = jours × TJH × fx.
- Vérifie le barème IS au seuil (base 50000, seuil 42500, 0.15/0.25).
- Route testée via FastAPI TestClient + dependency_overrides[get_db].
"""

from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.routes.forecast import router as forecast_router
from backend.db import models
from backend.db.base import Base, get_db
from backend.services import forecast as forecast_service


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    try:
        yield session
    finally:
        session.close()


def _make_client(db, code="SWIB") -> models.Client:
    client = models.Client(code=code, legal_name="Client Test", currency="USD")
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


# --------------------------------------------------------------------------- #
# Service : upsert + projection                                               #
# --------------------------------------------------------------------------- #


def test_projected_revenue_equals_days_rate_fx(db_session):
    client = _make_client(db_session)
    items = [
        {"month": "2026-01", "client_id": client.id, "days": Decimal("20"),
         "rate": Decimal("500"), "fx_rate": Decimal("0.9"), "note": ""},
        {"month": "2026-02", "client_id": client.id, "days": Decimal("18"),
         "rate": Decimal("500"), "fx_rate": Decimal("0.9"), "note": ""},
    ]
    forecast_service.upsert_inputs(db_session, items)

    projection = forecast_service.project(db_session, 2026)
    by_month = {m["month"]: m for m in projection["months"]}

    # 20 × 500 × 0.9 = 9000
    assert by_month["2026-01"]["revenue_eur"] == Decimal("9000.00")
    # 18 × 500 × 0.9 = 8100
    assert by_month["2026-02"]["revenue_eur"] == Decimal("8100.00")
    # Mois sans entrée → 0
    assert by_month["2026-03"]["revenue_eur"] == Decimal("0.00")
    assert projection["totals"]["revenue_eur"] == Decimal("17100.00")


def test_upsert_is_idempotent_on_month_client(db_session):
    client = _make_client(db_session)
    forecast_service.upsert_inputs(
        db_session,
        [{"month": "2026-01", "client_id": client.id, "days": Decimal("10"),
          "rate": Decimal("400"), "fx_rate": Decimal("1"), "note": "v1"}],
    )
    forecast_service.upsert_inputs(
        db_session,
        [{"month": "2026-01", "client_id": client.id, "days": Decimal("15"),
          "rate": Decimal("400"), "fx_rate": Decimal("1"), "note": "v2"}],
    )
    rows = forecast_service.get_inputs(db_session, 2026)
    assert len(rows) == 1
    assert rows[0].days == Decimal("15")
    assert rows[0].note == "v2"


def test_cumulative_cash_uses_starting_cash(db_session):
    client = _make_client(db_session)
    forecast_service.upsert_inputs(
        db_session,
        [{"month": "2026-01", "client_id": client.id, "days": Decimal("10"),
          "rate": Decimal("100"), "fx_rate": Decimal("1"), "note": ""}],
    )
    projection = forecast_service.project(
        db_session, 2026, starting_cash_eur=Decimal("5000")
    )
    jan = projection["months"][0]
    # 5000 + (1000 - 0 charges) = 6000
    assert jan["cumulative_cash_eur"] == Decimal("6000.00")


# --------------------------------------------------------------------------- #
# Service : estimation IS                                                     #
# --------------------------------------------------------------------------- #


def test_is_splits_at_threshold(db_session):
    # Barème par défaut : 0.15 jusqu'à 42500, 0.25 au-delà.
    result = forecast_service.estimate_is(
        db_session, 2026, base_override=Decimal("50000")
    )
    assert result["base_eur"] == Decimal("50000.00")
    assert result["threshold_eur"] == Decimal("42500.00")
    # 42500 × 0.15 = 6375
    assert result["is_low_eur"] == Decimal("6375.00")
    # 7500 × 0.25 = 1875
    assert result["is_high_eur"] == Decimal("1875.00")
    assert result["is_total_eur"] == Decimal("8250.00")


def test_is_below_threshold_only_low_rate(db_session):
    result = forecast_service.estimate_is(
        db_session, 2026, base_override=Decimal("30000")
    )
    # 30000 × 0.15 = 4500 ; pas de tranche haute
    assert result["is_low_eur"] == Decimal("4500.00")
    assert result["is_high_eur"] == Decimal("0.00")
    assert result["is_total_eur"] == Decimal("4500.00")


def test_is_includes_positive_investment_gain(db_session):
    client = _make_client(db_session)
    forecast_service.upsert_inputs(
        db_session,
        [{"month": "2026-01", "client_id": client.id, "days": Decimal("100"),
          "rate": Decimal("100"), "fx_rate": Decimal("1"), "note": ""}],
    )
    # Plus-value latente +2000 (prise en compte) et une moins-value -500 (ignorée).
    db_session.add(models.Investment(
        label="BTC", type="crypto", currency="EUR",
        opening_value_eur=Decimal("1000"), current_value_eur=Decimal("3000")))
    db_session.add(models.Investment(
        label="ETH", type="crypto", currency="EUR",
        opening_value_eur=Decimal("2000"), current_value_eur=Decimal("1500")))
    db_session.commit()

    result = forecast_service.estimate_is(db_session, 2026)
    # Résultat projeté = 10000 (revenu) - 0 (charges) + 2000 (PV) = 12000
    assert result["base_eur"] == Decimal("12000.00")


# --------------------------------------------------------------------------- #
# Route : GET / PUT                                                           #
# --------------------------------------------------------------------------- #


@pytest.fixture
def client_app(db_session):
    app = FastAPI()
    app.include_router(forecast_router)
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def test_route_put_then_get(client_app, db_session):
    client = _make_client(db_session)
    body = {
        "year": 2026,
        "inputs": [
            {"month": "2026-01", "client_id": client.id, "days": "20",
             "rate": "500", "fx_rate": "0.9", "note": "SWIB janv"},
        ],
    }
    put_resp = client_app.put("/api/forecast", json=body)
    assert put_resp.status_code == 200
    data = put_resp.json()
    assert len(data["inputs"]) == 1
    assert data["projection"]["months"][0]["revenue_eur"] == "9000.00"

    get_resp = client_app.get("/api/forecast", params={"year": 2026})
    assert get_resp.status_code == 200
    gdata = get_resp.json()
    assert gdata["projection"]["totals"]["revenue_eur"] == "9000.00"
    assert "is" in gdata and "is_total_eur" in gdata["is"]


def test_route_get_with_starting_cash(client_app, db_session):
    client = _make_client(db_session)
    forecast_service.upsert_inputs(
        db_session,
        [{"month": "2026-01", "client_id": client.id, "days": Decimal("10"),
          "rate": Decimal("100"), "fx_rate": Decimal("1"), "note": ""}],
    )
    resp = client_app.get(
        "/api/forecast", params={"year": 2026, "starting_cash_eur": "5000"}
    )
    assert resp.status_code == 200
    jan = resp.json()["projection"]["months"][0]
    assert jan["cumulative_cash_eur"] == "6000.00"
