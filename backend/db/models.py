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

    is_low_rate: Mapped[Decimal] = mapped_column(RATE, default=Decimal("0.15"))
    is_threshold: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("42500"))
    is_high_rate: Mapped[Decimal] = mapped_column(RATE, default=Decimal("0.25"))

    next_invoice_number: Mapped[int] = mapped_column(Integer, default=62)
    default_fx_usd: Mapped[Decimal] = mapped_column(RATE, default=Decimal("0.92"))
    default_fx_cad: Mapped[Decimal] = mapped_column(RATE, default=Decimal("0.68"))


class Client(Base):
    """Client facturé (SWIB, NWH, ...)."""

    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String, unique=True, index=True)
    legal_name: Mapped[str] = mapped_column(String)
    address: Mapped[str] = mapped_column(Text, default="")
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    tjh: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    pay_iban: Mapped[str] = mapped_column(String, default="")
    counterparty_match: Mapped[str] = mapped_column(String, default="")

    invoices: Mapped[list["Invoice"]] = relationship(back_populates="client")
    forecast_inputs: Mapped[list["ForecastInput"]] = relationship(back_populates="client")


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
    """Facture émise."""

    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String, unique=True, index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    period_label: Mapped[str] = mapped_column(String, default="")
    period_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    hours: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    rate: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    issue_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String, default="draft")  # draft|sent|paid
    paid_transaction_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("transactions.id"), nullable=True
    )
    pdf_path: Mapped[str] = mapped_column(String, default="")
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


class ForecastInput(Base):
    """Entrée de prévision mensuelle (jours × TJH × fx par client)."""

    __tablename__ = "forecast_inputs"
    __table_args__ = (
        UniqueConstraint("month", "client_id", name="uq_month_client"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    month: Mapped[str] = mapped_column(String, index=True)  # 'YYYY-MM'
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    days: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    rate: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    fx_rate: Mapped[Decimal] = mapped_column(RATE, default=Decimal("1"))
    note: Mapped[str] = mapped_column(Text, default="")

    client: Mapped["Client"] = relationship(back_populates="forecast_inputs")
