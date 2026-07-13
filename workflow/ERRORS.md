# Known Errors & Investigation Methodology

## TL;DR
1. **Check the Error Registry below** — has this been solved before?
2. **Simplify before complexifying** — minimal fix first, test, then add complexity
3. **Compare with existing code** — copy working patterns, don't invent new ones
4. **Test after every change** — one change at a time, verify each
5. **If stuck** — STOP, restore to working state, restart simpler
6. **After fixing** — add an entry to the Error Registry immediately

---

## 🔍 Investigation Methodology

> **Read this BEFORE attempting to fix ANY error.**

### Fundamental Principles

#### 1. Simplify BEFORE Complexifying
- ❌ **BAD:** Add complex solutions
- ✅ **GOOD:** Create a minimal working version first

#### 2. Compare With Existing Code
- ❌ **BAD:** Create new code without looking at how it's done elsewhere
- ✅ **GOOD:** Find similar examples in the codebase, copy the working pattern

#### 3. Test Progressively
- ❌ **BAD:** Create everything at once, test only at the end
- ✅ **GOOD:** Create one thing at a time, test after each addition

#### 4. Isolate the Problem
- ❌ **BAD:** Modify several things at the same time
- ✅ **GOOD:** Test if the problem existed before your changes

#### 5. Don't Break the Application
- ❌ **BAD:** Keep modifying even if the app no longer works
- ✅ **GOOD:** Restore immediately if the app is broken

### Checklist Before Modifying Code
- [ ] I've read the existing code to understand the pattern
- [ ] I've found similar examples in the codebase
- [ ] I will create a minimal version first
- [ ] I will test after each modification
- [ ] I know how to restore if it breaks
- [ ] I will NOT add unnecessary complexity

---

## Error Registry

## Error Index
| ID | Category | Short Description | Status | First Seen | Epic |
|---|---|---|---|---|---|
| ERR-001 | INFRA | Dashboard bloqué « Chargement… » — port 8000 pris par un autre projet | Resolved | 2026-07-01 | EPIC-4 |
| ERR-002 | LOGIC | Rapprochement facture en devise impossible (matcher comparait EUR vs montant natif) | Resolved | 2026-07-03 | EPIC-5 |

---

## Error Categories
- **DATA** — ingestion, parsing, schema, quality issues
- **CONFIG** — missing env vars, bad config values
- **INTEGRATION** — API failures, DB connection errors
- **LOGIC** — incorrect calculations, wrong business logic
- **PERFORMANCE** — timeouts, memory issues, slow queries
- **DEPENDENCY** — package conflicts, version mismatches
- **INFRA** — deployment, environment, path issues
- **UI** — frontend rendering, state management

---

## Error Entries

### ERR-001: Dashboard bloqué sur « Chargement… »
**Category:** INFRA
**Status:** `Resolved`
**First seen:** 2026-07-01 — EPIC-4

#### Symptoms
```
Dashboard affiche "Chargement…" indéfiniment.
curl :8000/health → HTTP 000 (connexion refusée).
Un autre projet (Claude/Stocks) tournait aussi sur :8000 / :3000
(requêtes /api/holding-signals dans les logs) → back LGC éjecté.
```

#### Root Cause
Conflit de port : LGC et un autre projet local (Stocks) utilisaient tous deux
`:8000` (back) et `:3000` (front). Le back LGC s'est arrêté, le front continuait
d'interroger `:8000` (mort ou servant l'autre projet) → fetch en attente → écran
de chargement figé.

#### Fix Applied
**Date fixed:** 2026-07-01
LGC déplacé sur des ports isolés : **back :8001**, **front :3001**.
- `Makefile` : `BACK_PORT=8001`, `FRONT_PORT=3001`.
- `frontend/.env.local` : `NEXT_PUBLIC_API_URL=http://localhost:8001`.
- CORS (`main.py`) autorise déjà `localhost:3001`.

#### Prevention Rule
> 🔒 **RULE ERR-001:** Avant de lancer un serveur, TOUJOURS vérifier que le port
> est libre (`lsof -ti :PORT`). En cas de conflit avec un autre projet, décaler
> LGC sur ses ports dédiés (8001/3001) plutôt que tuer le process de l'autre projet.

#### Test Added
- [x] Vérif manuelle : Dashboard charge sur :3001 → :8001 (screenshot). N/A pour test auto.

---

