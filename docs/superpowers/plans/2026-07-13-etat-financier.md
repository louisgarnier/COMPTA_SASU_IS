# Onglet État financier — Plan (V1)

**Goal:** Comparer le compte de résultat de l'app au comptable validé (stocké par exercice, jamais en dur), avec un pont de réconciliation qui se ferme au centime.

**Architecture:** Nouvelle table `accountant_statements` (une ligne / exercice, auto-migrée). Endpoint de comparaison qui fusionne le CdR app (calculé via `pnl`) + les chiffres comptable stockés + un pont dérivé. Nouvelle page `/etat-financier`.

## Global Constraints
- Chiffres comptable = DONNÉES saisies/stockées par exercice (table), jamais en dur dans le code (règle anti-hardcoding).
- Montants `Decimal`. App CdR = `pnl.summary`/`monthly_pnl` (revenue accrual, charges). Résultat app = revenue − charges.
- Pont auto-fermant : résidu = app_result − dotations − provision − comptable_result (étiqueté « classement charges + méthode FX »).
- V1 : compte de résultat + pont. Pas de bilan (V2). Résidu laissé agrégé.

---

### Task 1 — Modèle `AccountantStatement`
**Files:** `backend/db/models.py`
- PK `year:int`. Colonnes `Decimal` (default 0) : `production_vendue, charges_exploitation, resultat_exploitation, produits_financiers, charges_financieres, resultat_financier, dotations_amortissements, provision_change, is_amount, resultat_net`. `note:str=""`.
- Auto-migration via `_ensure_columns`/`create_all`.
- **Test** : implicite (couvert par l'endpoint).

### Task 2 — CRUD chiffres comptable
**Files:** `backend/api/routes/financial.py` (nouveau), enregistrer dans l'app.
- `GET /api/accountant-statement/{year}` → figures stockées ou 404.
- `PUT /api/accountant-statement/{year}` (upsert) → enregistre, renvoie la ligne.
- **Test** : PUT crée puis GET relit ; PUT réécrit (upsert).

### Task 3 — Endpoint de comparaison + pont
**Files:** `backend/api/routes/financial.py`
- `GET /api/financial-statement?year=` → `{year, is_regime, app:{production_vendue, charges_exploitation, resultat}, accountant:{…}|null, bridge:[{label, amount, anchor?}]}`.
- `app` depuis `pnl.summary(db, year)` : production_vendue=revenue_eur, charges_exploitation=charges_eur, resultat=result_eur.
- `bridge` si `accountant` présent : [App result (anchor)] − dotations − provision − résidu = [Comptable result (anchor)] ; résidu = app_result − dotations − provision − accountant.resultat_net.
- **Test** : sans comptable → bridge vide/accountant null ; avec comptable saisi → pont ferme (somme des steps = comptable.resultat_net).

### Task 4 — Front : page `/etat-financier` + nav
**Files:** `frontend/app/etat-financier/page.tsx` (nouveau), `frontend/src/components/Nav.tsx`, `frontend/src/api/client.ts`
- Nav : entrée `{ href:'/etat-financier', label:'État financier', icon:'📋' }`.
- api : `financialAPI.statement(year)`, `financialAPI.getAccountant(year)`, `financialAPI.saveAccountant(year, body)`.
- Page : sélecteur d'exercice, 3 KPI (résultat app / comptable / écart), tableau comparatif (CA, charges, résultat exploitation, résultat financier, résultat net), pont (waterfall), bouton « Saisir le compte de résultat validé » (modale formulaire → PUT).
- `tsc` clean, suite front verte.

### Task 5 — Saisie des chiffres comptable 2025 (données)
- Après build : PUT des chiffres 2025 lus du CdR (CA 218011, charges 36453, résultat exploitation 181557, produits fin. 651, charges fin. 8428, résultat fin. −7777, dotations 1408, provision 3004, IS 0, résultat net 173780). Vérifier le pont ferme (app 179324 → 173780).
