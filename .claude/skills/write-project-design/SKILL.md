---
name: write-project-design
description: Use when authoring or changing the project-plan document in this project — the implementation task breakdown and build order derived mechanically from an approved system design, per Löwy's "project design" step.
---

# Write the project design

A project plan is the implementation task breakdown, build order and per-service ADR flags,
derived mechanically from an approved system design. It consumes that architecture; it never
decomposes services itself.

`CLAUDE.md`'s **Model selection** table names the files in the `documentation` row. That row
splits on which document the change touches: take the branch for the **project-plan** document
and read and follow both files its *How the work is done* column labels there. The **work file**
carries the derivation order, the ADR-flagging step and the task-list shape; the **completion
bar** carries what must be true before the draft is reviewable, including that the plan is
judged against the system design rather than on its own. The same bar is what the review
applies, so satisfying it is not a separate exercise from passing review.

The lifecycle around the draft — issue, worktree, PR, review, fix, merge — is the contribution
workflow's, routed from `CLAUDE.md`'s **Contribution workflow** section. The work file states
only what is specific to the project plan.
