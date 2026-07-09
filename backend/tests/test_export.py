"""Tests export CSV des transactions (clôture / expert-comptable)."""

from datetime import date
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.routes.transactions import router as tx_router
from backend.db import models
from backend.db.base import Base, get_db


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", future=True,
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, future=True)()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def client(db):
    app = FastAPI()
    app.include_router(tx_router)
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_transactions_csv_export(client, db):
    """
    Export CSV d'un exercice : date, libellé, contrepartie, catégorie, type,
    devise, montant natif, montant EUR (réel sinon théorique), compte.
    Filtre STRICT sur l'exercice ; champs avec ';' correctement échappés.
    """
    db.add(models.BankAccount(provider="qonto", account_uid="ACC", currency="EUR", name="Qonto"))
    cat = models.Category(name="Repas", type="charge")
    db.add(cat)
    db.add(models.FxRate(currency="USD", rate=Decimal("0.90")))
    db.commit()
    db.add(models.Transaction(
        account_uid="ACC", external_id="t1", booked_date=date(2026, 3, 5),
        amount=Decimal("-42.50"), currency="EUR", kind="charge",
        category_id=cat.id, description="Resto; client", counterparty="Le Rostand",
    ))
    db.add(models.Transaction(  # devise avec EUR réel alloué
        account_uid="ACC", external_id="t2", booked_date=date(2026, 4, 1),
        amount=Decimal("1000"), currency="USD", kind="revenue",
        amount_eur=Decimal("870.00"),
    ))
    db.add(models.Transaction(  # hors exercice → exclue
        account_uid="ACC", external_id="t3", booked_date=date(2025, 12, 30),
        amount=Decimal("100"), currency="EUR", kind="revenue",
    ))
    db.commit()

    resp = client.get("/api/transactions/export?year=2026")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "transactions_2026" in resp.headers.get("content-disposition", "")
    lines = resp.text.splitlines()
    assert lines[0] == "date;description;contrepartie;categorie;type;devise;montant;montant_eur;compte"
    body = resp.text
    assert "2026-03-05" in body and "Le Rostand" in body and "-42.50" in body
    assert '"Resto; client"' in body          # point-virgule échappé
    assert "870.00" in body                    # EUR réel prioritaire
    assert "2025-12-30" not in body            # hors exercice
