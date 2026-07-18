---
name: write-impl-spec
description: Use when authoring an implementation spec and TDD plan for a slice of the Smart Charging build (a docs/plans/YYYY-MM-DD-<slice>-design.md plus its paired task plan) — deriving the concrete, test-driven build sequence from an approved project-plan slice and the ADRs, before any custom_components/ code is written.
---

# Write an implementation spec (per-slice design + TDD plan)

Author the two documents that sit between the architecture and the code for one build slice:
a **design** (`docs/plans/YYYY-MM-DD-<slice>-design.md` — scope, config surface, control flow,
mapping to services, deferrals, testing, packaging) and a **TDD plan**
(`docs/plans/YYYY-MM-DD-<slice>.md` — bite-sized task-by-task build order). Both **derive** from an
already-approved slice of `docs/design/project-plan.md`; they do not re-decompose the system or
invent behavior.

**The core discipline: derive, don't design.** `system-design.md` owns the service shape,
`project-plan.md` owns the build sequence, and the `docs/analysis/` docs own the behavior. This spec
turns one slice of that into concrete files, functions, and tests — citing those sources, never
restating or overriding them. If you find yourself inventing a service or a behavioral rule, stop:
open a GitHub issue against the owning doc and fix it there first (via its own issue-first
review cycle), then resume.

## The cycle (do every step, in order)

0. **Open (or link) a GitHub issue** describing the slice and its scope. Branch as
   `feature/<slice>` (or `docs/<issue-number>` if the work is spec-only), per CLAUDE.md's
   branch-naming convention.
1. **Identify the slice** from `docs/design/project-plan.md`: which tasks/services it covers, in
   what build order, and which ADR gates apply. List them — this is what the plan's sequence must
   obey, not something to renegotiate for convenience.
2. **Scope it** with the `brainstorming` skill: nail the slice boundary (the same discipline
   applies to any slice, MVP or post-MVP), the minimal config surface, and the explicit
   deferrals **before** writing. Get the human partner's decisions on any
   real fork (a safety-relevant omission, a config field, an entity's home).
3. **Write the design doc** (`...-<slice>-design.md`): success criteria, install-time config, the
   control flow, a table **mapping every piece to its named service** in `system-design.md`,
   deliberate deferrals (with any safety caveat stated out loud), testing approach, and packaging.
4. **Derive the TDD plan** (`...-<slice>.md`) with the `writing-plans` skill: bite-sized tasks
   (failing test → minimal impl → green → commit), each naming exact file paths, the ADR it honors,
   and its **test boundary per ADR-0009** (plain pytest for `modes/`/`engines/`; HA harness for
   adapters, coordinator, entities, config flow). Name the integration checkpoints.
5. **Self-check:** every task traces to a `project-plan.md` task and a `system-design.md` service
   (no new service/call direction); behavior is cited from the analysis docs as a **test anchor**,
   not restated; every ADR gate is opened before the task it blocks; every domain term is already in
   the `system-overview.md` glossary; entity ids match ADR-0004 native naming.
6. **Review** — launch the `impl-spec-reviewer` agent (fresh, separate Opus; never review inline).
   Post its findings to the PR via the `submit-pr-review` skill in **local mode**.
7. **Address** the review feedback.
8. **Commit and push** (`docs: add <slice> implementation spec` / `... plan`), referencing the
   issue — commit and push freely; there is no pre-commit approval gate.
9. **Manual approval gates the merge** — the human partner's explicit approval is required before
   the PR is **merged** (enforced by `CODEOWNERS` + branch protection), not before each commit.
10. **Stop and report** status. Once approved, the `develop-task` skill consumes the plan
    task-by-task to write the code.

## Rules

- **Derive, don't design.** No service, call direction, or volatility that isn't already in
  `system-design.md`; the only things this spec adds are *sequence*, *concrete files/signatures*,
  and *tests*.
- **Behavior is owned by the analysis docs.** Cite `control-cycle.md`, `resolution-rules.md`,
  `requirements.md`, and the use-cases; attribute any formula/threshold as a test anchor. If a spec
  and its source ever disagree, the source wins.
- **Honor the ADRs.** Adapters (0003), package layout (0002/0010), config split (0005),
  coordinator/two-clamps (0006), fault-on-`None` (0007), testing split (0009), native naming (0004).
- **Respect the test boundary.** Pure logic → plain pytest; HA-coupled → HA harness. Name it per
  task.
- **No `custom_components/` code here.** The spec is a planning artifact; code is written by
  `develop-task` against the approved plan.

## Common mistakes

- Inventing a service or a behavioral rule instead of citing the design/analysis doc that owns it.
- Restating a formula/threshold as if the spec owns it (it will drift from the analysis doc).
- A task with no exact file path, no failing test, or no stated test boundary.
- Routing pure-logic tests through the HA harness (or vice versa).
- A silent deferral of a mandated safety behavior (a clamp, the fault path) — state it as a known
  deviation, out loud.
