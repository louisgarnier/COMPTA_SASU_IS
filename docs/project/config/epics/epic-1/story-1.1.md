# Story 1.1 — Scaffold back + front (squelette qui tourne)

## Goal
Un squelette **back (FastAPI `/health`)** + **front (Next.js)** qui démarre en **une seule commande**, sans dépendance base de données (la DB arrive en S1.2).

## Contexte / point de départ
Du code de scaffold **template générique** existe déjà sur disque (`backend/api/main.py` titré *« API Template »*, `backend/database/`, `backend/api/models.py`, `frontend/`), hérité du générateur de projet — **non validé pour LGC**. Cette story le remet aux couleurs LGC et le fait réellement tourner, en s'alignant sur l'architecture §5. La couche DB complète (SQLAlchemy/Alembic/entités) est **hors périmètre** (→ S1.2).

## Périmètre
**Dans le scope**
- App FastAPI minimale qui expose `/health` (+ `/`) et démarre sur `:8000`.
- CORS autorisant `http://localhost:3000` (middleware couche externe).
- App Next.js (App Router) qui démarre sur `:3000`, page d'accueil placeholder LGC qui **ping `/health`** et affiche l'état back (vert/rouge).
- Client API front minimal (`src/api/client.ts`) pointant sur `http://localhost:8000`.
- **Script de lancement 1 commande** qui démarre back + front ensemble.
- Renommage/nettoyage du template : titres/description LGC, suppression des références `.windsurfrules` et `API Template`.
- Retirer l'appel `init_database()` du lifespan (dépend de la DB → S1.2) : le squelette doit démarrer **sans** base.

**Hors scope (stories suivantes)**
- Modèles SQLAlchemy, migrations Alembic, création de `lgc.db` → **S1.2**
- Loggers fichiers `logs/*` → **S1.3**
- Entité/API Settings → **S1.4**

## Acceptance Criteria
- [x] `GET http://localhost:8000/health` renvoie `200` `{"status":"healthy"}`. *(curl live via make dev)*
- [x] `GET http://localhost:8000/` renvoie `200` avec un message identifiant LGC. *(`{"message":"LGC API","status":"ok"}`)*
- [x] Le back démarre **sans** base de données (aucun appel DB au startup). *(log uvicorn, `init_database` retiré)*
- [x] CORS : une requête front `localhost:3000` → back `:8000` passe sans erreur CORS. *(en-tête `access-control-allow-origin` présent + test)*
- [x] `http://localhost:3000` affiche une page LGC qui **ping `/health`** et indique « back OK ». *(page sert LGC/Suivi cashflow SASU/État du backend)*
- [x] **Une seule commande** documentée lance back **et** front. *(`make dev`)*
- [x] Aucune trace du template générique (`API Template`, `.windsurfrules`) dans le code back/front conservé.
- [x] Tests verts : `pytest` (4) et test front (2). *(`make test` tout vert)*

## Tasks
- [ ] Nettoyer `backend/api/main.py` : titre/description LGC, retirer `init_database()` du lifespan, garder CORS + `/` + `/health`.
- [ ] Statuer sur le scaffold DB parasite (`backend/database/`, `backend/api/models.py`, `schema.sql`) : à **supprimer** ici (recréé proprement en S1.2 sous `backend/db/` selon archi §5) — à confirmer avec toi.
- [ ] Front : page `app/page.tsx` LGC qui appelle `/health` via `src/api/client.ts` et affiche l'état.
- [ ] Script de lancement 1 commande (`scripts/dev.sh` ou `Makefile` — à trancher) : uvicorn `:8000` + `next dev` `:3000`.
- [ ] Vérifier `backend/requirements.txt` (fastapi, uvicorn) et `frontend/package.json` (next, react) cohérents avec archi §1.
- [ ] Tests : `backend/tests/test_api.py` (health + root), test front minimal du rendu de la page.
- [ ] Lancer les deux, capturer les preuves (sortie pytest, curl `/health`, page front OK).
- [ ] MàJ `build-log.md` + `codebase.md`, cocher AC, avancer `ACTIVE.md`.

## Décisions tranchées (validées)
1. **Script de lancement** : ✅ **Makefile** (`make dev` lance back+front, `make test` lance les tests).
2. **Scaffold DB parasite** : ✅ **Supprimer maintenant** (`backend/database/`, `backend/api/models.py`, `schema.sql`, `routes/example.py`) — recréé proprement en S1.2 sous `backend/db/` (archi §5).

## Status: `done` (2026-07-01)
