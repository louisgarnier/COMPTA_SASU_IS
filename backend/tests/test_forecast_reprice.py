"""
Tests de la repropagation du taux/mode d'un client vers ses prévisions futures
(`forecast.reprice_client_forecasts`).

Base SQLite en mémoire dédiée. On seed un client, ses factures `status='forecast'`
et un taux FX, puis on vérifie : préservation de la quantité de travail, bascule de
mode (jours⇄heures via h/j), filtre mois ≥ courant, et écriture effective en `apply`.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db import models
from backend.db.base import Base
from backend.services import forecast

TODAY = date(2026, 7, 1)  # mois courant = 2026-07


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, future=True)()
    session.add(models.FxRate(currency="USD", rate=Decimal("0.92")))
    yield session
    session.close()


def _client(db, **kw):
    defaults = dict(
        code="SWIB", legal_name="Alpha", currency="USD", tjh=Decimal("120"),
        billing_mode="thm", default_hours_per_day=Decimal("8"), payment_terms_days=60,
    )
    defaults.update(kw)
    c = models.Client(**defaults)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _forecast(db, client, month, *, days, hours, rate, rate_unit, currency="USD"):
    amount = (Decimal(hours) if rate_unit == "hour" else Decimal(days)) * Decimal(rate)
    inv = models.Invoice(
        number=f"F-{client.id}-{month}", client_id=client.id, month=month,
        period_label=month, status="forecast", rate=Decimal(rate), rate_unit=rate_unit,
        days=Decimal(days), hours=Decimal(hours), hours_per_day=Decimal("8"),
        currency=currency, amount=amount,
        amount_eur_forecast=(amount * Decimal("0.92")).quantize(Decimal("0.01")),
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


def test_preview_thm_keeps_hours_applies_new_rate(db):
    """THM : les heures restent la source ; nouveau montant = heures × nouveau taux. Aperçu n'écrit rien."""
    c = _client(db, tjh=Decimal("130"), billing_mode="thm")
    inv = _forecast(db, c, "2026-08", days=19, hours=152, rate=120, rate_unit="hour")

    res = forecast.reprice_client_forecasts(db, c.id, apply=False, today=TODAY)

    assert res["count"] == 1
    row = res["rows"][0]
    assert row["quantity"] == Decimal("152")
    assert row["unit"] == "h"
    assert row["old_amount"] == Decimal("18240.00")          # 152 × 120
    assert row["new_amount"] == Decimal("19760.00")          # 152 × 130
    assert row["new_amount_eur"] == Decimal("18179.20")      # × 0.92
    # apply=False → la facture n'a pas bougé.
    db.refresh(inv)
    assert inv.rate == Decimal("120")
    assert inv.amount == Decimal("18240")


def test_apply_writes_new_amounts(db):
    c = _client(db, tjh=Decimal("130"), billing_mode="thm")
    inv = _forecast(db, c, "2026-08", days=19, hours=152, rate=120, rate_unit="hour")

    forecast.reprice_client_forecasts(db, c.id, apply=True, today=TODAY)

    db.refresh(inv)
    assert inv.rate == Decimal("130")
    assert inv.amount == Decimal("19760.00")
    assert inv.amount_eur_forecast == Decimal("18179.20")


def test_mode_switch_tjm_to_thm_preserves_effort(db):
    """Bascule TJM→THM : les heures (jours × h/j) deviennent la source, montant = heures × taux horaire."""
    c = _client(db, tjh=Decimal("100"), billing_mode="thm", default_hours_per_day=Decimal("8"))
    # Prévision créée en TJM : 20 jours source, 160 heures dérivées.
    inv = _forecast(db, c, "2026-09", days=20, hours=160, rate=800, rate_unit="day")

    res = forecast.reprice_client_forecasts(db, c.id, apply=True, today=TODAY)

    row = res["rows"][0]
    assert row["quantity"] == Decimal("160")     # heures = nouvelle source
    assert row["unit"] == "h"
    assert row["new_amount"] == Decimal("16000.00")  # 160 × 100
    db.refresh(inv)
    assert inv.rate_unit == "hour"
    assert inv.days == Decimal("20.00")          # 160 ÷ 8


def test_only_current_and_future_months(db):
    """Les prévisions avant le mois courant ne sont pas recalculées."""
    c = _client(db, tjh=Decimal("130"), billing_mode="hour")
    past = _forecast(db, c, "2026-05", days=19, hours=152, rate=120, rate_unit="hour")
    current = _forecast(db, c, "2026-07", days=19, hours=152, rate=120, rate_unit="hour")
    future = _forecast(db, c, "2026-11", days=19, hours=152, rate=120, rate_unit="hour")

    res = forecast.reprice_client_forecasts(db, c.id, apply=True, today=TODAY)

    assert res["count"] == 2  # juillet (courant) + novembre
    assert {r["month"] for r in res["rows"]} == {"2026-07", "2026-11"}
    db.refresh(past)
    assert past.amount == Decimal("18240")     # mai intact
    db.refresh(current)
    assert current.amount == Decimal("19760.00")  # juillet recalculé
