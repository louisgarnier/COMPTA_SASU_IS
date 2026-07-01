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

## 🔒 Prevention Rules Summary
| Rule ID | Applies To | Rule |
|---|---|---|

---

## 📊 Error Patterns
| Pattern | Count | Root Cause Theme | Systemic Fix |
|---|---|---|---|
