from decimal import Decimal
from datetime import date
from backend.services import statement_extract as se

# Texte linéarisé représentatif d'un « Relevé des soldes » Revolut (extrait réel anonymisé).
REVOLUT_TEXT = """Relevé des soldes
Relevé généré le 23 mars 2026
Informations en date du 31 décembre 2025 (UTC)
Main
Devise EUR
Type International
IBAN FR76 2823 3000 0145 5029 8993 527
Solde réglé
€11 626.90
Main
Devise USD
IBAN FR76 2823 3000 0145 5029 8993 527
Solde réglé
$80 381.99
USD
Devise USD
IBAN FR76 2823 3000 0112 7112 9737 484
Solde réglé
$40 320.00
Louis CAD
Devise CAD
IBAN FR76 2823 3000 0145 5029 8993 527
Solde réglé
5 580.00 CAD
XRP
Devise XRP
Solde réglé
3 000.000000
"""


def test_revolut_as_of_date():
    out = se.extract_revolut_balances(REVOLUT_TEXT)
    assert out["as_of"] == date(2025, 12, 31)


def test_revolut_balances_by_account():
    out = se.extract_revolut_balances(REVOLUT_TEXT)
    by = {(b["currency"], b["iban_last4"]): b["amount"] for b in out["balances"]}
    assert by[("EUR", "3527")] == Decimal("11626.90")
    assert by[("USD", "3527")] == Decimal("80381.99")
    assert by[("USD", "7484")] == Decimal("40320.00")
    assert by[("CAD", "3527")] == Decimal("5580.00")
    # XRP : pas d'IBAN → clé (XRP, None), montant à 6 décimales
    xrp = [b for b in out["balances"] if b["currency"] == "XRP"][0]
    assert xrp["amount"] == Decimal("3000.000000")
    assert xrp["iban_last4"] is None


# Deux comptes consécutifs, SANS ligne « titre » entre eux : la ligne de montant du
# premier compte (« €100.00 ») est immédiatement suivie de la ligne « Devise » du
# second compte. Le détecteur de « ligne titre » ne doit pas confondre le montant
# avec un nom de compte.
REVOLUT_TEXT_NO_TITLE_BETWEEN = """Relevé des soldes
Relevé généré le 23 mars 2026
Informations en date du 31 décembre 2025 (UTC)
Main
Devise EUR
IBAN FR76 2823 3000 0145 5029 8993 527
Solde réglé
€100.00
Devise USD
IBAN FR76 2823 3000 0112 7112 9737 484
Solde réglé
$200.00
"""


def test_revolut_amount_line_not_mistaken_for_account_name():
    out = se.extract_revolut_balances(REVOLUT_TEXT_NO_TITLE_BETWEEN)
    balances = out["balances"]
    assert len(balances) == 2
    second = balances[1]
    # Le nom du second compte ne doit JAMAIS être une chaîne de montant qui a fuité
    # depuis le solde du compte précédent.
    assert second["name"] != "€100.00"
    assert not str(second["name"]).lstrip().startswith(("€", "$", "£"))
