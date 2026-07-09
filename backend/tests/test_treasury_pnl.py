"""
Tests Trésorerie consolidée + Compte de résultat mensuel.

SQLite en mémoire, données semées : un compte EUR, un compte USD (avec
amount_eur), un placement, et des transactions réparties sur plusieurs mois
(un produit en février, une charge en février, un investissement + une
conversion qui doivent être exclus du P&L).
"""

from decimal import Decimal
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from backend.db.base import Base, get_db
from backend.db import models
from backend.services.pnl import monthly_pnl
from backend.services.treasury import (
    consolidated_treasury,
    eur_amount,
    link_fx_conversion,
)


# --- Fixtures -------------------------------------------------------------


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
    # Paramètres société (singleton).
    db.add(models.Settings(id=1))
    # Taux FX théoriques (source unique de conversion EUR sous le nouveau modèle).
    db.add(models.FxRate(currency="USD", rate=Decimal("0.90")))
    db.add(models.FxRate(currency="CAD", rate=Decimal("0.68")))

    # Compte EUR : ouverture 1000, +500 (janv) -300 (fév) = 1200 EUR.
    db.add(models.BankAccount(
        provider="qonto", account_uid="eur-1", currency="EUR", name="Qonto EUR",
        opening_balance=Decimal("1000.00"), opening_balance_date=date(2026, 1, 1),
    ))
    # Compte USD : ouverture 0, +1000 USD (amount_eur=900) = 1000 USD / 900 EUR.
    db.add(models.BankAccount(
        provider="revolut", account_uid="usd-1", currency="USD", name="Revolut USD",
        opening_balance=Decimal("0.00"), opening_balance_date=date(2026, 1, 1),
    ))

    # Catégories.
    cat_rev = models.Category(id=1, name="Prestations", type="revenue")
    cat_chg = models.Category(id=2, name="Frais", type="charge")
    cat_conv = models.Category(id=3, name="Conversion", type="conversion")
    db.add_all([cat_rev, cat_chg, cat_conv])

    # --- Transactions compte EUR ---
    # Produit janvier +500 EUR.
    db.add(models.Transaction(
        account_uid="eur-1", external_id="e1", booked_date=date(2026, 1, 15),
        amount=Decimal("500.00"), currency="EUR", kind="revenue", category_id=1,
        amount_eur=Decimal("500.00"),
    ))
    # Produit février +800 EUR.
    db.add(models.Transaction(
        account_uid="eur-1", external_id="e2", booked_date=date(2026, 2, 10),
        amount=Decimal("800.00"), currency="EUR", kind="revenue", category_id=1,
        amount_eur=Decimal("800.00"),
    ))
    # Charge février -300 EUR.
    db.add(models.Transaction(
        account_uid="eur-1", external_id="e3", booked_date=date(2026, 2, 20),
        amount=Decimal("-300.00"), currency="EUR", kind="charge", category_id=2,
        amount_eur=Decimal("-300.00"),
    ))
    # Conversion (à exclure du P&L), catégorie type conversion.
    db.add(models.Transaction(
        account_uid="eur-1", external_id="e4", booked_date=date(2026, 2, 25),
        amount=Decimal("900.00"), currency="EUR", kind="conversion", category_id=3,
        amount_eur=Decimal("900.00"),
    ))

    # --- Transactions compte USD ---
    # Crédit +1000 USD, amount_eur=900 (kind revenue, mais devise USD).
    db.add(models.Transaction(
        account_uid="usd-1", external_id="u1", booked_date=date(2026, 3, 5),
        amount=Decimal("1000.00"), currency="USD", kind="revenue", category_id=1,
        amount_eur=Decimal("900.00"),
    ))
    # Ligne investissement (à exclure du P&L).
    db.add(models.Transaction(
        account_uid="usd-1", external_id="u2", booked_date=date(2026, 2, 5),
        amount=Decimal("-200.00"), currency="USD", kind="investment",
        amount_eur=Decimal("-180.00"),
    ))

    # Placement : valeur courante EUR = 5000.
    db.add(models.Investment(
        label="PEA", type="bourse", currency="EUR",
        current_value=Decimal("5000.00"), current_value_eur=Decimal("5000.00"),
    ))

    db.commit()


# --- Tests service : trésorerie ------------------------------------------


def test_consolidated_balances(session):
    result = consolidated_treasury(session)

    balances = {a["account_uid"]: a["balance"] for a in result["accounts"]}
    # EUR : 1000 + 500 + 800 - 300 + 900 (conversion compte, incluse au solde) = 2900.
    assert balances["eur-1"] == Decimal("2900.00")
    # USD : 0 + 1000 - 200 = 800 USD (solde en devise du compte).
    assert balances["usd-1"] == Decimal("800.00")


