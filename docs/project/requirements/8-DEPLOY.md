# 🚀 Stage 8 — Deploy & Observability

> **Output →** `docs/project/config/deploy.md`
> **Instructions:** Production readiness gate. Run this stage AFTER Step 7 wrap-up is complete and BEFORE the first production push.
> Status: `[ ] Draft` → `[ ] Staging verified` → `[ ] Locked` → `[ ] Live`

## 📥 Inputs from earlier stages
- **`3-ARCHITECTURE.md`** → deployment target, env structure, secrets list, scaling assumptions
- **`4-LOGGING.md`** → log destinations, retention, redaction rules
- **`6-BUILD.md`** → all Story Sign-Off gates green (security / performance / a11y / simplification)
- **`workflow/ADR.md`** → any deploy-time architectural decisions
- **`workflow/ERRORS.md`** → known failure modes that need monitoring

---

## Overview

A working build is not a deployable build. This stage forces explicit answers to:
- What environment config has to be set?
- What can break the database during this deploy?
- How do we roll back when it does?
- How do we know if something fails in prod?
- What gets smoke-tested before we call it live?

Code that ships without this stage will eventually surprise the user — and the surprise will be silent because nothing is watching.

---

## §1 — Environment configuration

List every env var the app needs in production. Mark which are present in `.env.example`.

| Var | Purpose | Source | In .env.example? | Set in deploy env? |
|---|---|---|---|---|
| `DATABASE_URL` | Postgres connection | infra | ✅ / ❌ | ✅ / ❌ |
| `LOG_LEVEL` | runtime logging level | choice | ✅ / ❌ | ✅ / ❌ |
| `SENTRY_DSN` | error tracking | secret | ✅ / ❌ | ✅ / ❌ |
| ... | | | | |

**Sign-off:**
- [ ] Every entry in `.env.example` has a value in the deploy environment
- [ ] No real secrets in `.env.example` — placeholders only
- [ ] `.gitignore` covers `.env`, `.env.local`, `*.pem`, `*.key`

---

## §2 — Database & migrations safety

> Invoke `postgres-best-practices` skill before filling this section.

| Item | Answer |
|---|---|
| Are there pending migrations? | Yes / No |
| Migration command | `[e.g. alembic upgrade head]` |
| Forward-compatible? (old code can still run while migration applies) | ✅ / ❌ |
| Is any column being dropped or renamed? | ✅ / ❌ — if yes, multi-phase plan needed |
| Index creation: built `CONCURRENTLY`? | ✅ / ❌ / N/A |
| Estimated runtime on prod row count | `[duration]` |
| Dry-run executed on staging copy of prod data? | ✅ / ❌ |
| Rollback procedure documented in `deploy.md`? | ✅ / ❌ |

**Sign-off:**
- [ ] Migration dry-run passed against staging
- [ ] Rollback steps tested (not just written)

---

## §3 — Observability & monitoring

| Layer | What's wired | Smoke test |
|---|---|---|
| Backend errors | `[Sentry / OTel / Cloudwatch / ...]` | Triggered a deliberate `raise` and confirmed it surfaced in dashboard |
| Frontend errors | `[Sentry SDK / window.onerror / ...]` | Triggered a deliberate throw in browser, confirmed surfaced |
| HTTP latency | `[APM / structured logs / ...]` | Confirmed p95 metric is visible |
| Logs | `logs/backend_*.log` (dev) → `[prod sink]` | Confirmed logs reach the prod sink |
| Alerts | `[on-call rule / Slack / PagerDuty]` | Test alert fired and received |

**Sign-off:**
- [ ] At least one error tracker wired for each layer of the stack
- [ ] Each layer's smoke test produced a visible event in the dashboard
- [ ] At least one alert rule exists for "error rate > threshold"

---

## §4 — Rollback plan

| Question | Answer |
|---|---|
| Deploy mechanism | `[git push / CI artifact / container / manual]` |
| Rollback mechanism | `[revert commit / redeploy previous tag / blue-green / ...]` |
| Estimated rollback time | `[< 5 min / < 30 min / ...]` |
| Data rollback possible? | ✅ / ❌ / Partially |
| If migrations applied, can previous code run against new schema? | ✅ / ❌ |
| Decision authority for rollback | `[user / on-call / ...]` |

**Sign-off:**
- [ ] Rollback procedure rehearsed (or at minimum walked through step-by-step in dry-run)
- [ ] Previous deploy artifact / commit hash recorded in `deploy.md` before push

---

## §5 — Pre-deploy gate (all required)

> Tick every box. Any unchecked box blocks the deploy.

### Stories & builds
- [ ] All stories in `epics/overview.md` marked `[x] Done`
- [ ] `build-log.md` Definition of Done checklist 100% complete
- [ ] `codebase.md` reflects current modules and data flows

### Quality gates from Step 6
- [ ] Every story passed its security gate (or marked N/A in sign-off)
- [ ] Every story passed its performance gate (or marked N/A)
- [ ] Every UI story passed its a11y gate (or marked N/A)
- [ ] `webapp-testing` E2E suite green against staging

### Production hygiene
- [ ] §1 env config: every required var set in deploy env
- [ ] §2 migration: dry-run passed on staging copy, rollback documented
- [ ] §3 observability: all layers wired and smoke-tested
- [ ] §4 rollback: mechanism documented, previous artifact recorded
- [ ] No leftover `print` / `console.log` / debug routes
- [ ] No commented-out dead code in changed files

### Secrets review
- [ ] `git diff --cached | grep -iE "password|secret|api_key|token"` returns no real values
- [ ] All third-party API keys scoped to minimum permissions

---

## §6 — Smoke test plan (post-deploy)

After deploy, before declaring success:

| Check | How | Pass criterion |
|---|---|---|
| App responds | `curl https://[prod]/health` | 200 OK with expected payload |
| Critical user path | Manual or scripted | Login → core action → logout works |
| Errors surface | Trigger known-bad request | Error visible in tracker within 1 min |
| Logs flow | Tail prod log sink | Lines appear matching the test traffic |
| Database reachable | Run a known SELECT | Returns expected row |

**Smoke test outcome:**
```
Date: [YYYY-MM-DD]
Operator: [name]
Result: ✅ PASS / ❌ FAIL — [details]
Action on FAIL: [rollback executed / ticket filed / etc.]
```

---

## 📤 Outputs

- `docs/project/config/deploy.md` — fully filled, status `Locked`
- `workflow/ADR.md` — any deploy-time decision (e.g. blue-green vs in-place) appended
- `workflow/ERRORS.md` — any deploy-time failure appended with prevention rule

```
✅ Deploy stage complete on: [DATE]
✅ Production live on: [DATE]
→ Project enters maintenance mode. New work cycles back to Stage 5 (new Epic) or Stage 6 (next story).
```
