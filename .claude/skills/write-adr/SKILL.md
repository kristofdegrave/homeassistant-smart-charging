---
name: write-adr
description: Use when making or changing an architectural decision in this project — drafting a new Architecture Decision Record, or superseding an existing one.
---

# Write an ADR

An architectural decision is captured as a numbered, immutable Architecture Decision Record.

`CLAUDE.md`'s **Model selection** table names the files in the `adr` row. Read and follow both
of the ones its *How the work is done* column names: the **work file** carries the numbering,
the template, the cross-check against existing ADRs and the rules; the **completion bar**
carries what must be true before the draft is reviewable, including whether the decision
warranted a record at all. The same bar is what the review applies, so satisfying it is not a
separate exercise from passing review.

The lifecycle around the draft — issue, worktree, PR, review, fix, merge — is the contribution
workflow's, routed from `CLAUDE.md`'s **Contribution workflow** section. The work file states
only what is specific to an ADR, including the one branch-naming override that workflow
sanctions.
