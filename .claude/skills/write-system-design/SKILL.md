---
name: write-system-design
description: Use when authoring or changing the system-design document in this project — the volatility-based service decomposition (Löwy's IDesign Method) that the implementation architecture is derived from.
---

# Write the system design

A system design is a volatility-based service decomposition — static and dynamic architecture —
validated against the behaviour already drafted in the analysis documents, never derived from it
one service per use case.

`CLAUDE.md`'s **Model selection** table names the files in the `documentation` row — one work
file and one completion bar, as in every other row. Both route onward, because the label covers
two documents: the work file carries a route per document, and the completion bar carries the
same routes plus the condition itself and why the label splits. Follow them through to the system design's
own pair and follow those. The work file there carries how the document is written; the
completion bar carries what must be true before the draft is reviewable, and is also what the
review applies, so satisfying it is not a separate exercise from passing review. A change
touching the project plan instead follows that branch, through the same two files.

The lifecycle around the draft — issue, worktree, PR, review, fix, merge — is the contribution
workflow's, routed from `CLAUDE.md`'s **Contribution workflow** section. The work file states
only what is specific to the system design.
