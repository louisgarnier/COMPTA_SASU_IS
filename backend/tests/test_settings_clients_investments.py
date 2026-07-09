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

from backend.api.routes import clients, investments, invoices, settings
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
    app.include_router(invoices.router)
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
            "capital_eur": "100",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["company_name"] == "LGC SASU"
    assert data["siret"] == "12345678900010"
    assert data["next_invoice_number"] == 100
    assert Decimal(str(data["capital_eur"])) == Decimal("100")
    # Persistance vérifiée par un GET suivant.
    assert client.get("/api/settings").json()["company_name"] == "LGC SASU"


def test_settings_validation_rejects_out_of_range(client: TestClient):
    """Bornes métier : taux IS ∈ [0,1], seuil/capital ≥ 0, n° facture ≥ 1, SIRET 14 chiffres."""
    client.get("/api/settings")
    assert client.put("/api/settings", json={"is_low_rate": "5"}).status_code == 422
    assert client.put("/api/settings", json={"is_high_rate": "-0.1"}).status_code == 422
    assert client.put("/api/settings", json={"next_invoice_number": 0}).status_code == 422
    assert client.put("/api/settings", json={"capital_eur": "-1"}).status_code == 422
    assert client.put("/api/settings", json={"siret": "123"}).status_code == 422


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


def test_client_create_rejects_empty_code(client: TestClient):
    """Un code vide est refusé proprement (422), pas de 500 ni de client fantôme."""
    resp = client.post("/api/clients", json={"code": "", "legal_name": "Sans code"})
    assert resp.status_code == 422
    # Aucun client n'a été créé.
    assert client.get("/api/clients").json() == []


def test_client_create_duplicate_code_returns_409(client: TestClient):
    """Un code déjà utilisé renvoie 409 (message clair), pas un 500 IntegrityError brut."""
    first = client.post("/api/clients", json={"code": "SWIB", "legal_name": "Alpha"})
    assert first.status_code == 201
    dup = client.post("/api/clients", json={"code": "SWIB", "legal_name": "Autre"})
    assert dup.status_code == 409
    assert "code" in dup.json()["detail"].lower()


def test_client_patch_to_duplicate_code_returns_409(client: TestClient):
    """Renommer un client vers un code déjà pris renvoie 409, pas 500."""
    client.post("/api/clients", json={"code": "SWIB", "legal_name": "Alpha"})
    b = client.post("/api/clients", json={"code": "NWH", "legal_name": "New Wave"}).json()
    clash = client.patch(f"/api/clients/{b['id']}", json={"code": "SWIB"})
    assert clash.status_code == 409


def test_client_delete_204_when_no_invoices(client: TestClient):
    """Un client sans facture liée se supprime (204) et disparaît (404 ensuite)."""
    cid = client.post(
        "/api/clients", json={"code": "SWIB", "legal_name": "Alpha"}
    ).json()["id"]
    assert client.delete(f"/api/clients/{cid}").status_code == 204
    assert client.get(f"/api/clients/{cid}").status_code == 404
    # 404 si le client n'existe pas.
    assert client.delete("/api/clients/9999").status_code == 404


def test_client_delete_409_when_linked_to_invoices(client: TestClient):
    """Un client avec facture/prévision liée renvoie 409 (jamais 500)."""
    cid = client.post(
        "/api/clients", json={"code": "SWIB", "legal_name": "Alpha"}
    ).json()["id"]
    inv = client.post(
        "/api/invoices",
        json={"client_id": cid, "hours": "10", "rate": "100", "currency": "USD"},
    )
    assert inv.status_code == 201, inv.text

    blocked = client.delete(f"/api/clients/{cid}")
    assert blocked.status_code == 409
    # Le client est toujours là.
    assert client.get(f"/api/clients/{cid}").status_code == 200

    # Une fois la facture supprimée, la suppression du client passe.
    assert client.delete(f"/api/invoices/{inv.json()['id']}").status_code == 204
    assert client.delete(f"/api/clients/{cid}").status_code == 204


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


# --------------------------------------------------------------------------- #
# Lot C — seuil d'alerte trésorerie + marqueur « envoyée »
# --------------------------------------------------------------------------- #
def test_settings_low_treasury_alert_roundtrip(client: TestClient):
    """Seuil d'alerte tréso : défaut 0 (désactivé), modifiable, négatif refusé."""
    data = client.get("/api/settings").json()
    assert Decimal(data["low_treasury_alert_eur"]) == Decimal("0")

    resp = client.put("/api/settings", json={"low_treasury_alert_eur": "25000"})
    assert resp.status_code == 200
    assert Decimal(resp.json()["low_treasury_alert_eur"]) == Decimal("25000")

    assert client.put("/api/settings", json={"low_treasury_alert_eur": "-1"}).status_code == 422


def test_invoice_sent_date_marker(client: TestClient):
    """
    Marqueur « envoyée » : posable/effaçable sur une facture émise (due),
    refusé (422) sur une prévision — ce n'est PAS une transition de statut.
    """
    c = client.post("/api/clients", json={"code": "SWIB", "legal_name": "Swib"}).json()
    inv = client.post("/api/invoices", json={
        "client_id": c["id"], "hours": "8", "rate": "100", "currency": "USD",
        "issue_date": "2026-06-01",
    }).json()
    assert inv["status"] == "due"
    assert inv["sent_date"] is None

    resp = client.patch(f"/api/invoices/{inv['id']}", json={"sent_date": "2026-06-02"})
    assert resp.status_code == 200
    assert resp.json()["sent_date"] == "2026-06-02"

    # Effacement (null explicite) permis.
    resp = client.patch(f"/api/invoices/{inv['id']}", json={"sent_date": None})
    assert resp.status_code == 200
    assert resp.json()["sent_date"] is None

    # Prévision → 422 (créée directement en base : la route POST émet toujours en 'due').
    gen = client.app.dependency_overrides[get_db]()
    db = next(gen)
    fc = models.Invoice(number="F-1-2026-08", client_id=c["id"], status="forecast", month="2026-08")
    db.add(fc)
    db.commit()
    fc_id = fc.id
    db.close()
    resp = client.patch(f"/api/invoices/{fc_id}", json={"sent_date": "2026-06-02"})
    assert resp.status_code == 422
