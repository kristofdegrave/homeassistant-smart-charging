# Work type: `requirement` — how the work is done

Add or change a requirement (`Rnn` / `NFnn`), a constraint (`Cnn`), or a glossary term in this
project's analysis layer — `docs/analysis/requirements.md` and
`docs/analysis/system-overview.md`. Every requirement describes **what** the system must do,
never **how**.

This file is the `requirement` row's work file in `CLAUDE.md`'s **Model selection** table. It
carries **how a requirement is written** and nothing else.

The completion bar is shared with the `uc` row — `done.md` beside this file routes to it —
because one reviewer covers the whole analysis tree.

## Drafting a requirement

- **The implement step (draft)**: the requirement in `docs/analysis/requirements.md` — or the constraint
  row, or the glossary term — in the format below, then self-check against `done.md` before
  requesting review.
- **Propagate inside the analysis layer**, before the review step — the bar's 5.2 item
  *Ripples are propagated* names the targets and judges the result. What that means while
  drafting: do it in the same sitting as the requirement itself, while you still know which
  documents you touched. A ripple deferred to a follow-up is the one that gets lost.
- **Propagate past the analysis layer**, same step. The procedure is below; what the finished
  PR has to show for it is the bar's *Code backing* item.

### Propagating past the analysis layer

The documents are not the last stop, and a requirement the code contradicts is not consistent.
This is how you settle whether the change touches shipped behaviour, which is the question
`CLAUDE.md`'s **Contribution workflow** section's `needs-approval` gate turns on.

- **What is in scope** is the *Code backing* item of `done.md` — for this work type, every
  acceptance criterion and constraint row the change adds or alters. Read them off the diff; do
  not re-derive the list here.
- **The search.** Per in-scope item, search `custom_components/` for the behaviour it
  constrains — the entity it names, the clamp, the lookup, the default. This is a targeted
  lookup per item, never a sweep of the codebase.
- **State the finding, file what it turns up, and you are done** — the bar's items 4.2, *The
  finding is stated*, and 4.3, *A gap is filed*, state both, carry the drafting order, and
  judge the result. Done when both hold for every item you took.

## Requirement format

The shape an author types. What must be true of the result — that the priority is there, that
the criteria are SMART, that every configurable parameter carries a default — is the bar's 5.2,
which names this block and judges conformance to it.

```
### Rnn — <short title>

**Priority:** Must | Should | Could | Won't   (MoSCoW)
**What:** One sentence — what the system must do, not how.

**Acceptance criteria:**

- [ ] <one SMART, testable statement>
```

- **Constraints (`Cnn`)** — the bar's 5.2 item *A constraint (`Cnn`) is a hard rule that holds
  regardless of mode* states what one is and judges it. What that means while drafting: decide
  which of the two you are writing before you type a heading, because a constraint is a row of
  the constraints table and never a `### Cnn` section of its own.
- **Glossary terms** — the bar's 5.2 item *A glossary term defines meaning only* states the
  split from the `sc_` binding and judges it. What that means while drafting: write the meaning
  into `docs/analysis/system-overview.md` first and the binding into
  `docs/analysis/entity-catalog.md` second, so the entity row has a term to point at.

## Rules

The rules a finished requirement is judged by are the bar's, at the severity each miss lands
at, and are not repeated here. Two of them have a drafting order this file owns:

- **Where a requirement lives** — the bar's 2.2, *Every requirement has exactly one home*,
  states it and judges it. What that means while drafting: check the design document's coverage
  table *before* writing, since a second home is nearly free to avoid and expensive to unpick.
- **What, not how** — the rule itself is `CLAUDE.md`'s **Requirements standard**, and the bar's
  5.2 judges the criterion-level form of it. What that means while drafting: if you cannot
  state the criterion without naming a module, a service call or a data structure, the *what*
  hasn't been found yet.

## Common mistakes

- Adding a term to a requirement without defining it in the glossary first.
- Leaving ripples unpropagated (requirement added but no `entity-catalog.md` row / no clamp in
  `control-cycle.md`).
- Propagating to the documents only — merging a criterion the shipped code contradicts, with
  nothing filed to close the gap.
- Acceptance criteria that describe *how* (a mechanism) instead of an observable *what*.
- Duplicating a requirement's home in two documents.
- Drafting against this file alone and never opening `done.md` — the bar is where most of what
  a review will say already is.
