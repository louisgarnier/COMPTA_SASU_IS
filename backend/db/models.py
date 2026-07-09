"""
Modèles SQLAlchemy LGC — reflètent le data model de l'architecture §4.

Conventions :
- Montants : `Numeric(18, 2)` → `Decimal` (jamais float sur l'argent).
- Taux de change : `Numeric(18, 6)`.
- Devises : ISO 3 lettres ('EUR', 'USD', 'CAD').
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base

# Précisions réutilisables
MONEY = Numeric(18, 2)
RATE = Numeric(18, 6)


class Settings(Base):
    """Paramètres société (table singleton, id=1)."""

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    company_name: Mapped[str] = mapped_column(String, default="")
    siret: Mapped[str] = mapped_column(String, default="")
    naf: Mapped[str] = mapped_column(String, default="")
    tva_intracom: Mapped[str] = mapped_column(String, default="")
    address: Mapped[str] = mapped_column(Text, default="")
    email: Mapped[str] = mapped_column(String, default="")
    capital_eur: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("100"))

    # Bloc bancaire — DÉPRÉCIÉ (2026-07-09) : le bloc de réception vit désormais
    # sur la fiche client (pay_bic/pay_bank_name/pay_bank_address). Colonnes
    # conservées dormantes (migrations additives uniquement).
    bank_name: Mapped[str] = mapped_column(String, default="")
    bank_bic: Mapped[str] = mapped_column(String, default="")
    bank_address: Mapped[str] = mapped_column(Text, default="")
    # Mention légale imprimée sur la facture (ex. franchise en base art. 293 B) —
    # paramétrable, plus de texte en dur dans le template.
    invoice_legal_mention: Mapped[str] = mapped_column(
        Text, default="TVA non applicable, art. 293 B du CGI."
    )

    is_low_rate: Mapped[Decimal] = mapped_column(RATE, default=Decimal("0.15"))
    is_threshold: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("42500"))
    is_high_rate: Mapped[Decimal] = mapped_column(RATE, default=Decimal("0.25"))

    # Poche distribuable initiale : stock accumulé AVANT le 1er exercice IS
    # (ère IR / pré-app). Le RAN des exercices IS se CHAÎNE ensuite tout seul
    # (nets des exercices − distributions versées) — cf. pnl.retained_earnings.
    retained_earnings_eur: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    # Exercice de début du régime IS (ex. 2026). Avant : régime IR → IS estimé
    # nul et exercices exclus du chaînage du RAN. NULL = tout est à l'IS.
    is_start_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    next_invoice_number: Mapped[int] = mapped_column(Integer, default=62)


class Client(Base):
    """Client facturé (SWIB, NWH, ...)."""

    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String, unique=True, index=True)
    legal_name: Mapped[str] = mapped_column(String)
    # Adresse structurée (facturation internationale) : rue en libre, puis
    # ville / état-région / code postal composés « Toronto, ON M5J 2P1 ».
    address: Mapped[str] = mapped_column(Text, default="")
    city: Mapped[str] = mapped_column(String, default="")
    state_region: Mapped[str] = mapped_column(String, default="")
    postal_code: Mapped[str] = mapped_column(String, default="")
    country: Mapped[str] = mapped_column(String, default="")
    contact_name: Mapped[str] = mapped_column(String, default="")
    email: Mapped[str] = mapped_column(String, default="")
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    tjh: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    # Mode de facturation : 'tjm' (taux journalier) | 'thm' (taux horaire).
    billing_mode: Mapped[str] = mapped_column(String, default="tjm")
    default_hours_per_day: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("8"))
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=45)
    # Bloc bancaire de RÉCEPTION par client (décision 2026-07-09) : l'IBAN est
    # par compte devise, le BIC/banque/adresse banque l'accompagnent — la fiche
    # client est autonome (tout ce qui s'imprime sur sa facture est ici).
    pay_iban: Mapped[str] = mapped_column(String, default="")
    pay_bic: Mapped[str] = mapped_column(String, default="")
    pay_bank_name: Mapped[str] = mapped_column(String, default="")
    pay_bank_address: Mapped[str] = mapped_column(Text, default="")
    counterparty_match: Mapped[str] = mapped_column(String, default="")

    invoices: Mapped[list["Invoice"]] = relationship(back_populates="client")


class BankAccount(Base):
    """Compte bancaire connecté (Revolut, Qonto)."""

    __tablename__ = "bank_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String)  # 'revolut' | 'qonto'
    account_uid: Mapped[str] = mapped_column(String, unique=True, index=True)
    currency: Mapped[str] = mapped_column(String(3))
    iban_masked: Mapped[str] = mapped_column(String, default="")
    name: Mapped[str] = mapped_column(String, default="")
    balance: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    opening_balance: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    opening_balance_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account")


class OpeningBalance(Base):
    """
    Solde d'ouverture d'exercice — saisi depuis le relevé officiel de fin d'année.

    Ancre la reconstruction de trésorerie : le solde au 1er janvier d'un exercice
    est le solde de clôture au 31/12 de l'exercice précédent, repris du relevé.
    Ré-ancrer chaque année corrige la dérive cumulée (arrondis FX, flux manquants).

    Clé (account_uid, year) — `year` = exercice **ouvert** : le solde vaut au
    01/01/`year` (= 31/12/`year`-1). Pure donnée, aucune valeur en dur dans le code :
    l'utilisateur la saisit via Réglages → Soldes d'ouverture d'exercice.
    """

    __tablename__ = "opening_balances"
    __table_args__ = (
        UniqueConstraint("account_uid", "year", name="uq_opening_account_year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_uid: Mapped[str] = mapped_column(
        ForeignKey("bank_accounts.account_uid"), index=True
    )
    year: Mapped[int] = mapped_column(Integer, index=True)  # exercice ouvert
    balance: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    note: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )


class Category(Base):
    """Catégorie de transaction (arbre optionnel)."""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, index=True)
    # 'revenue' | 'charge' | 'conversion' | 'transfer' | 'internal' | 'uncategorized'
    type: Mapped[str] = mapped_column(String)
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("categories.id"), nullable=True
    )
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)

    rules: Mapped[list["CategoryRule"]] = relationship(back_populates="category")


class CategoryRule(Base):
    """Règle de catégorisation (contrepartie / description → catégorie)."""

    __tablename__ = "category_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_field: Mapped[str] = mapped_column(String)  # 'counterparty' | 'description'
    pattern: Mapped[str] = mapped_column(String)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    priority: Mapped[int] = mapped_column(Integer, default=100)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    category: Mapped["Category"] = relationship(back_populates="rules")


class Transaction(Base):
    """Transaction bancaire importée."""

    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("account_uid", "external_id", name="uq_account_external"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_uid: Mapped[str] = mapped_column(
        ForeignKey("bank_accounts.account_uid"), index=True
    )
    external_id: Mapped[str] = mapped_column(String, index=True)
    booked_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    value_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    amount: Mapped[Decimal] = mapped_column(MONEY)
    currency: Mapped[str] = mapped_column(String(3))
    description: Mapped[str] = mapped_column(Text, default="")
    counterparty: Mapped[str] = mapped_column(String, default="")
    category_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("categories.id"), nullable=True
    )
    # 'revenue' | 'charge' | 'conversion' | 'transfer' | 'investment' | 'other'
    kind: Mapped[str] = mapped_column(String, default="other")
    fx_rate: Mapped[Optional[Decimal]] = mapped_column(RATE, nullable=True)
    amount_eur: Mapped[Optional[Decimal]] = mapped_column(MONEY, nullable=True)
    linked_conversion_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("transactions.id"), nullable=True
    )
    invoice_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("invoices.id"), nullable=True
    )
    raw_json: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    account: Mapped["BankAccount"] = relationship(back_populates="transactions")
    category: Mapped[Optional["Category"]] = relationship()


class Invoice(Base):
    """
    Facture — objet unique parcourant le cycle de vie `forecast → due → paid`.

    Fusion de l'ancien `forecast_inputs` : une prévision de CA EST une facture
    prévisionnelle (`status='forecast'`, `month` renseigné, sans numéro réel).
    À la génération elle passe `due` (numéro, dates), au paiement `paid`
    (transaction rapprochée, montant reçu, taux réel, variance).
    """

    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String, unique=True, index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))

    # Période / rattachement mensuel (source anti-doublon : client × month).
    month: Mapped[str] = mapped_column(String, default="", index=True)  # 'YYYY-MM'
    period_label: Mapped[str] = mapped_column(String, default="")
    period_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Assiette de facturation (à l'heure : hours = days × hours_per_day).
    days: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    hours_per_day: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("8"))
    hours: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    rate: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    # Unité du taux : 'day' (montant = jours × taux) | 'hour' (= heures × taux).
    rate_unit: Mapped[str] = mapped_column(String, default="day")
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    note: Mapped[str] = mapped_column(Text, default="")

    # Prévisionnel (taux théorique).
    fx_rate_forecast: Mapped[Decimal] = mapped_column(RATE, default=Decimal("1"))
    amount_eur_forecast: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))

    # Génération.
    issue_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String, default="forecast")  # forecast|due|paid
    pdf_path: Mapped[str] = mapped_column(String, default="")

    # Rapprochement / paiement (réel).
    paid_transaction_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("transactions.id"), nullable=True
    )
    paid_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    amount_received: Mapped[Optional[Decimal]] = mapped_column(MONEY, nullable=True)
    fx_rate: Mapped[Optional[Decimal]] = mapped_column(RATE, nullable=True)
    amount_eur_received: Mapped[Optional[Decimal]] = mapped_column(MONEY, nullable=True)
    variance_eur: Mapped[Optional[Decimal]] = mapped_column(MONEY, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    client: Mapped["Client"] = relationship(back_populates="invoices")


class Investment(Base):
    """Placement (crypto, bourse, ...) — suivi valeur d'ouverture / courante."""

    __tablename__ = "investments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)  # crypto|bourse|placement|autre
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    opening_value: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    opening_value_eur: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    current_value: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    current_value_eur: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    as_of_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")


class FxRate(Base):
    """Taux de change théorique devise → EUR (éditable dans les Réglages)."""

    __tablename__ = "fx_rates"

    currency: Mapped[str] = mapped_column(String(3), primary_key=True)  # 'USD', 'CAD'…
    rate: Mapped[Decimal] = mapped_column(RATE, default=Decimal("1"))  # 1 unité devise = ? EUR
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )


class BalanceDocument(Base):
    """Justificatif officiel de solde (relevé PDF/image) stocké en local."""

    __tablename__ = "balance_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_uid: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    label: Mapped[str] = mapped_column(String, default="")
    doc_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    filename: Mapped[str] = mapped_column(String)
    file_path: Mapped[str] = mapped_column(String)
    content_type: Mapped[str] = mapped_column(String, default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# Note : l'ancien modèle `ForecastInput` (table `forecast_inputs`) a été fusionné
# dans `Invoice` (status='forecast'). La table physique éventuelle est laissée
# dormante en base locale ; plus aucun code ne la lit ni ne l'écrit.
