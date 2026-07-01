# Architecture Decision Records (ADR)

## TL;DR
- Log every significant technical decision here (if wrong = 2+ hours to undo)
- Check this BEFORE making architectural changes — don't contradict past decisions
- Never delete/modify entries — append only
- To override a past decision: add a new ADR referencing the old one

---

## ADR Index
| ID | Title | Status | Date | Epic |
|---|---|---|---|---|
| ADR-001 | SQLite local (portable Postgres) comme base | Accepted | 2026-07-01 | Pre-epic |
| ADR-002 | Synchro bancaire par pull à la demande (pas de webhook) | Accepted | 2026-07-01 | Pre-epic |
| ADR-003 | WeasyPrint (HTML+CSS) pour la génération des factures | Accepted | 2026-07-01 | Pre-epic |
| ADR-004 | Pas d'auth en v1 (local mono-utilisateur non exposé) | Accepted | 2026-07-01 | Pre-epic |
| ADR-005 | Catégorisation par règles éditables (pas de LLM en v1) | Accepted | 2026-07-01 | Pre-epic |
| ADR-006 | Taux FX théorique par devise (Réglages) comme source unique de conversion EUR | Accepted | 2026-07-01 | Epic-4 |

### ADR-001 — SQLite local, schéma portable Postgres
**Context :** outil perso mono-utilisateur, local-first (PRD Constraints §9), migration cloud possible plus tard.
**Décision :** SQLite via SQLAlchemy + Alembic ; montants en `Decimal`/NUMERIC ; FK activées.
**Conséquences :** zéro infra ; un seul writer (OK 1 user) ; migration Postgres = changer l'URL + review types.

### ADR-002 — Synchro par pull à la demande
**Context :** local, pas d'endpoint HTTPS public → webhook Enable Banking impossible sans hosting.
**Décision :** bouton « Synchroniser » → pull transactions + soldes ; pas de webhook en v1.
**Conséquences :** simple, suffisant pour un tableau de bord consulté ; pas de temps réel (acceptable).

### ADR-003 — WeasyPrint pour les factures
**Context :** reproduire fidèlement la mise en page des factures Word (mentions légales, IBAN par devise).
**Décision :** template Jinja2 HTML/CSS → PDF via WeasyPrint.
**Conséquences :** haute fidélité ; dépendance libs système (`brew install pango`) ; fallback `fpdf2` si blocage.

### ADR-004 — Pas d'auth en v1
**Context :** app locale non exposée (NG3, Constraints §9).
**Décision :** aucune authentification en v1.
**Conséquences :** simplicité ; devient un pré-requis obligatoire dès qu'on héberge (v2 cloud).

### ADR-005 — Catégorisation par règles
**Context :** besoin déterministe, testable, gratuit ; données bancaires sensibles.
**Décision :** moteur de règles éditables (contrepartie/description → catégorie), fallback « à catégoriser ».
**Conséquences :** transparent et corrigeable ; « catégo intelligente » LLM = piste v2.

### ADR-006 — Taux FX théorique par devise comme source unique de conversion EUR
**Context :** les transactions/soldes restent en devise native (Qonto EUR, Revolut USD/CAD…). On ne peut jamais additionner bêtement des devises différentes. Il faut un reporting consolidé en EUR (total tréso + P&L + IS) et des prévisions saisies dans une devise puis converties.
**Décision :** un taux théorique par devise stocké dans `fx_rates` (devise → EUR, EUR=1), éditable dans les Réglages. Table = source unique de vérité ; `amount_eur`/`fx_rate` figés sur la transaction sont **ignorés** pour les agrégats (montant natif × taux courant). Les devises listées sont uniquement celles présentes dans les transactions/comptes ; une devise sans taux est signalée « à renseigner » (fallback 1). Le vrai taux réalisé remplacera le théorique quand la transaction arrivera (forecast → réel).
**Conséquences :** cohérence totale des agrégats EUR ; un seul endroit à corriger ; solde par devise toujours exact en natif ; risque de sous-estimation si un taux manque (mitigé par le flag `missing`). Impacte `services/fx.py`, `treasury.py`, `pnl.py`, `forecast.py`, route `/api/fx-rates`, écran Réglages.

---

## Planning Lessons — Specification gaps to check before every plan

These are categories of gaps that consistently cause bugs or delays. Use as a checklist when writing plans.

### Category A — External API contracts
| # | Gap to avoid | What the spec must include |
|---|---|---|
| A1 | Hardcoding API values that are owned by the external service | "Names/IDs are enum values owned by the API. Always fetch from the API — never hardcode." |
| A2 | Assuming one global unique ID per entity across accounts | "Check whether the external system scopes IDs per account or globally. Dedup must match." |
| A3 | Undefined history window for sync/import operations | "Specify: how far back on first sync, how far back on subsequent syncs, whether user can control it." |

### Category B — Infrastructure & secrets
| # | Gap to avoid | What the spec must include |
|---|---|---|
| B1 | Unspecified secret format for hosting platform | "Specify exact storage format. Document that multi-line secrets must be stored single-line and reconstructed at runtime." |
| B2 | Relying on package extras for critical transitive deps | "Always pin transitive dependencies explicitly. Never rely on extras to pull in critical packages." |
| B3 | Env var formatting issues not anticipated | "After adding any secret to the hosting platform, verify in raw editor — no trailing chars, newlines, or quotes." |

### Category C — Framework behaviour
| # | Gap to avoid | What the spec must include |
|---|---|---|
| C1 | CORS middleware ordering left implicit | "State explicitly: CORS must be the outermost middleware layer. Register it last, after all middleware decorators." |
| C2 | External client instantiation outside error handler | "Every external client call at a system boundary must be inside the error handler. No exceptions." |

### Category D — Test design
| # | Gap to avoid | What the spec must include |
|---|---|---|
| D1 | Single mock return_value reused across multiple DB calls | "State the multi-call mock rule before any test is written: use side_effect=[...] when the same chain is called more than once." |
| D2 | Assertions wrapped in conditional guards | "Never wrap assertions in conditional guards. Assert unconditionally — a missing row is a test failure, not a no-op." |

### Meta-lesson
Most bugs happen at **integration seams** — where two systems meet. Every plan must include an "Integration assumptions to verify" section per external dependency, listing format contracts, known edge cases, and how to validate before coding. See `3-ARCHITECTURE.md` Section 9.

---

## ADR Template
> Copy this block for each new decision. One ADR per significant choice.
> What counts as "significant"? If getting it wrong would cost more than 2 hours to undo — write an ADR.

---

### ADR-001: [Decision Title]
**Date:** [DATE]
**Epic / Story:** EPIC-X / Story X.Y
**Status:** `Proposed` → `Accepted` → `Superseded by ADR-XXX`
**Decided by:** [Human / AI / Both]

#### Context
> What situation forced this decision? What constraints existed?

[Describe the context in 2-4 sentences.]

#### Decision
> What was decided? State it clearly and unambiguously.

**We will [do X] using [approach Y].**

#### Alternatives Considered
| Option | Pros | Cons | Reason Rejected |
|---|---|---|---|
| [Option A — chosen] | [pros] | [cons] | *Chosen* |
| [Option B] | [pros] | [cons] | [Why rejected] |

#### Consequences
**Positive:**
- [What this decision enables or improves]

**Negative / Trade-offs:**
- [What this decision constrains or makes harder]

**What this decision affects:**
- Files: `src/[file]`
- Modules: [which modules are shaped by this choice]

#### Review Triggers
- [ ] If [condition]

---

## 📌 Superseded Decisions
| Superseded ADR | Superseded By | Date | Reason |
|---|---|---|---|
