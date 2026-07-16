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


QONTO_CSV = (
    "Statut;Date de la valeur (local);Montant total (TTC);Débit;Crédit;Solde;Devise;"
    "Nom du compte;IBAN du compte\n"
    "Exécuté;15-02-2025;1000,00;;1000,00;5000,00;EUR;Compte principal;FR7616958000011078824351453\n"
    "Exécuté;27-02-2025;-200,00;200,00;;4800,00;EUR;Compte principal;FR7616958000011078824351453\n"
    "Exécuté;03-03-2025;-50,00;50,00;;4750,00;EUR;Compte principal;FR7616958000011078824351453\n"
)


def test_qonto_month_end_takes_last_solde_of_month():
    out = se.extract_qonto_month_end(QONTO_CSV, 2025, 2)
    assert len(out) == 1
    assert out[0]["currency"] == "EUR"
    assert out[0]["iban_last4"] == "1453"
    assert out[0]["amount"] == Decimal("4800.00")  # solde du 27/02, dernière op de févr


def test_qonto_month_end_empty_when_no_op():
    assert se.extract_qonto_month_end(QONTO_CSV, 2025, 1) == []


# Export réel Qonto/Revolut : antichrono (plus récent en premier). Le jour de
# clôture (28/02, dernier jour du mois cible) a DEUX lignes avec des soldes
# différents : la 1re ligne du fichier est la plus récente (bon solde), la 2e
# ligne du fichier est une opération plus ancienne du même jour (mauvais solde
# si on se contente d'un tie-break "dernière ligne vue gagne").
QONTO_CSV_ANTICHRONO_SAME_DAY_TIE = (
    "Statut;Date de la valeur (local);Montant total (TTC);Débit;Crédit;Solde;Devise;"
    "Nom du compte;IBAN du compte\n"
    "Exécuté;28-02-2025;-100,00;100,00;;4700,00;EUR;Compte principal;FR7616958000011078824351453\n"
    "Exécuté;28-02-2025;1000,00;;1000,00;4800,00;EUR;Compte principal;FR7616958000011078824351453\n"
    "Exécuté;15-02-2025;1000,00;;1000,00;5000,00;EUR;Compte principal;FR7616958000011078824351453\n"
)


def test_qonto_month_end_antichrono_same_day_tie_keeps_most_recent():
    out = se.extract_qonto_month_end(QONTO_CSV_ANTICHRONO_SAME_DAY_TIE, 2025, 2)
    assert len(out) == 1
    # La ligne la plus récente est la 1re du fichier (antichrono) : solde 4700,00.
    # Un tie-break naïf "d >= prev" écraserait avec 4800,00 (2e ligne, même jour,
    # mais opération plus ancienne).
    assert out[0]["amount"] == Decimal("4700.00")


# Même cas, mais fichier chrono (plus ancien en premier) — doit continuer à
# fonctionner : la dernière ligne du fichier pour le jour de clôture est la
# plus récente.
QONTO_CSV_CHRONO_SAME_DAY_TIE = (
    "Statut;Date de la valeur (local);Montant total (TTC);Débit;Crédit;Solde;Devise;"
    "Nom du compte;IBAN du compte\n"
    "Exécuté;15-02-2025;1000,00;;1000,00;5000,00;EUR;Compte principal;FR7616958000011078824351453\n"
    "Exécuté;28-02-2025;1000,00;;1000,00;4800,00;EUR;Compte principal;FR7616958000011078824351453\n"
    "Exécuté;28-02-2025;-100,00;100,00;;4700,00;EUR;Compte principal;FR7616958000011078824351453\n"
)


def test_qonto_month_end_chrono_same_day_tie_keeps_most_recent():
    out = se.extract_qonto_month_end(QONTO_CSV_CHRONO_SAME_DAY_TIE, 2025, 2)
    assert len(out) == 1
    # Fichier chrono : la dernière ligne (3e) est la plus récente → 4700,00.
    assert out[0]["amount"] == Decimal("4700.00")
