---
name: Use-case analysis
about: Request a Smart Charging use-case document to be drafted by the CI runner
title: "UCnn — <goal as an active verb phrase>"
labels: generate-uc
assignees: ""
---

<!--
Adding the `generate-uc` label triggers the generation workflow. The runner drafts
docs/analysis/use-cases/<slug>.md following the write-use-case skill, updates the
entity-catalog, and opens a PR that Closes this issue. A reviewer runs on the PR;
you give the final manual approval and merge.
-->

## Use-case

- **UC number:** UCnn
- **Goal:** <active verb phrase>
- **Primary actor:** <EV driver | Household energy manager>
- **Requirement(s) satisfied:** <e.g. R2>
- **File slug:** `docs/analysis/use-cases/<UCnn-slug>.md`
- **Mode use-case?** <yes → needs stateDiagram-v2 + State model | no>

## Key notes / scope

<!-- Anything the drafter must capture: alternate/exception flows, «extend»/«include»
relationships, thresholds, edge cases. See the plan's Task 4–13 table for the intended scope. -->

-

## Authoring contract (for the runner)

- Follow the **write-use-case** skill and the template in
  `docs/plans/2026-06-25-use-cases-design.md`.
- Every domain term must already be in the `system-overview.md` glossary — add it there first if not.
- Reference (do not restate) `control-cycle.md` and `resolution-rules.md`.
- Update `entity-catalog.md`'s *Read by* / *Written by* columns for every entity touched.
- Requirements satisfied must match the requirement(s) listed above.
