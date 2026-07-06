"""
Tests du service + routes Banking (Enable Banking).

Sans identifiants ni réseau, le service DOIT être en mode MOCK et fournir des
données déterministes. On vérifie :
- mode MOCK actif (pas de creds/pyjwt),
- list_aspsps contient 'Revolut Business' et 'Qonto',
- sync insère des transactions, signe les montants (un DBIT est négatif),
- un DEUXIÈME sync n'ajoute rien (dedup) et compte des skipped,
- un trade FX (même external_id, comptes différents) n'est PAS dédupliqué,
- les routes répondent (TestClient + dependency_overrides[get_db]).
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.routes.banking import router
from backend.db import models
from backend.db.base import Base, get_db
from backend.services import banking as banking_service


@pytest.fixture(autouse=True)
def _force_mock_mode(monkeypatch):
    """
    Les tests banking supposent le mode MOCK (aucun identifiant réseau).
    L'environnement local peut désormais contenir de vrais identifiants
    Enable Banking (`.env` + `secrets/eb_private.pem`) → on les neutralise
    pour garder les tests hermétiques. Les tests de signature JWT
    ré-injectent app_id + clé eux-mêmes (monkeypatch local prioritaire).
    """
    monkeypatch.setattr(banking_service.settings, "enable_banking_app_id", "")


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, future=True)()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client(session):
    app = FastAPI()
    app.include_router(router)

    def _override():
        yield session

    app.dependency_overrides[get_db] = _override
    return TestClient(app)


# ---------------------------------------------------------------------------
# Service (mode mock)
# ---------------------------------------------------------------------------

def test_mock_mode_active():
    """Sans app_id / clé / pyjwt, le service est en mode mock."""
    assert banking_service.is_live() is False
    st = banking_service.status()
    assert st["live"] is False
    assert "mock" in st["message"].lower()


def test_list_aspsps_contains_revolut_and_qonto():
    names = {a["name"] for a in banking_service.list_aspsps(country="FR")}
    assert "Revolut Business" in names
    assert "Qonto" in names


def test_create_session_creates_accounts(session):
    result = banking_service.create_session(session, code="dummy-code")
    accounts = result["accounts"]
    assert len(accounts) >= 2
    providers = {a.provider for a in accounts}
    assert "revolut" in providers
    assert "qonto" in providers
    # Idempotent : une 2e session ne duplique pas les comptes.
    banking_service.create_session(session, code="dummy-code")
    assert session.query(models.BankAccount).count() == len(accounts)


def test_sync_inserts_and_signs_amounts(session):
    banking_service.create_session(session, code="c")
    result = banking_service.sync(session)

    assert result["accounts_synced"] >= 2
    assert result["transactions_added"] > 0
    assert session.query(models.Transaction).count() == result["transactions_added"]

    # Un DBIT connu doit être négatif ; un CRDT positif.
    dbit = (
        session.query(models.Transaction)
        .filter(models.Transaction.external_id == "rev-tx-002")
        .one()
    )
    assert dbit.amount < 0
    assert dbit.amount == Decimal("-89.90")

    crdt = (
        session.query(models.Transaction)
        .filter(models.Transaction.external_id == "rev-tx-001")
        .one()
    )
    assert crdt.amount > 0

    # booked_date >= 2026-01-01
    for t in session.query(models.Transaction).all():
        assert t.booked_date is not None
        assert t.booked_date.year == 2026


def test_second_sync_is_deduped(session):
    banking_service.create_session(session, code="c")
    first = banking_service.sync(session)
    count_after_first = session.query(models.Transaction).count()

    second = banking_service.sync(session)
    count_after_second = session.query(models.Transaction).count()

    assert second["transactions_added"] == 0
    assert second["transactions_skipped"] > 0
    assert count_after_second == count_after_first == first["transactions_added"]


def test_fx_shared_external_id_not_deduped_across_accounts(session):
    """Un même external_id sur deux comptes différents = deux transactions."""
    banking_service.create_session(session, code="c")
    banking_service.sync(session)
    fx_legs = (
        session.query(models.Transaction)
        .filter(models.Transaction.external_id == "fx-shared-777")
        .all()
    )
    assert len(fx_legs) == 2
    assert {leg.account_uid for leg in fx_legs} == {"mock-revolut-eur", "mock-qonto-eur"}


def test_sync_updates_balance_and_last_synced(session):
    banking_service.create_session(session, code="c")
    banking_service.sync(session)
    for acc in session.query(models.BankAccount).all():
        assert acc.last_synced_at is not None


def test_sync_isolates_failing_account(session, monkeypatch):
    """Un compte en échec (ex. consentement expiré) n'avorte pas toute la synchro."""
    banking_service.create_session(session, code="c")
    accounts = session.query(models.BankAccount).all()
    fail_uid = accounts[0].account_uid
    real_fetch = banking_service._fetch_raw_transactions

    def flaky(account):
        if account.account_uid == fail_uid:
            raise RuntimeError("consentement expiré (401)")
        return real_fetch(account)

    monkeypatch.setattr(banking_service, "_fetch_raw_transactions", flaky)
    res = banking_service.sync(session)

    # Le compte fautif est isolé et noté ; les autres sont bien synchronisés.
    assert res["accounts_synced"] == len(accounts) - 1
    assert res["accounts_total"] == len(accounts)
    assert any(e["account_uid"] == fail_uid for e in res["errors"])
    assert res["transactions_added"] > 0  # les autres comptes ont importé


