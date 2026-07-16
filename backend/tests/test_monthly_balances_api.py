# backend/tests/test_monthly_balances_api.py
from decimal import Decimal
from datetime import date
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from backend.db.base import Base, get_db
from backend.db import models
from backend.api.main import app


@pytest.fixture()
def client():
    engine = create_engine("sqlite:///:memory:", future=True,
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, future=True)
    db = TestingSession()
    db.add(models.Settings(id=1))
    db.add(models.BankAccount(provider="revolut", account_uid="acc", currency="EUR",
                              iban_masked="FR76****527", name="LGC", balance=Decimal("0")))
    db.add(models.OpeningBalance(account_uid="acc", year=2025, balance=Decimal("1000"), note=""))
    db.commit()

    def _override():
        s = TestingSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_put_then_reconciliation(client):
    r = client.put("/api/monthly-balances?year=2025&month=1",
                   json={"items": [{"account_uid": "acc", "balance": "1000.00"}]})
    assert r.status_code == 200
    view = client.get("/api/monthly-balances/reconciliation?year=2025").json()
    jan = view["months"][0]
    assert jan["status"] == "ok"           # officiel 1000 == reconstruit 1000
    assert view["coverage"] == "1/12"


def test_extract_does_not_write(client):
    csv_text = ("Statut;Date de la valeur (local);Solde;Devise;Nom du compte;IBAN du compte\n"
                "Exécuté;15-01-2025;1000,00;EUR;Compte principal;FR7616958000011078824351453\n")
    r = client.post("/api/monthly-balances/extract",
                    data={"provider": "qonto", "year": "2025", "month": "1"},
                    files={"file": ("q.csv", csv_text, "text/csv")})
    assert r.status_code == 200
    assert r.json()["proposal"]  # renvoie une proposition
    # rien n'a été écrit : la reconciliation reste sans officiel
    view = client.get("/api/monthly-balances/reconciliation?year=2025").json()
    assert view["coverage"] == "0/12"
