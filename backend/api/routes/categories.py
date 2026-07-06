"""
Routes Catégories & Règles de catégorisation.

Deux routeurs exportés :
- `router`       (prefix /api/categories)      → CRUD partiel des catégories.
- `rules_router` (prefix /api/category-rules)  → CRUD des règles.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db import models
from backend.db.base import get_db
from backend.logging_config import get_logger

logger = get_logger("categories", channel="api")

router = APIRouter(prefix="/api/categories", tags=["categories"])
rules_router = APIRouter(prefix="/api/category-rules", tags=["category-rules"])


# --------------------------------------------------------------------------- #
# Schémas Catégories
# --------------------------------------------------------------------------- #
class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    parent_id: Optional[int]
    is_system: bool


class CategoryCreate(BaseModel):
    name: str
    type: str
    parent_id: Optional[int] = None


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    parent_id: Optional[int] = None


# --------------------------------------------------------------------------- #
# Schémas Règles
# --------------------------------------------------------------------------- #
class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    match_field: str
    pattern: str
    category_id: int
    priority: int
    enabled: bool


class RuleCreate(BaseModel):
    match_field: str
    pattern: str
    category_id: int
    priority: int = 100
    enabled: bool = True


class RuleUpdate(BaseModel):
    match_field: Optional[str] = None
    pattern: Optional[str] = None
    category_id: Optional[int] = None
    priority: Optional[int] = None
    enabled: Optional[bool] = None


# --------------------------------------------------------------------------- #
# Endpoints Catégories
# --------------------------------------------------------------------------- #
@router.get("", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)) -> list[models.Category]:
    """Liste toutes les catégories (triées par nom)."""
    rows = (
        db.execute(select(models.Category).order_by(models.Category.name.asc()))
        .scalars()
        .all()
    )
    logger.info("📤 [Categories] list: %d résultat(s)", len(rows))
    return rows


@router.post("", response_model=CategoryOut, status_code=201)
def create_category(payload: CategoryCreate, db: Session = Depends(get_db)) -> models.Category:
    """Crée une catégorie (utilisateur → is_system=False)."""
    cat = models.Category(
        name=payload.name, type=payload.type, parent_id=payload.parent_id, is_system=False
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    logger.info("📤 [Categories] create: « %s » (%s) ✅", cat.name, cat.type)
    return cat


@router.patch("/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: int, payload: CategoryUpdate, db: Session = Depends(get_db)
) -> models.Category:
    """Met à jour partiellement une catégorie ; 404 si absente."""
    cat = db.get(models.Category, category_id)
    if cat is None:
        raise HTTPException(status_code=404, detail="Catégorie introuvable")
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(cat, field, value)
    db.commit()
    db.refresh(cat)
    logger.info("📤 [Categories] update: id=%s, %d champ(s) ✅", category_id, len(changes))
    return cat


@router.delete("/{category_id}", status_code=204)
def delete_category(category_id: int, db: Session = Depends(get_db)):
    """
    Supprime une catégorie utilisateur (404 si absente, 409 si système).

    FK-safe : les transactions rattachées sont réaffectées au fourre-tout
    « À catégoriser » et les règles ciblant cette catégorie sont supprimées,
    afin de ne pas violer les contraintes d'intégrité (RESTRICT).
    """
    from backend.services.categorize import get_or_create_uncategorized

    cat = db.get(models.Category, category_id)
    if cat is None:
        raise HTTPException(status_code=404, detail="Catégorie introuvable")
    if cat.is_system:
        raise HTTPException(
            status_code=409, detail="Catégorie système — suppression interdite"
        )

    uncategorized = get_or_create_uncategorized(db)
    # Réaffecte les transactions de cette catégorie au fourre-tout.
    (
        db.query(models.Transaction)
        .filter(models.Transaction.category_id == category_id)
        .update({models.Transaction.category_id: uncategorized.id})
    )
    # Supprime les règles qui ciblaient cette catégorie.
    db.query(models.CategoryRule).filter(
        models.CategoryRule.category_id == category_id
    ).delete()
    db.delete(cat)
    db.commit()
    logger.info("🗑️ [Categories] delete: id=%s (tx réaffectées au fourre-tout) ✅", category_id)


@router.post("/recategorize")
def recategorize(db: Session = Depends(get_db)) -> dict:
    """Rejoue les règles sur TOUTES les transactions ; retourne le nombre modifié."""
    from backend.services.categorize import recategorize_all

    changed = recategorize_all(db)
    logger.info("📤 [Categories] recategorize: %d transaction(s) modifiée(s) ✅", changed)
    return {"changed": changed}


# --------------------------------------------------------------------------- #
# Endpoints Règles
# --------------------------------------------------------------------------- #
@rules_router.get("", response_model=list[RuleOut])
def list_rules(db: Session = Depends(get_db)) -> list[models.CategoryRule]:
    """Liste toutes les règles (triées par priorité croissante)."""
    rows = (
        db.execute(
            select(models.CategoryRule).order_by(
                models.CategoryRule.priority.asc(), models.CategoryRule.id.asc()
            )
        )
        .scalars()
        .all()
    )
    logger.info("📤 [Rules] list: %d résultat(s)", len(rows))
    return rows


@rules_router.post("", response_model=RuleOut, status_code=201)
def create_rule(payload: RuleCreate, db: Session = Depends(get_db)) -> models.CategoryRule:
    """Crée une règle de catégorisation ; 404 si la catégorie cible n'existe pas."""
    if db.get(models.Category, payload.category_id) is None:
        raise HTTPException(status_code=404, detail="Catégorie cible introuvable")
    rule = models.CategoryRule(
        match_field=payload.match_field,
        pattern=payload.pattern,
        category_id=payload.category_id,
        priority=payload.priority,
        enabled=payload.enabled,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    logger.info("📤 [Rules] create: %s ~ « %s » ✅", rule.match_field, rule.pattern)
    return rule


@rules_router.patch("/{rule_id}", response_model=RuleOut)
def update_rule(
    rule_id: int, payload: RuleUpdate, db: Session = Depends(get_db)
) -> models.CategoryRule:
    """Met à jour partiellement une règle ; 404 si absente."""
    rule = db.get(models.CategoryRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Règle introuvable")
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(rule, field, value)
    db.commit()
    db.refresh(rule)
    logger.info("📤 [Rules] update: id=%s, %d champ(s) ✅", rule_id, len(changes))
    return rule


@rules_router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    """Supprime une règle ; 404 si absente."""
    rule = db.get(models.CategoryRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Règle introuvable")
    db.delete(rule)
    db.commit()
    logger.info("📤 [Rules] delete: id=%s ✅", rule_id)
