"""Tests de la couche DB : création des tables + intégrité + Decimal."""

from decimal import Decimal

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from backend.db.base import Base
from backend.db import models


def _memory_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, future=True)()


def test_all_tables_created():
    engine, _ = _memory_session()
    tables = set(inspect(engine).get_table_names())
    expected = {
        "settings", "clients", "bank_accounts", "categories", "category_rules",
        "transactions", "invoices", "investments", "forecast_inputs",
    }
    assert expected.issubset(tables)


def test_money_roundtrips_as_decimal():
    _, session = _memory_session()
    acc = models.BankAccount(
        provider="revolut", account_uid="acc-1", currency="EUR",
        balance=Decimal("1234.56"),
    )
    session.add(acc)
    session.commit()
    fetched = session.query(models.BankAccount).first()
    assert isinstance(fetched.balance, Decimal)
    assert fetched.balance == Decimal("1234.56")


def test_unique_account_external_constraint():
    from sqlalchemy.exc import IntegrityError

    _, session = _memory_session()
    session.add(models.BankAccount(provider="qonto", account_uid="a", currency="EUR"))
    session.commit()
    session.add(models.Transaction(
        account_uid="a", external_id="x", amount=Decimal("10"), currency="EUR"))
    session.commit()
    session.add(models.Transaction(
        account_uid="a", external_id="x", amount=Decimal("20"), currency="EUR"))
    try:
        session.commit()
        assert False, "doublon (account_uid, external_id) aurait dû être rejeté"
    except IntegrityError:
        session.rollback()
