"""
Tests du domaine Factures (service + routes).

- SQLite en mémoire (même patron que test_db.py).
- Numérotation : Settings(next_invoice_number=62) → 1re facture '62' + compteur=63,
  2e facture '63'.
- Montant = hours * rate (Decimal).
- render_html contient société, client, mention art. 293 B et le montant.
- reconcile_payments relie une transaction qui matche et passe la facture 'paid'.
- generate_pdf N'EST PAS appelé (WeasyPrint non requis en test).
- Routes via FastAPI TestClient + dependency_overrides[get_db].
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.routes.invoices import router as invoices_router
from backend.db import models
from backend.db.base import Base, get_db
from backend.services import invoices as invoices_service


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite:///:memory:", future=True,
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, future=True)()
    yield db
    db.close()


def _seed(db):
    """Amorce Settings(next_invoice_number=62) + un client."""
    db.add(models.Settings(id=1, company_name="LGC SASU", siret="12345678900011",
                           tva_intracom="FR00123456789", address="1 rue du Code, Paris",
                           next_invoice_number=62))
    client = models.Client(code="SWIB", legal_name="Swib Corp",
                           address="10 Market St", currency="USD",
                           counterparty_match="SWIB")
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


# --------------------------------------------------------------------------- #
# Service : numérotation, montant, rendu HTML, rapprochement
# --------------------------------------------------------------------------- #

def test_next_number_does_not_increment(session):
    _seed(session)
    assert invoices_service.next_number(session) == "62"
    # Toujours 62 : la lecture ne consomme pas le numéro.
    assert invoices_service.next_number(session) == "62"
    assert session.get(models.Settings, 1).next_invoice_number == 62


def test_create_invoice_numbering_and_amount(session):
    client = _seed(session)
    data = {"client_id": client.id, "period_label": "Juin 2026",
            "hours": Decimal("120"), "rate": Decimal("85"), "currency": "USD"}

    inv1 = invoices_service.create_invoice(session, data, issue_date=date(2026, 7, 1))
    assert inv1.number == "62"
    assert inv1.amount == Decimal("10200")  # 120 * 85
    assert inv1.status == "due"
    assert inv1.issue_date == date(2026, 7, 1)
    assert session.get(models.Settings, 1).next_invoice_number == 63

    inv2 = invoices_service.create_invoice(session, data, issue_date=date(2026, 7, 1))
    assert inv2.number == "63"
    assert session.get(models.Settings, 1).next_invoice_number == 64


def test_create_invoice_sets_due_date_from_client_terms(session):
    # Le cashflow prévisionnel a besoin d'une échéance : create_invoice la pose
    # (émission + délai de paiement du client).
    client = _seed(session)
    client.payment_terms_days = 45
    session.commit()
    data = {"client_id": client.id, "hours": Decimal("10"), "rate": Decimal("100"),
            "currency": "USD"}
    inv = invoices_service.create_invoice(session, data, issue_date=date(2026, 1, 31))
    # 31 janv + 45j = 17 mars 2026.
    assert inv.due_date == date(2026, 3, 17)


def test_render_html_contains_key_fields(session):
    client = _seed(session)
    inv = invoices_service.create_invoice(
        session,
        {"client_id": client.id, "hours": Decimal("10"), "rate": Decimal("100"),
         "currency": "USD"},
        issue_date=date(2026, 7, 1),
    )
    html = invoices_service.render_html(session, inv)
    assert "LGC SASU" in html          # société
    assert "Swib Corp" in html         # client
    assert "art. 293 B" in html        # mention TVA
    assert "1 000" in html             # montant 10 * 100 (format espace)


def test_reconcile_links_matching_transaction(session):
    client = _seed(session)
    inv = invoices_service.create_invoice(
        session,
        {"client_id": client.id, "hours": Decimal("100"), "rate": Decimal("50"),
         "currency": "USD"},
        issue_date=date(2026, 7, 1),
    )  # amount = 5000

    session.add(models.BankAccount(provider="revolut", account_uid="acc-1", currency="EUR"))
    session.commit()
    # Transaction de revenu qui matche montant + contrepartie.
    tx = models.Transaction(account_uid="acc-1", external_id="t1",
                            amount=Decimal("5000"), currency="EUR", amount_eur=Decimal("5000"),
                            counterparty="SWIB CORP PAYMENT", kind="revenue")
    # Transaction bruit (montant différent, ne doit pas matcher).
    noise = models.Transaction(account_uid="acc-1", external_id="t2",
                               amount=Decimal("999"), currency="EUR", amount_eur=Decimal("999"),
                               counterparty="SWIB", kind="revenue")
    session.add_all([tx, noise])
    session.commit()

    count = invoices_service.reconcile_payments(session)
    assert count == 1

    session.refresh(inv)
    session.refresh(tx)
    assert inv.status == "paid"
    assert inv.paid_transaction_id == tx.id
    assert tx.invoice_id == inv.id


def test_reconcile_no_match_when_counterparty_differs(session):
    client = _seed(session)
    inv = invoices_service.create_invoice(
        session,
        {"client_id": client.id, "hours": Decimal("100"), "rate": Decimal("50"),
         "currency": "USD"},
        issue_date=date(2026, 7, 1),
    )
    session.add(models.BankAccount(provider="revolut", account_uid="acc-1", currency="EUR"))
    session.commit()
    tx = models.Transaction(account_uid="acc-1", external_id="t1",
                            amount=Decimal("5000"), currency="EUR", amount_eur=Decimal("5000"),
                            counterparty="AUTRE CLIENT", kind="revenue")
    session.add(tx)
    session.commit()

    assert invoices_service.reconcile_payments(session) == 0
    session.refresh(inv)
    assert inv.status == "due"


# --------------------------------------------------------------------------- #
# Routes : TestClient + dependency_overrides[get_db]
# --------------------------------------------------------------------------- #

@pytest.fixture()
def client(session):
    app = FastAPI()
    app.include_router(invoices_router)
    app.dependency_overrides[get_db] = lambda: session
    _seed(session)
    return TestClient(app)


def test_route_create_and_get_invoice(client, session):
    client_id = session.query(models.Client).first().id
    resp = client.post("/api/invoices", json={
        "client_id": client_id, "period_label": "Juin 2026",
        "hours": "120", "rate": "85", "currency": "USD",
        "issue_date": "2026-07-01",
    })
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["number"] == "62"
    assert Decimal(body["amount"]) == Decimal("10200")
    assert body["client_name"] == "Swib Corp"
    assert body["status"] == "due"

    inv_id = body["id"]
    got = client.get(f"/api/invoices/{inv_id}")
    assert got.status_code == 200
    assert got.json()["number"] == "62"


def test_route_list_and_patch_status(client, session):
    client_id = session.query(models.Client).first().id
    created = client.post("/api/invoices", json={
        "client_id": client_id, "hours": "10", "rate": "100",
        "currency": "USD", "issue_date": "2026-07-01",
    }).json()

    listing = client.get("/api/invoices")
    assert listing.status_code == 200
    assert len(listing.json()) == 1
    assert listing.json()[0]["client_name"] == "Swib Corp"

    # Un statut valide autre que « payé » passe (ici retour en prévisionnel).
    patched = client.patch(f"/api/invoices/{created['id']}", json={"status": "forecast"})
    assert patched.status_code == 200
    assert patched.json()["status"] == "forecast"


def test_patch_status_paid_is_rejected(client, session):
    """« payé » manuel interdit : l'encaissement passe par le rapprochement."""
    client_id = session.query(models.Client).first().id
    created = client.post("/api/invoices", json={
        "client_id": client_id, "hours": "10", "rate": "100",
        "currency": "USD", "issue_date": "2026-07-01",
    }).json()

    resp = client.patch(f"/api/invoices/{created['id']}", json={"status": "paid"})
    assert resp.status_code == 409, resp.text
    # La facture n'a pas changé de statut.
    assert client.get(f"/api/invoices/{created['id']}").json()["status"] == "due"


