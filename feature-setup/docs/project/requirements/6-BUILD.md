# 🔨 Stage 6 — Build Log & Iteration Journal
> **Output →** `docs/project/config/build-log.md`
> **Instructions:** Updated by the AI after EVERY session. This is the project's live memory.
> Newest session entries go at the TOP of the Session Log.
>
> ⚠️ TWO DISTINCT TESTING LAYERS — never confuse them:
> - **Build Tests** (this file) → run during dev, per story, prove "I built this correctly"
> - **Blind Scenarios** (`../testing/BLIND_SCENARIOS.md`) → run AFTER dev, prove "the solution works overall"

## 📥 Inputs from 5-EPICS.md
- **Epic Structure** → Organize sessions by epic progression
- **Story Breakdown** → One story per session, follow story sequence
- **Acceptance Criteria** → Use as session sign-off requirements
- **Task Lists** → Track specific actions completed in each session
- **Test Requirements** → Write dev tests per story specifications
- **Dependencies** → Respect story sequencing and blockers
- **Current Status** → Update epic/story progress tracking

---

## ⚡ Current Session
```
Date:
Working on: EPIC-X / Story X.Y — [Name]
Goal for this session:
```

---

## 📊 Project Health Dashboard
| Metric | Status |
|---|---|
| Dev tests passing | ✅ / ❌ [X/Y passing] |
| Linter clean | ✅ / ❌ |
| Open blockers | [N] |
| Stories completed | [X / Y total] |
| Last working state | [commit hash or description] |

---

## 🚧 Active Blockers
> *Things preventing progress. Must be resolved before moving on.*

| # | Blocker | Since | Resolution |
|---|---|---|---|
| B1 | | | |

---

## ✅ Session Log
> Each entry follows the same structure: Build → Test → Log Evidence → Sign-Off.
> A story is NOT done until its tests pass and log evidence is recorded.

---

### [DATE] — Session [N]

#### 📦 What Was Built
**Story:** EPIC-X / Story X.Y — [Story Name]
**Objective:** [One-sentence goal for this session]

**Code changes:**
- `src/[file]` — [what was added/changed and why]
- `tests/dev/[file]` — [tests written for this story]

**Decisions made:**
- [Decision] → [Reason]

---

#### 🧪 Build Tests — Story X.Y
> Tests that prove THIS story works. Written in the same session as the code.

| Test | File | What It Covers | Result |
|---|---|---|---|
| `test_[name]` | `tests/dev/test_[module].py` | Happy path: [describe] | ✅ / ❌ |
| `test_[name]` | `tests/dev/test_[module].py` | Edge case: [describe] | ✅ / ❌ |
| `test_[name]` | `tests/dev/test_[module].py` | Failure case: [describe] | ✅ / ❌ |

**Run command:** `pytest tests/dev/test_[module].py -v`

**Test result summary:**
```
[Paste or summarize pytest/vitest output here]
e.g.  3 passed, 0 failed in 0.45s
```

---

#### 📋 Log Evidence
> Logs are proof the build is working — not just that tests pass.
> Paste key log lines showing the feature behaving correctly in practice.

**Log location:** `[logs/app.log / stdout / etc.]`

```
[Paste relevant log snippet]

e.g.
2024-03-11 14:22:01 INFO  [ingestion] Loaded 1,432 rows from raw/data.csv
2024-03-11 14:22:01 INFO  [ingestion] Schema validated — all required columns present
2024-03-11 14:22:02 INFO  [ingestion] 0 duplicates found, 1,432 rows written to interim/
```

**What the logs confirm:**
- ✅ [e.g. Data loaded correctly]
- ✅ [e.g. Errors surface explicitly — no silent failures]
- ✅ [e.g. Row counts consistent at input and output]

---

#### 🔒 Story Sign-Off
- [ ] Code written and working
- [ ] Tests written (same session, not after)
- [ ] All tests passing
- [ ] Log evidence recorded above
- [ ] Story marked `[x] Done` in `docs/4-EPICS.md`
- [ ] Linter clean

