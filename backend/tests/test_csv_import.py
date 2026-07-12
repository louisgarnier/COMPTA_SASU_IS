"""
Tests du service d'import CSV bancaire (Qonto / Revolut, historique 2025).

Fixtures synthétiques : en-têtes STRICTEMENT identiques aux exports réels,
données inventées. Les vrais fichiers (docs/docs2025/, gitignorés) ne sont
jamais lus par les tests.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db import models
from backend.db.base import Base
from backend.services import csv_import

REVOLUT_HEADER = (
    "Date started (UTC),Date completed (UTC),ID,Type,State,Description,"
    "Reference,Payer,Card number,Card label,Card state,Orig currency,"
    "Orig amount,Payment currency,Amount,Total amount,Exchange rate,Fee,"
    "Fee currency,Balance,Account,International account number,"
    "Beneficiary account number,Beneficiary sort code or routing number,"
    "Beneficiary IBAN,Beneficiary BIC,Beneficiary name,MCC,"
    "Related transaction id,Spend program,Sender account,Sender name,Card references"
)

def revolut_line(*, completed="2025-03-10", txid="rev-1", type_="CARD_PAYMENT",
                 desc="Subway", amount="-11.80", total="-11.80", fee="0.00",
                 balance="100.00", account="EUR Main",
                 iban="FR7628233000014550298993527", currency="EUR",
                 beneficiary=""):
    return (
        f"2025-03-09,{completed},{txid},{type_},COMPLETED,{desc},,Louis G,,,"
        f",{currency},{amount},{currency},{amount},{total},,{fee},{currency},"
        f"{balance},{account},{iban},,,,,{beneficiary},5814,,,,,"
    )

QONTO_HEADER = (
    "Statut;Date de la valeur (UTC);Date de la valeur (local);"
    "Date de l'opération (UTC);Date de l'opération (local);Montant total (TTC);"
    "Débit;Crédit;Solde;Devise;Montant total (TTC) (local);Devise (local);"
    "Montant total de la TVA;Montant total (HT);Montant de la TVA (0.0 %);"
    "Montant (0.0 % HT);Montant de la TVA (20.0 %);Montant (20.0 % HT);"
    "Nom du compte;IBAN du compte;Nom de la contrepartie;IBAN de la contrepartie;"
    "Méthode de paiement;Nom de la carte;Initiateur;Adresse email de l'initiateur;"
    "Équipe;Justificatif;Justificatif requis;Justificatif perdu;"
    "Identifiant de transaction;Référence;Note;Banque;ID du compte;"
    "Catégorie de trésorerie;Sous-catégorie de trésorerie"
)

def qonto_line(*, op_date="15-03-2025 10:00:00", montant="-292,79",
               solde="555,13", contrepartie="GOCARDLESS",
               txid="qo-1", reference="Neovi Expertise PRLV",
               iban="FR7616958000011078824351453"):
    return (
        f"Exécuté;{op_date};{op_date};{op_date};{op_date};{montant};;;{solde};EUR;"
        f"{montant};EUR;;{montant};;;;;Compte principal;{iban};{contrepartie};;"
        f"Prélèvement;;;;;\"\";true;false;{txid};{reference};;Qonto;{iban};;"
    )


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite:///:memory:", future=True,
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, future=True)
    s = TestSession()
    yield s
    s.close()


@pytest.fixture()
def accounts(session):
    """Comptes existants : mêmes masques que les comptes live."""
    a_eur = models.BankAccount(
        provider="revolut", account_uid="uid-rev-eur", currency="EUR",
        iban_masked="FR76****27", name="Revolut EUR",
    )
    a_qonto = models.BankAccount(
        provider="qonto", account_uid="uid-qonto", currency="EUR",
        iban_masked="FR76****53", name="Qonto",
    )
    session.add_all([a_eur, a_qonto])
    session.commit()
    return {"eur": a_eur, "qonto": a_qonto}


def test_detect_format_revolut():
    text = REVOLUT_HEADER + "\n" + revolut_line()
    assert csv_import.detect_format(text) == "revolut"


def test_detect_format_qonto():
    text = QONTO_HEADER + "\n" + qonto_line()
    assert csv_import.detect_format(text) == "qonto"


def test_detect_format_unknown_raises():
    with pytest.raises(ValueError):
        csv_import.detect_format("a,b,c\n1,2,3")


def test_parse_revolut_uses_total_amount_fee_included():
    """Le montant importé est « Total amount » (chaîne avec Balance), pas « Amount »."""
    text = REVOLUT_HEADER + "\n" + revolut_line(
        amount="-185.04", total="-186.89", fee="-1.85"
    )
    rows = csv_import.parse_csv(text)
    assert len(rows) == 1
    assert rows[0].amount == Decimal("-186.89")


def test_parse_revolut_row_fields():
    text = REVOLUT_HEADER + "\n" + revolut_line(
        completed="2025-12-30", txid="abc-123", desc="Trainline",
        amount="41.30", total="41.30", account="EUR Main",
        iban="FR7628233000014550298993527", beneficiary="Trainline SAS",
    )
    (row,) = csv_import.parse_csv(text)
    assert row.external_id == "abc-123"
    assert row.booked_date == date(2025, 12, 30)
    assert row.value_date == date(2025, 3, 9)
    assert row.currency == "EUR"
    assert row.account_name == "EUR Main"
    assert row.iban == "FR7628233000014550298993527"
    assert row.description == "Trainline"
    assert row.counterparty == "Trainline SAS"


def test_parse_qonto_french_decimals_and_dates():
    text = QONTO_HEADER + "\n" + qonto_line(
        op_date="01-07-2025 05:21:10", montant="-1 292,79", txid="qo-42"
    )
    (row,) = csv_import.parse_csv(text)
    assert row.amount == Decimal("-1292.79")
    assert row.booked_date == date(2025, 7, 1)
    assert row.external_id == "qo-42"
    assert row.currency == "EUR"
    assert row.counterparty == "GOCARDLESS"


def test_parse_qonto_nbsp_thousands_separator():
    """Séparateur de milliers en espace insécable (U+00A0) — export FR réel."""
    text = QONTO_HEADER + "\n" + qonto_line(montant="-1 292,79", txid="qo-44")
    (row,) = csv_import.parse_csv(text)
    assert row.amount == Decimal("-1292.79")


def test_parse_qonto_credit_positive():
    text = QONTO_HEADER + "\n" + qonto_line(montant="1 500,00", txid="qo-43")
    (row,) = csv_import.parse_csv(text)
    assert row.amount == Decimal("1500.00")


def test_analyze_matches_account_by_masked_iban_and_currency(session, accounts):
    text = REVOLUT_HEADER + "\n" + revolut_line(txid="r1")
    result = csv_import.analyze(session, text, year=2025)
    assert result["bank"] == "revolut"
    (acc,) = result["accounts"]
    assert acc["matched"] is True
    assert acc["account_id"] == accounts["eur"].id
    assert result["importable"] == 1


def test_analyze_unmatched_account_is_skipped_with_warning(session, accounts):
    # IBAN inconnu → aucune création de compte, lignes écartées
    text = REVOLUT_HEADER + "\n" + revolut_line(
        txid="r1", iban="GB33BUKB20201555555555"
    )
    result = csv_import.analyze(session, text, year=2025)
    assert result["importable"] == 0
    assert result["skipped_no_account"] == 1
    assert any("GB33****55" in w for w in result["warnings"])


def test_analyze_xrp_account_skipped(session, accounts):
    text = (
        REVOLUT_HEADER + "\n"
        + revolut_line(txid="r1")
        + "\n"
        + revolut_line(txid="r2", account="XRP", iban="", currency="XRP",
                       type_="EXCHANGE", amount="3000.0", total="3000.0",
                       balance="3000.0")
    )
    result = csv_import.analyze(session, text, year=2025)
    assert result["importable"] == 1
    assert result["skipped_no_account"] == 1
    assert any("XRP" in w for w in result["warnings"])


def test_analyze_filters_out_of_period(session, accounts):
    text = (
        REVOLUT_HEADER + "\n"
        + revolut_line(txid="r1", completed="2025-06-01")
        + "\n"
        + revolut_line(txid="r2", completed="2026-01-15")
    )
    result = csv_import.analyze(session, text, year=2025)
    assert result["importable"] == 1
    assert result["out_of_period"] == 1


def test_analyze_detects_existing_duplicates(session, accounts):
    session.add(models.Transaction(
        account_uid="uid-rev-eur", external_id="r1",
        booked_date=date(2025, 3, 10), amount=Decimal("-11.80"),
        currency="EUR",
    ))
    session.commit()
    text = REVOLUT_HEADER + "\n" + revolut_line(txid="r1")
    result = csv_import.analyze(session, text, year=2025)
    assert result["duplicates"] == 1
    assert result["importable"] == 0


def test_analyze_computes_opening_and_closing_balance(session, accounts):
    # Fichier antichrono (comme l'export réel) : dernier solde en premier.
    text = (
        REVOLUT_HEADER + "\n"
        + revolut_line(txid="r2", completed="2025-06-02", total="-10.00", balance="90.00")
        + "\n"
        + revolut_line(txid="r1", completed="2025-06-01", total="-20.00", balance="100.00")
    )
    result = csv_import.analyze(session, text, year=2025)
    (acc,) = result["accounts"]
    # ouverture = solde après la 1re tx chrono − son montant = 100 − (−20) = 120
    assert acc["opening_balance"] == "120.00"
    assert acc["closing_balance"] == "90.00"


def test_analyze_balance_zero_is_a_real_balance(session, accounts):
    """Un solde 0.00 sur la ligne frontière ne doit pas être ignoré (0 est falsy)."""
    text = (
        REVOLUT_HEADER + "\n"
        + revolut_line(txid="r2", completed="2025-06-02", total="-100.00", balance="0.00")
        + "\n"
        + revolut_line(txid="r1", completed="2025-06-01", total="-20.00", balance="100.00")
    )
    result = csv_import.analyze(session, text, year=2025)
    (acc,) = result["accounts"]
    assert acc["closing_balance"] == "0.00"
    assert acc["opening_balance"] == "120.00"


def test_analyze_same_day_boundary_uses_file_order(session, accounts):
    """Deux tx le même jour : l'export est antichrono, la 1re ligne du fichier
    est la plus récente → closing = son solde ; opening dérivé de la dernière ligne."""
    text = (
        REVOLUT_HEADER + "\n"
        + revolut_line(txid="aaa", completed="2025-06-01", total="-10.00", balance="70.00")
        + "\n"
        + revolut_line(txid="zzz", completed="2025-06-01", total="-20.00", balance="80.00")
    )
    result = csv_import.analyze(session, text, year=2025)
    (acc,) = result["accounts"]
    assert acc["closing_balance"] == "70.00"   # 1re ligne du fichier = la plus récente
    assert acc["opening_balance"] == "100.00"  # 80.00 − (−20.00)


def test_execute_inserts_transactions_and_categorizes(session, accounts, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        csv_import.backup_service, "create_backup",
        lambda **kw: calls.append(kw) or (tmp_path / "b.db"),
    )
    text = (
        REVOLUT_HEADER + "\n"
        + revolut_line(txid="r1", completed="2025-06-01", total="-20.00")
        + "\n"
        + revolut_line(txid="r2", completed="2026-01-15")  # hors période
    )
    report = csv_import.execute(session, text, year=2025)
    assert calls == [{"reason": "import"}]
    assert report["inserted"] == 1
    assert report["out_of_period"] == 1
    txs = session.query(models.Transaction).all()
    assert len(txs) == 1
    assert txs[0].external_id == "r1"
    assert txs[0].amount == Decimal("-20.00")
    assert txs[0].account_uid == "uid-rev-eur"


def test_execute_is_idempotent(session, accounts, monkeypatch, tmp_path):
    monkeypatch.setattr(
        csv_import.backup_service, "create_backup", lambda **kw: tmp_path / "b.db"
    )
    text = REVOLUT_HEADER + "\n" + revolut_line(txid="r1", completed="2025-06-01")
    csv_import.execute(session, text, year=2025)
    report2 = csv_import.execute(session, text, year=2025)
    assert report2["inserted"] == 0
    assert report2["duplicates"] == 1
    assert session.query(models.Transaction).count() == 1


def test_execute_does_not_touch_account_balance(session, accounts, monkeypatch, tmp_path):
    monkeypatch.setattr(
        csv_import.backup_service, "create_backup", lambda **kw: tmp_path / "b.db"
    )
    accounts["eur"].balance = Decimal("48594.25")
    session.commit()
    text = REVOLUT_HEADER + "\n" + revolut_line(txid="r1", completed="2025-06-01")
    csv_import.execute(session, text, year=2025)
    session.refresh(accounts["eur"])
    assert accounts["eur"].balance == Decimal("48594.25")
    assert accounts["eur"].last_synced_at is None


def test_execute_backup_failure_aborts(session, accounts, monkeypatch):
    def _boom(**kw):
        raise OSError("disque plein")
    monkeypatch.setattr(csv_import.backup_service, "create_backup", _boom)
    text = REVOLUT_HEADER + "\n" + revolut_line(txid="r1", completed="2025-06-01")
    with pytest.raises(OSError):
        csv_import.execute(session, text, year=2025)
    assert session.query(models.Transaction).count() == 0
