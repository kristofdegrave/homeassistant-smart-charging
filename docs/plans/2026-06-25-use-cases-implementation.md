# Use-Cases Analysis Layer — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Write the Smart Charging v3 behaviour layer — `control-cycle.md`, `resolution-rules.md`, and ten use-case documents — per the approved design in [2026-06-25-use-cases-design.md](2026-06-25-use-cases-design.md).

**Architecture:** Analysis documentation, not code. Use-cases capture goal-oriented behaviours (Given/When/Then scenarios, BDD-flavoured); two mechanism docs capture the control pipeline and shared priority-ordered resolutions. The "test" for each document is a review by a **fresh, separate Opus agent** (per CLAUDE.md) checking cross-document consistency and requirement coverage — there is no executable test.

**Tech Stack:** Markdown + Mermaid diagrams. No build step. Reviewed on `main`.

---

## Conventions for every task

These replace the code-oriented TDD loop for documentation work. Each task below follows this exact cycle:

1. **Draft** the document against the template in the design doc (§ "Document templates").
2. **Self-check the 6Cs** (Clarity, Concision, Completeness, Consistency, Correctness, Concreteness) and confirm every domain term is already in the `system-overview.md` glossary — add it there first if not.
3. **Review** — spawn a **fresh Opus agent** (never review inline) with the review brief below.
4. **Address** the review feedback in the draft.
5. **Commit** with `docs: review and refine <filename>` once approved.

**Review brief (reuse for every doc, fill in `<FILE>`):**

> Review `docs/analysis/<FILE>` as a fresh Opus agent. Check: (1) cross-document consistency — every domain term matches the `system-overview.md` glossary; every requirement ID matches `requirements.md`; relationships to other use-cases are accurate. (2) Requirement coverage — the doc satisfies every requirement it claims, and nothing it describes contradicts another analysis doc. (3) Use-case quality — testable pre/postconditions, Given/When/Then scenarios, no implementation detail ("what, not how"), no duplication of the shared resolution rules. Report issues by severity; do not edit the file.

**Gate:** Do not start a use-case task until `control-cycle.md` and `resolution-rules.md` are committed — the use-cases reference both.

---

## Task 1: Control-cycle flow document

**Files:**
- Create: `docs/analysis/control-cycle.md`

**Content requirements:**
- Follow the flow-document standard (CLAUDE.md): Purpose → Trigger → Domain events → Mermaid diagram → Steps → Edge cases → Requirements satisfied.
- Describe the coordinator spine: read sensors → smooth (R10) → dispatch to active mode module → apply peak-protection clamp (R3) → set charger current.
- Include voltage-aware conversion (NF4) and the rapid-cycling invariant (R11) as steps/edge cases.
- Mermaid: a `flowchart TD` of the cycle (mirror the orientation diagram already in `system-overview.md` "How it fits together", expanded with the clamp and smoothing).
- Domain events (past-tense PascalCase), e.g. `SensorsRead`, `ChargerCurrentSet`, `PeakLimitClamped`.
- **Requirements satisfied:** R3, R10, R11, NF4.

**Cycle:** Draft → 6Cs self-check → fresh-Opus review (`<FILE>` = `control-cycle.md`) → address → commit `docs: review and refine control-cycle.md`.

---

## Task 2: Resolution-rules document

**Files:**
- Create: `docs/analysis/resolution-rules.md`

**Content requirements:**
- Short intro: these are the shared priority-ordered lookups extracted from the use-cases (avoids duplication).
- One decision table per resolution, each stating priority order + requirement link:
  - **Active SOC limit (R7):** solar-reserve cap → solar step-up → default `sc_active_soc`.
  - **Departure time (R14):** external sensor → public-holiday/home-day override → day-of-week default; any may be "no deadline".
  - **Effective peak limit:** `min(monthly_peak_demand, maximum_peak)`, rising to `maximum_peak` under deadline urgency.
  - **Auto mode-selection (R16):** conditions → active mode, including Solar→CapTar escalation and revert; note `Manual` sets the mode directly.
- No prose mechanism that belongs in `control-cycle.md`; tables, not narrative.
- **Requirements satisfied:** R7, R14, R16 (Auto selection); references the effective-peak-limit glossary term.

**Cycle:** Draft → 6Cs self-check → fresh-Opus review (`<FILE>` = `resolution-rules.md`) → address → commit `docs: review and refine resolution-rules.md`.

---

## Task 3: Use-cases index README

**Files:**
- Create: `docs/analysis/use-cases/README.md`

**Content requirements:**
- Mirror the style of the existing `flows/README.md`.
- Intro: every use-case follows the template in the design doc; Given/When/Then scenarios; every domain term must already be in the glossary.
- Inventory table = Decision 3 table from the design doc (UC01–UC10, goal, primary actor, reqs, status column).
- Note UC05's `«extend»` relationship and that Auto profile / Manual profile / Off mode are intentionally **not** use-cases (point to `resolution-rules.md`).

