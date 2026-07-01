---
name: write-requirement
description: Use when adding or changing a requirement (Rnn / NFnn), constraint (Cnn), or glossary term in the Smart Charging analysis docs (requirements.md, system-overview.md).
---

# Write a requirement

Add or change a requirement, non-functional requirement, constraint, or glossary term in the Smart
Charging analysis layer. Every requirement describes **what** the system must do, never **how**.

## The cycle (do every step, in order)

1. **Draft** the requirement in `requirements.md` (or the constraint row / glossary term).
2. **6Cs self-check** — Clarity, Concision, Completeness, Consistency, Correctness, Concreteness.
   Confirm **every domain term is already in the `system-overview.md` glossary**; if not, add it
   there first.
3. **Propagate** — a new/changed requirement usually ripples: update the glossary, the mechanism
   docs (`control-cycle.md` / `resolution-rules.md`), and `entity-catalog.md` (new `sc_` entities,
   with defaults matching the requirement) so the whole analysis layer stays consistent.
4. **Review** — launch the `analysis-reviewer` agent (fresh, separate Opus; never review inline).
5. **Address** the feedback.
6. **Commit** (`docs: <concise description>`, or `docs: review and refine <file>` for a doc pass).
7. **Stop and report** before the next document.

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
