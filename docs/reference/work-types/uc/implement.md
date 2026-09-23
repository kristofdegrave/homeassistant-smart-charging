# Work type: `uc` — how the work is done

Author a use-case (`docs/analysis/use-cases/UCnn-*.md`) following this project's analysis-first
methodology. Use-cases capture **goal-oriented behaviour** in Given/When/Then; they reference
the shared mechanism documents rather than restating them.

This file is the `uc` row's work file in `CLAUDE.md`'s **Model selection** table. It carries
**how a use-case is written** and nothing else.

The completion bar beside this file, `done.md`, is shared with the `requirement` row, because
one reviewer covers the whole analysis tree.

## Drafting a use-case

- **Numbering** (before drafting): the next sequential integer after the highest existing
  `UCnn`, zero-padded to 2 digits. This is the document's own number, unrelated to the
  branch/issue numbering the contribution workflow handles.
- **The implement step (draft)**: against the template below, then self-check against `done.md` before
  requesting review.
- **Update `docs/analysis/entity-catalog.md`**, before the review step — for every `sc_` entity
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
- **The search, capped.** Per in-scope item, run **one** targeted search of the product-code
  tree for the thing the item names — the entity id, the adapter role, the domain event name,
  the threshold, the ordering — and open at most one file, the best match. The tree itself is
  the one the `development` work type's stack overlay names.
  **Stop after five items**; where the diff has more — a brand-new use-case, whose diff is
  the whole document, always will — say the set was sampled and name the five you took. Five
  suits a drafting session's turn budget, and one use-case edit routinely touches more
  assertions than one requirement edit touches criteria. The cap is this step's own: it is
  deliberately not derived from what any other artifact does, so it neither follows nor
  constrains them. It is a fixed lookup count either way, never a sweep.
- **State the finding, file what it turns up, and you are done** — the bar's items 4.2, *The
  finding is stated*, and 4.3, *A gap is filed*, state both, carry the drafting order, and
  judge the result. Done when both hold for every item you took.

## Template (section order)

**Given/When/Then, mapped**: Given = the preconditions · When = the trigger and the actions it
sets off · Then = the system's responses and the postconditions. The same mapping holds for the
main, alternate and exception flows alike.

`# UCnn — <goal as active verb phrase>` then:
Primary actor · Stakeholders & interests · Scope/level · **Preconditions** (testable state, not
actions) · **Trigger** · **Main success scenario** (Given/When/Then) · **Alternate flows** (numbered
to the basic-step they branch from, e.g. 4a) · **Exception flows** (goal not met) · **Postconditions**
· **State model** (stateful UCs only — see below) · **Domain events produced** (past-tense PascalCase)
· **Diagram** (Mermaid) · **Requirements satisfied** · **Relationships** (`«extend»` / `«include»`).

## Rules

- **Form** — per *Write rules as items, with the shortest example that teaches them*, in
  [`ai-authoring.md`'s Principles](../../method/ai-authoring.md#principles).
- **What, not how.** Describe observable behaviour. No modules, platform services, timer
  helpers, or persistence. Entity ids that are ubiquitous language are fine, but prefer domain terms in GWT
  ("the active SOC limit", "charger status") — the `sc_` binding lives in
  `docs/analysis/entity-catalog.md`. The bar's item 3.1 states it and judges it, carve-out
  included. What that means while drafting: a State model is a *what*, so write the states,
  transitions, thresholds and set-point rule without hedging.
- **Don't duplicate mechanism.** Reference `docs/analysis/control-cycle.md` (read → smooth →
  dispatch → clamp → set; peak clamp R3, grid ceiling clamp C4, rapid-cycling R11) and
  `docs/analysis/resolution-rules.md` (active SOC limit R7, departure deadline R14, effective
  peak limit, Auto mode-selection R16) — do not restate them.
- **Mode use-cases carry a `stateDiagram-v2` + State model subsection** — the bar's 5.1 states
  which use-cases, what the model has to agree with, and the severities. What that means while
  drafting: re-derive the archived `docs/archive/process-flow.md` machines against the
  *current* requirements. The archive is a checklist of states worth considering, not a source
  of truth, and copying it forward is how a state model ends up disagreeing with its own
  scenarios.
- **Deadline logic is UC05's** (`«extend»`) — the bar's 5.1 item *Deadline escalation is
  referenced, not restated* judges it. What that means while drafting: write "Extended by UC05
  when the deadline is at risk" and move on, rather than re-deriving urgency escalation.
- One statement per line; always name the subject (Actor or System); active voice; verifiable
  pre/postconditions.

### Skills

The method skills this work file uses, by step: `research` when a fact a use-case rests on is
external, cited from the document by linking the issue comment; `receiving-code-review` in the
review step. This work type names no stack skill.

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
