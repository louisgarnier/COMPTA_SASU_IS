"""
Tests Balance timeline — solde de trésorerie mensuel cumulé (EUR).

Passé/en cours : reconstruction opening_balance + Σ mouvements à la fin de mois.
Futur : solde de fin du mois courant + cumul des nets de prévision (forecast).

SQLite en mémoire. today figé au 2026-07-03 pour un déroulé déterministe.
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db import models
from backend.db.base import Base, get_db
from backend.services.treasury import balance_timeline, consolidated_treasury

TODAY = date(2026, 7, 3)


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
    _seed(db)
    yield db
    db.close()


def _seed(db):
    db.add(models.Settings(id=1))
    db.add(models.FxRate(currency="USD", rate=Decimal("0.90")))

    # Compte EUR : ouverture 1000 le 1er janvier.
    db.add(
        models.BankAccount(
            provider="qonto",
            account_uid="eur-1",
            currency="EUR",
            name="Qonto EUR",
            opening_balance=Decimal("1000.00"),
            opening_balance_date=date(2026, 1, 1),
        )
    )

    cat_rev = models.Category(id=1, name="Prestations", type="revenue")
    # Type 'transfer' : mouvement compté au solde mais exclu des charges forecast,
    # pour que les nets futurs ne dépendent que des ForecastInput (test net propre).
    cat_tr = models.Category(id=3, name="Virement", type="transfer")
    db.add_all([cat_rev, cat_tr])

    # Mouvements : +500 (janv), +800 (fév), -300 (mars). Aucun ensuite.
    db.add(models.Transaction(
        account_uid="eur-1", external_id="e1", booked_date=date(2026, 1, 15),
        amount=Decimal("500.00"), currency="EUR", kind="revenue", category_id=1,
    ))
    db.add(models.Transaction(
        account_uid="eur-1", external_id="e2", booked_date=date(2026, 2, 10),
        amount=Decimal("800.00"), currency="EUR", kind="revenue", category_id=1,
    ))
    db.add(models.Transaction(
        account_uid="eur-1", external_id="e3", booked_date=date(2026, 3, 20),
        amount=Decimal("-300.00"), currency="EUR", kind="transfer", category_id=3,
    ))

    # Prévision : un client + une entrée en août → revenu 1000 EUR (10 j × 100 × 1).
    db.add(models.Client(id=1, code="ACME", legal_name="Acme", currency="EUR"))
    db.commit()
    # Fusion : prévision = facture status='forecast' (via le service).
    from backend.services import forecast as _fc
    _fc.upsert_inputs(db, [{
        "month": "2026-08", "client_id": 1,
        "days": Decimal("10"), "rate": Decimal("100"), "fx_rate": Decimal("1"), "note": "",
    }])

    db.commit()


# --- Reconstruction passée -------------------------------------------------


def test_past_month_end_reconstruction(session):
    result = balance_timeline(session, 2026, today=TODAY)
    by_month = {m["month"]: m for m in result["months"]}

    # Fin janvier : 1000 + 500 = 1500.
    assert by_month["2026-01"]["balance_eur"] == Decimal("1500.00")
    # Fin février : 1500 + 800 = 2300.
    assert by_month["2026-02"]["balance_eur"] == Decimal("2300.00")
    # Fin mars : 2300 - 300 = 2000. Stable jusqu'en juillet.
    assert by_month["2026-03"]["balance_eur"] == Decimal("2000.00")
    assert by_month["2026-06"]["balance_eur"] == Decimal("2000.00")
    assert by_month["2026-07"]["balance_eur"] == Decimal("2000.00")

    # Mois passés/courant : pas prévisionnels.
    for key in ("2026-01", "2026-02", "2026-03", "2026-06", "2026-07"):
        assert by_month[key]["is_forecast"] is False


def test_anchor_matches_consolidated_treasury(session):
    # Le solde courant reconstruit doit coller au total consolidé (as_of=today),
    # qui reconstruit lui aussi opening + mouvements pour un compte non synchronisé.
    result = balance_timeline(session, 2026, today=TODAY)
    consolidated = consolidated_treasury(session, as_of=TODAY)
    assert result["current_balance_eur"] == consolidated["bank_total_eur"]
    assert result["current_balance_eur"] == Decimal("2000.00")


# --- Projection future -----------------------------------------------------


def test_future_months_are_forecast_and_increment_at_payment_date(session):
    result = balance_timeline(session, 2026, today=TODAY)
    by_month = {m["month"]: m for m in result["months"]}

    # Août à décembre : prévisionnels.
    for key in ("2026-08", "2026-09", "2026-10", "2026-11", "2026-12"):
        assert by_month[key]["is_forecast"] is True

    # La prévision d'août (prestation) est encaissée à 60 j → cash fin octobre.
    # Le solde monte donc à l'ENCAISSEMENT (cohérent avec le cashflow), pas à la prestation.
    assert by_month["2026-08"]["balance_eur"] == Decimal("2000.00")
    assert by_month["2026-09"]["balance_eur"] == Decimal("2000.00")
    assert by_month["2026-10"]["balance_eur"] == Decimal("3000.00")
    assert by_month["2026-12"]["balance_eur"] == Decimal("3000.00")

    assert result["projected_year_end_eur"] == Decimal("3000.00")


def test_next_year_timeline_chains_through_end_of_current_year(session):
    """
    Vue 2027 (T-3) : la courbe doit PARTIR du solde projeté au 31/12/2026
    (solde actuel + nets d'août-déc 2026, dont l'encaissement d'octobre),
    pas du solde d'aujourd'hui — sinon les nets de fin 2026 sont perdus.
    """
    result = balance_timeline(session, 2027, today=TODAY)
    months = {m["month"]: m for m in result["months"]}
    # Solde actuel 2000 (1000+500+800−300) + encaissement oct 2026 (+1000) = 3000.
    assert months["2027-01"]["balance_eur"] == Decimal("3000.00")
    assert months["2027-12"]["balance_eur"] == Decimal("3000.00")
    assert all(m["is_forecast"] for m in result["months"])


def test_open_due_invoice_appears_in_balance_line(session):
    """Régression : une facture `due` (générée) doit remonter dans la ligne de solde
    (avant le fix, le solde futur lisait forecast.project qui ignore les factures due)."""
    # Facture due échéant en septembre pour 500 EUR.
    session.add(models.Invoice(
        number="F-DUE-1", client_id=1, month="2026-09", status="due",
        due_date=date(2026, 9, 15), currency="EUR",
        amount=Decimal("500"), amount_eur_forecast=Decimal("500"),
    ))
    session.commit()
    result = balance_timeline(session, 2026, today=TODAY)
    by_month = {m["month"]: m for m in result["months"]}
    # Septembre encaisse la facture due (+500) → 2000 + 500 = 2500.
    assert by_month["2026-09"]["balance_eur"] == Decimal("2500.00")


def test_twelve_months_and_shape(session):
    result = balance_timeline(session, 2026, today=TODAY)
    assert result["year"] == 2026
    assert len(result["months"]) == 12
    assert result["months"][0]["month"] == "2026-01"
    assert result["months"][11]["month"] == "2026-12"


# --- Route -----------------------------------------------------------------


def _client(session, monkeypatch):
    import backend.api.routes.dashboard_balance as mod

    real = mod.balance_timeline
    monkeypatch.setattr(
        mod, "balance_timeline", lambda db, year: real(db, year, today=TODAY)
    )

    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[get_db] = lambda: session
    return TestClient(app)


def test_route_balance_timeline(session, monkeypatch):
    client = _client(session, monkeypatch)
    resp = client.get("/api/dashboard/balance-timeline?year=2026")
    assert resp.status_code == 200
    body = resp.json()
    assert body["year"] == 2026
    assert len(body["months"]) == 12
    assert body["current_balance_eur"] == "2000.00"
    assert body["projected_year_end_eur"] == "3000.00"
    # Encaissement attendu fin octobre (prévision août + 60 j).
    oct_m = next(m for m in body["months"] if m["month"] == "2026-10")
    assert oct_m["is_forecast"] is True
    assert oct_m["balance_eur"] == "3000.00"
