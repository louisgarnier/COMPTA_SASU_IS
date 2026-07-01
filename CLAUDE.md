## Project: LGC
One-liner: Web app locale qui remplace l'Excel manuel de suivi cashflow d'une SASU — importe les transactions bancaires via Open Banking (Enable Banking) pour piloter tréso, forecast, P&L, estimation IS et facturation sans ressaisie.
Current stage: EPIC-1..6 — MVP en construction (backend complet + front en cours)

## Non-goals — these are LAW, do not implement
- NG1 — Logiciel comptable complet (journal, grand livre, liasse) — ne remplace pas l'expert-comptable.
- NG2 — Déclaration/télétransmission fiscale réelle — l'IS est une **estimation**.
- NG3 — Multi-utilisateur / fonctions d'équipe.
- NG4 — Hébergement cloud / synchro auto 24-7 (reporté v2 ; v1 = local + synchro manuelle).
- NG5 — OCR de tickets/reçus — les factures sont **générées** (sortantes), pas scannées.
- NG6 — Open Banking crypto/bourse — saisie **manuelle** uniquement.
- NG7 — Gestion de TVA — SASU en franchise en base (art. 293 B), aucune TVA.
- NG8 — Rapprochement FX 100 % auto au-delà du lien conversion Revolut — lien **manuel** de secours accepté.

## Stack
- Frontend: Next.js 16 (App Router) + React 19 + TypeScript + Tailwind v4 (`:3000`)
- Backend: FastAPI + SQLAlchemy 2.0 (`:8000`), services (banking, categorize, treasury, pnl, forecast, invoices)
- Database: SQLite local (`data/lgc.db`), montants en `Decimal`, FK activées
- Intégrations: Enable Banking (Open Banking, mode mock sans creds) · WeasyPrint (PDF factures, lazy) · PyJWT (RS256)
- Lancement: `make dev` (back+front) · `make seed` (données démo) · `make test`

## Session start — read these files in order before any code
1. `docs/project/config/build-log.md` — current stage + blockers
2. `docs/project/config/codebase.md` — existing modules
3. `workflow/ERRORS.md` — known problem areas
4. `workflow/ADR.md` — architectural decisions already made
5. `docs/project/config/epics/ACTIVE.md` — current story (once epics are defined)

## Sealed files — never read or modify during development
- `docs/project/testing/BLIND_SCENARIOS.md`
