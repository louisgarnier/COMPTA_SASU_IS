"""
Tests Story ④ : génération de facture (forecast → due) + rendu HTML imprimable.

- SQLite en mémoire (pattern test_invoices.py).
- Génération : numéro réel, dates (issue + échéance), période, statut 'due'.
- Rendu : le HTML porte client, montant, mentions légales, IBAN, désignation h/taux.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db import models
from backend.db.base import Base
from backend.services import invoices as invoices_service


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
    try:
        yield session
    finally:
        session.close()


def _setup(db):
    db.add(models.Settings(
        id=1, company_name="SASU LGC", siret="89218975400013", naf="6202A",
        tva_intracom="FR65892189754", address="12 Place Paul Mistral, 38000 Grenoble",
        email="me@x.com", capital_eur=Decimal("100"), bank_name="Revolut Bank UAB",
        bank_bic="REVOFRP2", bank_address="Vilnius", next_invoice_number=68,
    ))
    client = models.Client(
        code="SWIB", legal_name="Alpha Financial Markets Consulting Inc.",
        address="437 Madison Ave", country="USA", currency="USD",
        billing_mode="thm", payment_terms_days=60,
        pay_iban="FR7628233000011271129737484", default_hours_per_day=Decimal("8"),
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


def _forecast_invoice(db, client):
    inv = models.Invoice(
        number="F-1-2026-05", client_id=client.id, month="2026-05", currency="USD",
        rate_unit="hour", hours=Decimal("152"), rate=Decimal("120"),
        amount=Decimal("18240"), amount_eur_forecast=Decimal("16780.80"),
        status="forecast",
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


# --------------------------------------------------------------------------- #
# Génération forecast → due                                                    #
# --------------------------------------------------------------------------- #


def test_generate_assigns_number_dates_and_due_status(db):
    client = _setup(db)
    inv = _forecast_invoice(db, client)

    out = invoices_service.generate_invoice(db, inv.id, issue_date=date(2026, 6, 1))

    assert out.status == "due"
    assert out.number == "68"                       # numéro réel du compteur
    assert out.issue_date == date(2026, 6, 1)
    assert out.due_date == date(2026, 7, 31)        # +60 jours
    assert out.period_start == date(2026, 5, 1)
    assert out.period_end == date(2026, 5, 31)
    # Compteur incrémenté
    assert db.get(models.Settings, 1).next_invoice_number == 69


def test_generate_anchors_issue_to_month_end_and_due_plus_term(db):
    """Sans issue_date : émission = fin du mois de SERVICE (pas aujourd'hui),
    échéance = fin de mois + délai client (règle métier : 45 j)."""
    client = _setup(db)
    client.payment_terms_days = 45
    db.commit()
    inv = _forecast_invoice(db, client)  # mois de service 2026-05

    out = invoices_service.generate_invoice(db, inv.id)  # issue_date=None

    assert out.issue_date == date(2026, 5, 31)
    assert out.due_date == date(2026, 7, 15)  # 31/05 + 45 j
    assert out.amount == Decimal("18240.00")  # montant inchangé


def test_generate_rejects_non_forecast(db):
    client = _setup(db)
    inv = _forecast_invoice(db, client)
    invoices_service.generate_invoice(db, inv.id, issue_date=date(2026, 6, 1))
    # Re-générer une facture déjà 'due' est refusé.
    with pytest.raises(Exception):
        invoices_service.generate_invoice(db, inv.id, issue_date=date(2026, 6, 1))


# --------------------------------------------------------------------------- #
# Rendu HTML imprimable                                                        #
# --------------------------------------------------------------------------- #


def test_render_html_contains_key_elements(db):
    client = _setup(db)
    # Nouveau modèle (2026-07-09) : le bloc bancaire vit sur la FICHE CLIENT.
    client.pay_bic = "REVOFRP2"
    db.commit()
    inv = _forecast_invoice(db, client)
    invoices_service.generate_invoice(db, inv.id, issue_date=date(2026, 6, 1))

    html = invoices_service.render_html(db, inv)

    assert "Alpha Financial Markets Consulting Inc." in html
    assert "FR7628233000011271129737484" in html          # IBAN client
    assert "REVOFRP2" in html                               # BIC fiche client
    assert "152" in html and "120" in html                 # heures @ taux
    assert "18" in html and "240" in html                  # montant
    assert "293 B" in html                                  # mention TVA
    assert "89218975400013" in html                        # SIRET
    assert "68" in html                                     # numéro
