# Active Context

## Current Sprint
- **Epic:** MVP EPIC-1 → 6 — **code complet, testable** (mode "bombarde tout", sans checkpoints)
- **Story:** — *(à définir après revue front par l'utilisateur)*
- **Goal:** L'utilisateur teste le front (`make dev` + `make seed`), puis on itère sur les retours.
- **À faire ensuite (hors code) :** brancher WeasyPrint (`brew install pango`), creds Enable Banking pour synchro réelle, migrations Alembic.

## Completed
- **S1.1 — Scaffold back + front** *(2026-07-01)* — FastAPI `/health` + Next.js, `make dev`, tests verts.
- **MVP EPIC-1 → 6 — backend + front** *(2026-07-01)* — 9 modèles DB, 6 services, 27 endpoints, 7 pages front, seed démo. 60 tests back + 7 front verts, `next build` OK, 7 pages vérifiées visuellement.
- **EPIC-5 facturation — cycle de vie complet** *(2026-07-03)* — ① client card · ② fusion forecast→facture (statuts forecast/due/paid, anti-doublon) · ③ grille Forecast horaire (TJM/THM, année, N clients) · ④ génération facture (page imprimable fidèle .docx, IBAN/mentions) · ⑤ rapprochement manuel tx↔facture + variance forecast/réel. **117 tests back + 9 front verts**, tsc clean. Cf. `build-log.md`.
