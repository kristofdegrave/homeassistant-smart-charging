# Work type: `requirement` — how the work is done

Add or change a requirement (`Rnn` / `NFnn`), a constraint (`Cnn`), or a glossary term in this
project's analysis layer — `docs/analysis/requirements.md` and
`docs/analysis/system-overview.md`. Every requirement describes **what** the system must do,
never **how**.

This file is the `requirement` row's work file in `CLAUDE.md`'s **Model selection** table. It
carries **how a requirement is written** and nothing else. Two things deliberately sit
elsewhere:

- The lifecycle around the draft — issue, worktree, PR, review, fix, merge — belongs to the
  contribution workflow and is not re-derived here. It applies with no exceptions, including
  to a typo-level or pure-wording edit.
- *What must be true of a finished requirement* is the completion bar, `done.md`, named
  alongside this file in the same row and again in that row's review column. The author checks
  it before requesting review and the reviewer applies it, so it is written once for both. That
  file is shared with the `uc` row, because one reviewer covers the whole analysis tree.

## Drafting a requirement

- **Step 1 (draft)**: the requirement in `docs/analysis/requirements.md` — or the constraint
  row, or the glossary term — in the format below, then self-check against `done.md` before
  requesting review.
- **Propagate inside the analysis layer**, before step 3's review. A new or changed requirement
  usually ripples: update the glossary, the mechanism documents
  (`docs/analysis/control-cycle.md` / `docs/analysis/resolution-rules.md`) and
  `docs/analysis/entity-catalog.md` (new `sc_` entities, with defaults matching the
  requirement), so the whole analysis layer stays consistent.
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
- **State the finding in the PR body**: either the code already satisfies every such item —
  naming the file and the function that does — or it does not. Behaviour the code does not
  implement at all is this second case, not an exemption from it. Where it does not, **file a
  `specs` child issue for that gap as part of this PR** and reference it in the body — a
  `specs` issue, never a task issue, for the reason `CLAUDE.md`'s **Contribution workflow**
  section routes to; its **Tracker mechanics** section routes to the filing commands.

## Requirement format

```
### Rnn — <short title>

**Priority:** Must | Should | Could | Won't   (MoSCoW)
**What:** One sentence — what the system must do, not how.

**Acceptance criteria:**

- [ ] SMART, testable statements (specific, measurable, with the configurable default in parentheses).
```

- **Constraints (`Cnn`)** are hard rules that must never be violated, regardless of mode; they
  live in the constraints table, one row each, and are enforced as invariants (see
  `docs/analysis/control-cycle.md`).
- **Glossary terms** define *meaning* only; the `sc_` entity *binding* (id, unit, default) lives
  in `docs/analysis/entity-catalog.md`. Never restate a definition — link to the glossary term.

## Rules

- **What, not how** — no implementation, no HA/Python detail.
- **MoSCoW priority on every requirement.**
- **SMART acceptance criteria** — measurable and testable; state the configurable default and
  range.
- **Every requirement has exactly one home** — a use-case, a mechanism document,
  `docs/analysis/resolution-rules.md`, or the constraints table. Check the design document's
  coverage table; don't create a second home.
- Give every configurable parameter a concrete default (avoid "no default specified").

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