### ERR-002: Rapprochement d'une facture en devise impossible
**Category:** LOGIC
**Status:** `Resolved`
**First seen:** 2026-07-03 — EPIC-5 (story ② cycle de vie)

#### Symptoms
Une facture en USD (`amount` natif) ne se rapprochait jamais de sa transaction USD
dès que la transaction portait un `amount_eur`. `reconcile_payments` renvoyait 0.

#### Root Cause
`_amount_matches` comparait `tx.amount_eur` (ex. 9045 €) au montant **natif** de la
facture (`invoice.amount`, ex. 10050 $) → écart énorme, jamais dans la tolérance.
Ça ne « marchait » que par coïncidence quand facture et tx avaient la même valeur
numérique (cas EUR).

#### Fix
`_amount_matches(tx, invoice)` : **même devise → compare les montants natifs**
(rapprochement FX exact) ; devises différentes → repli sur l'EUR (théorique côté
facture). Le taux réel encaissé + la variance sont figés sur la facture au paiement.

#### Prevention Rule
> 🔒 **RULE ERR-002:** Pour rapprocher deux montants, comparer d'abord **dans la même
> devise** (natif ↔ natif). Ne jamais comparer un montant EUR converti à un montant
> natif — la conversion masque/fausse l'égalité.

#### Test Added
- [x] `test_invoice_lifecycle.py::test_reconcile_fills_payment_fields_and_variance`
  (facture USD 10050 ↔ tx USD 10050, EUR reçu 9045, variance +45).

---

### ERR-003 — 500 à l'enregistrement d'un client (UNIQUE(clients.code))
**Symptôme :** page Clients, ❌ HTTP 500 en enregistrant. Trace : `sqlite3.IntegrityError: UNIQUE constraint failed: clients.code` sur `INSERT`.
**Cause racine :** `create_client`/`update_client` ne géraient pas l'`IntegrityError` → 500 brut. Déclencheur : enregistrer un client **sans code** (le 1ᵉʳ passe et crée un fantôme `code=""`, le 2ᵉ collisionne). Aussi tout code doublon.
**Fix :** `_require_code()` refuse un code vide (422) ; `_commit_or_409()` traduit la collision UNIQUE en **409** propre. Garde-fou front : save bloqué si code vide.

#### Prevention Rule
> 🔒 **RULE ERR-003 :** Toute écriture DB sous contrainte `UNIQUE`/FK doit **attraper `IntegrityError`** et rendre un 409/422 lisible — jamais laisser remonter un 500. Valider les champs identifiants non vides **avant** l'INSERT.

#### Test Added
- [x] `test_settings_clients_investments.py` : `test_client_create_rejects_empty_code` (422),
  `test_client_create_duplicate_code_returns_409`, `test_client_patch_to_duplicate_code_returns_409`.

---

### ERR-004 — `AssertionError: Status code 204 must not have a response body` (collection échoue au démarrage)

**Symptôme :** `pytest` s'arrête à la collection ; l'import de `backend.api.main` lève `AssertionError` sur une route `DELETE ... status_code=204`.

