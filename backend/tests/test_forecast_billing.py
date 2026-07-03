"""
Tests Story ③ : grille Forecast en facturation TJM (jour) / THM (heure).

- SQLite en mémoire (pattern test_forecast.py).
- Le FX vient des taux théoriques (`fx_rates`), plus de fx_rate manuel.
- Montant natif = jours × taux (TJM) ou heures × taux (THM) ; EUR = montant × FX.
"""

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db import models
from backend.db.base import Base
from backend.services import cashflow as cashflow_service
from backend.services import forecast as forecast_service

from datetime import date

_TODAY = date(2026, 7, 3)


@pytest.fixture
def db():
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


def _client(db, mode="tjm", ccy="USD", hpd="8"):
    c = models.Client(
        code="SWIB", legal_name="Swib", currency=ccy,
        billing_mode=mode, default_hours_per_day=Decimal(hpd),
    )
    db.add(c)
    db.add(models.FxRate(currency=ccy, rate=Decimal("0.9")))
    db.commit()
    db.refresh(c)
    return c


# --------------------------------------------------------------------------- #
# TJM — taux journalier                                                        #
# --------------------------------------------------------------------------- #


def test_tjm_amount_is_days_times_rate_with_half_day(db):
    c = _client(db, mode="tjm")
    forecast_service.upsert_inputs(db, [{
        "month": "2026-08", "client_id": c.id, "rate_unit": "day",
        "days": Decimal("16.5"), "rate": Decimal("900"), "note": "",
    }])
    inv = db.query(models.Invoice).one()
    assert inv.rate_unit == "day"
    assert inv.days == Decimal("16.50")
    assert inv.hours == Decimal("132.00")           # 16.5 × 8
    assert inv.amount == Decimal("14850.00")        # 16.5 × 900
    assert inv.amount_eur_forecast == Decimal("13365.00")  # × 0.9


# --------------------------------------------------------------------------- #
# THM — taux horaire (jours ⇄ heures liés)                                     #
# --------------------------------------------------------------------------- #


def test_thm_amount_is_hours_times_rate(db):
    c = _client(db, mode="thm")
    forecast_service.upsert_inputs(db, [{
        "month": "2026-08", "client_id": c.id, "rate_unit": "hour",
        "hours": Decimal("6"), "rate": Decimal("120"), "note": "",
    }])
    inv = db.query(models.Invoice).one()
    assert inv.rate_unit == "hour"
    assert inv.hours == Decimal("6.00")
    assert inv.days == Decimal("0.75")              # 6 ÷ 8
    assert inv.amount == Decimal("720.00")          # 6 × 120
    assert inv.amount_eur_forecast == Decimal("648.00")   # × 0.9


def test_thm_derives_days_from_hours(db):
    c = _client(db, mode="thm")
    forecast_service.upsert_inputs(db, [{
        "month": "2026-09", "client_id": c.id, "rate_unit": "hour",
        "hours": Decimal("120"), "rate": Decimal("100"), "note": "",
    }])
    inv = db.query(models.Invoice).one()
    assert inv.days == Decimal("15.00")             # 120 ÷ 8
    assert inv.amount == Decimal("12000.00")


# --------------------------------------------------------------------------- #
# Round-trip + FX théorique                                                    #
# --------------------------------------------------------------------------- #


def test_get_inputs_returns_rate_unit_and_hours(db):
    c = _client(db, mode="thm")
    forecast_service.upsert_inputs(db, [{
        "month": "2026-08", "client_id": c.id, "rate_unit": "hour",
        "hours": Decimal("10"), "rate": Decimal("120"), "note": "n",
    }])
    rows = forecast_service.get_inputs(db, 2026)
    assert len(rows) == 1
    assert rows[0].rate_unit == "hour"
    assert rows[0].hours == Decimal("10.00")
    assert rows[0].note == "n"


def test_forecast_incoming_uses_theoretical_fx(db):
    """cashflow : encaissement prévisionnel = amount_eur_forecast (FX Réglages)."""
    c = _client(db, mode="thm")
    forecast_service.upsert_inputs(db, [{
        "month": "2026-08", "client_id": c.id, "rate_unit": "hour",
        "hours": Decimal("100"), "rate": Decimal("120"), "note": "",
    }])
    by = {m["month"]: m for m in cashflow_service.monthly_cashflow(db, 2026, today=_TODAY)["months"]}
    aug = by["2026-08"]
    assert aug["is_forecast"] is True
    # 100 × 120 = 12000 $ × 0.9 = 10800 €
    assert aug["incoming_by_ccy"] == {"USD": Decimal("10800.00")}
    assert aug["incoming_eur"] == Decimal("10800.00")
