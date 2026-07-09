"""
Tests du widget « D'où vient ma trésorerie ? » (pont ouverture → banque).

Le pont doit BOUCLER exactement : ouverture + Σ lignes identifiées + résiduel
= solde bancaire actuel. Les lignes transfer/internal sont groupées par nom de
catégorie (aucun nom en dur dans le code). Les remboursements (+) sur charges
restent DANS les charges nettes (pas en « autres revenus »).
"""

from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db import models
from backend.db.base import Base
from backend.services.treasury import treasury_bridge

_TODAY = date(2026, 7, 8)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, future=True)()
    _seed(s)
    try:
        yield s
    finally:
        s.close()


def _seed(db):
    db.add(models.Settings(id=1))
    db.add(models.FxRate(currency="USD", rate=Decimal("0.90")))
    # Compte EUR synchronisé : solde actuel 1000.
    db.add(models.BankAccount(
        provider="qonto", account_uid="ACC", currency="EUR", name="Qonto",
        balance=Decimal("1000.00"), last_synced_at=datetime(2026, 7, 8, 8, 0),
    ))
    # Ouverture d'exercice saisie : 800 au 01/01/2026.
    db.add(models.OpeningBalance(account_uid="ACC", year=2026, balance=Decimal("800.00")))
    # Catégories : charge + transfert dividendes (nom LIBRE, pas en dur).
    db.add(models.Category(id=1, name="Frais", type="charge"))
    db.add(models.Category(id=2, name="Dividendes dirigeant", type="transfer"))
    db.add(models.Category(id=3, name="Ventes", type="revenue"))
    db.add(models.Client(id=1, code="SWIB", legal_name="Swib", currency="EUR"))
    db.commit()


def _tx(db, ext, d, amount, *, kind, cat=None, invoice_id=None, eur=None):
    db.add(models.Transaction(
        account_uid="ACC", external_id=ext, booked_date=d,
        amount=Decimal(str(amount)), currency="EUR", kind=kind,
        category_id=cat, invoice_id=invoice_id,
        amount_eur=Decimal(str(eur)) if eur is not None else None,
    ))
    db.commit()


def test_bridge_closes_exactly_on_bank_balance(db):
    # Facture 2026 payée 500 ; facture 2025 payée 300 (encaissée en 2026).
    inv26 = models.Invoice(number="10", client_id=1, month="2026-02", status="paid",
                           currency="EUR", amount=Decimal("500"),
                           amount_eur_received=Decimal("500"), paid_date=date(2026, 3, 1))
    inv25 = models.Invoice(number="9", client_id=1, month="2025-12", status="paid",
                           currency="EUR", amount=Decimal("300"),
                           amount_eur_received=Decimal("300"), paid_date=date(2026, 1, 15))
    db.add_all([inv26, inv25])
    db.commit()
    _tx(db, "p26", date(2026, 3, 1), "500", kind="revenue", cat=3, invoice_id=inv26.id)
    _tx(db, "p25", date(2026, 1, 15), "300", kind="revenue", cat=3, invoice_id=inv25.id)
    # Charge −150 + remboursement +50 → charges NETTES −100.
    _tx(db, "c1", date(2026, 2, 10), "-150", kind="charge", cat=1)
    _tx(db, "c2", date(2026, 4, 2), "50", kind="charge", cat=1)
    # Revenu non facturé +80 (indemnité client).
    _tx(db, "r1", date(2026, 6, 9), "80", kind="revenue", cat=3)
    # Dividendes −500 (catégorie transfer, nom libre).
    _tx(db, "d1", date(2026, 5, 1), "-500", kind="transfer", cat=2)
    # Jambe de conversion −80 : dans le solde bancaire mais dans AUCUNE ligne
    # (les conversions vivent dans le résiduel) → résiduel attendu −80.
    _tx(db, "cv1", date(2026, 6, 15), "-80", kind="conversion")

    out = treasury_bridge(db, today=_TODAY)

    lines = {l["key"]: Decimal(str(l["amount_eur"])) for l in out["lines"]}
    assert Decimal(str(out["opening_eur"])) == Decimal("800.00")
    assert lines["received_current"] == Decimal("500.00")
    assert lines["received_prior"] == Decimal("300.00")
    assert lines["other_revenue"] == Decimal("80.00")   # SANS le remboursement
    assert lines["charges"] == Decimal("-100.00")       # nettes du remboursement
    assert lines["cat:Dividendes dirigeant"] == Decimal("-500.00")
    # Banque reconstruite au 08/07 : 800+500+300−150+50+80−500−80 = 1000.
    # Lignes identifiées = 280 → résiduel = 1000 − 800 − 280 = −80 (la conversion).
    assert Decimal(str(out["residual_eur"])) == Decimal("-80.00")
    total = Decimal(str(out["opening_eur"])) + sum(lines.values()) + Decimal(str(out["residual_eur"]))
    assert total == Decimal(str(out["bank_today_eur"])) == Decimal("1000.00")
    # Résiduel 80/1480 ≈ 5,4 % du volume > seuil 2 % → alerte.
    assert out["residual_warning"] is True