**Pre-sign-off engineering gates** (skip the row only if N/A — mark why):
- [ ] **Interface design** (if new API / module / component contract): `api-and-interface-design` skill invoked → Hyrum's-Law-aware contract chosen
- [ ] **Security pass** (if story touches user input / auth / data / external services): `security-and-hardening` skill invoked → `SECURITY-CHECKLIST.md` rows ticked or marked N/A
- [ ] **Performance pass** (if PRD has perf budget or Core Web Vitals target): `performance-optimization` skill invoked → measurement recorded → `PERFORMANCE-CHECKLIST.md` rows ticked
- [ ] **Simplification pass** (tests are green; implementation feels heavy): `code-simplification` skill invoked → simplifications committed separately from feature commit

**Commit:** `[EPIC-X] feat: description` — `[hash]`
**Next session:** EPIC-X / Story X.Y+1 — [Name]

---

### [DATE] — Session [N-1]
*(duplicate the full session block above for each new session)*

---

## 🧪 Cumulative Dev Test Status
> Master view across all sessions. Updated each session.

| Module | Test File | Tests | Passing | Coverage |
|---|---|---|---|---|
| [module] | `tests/dev/test_[module].py` | [N] | ✅ / ❌ | [%] |

**Last full suite run:** [date]
**Command:** `pytest tests/dev/ --cov=src -v`
```
[Paste last full run summary]
e.g.  12 passed, 0 failed — coverage: 84%
```

---

## 🔄 Key Decisions Log
> Architectural or approach decisions made *during* the build.
> (Pre-build decisions live in `docs/3-ARCHITECTURE.md`)

| Date | Decision | Alternatives Considered | Reason |
|---|---|---|---|
| | | | |

---

## 📦 Dependencies Added During Build
> Every package must have been approved in `docs/3-ARCHITECTURE.md` first.

| Package | Date Added | Reason | Approved in Architecture? |
|---|---|---|---|
| | | | ✅ / ❌ |

---

## 🏁 Definition of Done — Pre-Scenario Checklist
> Complete ALL of these before opening `tests/blind/SCENARIOS.md`.
> The build is not done until this checklist is fully checked.

### Code
- [ ] All EPIC stories marked `[x] Done` in `docs/4-EPICS.md`
- [ ] No hardcoded credentials or paths
- [ ] No leftover debug `print` / `console.log` statements
- [ ] No commented-out dead code

### Tests
- [ ] Every story has corresponding tests in `tests/dev/`
- [ ] Full dev test suite passes: `pytest tests/dev/` → 0 failures
- [ ] Coverage ≥ 80% (or justified exception documented here)
- [ ] Log evidence recorded for each story in the session log above

### Quality
- [ ] Linter passes with 0 warnings (`ruff` / `eslint`)
- [ ] Formatter applied (`black` / `prettier`)
- [ ] All functions have docstrings / JSDoc

### Documentation
- [ ] `README.md` accurately reflects current setup and usage
- [ ] `.env.example` matches all current variables
- [ ] `docs/project/requirements/6-BUILD.md` is fully up to date (this file)

### Final check
- [ ] Full end-to-end smoke test passes with sample data
- [ ] `3-ARCHITECTURE.md` reflects any changes made during build

---

## 📤 Outputs for 7-CODEBASE.md

**After EVERY session, these outputs must be updated in the codebase documentation:**

- **New Modules Created** → CODEBASE Section: Codebase Map (add new files)
- **Module Documentation** → CODEBASE individual module sections (purpose, exports, usage)
- **Data Flow Changes** → CODEBASE Section: Data Flows (update flow diagrams)
- **Dependencies Added** → CODEBASE Section: Dependency Map (track new imports)
- **Technical Debt** → CODEBASE Section: Known Technical Debt (document shortcuts)
- **Architectural Changes** → CODEBASE change log entries (what changed and why)
- **Session Decisions** → Feed into `../../../workflow/ADR.md` (significant technical choices)
- **Bugs Encountered** → Feed into `../../../workflow/ERRORS.md` (problems found and fixed)

---

```
✅ Definition of Done complete on: [DATE]

→ Now open ../testing/BLIND_SCENARIOS.md and run scenarios cold.
→ Do NOT pre-test or prepare — the point is that the code faces them blind.
```
