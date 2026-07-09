"""
Tests FX réalisé — reconstitution du taux de change réellement obtenu sur les
encaissements en devise à partir des conversions Revolut appariées.

Scénario (ancre : solde devise = 0 aujourd'hui) : des encaissements en USD sont
convertis en EUR par lots. Certaines conversions anciennes convertissent du cash
d'un exercice antérieur (reliquat) et ne doivent être rattachées à aucune facture.
"""

from decimal import Decimal
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from backend.db.base import Base
from backend.db import models
from backend.services import fx_realized


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
    yield db
    db.close()


def _acc(db):
    db.add(models.Settings(id=1))
    db.add(models.FxRate(currency="USD", rate=Decimal("0.92")))
    db.add(models.FxRate(currency="CAD", rate=Decimal("0.68")))
    db.add(models.BankAccount(provider="revolut", account_uid="usd", currency="USD"))
    db.add(models.BankAccount(provider="revolut", account_uid="eur", currency="EUR"))
    db.add(models.Client(id=1, code="ACME", legal_name="Acme", currency="USD"))
    db.commit()


def _rev(db, ext, d, amount, cur="USD", invoice_id=None):
    tx = models.Transaction(
        account_uid="usd", external_id=ext, booked_date=d,
        amount=Decimal(amount), currency=cur, kind="revenue",
        invoice_id=invoice_id,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


def _conv(db, ext, d, foreign_amount, eur_amount, cur="USD"):
    """Paire de conversion : jambe devise (négative) + jambe EUR (positive)."""
    db.add(models.Transaction(
        account_uid="usd", external_id=ext + "-f", booked_date=d,
        amount=Decimal(foreign_amount), currency=cur, kind="conversion",
    ))
    db.add(models.Transaction(
        account_uid="eur", external_id=ext + "-e", booked_date=d,
        amount=Decimal(eur_amount), currency="EUR", kind="conversion",
    ))
    db.commit()


# --- Appariement des jambes de conversion --------------------------------


def test_pair_conversions_same_day_multi_currency(session):
    _acc(session)
    # Même jour : USD -1000 -> 850 EUR et CAD -2000 -> 1240 EUR.
    session.add_all([
        models.Transaction(account_uid="usd", external_id="u", booked_date=date(2026, 6, 1),
                           amount=Decimal("-1000"), currency="USD", kind="conversion"),
        models.Transaction(account_uid="usd", external_id="c", booked_date=date(2026, 6, 1),
                           amount=Decimal("-2000"), currency="CAD", kind="conversion"),
        models.Transaction(account_uid="eur", external_id="e1", booked_date=date(2026, 6, 1),
                           amount=Decimal("850"), currency="EUR", kind="conversion"),
        models.Transaction(account_uid="eur", external_id="e2", booked_date=date(2026, 6, 1),
                           amount=Decimal("1240"), currency="EUR", kind="conversion"),
    ])
    session.commit()
    pairs = fx_realized.pair_conversions(session)
    by_cur = {p["currency"]: p for p in pairs}
    # Appariement par rang de magnitude : plus grosse devise ↔ plus grosse jambe EUR.
    assert by_cur["USD"]["foreign"] == Decimal("1000")
    assert by_cur["USD"]["eur"] == Decimal("850")
    assert by_cur["CAD"]["foreign"] == Decimal("2000")
    assert by_cur["CAD"]["eur"] == Decimal("1240")


# --- Allocation à rebours -------------------------------------------------


def test_recent_income_gets_recent_rate_leftover_excluded(session):
    _acc(session)
    # Encaissements 2026 : 1000 USD (mars) + 1000 USD (juin) = 2000 USD.
    t_mar = _rev(session, "r1", date(2026, 3, 10), "1000")
    t_jun = _rev(session, "r2", date(2026, 6, 10), "1000")
    # Conversions : une ANCIENNE (janv) de 3000 USD @0.80 = cash 2025 (reliquat),
    # puis juin 2000 USD @0.86.
    _conv(session, "cJan", date(2026, 1, 5), "-3000", "2400")   # 0.80, exercice antérieur
    _conv(session, "cJun", date(2026, 6, 12), "-2000", "1720")  # 0.86, année courante

    res = fx_realized.allocate(session)

    session.refresh(t_mar)
    session.refresh(t_jun)
    # Les 2000 USD encaissés en 2026 s'apparient à la conversion de juin (0.86),
    # pas à la conversion de janvier (reliquat 2025).
    assert t_jun.amount_eur == Decimal("860.00")
    assert t_mar.amount_eur == Decimal("860.00")
    assert t_jun.fx_rate == Decimal("0.860000")
    # Le reliquat 2025 (3000 USD @0.80) n'est rattaché à aucun encaissement.
    assert res["by_currency"]["USD"]["leftover_foreign"] == Decimal("3000.00")


def test_propagates_to_paid_invoice(session):
    _acc(session)
    inv = models.Invoice(
        number="1", client_id=1, month="2026-06", currency="USD",
        amount=Decimal("1000"), amount_eur_forecast=Decimal("920"),
        status="paid",
    )
    session.add(inv)
    session.commit()
    tx = _rev(session, "r1", date(2026, 6, 10), "1000", invoice_id=inv.id)
    inv.paid_transaction_id = tx.id
    session.commit()
    _conv(session, "cJun", date(2026, 6, 12), "-1000", "860")  # 0.86

    fx_realized.allocate(session)
    session.refresh(inv)
    # Le vrai EUR encaissé (860) remplace le montant natif ; variance vs prévision.
    assert inv.amount_eur_received == Decimal("860.00")
    assert inv.variance_eur == Decimal("-60.00")  # 860 - 920


def test_report_flags_real_vs_composite(session):
    """Le rapport FX distingue taux « réel » (1 conversion) et « composé » (2+)."""
    _acc(session)
    # 2 factures USD successives : 20k (juin) puis 25k (juin, plus récente).
    inv20 = models.Invoice(number="1", client_id=1, month="2026-06", currency="USD",
                           amount=Decimal("20000"), amount_eur_forecast=Decimal("18400"), status="paid")
    inv25 = models.Invoice(number="2", client_id=1, month="2026-06", currency="USD",
                           amount=Decimal("25000"), amount_eur_forecast=Decimal("23000"), status="paid")
    session.add_all([inv20, inv25])
    session.commit()
    t20 = _rev(session, "r20", date(2026, 6, 5), "20000", invoice_id=inv20.id)
    t25 = _rev(session, "r25", date(2026, 6, 20), "25000", invoice_id=inv25.id)
    inv20.paid_transaction_id = t20.id
    inv25.paid_transaction_id = t25.id
    session.commit()
    # Conversion récente 40k @0.88 ; conversion du 1er juin (AVANT les deux
    # encaissements) : elle écoulait du cash antérieur → reliquat, pas les factures.
    _conv(session, "cLate", date(2026, 6, 25), "-40000", "35200")  # 0.88
    _conv(session, "cEarly", date(2026, 6, 1), "-5000", "4250")    # 0.85 → reliquat

    rep = fx_realized.fx_report(session)
    by_num = {r["invoice_number"]: r for r in rep["invoices"]}
    # inv25 (la plus récente) : 25k absorbés entièrement par la conversion 40k @0.88 → RÉEL.
    assert by_num["2"]["composite"] is False
    assert by_num["2"]["rate"] == Decimal("0.880000")
    # inv20 : 15k restants @0.88 + 5k NON couverts (la conv du 1er juin lui est
    # antérieure → interdite) → COMPOSÉ (2 tranches dont 1 théorique @0.92).
    assert by_num["1"]["composite"] is True
    assert len(by_num["1"]["parts"]) == 2
    assert by_num["1"]["parts"][-1]["date"] is None  # tranche théorique
    # pondéré = (15000×0.88 + 5000×0.92)/20000 = 0.89
    assert by_num["1"]["rate"] == Decimal("0.890000")
    # Sections attendues présentes ; la conv du 1er juin part en reliquat.
    assert len(rep["conversions"]) == 2
    assert rep["leftover"]["USD"] == Decimal("5000.00")


def test_income_beyond_conversions_falls_back_theoretical(session):
    _acc(session)
    # 1000 USD encaissés mais AUCUNE conversion (pas encore converti).
    tx = _rev(session, "r1", date(2026, 6, 10), "1000")
    res = fx_realized.allocate(session)
    session.refresh(tx)
    # Repli sur le taux théorique (0.92), signalé non couvert.
    assert tx.amount_eur == Decimal("920.00")
    assert res["by_currency"]["USD"]["uncovered_foreign"] == Decimal("1000.00")


def test_income_cannot_consume_conversion_older_than_itself():
    """
    Contrainte physique : une conversion ne peut écouler que des encaissements
    ANTÉRIEURS ou égaux à sa date (on ne convertit pas de l'argent pas encore
    arrivé). Sans elle, un paiement de janv N+1 « volait » les conversions de
    juin N et décalait l'EUR réel de TOUTES les factures déjà payées
    (instabilité cross-year observée : 6 factures modifiées, dont une de 2025).
    """
    from backend.services.fx_realized import _allocate_currency

    incomes = [
        {"id": 1, "foreign": Decimal("1000"), "date": date(2026, 5, 1)},   # avant la conv
        {"id": 2, "foreign": Decimal("500"), "date": date(2027, 1, 20)},   # APRÈS la conv
    ]
    convs = [{"foreign": Decimal("1500"), "rate": Decimal("0.85"), "date": date(2026, 6, 3)}]
    out = _allocate_currency(incomes, convs, Decimal("0.90"))

    # L'encaissement 2026 consomme la conversion (850) ; celui de 2027 NE PEUT
    # PAS (la conversion lui est antérieure) → repli théorique (450), non couvert.
    assert out["realized"][1]["eur"] == Decimal("850.00")
    assert out["realized"][2]["eur"] == Decimal("450.00")
    assert out["realized"][2]["parts"][0]["date"] is None  # théorique
    assert out["uncovered_foreign"] == Decimal("500.00")
    assert out["leftover_foreign"] == Decimal("500.00")   # 1500 − 1000
