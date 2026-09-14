---
name: write-impl-spec
description: Use when authoring an implementation spec and TDD plan for a slice of the Smart Charging build (a docs/plans/YYYY-MM-DD-<slice>-design.md plus its paired task plan) — deriving the concrete, test-driven build sequence from an approved project-plan slice and the ADRs, before any custom_components/ code is written.
---

# Write an implementation spec (per-slice design + TDD plan)

A build slice is specified as two documents that derive from an already-approved slice of the
project plan: a per-slice design, and the task-by-task TDD plan built from it.

`CLAUDE.md`'s **Model selection** table names the files in the `specs` row. Read and follow
both of the ones its *How the work is done* column names: the **work file** carries the
drafting order, the derive-don't-design discipline, the cap on both documents and the rules;
the **completion bar** carries what must be true before the draft is reviewable, including the
Verify-live checklist the slice is judged against after deployment. The same bar is what the
review applies, so satisfying it is not a separate exercise from passing review.

The lifecycle around the draft — issue, worktree, PR, review, fix, merge — is the contribution
workflow's, routed from `CLAUDE.md`'s **Contribution workflow** section. The work file states
only what is specific to an implementation spec.