def test_bridge_as_of_recomputes_everything_at_date(db):
    """
    Preuve de dynamisme : à `as_of=15/03/2026`, le pont ne voit que les flux
    jusqu'à cette date et boucle sur le solde RECONSTRUIT à cette date.
    """
    inv26 = models.Invoice(number="10", client_id=1, month="2026-02", status="paid",
                           currency="EUR", amount=Decimal("500"),
                           amount_eur_received=Decimal("500"), paid_date=date(2026, 3, 1))
    inv25 = models.Invoice(number="9", client_id=1, month="2025-12", status="paid",
                           currency="EUR", amount=Decimal("300"),
                           amount_eur_received=Decimal("300"), paid_date=date(2026, 1, 15))
    db.add_all([inv26, inv25])
    db.commit()
    _tx(db, "p26", date(2026, 3, 1), "500", kind="revenue", cat=3, invoice_id=inv26.id)
    _tx(db, "p25", date(2026, 1, 15), "300", kind="revenue", cat=3, invoice_id=inv25.id)
    _tx(db, "c1", date(2026, 2, 10), "-150", kind="charge", cat=1)
    _tx(db, "c2", date(2026, 4, 2), "50", kind="charge", cat=1)      # APRÈS as_of
    _tx(db, "d1", date(2026, 5, 1), "-500", kind="transfer", cat=2)  # APRÈS as_of

    out = treasury_bridge(db, as_of=date(2026, 3, 15), today=_TODAY)

    lines = {l["key"]: Decimal(str(l["amount_eur"])) for l in out["lines"]}
    assert lines["received_current"] == Decimal("500.00")
    assert lines["received_prior"] == Decimal("300.00")
    assert lines["charges"] == Decimal("-150.00")        # sans le remboursement d'avril
    assert "cat:Dividendes dirigeant" not in lines        # versés en mai → absents
    # Banque reconstruite au 15/03 : 800 + 300 − 150 + 500 = 1450, résiduel 0.
    assert Decimal(str(out["bank_today_eur"])) == Decimal("1450.00")
    assert Decimal(str(out["residual_eur"])) == Decimal("0.00")
    assert out["as_of"] == "2026-03-15"


def test_routes_tolerate_datetime_as_of(db):
    """
    Régression : un `as_of` avec HEURE (« 2026-03-15T22:34:00.000Z ») doit être
    tronqué à la date, pas rejeté (« Datetimes provided to dates should have
    zero time »). Chaîne vide / 'undefined' → ignorée. Garbage → 422 clair.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.routes.dashboard_bridge import router as bridge_router
    from backend.api.routes.transactions import router as tx_router
    from backend.api.routes.treasury import router as treasury_router
    from backend.db.base import get_db

    app = FastAPI()
    app.include_router(bridge_router)
    app.include_router(tx_router)
    app.include_router(treasury_router)
    app.dependency_overrides[get_db] = lambda: db

    c = TestClient(app)
    assert c.get("/api/dashboard/treasury-bridge?as_of=2026-03-15T22:34:00.000Z").status_code == 200
    assert c.get("/api/transactions?bridge=charges&as_of=2026-03-15T22:34:00").status_code == 200
    assert c.get("/api/treasury?as_of=2026-03-15T22:34:00.000Z").status_code == 200
    # Vide / 'undefined' → ignoré (comportement par défaut).
    assert c.get("/api/dashboard/treasury-bridge?as_of=").status_code == 200
    assert c.get("/api/transactions?bridge=charges&as_of=undefined").status_code == 200
    # Garbage → 422 avec message lisible.
    r = c.get("/api/dashboard/treasury-bridge?as_of=n-importe-quoi")
    assert r.status_code == 422
    assert "date invalide" in r.json()["detail"]


def test_bridge_reports_pending_dues(db):
    db.add(models.Invoice(number="11", client_id=1, month="2026-06", status="due",
                          currency="EUR", amount=Decimal("700"),
                          amount_eur_forecast=Decimal("700")))
    db.commit()
    out = treasury_bridge(db, today=_TODAY)
    assert Decimal(str(out["due_pending_eur"])) == Decimal("700.00")
