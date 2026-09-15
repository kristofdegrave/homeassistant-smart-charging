# Work type: `specs` — how the work is done

Author the two documents that sit between the architecture and the code for one build slice:
a **design** (`docs/plans/YYYY-MM-DD-<slice>-design.md` — the slice's scope and the concrete
decisions it makes) and a **TDD plan** (`docs/plans/YYYY-MM-DD-<slice>.md` — bite-sized
task-by-task build order). Both **derive** from an already-approved slice of
`docs/design/project-plan.md`; they do not re-decompose the system or invent behavior.

Two words for two sizes. The spec covers one **build slice** — `project-plan.md`'s unit. Its
tasks are the flow's **vertical slices** — the unit one child issue, one PR and one verify-live
pass are each cut to, as the **Ticket** stage of
[idea-to-product.md](../../idea-to-product.md) defines it. The task entries below are where
that shape is written down, which is why they carry the two keys the flow reads off them.

This file is the `specs` row's work file in `CLAUDE.md`'s **Model selection** table. It carries
**how a spec is written** and nothing else.

## The core discipline: derive, don't design

`docs/design/system-design.md` owns the service shape, `docs/design/project-plan.md` owns the
build sequence, and the `docs/analysis/` docs own the behavior. This spec turns one slice of
that into concrete files, functions, and tests — citing those sources, never restating or
overriding them. If you find yourself inventing a service or a behavioral rule, stop: open a
GitHub issue against the owning doc and fix it there first (via its own issue-first review
cycle), then resume.

## Drafting a spec

The implement step of the contribution workflow, in order:

1. **Identify the slice** from `docs/design/project-plan.md`: which tasks/services it covers,
   in what build order, and which ADR gates apply. List them — this is what the plan's
   sequence must obey, not something to renegotiate for convenience.
2. **Scope it** with the `brainstorming` skill: nail the slice boundary (the same discipline
   applies to any slice, MVP or post-MVP), the minimal config surface, and the explicit
   deferrals **before** writing. Get the human partner's decisions on any real fork (a
   safety-relevant omission, a config field, an entity's home).
3. **Write the design doc** (`...-<slice>-design.md`), capped at what only it can say. The
   bar's item 3, *Each plan document carries only what it alone can say*, lists that cap item
   for item and judges it. What that means while drafting: anything outside the list is a
   **cut candidate**, not yet a copy — *Cap both plan documents* below is the test that
   decides which it is. The cap's headings answer five questions in order — what problem the
   slice solves (scope and success criteria), what the solution is (the decisions and the
   structure they land in), which implementation decisions are settled here (`D-n`), which
   testing decisions are (the testing approach), and what is out of scope (the deferrals) — so
   a draft that answers them under those headings is complete, and one that adds a heading
   beside them has something to place. The testing approach opens by naming the **testing
   seam(s)** the tasks' failing tests drive through: a seam the suite already has over one the
   slice would add, and one seam for the whole slice where one reaches every task. Named up
   front, the seam is what every task's test is then written against; found per task, each
   task invents its own.
4. **Derive the TDD plan** (`...-<slice>.md`) with the `writing-plans` skill, one **task
   entry** per task in the shape *The task entry* below fixes: a vertical slice, bite-sized
   (failing test → minimal impl → green → commit), naming exact file paths, the ADR it honors,
   its test boundary per ADR-0009, the tasks it is **blocked by** and its **Verify live**
   list. Name the integration checkpoints.
5. **Write each task's Verify-live list** into its entry, before the entry is finished. The
   bar's item 7, *Every task carries a usable Verify-live list*, defines what an item must
   name, says why the list has to exist, and judges it. What that means while drafting: write
   it **now**, and know what the timing buys — a list written once the build exists is written
   from what the build produced rather than from what the task promised, and nothing downstream
   can tell those two apart. The first task's list is the one the flow drives on the real
   installation before the second task starts, so it is the one to write as if it will be read
   aloud at a dashboard.

Once approved and merged, the `development` work type consumes the plan task-by-task to write
the code, and the task issues are filed from the same entries — one issue per task, its
blocked-by edges read off the entry's **Blocked by** line.

## The task entry

One entry per task, with its heading and these keys — the bar's items 5 and 7 judge each:

- **Vertical.** The task has the shape the **Ticket** stage gives a child issue, because it
  becomes one. The test to apply while cutting tasks: **something about this task is
  observable on the installation the day it merges, without a later task landing first.** A
  task that fails it is layer-shaped and is re-cut along the behaviour instead — one
  behaviour through adapter, engine, coordinator and entity, whichever it touches, then the
  next behaviour.
- **Files and test.** Exact file paths, the concrete failing test, and its test boundary per
  ADR-0009 — the keys the entries already carried.
- **Blocked by.** The ids of the tasks this one cannot start before, or `none`, stated
  either way — an entry that says nothing leaves the filer to guess which it meant. This line
  is what becomes the child issue's native blocked-by edge; the ids therefore name tasks in
  this plan, never issues, since none exist yet.
