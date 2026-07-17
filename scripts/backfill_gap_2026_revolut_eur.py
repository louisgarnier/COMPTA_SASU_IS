"""Backfill des 2 transactions Revolut EUR perdues dans le trou d'import 2025→2026.

Contexte : l'import CSV s'est arrêté au 30/12/2025, la synchro live Enable Banking a
démarré le 02/01/2026. Deux débits du 1er/2 janvier (confirmés sur le relevé de
transactions Revolut officiel) sont passés entre les deux → résidu −23,00 € sur le
compte Revolut EUR. On les réinsère (source « relevé »), catégorie Repas comme leurs sœurs.

Idempotent : ne réinsère pas si l'external_id existe déjà.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.db.base import SessionLocal
from backend.db import models

ACCOUNT_UID = "cd56227f-c427-41bc-8e20-cd40dced4872"  # Revolut Main · EUR
CAT_REPAS = 8

MISSING = [
    {
        "external_id": "manual-gap-2026-01-01-yen-grandes-hall",
        "booked_date": date(2026, 1, 1),
        "value_date": date(2026, 1, 1),
        "amount": Decimal("-8.00"),
        "counterparty": "Yen Grandes Hall",
        "description": "Yen Grandes Hall",
    },
    {
        "external_id": "manual-gap-2026-01-02-500-degres",
        "booked_date": date(2026, 1, 2),
        "value_date": date(2026, 1, 2),
        "amount": Decimal("-15.00"),
        "counterparty": "500 Degres",
        "description": "500 Degres",
    },
]


def main() -> None:
    db = SessionLocal()
    try:
        added = 0
        for m in MISSING:
            exists = (
                db.query(models.Transaction)
                .filter(
                    models.Transaction.account_uid == ACCOUNT_UID,
                    models.Transaction.external_id == m["external_id"],
                )
                .first()
            )
            if exists is not None:
                print(f"= déjà présent : {m['counterparty']} ({m['external_id']})")
                continue
            db.add(
                models.Transaction(
                    account_uid=ACCOUNT_UID,
                    external_id=m["external_id"],
                    booked_date=m["booked_date"],
                    value_date=m["value_date"],
                    amount=m["amount"],
                    currency="EUR",
                    description=m["description"],
                    counterparty=m["counterparty"],
                    category_id=CAT_REPAS,
                    kind="charge",
                )
            )
            added += 1
            print(f"+ ajouté : {m['booked_date']} {m['amount']} {m['counterparty']}")
        db.commit()
        print(f"✅ backfill terminé — {added} transaction(s) ajoutée(s)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
