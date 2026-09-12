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

The spec's own sections belong to `write-impl-spec`. Wherever it lands, it stays *derived*
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
