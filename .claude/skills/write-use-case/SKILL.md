---
name: write-use-case
description: Use when authoring or editing a use-case document under docs/analysis/use-cases/ in the Smart Charging project (a UCnn-*.md file, or a change to one).
---

# Write a use-case

Author a Smart Charging use-case (`docs/analysis/use-cases/UCnn-*.md`) following the project's
analysis-first methodology. Use-cases capture **goal-oriented behaviour** in Given/When/Then; they
reference the shared mechanism docs rather than restating them.

Follows this project's contribution workflow, defined in `CLAUDE.md` (issue → worktree → PR →
review → fix/resolve → merge) — no exceptions, including typo-level or pure-wording edits.
This skill covers only what's specific to a use-case — don't re-derive the universal steps
here.

## Use-case-specific additions to the workflow

- **Numbering** (before drafting): for a new use-case, next sequential integer after the
  highest existing `UCnn`, zero-padded to 2 digits. This is the document's own number,
  unrelated to the branch/issue numbering the workflow handles.
- **Step 1 (draft)**: against the template below. Before step 3's review, self-check per
  `CLAUDE.md`'s "Review protocol for analysis documents" (6Cs + glossary-first).
- **Update `entity-catalog.md`**, before step 3's review — for every `sc_` entity the use-case
  touches, add this UC to the entity's *Read by* and/or *Written by* column. This is the last
  content step inside the analysis layer.
- **Propagate past the analysis layer**, same step — the documents are not the last stop, and a
  use-case the shipped code contradicts is not consistent. This is how you settle whether the
  change touches shipped behaviour, which is the question `CLAUDE.md`'s **Contribution
  workflow** section's `needs-approval` gate turns on.
  - **In scope: the behavioural assertions this change adds or alters** — read them off the
    diff. A use-case asserts behaviour in a Given/When/Then step of the main success scenario,
    an alternate flow, an exception flow, a **Trigger**, a **State model** state or transition,
    and a **domain event** under *Domain events produced*. Each names something the running
    integration does: a value written through an adapter role, a condition it acts on, a bound
    it applies, a state it enters, an event it fires. A pre- or postcondition is in scope only
    where it asserts behaviour no in-scope item in the same diff already covers — otherwise
    that item covers it and you do not search twice.
  - **No-op branch.** A change altering none of those asserts no behaviour, and this step is
    one line in the PR body saying nothing was in scope: rewording, a link or cross-reference,
    a renumbering, the Mermaid diagram redrawn to match steps already in the diff, and
    Stakeholders / Scope / Relationships / *Requirements satisfied* prose — the last because a
    requirement's home is `requirements.md`, so restating one here changes nothing.
  - **The search, capped.** Per in-scope item, run **one** targeted search of
    `custom_components/` for the thing it names — the entity id, the adapter role, the domain
    event (it ships as an `EVENT_*` constant whose value is the snake_cased event name), the
    threshold, the ordering — and open at most the one file that matches. **Stop after five
    items**; where the diff has more, say the set was sampled and name the five you took. Five
    rather than the three `analysis-reviewer` samples, because a drafting session has the
    fuller turn budget and one use-case edit routinely touches more assertions than one
    requirement edit touches criteria. It is a fixed lookup count either way, never a sweep.
  - **State the finding in the PR body**, per item you took: either the code already satisfies
    it — name the file and the function that does — or it does not. Behaviour the code does
    not implement at all is this second case, not an exemption from it. Where it does not,
    **file a `specs` child issue for that gap as part of this PR** and reference it in the
    body — a `specs` issue, never a task issue, because a task issue needs the anchored plan
    reference `CLAUDE.md`'s **Issue conventions** section routes to, and no such plan exists
    yet; `CLAUDE.md`'s **Tracker mechanics** section routes to the filing commands. Done when
    the PR body names which of the two cases holds for every item you took, and names the
    `specs` issue wherever it is the second.

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
- Propagating to the documents only — merging a step, trigger, state transition or domain
  event the shipped code contradicts, with nothing filed to close the gap.
- A mode UC whose `stateDiagram-v2` states don't match its Given/When/Then scenarios.
