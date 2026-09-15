---
layer: method
---

# From idea to result

[contribution-workflow.md](contribution-workflow.md) covers one unit of work, from its issue
to its merge. This document covers everything around that: how a raw idea gets routed,
specified, sliced into filed issues, and how a shipped slice is confirmed to actually work on
the real installation.

Eight stages. Each one names what it must produce before the next starts.

## 1. Capture

An in-conversation idea, or an existing issue with the `idea` label. Either way this stage
produces one `idea`-labelled issue: everything downstream — the decisions, the research
findings, the epic it is split from — is recorded against an issue, so an in-conversation idea
is filed before grilling starts. `work-idea` then runs the dialogue.

## 2. Grill

Stress-test the idea before decomposing it — `work-idea` runs this through the `grilling`
skill, which owns the technique. Two kinds of output, each with its own home:

- **Decisions** are written down, never left in chat scrollback: on the idea issue while
  grilling, then moved into the epic body under a *Decisions so far* heading when the epic is
  filed (**Ticket** below). One entry per settled question. A single-artifact idea, which
  never gets an epic, keeps them on its own issue.
- **Facts are the agent's job, never the user's.** A question of fact goes to the `research`
  skill, which owns which sources count, what the comment contains and how a durable finding
  is cited; what it produces is a comment **on the issue that needed it**. There is
  deliberately no research folder — a second store of facts would rot beside the analysis
  docs.

## 3. Route — two tracks

Every idea goes down exactly one track. The split is whether the behaviour already ships.

**New behaviour** → the analysis chain first: `requirement` and/or `uc`, plus an `adr` if a
structural decision surfaced (`CLAUDE.md`'s **Architecture Decision Records** section has the
bar for that). Then a spec, then tickets.

**Bug or enhancement against shipped behaviour** (the `bug`/`enhancement` kind label,
[contribution-workflow.md](contribution-workflow.md)'s **Issue conventions**; no context label
yet, because the fixing artifact is not known until the claim is verified) → skips the
analysis chain, but **the claim is verified before anything is designed** — the
`diagnosing-bugs` skill owns that step: reproduce it on the real installation, or as a
failing test at the harness seam ADR-0009 assigns to that layer. A claim that cannot be
reproduced is not a defect yet — say so on the issue and stop there rather than designing a
fix for a behaviour nobody has seen.

## 4. Spec

- **New behaviour**: always a `specs` issue.
- **Bug track**: a `specs` issue only when grilling yields more than one slice. A one-slice fix
  goes straight from the grilled issue to work.