def test_disconnect_account(session, client):
    banking_service.create_session(session, code="c")
    acc = session.query(models.BankAccount).first()
    resp = client.delete(f"/api/banking/connections/{acc.id}")
    assert resp.status_code == 204
    assert session.get(models.BankAccount, acc.id) is None
    # 404 si le compte n'existe pas.
    assert client.delete("/api/banking/connections/999999").status_code == 404


# ---------------------------------------------------------------------------
# Routes (TestClient)
# ---------------------------------------------------------------------------

def test_route_status(client):
    resp = client.get("/api/banking/status")
    assert resp.status_code == 200
    assert resp.json()["live"] is False


def test_route_aspsps(client):
    resp = client.get("/api/banking/aspsps", params={"country": "FR"})
    assert resp.status_code == 200
    names = {a["name"] for a in resp.json()}
    assert {"Revolut Business", "Qonto"}.issubset(names)


def test_route_connect(client):
    resp = client.post("/api/banking/connect", json={"aspsp_name": "Revolut Business"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["authorization_url"]
    assert body["state"]


def test_route_sessions_then_connections_then_sync(client):
    r1 = client.post("/api/banking/sessions", json={"code": "abc"})
    assert r1.status_code == 200
    assert len(r1.json()["accounts"]) >= 2

    r2 = client.get("/api/banking/connections")
    assert r2.status_code == 200
    assert len(r2.json()) >= 2

    r3 = client.post("/api/banking/sync")
    assert r3.status_code == 200
    assert r3.json()["transactions_added"] > 0

    # 2e sync via route = dedup.
    r4 = client.post("/api/banking/sync")
    assert r4.json()["transactions_added"] == 0
    assert r4.json()["transactions_skipped"] > 0


# --- Chargement de la clé privée (PEM complet OU base64 brut type Railway) ---


def _rsa_pem_pair():
    """Génère une paire RSA de test → (PEM privé PKCS8, objet clé publique)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    return pem, key.public_key()


def _assert_signs(tmp_path, monkeypatch, key_text, pub):
    """Écrit key_text dans le fichier clé, signe un JWT, le vérifie avec la clé publique."""
    import jwt

    key_file = tmp_path / "eb_private.pem"
    key_file.write_text(key_text, encoding="utf-8")
    monkeypatch.setattr(
        banking_service.settings, "enable_banking_private_key_path", str(key_file)
    )
    monkeypatch.setattr(banking_service.settings, "enable_banking_app_id", "test-kid")

    token = banking_service._make_jwt()
    decoded = jwt.decode(token, pub, algorithms=["RS256"], audience="api.enablebanking.com")
    assert decoded["iss"] == "enablebanking.com"
    assert jwt.get_unverified_header(token)["kid"] == "test-kid"


def test_make_jwt_accepts_full_pem(tmp_path, monkeypatch):
    pem, pub = _rsa_pem_pair()
    _assert_signs(tmp_path, monkeypatch, pem, pub)


def test_make_jwt_accepts_raw_base64_body(tmp_path, monkeypatch):
    # Cas Railway : en-têtes retirés + tout sur une ligne (newlines supprimés).
    pem, pub = _rsa_pem_pair()
    body = "".join(
        l for l in pem.splitlines() if l and not l.startswith("-----")
    )
    assert "\n" not in body and not body.startswith("-----")
    _assert_signs(tmp_path, monkeypatch, body, pub)


# --- Régression S3.3 : sync catégorise automatiquement les nouvelles écritures ---


def test_sync_auto_categorizes(session):
    # Une règle : contrepartie contenant 'URSSAF' → catégorie de type charge.
    cat = models.Category(name="Cotisations URSSAF", type="charge")
    session.add(cat)
    session.flush()
    session.add(models.CategoryRule(
        match_field="counterparty", pattern="URSSAF",
        category_id=cat.id, priority=50, enabled=True))
    # Crée les comptes mock puis synchronise.
    banking_service.create_session(session, "mock-code")
    res = banking_service.sync(session)

    assert res["transactions_added"] > 0
    assert res["transactions_categorized"] > 0  # la régression : valait 0 avant le fix

    urssaf = (
        session.query(models.Transaction)
        .filter(models.Transaction.counterparty.ilike("%URSSAF%"))
        .first()
    )
    assert urssaf is not None
    assert urssaf.category_id == cat.id  # catégorisée pendant le sync, sans appel manuel


# --- Le sync rapproche automatiquement les paiements (boucle accrual) ---------


def test_sync_auto_reconciles_open_invoice(session):
    # Facture SWIB de 5400 EUR en attente : l'encaissement mock « SWIB LLC »
    # (5400 EUR) doit la solder pendant le sync, sans appel manuel à reconcile.
    client = models.Client(
        code="SWIB", legal_name="SWIB LLC", currency="EUR",
        counterparty_match="SWIB",
    )
    session.add(client)
    session.commit()
    session.refresh(client)
    session.add(models.Invoice(
        number="90", client_id=client.id, month="2026-01", status="due",
        currency="EUR", amount=Decimal("5400.00"),
        issue_date=date(2025, 12, 1), due_date=date(2026, 1, 15),
    ))
    session.commit()

    banking_service.create_session(session, "mock-code")
    res = banking_service.sync(session)

    assert res["invoices_reconciled"] >= 1
    inv = session.query(models.Invoice).filter_by(number="90").one()
    assert inv.status == "paid"
    assert inv.paid_transaction_id is not None