- **Verify live.** One item per observable: the entity id to watch and the value, **with its
  unit**, it is expected to show once the task is deployed. A task with nothing observable —
  a pure refactor, an integration checkpoint whose observables earlier entries already list —
  says `none` and the reason in one line, so the pass can tell that from a forgotten list.

## Cap both plan documents

`docs/plans/` is this project's largest artifact class and its weakest oracle. A plan that
restates a rule is a second place for that rule to be wrong, and the plan's copy is the one the
build reads. So the design doc carries the decisions and the structure, the TDD plan carries
the tasks, and neither carries what another doc already owns. Cut, when a draft has it — the
first two bullets in either document, the third in the TDD plan, where the task entries live:

- **A restated formula or threshold.** Cite the owning analysis doc and the R-number instead,
  as a test anchor. The `development` work file already sends the author to `control-cycle.md`,
  `resolution-rules.md`, `requirements.md` and the use-case for the rule itself, so the plan's
  copy is only a further version to keep in sync.
- **Restated ADR rationale.** Name the ADR and what it obliges this slice to do; the *why*
  stays in the ADR, where a reader who needs it will look.
- **Per-task narrative that states no fact the task does not already carry** — a paragraph
  re-telling a task whose own entry already names its file, its failing test and its boundary.

**This removes copies, never content that exists only in the plan.** Before cutting anything,
find the doc that owns it and read what it actually says:

- It says the same thing → a duplicate. Cut it; cite the source.
- No doc owns it, or none says it → **not a duplicate.** First ask what kind of thing it is.
  A `D-n` decision, a file layout, a signature, a test boundary appears only in the plan **by
  construction** — that is the plan doing its job, and there is nothing to do. A *behavioural*
  rule — a formula, a threshold, a resolution order — is different: it is a rule the analysis
  layer is missing, and the plan holds the only copy. For that one, in this order: **keep the
  text exactly as it stands** — cutting it here loses it; say so out loud in the PR body; and
  open the issue against the owning doc per *derive, don't design*. Only once that doc states
  the rule does the text here become a duplicate, replaced then by a citation to it. That, and
  never a deletion in this document, is the end state.
- It says something **different** → stop. One of the two is wrong, and no wording of the plan
  resolves it; take it to the owning doc rather than writing a paragraph here that explains the
  discrepancy away.

This file is the only home for the **author and fix side** of that three-way test — what to do
with the *text* in front of you: cut it, keep it and open an issue, or stop. The bar's item 2
holds the reviewer's side — what to do with the *finding*: which severity it carries, and that
a rule only the plan states is reported as a gap against the owning doc rather than as a
deletion here. Different actors, different actions, so neither is a duplicate of the other;
what they share is the one classification both start from, which the bar states as the
criterion and this file states as the procedure.

**A long plan is not the defect** — the bar's item 3 states that and judges by it. What it
means here is a single instruction: the test above is the *only* reason to remove a line.
Trimming to make the document look shorter is a regression, not an application of this
section.

## Rules

- **Derive, don't design.** No service, call direction, or volatility that isn't already in
  `system-design.md`; the only things this spec adds are *sequence*, *concrete
  files/signatures*, and *tests*.
- **Behavior is owned by the analysis docs.** Cite `control-cycle.md`, `resolution-rules.md`,
  `requirements.md`, and the use-cases; attribute any formula/threshold as a test anchor. If a
  spec and its source ever disagree, the source wins.
- **Keep both plan documents capped**, per the section above: decisions, structure and tasks —
  no restated formula, no restated ADR rationale, no narrative that repeats its own task.
- **Honor the ADRs.** The bar's item 4, *ADR compliance and gates*, enumerates the records a
  slice is ordinarily gated on and judges compliance with them. What that means while
  drafting: open each gate in the plan **before** the task it blocks, rather than leaving the
  review to discover the order is wrong.
- **Respect the test boundary.** Pure logic → plain pytest; HA-coupled → HA harness. Name it
  per task.
- **No `custom_components/` code here.** The spec is a planning artifact; code is written by the
  `development` work type against the approved plan.

## Common mistakes

- Inventing a service or a behavioral rule instead of citing the design/analysis doc that owns
  it.
- Restating a formula/threshold as if the spec owns it (it will drift from the analysis doc).
- Deleting a formula that appears **only** in the plan as if it were a duplicate — it is an
  undocumented rule, and cutting it loses the only copy. Report it and fix the owning doc.
- Restating an ADR's rationale, or narrating a task the task entry already describes.
- A task with no exact file path, no failing test, or no stated test boundary.
- Routing pure-logic tests through the HA harness (or vice versa).
- A silent deferral of a mandated safety behavior (a clamp, the fault path) — state it as a
  known deviation, out loud.
- Cutting tasks by layer — one per adapter, engine, coordinator, entity — so nothing is
  observable until the last of them lands; cut by behaviour, each task through every layer.
- A task entry with no **Blocked by** line, so the filer cannot tell "none" from "forgot".
- A Verify-live item carrying a bare number, or a "sensor" with no entity id — the unit and the
  id are what the pass checks.
- Leaving a task's Verify-live list to be written after deployment, when the task can no
  longer be judged against what it promised.
- Drafting against this file alone and never opening `done.md` — the bar is where most of what
  a review will say already is.
