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

    projection = forecast_service.project(db_session, 2026)
    by_month = {m["month"]: m for m in projection["months"]}

    # 20 × 500 × 0.9 = 9000
    assert by_month["2026-01"]["revenue_eur"] == Decimal("9000.00")
    # 18 × 500 × 0.9 = 8100
    assert by_month["2026-02"]["revenue_eur"] == Decimal("8100.00")
    # Mois sans entrée → 0
    assert by_month["2026-03"]["revenue_eur"] == Decimal("0.00")
    assert projection["totals"]["revenue_eur"] == Decimal("17100.00")


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


def test_is_includes_positive_investment_gain(db_session):
    client = _make_client(db_session)
    forecast_service.upsert_inputs(
        db_session,
        [{"month": "2026-01", "client_id": client.id, "days": Decimal("100"),
          "rate": Decimal("100"), "fx_rate": Decimal("1"), "note": ""}],
    )
    # Plus-value latente +2000 (prise en compte) et une moins-value -500 (ignorée).
    db_session.add(models.Investment(
        label="BTC", type="crypto", currency="EUR",
        opening_value_eur=Decimal("1000"), current_value_eur=Decimal("3000")))
    db_session.add(models.Investment(
        label="ETH", type="crypto", currency="EUR",
        opening_value_eur=Decimal("2000"), current_value_eur=Decimal("1500")))
    db_session.commit()

    result = forecast_service.estimate_is(db_session, 2026)
    # Résultat projeté = 10000 (revenu) - 0 (charges) + 2000 (PV) = 12000
    assert result["base_eur"] == Decimal("12000.00")


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
