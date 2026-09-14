---
name: write-system-design
description: Use when authoring or changing the system-design document in this project — the volatility-based service decomposition (Löwy's IDesign Method) that the implementation architecture is derived from.
---

# Write the system design

A system design is a volatility-based service decomposition — static and dynamic architecture —
validated against the behaviour already drafted in the analysis documents, never derived from it
one service per use case.

`CLAUDE.md`'s **Model selection** table resolves the files in the `documentation` row. That row
splits on which document the change touches: take the branch for the **system-design** document,
and read and follow the **work file** and the **completion bar** in the directory that branch
names — the roles inside it are fixed by convention. The work file carries the drafting order,
the service classifications, the diagrams and the rules; the completion bar carries what must be
true before the draft is reviewable. The same bar is what the review applies, so satisfying it is
not a separate exercise from passing review.

The lifecycle around the draft — issue, worktree, PR, review, fix, merge — is the contribution
workflow's, routed from `CLAUDE.md`'s **Contribution workflow** section. The work file states
only what is specific to the system design.
