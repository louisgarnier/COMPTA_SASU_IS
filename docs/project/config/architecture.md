# Architecture — LGC
> **Status:** `Draft` (à valider avant plan d'implémentation) — 2026-07-01
> Source des décisions techniques. Ajouter une dépendance = mettre à jour ce fichier d'abord.

---

## 1. Tech Stack

### Core
| Layer | Choix | Version | Raison |
|---|---|---|---|
| Language (back) | Python | 3.11+ | Idéal calculs FX / forecast / PDF ; blueprint Enable Banking en Python |
| Language (front) | TypeScript | 5.x | Next.js |
| Framework (back) | FastAPI | 0.11x | API REST typée, async, léger |
| Framework (front) | Next.js (App Router) | 14/15 | UI moderne responsive, portable Vercel plus tard |
| Testing | pytest (back) / vitest (front) | — | Conforme code preferences |
| Linter | ruff (py) / eslint (ts) | — | |
| Formatter | black (py) / prettier (ts) | — | |

### Data & Storage
| Layer | Choix | Raison |
|---|---|---|
| Database | **SQLite** (local) | Mono-utilisateur local ; fichier sur le Mac |
| ORM | **SQLAlchemy** + Alembic (migrations) | Portable SQLite → PostgreSQL sans réécriture |
| File storage | Système de fichiers local (`data/invoices/`) | PDF de factures générés |
| Cloud/BaaS | **none** (v1) | Reporté (NG4) — archi pensée pour migrer vers Postgres/Supabase |

### Auth & Services
| Layer | Choix | Raison |
|---|---|---|
| Auth | **none** (v1) | Local mono-utilisateur, non exposé (Constraints §9 PRD) |
| AI / LLM | **none** (v1) | Catégorisation par règles ; « catégo intelligente » = idée v2 |
| PDF | **WeasyPrint** (HTML+CSS → PDF via Jinja2) | Meilleure fidélité à la mise en page Word actuelle ; templating simple |

### Infrastructure
| Layer | Choix | Raison |
|---|---|---|
| Hosting | **none** (local) | v1 local |
| Containerization | none (v1) | Simplicité ; `docker` possible plus tard |
| CI/CD | none (v1) | |
| Monitoring | Logs fichiers locaux | Conventions repo (`logs/`) |

**Approved external packages (aucune autre sans mise à jour de ce fichier) :**
```
# Backend
- fastapi, uvicorn        — API
- pydantic                — modèles/validation
- sqlalchemy, alembic     — ORM + migrations
- httpx                   — appels Enable Banking
- pyjwt[cryptography]     — JWT RS256 (Enable Banking)
- python-dotenv           — secrets .env
- weasyprint, jinja2      — génération PDF factures
- pytest, ruff, black     — tooling

# Frontend
- next, react             — UI
- tailwindcss             — styles responsive
- recharts                — graphiques dashboard/forecast
- eslint, prettier, vitest — tooling
```

---

## 2. System Overview

```
┌───────────────────────────────────────────────────────────┐
│                 FRONTEND (Next.js, :3000)                  │
│  Dashboard · Transactions · Forecast · Factures            │
│  API client (fetch) → backend                              │
└───────────────────────────┬───────────────────────────────┘
                            │ HTTP (localhost)
                            ↓
┌───────────────────────────────────────────────────────────┐
│                 BACKEND (FastAPI, :8000)                   │
│  routes/ → services/ → db (SQLAlchemy)                     │
│  ┌─────────┬──────────┬──────────┬──────────┬──────────┐  │
│  │ banking │categorize│ treasury │ forecast │ invoices │  │
│  └─────────┴──────────┴──────────┴──────────┴──────────┘  │
│         │                                    │            │
│         ↓ httpx (pull, à la demande)          ↓ WeasyPrint │
│  ┌──────────────┐                     ┌───────────────┐   │
│  │ Enable Banking│                     │  PDF factures │   │
│  └──────────────┘                     └───────────────┘   │
│         ↕                                                  │
│  ┌──────────────────────────────────────────────────┐    │
│  │ Logger (logs/backend_*.log, api_*.log)           │    │
│  └──────────────────────────────────────────────────┘    │
└───────────────────────────┬───────────────────────────────┘
                            ↓
                   ┌─────────────────┐
                   │ SQLite (local)  │  data/lgc.db
                   └─────────────────┘
```

**Data flow :** clic « Synchroniser » → `banking` pull Enable Banking → dédup → `categorize` applique les règles → `treasury` recompute soldes/EUR → `invoices` rapproche paiements → UI relit via API.

---

## 3. Component Breakdown (backend `services/`)

- **banking** — connexion OAuth (aspsps, connect, sessions), pull transactions + soldes, dédup, résolution `external_id`, signe des montants.
- **categorize** — moteur de règles (contrepartie/description → catégorie), fallback « à catégoriser », re-catégorisation.
- **treasury** — consolidation soldes bancaires + actifs manuels ; calcul `amount_eur` via rattachement des conversions FX Revolut ; P&L mensuel.
- **forecast** — projection mensuelle (jours×TJH×fx par client) + charges moyennes + déroulé tréso + estimation IS.
- **invoices** — numérotation, rendu PDF (Jinja2+WeasyPrint), rapprochement paiement→facture.

Chaque service = une responsabilité, testable isolément, interface claire (fonctions pures autant que possible ; I/O DB en bordure).

---

## 4. Data Model (SQLite via SQLAlchemy)

```
settings (singleton)
  company_name, siret, naf, tva_intracom, address
  is_low_rate=0.15, is_threshold=42500, is_high_rate=0.25
  next_invoice_number (seed=62), default_fx_usd, default_fx_cad

clients
  id, code ('SWIB'|'NWH'), legal_name, address, currency ('USD'|'CAD'),
  tjh, pay_iban, counterparty_match (pour rapprochement paiement)

bank_accounts
  id, provider ('revolut'|'qonto'), account_uid UNIQUE, currency,
  iban_masked, name, balance, last_synced_at,
  opening_balance, opening_balance_date (=2026-01-01, saisie manuelle)

transactions
  id, account_uid FK, external_id, booked_date, value_date,
  amount NUMERIC, currency, description, counterparty,
  category_id FK, kind ('revenue'|'charge'|'conversion'|'transfer'|'investment'|'other'),
  fx_rate, amount_eur, linked_conversion_id FK(self, nullable),
  invoice_id FK(nullable), raw_json, created_at
  UNIQUE(account_uid, external_id)

categories
  id, name, type ('revenue'|'charge'|'conversion'|'transfer'|'internal'|'uncategorized'),
  parent_id FK(self, nullable), is_system

category_rules
  id, match_field ('counterparty'|'description'), pattern, category_id FK,
  priority, enabled

invoices
  id, number UNIQUE, client_id FK, period_label, period_start, period_end,
  hours, rate, currency, amount, issue_date, due_date,
  status ('draft'|'sent'|'paid'), paid_transaction_id FK(nullable),
  pdf_path, created_at

investments   (ex-manual_assets)
  id, label, type ('crypto'|'bourse'|'placement'|'autre'),
  currency ('EUR'|'USD'|'CAD'|...),
  opening_value (devise native, placements pré-année) + opening_value_eur (converti),
  current_value  (devise native)                      + current_value_eur (converti),
  as_of_date, note
  -- gain/perte par devise = current_value − opening_value − apports année (transactions kind='investment')
  -- valeurs d'ouverture pré-année s'ajoutent au solde d'ouverture de leur devise (position de départ réelle)
  -- gain net positif agrégé EUR → base IS (S5.3)

forecast_inputs
  id, month (YYYY-MM), client_id FK, days, rate, fx_rate, note
```

**Relations :** client 1—N invoices ; invoice 0/1—1 transaction (paiement) ; transaction N—1 category ; transaction 0/1—1 conversion (self) ; account 1—N transactions.

---

## 5. Folder Structure
```
compta_sasu/
├── backend/
│   ├── api/
│   │   ├── main.py                 # FastAPI + CORS + lifespan
│   │   ├── routes/                 # banking, transactions, categories,
│   │   │                           # treasury, forecast, invoices, settings
│   │   └── schemas.py              # Pydantic
│   ├── services/                   # banking, categorize, treasury, forecast, invoices
│   ├── db/
│   │   ├── models.py               # SQLAlchemy
│   │   ├── session.py
│   │   └── migrations/             # Alembic
│   ├── templates/invoice.html      # Jinja2 (WeasyPrint)
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── app/                        # dashboard, transactions, forecast, invoices
│   ├── src/{components,api,types}/
│   └── package.json
├── data/                           # lgc.db + invoices/*.pdf (gitignored)
├── logs/                           # gitignored
└── docs/…                          # (existant)
```

---

## 6. Environment Variables
| Variable | Description | Exemple |
|---|---|---|
| `ENABLE_BANKING_APP_ID` | App ID (portail Enable Banking) | `uuid` |
| `ENABLE_BANKING_PRIVATE_KEY_PATH` | Chemin vers la clé PEM RS256 (fichier local gitignored) | `./secrets/eb_private.pem` |
| `ENABLE_BANKING_REDIRECT_URL` | Callback OAuth local | `http://localhost:3000/banking/callback` |
| `DATABASE_URL` | Connexion SQLite | `sqlite:///./data/lgc.db` |
| `LOG_LEVEL` | Verbosité | `INFO` |

> En local, on stocke la **vraie clé PEM** dans un fichier gitignored (pas les soucis de newlines de Railway). Si migration cloud → repasser au body base64 reconstruit au runtime (cf. blueprint).

---

## 7. API Design (principaux endpoints)
| Method | Endpoint | Rôle |
|---|---|---|
| GET | `/api/banking/aspsps?country=FR` | Liste des banques (jamais hardcodée) |
| POST | `/api/banking/connect` | Démarre OAuth → URL d'autorisation |
| POST | `/api/banking/sessions` | Échange le `code` → crée session + comptes |
| GET | `/api/banking/connections` | Comptes connectés |
| POST | `/api/banking/sync` | Pull transactions + soldes (dédup) |
| GET | `/api/transactions` | Liste filtrée (date, catégorie, statut) |
| PATCH | `/api/transactions/{id}` | Éditer catégorie / lien conversion / facture |
| GET/POST/PATCH | `/api/categories`, `/api/category-rules` | Catégories & règles |
| GET | `/api/treasury` | Tréso consolidée (banques + actifs manuels) |
| GET/POST | `/api/manual-assets` | Crypto / bourse |
| GET | `/api/pnl?year=2026` | P&L mensuel EUR |
| GET/PUT | `/api/forecast` | Entrées + projection + estimation IS |
| GET/POST | `/api/invoices` · POST `/api/invoices/{id}/pdf` | Factures + PDF |
| GET/PUT | `/api/settings` | Paramètres société / barèmes / seed n° facture |

---

## 8. Key Technical Decisions
| Décision | Options | Choix | Raison |
|---|---|---|---|
| Base de données | SQLite vs Postgres | **SQLite** local | Mono-utilisateur, zéro infra ; schéma portable Postgres |
| Synchro bancaire | Webhook (push) vs Pull (bouton) | **Pull à la demande** | Local, pas d'endpoint public ; simple et suffisant |
| Génération PDF | WeasyPrint vs ReportLab vs fpdf2 | **WeasyPrint** | Fidélité HTML/CSS à la facture Word actuelle |
| Auth | Supabase Auth vs none | **none** (v1) | Local non exposé (NG3, Constraints) |
| Catégorisation | LLM vs règles | **Règles éditables** | Déterministe, gratuit, testable ; LLM = v2 |
| Stockage clé EB | .env inline vs fichier PEM | **Fichier PEM gitignored** | Local : évite les soucis de newlines |

---

## 9. Integration Seams — à vérifier AVANT de coder
| Dépendance | Contrat de format | Edge cases | Comment valider avant de coder |
|---|---|---|---|
| Enable Banking — ASPSP | Noms possédés par l'API — jamais hardcoder | Nom faux → `422 WRONG_ASPSP_PROVIDED` | Appeler `GET /aspsps?country=FR`, vérifier que **Revolut Business** et **Qonto** y figurent (résout Q2) |
| Enable Banking — dédup | `transaction_id` / `entry_reference` / `internal_transaction_id` | Trades FX Revolut : même `transaction_id` sur 2 comptes | Clé unique **(account_uid, external_id)**, jamais `external_id` seul |
| Enable Banking — JWT | RS256, `kid`=App ID, exp 1h | Clé PEM mal formée | En local : PEM fichier valide ; tester un `GET /aspsps` authentifié |
| Enable Banking — redirect | URL enregistrée = octet pour octet identique | **https parfois exigé** vs `http://localhost` | ⚠️ **RISQUE** : vérifier si le portail accepte un callback localhost ; sinon tunnel/loopback https. À tester au 1er branchement |
| Enable Banking — consentement | `access.valid_until` ~90 j | Expiration silencieuse | Stocker l'expiration, afficher un rappel de reconnexion |
| Montants | `credit_debit_indicator` DBIT/CRDT | Signe | DBIT → négatif, CRDT → positif |
| Rattachement FX EUR | Crédit devise ↔ conversion Revolut vers EUR Main | Conversion partielle / différée | Heuristique (devise+montant+date proche) + **lien manuel** en secours |

**Règle :** une colonne non remplie = risque à lever avant de figer l'archi. Le seul flag ouvert = **callback localhost vs https** (à tester au branchement).

---

## 10. Known Limitations & Technical Debt
- [ ] SQLite mono-writer — OK mono-utilisateur ; concurrence = migration Postgres.
- [ ] Rapprochement FX heuristique — lien manuel requis dans les cas ambigus.
- [ ] IS = estimation simplifiée (barèmes bruts) — pas les règles fiscales complètes.
- [ ] Pas d'auth — dépend du non-exposé local.

## 10bis. Platform Gotchas
- **WeasyPrint** dépend de libs système (pango, cairo, gdk-pixbuf) → `brew install pango` sur macOS. Fallback `fpdf2` si blocage.
- **SQLite** : activer les FK (`PRAGMA foreign_keys=ON`) ; NUMERIC pour montants (pas de float sur l'argent → `Decimal`).
- **Enable Banking** : callback localhost à valider (cf. §9) ; consentement 90 j.
- **CORS** : autoriser `http://localhost:3000` ; middleware CORS en couche la plus externe.

---

## 11. Performance & Scalability
- Charge attendue : 1 utilisateur, ~30-60 transactions/mois, 4-5 comptes.
- Rupture : usage multi-utilisateur/concurrent → migrer SQLite→Postgres + auth + hosting.

---

## 📤 Outputs for 4-LOGGING.md
Stack (Python/FastAPI + Next.js) · composants (5 services) · fichiers `logs/backend_*.log`, `api_*.log`, `frontend_*.log` · `LOG_LEVEL` · masquage IBAN/PII.
