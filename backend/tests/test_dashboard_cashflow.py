"""
Tests du domaine Cashflow (encaissements/décaissements mensuels par devise).

- SQLite en mémoire (pattern test_forecast.py).
- Passé/mois en cours → réel (transactions). Futur → prévision (forecast).
- Réf. today = 2026-07-03 : Jan–Juin écoulés, Juillet en cours, Août+ futurs.
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

from backend.api.routes.dashboard_cashflow import router as cashflow_router
from backend.db import models
from backend.db.base import Base, get_db
from backend.services import cashflow as cashflow_service
from backend.services import forecast as forecast_service

_TODAY = date(2026, 7, 3)  # Jan–Juin écoulés, Juil en cours, Août+ futurs


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


def _base(db):
    """Compte + catégories + taux USD théorique 0.9."""
    db.add(models.BankAccount(provider="revolut", account_uid="ACC", currency="EUR"))
    rev = models.Category(name="Ventes", type="revenue")
    chg = models.Category(name="Charges", type="charge")
    db.add_all([rev, chg])
    db.add(models.FxRate(currency="USD", rate=Decimal("0.9")))
    db.commit()
    db.refresh(rev)
    db.refresh(chg)
    return rev, chg


def _tx(db, cat_id, d, amount, currency, kind, ext):
    db.add(
        models.Transaction(
            account_uid="ACC",
            external_id=ext,
            booked_date=d,
            amount=Decimal(str(amount)),
            currency=currency,
            kind=kind,
            category_id=cat_id,
        )
    )
    db.commit()


def _by_month(result):
    return {m["month"]: m for m in result["months"]}


# --------------------------------------------------------------------------- #
# Service : mois passés = réel par devise                                      #
# --------------------------------------------------------------------------- #


def test_past_months_real_incoming_outgoing_by_currency(db_session):
    rev, chg = _base(db_session)
    # Janvier : encaissements EUR 1000 + USD 2000 (→ 1800 EUR).
    _tx(db_session, rev.id, date(2026, 1, 10), "1000", "EUR", "revenue", "r1")
    _tx(db_session, rev.id, date(2026, 1, 20), "2000", "USD", "revenue", "r2")
    # Février : décaissements EUR -300 + USD -100 (→ 90 EUR magnitude).
    _tx(db_session, chg.id, date(2026, 2, 5), "-300", "EUR", "charge", "c1")
    _tx(db_session, chg.id, date(2026, 2, 15), "-100", "USD", "charge", "c2")

    result = cashflow_service.monthly_cashflow(db_session, 2026, today=_TODAY)
    by = _by_month(result)

    jan = by["2026-01"]
    assert jan["is_forecast"] is False
    assert jan["incoming_by_ccy"] == {"EUR": Decimal("1000.00"), "USD": Decimal("1800.00")}
    assert jan["incoming_eur"] == Decimal("2800.00")
    assert jan["outgoing_by_ccy"] == {}
    assert jan["outgoing_eur"] == Decimal("0.00")

    feb = by["2026-02"]
    assert feb["is_forecast"] is False
    assert feb["outgoing_by_ccy"] == {"EUR": Decimal("300.00"), "USD": Decimal("90.00")}
    assert feb["outgoing_eur"] == Decimal("390.00")
    assert feb["incoming_by_ccy"] == {}


def test_totals_sum_over_year(db_session):
    rev, chg = _base(db_session)
    _tx(db_session, rev.id, date(2026, 1, 10), "1000", "EUR", "revenue", "r1")
    _tx(db_session, chg.id, date(2026, 2, 5), "-300", "EUR", "charge", "c1")

    result = cashflow_service.monthly_cashflow(db_session, 2026, today=_TODAY)
    totals = result["totals"]
    # Incoming : 1000 réel (Jan), aucune prévision → 1000.
    assert totals["incoming_eur"] == Decimal("1000.00")
    # Outgoing : 300 réel (Fév) + prorata du mois COURANT (juillet, moyenne 300/6=50
    # sur les 29 jours restants du 03/07 : 50×29/31 = 46,77) + 5 mois futurs
    # (Août–Déc) à 50 = 250. Total = 300 + 46,77 + 250 = 596,77.
    assert totals["outgoing_eur"] == Decimal("596.77")
    assert totals["net_eur"] == Decimal("403.23")


# --------------------------------------------------------------------------- #
# Break B — mois passés : EUR réellement encaissé, pas le taux théorique       #
# --------------------------------------------------------------------------- #


def test_past_month_uses_realized_amount_eur_not_theoretical(db_session):
    """
    Un encaissement en devise avec `amount_eur` figé (conversion réelle Revolut)
    doit compter au montant EUR RÉEL, pas natif × taux théorique des Réglages.
    """
    rev, _chg = _base(db_session)
    # 2000 USD encaissés, mais réellement convertis à 1700 € (≠ 2000×0.9 = 1800).
    db_session.add(models.Transaction(
        account_uid="ACC", external_id="r-real", booked_date=date(2026, 1, 20),
        amount=Decimal("2000"), currency="USD", kind="revenue", category_id=rev.id,
        amount_eur=Decimal("1700.00"),
    ))
    db_session.commit()

    by = _by_month(cashflow_service.monthly_cashflow(db_session, 2026, today=_TODAY))
    jan = by["2026-01"]
    # Réel 1700, PAS 1800 théorique.
    assert jan["incoming_by_ccy"] == {"USD": Decimal("1700.00")}
    assert jan["incoming_eur"] == Decimal("1700.00")


def test_flows_are_netted_of_refunds(db_session):
    """Un remboursement (+) sur charge réduit les sorties du mois (net)."""
    rev, chg = _base(db_session)
    _tx(db_session, chg.id, date(2026, 2, 5), "-100", "EUR", "charge", "c1")
    _tx(db_session, chg.id, date(2026, 2, 18), "30", "EUR", "charge", "c2")  # refund

    by = _by_month(cashflow_service.monthly_cashflow(db_session, 2026, today=_TODAY))
    feb = by["2026-02"]
    assert feb["outgoing_by_ccy"] == {"EUR": Decimal("70.00")}  # 100 − 30
    assert feb["outgoing_eur"] == Decimal("70.00")


# --------------------------------------------------------------------------- #
# Break C — mois courant : réel déjà encaissé + attendu restant                #
# --------------------------------------------------------------------------- #


def test_current_month_combines_real_and_expected(db_session):
    """
    Le mois EN COURS doit additionner le réel déjà encaissé et l'attendu restant
    (factures non encore payées dont l'échéance tombe ce mois-ci).
    """
    rev, _chg = _base(db_session)
    # Réel déjà encaissé en juillet (mois courant) : 900 € (USD converti).
    db_session.add(models.Transaction(
        account_uid="ACC", external_id="r-jul", booked_date=date(2026, 7, 1),
        amount=Decimal("1000"), currency="USD", kind="revenue", category_id=rev.id,
        amount_eur=Decimal("900.00"),
    ))
    # Facture émise non payée, échéance 15/07 → attendue ce mois-ci : 3000 €.
    client = models.Client(code="NWH", legal_name="NWH", currency="EUR", payment_terms_days=45)
    db_session.add(client)
    db_session.commit()
    db_session.refresh(client)
    db_session.add(models.Invoice(
        number="200", client_id=client.id, month="2026-05", status="due",
        currency="EUR", amount=Decimal("3000"), amount_eur_forecast=Decimal("3000"),
        issue_date=date(2026, 5, 31), due_date=date(2026, 7, 15),
    ))
    db_session.commit()

    by = _by_month(cashflow_service.monthly_cashflow(db_session, 2026, today=_TODAY))
    jul = by["2026-07"]
    assert jul["is_forecast"] is False
    # 900 réel encaissé + 3000 attendu (facture due) = combinés.
    assert jul["incoming_by_ccy"] == {"EUR": Decimal("3000.00"), "USD": Decimal("900.00")}
    assert jul["incoming_eur"] == Decimal("3900.00")
    # Ventilation exposée : la part ATTENDUE (non encaissée) est identifiable,
    # pour l'afficher pâle et ne pas la compter en « Réel » côté front.
    assert jul["incoming_expected_by_ccy"] == {"EUR": Decimal("3000.00")}
    assert jul["incoming_expected_eur"] == Decimal("3000.00")

    # Mois passé : aucune part attendue.
    jan = by["2026-01"]
    assert jan["incoming_expected_eur"] == Decimal("0.00")
    # Mois futur : tout est attendu (cohérent avec is_forecast=True).
    aou = by["2026-08"]
    assert aou["incoming_expected_eur"] == aou["incoming_eur"]


# --------------------------------------------------------------------------- #
# Vue fiscale : ventilation prior-year + débordement année suivante            #
# --------------------------------------------------------------------------- #


def test_prior_year_receipts_are_flagged_per_month(db_session):
    """Un encaissement 2026 d'une facture 2025 est marqué `prior` (vue fiscale)."""
    rev, _ = _base(db_session)
    client = models.Client(code="SWIB", legal_name="Swib", currency="USD")
    db_session.add(client)
    db_session.commit()
    db_session.refresh(client)
    inv25 = models.Invoice(number="56", client_id=client.id, month="2025-11",
                           status="paid", currency="USD", amount=Decimal("16320"),
                           amount_eur_received=Decimal("13964.59"),
                           paid_date=date(2026, 1, 23))
    db_session.add(inv25)
    db_session.commit()
    db_session.add(models.Transaction(
        account_uid="ACC", external_id="p56", booked_date=date(2026, 1, 23),
        amount=Decimal("16320"), currency="USD", kind="revenue", category_id=rev.id,
        amount_eur=Decimal("13964.59"), invoice_id=inv25.id,
    ))
    db_session.commit()

    by = _by_month(cashflow_service.monthly_cashflow(db_session, 2026, today=_TODAY))
    jan = by["2026-01"]
    assert jan["incoming_by_ccy"] == {"USD": Decimal("13964.59")}          # vue caisse
    assert jan["incoming_prior_by_ccy"] == {"USD": Decimal("13964.59")}    # marqué prior
    # Vue fiscale (front) : incoming − prior = 0 pour janvier.


def test_year_invoice_paid_next_year_lands_in_overflow(db_session):
    """Facture déc 2026 encaissée (ou attendue) début 2027 → bucket `overflow`."""
    _base(db_session)
    client = models.Client(code="NWH", legal_name="NWH", currency="CAD",
                           payment_terms_days=45)
    db_session.add(client)
    db_session.commit()
    db_session.refresh(client)
    # Émise, non payée : service déc 2026, échéance 14/02/2027 → hors barres 2026.
    db_session.add(models.Invoice(
        number="80", client_id=client.id, month="2026-12", status="due",
        currency="CAD", amount=Decimal("30000"), amount_eur_forecast=Decimal("18600"),
        issue_date=date(2026, 12, 31), due_date=date(2027, 2, 14),
    ))
    db_session.commit()

    out = cashflow_service.monthly_cashflow(db_session, 2026, today=_TODAY)
    # Absente des 12 mois (cash 2027)…
    assert all(m["incoming_by_ccy"] == {} or "CAD" not in m["incoming_by_ccy"]
               for m in out["months"])
    # …mais présente dans le débordement fiscal (attendu).
    assert out["overflow"]["expected_by_ccy"] == {"CAD": Decimal("18600.00")}
    assert out["overflow"]["real_by_ccy"] == {}


# --------------------------------------------------------------------------- #
# Service : mois futurs = prévision                                           #
# --------------------------------------------------------------------------- #


def test_future_incoming_bucketed_on_expected_payment_date(db_session):
    """
    L'encaissement d'une prévision de septembre à 45j tombe en NOVEMBRE
    (fin sept + 45j ≈ 14 nov), pas en septembre → cœur du modèle accrual/cash.
    """
    rev, chg = _base(db_session)
    # Charges écoulées → moyenne mensuelle des 6 mois = 600/6 = 100.
    _tx(db_session, chg.id, date(2026, 1, 20), "-600", "EUR", "charge", "c1")

    client = models.Client(
        code="SWIB", legal_name="SWIB", currency="USD", payment_terms_days=45
    )
    db_session.add(client)
    db_session.commit()
    db_session.refresh(client)
    forecast_service.upsert_inputs(
        db_session,
        [{"month": "2026-09", "client_id": client.id, "days": Decimal("10"),
          "rate": Decimal("500"), "fx_rate": Decimal("0.9"), "note": ""}],
    )

    by = _by_month(cashflow_service.monthly_cashflow(db_session, 2026, today=_TODAY))

    # Septembre (mois travaillé) : AUCUN encaissement — l'argent n'arrive pas encore.
    sep = by["2026-09"]
    assert sep["is_forecast"] is True
    assert sep["incoming_by_ccy"] == {}
    # Charges prévisionnelles futures = moyenne des mois écoulés, bucket EUR.
    assert sep["outgoing_by_ccy"] == {"EUR": Decimal("100.00")}

    # Novembre : le cash de la presta de septembre (10 × 500 × 0.9 = 4500 USD-EUR).
    nov = by["2026-11"]
    assert nov["incoming_by_ccy"] == {"USD": Decimal("4500.00")}
    assert nov["incoming_eur"] == Decimal("4500.00")


def test_due_invoice_bucketed_on_due_date(db_session):
    """Une facture émise (`due`) apparaît au cashflow le mois de son `due_date`."""
    _base(db_session)
    client = models.Client(
        code="NWH", legal_name="NWH", currency="EUR", payment_terms_days=45
    )
    db_session.add(client)
    db_session.commit()
    db_session.refresh(client)
    # Émise, non payée : service août, échéance 2026-10-01 → cash en octobre.
    db_session.add(models.Invoice(
        number="100", client_id=client.id, month="2026-08", status="due",
        currency="EUR", amount=Decimal("3000"),
        issue_date=date(2026, 8, 18), due_date=date(2026, 10, 1),
    ))
    db_session.commit()

    by = _by_month(cashflow_service.monthly_cashflow(db_session, 2026, today=_TODAY))
    assert by["2026-10"]["incoming_by_ccy"] == {"EUR": Decimal("3000.00")}
    assert by["2026-08"]["incoming_by_ccy"] == {}


# --------------------------------------------------------------------------- #
# Route : GET /api/dashboard/cashflow                                         #
# --------------------------------------------------------------------------- #


@pytest.fixture
def client_app(db_session):
    app = FastAPI()
    app.include_router(cashflow_router)
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def test_route_get_cashflow(client_app, db_session):
    rev, _chg = _base(db_session)
    _tx(db_session, rev.id, date(2026, 1, 10), "1000", "EUR", "revenue", "r1")

    resp = client_app.get("/api/dashboard/cashflow", params={"year": 2026})
    assert resp.status_code == 200
    data = resp.json()
    assert data["year"] == 2026
    assert len(data["months"]) == 12
    jan = {m["month"]: m for m in data["months"]}["2026-01"]
    assert jan["incoming_by_ccy"] == {"EUR": "1000.00"}
    assert data["totals"]["incoming_eur"] == "1000.00"


# --------------------------------------------------------------------------- #
# Sélecteur de certitude : scope = realized | engaged | forecast               #
# --------------------------------------------------------------------------- #


def _scope_fixture(db_session):
    """1 facture due (échéance oct) + 1 prévision (sept→nov) + charges réelles."""
    rev, chg = _base(db_session)
    client = models.Client(code="SWIB", legal_name="Swib", currency="USD",
                           payment_terms_days=45)
    db_session.add(client)
    db_session.commit()
    db_session.refresh(client)
    # Charge réelle passée (janvier).
    _tx(db_session, chg.id, date(2026, 1, 20), "-600", "EUR", "charge", "c1")
    # Facture ÉMISE : échéance 2026-10-01 → attendue en octobre.
    db_session.add(models.Invoice(
        number="10", client_id=client.id, month="2026-08", status="due",
        currency="USD", amount=Decimal("2000"), amount_eur_forecast=Decimal("1800"),
        issue_date=date(2026, 8, 18), due_date=date(2026, 10, 1),
    ))
    db_session.commit()
    # PRÉVISION septembre : encaissement attendu mi-novembre (fin sept + 45 j).
    forecast_service.upsert_inputs(db_session, [
        {"month": "2026-09", "client_id": client.id, "rate_unit": "day",
         "days": Decimal("10"), "rate": Decimal("500"), "note": ""},
    ])


def test_scope_realized_shows_no_expected_flows(db_session):
    _scope_fixture(db_session)
    out = cashflow_service.monthly_cashflow(db_session, 2026, today=_TODAY, scope="realized")
    by = {m["month"]: m for m in out["months"]}
    # Aucun encaissement attendu, aucune charge projetée : futur éteint.
    assert by["2026-10"]["incoming_eur"] == Decimal("0.00")
    assert by["2026-11"]["incoming_eur"] == Decimal("0.00")
    assert by["2026-09"]["outgoing_eur"] == Decimal("0.00")  # pas de moyenne projetée


def test_scope_engaged_shows_due_only_no_projected_charges(db_session):
    _scope_fixture(db_session)
    out = cashflow_service.monthly_cashflow(db_session, 2026, today=_TODAY, scope="engaged")
    by = {m["month"]: m for m in out["months"]}
    # La facture ÉMISE apparaît à son échéance…
    assert by["2026-10"]["incoming_by_ccy"] == {"USD": Decimal("1800.00")}
    # …la PRÉVISION non générée n'apparaît pas…
    assert by["2026-11"]["incoming_eur"] == Decimal("0.00")
    # …et pas de charges projetées.
    assert by["2026-09"]["outgoing_eur"] == Decimal("0.00")


def test_scope_forecast_is_current_behavior(db_session):
    _scope_fixture(db_session)
    out = cashflow_service.monthly_cashflow(db_session, 2026, today=_TODAY, scope="forecast")
    by = {m["month"]: m for m in out["months"]}
    assert by["2026-10"]["incoming_by_ccy"] == {"USD": Decimal("1800.00")}
    assert by["2026-11"]["incoming_by_ccy"] == {"USD": Decimal("4500.00")}  # prévision
    assert by["2026-09"]["outgoing_eur"] > Decimal("0")  # charges projetées (moyenne)


def test_nonop_outflows_exposed_separately(db_session):
    """
    Audit v2 : dividendes / IS payé / investissements sont de VRAIES sorties de
    cash absentes des barres (vue opérationnelle). Le backend les expose dans
    `outgoing_nonop_*` pour que le front puisse les afficher sur demande.
    """
    rev, chg = _base(db_session)
    dist = models.Category(name="Dividendes", type="distribution")
    invst = models.Category(name="Investissement", type="internal")
    db_session.add_all([dist, invst])
    db_session.commit()
    _tx(db_session, chg.id, date(2026, 2, 5), "-100", "EUR", "charge", "c1")
    _tx(db_session, dist.id, date(2026, 2, 10), "-500", "EUR", "transfer", "d1")
    _tx(db_session, invst.id, date(2026, 3, 1), "-2000", "EUR", "investment", "i1")

    by = _by_month(cashflow_service.monthly_cashflow(db_session, 2026, today=_TODAY))
    feb, mar = by["2026-02"], by["2026-03"]
    # Les barres opérationnelles restent inchangées…
    assert feb["outgoing_eur"] == Decimal("100.00")
    # …et le non-opérationnel est exposé à part (magnitude positive).
    assert feb["outgoing_nonop_by_ccy"] == {"EUR": Decimal("500.00")}
    assert mar["outgoing_nonop_eur"] == Decimal("2000.00")


def test_expected_investment_redemption_in_forecast_inflows(db_session):
    """
    Remboursement de placement attendu : encaissement EUR au mois d'échéance en
    scope prévisionnel uniquement (part « attendue »), rien une fois clôturé
    ni dans les scopes réalisé/engagé.
    """
    _base(db_session)
    db_session.add(models.Investment(
        label="K Technologie", type="bourse", currency="EUR",
        opening_value_eur=Decimal("69600"), current_value_eur=Decimal("77000"),
        expected_value_eur=Decimal("76300"), expected_month="2026-12",
    ))
    db_session.commit()

    by = _by_month(cashflow_service.monthly_cashflow(db_session, 2026, today=_TODAY, scope="forecast"))
    dec = by["2026-12"]
    # Entrée NON-OP (symétrique de la sortie initiale vers le placement) :
    # jamais dans les entrées opérationnelles.
    assert dec["incoming_nonop_by_ccy"].get("EUR") == Decimal("76300.00")
    assert dec["incoming_nonop_eur"] == Decimal("76300.00")
    assert "EUR" not in dec["incoming_by_ccy"]

    by_eng = _by_month(cashflow_service.monthly_cashflow(db_session, 2026, today=_TODAY, scope="engaged"))
    assert by_eng["2026-12"]["incoming_nonop_eur"] == Decimal("0.00")

    # Clôturé → plus d'attendu (le réel a pris le relais).
    inv = db_session.query(models.Investment).first()
    inv.closed_date = _TODAY
    db_session.commit()
    by2 = _by_month(cashflow_service.monthly_cashflow(db_session, 2026, today=_TODAY, scope="forecast"))
    assert by2["2026-12"]["incoming_nonop_eur"] == Decimal("0.00")


def test_real_nonop_inflow_lands_in_incoming_nonop(db_session):
    """
    Un encaissement réel non-op (remboursement de placement catégorisé
    « Investissement ») va dans incoming_nonop — jamais en sortie négative ni
    dans les entrées opérationnelles.
    """
    rev, chg = _base(db_session)
    inv_cat = models.Category(name="Investissement", type="internal")
    db_session.add(inv_cat)
    db_session.commit()
    _tx(db_session, inv_cat.id, date(2026, 6, 15), "76300", "EUR", "investment", "redemp1")
    _tx(db_session, inv_cat.id, date(2026, 6, 10), "-70000", "EUR", "investment", "out1")

    by = _by_month(cashflow_service.monthly_cashflow(db_session, 2026, today=_TODAY))
    juin = by["2026-06"]
    assert juin["incoming_nonop_by_ccy"].get("EUR") == Decimal("76300.00")
    assert juin["outgoing_nonop_by_ccy"].get("EUR") == Decimal("70000.00")
    assert "EUR" not in juin["incoming_by_ccy"]


def test_fiscal_nonop_attribution(db_session):
    """
    Vue fiscale — rattachement à l'exercice :
    - placements : tous les flux datés de l'exercice (achat ET remboursement) ;
    - distributions : seul l'excédent au-delà du pool des exercices antérieurs
      (poche Réglages) s'affiche, au mois du virement, virement à cheval scindé ;
    - IS payé : pool N-1 pré-IS = 0 → tout paiement IS de l'exercice est un
      acompte de l'exercice, visible en fiscal.
    """
    rev, chg = _base(db_session)
    dist = models.Category(name="Dividendes", type="distribution")
    invc = models.Category(name="Investissement", type="internal")
    ispay = models.Category(name="IS payé", type="is_payment")
    db_session.add_all([dist, invc, ispay])
    # Poche pré-IS = pool distribuable des exercices antérieurs : 100 000.
    db_session.add(models.Settings(id=1, retained_earnings_eur=Decimal("100000"),
                                   is_start_year=2026))
    db_session.commit()

    # Distributions 2026 : 60 000 (mars) puis 70 000 (mai) → cumul 130 000.
    # Pool 100 000 → mars entièrement 2025 (masqué), mai à cheval : 30 000 en fiscal.
    _tx(db_session, dist.id, date(2026, 3, 10), "-60000", "EUR", "transfer", "d1")
    _tx(db_session, dist.id, date(2026, 5, 10), "-70000", "EUR", "transfer", "d2")
    # Placement acheté en juin : visible en fiscal tel quel.
    _tx(db_session, invc.id, date(2026, 6, 10), "-70000", "EUR", "investment", "p1")
    # IS payé en avril (pool N-1 = 0, exercice 2025 pré-IS) : tout en fiscal.
    _tx(db_session, ispay.id, date(2026, 4, 15), "-5000", "EUR", "transfer", "i1")

    by = _by_month(cashflow_service.monthly_cashflow(db_session, 2026, today=_TODAY))

    # Caisse : tout apparaît aux mois réels.
    assert by["2026-03"]["outgoing_nonop_by_ccy"].get("EUR") == Decimal("60000.00")
    assert by["2026-05"]["outgoing_nonop_by_ccy"].get("EUR") == Decimal("70000.00")
    # Fiscal : mars masqué, mai scindé (30 000), placement + IS entiers.
    assert "EUR" not in by["2026-03"]["outgoing_nonop_fiscal_by_ccy"]
    assert by["2026-05"]["outgoing_nonop_fiscal_by_ccy"].get("EUR") == Decimal("30000.00")
    assert by["2026-06"]["outgoing_nonop_fiscal_by_ccy"].get("EUR") == Decimal("70000.00")
    assert by["2026-04"]["outgoing_nonop_fiscal_by_ccy"].get("EUR") == Decimal("5000.00")

    # Somme fiscale des distributions == « acomptes sur l'exercice » du P&L
    # (versé 130 000 − pool 100 000 = 30 000) : cohérence structurelle.
    total_dist_fiscal = sum(
        Decimal(str(m["outgoing_nonop_fiscal_eur"])) for m in by.values()
    ) - Decimal("70000") - Decimal("5000")
    assert total_dist_fiscal == Decimal("30000.00")


def test_fiscal_nonop_includes_expected_redemption(db_session):
    """Le remboursement de placement attendu apparaît aussi en vue fiscale."""
    _base(db_session)
    db_session.add(models.Settings(id=1))
    db_session.add(models.Investment(
        label="K", type="bourse", currency="EUR",
        opening_value_eur=Decimal("69600"),
        expected_value_eur=Decimal("76300"), expected_month="2026-12",
    ))
    db_session.commit()
    by = _by_month(cashflow_service.monthly_cashflow(db_session, 2026, today=_TODAY, scope="forecast"))
    assert by["2026-12"]["incoming_nonop_fiscal_eur"] == Decimal("76300.00")