**Cycle:** Draft → 6Cs self-check → fresh-Opus review (`<FILE>` = `use-cases/README.md`) → address → commit `docs: review and refine use-cases README`.

---

## Tasks 4–13: One use-case per task

Each follows the **use-case template** from the design doc (Primary actor · Stakeholders · Scope/level · Preconditions · Trigger · Main success scenario (Given/When/Then) · Alternate flows (numbered to branch step) · Exception flows · Postconditions · Domain events · Mermaid · Requirements satisfied · Relationships).

Write **one at a time**, each with its own draft → 6Cs → fresh-Opus review → address → commit `docs: review and refine UCnn-<slug>`.

| Task | File | Goal | Primary actor | Reqs | Key notes |
|------|------|------|---------------|------|-----------|
| 4  | `use-cases/UC01-charge-from-solar-surplus.md` | Charge from solar surplus (incl. grid fallback) | Household energy manager | R1 | Alternate flow: grid fallback when surplus < min current; post-surplus hold (ride out clouds). Extended by UC05. References active-SOC-limit + effective-peak-limit rules. |
| 5  | `use-cases/UC02-charge-from-solar-only.md` | Charge from solar only | Household energy manager | R2 | No grid fallback; stop with no hold when surplus < threshold. Extended by UC05. |
| 6  | `use-cases/UC03-charge-cost-efficiently-from-grid.md` | Charge cost-efficiently from the grid | Household energy manager | R4 | Charge only while low-tariff flag active; default 0 A otherwise. Extended by UC05. |
| 7  | `use-cases/UC04-charge-at-maximum-power.md` | Charge at maximum power | EV driver | R17 | Ignores solar/tariff; configurable peak-protection option. Respects SOC limit + C1. |
| 8  | `use-cases/UC05-guarantee-ready-by-departure.md` | Guarantee the car is ready by departure | EV driver | R5 | The `«extend»` use-case. Documents urgency escalation up to maximum peak; never raises the active SOC limit; deadline-unreachable notification. Lists which UCs it extends (UC01/02/03). |
| 9  | `use-cases/UC06-store-abundant-solar.md` | Store abundant solar by stepping up the limit | Household energy manager | R8 | Applies only while in a solar mode; step interval; clamps to max. References active-SOC-limit rule (R7). |
| 10 | `use-cases/UC07-reserve-capacity-for-tomorrow.md` | Reserve capacity for tomorrow's solar | Household energy manager | R9 | Solar-reserve cap while sun down; suppresses low-tariff grid charging; deadline may charge up to cap. Consumes home-day flag set by UC08. |
| 11 | `use-cases/UC08-plan-tomorrow-home-day.md` | Plan tomorrow's home day (evening prompt) | EV driver | R13 | The genuinely interactive UC: actionable yes/no notification; timeout → "no"; skipped if external source already set the flag. Feeds UC07. |
| 12 | `use-cases/UC09-sync-charge-limit-with-car.md` | Keep the charge limit in sync with the car | EV driver | R6 | Bidirectional sync; reset to default on unplug; never change while away (C2); adopt user's manual change. |
| 13 | `use-cases/UC10-remind-to-plug-in.md` | Remind me to plug in | EV driver | R12 | Single reminder within lead time of departure (resolved via R14); de-dup until reconnect/disconnect. |

---

## Task 14: Revisit requirements & supersede flows references

**Files:**
- Modify: `docs/analysis/requirements.md` (only if use-cases revealed gaps/contradictions)
- Modify: `CLAUDE.md` and `docs/plans/2026-06-24-analysis-approach-design.md` — update the document-structure sections that still point to the old `flows/` layout, pointing them at `use-cases/` + `control-cycle.md` + `resolution-rules.md`.
- Delete or rewrite: `docs/analysis/flows/README.md` (superseded).

**Steps:**
1. Re-read each use-case for any requirement gap or contradiction surfaced while writing; patch `requirements.md` if needed (fresh-Opus review for any requirement change).
2. Update the structure references in `CLAUDE.md` and the methodology design doc.
3. Remove the now-superseded `flows/` README (or replace with a one-line pointer to the new structure).
4. Commit: `docs: supersede flows layer with use-cases structure`.

---

## Done when

- [ ] `control-cycle.md` and `resolution-rules.md` written, reviewed, committed.
- [ ] `use-cases/README.md` + UC01–UC10 written, reviewed, committed.
- [ ] Every requirement (R1–R17, NF1–NF4, C1–C3) is reachable from a use-case or a mechanism doc (coverage table in design doc holds).
- [ ] Old `flows/` references in CLAUDE.md and the methodology doc updated.
