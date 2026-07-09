"""
Tests Soldes d'ouverture d'exercice.

Vérifie : upsert pure-donnée, colonne Contrôle (ouverture implicite vs saisie,
écart signalé), ancre annuelle qui pilote la reconstruction de trésorerie, et
sélecteur d'exercices.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from backend.db.base import Base
from backend.db import models
from backend.services import openings as ob
from backend.services.treasury import consolidated_treasury


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, future=True)()
    _seed(db)
    yield db
    db.close()


def _seed(db):
    db.add(models.Settings(id=1))
    db.add(models.FxRate(currency="USD", rate=Decimal("0.90")))
    # Compte EUR : solde actuel 1200, mouvement +200 en 2026 → ouverture implicite 1000.
    db.add(models.BankAccount(
        provider="qonto", account_uid="eur-1", currency="EUR", name="Qonto EUR",
        balance=Decimal("1200.00"), last_synced_at=None,
    ))
    db.add(models.Transaction(
        account_uid="eur-1", external_id="e1", booked_date=date(2026, 3, 10),
        amount=Decimal("200.00"), currency="EUR", kind="revenue",
    ))
    db.commit()


TODAY = date(2026, 7, 7)


def test_set_and_get_openings_is_pure_data(session):
    ob.set_openings(session, 2026, [{"account_uid": "eur-1", "balance": "1000.00"}], today=TODAY)
    row = (
        session.query(models.OpeningBalance)
        .filter_by(account_uid="eur-1", year=2026)
        .one()
    )
    assert row.balance == Decimal("1000.00")

    view = ob.get_openings(session, 2026, today=TODAY)
    acc = view["accounts"][0]
    assert acc["balance"] == Decimal("1000.00")


def test_control_flags_ok_when_reconciles(session):
    # Ouverture saisie = ouverture implicite (1200 actuel − 200 mouvement) → concorde.
    view = ob.set_openings(
        session, 2026, [{"account_uid": "eur-1", "balance": "1000.00"}], today=TODAY
    )
    ctrl = view["accounts"][0]["control"]
    assert ctrl["implied"] == Decimal("1000.00")
    assert ctrl["diff"] == Decimal("0.00")
    assert ctrl["status"] == "ok"


def test_control_flags_gap_when_mismatch(session):
    # Saisie 977.83 alors qu'implicite = 1000 → écart −22.17 signalé.
    view = ob.set_openings(
        session, 2026, [{"account_uid": "eur-1", "balance": "977.83"}], today=TODAY
    )
    ctrl = view["accounts"][0]["control"]
    assert ctrl["status"] == "warn"
    assert ctrl["diff"] == Decimal("-22.17")


def test_anchor_drives_treasury_reconstruction(session):
    # Sans saisie : reconstruction retombe sur opening_balance legacy (0) + 200 = 200.
    before = consolidated_treasury(session, as_of=date(2026, 6, 30))
    assert before["accounts"][0]["balance"] == Decimal("200.00")

    # Après saisie ouverture 1000 pour 2026 : 1000 + 200 = 1200.
    ob.set_openings(session, 2026, [{"account_uid": "eur-1", "balance": "1000.00"}], today=TODAY)
    after = consolidated_treasury(session, as_of=date(2026, 6, 30))
    assert after["accounts"][0]["balance"] == Decimal("1200.00")


def test_list_years_includes_saved_and_current(session):
    ob.set_openings(session, 2025, [{"account_uid": "eur-1", "balance": "500"}], today=TODAY)
    years = ob.list_years(session, today=TODAY)
    assert 2025 in years and 2026 in years
