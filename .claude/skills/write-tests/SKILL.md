---
name: write-tests
description: Use when authoring or expanding a test suite for the Smart Charging integration — choosing the right harness per ADR-0009 (plain pytest for pure logic, HA harness for adapters/coordinator/entities), covering the mandated edge cases, and naming tests for requirement/UC traceability.
---

# Write tests

A test suite is authored in the harness its layer requires and covers the cases this project
mandates. This is usually reached from inside a development task's TDD loop, but it also stands
alone when back-filling or expanding coverage.

`CLAUDE.md`'s **Model selection** table names the files in the `testing` row. Read and follow
the two its *How the work is done* column labels **work file** and **completion bar**: the work
file carries how each test is chosen, named and structured; the completion bar carries what must
be true before the suite is reviewable, including the harness mapping and the mandated cases. The
same bar is what the review applies, so satisfying it is not a separate exercise from passing
review.

The lifecycle around the work — issue, worktree, PR, review, fix, merge — is the contribution
workflow's, routed from `CLAUDE.md`'s **Contribution workflow** section. The work file states
only what is specific to a test suite.