def test_consolidated_eur_totals(session):
    result = consolidated_treasury(session)

    # Bank EUR total :
    #   compte EUR = 2900 EUR
    #   compte USD (équiv EUR) = amount_eur 900 + (-180) = 720 EUR
    assert result["bank_total_eur"] == Decimal("3620.00")
    assert result["investments_total_eur"] == Decimal("5000.00")
    assert result["total_eur"] == Decimal("8620.00")


def test_eur_amount_uses_theoretical_rates(session):
    # Modèle théorique : montant natif × taux Réglages (amount_eur/fx_rate ignorés).
    rates = {"EUR": Decimal("1"), "USD": Decimal("0.90")}
    # Devise EUR -> montant tel quel.
    tx_eur = models.Transaction(account_uid="x", external_id="z2", amount=Decimal("50"),
                                currency="EUR")
    assert eur_amount(tx_eur, rates) == Decimal("50")
    # USD -> montant × 0.90 (même si amount_eur/fx_rate figés existent, ignorés).
    tx_usd = models.Transaction(account_uid="x", external_id="z", amount=Decimal("100"),
                                currency="USD", amount_eur=Decimal("88"),
                                fx_rate=Decimal("0.95"))
    assert eur_amount(tx_usd, rates) == Decimal("90.00")
    # Devise sans taux -> fallback 1 (à régler dans les Réglages).
    tx_jpy = models.Transaction(account_uid="x", external_id="z5", amount=Decimal("100"),
                                currency="JPY")
    assert eur_amount(tx_jpy, rates) == Decimal("100")


def test_link_fx_conversion(session):
    credit = session.query(models.Transaction).filter_by(external_id="u1").one()
    # On crée une conversion EUR appariée : 1000 USD -> 920 EUR.
    conv = models.Transaction(
        account_uid="eur-1", external_id="c1", booked_date=date(2026, 3, 6),
        amount=Decimal("920.00"), currency="EUR", kind="conversion",
    )
    session.add(conv)
    session.commit()

    updated = link_fx_conversion(session, credit.id, conv.id)
    assert updated.linked_conversion_id == conv.id
    assert updated.amount_eur == Decimal("920.00")
    assert updated.fx_rate == Decimal("0.920000")


# --- Tests service : P&L --------------------------------------------------


def test_monthly_pnl_twelve_months(session):
    result = monthly_pnl(session, 2026)
    assert result["year"] == 2026
    assert len(result["months"]) == 12
    assert result["months"][0]["month"] == "2026-01"
    assert result["months"][11]["month"] == "2026-12"


def test_monthly_pnl_february(session):
    result = monthly_pnl(session, 2026)
    feb = next(m for m in result["months"] if m["month"] == "2026-02")
    # Fév : produit 800, charge -300, résultat 500.
    # L'investissement (-180) et la conversion (900) sont exclus.
    assert feb["revenue_eur"] == Decimal("800.00")
    assert feb["charges_eur"] == Decimal("-300.00")
    assert feb["result_eur"] == Decimal("500.00")


def test_monthly_pnl_totals(session):
    result = monthly_pnl(session, 2026)
    # Produits : janv 500 + fév 800 + mars 900 (USD amount_eur) = 2200.
    # Charges : fév -300.
    assert result["totals"]["revenue_eur"] == Decimal("2200.00")
    assert result["totals"]["charges_eur"] == Decimal("-300.00")
    assert result["totals"]["result_eur"] == Decimal("1900.00")


# --- Tests P&L accrual (revenu = mois travaillé, pas mois payé) ------------


def _add_client(db, **kw):
    c = models.Client(code=kw.pop("code", "ACME"), legal_name="ACME", currency="EUR", **kw)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def test_pnl_counts_issued_invoice_in_service_month(session):
    # Facture émise (non encore payée) pour AVRIL, échéance juin (45j).
    client = _add_client(session)
    session.add(models.Invoice(
        number="200", client_id=client.id, month="2026-04", status="due",
        currency="EUR", amount=Decimal("2000"), amount_eur_forecast=Decimal("2000"),
        issue_date=date(2026, 4, 30), due_date=date(2026, 6, 14),
    ))
    session.commit()

    apr = next(m for m in monthly_pnl(session, 2026)["months"] if m["month"] == "2026-04")
    # Revenu reconnu en avril (mois travaillé), bien qu'encaissé plus tard.
    assert apr["revenue_eur"] == Decimal("2000.00")


