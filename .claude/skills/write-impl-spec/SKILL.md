---
name: write-impl-spec
description: Use when authoring an implementation spec and TDD plan for a slice of the Smart Charging build (a docs/plans/YYYY-MM-DD-<slice>-design.md plus its paired task plan) — deriving the concrete, test-driven build sequence from an approved project-plan slice and the ADRs, before any custom_components/ code is written.
---

# Write an implementation spec (per-slice design + TDD plan)

Author the two documents that sit between the architecture and the code for one build slice:
a **design** (`docs/plans/YYYY-MM-DD-<slice>-design.md` — the slice's scope and the concrete
decisions it makes; Step 1's item 3 below lists what it carries) and a **TDD plan**
(`docs/plans/YYYY-MM-DD-<slice>.md` — bite-sized task-by-task build order). Both **derive** from an
already-approved slice of `docs/design/project-plan.md`; they do not re-decompose the system or
invent behavior.

**The core discipline: derive, don't design.** `system-design.md` owns the service shape,
`project-plan.md` owns the build sequence, and the `docs/analysis/` docs own the behavior. This spec
turns one slice of that into concrete files, functions, and tests — citing those sources, never
restating or overriding them. If you find yourself inventing a service or a behavioral rule, stop:
open a GitHub issue against the owning doc and fix it there first (via its own issue-first
review cycle), then resume.

Follows this project's contribution workflow, defined in `CLAUDE.md` (issue → worktree → PR →
review → fix/resolve → merge) — context label `specs`, branch `specs/<issue-number>`. This
skill covers only what's specific to an implementation spec — don't re-derive the universal
steps here.

## Spec-specific additions to the workflow

- **Step 1 (do the work)**, in order:
  1. **Identify the slice** from `docs/design/project-plan.md`: which tasks/services it
     covers, in what build order, and which ADR gates apply. List them — this is what the
     plan's sequence must obey, not something to renegotiate for convenience.
  2. **Scope it** with the `brainstorming` skill: nail the slice boundary (the same
     discipline applies to any slice, MVP or post-MVP), the minimal config surface, and the
     explicit deferrals **before** writing. Get the human partner's decisions on any real
     fork (a safety-relevant omission, a config field, an entity's home).
  3. **Write the design doc** (`...-<slice>-design.md`), capped at what only it can say:
     the slice's scope and success criteria, install-time config, the **concrete decisions**
     (`D-n`) this slice makes and the concrete structure they land in (files, classes,
     signatures), a table **mapping every piece to its named service** in `system-design.md`,
     deliberate deferrals (with any safety caveat stated out loud), testing approach, and
     packaging. This list is the cap: anything outside it is a **cut candidate**, not yet a
     copy — **Cap both plan documents** below is the test that decides which it is.
  4. **Derive the TDD plan** (`...-<slice>.md`) with the `writing-plans` skill: bite-sized
     tasks (failing test → minimal impl → green → commit), each naming exact file paths, the
     ADR it honors, and its **test boundary per ADR-0009** (plain pytest for `modes/`/
     `engines/`; HA harness for adapters, coordinator, entities, config flow). Name the
     integration checkpoints.
- **Self-check**, before step 3's review: every task traces to a `project-plan.md` task and a
  `system-design.md` service (no new service/call direction); behavior is cited from the
  analysis docs as a **test anchor**, not restated; every ADR gate is opened before the task
  it blocks; every domain term is already in the `system-overview.md` glossary; entity ids
  match ADR-0004 native naming.
- Once approved and merged, the `develop-task` skill consumes the plan task-by-task to write
  the code.

## Cap both plan documents

`docs/plans/` is this project's largest artifact class and its weakest oracle. A plan that
restates a rule is a second place for that rule to be wrong, and the plan's copy is the one the
build reads. So the design doc carries the decisions and the structure, the TDD plan carries
the tasks, and neither carries what another doc already owns. Cut, when a draft has it — the
first two bullets in either document, the third in the TDD plan, where the task entries live:

- **A restated formula or threshold.** Cite the owning analysis doc and the R-number instead,
  as a test anchor. `develop-task` already sends the author to `control-cycle.md`,
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

**A long plan is not the defect.** A slice whose decisions and task list genuinely run long is a
correct plan at its natural length, and trimming detail the build needs is a regression. The
test is never the line count — it is whether a line says something no other doc says.

## Rules

- **Derive, don't design.** No service, call direction, or volatility that isn't already in
  `system-design.md`; the only things this spec adds are *sequence*, *concrete files/signatures*,
  and *tests*.
- **Behavior is owned by the analysis docs.** Cite `control-cycle.md`, `resolution-rules.md`,
  `requirements.md`, and the use-cases; attribute any formula/threshold as a test anchor. If a spec
  and its source ever disagree, the source wins.
- **Keep both plan documents capped**, per the section above: decisions, structure and tasks —
  no restated formula, no restated ADR rationale, no narrative that repeats its own task.
- **Honor the ADRs.** Adapters (0003), package layout (0002/0010), config split (0005),
  coordinator/two-clamps (0006), fault-on-`None` (0007), testing split (0009), native naming (0004).
- **Respect the test boundary.** Pure logic → plain pytest; HA-coupled → HA harness. Name it per
  task.
- **No `custom_components/` code here.** The spec is a planning artifact; code is written by
  `develop-task` against the approved plan.

## Common mistakes

- Inventing a service or a behavioral rule instead of citing the design/analysis doc that owns it.
- Restating a formula/threshold as if the spec owns it (it will drift from the analysis doc).
- Deleting a formula that appears **only** in the plan as if it were a duplicate — it is an
  undocumented rule, and cutting it loses the only copy. Report it and fix the owning doc.
- Restating an ADR's rationale, or narrating a task the task entry already describes.
- A task with no exact file path, no failing test, or no stated test boundary.
- Routing pure-logic tests through the HA harness (or vice versa).
- A silent deferral of a mandated safety behavior (a clamp, the fault path) — state it as a known
  deviation, out loud.
