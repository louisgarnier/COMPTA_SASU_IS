"""
Tests des routes État financier : CRUD des chiffres comptable + comparaison
et pont de réconciliation (qui doit se fermer au centime).
"""

from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.routes import financial, settings
from backend.db import models  # noqa: F401
from backend.db.base import Base, get_db


@pytest.fixture()
def client() -> TestClient:
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, future=True)

    def _override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(settings.router)
    app.include_router(financial.router)
    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)


def test_accountant_statement_upsert_and_get(client: TestClient):
    """PUT crée puis GET relit ; un second PUT remplace (upsert)."""
    assert client.get("/api/accountant-statement/2025").status_code == 404

    body = {"production_vendue": "218010.52", "charges_exploitation": "36453.00",
            "resultat_net": "173780.00", "dotations_amortissements": "1408.00",
            "provision_change": "3004.00", "note": "CdR validé"}
    r = client.put("/api/accountant-statement/2025", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["year"] == 2025
    assert Decimal(r.json()["production_vendue"]) == Decimal("218010.52")

    got = client.get("/api/accountant-statement/2025").json()
    assert Decimal(got["resultat_net"]) == Decimal("173780.00")

    # Upsert : réécriture en place.
    client.put("/api/accountant-statement/2025", json={**body, "resultat_net": "173000.00"})
    assert Decimal(client.get("/api/accountant-statement/2025").json()["resultat_net"]) == Decimal("173000.00")


def test_financial_statement_bridge_closes(client: TestClient):
    """
    Sans comptable : accountant=null, bridge vide. Avec comptable saisi : le pont
    ferme (premier ancrage + étapes = dernier ancrage = résultat net comptable).
    """
    empty = client.get("/api/financial-statement?year=2025").json()
    assert empty["accountant"] is None
    assert empty["bridge"] == []
    # Côté app présent même sans comptable.
    assert "resultat" in empty["app"]

    client.put("/api/accountant-statement/2025", json={
        "production_vendue": "218010.52", "charges_exploitation": "36453.00",
        "dotations_amortissements": "1408.00", "provision_change": "3004.00",
        "resultat_net": "173780.00",
    })
    fs = client.get("/api/financial-statement?year=2025").json()
    assert fs["accountant"] is not None
    steps = fs["bridge"]
    assert len(steps) == 5
    # Pont fermé : ancrage_départ + 3 étapes == ancrage_arrivée.
    total = sum(Decimal(s["amount"]) for s in steps[:-1])
    assert total == Decimal(steps[-1]["amount"])
    assert steps[-1]["amount"] == "173780.00"
    assert steps[0]["anchor"] is True and steps[-1]["anchor"] is True