def test_patch_status_invalid_enum_422(client, session):
    client_id = session.query(models.Client).first().id
    created = client.post("/api/invoices", json={
        "client_id": client_id, "hours": "10", "rate": "100",
        "currency": "USD", "issue_date": "2026-07-01",
    }).json()

    resp = client.patch(f"/api/invoices/{created['id']}", json={"status": "sent"})
    assert resp.status_code == 422, resp.text


def test_delete_last_invoice_gives_number_back(client, session):
    """Supprimer la facture au dernier n° émis rend le numéro (compteur -1)."""
    client_id = session.query(models.Client).first().id
    created = client.post("/api/invoices", json={
        "client_id": client_id, "hours": "10", "rate": "100",
        "currency": "USD", "issue_date": "2026-07-01",
    }).json()
    assert created["number"] == "62"

    resp = client.delete(f"/api/invoices/{created['id']}")
    assert resp.status_code == 204, resp.text

    # Le prochain numéro reprend à 62 (pas de trou).
    nxt = client.post("/api/invoices", json={
        "client_id": client_id, "hours": "5", "rate": "50",
        "currency": "USD", "issue_date": "2026-07-02",
    }).json()
    assert nxt["number"] == "62"


def test_delete_non_last_invoice_keeps_counter(client, session):
    """Supprimer une facture qui n'est pas la dernière ne recule pas le compteur."""
    client_id = session.query(models.Client).first().id
    first = client.post("/api/invoices", json={
        "client_id": client_id, "hours": "10", "rate": "100",
        "currency": "USD", "issue_date": "2026-07-01",
    }).json()  # n°62
    client.post("/api/invoices", json={
        "client_id": client_id, "hours": "10", "rate": "100",
        "currency": "USD", "issue_date": "2026-07-02",
    })  # n°63 (dernier)

    # On supprime la 62 (pas la dernière) → compteur inchangé (prochain = 64).
    assert client.delete(f"/api/invoices/{first['id']}").status_code == 204
    nxt = client.post("/api/invoices", json={
        "client_id": client_id, "hours": "5", "rate": "50",
        "currency": "USD", "issue_date": "2026-07-03",
    }).json()
    assert nxt["number"] == "64"


def test_route_delete_invoice(client, session):
    client_id = session.query(models.Client).first().id
    created = client.post("/api/invoices", json={
        "client_id": client_id, "hours": "10", "rate": "100",
        "currency": "USD", "issue_date": "2026-07-01",
    }).json()

    resp = client.delete(f"/api/invoices/{created['id']}")
    assert resp.status_code == 204, resp.text
    assert client.get(f"/api/invoices/{created['id']}").status_code == 404
    assert client.get("/api/invoices").json() == []


def test_route_delete_missing_invoice_404(client):
    assert client.delete("/api/invoices/9999").status_code == 404


def test_route_create_unknown_client_404(client):
    resp = client.post("/api/invoices", json={
        "client_id": 9999, "hours": "1", "rate": "1", "currency": "USD",
    })
    assert resp.status_code == 404