def test_pnl_no_double_count_when_payment_reconciled(session):
    # Facture payée rattachée à sa transaction d'encaissement : comptée UNE fois,
    # au mois travaillé (mai), pas au mois d'encaissement (juillet).
    client = _add_client(session, code="NWH")
    inv = models.Invoice(
        number="201", client_id=client.id, month="2026-05", status="paid",
        currency="EUR", amount=Decimal("1000"), amount_eur_received=Decimal("1000"),
        issue_date=date(2026, 5, 31), due_date=date(2026, 7, 15),
        paid_date=date(2026, 7, 1),
    )
    session.add(inv)
    session.commit()
    session.refresh(inv)
    # Encaissement importé, rattaché à la facture (invoice_id) → exclu du P&L.
    session.add(models.Transaction(
        account_uid="eur-1", external_id="paid1", booked_date=date(2026, 7, 1),
        amount=Decimal("1000"), currency="EUR", kind="revenue", category_id=1,
        amount_eur=Decimal("1000"), invoice_id=inv.id,
    ))
    session.commit()

    by = {m["month"]: m for m in monthly_pnl(session, 2026)["months"]}
    assert by["2026-05"]["revenue_eur"] == Decimal("1000.00")  # facture, mois travaillé
    assert by["2026-07"]["revenue_eur"] == Decimal("0.00")     # tx rattachée exclue


# --- Tests routes ---------------------------------------------------------


def _client(session):
    from backend.api.routes.treasury import router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: session
    return TestClient(app)


def test_route_treasury(session):
    client = _client(session)
    resp = client.get("/api/treasury")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_eur"] == "8620.00"
    assert len(body["accounts"]) == 2


def test_route_pnl_default_year(session):
    client = _client(session)
    resp = client.get("/api/pnl")
    assert resp.status_code == 200
    body = resp.json()
    assert body["year"] == 2026
    assert len(body["months"]) == 12
    assert body["totals"]["result_eur"] == "1900.00"


def test_route_pnl_explicit_year(session):
    client = _client(session)
    resp = client.get("/api/pnl?year=2025")
    assert resp.status_code == 200
    body = resp.json()
    assert body["year"] == 2025
    # Aucune transaction en 2025 -> tout à zéro.
    assert body["totals"]["result_eur"] == "0.00"


# --- Régression : un compte synchronisé utilise le solde réel du provider ------


def test_synced_account_prefers_real_balance(session):
    from datetime import datetime

    # eur-1 : opening 1000 + mouvements = 2900 (reconstruction).
    acc = session.query(models.BankAccount).filter_by(account_uid="eur-1").one()
    # Le provider renvoie un solde réel différent (ex. mouvements hors fenêtre).
    acc.balance = Decimal("9999.00")
    acc.last_synced_at = datetime(2026, 6, 30)
    session.commit()

    # Vue courante → solde réel, PAS le 2900 recalculé (c'était le bug).
    res = consolidated_treasury(session)
    eur = next(a for a in res["accounts"] if a["account_uid"] == "eur-1")
    assert eur["balance"] == Decimal("9999.00")

    # Vue historique (as_of) → repasse en reconstruction opening + mouvements.
    at = consolidated_treasury(session, as_of=date(2026, 2, 28))
    eur_h = next(a for a in at["accounts"] if a["account_uid"] == "eur-1")
    assert eur_h["balance"] == Decimal("2900.00")


def test_pnl_detail_charges_by_category(session):
    """
    Lot B (clôture) : détail annuel — charges par CATÉGORIE × mois (net des
    remboursements), en plus des produits mensuels existants.
    """
    from backend.services.pnl import annual_detail

    out = annual_detail(session, 2026)
    assert len(out["months"]) == 12
    cats = {r["category"]: r for r in out["charges_by_category"]}
    # Frais (fév −300) et USD (fév −100×0.9=−90) selon le seed du module :
    assert "Frais" in cats
    row = cats["Frais"]
    assert row["total_eur"] > 0                      # magnitudes positives
    assert len(row["by_month"]) == 12
    assert sum(Decimal(str(v)) for v in row["by_month"]) == Decimal(str(row["total_eur"]))
    # Total charges du détail == total charges du P&L (cohérence).
    total = sum(Decimal(str(r["total_eur"])) for r in out["charges_by_category"])
    from backend.services.pnl import monthly_pnl
    assert total == abs(Decimal(str(monthly_pnl(session, 2026)["totals"]["charges_eur"])))
