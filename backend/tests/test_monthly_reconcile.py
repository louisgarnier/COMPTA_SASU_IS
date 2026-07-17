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


def _two_account_db():
    engine = create_engine("sqlite:///:memory:", future=True,
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, future=True)()
    db.add(models.Settings(id=1))
    # a = compte actif (ancre 1000) ; b = poche vide (aucune ancre, aucun mouvement → reconstruit 0)
    db.add(models.BankAccount(provider="revolut", account_uid="a", currency="EUR",
                              iban_masked="FR76****527", name="LGC", balance=Decimal("0")))
    db.add(models.BankAccount(provider="revolut", account_uid="b", currency="USD",
                              iban_masked="FR76****484", name="LGC", balance=Decimal("0")))
    db.add(models.OpeningBalance(account_uid="a", year=2025, balance=Decimal("1000"), note=""))
    db.commit()
    return db


def test_official_zero_is_ok_not_missing():
    # un solde officiel saisi à 0,00 est une vraie valeur → ok (pas manquant/vide)
    db = _two_account_db()
    db.add(models.MonthlyBalance(account_uid="b", year=2025, month=1,
                                 balance=Decimal("0.00"), currency="USD"))
    db.commit()
    jan = mr.monthly_reconciliation(db, 2025)["months"][0]
    b = next(x for x in jan["per_account"] if x["account_uid"] == "b")
    assert b["official"] == Decimal("0.00")
    assert b["status"] == "ok"


def test_empty_pocket_without_official_is_empty_not_missing():
    # compte b : reconstruit 0 et aucun relevé → « sans objet », pas « manquant »
    db = _two_account_db()
    jan = mr.monthly_reconciliation(db, 2025)["months"][0]
    b = next(x for x in jan["per_account"] if x["account_uid"] == "b")
    assert b["reconstructed"] == Decimal("0.00")
    assert b["official"] is None
    assert b["status"] == "empty"


def test_month_partial_when_active_account_unmapped():
    # a est actif (reconstruit 1000) sans relevé → manquant ; b vide → sans objet.
    # aucun officiel encore → mois « missing »… puis on mappe b (0,00) : a reste manquant → partiel.
    db = _two_account_db()
    db.add(models.MonthlyBalance(account_uid="b", year=2025, month=1,
                                 balance=Decimal("0.00"), currency="USD"))
    db.commit()
    jan = mr.monthly_reconciliation(db, 2025)["months"][0]
    a = next(x for x in jan["per_account"] if x["account_uid"] == "a")
    assert a["status"] == "missing"       # activité 1000, pas de relevé
    assert jan["status"] == "partial"     # b ok mais a manquant → incomplet


def test_settlement_date_counts_in_value_month_not_booked_month():
    # tx comptabilisée le 31/01 mais réglée le 02/02 → doit compter en FÉVRIER
    # (date de règlement = max(booked, value)), pas en janvier.
    engine = create_engine("sqlite:///:memory:", future=True,
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, future=True)()
    db.add(models.Settings(id=1))
    db.add(models.BankAccount(provider="revolut", account_uid="acc", currency="EUR",
                              iban_masked="FR76****527", name="LGC", balance=Decimal("0")))
    db.add(models.OpeningBalance(account_uid="acc", year=2025, balance=Decimal("1000"), note=""))
    db.add(models.Transaction(account_uid="acc", external_id="straddle", booked_date=date(2025, 1, 31),
                              value_date=date(2025, 2, 2), amount=Decimal("-50"), currency="EUR", kind="charge"))
    db.commit()
    # janvier : le -50 n'est pas encore réglé → reconstruit = 1000
    assert mr.reconstruct_balance(db, "acc", 2025, 1) == Decimal("1000.00")
    # février : réglé → reconstruit = 950
    assert mr.reconstruct_balance(db, "acc", 2025, 2) == Decimal("950.00")


def test_month_ok_only_when_all_active_accounts_reconciled():
    # a mappé et rapproché (1000) ; b poche vide sans objet → mois ok (le vide ne pénalise pas)
    db = _two_account_db()
    db.add(models.MonthlyBalance(account_uid="a", year=2025, month=1,
                                 balance=Decimal("1000.00"), currency="EUR"))
    db.commit()
    jan = mr.monthly_reconciliation(db, 2025)["months"][0]
    assert jan["status"] == "ok"
