# Codebase Documentation — Project-Specific Output
> Généré via `7-CODEBASE.md`. État après le build MVP (EPIC-1 → 6).

## Vue d'ensemble
App locale LGC = backend **FastAPI** (:8000) + frontend **Next.js App Router** (:3000).
`make dev` lance les deux · `make seed` remplit la démo · `make test` lance back+front.

## Backend (`backend/`)
| Module | Rôle |
|---|---|
| `api/main.py` | App FastAPI : lifespan (init_db + seed catégories), CORS, monte 27 endpoints. |
| `config.py` | Config env (`DATABASE_URL`, `LOG_LEVEL`, creds Enable Banking). |
| `logging_config.py` | `get_logger(name, channel)` → `logs/<channel>_<date>.log` + masquage IBAN/email/secrets. |
| `db/base.py` | Engine SQLite, `SessionLocal`, `get_db`, `init_db`, `PRAGMA foreign_keys=ON`. |
| `db/models.py` | Modèles SQLAlchemy (archi §4) : Settings, Client, BankAccount, Category, CategoryRule, Transaction, Invoice, Investment. Montants `Numeric`→`Decimal`. `Invoice` porte le cycle de vie `forecast→due→paid` (fusion de l'ex-`ForecastInput`, ADR-007) + `rate_unit` (day/hour). `Client.billing_mode` (tjm/thm). |
| `services/categorize.py` | Moteur de règles (substring, priorité), fallback « À catégoriser », `recategorize_all`, seed catégories/règles système. |
| `services/treasury.py` | `consolidated_treasury`, `link_fx_conversion`, `eur_amount`. |
| `services/pnl.py` | `monthly_pnl(year)` — P&L mensuel EUR, exploitation uniquement. |
| `services/forecast.py` | `project`, `estimate_is` (15%/25% seuil 42 500), `upsert_inputs`. |
| `services/invoices.py` | `create_invoice`, `generate_invoice` (forecast→due : n°+dates+désignation), `render_html`/`designation` (template imprimable FR), `timeline`, `reconcile_payments`/`_apply_payment` (fige paiement+variance, match natif↔natif), `reconcile_candidates` (revenus non liés triés par proximité), `manual_reconcile`/`unreconcile`. Routes `/generate`, `/print` (HTML Cmd+P→PDF), `/candidates`, `/reconcile`, `/unreconcile`. |
| `services/banking.py` | Enable Banking : `list_aspsps`, `start_auth`, `create_session`, `sync` (dédup `(account_uid, external_id)`, signe DBIT/CRDT). Seam **mock/live** (`is_live()`). |
| `services/backup.py` | Sauvegarde SQLite (API backup, copie cohérente) → `data/backups/`, rotation 30 j (tout le jour courant, 1/jour passé). Appelé **fail-closed** avant chaque `POST /api/banking/sync` (ADR-008). |
| `api/routes/*.py` | settings, clients, investments, transactions, categories (+rules), treasury (+pnl), forecast, invoices, banking. |
| `seed.py` | Données démo 2026 + `make seed` / `make seed-reset`. |
| `templates/invoice.html` | Gabarit facture (Jinja2, mentions art. 293 B). |

**Endpoints (27) :** `/api/{settings,clients,manual-assets,transactions,categories,category-rules,treasury,pnl,forecast,invoices,banking/*}` + `/health`, `/`.

## Frontend (`frontend/`)
| Élément | Rôle |
|---|---|
| `app/layout.tsx` | Layout + nav latérale (`Nav`). |
| `app/page.tsx` | **Dashboard** : StatCards (tréso, P&L, IS), graphe P&L mensuel (barres CSS), prévision tréso, comptes. |
| `app/transactions/page.tsx` | Liste filtrable, catégorisation inline, bouton Synchroniser. |
| `app/categories/page.tsx` | Catégories + éditeur de règles. |
| `app/forecast/page.tsx` | Grille prévisionnelle éditable + déroulé tréso + estimation IS. |
| `app/invoices/page.tsx` | Factures : cycle prévision→à encaisser→payée, Générer, Ouvrir (page imprimable), rapprochement manuel tx↔facture + colonne écart forecast/réel. |
| `app/banking/page.tsx` | Statut Enable Banking (mock/live), connexion, synchro, comptes. |
| `app/settings/page.tsx` | Paramètres société / IS / facturation / change. |
| `src/api/client.ts` | Client fetch typé (une API par domaine). |
| `src/components/{Nav,ui}.tsx` | Nav + primitives (PageTitle, Card, StatCard, Badge, Empty). |
| `src/lib/format.ts` | Formatage FR (eur, money, pct, dateFR). |
| `jest.config.js`, `postcss.config.mjs` | Tooling (next/jest SWC, Tailwind v4). |

## Lancement & tests
`make dev` · `make seed` · `make back` · `make front` · `make test` · `make install`.
- Back : **60 tests** (pytest). Front : **7 tests** (jest) + `next build` OK + `tsc` clean.

## Dette technique / points ouverts
- **WeasyPrint** : nécessite `brew install pango` pour générer les PDF (sinon 503).
- **Enable Banking** : mode démo par défaut ; `pyjwt` + creds (`ENABLE_BANKING_APP_ID`, clé PEM) pour la synchro réelle. Risque ouvert : callback localhost vs https (archi §9).
- **Alembic** : migrations versionnées à mettre en place (tables via `init_db` en dev).
- Cosmétique : "Total facturé" additionne des devises hétérogènes ; solde brut des comptes = 0 tant que non synchronisé (dashboard recalcule).
