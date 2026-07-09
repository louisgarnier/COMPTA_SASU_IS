"""
Helpers de parsing des paramètres de requête.

`parse_as_of` : accepte une date pure (« 2026-07-08 ») MAIS AUSSI une datetime
(« 2026-07-08T22:34:00.000Z ») en la tronquant à la date — certains navigateurs
ou chemins d'appel envoient l'heure. Chaîne vide/absente → None. Valeur
inintelligible → 422 avec un message clair (pas le pydantic brut).
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import HTTPException


def parse_as_of(value: Optional[str]) -> Optional[date]:
    """Parse un paramètre `as_of` tolérant (date ou datetime ISO, tronquée)."""
    if value is None:
        return None
    v = value.strip()
    if not v or v == "undefined":
        return None
    try:
        return date.fromisoformat(v[:10])
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"as_of : date invalide « {value} » (attendu AAAA-MM-JJ)",
        )
