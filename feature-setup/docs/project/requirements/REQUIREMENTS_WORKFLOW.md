# Project Development Workflow

This is the **master checklist** for developing a new project from scratch. Follow each numbered file in sequence, checking off steps as you complete them.

## Workflow Overview

```
PLAN IT:   1-BRAINSTORM → 2-PRD → 3-ARCHITECTURE → 4-LOGGING
BUILD IT:  5-EPICS → 6-BUILD → 7-CODEBASE
SHIP IT:   8-DEPLOY  (production readiness gate)
```

**Per-story checklists** (referenced from `6-BUILD.md` Story Sign-Off):
- `SECURITY-CHECKLIST.md` — OWASP, auth, input validation, secrets
- `PERFORMANCE-CHECKLIST.md` — Core Web Vitals, backend latency, common anti-patterns
- `ACCESSIBILITY-CHECKLIST.md` — semantic HTML, keyboard nav, contrast, ARIA

**Continuous Workflow Tools** (updated throughout development):
- `../../../workflow/ADR.md` - Architecture Decision Records
- `../../../workflow/ERRORS.md` - Known Errors Registry

---

## Agent Skills — Use These at Each Stage

This workflow is designed to be executed with **Superpowers skills**. Each stage maps to a skill. The agent must invoke the skill before starting the stage — not after.

| Stage | Skill to invoke | Purpose |
|---|---|---|
| Stage 1 — Brainstorm | `superpowers:brainstorming` | Structured idea validation before any spec is written |
| Stage 3 — Architecture | `superpowers:writing-plans` | Generates the implementation plan from the locked architecture |
| Stage 5 — Epics execution | `superpowers:subagent-driven-development` | Executes plan one task at a time with spec + quality review per task |
| Branch setup | `superpowers:using-git-worktrees` | Isolated workspace per feature — required before any code is written |
| Branch completion | `superpowers:finishing-a-development-branch` | Structured merge/PR/discard decision after all tasks pass |

**Rule:** Skills and this workflow run in parallel — the workflow defines WHAT to do, skills define HOW to execute it. Neither replaces the other.

---

## Check-In Cadence — Required

```
One task → stop → report to user → wait for approval → next task
```

- The agent completes **one task**, then stops and reports
- User reviews and says "go" or "next" before the agent continues
- The agent never chains multiple tasks without a check-in
- This applies even when using subagent-driven-development — the orchestrating agent checks in with the user between tasks, not just between epics

---

## Master Checklist

### 🎯 PLANNING PHASE

