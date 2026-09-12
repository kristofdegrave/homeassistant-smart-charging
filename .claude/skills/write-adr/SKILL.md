---
name: write-adr
description: Use when making or changing an architectural decision in this project — drafting a new Architecture Decision Record, or superseding an existing one.
---

# Write an ADR

An architectural decision is captured as a numbered, immutable Architecture Decision Record.

`CLAUDE.md`'s **Model selection** table names the work file in the `adr` row's *How the work is
done* column. Read it and follow it: it opens with the test for whether the decision is
ADR-worthy at all, then carries the numbering, the template, the self-checks, the cross-check
against existing ADRs, and the rules.

The lifecycle around the draft — issue, worktree, PR, review, fix, merge — is the contribution
workflow's, routed from `CLAUDE.md`'s **Contribution workflow** section. The work file states
only what is specific to an ADR, including the one branch-naming override that workflow
sanctions.
