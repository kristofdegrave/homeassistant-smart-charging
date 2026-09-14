---
name: write-use-case
description: Use when authoring or editing a use-case document under docs/analysis/use-cases/ in the Smart Charging project (a UCnn-*.md file, or a change to one).
---

# Write a use-case

A use-case captures goal-oriented behaviour in Given/When/Then, referencing the shared
mechanism documents rather than restating them.

`CLAUDE.md`'s **Model selection** table names the files in the `uc` row. Read and follow both
of the ones its *How the work is done* column names: the **work file** carries the numbering,
the template, the rules, the diagram types and the propagation step; the **completion bar**
carries what must be true before the draft is reviewable. The same bar is what the review
applies, so satisfying it is not a separate exercise from passing review.

The lifecycle around the draft — issue, worktree, PR, review, fix, merge — is the contribution
workflow's, routed from `CLAUDE.md`'s **Contribution workflow** section. The work file states
only what is specific to a use-case.
