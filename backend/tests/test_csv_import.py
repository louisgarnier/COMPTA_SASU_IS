"""
Tests du service d'import CSV bancaire (Qonto / Revolut, historique 2025).

Fixtures synthétiques : en-têtes STRICTEMENT identiques aux exports réels,
données inventées. Les vrais fichiers (docs/docs2025/, gitignorés) ne sont
jamais lus par les tests.
"""

from datetime import date
from decimal import Decimal

import pytest

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
