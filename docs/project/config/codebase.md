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
| `db/models.py` | Modèles SQLAlchemy (archi §4) : Settings, Client, BankAccount, Category, CategoryRule, Transaction, Invoice, Investment. Montants `Numeric`→`Decimal`. `Invoice` porte le cycle de vie `forecast→due→paid` (fusion de l'ex-`ForecastInput`, ADR-007) + `rate_unit` (day/hour). `Client.billing_mode` (tjm/thm). `BalanceDocument.period_year/period_month` (EPIC-8) ; nouvelle table `MonthlyBalance` (solde officiel de fin de mois par compte, unique `account_uid`+`year`+`month`). |
| `services/categorize.py` | Moteur de règles (substring, priorité), fallback « À catégoriser », `recategorize_all`, seed catégories/règles système. |
| `services/treasury.py` | `consolidated_treasury`, `link_fx_conversion`, `eur_amount`. |
| `services/pnl.py` | `monthly_pnl(year)` — P&L mensuel EUR, exploitation uniquement. |
| `services/forecast.py` | `project`, `estimate_is` (15%/25% seuil 42 500), `upsert_inputs`. |
| `services/invoices.py` | `create_invoice`, `generate_invoice` (forecast→due : n°+dates+désignation), `render_html`/`designation` (template imprimable FR), `timeline`, `reconcile_payments`/`_apply_payment` (fige paiement+variance, match natif↔natif), `reconcile_candidates` (revenus non liés triés par proximité), `manual_reconcile`/`unreconcile`. Routes `/generate`, `/print` (HTML Cmd+P→PDF), `/candidates`, `/reconcile`, `/unreconcile`. |
| `services/banking.py` | Enable Banking : `list_aspsps`, `start_auth`, `create_session`, `sync` (dédup `(account_uid, external_id)`, signe DBIT/CRDT). Seam **mock/live** (`is_live()`). |
| `services/csv_import.py` | Import CSV bancaire (Qonto/Revolut) : détection de format, parseurs (Revolut = « Total amount » frais inclus), `analyze` (preview : rattachement `(iban_masked, devise)`, dédup, périmètre année, soldes calculés), `execute` (backup fail-closed → insertion → catégorisation). Routes `POST /api/import/{preview,execute}`. |
| `services/backup.py` | Sauvegarde SQLite (API backup, copie cohérente) → `data/backups/`, rotation 30 j (tout le jour courant, 1/jour passé). Appelé **fail-closed** avant chaque `POST /api/banking/sync` (ADR-008). |
| `services/statement_extract.py` | Extraction de soldes officiels depuis relevé : `extract_revolut_balances` (parse « Relevé des soldes » PDF), `extract_qonto_month_end` (CSV, robuste à l'ordre du fichier/jour de clôture), `pdf_to_text` (pypdf, ne lève jamais), `map_to_accounts` (mapping devise + 4 derniers IBAN, repli devise unique). |
| `services/monthly_reconcile.py` | Tie-out mensuel (EPIC-8) : `reconstruct_balance` (ouvertures + Σ mouvements jusqu'à fin de mois, helper public `sum_movements`), `monthly_reconciliation(db, year)` (vue 12 mois, statut ok/warn/missing, couverture X/12). |
| `api/routes/*.py` | settings, clients, investments, transactions, categories (+rules), treasury (+pnl), forecast, invoices, banking, `monthly_balances` (extraction/upsert/vue de réconciliation mensuelle). |
| `seed.py` | Données démo 2026 + `make seed` / `make seed-reset`. |
| `templates/invoice.html` | Gabarit facture (Jinja2, mentions art. 293 B). |

**Endpoints (30+) :** `/api/{settings,clients,manual-assets,transactions,categories,category-rules,treasury,pnl,forecast,invoices,banking/*,accountant-statement/{year},financial-statement}` + `/health`, `/`. Placements : `manual-assets/{id}/{purchase-candidates,link-purchase,unlink-purchase}` (rapprochement achat). Rapprochement mensuel officiel : `monthly-balances/{extract,reconciliation}` (POST/GET) + `PUT /api/monthly-balances?year=&month=`. Pages front : + `/etat-financier`.

## Frontend (`frontend/`)
| Élément | Rôle |
|---|---|
| `app/layout.tsx` | Layout + nav latérale (`Nav`). |
| `app/page.tsx` | **Dashboard** : StatCards (tréso, P&L, IS), graphe P&L mensuel (barres CSS), prévision tréso, comptes. |
| `app/transactions/page.tsx` | Liste filtrable, catégorisation inline, bouton Synchroniser. |
| `app/categories/page.tsx` | Catégories + éditeur de règles. |
| `app/forecast/page.tsx` | Grille prévisionnelle éditable + déroulé tréso + estimation IS. |
| `app/invoices/page.tsx` | Factures : cycle prévision→à encaisser→payée, Générer, Ouvrir (page imprimable), rapprochement manuel tx↔facture + colonne écart forecast/réel. |
| `app/banking/page.tsx` | Statut Enable Banking (mock/live), connexion, synchro, comptes, + `MonthlyReconcileCard`. |
| `app/settings/page.tsx` | Paramètres société / IS / facturation / change. |
| `src/components/MonthlyReconcileCard.tsx` | Carte de rapprochement mensuel officiel (EPIC-8) : tableau 12 mois, dépliage détail par compte, badges pos/warn/neutral ; ingestion hybride dépôt de relevé → extraction auto → confirmation éditable → archivage PDF lié (`source_doc_id`). |
| `src/api/client.ts` | Client fetch typé (une API par domaine), dont `monthlyBalancesAPI` (extract/upsert/reconciliation). |
| `src/components/{Nav,ui}.tsx` | Nav + primitives (PageTitle, Card, StatCard, Badge, Empty). |
| `src/lib/format.ts` | Formatage FR (eur, money, pct, dateFR). |
| `jest.config.js`, `postcss.config.mjs` | Tooling (next/jest SWC, Tailwind v4). |

## Lancement & tests
`make dev` · `make seed` · `make back` · `make front` · `make test` · `make install`.
- Back : **293 tests** (pytest). Front : **14 suites / 36 tests** (jest) + `next build` OK + `tsc` clean.

## Dette technique / points ouverts
- **WeasyPrint** : nécessite `brew install pango` pour générer les PDF (sinon 503).
- **Enable Banking** : mode démo par défaut ; `pyjwt` + creds (`ENABLE_BANKING_APP_ID`, clé PEM) pour la synchro réelle. Risque ouvert : callback localhost vs https (archi §9).
- **Alembic** : migrations versionnées à mettre en place (tables via `init_db` en dev).
- Cosmétique : "Total facturé" additionne des devises hétérogènes ; solde brut des comptes = 0 tant que non synchronisé (dashboard recalcule).
- **Extraction Revolut (EPIC-8)** : le champ name/hint peut être pollué par une ligne de pied de page du PDF (cosmétique, mapping devise+IBAN non affecté). Chasse aux frais FX manquants sur les mois en écart (étape 2 du rapprochement mensuel) : hors périmètre v1, conditionnelle.
