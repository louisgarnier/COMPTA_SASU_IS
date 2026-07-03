"""
Tests des routes Settings / Clients / Investments.

Chaque test s'exécute contre une base SQLite en mémoire isolée, via une app
FastAPI minimale n'incluant que les trois routeurs concernés et un override de
`get_db` (pattern in-memory de test_db.py).
"""

from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.routes import clients, investments, settings
from backend.db import models  # noqa: F401 — enregistre les modèles sur Base.metadata
from backend.db.base import Base, get_db


@pytest.fixture()
def client() -> TestClient:
    """App FastAPI minimale + base en mémoire dédiée au test."""
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # partage la même connexion → la base persiste
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
    app.include_router(clients.router)
    app.include_router(investments.router)
    app.dependency_overrides[get_db] = _override_get_db

    return TestClient(app)


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
def test_settings_get_creates_and_returns_singleton(client: TestClient):
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == 1
    # Valeurs par défaut du modèle.
    assert Decimal(str(data["is_low_rate"])) == Decimal("0.15")
    assert data["next_invoice_number"] == 62


def test_settings_put_updates(client: TestClient):
    client.get("/api/settings")  # crée le singleton
    resp = client.put(
        "/api/settings",
        json={
            "company_name": "LGC SASU",
            "siret": "12345678900010",
            "next_invoice_number": 100,
            "default_fx_usd": "0.95",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["company_name"] == "LGC SASU"
    assert data["siret"] == "12345678900010"
    assert data["next_invoice_number"] == 100
    assert Decimal(str(data["default_fx_usd"])) == Decimal("0.95")
    # Persistance vérifiée par un GET suivant.
    assert client.get("/api/settings").json()["company_name"] == "LGC SASU"


# --------------------------------------------------------------------------- #
# Clients
# --------------------------------------------------------------------------- #
def test_client_create_list_patch_and_404(client: TestClient):
    # Create
    resp = client.post(
        "/api/clients",
        json={
            "code": "SWIB",
            "legal_name": "Swib LLC",
            "currency": "USD",
            "tjh": "850.00",
        },
    )
    assert resp.status_code == 201
    created = resp.json()
    cid = created["id"]
    assert created["code"] == "SWIB"
    assert Decimal(str(created["tjh"])) == Decimal("850.00")

    # List
    listed = client.get("/api/clients")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    # Get by id
    assert client.get(f"/api/clients/{cid}").json()["code"] == "SWIB"

    # Patch (partiel)
    patched = client.patch(f"/api/clients/{cid}", json={"tjh": "900.00"})
    assert patched.status_code == 200
    assert Decimal(str(patched.json()["tjh"])) == Decimal("900.00")
    assert patched.json()["code"] == "SWIB"  # inchangé

    # 404
    assert client.get("/api/clients/9999").status_code == 404
    assert client.patch("/api/clients/9999", json={"tjh": "1"}).status_code == 404


def test_client_billing_fields_and_defaults(client: TestClient):
    # Champs de facturation (story ① Client card).
    resp = client.post(
        "/api/clients",
        json={
            "code": "NWH",
            "legal_name": "New Wave Holdings",
            "currency": "CAD",
            "tjh": "120.00",
            "contact_name": "Jane Doe",
            "email": "billing@nwh.example",
            "country": "Canada",
        },
    )
    assert resp.status_code == 201
    c = resp.json()
    assert c["contact_name"] == "Jane Doe"
    assert c["email"] == "billing@nwh.example"
    assert c["country"] == "Canada"
    # Défauts métier : 8 h/jour, échéance 60 jours.
    assert Decimal(str(c["default_hours_per_day"])) == Decimal("8")
    assert c["payment_terms_days"] == 60

    # Patch d'un champ de facturation.
    patched = client.patch(
        f"/api/clients/{c['id']}",
        json={"payment_terms_days": 30, "default_hours_per_day": "7.5"},
    )
    assert patched.status_code == 200
    assert patched.json()["payment_terms_days"] == 30
    assert Decimal(str(patched.json()["default_hours_per_day"])) == Decimal("7.5")


# --------------------------------------------------------------------------- #
# Investments
# --------------------------------------------------------------------------- #
def test_investment_create_list_and_summary_gain(client: TestClient):
    client.post(
        "/api/manual-assets",
        json={
            "label": "BTC",
            "type": "crypto",
            "currency": "EUR",
            "opening_value_eur": "1000.00",
            "current_value_eur": "1500.00",
        },
    )
    client.post(
        "/api/manual-assets",
        json={
            "label": "PEA",
            "type": "bourse",
            "currency": "EUR",
            "opening_value_eur": "2000.00",
            "current_value_eur": "1800.00",
        },
    )

    listed = client.get("/api/manual-assets")
    assert listed.status_code == 200
    assert len(listed.json()) == 2

    summary = client.get("/api/manual-assets/summary")
    assert summary.status_code == 200
    s = summary.json()
    assert Decimal(str(s["total_opening_value_eur"])) == Decimal("3000.00")
    assert Decimal(str(s["total_current_value_eur"])) == Decimal("3300.00")
    # gain = (1500-1000) + (1800-2000) = 500 - 200 = 300
    assert Decimal(str(s["gain_eur"])) == Decimal("300.00")


def test_investment_patch_delete_and_404(client: TestClient):
    created = client.post(
        "/api/manual-assets",
        json={"label": "ETH", "type": "crypto", "current_value_eur": "500"},
    ).json()
    iid = created["id"]

    patched = client.patch(f"/api/manual-assets/{iid}", json={"current_value_eur": "750"})
    assert patched.status_code == 200
    assert Decimal(str(patched.json()["current_value_eur"])) == Decimal("750")

    assert client.delete(f"/api/manual-assets/{iid}").status_code == 204
    assert client.get("/api/manual-assets").json() == []

    # 404 sur ressource absente
    assert client.patch("/api/manual-assets/9999", json={"note": "x"}).status_code == 404
    assert client.delete("/api/manual-assets/9999").status_code == 404
