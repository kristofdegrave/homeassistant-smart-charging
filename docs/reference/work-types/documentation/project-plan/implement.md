# Work type: `documentation` — how `project-plan.md` is written

Author `docs/design/project-plan.md`: the implementation task breakdown, build order, and
per-service ADR flags, derived **mechanically** from an approved `docs/design/system-design.md`,
per Löwy's "project design" step. Rationale:
`docs/plans/2026-07-07-lowy-system-design-method.md`.

This file is the `documentation` work type's work file for a change touching
`docs/design/project-plan.md`, reached from the label's own `implement.md` one level up, which is
what the row names. Why the label splits at all, where a change touching
`docs/design/system-design.md` goes instead, and which bar a change falls under are stated once
in the label's own [`done.md`](../done.md).
It carries **how the project plan is written** and nothing else; the completion bar beside
it, `done.md`, carries what must be true of the finished plan.

**An approved `system-design.md` must exist first.** This work consumes that document; it does
not decompose services itself. The bar's item 1, *Derived, not designed*, states it and judges
it.

Löwy's "project design" step normally also assigns services to teams. On a solo project that
step collapses into a single sequenced, independently-testable task list — the point is the
*mechanical derivation from the architecture*, not who does each task.

## Drafting the project plan

**The implement step (do the work)**, in order:

1. **Read the approved `system-design.md`** — the service map, each service's classification
   (Client/Manager/Engine/Resource Access/Resource), and the static diagram's call directions.
2. **Derive the build order** mechanically from the call directions: Resource Access and
   Engines before the Managers and Clients that depend on them (a service can only be built
   once every service it calls exists or is stubbed). The bar's item 2, *Build order follows
   the call directions*, judges the result. What that means while drafting: don't renegotiate
   the order by convenience — it follows from the architecture.
3. **Flag ADR-worthy services** — a service boundary, protocol choice, or schema decision that
   would be expensive to reverse gets a line item to open an ADR *before* that service is
   built, not after. The bar's item 4, *ADR flags are real and come before the build*, judges
   which flags are genuine and where they sit.
4. **Write the task list**: one task per service (or a natural sub-slice of a large one), each
   independently testable, in the build order from step 2. For each task, name what it depends
   on and the integration checkpoint that proves it's wired correctly with its callers.

The approved task list is what the per-slice implementation specs and the implementation work
— in the product-code tree the `development` work type's stack overlay names — are then
derived from.

## Rules

- **Form** — rules as items, each with the shortest example that teaches it, per
  [`ai-authoring.md`'s Principles](../../../method/ai-authoring.md#principles). Guidance, not scored.
- **Derive, don't design** — the bar's item 1 states it and judges it. What that means while
  drafting: this document translates an already-approved architecture into a sequence; it does
  not introduce new services or change call directions. If building the plan reveals a gap in
  `system-design.md`, fix that document first — through its own work file and its own review
  cycle — and then resume here. A plan that patches the gap locally is the defect item 1
  catches.
- **Independently testable tasks** — the bar's item 3, *Tasks are complete and independently
  testable*, states it and judges it. What that means while drafting: each task is verifiable
  on its own before the next depends on it, which is what makes the derivation mechanical
  rather than a guess.
- **ADR before build, not after** — the bar's item 4 states it and judges it. What that means
  while drafting: a structural decision surfaced by a service boundary gets its ADR opened
  before the task that depends on it, never retrofitted.

## Common mistakes

Mistakes in how the work is done. The defects themselves are enumerated once, in the bar, so
none of them is restated here:

- Starting before `system-design.md` has completed its own review and approval cycle, so the
  plan derives from a moving target.
- Reordering tasks for convenience instead of following the call-direction dependency order.
- Treating "project design" as team/people assignment when there is no team — the task and
  build-order breakdown is the point on a solo project.
- Fixing an architecture gap inside the plan instead of sending it back to `system-design.md`.
- Drafting against this file alone and never opening `done.md` — the bar is where
  most of what a review will say already is.
