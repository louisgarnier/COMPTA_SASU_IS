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
