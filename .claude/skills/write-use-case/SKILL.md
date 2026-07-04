---
name: write-use-case
description: Use when authoring or editing a use-case document under docs/analysis/use-cases/ in the Smart Charging project (a UCnn-*.md file, or a change to one).
---

# Write a use-case

Author a Smart Charging use-case (`docs/analysis/use-cases/UCnn-*.md`) following the project's
analysis-first methodology. Use-cases capture **goal-oriented behaviour** in Given/When/Then; they
reference the shared mechanism docs rather than restating them.

## The cycle (do every step, in order)

0. **Open (or link) a GitHub issue** describing the intent and scope — a new use-case, or a
   behavioral change to an existing one (a change to acceptance criteria, a state model, or a
   set-point rule). Skip this step only for typo-level or pure-wording edits that don't change
   behavior. Reference the issue in the eventual commit/PR (`Closes #N`).
1. **Draft** against the template below.
2. **6Cs self-check** — Clarity, Concision, Completeness, Consistency, Correctness, Concreteness.
   Confirm **every domain term is already in the `system-overview.md` glossary**; if not, add it to
   the glossary first (that is a separate edit).
3. **Update `entity-catalog.md`** — for every `sc_` entity the use-case touches, add this UC to the
   entity's *Read by* and/or *Written by* column. This is the last content step before review.
4. **Review** — launch the `analysis-reviewer` agent (fresh, separate Opus; never review inline).
5. **Address** the feedback.
6. **Commit** with `docs: review and refine UCnn-<slug>`, referencing the issue from step 0.
7. **Stop and report** status before starting the next document.

## Template (section order)

Full template with rationale: `docs/plans/2026-06-25-use-cases-design.md`.

`# UCnn — <goal as active verb phrase>` then:
Primary actor · Stakeholders & interests · Scope/level · **Preconditions** (testable state, not
actions) · **Trigger** · **Main success scenario** (Given/When/Then) · **Alternate flows** (numbered
to the basic-step they branch from, e.g. 4a) · **Exception flows** (goal not met) · **Postconditions**
· **State model** (stateful UCs only — see below) · **Domain events produced** (past-tense PascalCase)
· **Diagram** (Mermaid) · **Requirements satisfied** · **Relationships** (`«extend»` / `«include»`).

## Rules

- **What, not how.** Describe observable behaviour. No Python, HA services, timer helpers, or
  persistence. Entity ids that are ubiquitous language are fine, but prefer domain terms in GWT
  ("the active SOC limit", "charger status") — the `sc_` binding lives in `entity-catalog.md`.
- **Don't duplicate mechanism.** Reference `control-cycle.md` (read → smooth → dispatch → clamp →
  set; peak clamp R3, grid ceiling clamp C4, rapid-cycling R11) and `resolution-rules.md` (active
  SOC limit R7, departure deadline R14, effective peak limit, Auto mode-selection R16) — do not
  restate them.
- **Mode use-cases (UC01–UC04) MUST carry a `stateDiagram-v2` + State model subsection**: states,
  transition conditions (thresholds/timers), and the set-point rule. Re-derive the archived
  `docs/archive/process-flow.md` machines against the *current* requirements (archive is a
  checklist, not a source of truth). UC08/UC10 carry a lighter state model; others may omit it.
- **Deadline logic is UC05's** (`«extend»`). A charging UC says "Extended by UC05 when the deadline
  is at risk" rather than restating urgency escalation.
- One statement per line; always name the subject (Actor or System); active voice; verifiable
  pre/postconditions.

## Diagram types

`stateDiagram-v2` for stateful modes · `flowchart TD` for decision logic · `sequenceDiagram` for
actor-driven prompts/notifications.

## Common mistakes

- Forgetting the `entity-catalog.md` *Read by*/*Written by* update (step 3) — the reviewer checks it.
- Using a domain term not yet in the glossary.
- Restating the peak/ceiling clamp or a resolution rule instead of referencing it.
- A mode UC whose `stateDiagram-v2` states don't match its Given/When/Then scenarios.
