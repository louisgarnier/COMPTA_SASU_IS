from decimal import Decimal
from datetime import date
from backend.services import statement_extract as se

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from backend.db.base import Base
from backend.db import models

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


def _db():
    engine = create_engine("sqlite:///:memory:", future=True,
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, future=True)()
    db.add_all([
        models.BankAccount(provider="revolut", account_uid="u-eur", currency="EUR",
                           iban_masked="FR76****527", name="LGC"),
        models.BankAccount(provider="revolut", account_uid="u-usd-main", currency="USD",
                           iban_masked="FR76****527", name="LGC"),
        models.BankAccount(provider="revolut", account_uid="u-usd-2", currency="USD",
                           iban_masked="FR76****484", name="LGC"),
    ])
    db.commit()
    return db


def test_map_by_currency_and_iban_last4():
    db = _db()
    extracted = [
        {"name": "Main", "currency": "USD", "iban_last4": "3527", "amount": Decimal("80381.99")},
        {"name": "USD", "currency": "USD", "iban_last4": "7484", "amount": Decimal("40320.00")},
    ]
    out = {r["account_uid"]: r for r in se.map_to_accounts(db, extracted)}
    # iban_masked se termine par 527 → last4 "3527" doit matcher "…527"
    assert out["u-usd-main"]["amount"] == Decimal("80381.99")
    assert out["u-usd-2"]["amount"] == Decimal("40320.00")
    assert all(r["matched"] for r in out.values())


def test_map_unmatched_currency_flagged():
    db = _db()
    extracted = [{"name": "XRP", "currency": "XRP", "iban_last4": None, "amount": Decimal("3000")}]
    out = se.map_to_accounts(db, extracted)
    assert out[0]["matched"] is False
    assert out[0]["account_uid"] is None


QONTO_PDF_TEXT = """Relevés de compte
Du 01/01/2025 au 31/01/2025
LGC
IBAN: FR76 1695 8000 0110 7882 4351 453
BIC: QNTOFRP1XXX
Solde au 01/01 + 315.48 EUR
Entrées + 4000.00 EUR
Sorties - 296.39 EUR
Solde au 31/01 + 4019.09 EUR
Date de valeur Transactions Débit Crédit
"""


def test_qonto_pdf_takes_closing_balance_not_opening():
    out = se.extract_qonto_pdf_month_end(QONTO_PDF_TEXT)
    assert len(out) == 1
    # clôture 31/01, pas l'ouverture 01/01 (315.48)
    assert out[0]["amount"] == Decimal("4019.09")
    assert out[0]["currency"] == "EUR"
    assert out[0]["iban_last4"] == "1453"


def test_qonto_pdf_negative_balance():
    text = QONTO_PDF_TEXT.replace("Solde au 31/01 + 4019.09 EUR", "Solde au 31/01 - 12.50 EUR")
    out = se.extract_qonto_pdf_month_end(text)
    assert out[0]["amount"] == Decimal("-12.50")


def test_qonto_pdf_empty_when_no_period():
    assert se.extract_qonto_pdf_month_end("un texte sans en-tête de période") == []


def test_iban_tail_ignores_fr76_prefix_on_two_digit_mask():
    # Régression : les IBAN Enable Banking réels sont masqués à 2 chiffres
    # « FR76****27 ». _iban_tail doit rendre « 27 » (chiffres après le masque),
    # pas « 627 » (bug : derniers chiffres de « 7627 » ré-agrégeant le préfixe).
    assert se._iban_tail("FR76****27") == "27"
    assert se._iban_tail("FR76****527") == "527"
    assert se._iban_tail("") is None
    assert se._iban_tail(None) is None


def _db_live_masks():
    """Structure réelle : masque 2 chiffres, plusieurs comptes par devise, IBAN Revolut partagé."""
    engine = create_engine("sqlite:///:memory:", future=True,
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, future=True)()
    db.add_all([
        models.BankAccount(provider="qonto", account_uid="q-eur", currency="EUR",
                           iban_masked="FR76****53", name="lgc"),
        models.BankAccount(provider="revolut", account_uid="r-eur", currency="EUR",
                           iban_masked="FR76****27", name="LGC"),
        models.BankAccount(provider="revolut", account_uid="r-usd", currency="USD",
                           iban_masked="FR76****27", name="LGC"),
        models.BankAccount(provider="revolut", account_uid="r-gbp", currency="GBP",
                           iban_masked="FR76****27", name="LGC"),
        models.BankAccount(provider="revolut", account_uid="r-usd2", currency="USD",
                           iban_masked="FR76****84", name="LGC"),
        models.BankAccount(provider="revolut", account_uid="r-eur2", currency="EUR",
                           iban_masked="", name="LGC"),
    ])
    db.commit()
    return db


def test_map_two_digit_mask_shared_iban_maps_to_primary_account():
    # Tous les sous-comptes Revolut partagent l'IBAN « …527 » (last4 « 3527 ») ;
    # le mapping doit viser le compte principal « ****27 » de chaque devise,
    # malgré plusieurs comptes de même devise (repli « unique » impossible).
    db = _db_live_masks()
    extracted = [
        {"name": "Main", "currency": "EUR", "iban_last4": "3527", "amount": Decimal("117013.40")},
        {"name": "Main", "currency": "USD", "iban_last4": "3527", "amount": Decimal("17280.00")},
        {"name": "Main", "currency": "GBP", "iban_last4": "3527", "amount": Decimal("0.00")},
    ]
    out = se.map_to_accounts(db, extracted)
    assert all(r["matched"] for r in out), out
    by_uid = {r["account_uid"]: r["amount"] for r in out}
    assert by_uid["r-eur"] == Decimal("117013.40")
    assert by_uid["r-usd"] == Decimal("17280.00")  # pas r-usd2 (****84)
    assert by_uid["r-gbp"] == Decimal("0.00")
