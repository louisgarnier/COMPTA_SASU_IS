# 📋 Stage 2 — Product Requirements Document (PRD)
> **Output →** `docs/project/config/prd.md`
> **Instructions:** Drafted with AI, decisions made by you. This is the source of truth.
> The AI reads this before every session. Be precise — vague requirements = scope creep.
> Status: `[ ] Draft` → `[ ] Reviewed` → `[ ] Locked`
> ⚠️ Once LOCKED, changes require a dated amendment at the bottom.

## 📥 Inputs from 1-BRAINSTORM.md
- **Name & one-liner (§1)** → Section 1 Project Summary
- **Problem (§2)** → Context for Goals (§2) and User Stories (§3) — AI derives these with you
- **Solution / user journey (§3)** → User Stories (§3) and Functional Requirements (§4)
- **Assumptions & risks (§4)** → Open Questions (§10)
- **Feasibility (§5)** → Constraints (§9) and Non-Functional Requirements (§5)
- **Success criteria / Go/No-Go rationale (§6)** → Goals (§2) and Definition of Done framing

---

## 1. Project Summary
| Field | Value |
|---|---|
| **Project name** | |
| **One-liner** | *(from BRAINSTORM.md)* |
| **Owner** | |
| **Target completion** | |
| **Tech stack** | *(confirm in ARCHITECTURE.md)* |

---

## 2. Goals & Non-Goals
> *This section is LAW for the AI. It will not build non-goals.*

### ✅ Goals (In Scope)
- G1: [Specific, measurable goal]
- G2:
- G3:

### ❌ Non-Goals (Out of Scope — AI must not implement these)
- NG1: [Explicit exclusion + reason]
- NG2:
- NG3:

---

## 3. User Stories
> *Format: "As a [user], I want to [action], so that [outcome]."*
> *Each story must be independently testable.*

### Must Have (MVP)
| ID | Story | Acceptance Criteria |
|---|---|---|
| US-01 | As a [user], I want to [x] | - [ ] Criterion 1 <br>- [ ] Criterion 2 |
| US-02 | | |

### Should Have
| ID | Story | Acceptance Criteria |
|---|---|---|
| US-10 | | |

### Nice to Have (v2 — do NOT build in v1)
| ID | Story | Notes |
|---|---|---|
| US-20 | | Defer to v2 |

---

## 4. Functional Requirements
> *What the system MUST do. Written as testable statements.*

- FR-01: The system shall [do X] when [condition Y]
- FR-02: The system shall reject [input] if [condition]
- FR-03: The system shall log [event] to [destination]

---

## 5. Non-Functional Requirements
> *Quality constraints — performance, security, reliability.*

| ID | Category | Requirement |
|---|---|---|
| NFR-01 | Performance | [e.g. Pipeline must complete in < 60s for 100k rows] |
| NFR-02 | Reliability | [e.g. Must handle network timeout and retry 3x] |
| NFR-03 | Security | [e.g. No credentials in source code — use .env] |
| NFR-04 | Observability | [e.g. All pipeline stages must log row counts] |

---

## 6. Data Requirements
> *(Skip if not applicable)*

| Dataset | Source | Format | Volume | Refresh |
|---|---|---|---|---|
| [Name] | [Origin] | CSV / API / DB | [Size] | [Daily/realtime] |

**Data constraints:**
- Raw data is READ ONLY
- PII handling: [describe or N/A]

---

## 7. Interfaces & Integrations
> *External systems this project talks to.*

| System | Direction | Method | Auth |
|---|---|---|---|
| [e.g. IBKR API] | Inbound | REST | API Key |
| [e.g. DB_CHOICE] | Read/Write | [ORM/client] | .env |

---

## 8. Error Handling Policy
- All errors must be caught and logged — no silent failures
- User-facing errors must show a clear message, not a stack trace
- Critical failures must [send alert / write to error log / etc.]

---

## 9. Constraints
- [e.g. Must run on Python 3.10+]
- [e.g. No paid external APIs]
- [e.g. Must work offline]

---

## 10. Open Questions
> *Unresolved decisions. Must be answered before LOCKED status.*

| # | Question | Owner | Deadline | Answer |
|---|---|---|---|---|
| Q1 | | | | |

---

## 📝 Amendments Log
> *Add entries here when the locked PRD changes. Never delete history.*

| Date | Change | Reason |
|---|---|---|
| | | |

---

## 📤 Outputs for 3-ARCHITECTURE.md

**Once PRD is LOCKED, these outputs feed directly into the architecture:**

- **Tech Stack Hint** → ARCHITECTURE Section 1 (Tech Stack decisions)
- **Functional Requirements** → ARCHITECTURE Section 3 (Component breakdown - what each component must do)
- **Non-Functional Requirements** → ARCHITECTURE Section 10 (Performance & scalability assumptions)
- **Data Requirements** → ARCHITECTURE Section 4 (Data model design)
- **Interfaces & Integrations** → ARCHITECTURE Section 8 (Key technical decisions)
- **Error Handling Policy** → ARCHITECTURE Section 8 (Technical decisions for error handling)
- **Constraints** → ARCHITECTURE Section 1 (Tech stack limitations)
- **User Stories** → ARCHITECTURE Section 2 (System overview - user flows)

---

*→ Once locked, proceed to `3-ARCHITECTURE.md` with the structured outputs above*
*→ Also write blind scenarios now in `../testing/BLIND_SCENARIOS.md` while requirements are fresh*
