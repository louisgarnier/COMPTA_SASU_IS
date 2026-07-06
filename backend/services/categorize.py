"""
Moteur de catégorisation par règles LGC.

Une transaction est catégorisée en confrontant ses champs `counterparty` /
`description` aux `CategoryRule` actives, triées par `priority` croissante.
La première règle qui matche gagne (substring insensible à la casse). En
l'absence de match, la transaction tombe dans la catégorie système
« À catégoriser » (type 'uncategorized').

Fonctions publiques :
- `apply_rules(db, transaction)` → category_id du premier match, sinon None.
- `categorize_transaction(db, transaction)` → pose category_id (match ou fallback).
- `recategorize_all(db)` → rejoue sur toutes les transactions, renvoie le nb modifiés.
- `seed_default_categories_and_rules(db)` → amorce catégories + règles système.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db import models
from backend.logging_config import get_logger

logger = get_logger("categorize", channel="backend")

# Nom + type de la catégorie fourre-tout (fallback).
UNCATEGORIZED_NAME = "À catégoriser"
UNCATEGORIZED_TYPE = "uncategorized"

# Correspondance type de catégorie → `Transaction.kind` (vocabulaire du filtre « Type »).
# Les deux vocabulaires coïncident sauf 'internal' (catégorie) ↔ 'investment' (kind).
_TYPE_TO_KIND = {
    "revenue": "revenue",
    "charge": "charge",
    "conversion": "conversion",
    "transfer": "transfer",
    "internal": "investment",
    "uncategorized": "other",
}


def kind_for_category_type(category_type: Optional[str]) -> str:
    """Dérive le `kind` d'une transaction depuis le type de sa catégorie."""
    return _TYPE_TO_KIND.get(category_type or "", "other")

# Catégories système par défaut : (name, type).
DEFAULT_CATEGORIES: list[tuple[str, str]] = [
    ("Revenus SWIB", "revenue"),
    ("Revenus NWH", "revenue"),
    ("URSSAF", "charge"),
    ("Retraite AG2R", "charge"),
    ("Prélèvement GoCardless", "charge"),
    ("Impôts DGFIP", "charge"),
    ("Outils/SaaS", "charge"),
    ("Repas", "charge"),
    ("Frais bancaires", "charge"),
    ("Conversion FX", "conversion"),
    ("Virement interne", "transfer"),
    ("Investissement", "internal"),
    (UNCATEGORIZED_NAME, UNCATEGORIZED_TYPE),
]

# Règles par défaut : (priority, match_field, pattern, nom de catégorie cible).
DEFAULT_RULES: list[tuple[int, str, str, str]] = [
    (10, "counterparty", "URSSAF", "URSSAF"),
    (20, "counterparty", "AG2R", "Retraite AG2R"),
    (30, "counterparty", "GOCARDLESS", "Prélèvement GoCardless"),
    (40, "counterparty", "DGFIP", "Impôts DGFIP"),
    (50, "description", "REVOLUT", "Conversion FX"),
]


def _field_value(transaction: models.Transaction, match_field: str) -> str:
    """Retourne la valeur du champ ciblé par une règle ('counterparty'|'description')."""
    if match_field == "counterparty":
        return transaction.counterparty or ""
    if match_field == "description":
        return transaction.description or ""
    # Champ inconnu → aucune valeur, la règle ne matchera jamais.
    return ""


def apply_rules(db: Session, transaction: models.Transaction) -> Optional[int]:
    """
    Confronte la transaction aux règles actives (priorité croissante).

    Retourne le `category_id` de la première règle dont le `pattern` apparaît
    (substring, insensible à la casse) dans le champ ciblé ; None si aucune.
    """
    rules = (
        db.execute(
            select(models.CategoryRule)
            .where(models.CategoryRule.enabled.is_(True))
            .order_by(models.CategoryRule.priority.asc(), models.CategoryRule.id.asc())
        )
        .scalars()
        .all()
    )
    for rule in rules:
        haystack = _field_value(transaction, rule.match_field).lower()
        needle = (rule.pattern or "").lower()
        if needle and needle in haystack:
            return rule.category_id
    return None


def get_or_create_uncategorized(db: Session) -> models.Category:
    """Retourne la catégorie fourre-tout système, en la créant si absente."""
    cat = db.execute(
        select(models.Category).where(
            models.Category.name == UNCATEGORIZED_NAME,
            models.Category.type == UNCATEGORIZED_TYPE,
        )
    ).scalar_one_or_none()
    if cat is None:
        cat = models.Category(
            name=UNCATEGORIZED_NAME, type=UNCATEGORIZED_TYPE, is_system=True
        )
        db.add(cat)
        db.commit()
        db.refresh(cat)
        logger.info("🗄️ [Categorize] create: catégorie fourre-tout « %s »", UNCATEGORIZED_NAME)
    return cat


def categorize_transaction(db: Session, transaction: models.Transaction) -> int:
    """
    Pose `transaction.category_id` selon les règles, sinon fourre-tout.

    Ne commit pas : l'appelant décide du commit (batch ou unitaire).
    Retourne le category_id appliqué.
    """
    category_id = apply_rules(db, transaction)
    if category_id is None:
        category_id = get_or_create_uncategorized(db).id
    transaction.category_id = category_id
    # Dérive `kind` du type de la catégorie (alimente le filtre « Type »).
    category = db.get(models.Category, category_id)
    transaction.kind = kind_for_category_type(category.type if category else None)
    return category_id


def recategorize_all(db: Session) -> int:
    """
    Rejoue la catégorisation sur toutes les transactions.

    Retourne le nombre de transactions dont le `category_id` a changé.
    """
    transactions = db.execute(select(models.Transaction)).scalars().all()
    changed = 0
    for tx in transactions:
        before = tx.category_id
        after = categorize_transaction(db, tx)
        if before != after:
            changed += 1
    db.commit()
    logger.info("📤 [Categorize] recategorize_all: %d transaction(s) modifiée(s) ✅", changed)
    return changed


def seed_default_categories_and_rules(db: Session) -> None:
    """
    Amorce catégories + règles système si les tables sont vides.

    Idempotent au sens « ne fait rien si déjà peuplé » : on ne réinsère pas si
    au moins une catégorie (resp. règle) existe déjà.
    """
    has_categories = db.execute(select(models.Category.id).limit(1)).first() is not None
    if not has_categories:
        for name, ctype in DEFAULT_CATEGORIES:
            db.add(models.Category(name=name, type=ctype, is_system=True))
        db.commit()
        logger.info(
            "🗄️ [Categorize] seed: %d catégories système créées", len(DEFAULT_CATEGORIES)
        )

    # Index nom → id pour rattacher les règles.
    by_name = {
        c.name: c.id
        for c in db.execute(select(models.Category)).scalars().all()
    }

    has_rules = db.execute(select(models.CategoryRule.id).limit(1)).first() is not None
    if not has_rules:
        created = 0
        for priority, match_field, pattern, target_name in DEFAULT_RULES:
            category_id = by_name.get(target_name)
            if category_id is None:
                logger.warning(
                    "⚠️ [Categorize] seed: catégorie « %s » absente, règle ignorée",
                    target_name,
                )
                continue
            db.add(
                models.CategoryRule(
                    match_field=match_field,
                    pattern=pattern,
                    category_id=category_id,
                    priority=priority,
                    enabled=True,
                )
            )
            created += 1
        db.commit()
        logger.info("🗄️ [Categorize] seed: %d règles système créées", created)
