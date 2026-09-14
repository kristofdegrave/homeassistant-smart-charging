---
name: develop-task
description: Use when implementing one task from a Smart Charging implementation plan (docs/plans/*.md) — writing the code and tests for that task test-first, following the project's ADR conventions, on Sonnet. Covers a single bite-sized task through to a reviewed, committed change.
---

# Develop one implementation-plan task (TDD)

One task from an approved implementation plan becomes working, test-covered code, written
test-first.

`CLAUDE.md`'s **Model selection** table names the files in the `development` row. Read and follow
the two its *How the work is done* column labels **work file** and **completion bar**: the work
file carries the reads, the TDD loop, the structural discipline and the rules; the completion bar
carries what must be true of the finished code before it is reviewable. The same bar is what the
review applies, so satisfying it is not a separate exercise from passing review.

The tests this loop writes are judged by the **`testing` row's** completion bar rather than this
row's — the work file and the bar both route there, and the bar states why.

The lifecycle around the work — issue, worktree, PR, review, fix, merge — is the contribution
workflow's, routed from `CLAUDE.md`'s **Contribution workflow** section. The work file states
only what is specific to a development task.
