# Work type: `uc` — how the work is done

Author a use-case (`docs/analysis/use-cases/UCnn-*.md`) following this project's analysis-first
methodology. Use-cases capture **goal-oriented behaviour** in Given/When/Then; they reference
the shared mechanism documents rather than restating them.

This file is the `uc` row's work file in `CLAUDE.md`'s **Model selection** table. It carries
**how a use-case is written** and nothing else. Two things deliberately sit elsewhere:

- The lifecycle around the draft — issue, worktree, PR, review, fix, merge — belongs to the
  contribution workflow and is not re-derived here. It applies with no exceptions, including
  to a typo-level or pure-wording edit.
- *What must be true of a finished use-case* is the completion bar, `done.md`, named alongside
  this file in the same row and again in that row's review column. The author checks it before
  requesting review and the reviewer applies it, so it is written once for both. That file is
  shared with the `requirement` row, because one reviewer covers the whole analysis tree.

## Drafting a use-case

- **Numbering** (before drafting): the next sequential integer after the highest existing
  `UCnn`, zero-padded to 2 digits. This is the document's own number, unrelated to the
  branch/issue numbering the contribution workflow handles.
- **Step 1 (draft)**: against the template below, then self-check against `done.md` before
  requesting review.
- **Update `docs/analysis/entity-catalog.md`**, before step 3's review — for every `sc_` entity
  the use-case touches, add this UC to the entity's *Read by* and/or *Written by* column. This
  is the last content step inside the analysis layer, and the bar judges the result.
- **Propagate past the analysis layer**, same step. The procedure is below; what the finished
  PR has to show for it is the bar's *Code backing* item.

### Propagating past the analysis layer

The documents are not the last stop, and a use-case the shipped code contradicts is not
consistent. This is how you settle whether the change touches shipped behaviour, which is the
question `CLAUDE.md`'s **Contribution workflow** section's `needs-approval` gate turns on.

- **What is in scope** is the *Code backing* item of `done.md` — it defines the behavioural
  assertions a use-case makes, which changes assert none, and how *Scope / level* and
  *Relationships* split. Read them off the diff; do not re-derive the list here.
- **The search, capped.** Per in-scope item, run **one** targeted search of
  `custom_components/` for the thing it names — the entity id, the adapter role, the domain
  event name, the threshold, the ordering — and open at most one file, the best match.
  **Stop after five items**; where the diff has more — a brand-new use-case, whose diff is
  the whole document, always will — say the set was sampled and name the five you took. Five
  suits a drafting session's turn budget, and one use-case edit routinely touches more
  assertions than one requirement edit touches criteria. The cap is this step's own: it is
  deliberately not derived from what any other artifact does, so it neither follows nor
  constrains them. It is a fixed lookup count either way, never a sweep.
- **State the finding in the PR body**, per item you took: either the code already satisfies
  it — name the file and the function that does — or it does not. Behaviour the code does
  not implement at all is this second case, not an exemption from it. Where it does not,
  **file a `specs` child issue for that gap as part of this PR** and reference it in the
  body — a `specs` issue, never a task issue, for the reason `CLAUDE.md`'s **Contribution
  workflow** section routes to; its **Tracker mechanics** section routes to the filing
  commands.

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
  ("the active SOC limit", "charger status") — the `sc_` binding lives in
  `docs/analysis/entity-catalog.md`.
- **Don't duplicate mechanism.** Reference `docs/analysis/control-cycle.md` (read → smooth →
  dispatch → clamp → set; peak clamp R3, grid ceiling clamp C4, rapid-cycling R11) and
  `docs/analysis/resolution-rules.md` (active SOC limit R7, departure deadline R14, effective
  peak limit, Auto mode-selection R16) — do not restate them.
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

- Forgetting the `entity-catalog.md` *Read by*/*Written by* update — the bar judges it.
- Using a domain term not yet in the glossary.
- Restating the peak/ceiling clamp or a resolution rule instead of referencing it.
- Propagating to the documents only — merging a step, trigger, state transition or domain
  event the shipped code contradicts, with nothing filed to close the gap.
- A mode UC whose `stateDiagram-v2` states don't match its Given/When/Then scenarios.
- Drafting against this file alone and never opening `done.md` — the bar is where most of what
  a review will say already is.
