"""
Tests d'INVARIANTS inter-modules — issus de l'audit structurel du 2026-07.

Chaque test encode une cohérence que plusieurs modules doivent respecter
ENSEMBLE (là où les tests unitaires valident chaque module isolément) :

1. Frontière d'exercice fiscal : une facture de prestation N payée en N+1
   impacte le P&L de N (au FX réel encaissé) et JAMAIS celui de N+1 ;
   le cash, lui, apparaît au cashflow de N+1.
2. P&L d'un exercice == Σ factures émises de l'exercice + filet des revenus
   non facturés encaissés dans l'exercice (pas de double comptage).
3. Machine à états gardée : pas de transition de statut par PATCH,
   pas de re-rapprochement d'une facture payée, pas d'unreconcile d'une
   facture non payée.
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.routes.invoices import router as invoices_router
from backend.db import models
from backend.db.base import Base, get_db
from backend.services import invoices as invoices_service
from backend.services.cashflow import monthly_cashflow
from backend.services.pnl import summary

_TODAY = date(2026, 7, 7)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    _seed(session)
    try:
        yield session
    finally:
        session.close()


def _seed(db):
    db.add(models.Settings(id=1, next_invoice_number=100))
    db.add(models.FxRate(currency="USD", rate=Decimal("0.90")))
    db.add(models.BankAccount(provider="revolut", account_uid="ACC", currency="USD"))
    db.add(models.Client(id=1, code="SWIB", legal_name="Swib", currency="USD"))
    db.add(models.Category(id=1, name="Prestations", type="revenue"))
    db.commit()


def _invoice_2025_paid_in_2026(db):
    """
    Facture nov 2025 (16 320 USD) payée par une transaction de janv 2026,
    convertie ensuite par une vraie conversion Revolut (2 jambes, même date) :
    16 320 USD → 13 964,59 EUR (taux réel ≈ 0.855674, ≠ théorique 0.90).
    `allocate` (relancé au rapprochement) déduira l'EUR réel de ces jambes.
    """
    tx = models.Transaction(
        account_uid="ACC", external_id="pay-56", booked_date=date(2026, 1, 23),
        amount=Decimal("16320"), currency="USD", kind="revenue", category_id=1,
    )
    conv_usd = models.Transaction(
        account_uid="ACC", external_id="cv-usd", booked_date=date(2026, 2, 5),
        amount=Decimal("-16320"), currency="USD", kind="conversion",
    )
    conv_eur = models.Transaction(
        account_uid="ACC", external_id="cv-eur", booked_date=date(2026, 2, 5),
        amount=Decimal("13964.59"), currency="EUR", kind="conversion",
    )
    inv = models.Invoice(
        number="56", client_id=1, month="2025-11", status="due",
        currency="USD", amount=Decimal("16320"),
        amount_eur_forecast=Decimal("14361.60"),
        issue_date=date(2025, 11, 30), due_date=date(2026, 1, 14),
    )
    db.add_all([tx, conv_usd, conv_eur, inv])
    db.commit()
    db.refresh(tx)
    db.refresh(inv)
    return inv, tx


# --------------------------------------------------------------------------- #
# 1. Frontière d'exercice fiscal (LE cœur de l'app)                            #
# --------------------------------------------------------------------------- #


def test_invoice_of_year_n_paid_in_n1_hits_pnl_n_only(db):
    inv, tx = _invoice_2025_paid_in_2026(db)
    invoices_service.manual_reconcile(db, inv.id, tx.id)

    p25 = summary(db, 2025)
    p26 = summary(db, 2026)
    # 2025 : le CA au FX RÉEL encaissé (pas le prévisionnel, pas le natif).
    assert p25["revenue_eur"] == Decimal("13964.59")
    # 2026 : RIEN — la transaction est rattachée, le filet ne la compte pas.
    assert p26["revenue_eur"] == Decimal("0.00")


def test_cash_of_that_payment_shows_in_cashflow_n1(db):
    inv, tx = _invoice_2025_paid_in_2026(db)
    invoices_service.manual_reconcile(db, inv.id, tx.id)

    cf26 = monthly_cashflow(db, 2026, today=_TODAY)
    jan = next(m for m in cf26["months"] if m["month"] == "2026-01")
    # Le CASH apparaît bien en 2026 (vue caisse), au FX réel.
    assert jan["incoming_eur"] == Decimal("13964.59")


def test_unreconciled_payment_pollutes_wrong_year_documented(db):
    """
    Gap B2 documenté : tant que la transaction N+1 n'est PAS rapprochée, elle
    entre au P&L N+1 par le filet (caisse) PENDANT que la facture `due` compte
    en N — double comptage transitoire inter-exercices. Ce test fige le
    comportement actuel pour le rendre visible ; si on le corrige un jour,
    ce test doit être mis à jour en conséquence.
    """
    _invoice_2025_paid_in_2026(db)  # due non rapprochée + tx libre
    p25 = summary(db, 2025)
    p26 = summary(db, 2026)
    assert p25["revenue_eur"] == Decimal("14361.60")  # facture due (prévisionnel)
    # Le filet compte la tx libre au taux THÉORIQUE (16320×0.90) — double peine :
    # mauvais exercice ET mauvais taux, tant que le rapprochement n'est pas fait.
    assert p26["revenue_eur"] == Decimal("14688.00")


# --------------------------------------------------------------------------- #
# 2. P&L == Σ factures + filet (pas de double comptage)                        #
# --------------------------------------------------------------------------- #


def test_pnl_equals_invoices_plus_unlinked_net(db):
    inv, tx = _invoice_2025_paid_in_2026(db)
    invoices_service.manual_reconcile(db, inv.id, tx.id)
    # Un revenu non facturé encaissé en 2026 (EUR, pour ne pas perturber
    # l'allocation FX) : compte via le filet.
    db.add(models.Transaction(
        account_uid="ACC", external_id="misc", booked_date=date(2026, 6, 9),
        amount=Decimal("346.68"), currency="EUR", kind="revenue", category_id=1,
    ))
    db.commit()

    p26 = summary(db, 2026)
    # 346.68 (filet) — et RIEN d'autre (la facture 2025 payée en 2026 est exclue).
    assert p26["revenue_eur"] == Decimal("346.68")


def test_unlinked_revenue_uses_realized_eur_when_known(db):
    """
    Le filet « revenus non facturés » valorise au FX RÉEL (`tx.amount_eur`,
    posé par l'allocation) quand il existe — pas au taux théorique.
    Cas réel : indemnité client +346,68 CAD convertie avec le reste du solde.
    """
    db.add(models.Transaction(
        account_uid="ACC", external_id="indemnity", booked_date=date(2026, 6, 9),
        amount=Decimal("346.68"), currency="USD", kind="revenue", category_id=1,
        amount_eur=Decimal("296.65"),  # EUR réel alloué (≠ 346.68×0.90=312.01)
    ))
    db.commit()
    p26 = summary(db, 2026)
    assert p26["revenue_eur"] == Decimal("296.65")


def test_charges_and_revenue_are_netted_of_refunds(db):
    """
    Décision produit 2026-07 : le P&L intègre TOUS les montants, + et −.
    Un remboursement (+) sur une catégorie charge vient en déduction des
    charges ; un avoir client (−) en déduction du CA (filet).
    """
    chg = models.Category(id=2, name="Frais", type="charge")
    db.add(chg)
    # Charge −100, puis remboursement +30 (ex. « Refund from Hotelcom »).
    db.add(models.Transaction(
        account_uid="ACC", external_id="c1", booked_date=date(2026, 3, 5),
        amount=Decimal("-100"), currency="EUR", kind="charge", category_id=2,
    ))
    db.add(models.Transaction(
        account_uid="ACC", external_id="c2", booked_date=date(2026, 4, 2),
        amount=Decimal("30"), currency="EUR", kind="charge", category_id=2,
    ))
    # Revenu non facturé +500, puis avoir client −50.
    db.add(models.Transaction(
        account_uid="ACC", external_id="r1", booked_date=date(2026, 5, 1),
        amount=Decimal("500"), currency="EUR", kind="revenue", category_id=1,
    ))
    db.add(models.Transaction(
        account_uid="ACC", external_id="r2", booked_date=date(2026, 5, 20),
        amount=Decimal("-50"), currency="EUR", kind="revenue", category_id=1,
    ))
    db.commit()

    p26 = summary(db, 2026)
    assert p26["charges_eur"] == Decimal("70.00")   # 100 − 30 (net)
    assert p26["revenue_eur"] == Decimal("450.00")  # 500 − 50 (net)


def test_retained_earnings_chains_across_years(db):
    """
    Report à nouveau AUTOMATIQUE (décision 2026-07) : en exercice N, le RAN =
    base initiale + Σ résultats nets des exercices < N − distributions versées.
    Le résultat de N-1 reste dans la société tant que le cash n'est pas sorti.
    """
    db.add(models.Category(id=5, name="Dividendes dirigeant", type="distribution"))
    # Exercice 2025 : facture payée 1000 € (aucune charge) → résultat 1000,
    # IS 15 % (sous le seuil) = 150 → net 850.
    inv = models.Invoice(number="1", client_id=1, month="2025-11", status="paid",
                         currency="EUR", amount=Decimal("1000"),
                         amount_eur_received=Decimal("1000"), paid_date=date(2026, 1, 10))
    db.add(inv)
    db.commit()
    db.add(models.Transaction(
        account_uid="ACC", external_id="p1", booked_date=date(2026, 1, 10),
        amount=Decimal("1000"), currency="EUR", kind="revenue", category_id=1,
        invoice_id=inv.id,
    ))
    # Distribution de 300 € versée en 2026 (catégorie type 'distribution').
    db.add(models.Transaction(
        account_uid="ACC", external_id="div1", booked_date=date(2026, 5, 2),
        amount=Decimal("-300"), currency="EUR", kind="transfer", category_id=5,
    ))
    db.commit()

    from backend.services.pnl import retained_earnings

    # 2026 : RAN = net 2025 (850) — la distribution 2026 ne compte que pour 2027.
    assert retained_earnings(db, 2026) == Decimal("850.00")
    # 2027 : RAN = net 2025 (850) + net 2026 (0, pas de résultat) − 300 versés = 550.
    assert retained_earnings(db, 2027) == Decimal("550.00")
    # La distribution n'est PAS une charge : P&L 2026 sans charges.
    s26 = summary(db, 2026)
    assert s26["charges_eur"] == Decimal("0.00")
    # « Déjà versé » de l'exercice exposé + reste distribuable net.
    assert s26["distributed_this_year_eur"] == Decimal("300.00")
    assert s26["remaining_distributable_eur"] == s26["distributable_eur"] - Decimal("300.00")


def test_is_regime_start_year_excludes_prior_years(db):
    """
    Régime réel de l'utilisateur : IS à partir de 2026, 2025 était à l'IR.
    - P&L d'un exercice AVANT le début IS : IS estimé = 0 (imposé à l'IR, hors société).
    - Le chaînage du RAN ignore ces exercices : RAN 2027 = poche initiale
      + net 2026 − distributions versées. La poche (166 200) est soldée par les
      versements 2026 → RAN 2027 = net 2026 exactement.
    """
    st = db.get(models.Settings, 1)
    st.is_start_year = 2026
    st.retained_earnings_eur = Decimal("400")  # poche pré-IS (ère IR)
    db.add(models.Category(id=5, name="Distribution dirigeant", type="distribution"))
    # Facture 2025 (ère IR) payée en 2026 : visible au P&L 2025 mais SANS IS,
    # et exclue du chaînage RAN.
    inv25 = models.Invoice(number="1", client_id=1, month="2025-11", status="paid",
                           currency="EUR", amount=Decimal("1000"),
                           amount_eur_received=Decimal("1000"), paid_date=date(2026, 1, 10))
    # Facture 2026 (ère IS) payée : résultat 2026 = 2000 → IS 15 % = 300 → net 1700.
    inv26 = models.Invoice(number="2", client_id=1, month="2026-03", status="paid",
                           currency="EUR", amount=Decimal("2000"),
                           amount_eur_received=Decimal("2000"), paid_date=date(2026, 4, 10))
    db.add_all([inv25, inv26])
    db.commit()
    for ext, d, amt, inv_id in (("p1", date(2026, 1, 10), "1000", inv25.id),
                                ("p2", date(2026, 4, 10), "2000", inv26.id)):
        db.add(models.Transaction(
            account_uid="ACC", external_id=ext, booked_date=d,
            amount=Decimal(amt), currency="EUR", kind="revenue", category_id=1,
            invoice_id=inv_id,
        ))
    # Sortie de la poche pré-IS en 2026 : 400 versés (catégorie distribution).
    db.add(models.Transaction(
        account_uid="ACC", external_id="div", booked_date=date(2026, 6, 1),
        amount=Decimal("-400"), currency="EUR", kind="transfer", category_id=5,
    ))
    db.commit()

    from backend.services.pnl import retained_earnings

    s25 = summary(db, 2025)
    assert s25["is_estimate_eur"] == Decimal("0.00")      # régime IR : pas d'IS société
    assert s25["is_regime"] == "IR"
    assert s25["net_result_eur"] == Decimal("1000.00")    # net = résultat (pas d'IS)

    # RAN 2026 = poche seule (2025 exclu du chaînage).
    assert retained_earnings(db, 2026) == Decimal("400.00")
    # RAN 2027 = poche 400 + net 2026 (1700) − versés 400 = net 2026.
    assert retained_earnings(db, 2027) == Decimal("1700.00")


# --------------------------------------------------------------------------- #
# 3. Machine à états gardée                                                    #
# --------------------------------------------------------------------------- #


@pytest.fixture
def client(db):
    app = FastAPI()
    app.include_router(invoices_router)
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_patch_cannot_change_status(client, db):
    inv, _ = _invoice_2025_paid_in_2026(db)
    # due → forecast interdit (dé-génération silencieuse = trou de numérotation).
    resp = client.patch(f"/api/invoices/{inv.id}", json={"status": "forecast"})
    assert resp.status_code == 409


def test_reconcile_already_paid_is_rejected(db):
    inv, tx = _invoice_2025_paid_in_2026(db)
    invoices_service.manual_reconcile(db, inv.id, tx.id)
    other = models.Transaction(
        account_uid="ACC", external_id="pay-x", booked_date=date(2026, 2, 1),
        amount=Decimal("16320"), currency="USD", kind="revenue",
    )
    db.add(other)
    db.commit()
    db.refresh(other)
    # Re-rapprocher une facture déjà payée → 409 (sinon transaction fantôme).
    with pytest.raises(HTTPException) as e:
        invoices_service.manual_reconcile(db, inv.id, other.id)
    assert e.value.status_code == 409


def test_unreconcile_non_paid_is_rejected(db):
    inv, _ = _invoice_2025_paid_in_2026(db)  # due, jamais payée
    with pytest.raises(HTTPException) as e:
        invoices_service.unreconcile(db, inv.id)
    assert e.value.status_code == 409