#### [ ] Stage 1: Brainstorm & Idea Validation
**File**: `1-BRAINSTORM.md`
**Trigger**: *"Let's start the brainstorm for [project name]"* — or run `python scripts/brainstorm.py`
- [ ] §0: Freeform input (raw thoughts, any format)
- [ ] §1: Define the one-liner (no conjunctions)
- [ ] §2: Identify the problem (who / current solution / why inadequate)
- [ ] §3: Describe the solution (user's journey, high-level only)
- [ ] §4: List assumptions & risks
- [ ] §5: Complete feasibility check
- [ ] §6: Go/No-Go decision (includes success criteria)
- [ ] **Output**: `docs/project/config/brainstorm.md` with GO decision
- [ ] **Status**: `Draft` → `Validated` → `GO — proceed to PRD`

#### [ ] Stage 2: Product Requirements Document
**File**: `2-PRD.md`
- [ ] Complete project summary table
- [ ] Define goals & non-goals (AI guardrails)
- [ ] Write user stories with acceptance criteria
- [ ] List functional requirements (testable statements)
- [ ] Define non-functional requirements (performance, security)
- [ ] Document data requirements (if applicable)
- [ ] Map interfaces & integrations
- [ ] Set error handling policy
- [ ] List constraints
- [ ] Answer all open questions
- [ ] **Status**: `Draft` → `Reviewed` → `Locked`

#### [ ] Stage 3: Architecture & Technical Design
**File**: `3-ARCHITECTURE.md`
- [ ] Define complete tech stack with versions
- [ ] List all approved external packages
- [ ] Create system overview diagram
- [ ] Break down components (responsibility, input, output)
- [ ] Design data model (if applicable)
- [ ] Define folder structure
- [ ] List environment variables
- [ ] Design API (if applicable)
- [ ] Record key technical decisions
- [ ] Document known limitations
- [ ] Set performance assumptions
- [ ] **Status**: `Draft` → `Reviewed` → `Locked`

#### [ ] Stage 4: Logging Setup & Architecture
**File**: `4-LOGGING.md`
- [ ] Configure backend logging (timestamps, emojis, levels)
- [ ] Implement HTTP request logging middleware
- [ ] Set up frontend terminal logging (API proxy)
- [ ] Create browser console logger utility
- [ ] Configure database operation logging
- [ ] Set up log file structure (/logs directory)
- [ ] Define logging conventions (emojis, prefixes, levels)
- [ ] Configure environment variables (LOG_LEVEL)
- [ ] Test end-to-end logging flow
- [ ] **Status**: `Draft` → `Configured` → `Tested` → `Locked`

### 🔨 BUILDING PHASE

#### [ ] Stage 5: Epics & Stories
**File**: `5-EPICS.md`
- [ ] Break all work into Epics
- [ ] Create stories for each epic (1 session completable)
- [ ] Define tasks for each story
- [ ] Set dependencies between stories
- [ ] Write acceptance criteria for each story
- [ ] Estimate time for each story
- [ ] Plan dev tests for each story
- [ ] Update epic overview table
- [ ] Set current status section
- [ ] **Status**: Stories defined and prioritized

#### [ ] Stage 6: Build Log & Session Journal
**File**: `6-BUILD.md`
- [ ] Update current session info before each session
- [ ] Maintain project health dashboard
- [ ] Track active blockers
- [ ] Log each session (build → test → evidence → sign-off)
- [ ] Record cumulative test status
- [ ] Log key decisions made during build
- [ ] Track dependencies added
- [ ] Complete Definition of Done checklist before scenarios
- [ ] **Status**: Updated after every session

#### [ ] Stage 7: Codebase Documentation
**File**: `7-CODEBASE.md`
- [ ] Update codebase map after each story
- [ ] Document each module (purpose, exports, usage, design)
- [ ] Maintain data flow diagrams
- [ ] Update dependency map
- [ ] Record technical debt
- [ ] Follow naming conventions
- [ ] **Status**: Always current with codebase

### 🔧 CONTINUOUS WORKFLOW (Throughout Development)

These files are updated **continuously** during development, not at the end:

#### Architecture Decision Records
**File**: `../../../workflow/ADR.md`
- Record decisions **as you make them** during any stage
- Document context, alternatives, consequences
- Reference from BUILD sessions when making technical choices
- **Status**: Living document, append-only

#### Known Errors Registry
**File**: `../../../workflow/ERRORS.md`
- Log bugs **as you encounter them** during BUILD
- Document root cause and fix immediately
- Create prevention rules for future development
- **Status**: Living document, searchable registry

### 🧪 TESTING PHASE

#### [ ] Blind Test Scenarios
**File**: `../testing/BLIND_SCENARIOS.md`
- [ ] Complete Definition of Done checklist first
- [ ] Run scenarios cold (no pre-testing)
- [ ] Record results for each scenario
- [ ] Fix any failures and re-run all scenarios
- [ ] Complete blind test sign-off
- [ ] **Status**: Only run after development complete

## Best Practices

### Requirements Analysis
- ✅ Ask clarifying questions
- ✅ Identify edge cases
- ✅ Consider non-functional requirements
- ✅ Document assumptions
- ❌ Don't assume - clarify

### Functionality Breakdown
- ✅ Keep functionalities focused (single responsibility)
- ✅ Make steps actionable
- ✅ Identify dependencies clearly
- ✅ Include acceptance criteria
- ❌ Don't create overly large functionalities

### Step Definition
- ✅ Steps should be completable in 1-2 days
- ✅ Each step should have clear deliverables
- ✅ Include testing in steps
- ✅ Document dependencies
- ❌ Don't create vague or too-large steps

