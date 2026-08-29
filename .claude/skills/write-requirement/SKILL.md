---
name: write-requirement
description: Use when adding or changing a requirement (Rnn / NFnn), constraint (Cnn), or glossary term in the Smart Charging analysis docs (requirements.md, system-overview.md).
---

# Write a requirement

Add or change a requirement, non-functional requirement, constraint, or glossary term in the Smart
Charging analysis layer. Every requirement describes **what** the system must do, never **how**.

Follows this project's development workflow, defined in `CLAUDE.md` (issue → worktree → PR →
review → fix/resolve → merge) — no exceptions, including typo-level or pure-wording edits.
This skill covers only what's specific to a requirement — don't re-derive the universal steps
here.

## Requirement-specific additions to the workflow

- **Step 1 (draft)**: the requirement in `requirements.md` (or the constraint row / glossary
  term). Before step 3's review, self-check per `CLAUDE.md`'s "Review protocol for analysis
  documents" (6Cs + glossary-first) — the reviewer is `analysis-reviewer`.
- **Propagate**, before step 3's review — a new/changed requirement usually ripples: update
  the glossary, the mechanism docs (`control-cycle.md` / `resolution-rules.md`), and
  `entity-catalog.md` (new `sc_` entities, with defaults matching the requirement) so the
  whole analysis layer stays consistent.

## Requirement format

```
### Rnn — <short title>

**Priority:** Must | Should | Could | Won't   (MoSCoW)
**What:** One sentence — what the system must do, not how.

**Acceptance criteria:**

- [ ] SMART, testable statements (specific, measurable, with the configurable default in parentheses).
```

- **Constraints (Cnn)** are hard rules that must never be violated, regardless of mode; they live in
  the constraints table, one row each, and are enforced as invariants (see `control-cycle.md`).
- **Glossary terms** define *meaning* only; the `sc_` entity *binding* (id, unit, default) lives in
  `entity-catalog.md`. Never restate a definition — link to the glossary term.

## Rules

- **What, not how** — no implementation, no HA/Python detail.
- **MoSCoW priority on every requirement.**
- **SMART acceptance criteria** — measurable and testable; state the configurable default and range.
- **Every requirement has exactly one home** — a use-case, a mechanism doc, `resolution-rules.md`,
  or the constraints table. Check the design doc's coverage table; don't create a second home.
- Give every configurable parameter a concrete default (avoid "no default specified").

## Common mistakes

- Adding a term to a requirement without defining it in the glossary first.
- Leaving ripples unpropagated (requirement added but no `entity-catalog.md` row / no clamp in
  `control-cycle.md`).
- Acceptance criteria that describe *how* (a mechanism) instead of an observable *what*.
- Duplicating a requirement's home in two documents.
