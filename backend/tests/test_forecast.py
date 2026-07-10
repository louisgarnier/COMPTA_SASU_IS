"""
Tests du domaine Prévision : service (projection + IS) et routes.

- SQLite en mémoire (pattern test_db.py).
- Vérifie revenu projeté = jours × TJH × fx.
- Vérifie le barème IS au seuil (base 50000, seuil 42500, 0.15/0.25).
- Route testée via FastAPI TestClient + dependency_overrides[get_db].
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.routes.forecast import router as forecast_router
from backend.db import models
from backend.db.base import Base, get_db
from backend.services import forecast as forecast_service


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    try:
        yield session
    finally:
        session.close()


def _make_client(db, code="SWIB") -> models.Client:
    client = models.Client(code=code, legal_name="Client Test", currency="USD")
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


# --------------------------------------------------------------------------- #
# Service : upsert + projection                                               #
# --------------------------------------------------------------------------- #


def test_projected_revenue_equals_days_rate_fx(db_session):
    client = _make_client(db_session)  # USD
    # FX théorique depuis les Réglages (plus de fx_rate manuel).
    db_session.add(models.FxRate(currency="USD", rate=Decimal("0.9")))
    db_session.commit()
    items = [
        {"month": "2026-01", "client_id": client.id, "rate_unit": "day",
         "days": Decimal("20"), "rate": Decimal("500"), "note": ""},
        {"month": "2026-02", "client_id": client.id, "rate_unit": "day",
         "days": Decimal("18"), "rate": Decimal("500"), "note": ""},
    ]
    forecast_service.upsert_inputs(db_session, items)

    projection = forecast_service.project(db_session, 2026, today=date(2026, 7, 3))
    by_month = {m["month"]: m for m in projection["months"]}

    # 20 × 500 × 0.9 = 9000
    assert by_month["2026-01"]["revenue_eur"] == Decimal("9000.00")
    # 18 × 500 × 0.9 = 8100
    assert by_month["2026-02"]["revenue_eur"] == Decimal("8100.00")
    # Mois sans entrée → 0
    assert by_month["2026-03"]["revenue_eur"] == Decimal("0.00")
    assert projection["totals"]["revenue_eur"] == Decimal("17100.00")


def test_projection_includes_issued_invoices_at_pnl_value(db_session):
    """
    Décision produit 2026-07 : le « CA projeté » inclut les factures ÉMISES et
    PAYÉES de l'exercice (même logique que le P&L accrual) — générer une facture
    ne fait plus chuter le CA projeté. Une payée compte à son EUR RÉEL encaissé.
    """
    client = _make_client(db_session)
    db_session.add(models.FxRate(currency="USD", rate=Decimal("0.9")))
    # Prévision mars : 10 j × 500 × 0.9 = 4500 (forecast).
    forecast_service.upsert_inputs(db_session, [
        {"month": "2026-03", "client_id": client.id, "rate_unit": "day",
         "days": Decimal("10"), "rate": Decimal("500"), "note": ""},
    ])
    # Facture ÉMISE janv : prévisionnel 9000.
    db_session.add(models.Invoice(
        number="200", client_id=client.id, month="2026-01", status="due",
        currency="USD", amount=Decimal("10000"), amount_eur_forecast=Decimal("9000"),
    ))
    # Facture PAYÉE fév : EUR réel encaissé 8500 (≠ prévisionnel 8100).
    db_session.add(models.Invoice(
        number="201", client_id=client.id, month="2026-02", status="paid",
        currency="USD", amount=Decimal("9000"), amount_eur_forecast=Decimal("8100"),
        amount_eur_received=Decimal("8500"),
    ))
    db_session.commit()

    projection = forecast_service.project(db_session, 2026, today=date(2026, 7, 3))
    by_month = {m["month"]: m for m in projection["months"]}
    assert by_month["2026-01"]["revenue_eur"] == Decimal("9000.00")  # due
    assert by_month["2026-02"]["revenue_eur"] == Decimal("8500.00")  # paid, RÉEL
    assert by_month["2026-03"]["revenue_eur"] == Decimal("4500.00")  # forecast
    assert projection["totals"]["revenue_eur"] == Decimal("22000.00")


def test_upsert_is_idempotent_on_month_client(db_session):
    client = _make_client(db_session)
    forecast_service.upsert_inputs(
        db_session,
        [{"month": "2026-01", "client_id": client.id, "days": Decimal("10"),
          "rate": Decimal("400"), "fx_rate": Decimal("1"), "note": "v1"}],
    )
    forecast_service.upsert_inputs(
        db_session,
        [{"month": "2026-01", "client_id": client.id, "days": Decimal("15"),
          "rate": Decimal("400"), "fx_rate": Decimal("1"), "note": "v2"}],
    )
    rows = forecast_service.get_inputs(db_session, 2026)
    assert len(rows) == 1
    assert rows[0].days == Decimal("15")
    assert rows[0].note == "v2"


def test_cumulative_cash_uses_starting_cash(db_session):
    client = _make_client(db_session)
    forecast_service.upsert_inputs(
        db_session,
        [{"month": "2026-01", "client_id": client.id, "days": Decimal("10"),
          "rate": Decimal("100"), "fx_rate": Decimal("1"), "note": ""}],
    )
    projection = forecast_service.project(
        db_session, 2026, starting_cash_eur=Decimal("5000")
    )
    jan = projection["months"][0]
    # 5000 + (1000 - 0 charges) = 6000
    assert jan["cumulative_cash_eur"] == Decimal("6000.00")


# --------------------------------------------------------------------------- #
# Service : forecast des charges (écoulé = réel, en cours = prorata, futur =   #
# moyenne des mois écoulés). Réf. today = 2026-07-03.                          #
# --------------------------------------------------------------------------- #


def _charge_cat(db) -> models.Category:
    db.add(
        models.BankAccount(provider="revolut", account_uid="ACC", currency="EUR")
    )
    cat = models.Category(name="Charges", type="charge")
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


def _add_charge(db, cat_id: int, d: date, amount_eur, ext: str) -> None:
    """Ajoute une charge opérationnelle (montant négatif, EUR) datée `d`."""
    db.add(
        models.Transaction(
            account_uid="ACC",
            external_id=ext,
            booked_date=d,
            amount=-Decimal(str(amount_eur)),
            currency="EUR",
            kind="charge",
            category_id=cat_id,
        )
    )
    db.commit()


_TODAY = date(2026, 7, 3)  # 3 juillet 2026 : Jan–Juin écoulés, Juil en cours


def test_elapsed_months_show_real_charges_not_average(db_session):
    cat = _charge_cat(db_session)
    _add_charge(db_session, cat.id, date(2026, 1, 15), "123.45", "j")
    _add_charge(db_session, cat.id, date(2026, 2, 10), "200", "f")

    projection = forecast_service.project(db_session, 2026, today=_TODAY)
    by_month = {m["month"]: m for m in projection["months"]}

    # Mois écoulés → charges RÉELLES (pas la moyenne (123.45+200)/6 = 53.91).
    assert by_month["2026-01"]["charges_eur"] == Decimal("123.45")
    assert by_month["2026-01"]["is_forecast"] is False
    assert by_month["2026-02"]["charges_eur"] == Decimal("200.00")
    assert by_month["2026-02"]["is_forecast"] is False


def test_future_months_use_average_of_elapsed_months(db_session):
    cat = _charge_cat(db_session)
    # Total charges Jan–Juin = 600 ; 6 mois écoulés → moyenne = 100.
    _add_charge(db_session, cat.id, date(2026, 1, 20), "600", "j")

    projection = forecast_service.project(db_session, 2026, today=_TODAY)
    by_month = {m["month"]: m for m in projection["months"]}

    assert by_month["2026-08"]["charges_eur"] == Decimal("100.00")
    assert by_month["2026-08"]["is_forecast"] is True
    assert by_month["2026-12"]["charges_eur"] == Decimal("100.00")


def test_full_future_year_falls_back_to_trailing_charge_avg(db_session):
    """Année entièrement future (2027 vu de 2026) : les charges ne sont pas 0,
    on retombe sur la moyenne des 12 derniers mois réels (repli IS)."""
    cat = _charge_cat(db_session)
    # 1200 € de charges sur les 6 mois écoulés de 2026 → moyenne 12 mois = 100/mois.
    _add_charge(db_session, cat.id, date(2026, 3, 10), "1200", "hist")

    projection = forecast_service.project(db_session, 2027, today=_TODAY)
    by_month = {m["month"]: m for m in projection["months"]}
    # Avant le fix : 0. Désormais ≈ 1200/12 = 100 par mois futur.
    assert by_month["2027-01"]["charges_eur"] == Decimal("100.00")
    assert by_month["2027-12"]["charges_eur"] == Decimal("100.00")


def test_current_month_prorata_of_remaining_days(db_session):
    cat = _charge_cat(db_session)
    # Moyenne des mois écoulés = 186 / 6 = 31.
    _add_charge(db_session, cat.id, date(2026, 1, 20), "186", "j")
    # Charge du mois en cours AVANT aujourd'hui (1 juil) → comptée en réel.
    _add_charge(db_session, cat.id, date(2026, 7, 1), "10", "j1")
    # Charge datée APRÈS aujourd'hui (10 juil) → ignorée du réel du mois en cours.
    _add_charge(db_session, cat.id, date(2026, 7, 10), "999", "j10")

    projection = forecast_service.project(db_session, 2026, today=_TODAY)
    july = {m["month"]: m for m in projection["months"]}["2026-07"]

    # réel avant aujourd'hui (10) + prorata jours restants : 31 × 29/31 = 29.
    assert july["charges_eur"] == Decimal("39.00")
    assert july["is_forecast"] is True


def test_month_exposes_actual_vs_forecast_charge_split(db_session):
    cat = _charge_cat(db_session)
    # Moyenne des mois écoulés = 186 / 6 = 31.
    _add_charge(db_session, cat.id, date(2026, 1, 20), "186", "j")
    # Charge du mois en cours AVANT aujourd'hui → composante réelle.
    _add_charge(db_session, cat.id, date(2026, 7, 1), "10", "j1")

    proj = forecast_service.project(db_session, 2026, today=_TODAY)
    by = {m["month"]: m for m in proj["months"]}

    # Écoulé : tout en réel, rien en prévision.
    assert by["2026-01"]["charges_actual_eur"] == Decimal("186.00")
    assert by["2026-01"]["charges_forecast_eur"] == Decimal("0.00")
    # En cours : réel passé (10) + prorata (31 × 29/31 = 29).
    assert by["2026-07"]["charges_actual_eur"] == Decimal("10.00")
    assert by["2026-07"]["charges_forecast_eur"] == Decimal("29.00")
    # Futur : tout en prévision (moyenne).
    assert by["2026-08"]["charges_actual_eur"] == Decimal("0.00")
    assert by["2026-08"]["charges_forecast_eur"] == Decimal("31.00")
    # Invariant : total = réel + prévision sur chaque mois.
    for m in proj["months"]:
        assert Decimal(m["charges_eur"]) == Decimal(m["charges_actual_eur"]) + Decimal(
            m["charges_forecast_eur"]
        )


def test_past_year_all_actual_no_forecast(db_session):
    cat = _charge_cat(db_session)
    _add_charge(db_session, cat.id, date(2025, 3, 5), "500", "m")
    _add_charge(db_session, cat.id, date(2025, 11, 8), "700", "n")

    projection = forecast_service.project(db_session, 2025, today=_TODAY)
    by_month = {m["month"]: m for m in projection["months"]}

    # Année passée → tous les mois sont écoulés → 100 % réel, aucun forecast.
    assert by_month["2025-03"]["charges_eur"] == Decimal("500.00")
    assert by_month["2025-11"]["charges_eur"] == Decimal("700.00")
    assert by_month["2025-05"]["charges_eur"] == Decimal("0.00")
    assert all(m["is_forecast"] is False for m in projection["months"])


# --------------------------------------------------------------------------- #
# Service : estimation IS                                                     #
# --------------------------------------------------------------------------- #


def test_is_splits_at_threshold(db_session):
    # Barème par défaut : 0.15 jusqu'à 42500, 0.25 au-delà.
    result = forecast_service.estimate_is(
        db_session, 2026, base_override=Decimal("50000")
    )
    assert result["base_eur"] == Decimal("50000.00")
    assert result["threshold_eur"] == Decimal("42500.00")
    # 42500 × 0.15 = 6375
    assert result["is_low_eur"] == Decimal("6375.00")
    # 7500 × 0.25 = 1875
    assert result["is_high_eur"] == Decimal("1875.00")
    assert result["is_total_eur"] == Decimal("8250.00")


def test_is_below_threshold_only_low_rate(db_session):
    result = forecast_service.estimate_is(
        db_session, 2026, base_override=Decimal("30000")
    )
    # 30000 × 0.15 = 4500 ; pas de tranche haute
    assert result["is_low_eur"] == Decimal("4500.00")
    assert result["is_high_eur"] == Decimal("0.00")
    assert result["is_total_eur"] == Decimal("4500.00")


def test_is_taxes_expected_and_realized_gains_not_latent(db_session):
    """
    Modèle 2026-07-10 : le gain LATENT n'entre plus dans la base IS. Comptent :
    le gain ATTENDU (échéance dans l'exercice, placement ouvert) et le gain
    RÉALISÉ (clôture rapprochée), pertes réalisées déductibles.
    """
    from datetime import date as date_type

    client = _make_client(db_session)
    forecast_service.upsert_inputs(
        db_session,
        [{"month": "2026-01", "client_id": client.id, "days": Decimal("100"),
          "rate": Decimal("100"), "fx_rate": Decimal("1"), "note": ""}],
    )
    # Latent pur (+2000 non taxé), attendu (+6700), réalisé (−500 déductible).
    db_session.add(models.Investment(
        label="BTC latent", type="crypto", currency="EUR",
        opening_value_eur=Decimal("1000"), current_value_eur=Decimal("3000")))
    db_session.add(models.Investment(
        label="K Technologie", type="bourse", currency="EUR",
        opening_value_eur=Decimal("69600"), current_value_eur=Decimal("77000"),
        expected_value_eur=Decimal("76300"), expected_month="2026-12"))
    db_session.add(models.Investment(
        label="ETH vendu à perte", type="crypto", currency="EUR",
        opening_value_eur=Decimal("2000"), current_value_eur=Decimal("1500"),
        closed_date=date_type(2026, 3, 1), realized_gain_eur=Decimal("-500")))
    db_session.commit()

    # Prévisionnel : attendu (76300−69600=6700) + réalisé (−500), latent exclu.
    assert forecast_service.financial_income(db_session, 2026, scope="forecast") == Decimal("6200")
    # Réalisé/engagé : uniquement le réalisé.
    assert forecast_service.financial_income(db_session, 2026, scope="engaged") == Decimal("-500")

    result = forecast_service.estimate_is(db_session, 2026)
    # Base projetée = 10000 (revenu) − 0 (charges) + 6200 (produits financiers)
    assert result["base_eur"] == Decimal("16200.00")


# --------------------------------------------------------------------------- #
# Route : GET / PUT                                                           #
# --------------------------------------------------------------------------- #


@pytest.fixture
def client_app(db_session):
    app = FastAPI()
    app.include_router(forecast_router)
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def test_route_put_then_get(client_app, db_session):
    client = _make_client(db_session)  # USD
    db_session.add(models.FxRate(currency="USD", rate=Decimal("0.9")))
    db_session.commit()
    body = {
        "year": 2026,
        "inputs": [
            {"month": "2026-01", "client_id": client.id, "rate_unit": "day",
             "days": "20", "rate": "500", "note": "SWIB janv"},
        ],
    }
    put_resp = client_app.put("/api/forecast", json=body)
    assert put_resp.status_code == 200
    data = put_resp.json()
    assert len(data["inputs"]) == 1
    assert data["projection"]["months"][0]["revenue_eur"] == "9000.00"

    get_resp = client_app.get("/api/forecast", params={"year": 2026})
    assert get_resp.status_code == 200
    gdata = get_resp.json()
    assert gdata["projection"]["totals"]["revenue_eur"] == "9000.00"
    assert "is" in gdata and "is_total_eur" in gdata["is"]


def test_route_get_with_starting_cash(client_app, db_session):
    client = _make_client(db_session)
    forecast_service.upsert_inputs(
        db_session,
        [{"month": "2026-01", "client_id": client.id, "days": Decimal("10"),
          "rate": Decimal("100"), "fx_rate": Decimal("1"), "note": ""}],
    )
    resp = client_app.get(
        "/api/forecast", params={"year": 2026, "starting_cash_eur": "5000"}
    )
    assert resp.status_code == 200
    jan = resp.json()["projection"]["months"][0]
    assert jan["cumulative_cash_eur"] == "6000.00"


def test_issue_past_month_creates_due_invoice(db_session):
    """issue=True + mois passé → facture `due` numérotée depuis le compteur."""
    client = _make_client(db_session)
    db_session.add(models.Settings(id=1, next_invoice_number=40))
    db_session.add(models.FxRate(currency="USD", rate=Decimal("1")))
    db_session.commit()

    forecast_service.upsert_inputs(
        db_session,
        [{"month": "2025-11", "client_id": client.id, "rate_unit": "day",
          "days": Decimal("10"), "rate": Decimal("100"), "note": ""}],
        issue=True,
        today=date(2026, 7, 1),
    )
    inv = db_session.query(models.Invoice).filter_by(month="2025-11").one()
    assert inv.status == "due"
    assert inv.number == "40"  # compteur consommé
    assert inv.issue_date == date(2025, 11, 30)
    # Compteur incrémenté pour la prochaine.
    assert db_session.get(models.Settings, 1).next_invoice_number == 41


def test_issue_leaves_future_month_as_forecast(db_session):
    """issue=True mais mois futur → reste en prévision (pas d'émission)."""
    client = _make_client(db_session)
    db_session.add(models.Settings(id=1, next_invoice_number=40))
    db_session.add(models.FxRate(currency="USD", rate=Decimal("1")))
    db_session.commit()

    forecast_service.upsert_inputs(
        db_session,
        [{"month": "2026-09", "client_id": client.id, "rate_unit": "day",
          "days": Decimal("10"), "rate": Decimal("100"), "note": ""}],
        issue=True,
        today=date(2026, 7, 1),
    )
    inv = db_session.query(models.Invoice).filter_by(month="2026-09").one()
    assert inv.status == "forecast"
    assert db_session.get(models.Settings, 1).next_invoice_number == 40  # inchangé


def test_issue_promotes_existing_forecast(db_session):
    """Une prévision passée déjà saisie est promue en `due` quand on émet."""
    client = _make_client(db_session)
    db_session.add(models.Settings(id=1, next_invoice_number=40))
    db_session.add(models.FxRate(currency="USD", rate=Decimal("1")))
    db_session.commit()

    item = {"month": "2025-12", "client_id": client.id, "rate_unit": "day",
            "days": Decimal("10"), "rate": Decimal("100"), "note": ""}
    forecast_service.upsert_inputs(db_session, [item])  # prévision
    forecast_service.upsert_inputs(db_session, [item], issue=True, today=date(2026, 7, 1))

    invs = db_session.query(models.Invoice).filter_by(month="2025-12").all()
    assert len(invs) == 1  # pas de doublon
    assert invs[0].status == "due" and invs[0].number == "40"


def test_issue_does_not_overwrite_paid(db_session):
    """Une facture déjà rapprochée (paid) n'est pas réécrite par une nouvelle saisie."""
    client = _make_client(db_session)
    db_session.add(models.Settings(id=1, next_invoice_number=40))
    db_session.add(models.FxRate(currency="USD", rate=Decimal("1")))
    db_session.add(models.Invoice(
        number="12", client_id=client.id, month="2025-11", period_label="2025-11",
        status="paid", days=Decimal("5"), hours=Decimal("40"), rate=Decimal("100"),
        currency="USD", amount=Decimal("500"), amount_eur_forecast=Decimal("500"),
    ))
    db_session.commit()

    forecast_service.upsert_inputs(
        db_session,
        [{"month": "2025-11", "client_id": client.id, "rate_unit": "day",
          "days": Decimal("10"), "rate": Decimal("100"), "note": ""}],
        issue=True,
        today=date(2026, 7, 1),
    )
    invs = db_session.query(models.Invoice).filter_by(month="2025-11").all()
    assert len(invs) == 1
    assert invs[0].status == "paid" and invs[0].amount == Decimal("500")  # intacte


def test_issued_past_invoice_counts_in_its_own_year_pnl(db_session):
    """Facture 2025 émise → compte dans le P&L 2025, jamais 2026."""
    from backend.services import pnl as pnl_service

    client = _make_client(db_session)
    db_session.add(models.Settings(id=1, next_invoice_number=40))
    db_session.add(models.FxRate(currency="USD", rate=Decimal("1")))
    db_session.commit()
    forecast_service.upsert_inputs(
        db_session,
        [{"month": "2025-11", "client_id": client.id, "rate_unit": "day",
          "days": Decimal("10"), "rate": Decimal("100"), "note": ""}],
        issue=True,
        today=date(2026, 7, 1),
    )
    # 10 × 100 × 1 = 1000 en 2025, 0 en 2026.
    assert pnl_service.summary(db_session, 2025)["revenue_eur"] == Decimal("1000.00")
    assert pnl_service.summary(db_session, 2026)["revenue_eur"] == Decimal("0.00")


def test_route_put_issue_returns_due_status(client_app, db_session):
    """PUT issue=True renvoie les factures émises avec leur statut `due`."""
    client = _make_client(db_session)
    db_session.add(models.Settings(id=1, next_invoice_number=40))
    db_session.add(models.FxRate(currency="USD", rate=Decimal("1")))
    db_session.commit()
    body = {
        "year": 2025,
        "issue": True,
        "inputs": [
            {"month": "2025-11", "client_id": client.id, "rate_unit": "day",
             "days": "10", "rate": "100", "note": ""},
        ],
    }
    resp = client_app.put("/api/forecast", json=body)
    assert resp.status_code == 200
    inputs = resp.json()["inputs"]
    assert len(inputs) == 1
    assert inputs[0]["status"] == "due"
    assert inputs[0]["number"] == "40"


def test_route_put_honors_starting_cash(client_app, db_session):
    """PUT renvoie une projection cumulée à partir de starting_cash_eur (pas 0)."""
    client = _make_client(db_session)
    db_session.add(models.FxRate(currency="USD", rate=Decimal("1")))
    db_session.commit()
    body = {
        "year": 2026,
        "starting_cash_eur": "10000",
        "inputs": [
            {"month": "2026-01", "client_id": client.id, "rate_unit": "day",
             "days": "10", "rate": "100", "note": ""},
        ],
    }
    resp = client_app.put("/api/forecast", json=body)
    assert resp.status_code == 200
    jan = resp.json()["projection"]["months"][0]
    # 10000 de départ + 1000 de revenu janvier = 11000 (et non 1000).
    assert jan["cumulative_cash_eur"] == "11000.00"


def test_route_delete_forecast_input(client_app, db_session):
    """DELETE supprime la prévision d'un client×mois et rien d'autre."""
    client = _make_client(db_session)
    forecast_service.upsert_inputs(
        db_session,
        [
            {"month": "2026-01", "client_id": client.id, "days": Decimal("10"),
             "rate": Decimal("100"), "note": ""},
            {"month": "2026-02", "client_id": client.id, "days": Decimal("8"),
             "rate": Decimal("100"), "note": ""},
        ],
    )

    resp = client_app.delete(f"/api/forecast/{client.id}/2026-01")
    assert resp.status_code == 204, resp.text

    remaining = forecast_service.get_inputs(db_session, 2026)
    months = [r.month for r in remaining]
    assert "2026-01" not in months
    assert "2026-02" in months


def test_delete_forecast_input_missing_is_noop(client_app, db_session):
    client = _make_client(db_session)
    # Aucune prévision : la suppression ne lève pas, renvoie 204.
    resp = client_app.delete(f"/api/forecast/{client.id}/2026-05")
    assert resp.status_code == 204


def test_delete_forecast_ignores_issued_invoice(db_session):
    """delete_input ne touche pas une facture émise (due/paid)."""
    client = _make_client(db_session)
    db_session.add(models.Invoice(
        number="90", client_id=client.id, month="2026-03", period_label="2026-03",
        status="due", days=Decimal("10"), hours=Decimal("80"), rate=Decimal("100"),
        currency="USD", amount=Decimal("1000"), amount_eur_forecast=Decimal("900"),
    ))
    db_session.commit()

    deleted = forecast_service.delete_input(db_session, client.id, "2026-03")
    assert deleted is False
    # La facture émise est toujours là.
    assert db_session.query(models.Invoice).filter_by(month="2026-03").count() == 1


def test_charges_projection_nets_refunds(db_session):
    """
    Régression (bug 2026-07-10) : un remboursement (+) sur une catégorie de
    charge doit RÉDUIRE les charges du mois — l'ancien `abs()` le comptait
    comme une charge supplémentaire (P&L projeté et IS gonflés de 2× le
    remboursé ; écart de 1 045,01 € constaté en prod : 522,50 € de refunds).
    """
    chg = models.Category(name="Frais", type="charge")
    db_session.add(chg)
    db_session.add(models.BankAccount(provider="qonto", account_uid="A", currency="EUR"))
    db_session.commit()
    db_session.add(models.Transaction(
        account_uid="A", external_id="c1", booked_date=date(2026, 2, 5),
        amount=Decimal("-100.00"), currency="EUR", description="charge",
        counterparty="X", kind="charge", category_id=chg.id))
    db_session.add(models.Transaction(
        account_uid="A", external_id="c2", booked_date=date(2026, 2, 20),
        amount=Decimal("30.00"), currency="EUR", description="refund",
        counterparty="X", kind="charge", category_id=chg.id))
    db_session.commit()

    proj = forecast_service.project(db_session, 2026, today=date(2026, 7, 4))
    feb = next(m for m in proj["months"] if m["month"] == "2026-02")
    # Net : 100 − 30 = 70 (l'ancien code donnait 130).
    assert feb["charges_actual_eur"] == Decimal("70.00")
