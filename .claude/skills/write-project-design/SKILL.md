---
name: write-project-design
description: Use when authoring or changing docs/design/project-plan.md in the Smart Charging project — deriving the implementation task breakdown mechanically from an approved docs/design/system-design.md, per Löwy's "project design" step.
---

# Write the project design (task breakdown from architecture)

Author `docs/design/project-plan.md`: the implementation task breakdown, build order, and
per-service ADR flags, derived mechanically from an approved `docs/design/system-design.md`.
Rationale: `docs/plans/2026-07-07-lowy-system-design-method.md`. **Requires an approved
`system-design.md` to exist first** — this skill consumes it, it does not decompose services
itself.

Löwy's "project design" step normally also assigns services to teams. On a solo project, that
step collapses into a single sequenced, independently-testable task list — the point is the
*mechanical derivation from the architecture*, not who does each task.

## The cycle (do every step, in order)

0. **Open (or link) a GitHub issue** describing the intent and scope. Branch as
   `docs/<issue-number>`, per CLAUDE.md's branch-naming convention.
1. **Read the approved `system-design.md`** — the service map, each service's classification
   (Client/Manager/Engine/Resource Access/Resource), and the static diagram's call directions.
2. **Derive the build order** mechanically from the call directions: Resource Access and Engines
   before the Managers and Clients that depend on them (a service can only be built once every
   service it calls exists or is stubbed). Don't renegotiate the order by convenience — it follows
   from the architecture.
3. **Flag ADR-worthy services** — a service boundary, protocol choice, or schema decision that
   would be expensive to reverse gets a line item to open an ADR (via `write-adr`) *before* that
   service is built, not after.
4. **Write the task list**: one task per service (or a natural sub-slice of a large one), each
   independently testable, in the build order from step 2. For each task, name what it depends on
   and the integration checkpoint that proves it's wired correctly with its callers.
5. **Self-check**: the build order doesn't contradict the static diagram's call directions; every
   ADR-worthy service from step 3 has a task line before the service that depends on it; every
   service in `system-design.md` appears in exactly one task (no service dropped, none duplicated).
6. **Review** — launch the `system-design-reviewer` agent (fresh, separate Opus; never review
   inline). It re-reads `system-design.md` alongside this plan to check consistency.
7. **Address** the review feedback.
8. **Manual review** — present the addressed draft to the human partner and get explicit approval
   before committing.
9. **Commit** (`docs: add project plan` or `docs: revise project plan`), referencing the issue
   from step 0.
10. **Stop and report** status. The approved task list feeds `writing-plans`/implementation work
    under `custom_components/`.

## Rules

- **Derive, don't design.** This document translates an already-approved architecture into a
  sequence; it does not introduce new services or change call directions. If building the plan
  reveals a gap in `system-design.md`, fix that document first (re-run `write-system-design`'s
  review cycle), then resume here.
- **Independently testable tasks.** Each task should be verifiable on its own before the next
  depends on it — that's what makes the derivation mechanical rather than a guess.
- **ADR before build, not after.** A structural decision surfaced by a service boundary gets its
  ADR opened before the task that depends on it, never retrofitted.

## Common mistakes

- Reordering tasks for convenience instead of following the call-direction dependency order.
- Treating "project design" as team/people assignment when there's no team — the task/build-order
  breakdown is the point on a solo project.
- Skipping the ADR flag for a service boundary that's clearly a structural decision.
- Starting this skill before `system-design.md` has completed its own review/approval cycle.
