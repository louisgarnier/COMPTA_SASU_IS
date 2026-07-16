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
