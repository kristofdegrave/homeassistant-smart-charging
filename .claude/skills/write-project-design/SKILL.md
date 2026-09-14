---
name: write-project-design
description: Use when authoring or changing the project-plan document in this project — the implementation task breakdown and build order derived mechanically from an approved system design, per Löwy's "project design" step.
---

# Write the project design

A project plan is the implementation task breakdown, build order and per-service ADR flags,
derived mechanically from an approved system design. It consumes that architecture; it never
decomposes services itself.

`CLAUDE.md`'s **Model selection** table names the files in the `documentation` row — one work
file and one completion bar, as in every other row. Both route onward, because the label covers
two documents: the work file carries a route per document, and the completion bar carries the
same routes plus the condition itself and why the label splits. Follow them through to the project plan's
own pair and follow those. The work file there carries how the document is written; the
completion bar carries what must be true before the draft is reviewable, and is also what the
review applies, so satisfying it is not a separate exercise from passing review. A change
touching the system design instead follows that branch, through the same two files.

The lifecycle around the draft — issue, worktree, PR, review, fix, merge — is the contribution
workflow's, routed from `CLAUDE.md`'s **Contribution workflow** section. The work file states
only what is specific to the project plan.