**Root cause :** les modules de routes ont `from __future__ import annotations`. L'annotation de retour `-> None` devient la **chaîne** `"None"`, que FastAPI 0.115 résout en `NoneType` **truthy** → il l'interprète comme un `response_model`. Or un 204 ne peut pas avoir de corps → assertion. (Sans future-annotations, `-> None` reste le vrai `None` et ne déclenche rien — d'où le comportement qui « marchait avant » selon la version de FastAPI.)

**Fix :** retirer l'annotation `-> None` sur les **handlers** décorés en 204 (7 endpoints : balance_docs, banking, categories ×2, clients, investments, invoices). Les helpers internes non-route gardent `-> None`.

#### Prevention Rule
> 🔒 **RULE ERR-004 :** Un handler de route en `status_code=204` (ou 304) ne doit **jamais** porter d'annotation de retour (`-> None`, `-> X`) quand le module a `from __future__ import annotations` — sinon FastAPI la prend pour un `response_model` et casse la collection. Laisser la signature sans annotation de retour.

#### Test Added
- [x] La suite complète importe l'app à la collection → toute régression 204 refait échouer `pytest` immédiatement (garde-fou implicite, aucun test dédié nécessaire).

---

### ERR-005 — `abs()` sur les charges : les remboursements comptés en charges (P&L projeté + IS gonflés)

**Date :** 2026-07-10 · **Découvert par :** l'utilisateur (écart net cashflow fiscal +348 777 vs résultat P&L projeté 347 731,72 → 1 045,01 €)

#### Root Cause
`forecast._charges_by_date` (et `_recent_monthly_charge_avg`) faisaient `abs(eur)` sur chaque transaction de catégorie charge : un **remboursement** (+386,17 hôtel, +109,33 INPI, +24 frais bancaires, +3 Amazon = 522,50 €) devenait une charge SUPPLÉMENTAIRE au lieu d'une déduction → charges réelles gonflées de 2× le remboursé (1 045,00) + moyenne projetée des mois futurs contaminée (~967 € de plus). Le cashflow, lui, nettait correctement — d'où l'écart entre les deux widgets.

#### Fix
Contribution SIGNÉE : charge (montant < 0) → positif, remboursement → négatif ; EUR réel (`amount_eur`) prioritaire sur le taux théorique ; moyenne future clampée ≥ 0. Écart après fix : 0,02 € (arrondis de sommes mensuelles).

#### Prevention Rule
**Jamais `abs()` sur un agrégat financier** — netter en signé puis afficher en magnitude au dernier moment. Quand deux widgets divergent, décomposer l'écart composante par composante (revenus/charges/non-op) au centime avant de conclure « vision différente ».

#### Test Added
- [x] `test_charges_projection_nets_refunds` (charge 100 − refund 30 → 70, l'ancien code donnait 130).

---

### ERR-006 — Les tests de route écrivaient dans le vrai `data/` (hook backup non isolé)

**Date :** 2026-07-11 · **Découvert par :** revue post-implémentation (fichier `lgc_20260711_062238_sync.db` apparu dans `data/backups/` pendant `pytest`)

#### Root Cause
Le hook `create_backup()` ajouté à `POST /api/banking/sync` utilise par défaut la vraie base (`engine.url.database`) et le vrai `data/backups/`. Les tests de route existants (`test_banking.py`) exercent `/sync` avec une session DB in-memory **mais le hook, lui, lisait le vrai fichier** → la suite de tests créait des sauvegardes de la base réelle.

#### Fix
`backend/tests/conftest.py` : fixture autouse `_backups_isolated` qui redirige `_default_db_path` vers une base vide en `tmp_path` (destination dérivée = tmp aussi). Vérifié : `ls data/backups/` identique avant/après la suite complète.

#### Prevention Rule
**Tout hook de route qui touche le système de fichiers réel doit être neutralisé par une fixture autouse dans `conftest.py` dès sa création** — une session DB de test isolée n'isole PAS les effets de bord fichiers.

#### Test Added
- [x] Isolation structurelle via `conftest.py` (couvre tous les tests présents et futurs) ; garde vérifiée manuellement par diff de `data/backups/` avant/après suite.

---

### ERR-007 — Nouveau type de catégorie invisible dans une des vues (fallthrough elif)

**Date :** 2026-07-13 · **Découvert par :** revue finale de branche (import-csv-2025), avant merge

#### Root Cause
Le type `immobilisation` ajouté pour le P&L était exclu des charges par **fallthrough** (chaîne `elif` sans `else` dans pnl.py) et tombait dans **aucun** bucket du cashflow (`_NONOP_TYPES` non mis à jour) : la dépense réelle (MacBook −1 313 €) disparaissait de la vue cashflow, cassant l'identité net = variation de trésorerie.

#### Fix
`immobilisation` ajouté explicitement à `pnl._EXCLUDED_CATEGORY_TYPES` ET `cashflow._NONOP_TYPES` (ordre des checks vérifié : bucket non-op puis continue, même schéma que internal/distribution/is_payment). Tests de régression dans les deux vues.

#### Prevention Rule
**Tout nouveau type de catégorie doit être passé en revue chez TOUS les consommateurs de `Category.type`** (pnl, cashflow, forecast, categorize `_TYPE_TO_KIND`) — une exclusion par fallthrough n'est pas une exclusion : elle casse silencieusement à la vue suivante. Grepper `Category.type`/`cat.type`/`ctype` avant de merger.

#### Test Added
- [x] `test_pnl_excludes_immobilisation_category` + `test_immobilisation_outflow_visible_in_nonop_bucket`.

---

## 🔒 Prevention Rules Summary
| Rule ID | Applies To | Rule |
|---|---|---|

---

## 📊 Error Patterns
| Pattern | Count | Root Cause Theme | Systemic Fix |
|---|---|---|---|