**Gate: a `requirement` or `uc` change that touches shipped behaviour does not get
`needs-approval` until a `specs` issue exists for it** — a child of the epic, where there is
one. Without it, an analysis document can merge describing behaviour the code does not have. The review loop applies that
label automatically on a clean verdict and knows nothing about child issues
([ci-pipeline.md](ci-pipeline.md)), so on a CI-driven PR the same condition is checked by
whoever approves the merge. The `specs` issue is the
earliest artifact that can carry that obligation — a `development`/`testing` issue cannot,
because it needs an approved plan's anchored `Plan:` line
([contribution-workflow.md](contribution-workflow.md)'s **Issue conventions**), and no such
plan exists until the spec itself is drafted and reviewed.

The spec's own sections belong to the `specs` work type —
[work-types/specs/implement.md](work-types/specs/implement.md), named in that row of
`CLAUDE.md`'s **Model selection** table. Wherever it lands, it stays *derived*
from the analysis and design documents — it never introduces behaviour they do not already
state.

## 5. Ticket

A **single-artifact** idea is one issue, filed directly (`file-task-issue`); no epic. A
**multi-artifact strand** gets a new **epic issue** first, Size only. If the idea started as
an issue, link it from the epic body and close the idea issue once it is fully captured —
never relabel the idea issue as the epic, because an epic stays open tracking children long
after the idea itself is decomposed.

Children are **vertical, demoable slices**: each a narrow end-to-end path through every layer
it touches, sized to one context window, and observable on its own once deployed.
Layer-shaped children ("the adapter ticket", "the entity ticket") are the anti-pattern — they
cannot be demoed and cannot be verified live. File them in dependency order.

**Epic membership and ordering are native GitHub relationships, not body text** — sub-issues
for membership, blocked-by edges for order.
[contribution-workflow.md](contribution-workflow.md)'s **Issue conventions** owns that rule
and the label/field rules that apply to every child; the `gh` commands that create the edges
are in [tracker-mechanics.md](tracker-mechanics.md).

What to file when:

- **Everything already decidable, now**: the `adr` issue if a structural decision surfaced,
  the `specs` issue, and any already-scoped `uc`, `requirement` or `workflow` issue.
- **`development`/`testing` issues wait for the plan.** They require the anchored `Plan:`
  line, so they cannot be filed until the spec issue's plan is drafted and reviewed. File them
  then, one per task in the plan's build order.
- **Anything that surfaces later** and belongs to the strand — a bug found mid-implementation,
  a follow-up — is attached as a sub-issue too. Belonging to an epic does not require a
  drafter-facing context label; `file-task-issue` covers which label such a child takes.

Milestone and priority are not yet standardized. Note urgency in the epic body rather than
inventing a scheme ad hoc.

## 6. Execute

[contribution-workflow.md](contribution-workflow.md), unchanged: issue → worktree → PR →
review → merge.

## 7. Verify live

A slice is not finished when it merges; it is finished when it has been observed working on
the real installation — otherwise every later slice is built on a foundation nobody has seen
run.

What that pass must produce, when it blocks the next slice, and how it differs from the
pre-merge runtime-verified self-check is the **Verify live** bar in
[definition-of-done.md](definition-of-done.md).

## 8. Close

When every child is closed and its slice verified live, close the epic with a summary of what
shipped. The originating idea issue is already closed — that happened at **Ticket**, once the
strand was fully captured.

---

The topics below govern this project's analysis and design documents — the artifact chain the
stages above run through. They moved here from `CLAUDE.md` with their rules unchanged — only
`###` sub-headings added and relative pointers made explicit — and are reached through its
routing table, so each keeps the heading it had there. They are **parked**:
this document is to become the method's default idea-to-product flow, and that rewrite names
their final home.

## Document structure

The full methodology is documented in
[2026-06-24-analysis-approach-design.md](../plans/2026-06-24-analysis-approach-design.md) — that
plan doc's own Document Structure/Writing Order sections predate the pivot recorded in
`docs/analysis/flows/README.md`; this topic and **Writing order** below are the current ones.

### The analysis documents

```text
docs/analysis/
  system-overview.md    — stakeholders, problem, goals, hardware
  requirements.md       — what the system must do (6Cs + SMART + MoSCoW)
  control-cycle.md      — start here: the coordinator loop (read → smooth → dispatch → clamp → set)
  resolution-rules.md   — shared priority-ordered lookups (active SOC limit, departure deadline,
                           effective peak limit, Auto mode-selection)
  entity-catalog.md     — every owned entity, config key, and adapter role: id/key, unit,
                           default, Read by / Written by
  use-cases/            — one goal-oriented UCnn-*.md per behaviour (inventory in
                           use-cases/README.md); flows/README.md is a historical mapping only —
                           no further flow documents are planned
```

Previous iteration archived at `docs/archive/` — do not use as source of truth.

### The design documents

```text
docs/design/
  system-design.md    — volatility-based service decomposition (Löwy's Method): static + dynamic architecture
  project-plan.md      — implementation task breakdown derived mechanically from system-design.md
```

See `docs/plans/2026-07-07-lowy-system-design-method.md` for the rationale, and the
`documentation` row of `CLAUDE.md`'s **Model selection** table for the cycle — its work file and
completion bar, which route onward, own how each of these two documents is written and what
"finished" means for it, including the Method's own discipline about what may drive a
decomposition.

### The architecture decision log

```text
docs/adl/
  template.md            — ADR template (Nygard + Considered options)
  0001-...md, 0002-...md — one file per architectural decision, sequential, never renumbered
```

### The post-mortems

```text
docs/postmortems/
  YYYY-MM-DD-<slug>.md — one dated analysis per shipped failure
```

What a post-mortem is, the two rules that do not reach it, and how it is reviewed are
`CLAUDE.md`'s **Post-mortems** topic.

## Writing order

### Analysis first, design once the use-cases are stable

1. `system-overview.md`
2. `requirements.md` (fresh from idea — not from archive)
3. `control-cycle.md`, then `resolution-rules.md`, then `entity-catalog.md`, then `use-cases/`
   one at a time
4. Revisit `requirements.md` after use-cases reveal gaps
5. Once the relevant use-cases are stable, `design/system-design.md` (volatility-based
   decomposition), then `design/project-plan.md` — before opening ADRs for the structural
   decisions the design surfaces

## Requirements standard

### What, never how — MoSCoW, SMART and the 6Cs

- Describe **what**, never **how**
- MoSCoW priority on every requirement
- SMART acceptance criteria
- 6Cs quality check: Clarity, Concision, Completeness, Consistency, Correctness, Concreteness
- Reference: [modernrequirements.com — Good Software Requirements](https://www.modernrequirements.com/blogs/good-software-requirements/)

## DDD alignment (lightweight)

### Two concepts adopted; tactical DDD out of scope

Two DDD concepts are intentionally adopted:

1. **Ubiquitous Language glossary** — lives in `system-overview.md`. Every domain term used across documents must be defined here first.
2. **Domain events** — each use-case and mechanism document lists the events it produces (past tense, PascalCase, e.g. `ChargingStarted`). Shown as named nodes in Mermaid diagrams. Map directly to HA automation triggers.

Full tactical DDD (Aggregates, Repositories, Value Objects) is out of scope.

## Review protocol for analysis documents

New or changed documents under `docs/analysis/**` follow the
[Contribution workflow](contribution-workflow.md), with these artifact-specific additions:

### The draft and the review come from the `uc` and `requirement` rows

- **The implement step's draft** and **the review step's review**: the `uc` and `requirement`
  rows of `CLAUDE.md`'s **Model selection** table name the files, and they are their only
  home — don't restate them here. Each row's work file carries how that artifact is written
  (the template, the numbering, the propagation step); the completion bar carries what must be
  true of the finished document — the 6Cs pass, the glossary-first check, cross-document
  consistency, requirement coverage — and both the author's self-check and the reviewer's
  criteria are that one file. It is one bar serving both rows, for the reason stated in the
  document that table's heading routes to, and it is written to cover this whole tree: a change
  touching only a document neither row owns — a mechanism document, or the glossary — is judged
  by that same bar, which carries a section for that kind of document.

### Never reference PR numbers or issue tracking statuses

- **Never reference PR numbers or issue tracking statuses** (e.g. "PR #30, still open",
  "issue #29, resolved", "has landed") inside the document body. These are ephemeral
  repo-management facts that rot as PRs merge and issues close and don't belong in a document
  meant to record durable reasoning — describe the underlying fact directly instead (e.g.
  "has since been reworded", not "issue #29 has since reworded"). This applies to ADRs too.

## Flow document standard

### Section order and Mermaid types

Applies to `control-cycle.md` (the one remaining flow document): Purpose → Trigger → **Domain events** → Mermaid diagram → Steps → Edge cases → Requirements satisfied.

Preferred Mermaid types: `flowchart TD`, `stateDiagram-v2`, `sequenceDiagram`.
