# Rapprochement côté ACHAT des placements — Plan

**Goal:** Lier un placement à la transaction bancaire **sortante** qui l'a financé, et dériver l'investi (natif exact + EUR) de cette sortie au lieu d'une saisie manuelle.

**Architecture:** Nouveau champ `Investment.opening_transaction_id` (auto-migré via `_ensure_columns`). Endpoints miroir du remboursement, mais sur les **sorties** (`amount < 0`). Front : action + modale sur la page Placements.

## Global Constraints
- Route prefix `/api/manual-assets`. Montants `Decimal`. `_tx_eur` = valorisation EUR canonique (amount_eur sinon taux plat → l'EUR reste au taux de référence ; c'est le **natif** qui devient exact).
- Flux interne à la liaison : `tx.kind='investment'` + catégorie type `internal` (comme le remboursement) → jamais compté en charge.
- Additif only : ne casse ni le remboursement existant ni ses tests.

---

### Task 1 — Modèle + schéma
**Files:** `backend/db/models.py`, `backend/api/routes/investments.py`
- `Investment.opening_transaction_id: Optional[int] = FK(transactions.id, nullable=True)` (avant `closed_transaction_id`).
- `InvestmentOut` : `opening_transaction_id: Optional[int] = None`.
- Auto-migration confirmée (`base.py:_ensure_columns` ALTER ADD COLUMN).

### Task 2 — `GET /{id}/purchase-candidates`
- Sorties `amount < 0`, `invoice_id IS NULL`, non déjà `opening_transaction_id`/`closed_transaction_id` d'un placement.
- Tri : même devise → `|amount|` vs `opening_value` natif ; sinon `|_tx_eur|` vs `opening_value_eur`. 20 max.
- Même shape de sortie que `candidates` (id, booked_date, description, counterparty, amount, currency, amount_eur).
- **Test** : une sortie proposée, un crédit exclu, tri par proximité.

### Task 3 — `POST /{id}/link-purchase` {transaction_id}
- 409 si `opening_transaction_id` déjà posé ; 404 tx absente ; 422 si `amount >= 0` ; 409 si `invoice_id` ; 409 si tx déjà liée (opening/closing) à un autre placement.
- Pose `opening_transaction_id`, `opening_value=abs(tx.amount)`, `currency=tx.currency`, `opening_value_eur=abs(_tx_eur(tx))` ; bascule tx interne+`investment`.
- Si déjà clôturé : recalcule `realized_gain_eur = received_eur − nouveau opening_eur`.
- **Test** : investi dérivé de la sortie (9060.02 natif), tx passée interne, gardes 409/422/404.

### Task 4 — `POST /{id}/unlink-purchase`
- 409 si non lié ; sinon `opening_transaction_id=None` (tx garde sa catégorie interne, comme `unreconcile`). N'efface pas `opening_value`.
- **Test** : délie, 409 si non lié.

### Task 5 — Filtre bruit remboursement
- `redemption_candidates` : exclure `kind ∈ {conversion, investment, internal}` (les « Exchanged to EUR Main »). Crédits `amount>0` sinon inchangés.
- **Test** : une conversion FX n'est plus candidate ; un vrai crédit (kind='other') l'est toujours (test existant vert).

### Task 6 — Front (api + page)
**Files:** `frontend/src/api/client.ts`, `frontend/app/placements/page.tsx`
- api : `purchaseCandidates(id)`, `linkPurchase(id, txId)`, `unlinkPurchase(id)`.
- Type `Investment` + `opening_transaction_id`.
- Cellule « Investi (achat) » : chip 🔗 tx#N si lié, sinon ⚠ saisie manuelle + bouton « 🔗 Rapprocher l'achat » ; « Délier » si lié.
- Modale achat = miroir de la modale remboursement (candidats sortants, clic → `linkPurchase`).
- `tsc` clean, suite front verte.
