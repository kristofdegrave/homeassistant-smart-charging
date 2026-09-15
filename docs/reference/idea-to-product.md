# From idea to product — the default flow

[contribution-workflow.md](contribution-workflow.md) covers one unit of work, from its issue
to its merge. This document covers the whole route an idea takes to a shipped result that has
been seen working: the **stages** in order, the **artifact** each produces, the **gate** that
must hold before the next one starts, and the **skills** used at each. It is the method's
default flow — what a project follows unless its profile says otherwise — and the document a
ported project reads first.

## How the stages are read

### The profile's deviations apply over this document

Before following a stage, read [profile.md](profile.md)'s **Flow**. It states either that this
project follows the flow as written, or one `###` per deviation — a stage removed, added or
reordered, a gate changed — each with its why. A deviation applies over the stage it names; the
contract for how one is written is that section's, and the method check refuses a deviation
whose work type this project does not enable.

### A stage whose work type the profile does not enable is skipped

Each artifact stage below carries the context label of the work type that produces its
artifact. A stage whose work type is absent from `.claude/profile.yml`'s `work_types.enabled`
is skipped, with no deviation needed — its gate then holds vacuously, and the next stage's
gate is the one that has to hold. The stages that carry no work type — Capture, Brainstorm,
Route, Ticket, Verify live, Close — are the flow's spine: a project that wants them changed
changes the method, since a deviation has no work type to name. One enabled work type has no
stage the other way round: `workflow` work changes the method's own tooling — a skill, a
reference document, the pipeline — so it is not a step an idea passes through; a `workflow`
issue is filed at **Ticket** like any other child and runs the chain, outside the artifact
chain.

### Where a stage names this project's documents, that is the instance, not the method

The stages are the method's; several of their rules name what this project fills them with —
the harness seam an ADR of this project assigns at **Route**, the analysis files and their
order at **Analysis**, every tree under **Document structure**. Those are this project's
instance of the method's slots, carried here until the stack overlays take them, the way the
work-type files still carry their stack-specific sentences (`CLAUDE.md`'s **Authoring AI
artifacts** topic concedes as much for those). A project porting the flow replaces the named
documents and keeps the stages; a deviation is for a stage, not for a document name.

### Every artifact stage runs through the contribution workflow

An artifact stage is one or more units of work, and each one runs
[contribution-workflow.md](contribution-workflow.md)'s chain unchanged — issue → worktree →
PR → review → merge — through the chain's own step skills (`file-task-issue`, `implement`,
`review`, `fix`, `cleanup`). A stage's **Skills** list therefore names only what is used at
that stage *besides* the chain's; the chain is never re-listed. How the artifact is written and
what "finished" means for it are the work file and completion bar the work type's row of
`CLAUDE.md`'s **Model selection** table names: this document says what a stage produces and
when it may start, never how.

### A gate names the rule that owns it

A gate is the condition that must hold before the next stage starts. Where another document
owns the rule the gate rests on, the gate names that rule and does not restate it — the gate is
the *placement* of the rule in the flow, not a second copy of it.

## 1. Capture

An in-conversation idea, or an existing issue with the `idea` label. Either way this stage
produces one `idea`-labelled issue: everything downstream — the decisions, the research
findings, the epic it is split from — is recorded against an issue, so an in-conversation idea
is filed before brainstorming starts.

### Artifact: one `idea`-labelled issue

Filed with the `idea` label alone — no context label yet, since nothing is scoped.

### Gate: the issue exists before anything is discussed

The issue-first rule, stated in `CLAUDE.md`'s own rules; here it means the `idea` issue is the
first thing that exists, not the epic.

### Skills

`file-task-issue`.

## 2. Brainstorm

**Mandatory, whatever form the idea arrived in** — a one-line thought, a filed `idea` issue, a
bug report that turns out to be a feature. An idea decomposed without the human partner's
buy-in relocates the ambiguity into the child issues, so no idea skips this stage. Two skills
own the technique, and the shape of the idea picks between them:

- **`grilling`** for a branch-heavy idea — one where settling a decision opens further
  decisions, so the dialogue has to work a design tree in rounds.
- **`brainstorming`** for a narrow one — a single artifact or a single behaviour, where the
  questions are few and the design converges in one pass.

`work-idea` sequences the stage for an `idea` issue: it runs the dialogue and writes the
outputs to their homes. Two kinds of output, each with its own home:

- **Decisions** are written down, never left in chat scrollback: on the idea issue while
  brainstorming, then moved into the epic body under a *Decisions so far* heading when the epic
  is filed (**Ticket** below). One entry per settled question. A single-artifact idea, which
  never gets an epic, keeps them on its own issue.
- **Facts are the agent's job, never the user's.** A question of fact goes to the `research`
  skill, which owns which sources count, what the comment contains and how a durable finding
  is cited; what it produces is a comment **on the issue that needed it**. There is
  deliberately no research folder — a second store of facts would rot beside the analysis
  docs.

### Artifact: the decisions, on the issue

One entry per settled question, plus a `research` comment per question of fact.

### Gate: every decision written, no question of fact left open

The idea is scoped enough to route and split — not designed in detail; that belongs to each
child's own stage. A question of fact still open is answered by a `research` comment before
the stage ends, not carried forward as an assumption.

### Skills

`work-idea`, `grilling`, `brainstorming`, `research`.

## 3. Route — two tracks

Every idea goes down exactly one track. The split is whether the behaviour already ships.

**New behaviour** → the artifact chain, from stage 5 onward, as far as the idea reaches: an
`adr` if a structural decision surfaced (`CLAUDE.md`'s **Architecture Decision Records** topic
has the bar for that), `requirement` and/or `uc`, design, spec, then the task issues.

**Bug or enhancement against shipped behaviour** (the `bug`/`enhancement` kind label,
[contribution-workflow.md](contribution-workflow.md)'s **Issue conventions**; no context label
yet, because the fixing artifact is not known until the claim is verified) → skips the
analysis chain, but **the claim is verified before anything is designed** — the
`diagnosing-bugs` skill owns that step: reproduce it on the real installation, or as a
failing test at the harness seam ADR-0009 assigns to that layer. A claim that cannot be
reproduced is not a defect yet — say so on the issue and stop there rather than designing a
fix for a behaviour nobody has seen. Once the fixing artifact is known, the issue gains that
artifact's context label and re-enters the chain at that artifact's stage.

### Artifact: the chosen track, written on the issue

And, on the shipped-behaviour track, the reproduction `diagnosing-bugs` leaves behind.

### Gate: on the shipped-behaviour track, the claim is reproduced

What counts as a reproduction is `diagnosing-bugs`'s to say. On the new-behaviour track this
gate does not apply; the track written on the issue is enough.

### Skills

`work-idea`, `diagnosing-bugs`.

## 4. Ticket

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

Whether the strand needs a `specs` issue is settled here, and written on the issue so it is
not re-argued:

- **New behaviour**: always a `specs` issue.
- **Bug track**: a `specs` issue only when brainstorming yields more than one slice. A
  one-slice fix goes straight from the routed issue to work.

What to file when:

- **Everything already decidable, now**: the `adr` issue if a structural decision surfaced,
  the `specs` issue, and any already-scoped `uc`, `requirement`, `documentation` or `workflow`
  issue.
- **`development`/`testing` issues wait for the plan.** They require the anchored `Plan:`
  line, so they cannot be filed until the spec issue's plan is drafted and reviewed. File them
  then, one per task in the plan's build order — the **Spec** stage's gate below says when.
- **Anything that surfaces later** and belongs to the strand — a bug found mid-implementation,
  a follow-up — is attached as a sub-issue too. Belonging to an epic does not require a
  drafter-facing context label; `file-task-issue` covers which label such a child takes.

Milestone and priority are not yet standardized. Note urgency in the epic body rather than
inventing a scheme ad hoc.

### Artifact: the epic and every child that is already decidable

Or the single issue, where the idea is one artifact.

### Gate: every decidable issue is filed, with its edges

Each child carries one context label and its board fields, sits under the epic as a native
sub-issue, and carries a blocked-by edge to each issue it cannot start before — the rules are
**Issue conventions**'; the check is that nothing downstream starts without an issue to run
against.

### Skills

`file-task-issue`.

## 5. ADR

The first artifact stage, and a **re-entrant** one: it is entered at the first point a
structural decision surfaces — usually Brainstorm — and entered again whenever a later stage
surfaces another, Design being the usual case. Whether a decision is architectural at all, the
calibration test and the two carve-outs are `CLAUDE.md`'s **Architecture Decision Records
(ADRs)** topic; the ADR is never edited in place once accepted, only superseded, per the same
topic.

### Artifact: one numbered record under `docs/adl/`

The `adr` work type's; the tree is under **Document structure** below.

### Gate: the ADR is merged before the work that depends on it is committed

The rule is the **Architecture Decision Records (ADRs)** topic's first sentence; here it
places the ADR ahead of every artifact that assumes the decision — an analysis document, a
design, a spec or code.

### Skills

`research` — for the facts an ADR's Context rests on, cited from the record by linking the
issue comment.

## 6. Analysis

The analysis documents under `docs/analysis/` — what the system must do and why, before any
design says how. Two work types write into this tree: `requirement` for the requirements, the
constraints and the glossary, `uc` for the use-cases. The rules that govern the tree are the
`###` below; how each document is drafted is the work file its row names.

### Artifact: the analysis documents, one change per issue

The tree is under **Document structure** below.

### Analysis first, in this order

1. `system-overview.md`
2. `requirements.md` (fresh from idea — not from archive)
3. `control-cycle.md`, then `resolution-rules.md`, then `entity-catalog.md`, then `use-cases/`
   one at a time
4. Revisit `requirements.md` after use-cases reveal gaps

The design documents follow once the relevant use-cases are stable — the **Design** stage's
own order.

### What, never how — MoSCoW, SMART and the 6Cs

- Describe **what**, never **how**
- MoSCoW priority on every requirement
- SMART acceptance criteria
- 6Cs quality check: Clarity, Concision, Completeness, Consistency, Correctness, Concreteness
- Reference: [modernrequirements.com — Good Software Requirements](https://www.modernrequirements.com/blogs/good-software-requirements/)

### Two DDD concepts adopted; tactical DDD out of scope

Two DDD concepts are intentionally adopted:

1. **Ubiquitous Language glossary** — lives in `system-overview.md`. Every domain term used across documents must be defined here first.
2. **Domain events** — each use-case and mechanism document lists the events it produces (past tense, PascalCase, e.g. `ChargingStarted`). Shown as named nodes in Mermaid diagrams. Map directly to HA automation triggers.

Full tactical DDD (Aggregates, Repositories, Value Objects) is out of scope.

### Section order and Mermaid types

Applies to `control-cycle.md` (the one remaining flow document): Purpose → Trigger → **Domain events** → Mermaid diagram → Steps → Edge cases → Requirements satisfied.

Preferred Mermaid types: `flowchart TD`, `stateDiagram-v2`, `sequenceDiagram`.

### The draft and the review come from the `uc` and `requirement` rows

New or changed documents under `docs/analysis/**` follow the contribution workflow with these
artifact-specific additions, and this rule is the first of them:

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

### Gate: a change touching shipped behaviour has a `specs` issue before `needs-approval`

**A `requirement` or `uc` change that touches shipped behaviour does not get
`needs-approval` until a `specs` issue exists for it** — a child of the epic, where there is
one. Without it, an analysis document can merge describing behaviour the code does not have.
The review loop applies that label automatically on a clean verdict and knows nothing about
child issues ([ci-pipeline.md](ci-pipeline.md)), so on a CI-driven PR the same condition is
checked by whoever approves the merge. The `specs` issue is the earliest artifact that can
carry that obligation — a `development`/`testing` issue cannot, because it needs an approved
plan's anchored `Plan:` line ([contribution-workflow.md](contribution-workflow.md)'s **Issue
conventions**), and no such plan exists until the spec itself is drafted and reviewed.
Whether a change touches shipped behaviour is settled by the propagation step each row's work
file carries.

### Skills

`research` — for a fact a requirement or use-case rests on, cited from the document by
linking the issue comment.

## 7. Design

The design documents under `docs/design/`: `system-design.md`, the volatility-based service
decomposition, then `project-plan.md`, the task breakdown derived from it. Written once the
relevant use-cases are stable, and **before opening ADRs for the structural decisions the
design surfaces** — which is the re-entry into the **ADR** stage above. The `documentation`
work type's row names the work file and bar for each of the two documents, including the
Method's own discipline about what may drive a decomposition.

### Artifact: `system-design.md`, then `project-plan.md`

The tree is under **Document structure** below.

### Gate: the slice a spec derives from is in an approved `project-plan.md`

The **Spec** stage derives from one slice of `project-plan.md` and never re-decomposes the
system — the rule is the `specs` work file's, *derive, don't design*. So a design change that
adds or reshapes a slice is merged before the spec for that slice is drafted, and a structural
decision the design surfaced has its ADR first (the **ADR** stage's gate).

### Skills

`domain-driven-design` — the strategic-design vocabulary the decomposition is argued in.

## 8. Spec

One design document and one TDD plan per build slice, both under `docs/plans/`, both
**derived** from the approved slice of `project-plan.md` and from the analysis documents — a
spec never introduces behaviour they do not already state. The `specs` row's work file carries
the drafting order, the cap on both documents and the slice's Verify-live checklist; its bar
carries what a finished spec must show.

### Artifact: the slice's design and TDD plan, under `docs/plans/`

Two documents per slice; the `specs` row names how each is written.

### Gate: the plan is merged, and its task issues are filed

A `development`/`testing` issue needs the anchored `Plan:` line, so none can exist before the
plan does (**Ticket** above). Filing them, one per task in build order, is part of finishing
the spec issue — the rule is [contribution-workflow.md](contribution-workflow.md)'s **Merge
and issue closing**, run by the chain's clean-up step. The **Implementation** stage starts
from those issues and from nothing else.

### Skills

`brainstorming` — scoping the slice boundary and the deferrals before writing;
`writing-plans` — deriving the TDD plan.

## 9. Implementation

One plan task per issue, TDD one behaviour at a time, against the files the `development` row
names. The row's work file carries the loop itself, the pre-commit self-check and the stack
references it sends the author to;
its bar, and the **Definition of Done** the contribution workflow names, carry what a finished
task must show, the Runtime check included. Stack skills are the work file's to name, never
this document's.

### Artifact: the task's code and its tests, one PR per task

Each PR closes its task issue and carries `Part of` for the epic.

### Gate: the Definition of Done, Runtime check included

The floor is `CLAUDE.md`'s **Definition of Done** topic — builds clean, tests green, coverage
matching the change, runtime-verified with the observation recorded in the PR — plus the
`development` bar the row names. A task whose diff changes observable runtime behaviour
carries the Runtime check section; that topic says which diffs do.

### Skills

`test-driven-development`, `verification-before-completion`, `receiving-code-review`.

## 10. Tests

Test-authoring work with a plan task of its own — a suite the plan calls for that no
implementation task carries, a harness, a regression test for a verified defect — under the
`testing` work type. It runs interleaved with **Implementation**, task by task in the plan's
build order, not after it: a project whose plans fold every test into its implementation tasks
has no issues at this stage, and a project that does not enable `testing` skips it, the
**Implementation** stage's bar then carrying the tests.

### Artifact: the task's tests, one PR per task

In the harness the plan task names for them.

### Gate: the Definition of Done, in the harness matched to what is tested

The same floor as the **Implementation** stage — `CLAUDE.md`'s **Definition of Done** topic —
plus the `testing` bar the row names; which harness a test belongs in is the tier taxonomy the
topic cites.

### Skills

`test-driven-development`, `verification-before-completion`, `receiving-code-review`.

## 11. Verify live

A slice is not finished when it merges; it is finished when it has been observed working on
the real installation — otherwise every later slice is built on a foundation nobody has seen
run.

What that pass must produce, when it blocks the next slice, and how it differs from the
pre-merge runtime-verified self-check is the **Verify live** bar in
[definition-of-done.md](definition-of-done.md).

### Artifact: the observation, as a comment on the epic

Or on the task issue where the work has no epic — the bar says which.

### Gate: the first slice of a strand is verified live before slice two starts

The bar's own rule; here it is what stops the **Implementation** stage of the next slice.

### Skills

None of the method's: the checklist comes from the spec, and the pass is run by the author of
the merged slice against the running installation.

## 12. Close

When every child is closed and its slice verified live, close the epic with a summary of what
shipped. The originating idea issue is already closed — that happened at **Ticket**, once the
strand was fully captured.

### Artifact: the closed epic, with its summary

What shipped, in the epic's closing comment; the idea issue was closed at **Ticket**.

### Gate: every child closed and every slice verified live

An epic closed over an unverified slice hides exactly the gap the **Verify live** stage
exists to surface.

### Skills

None of the method's; the commands are `CLAUDE.md`'s **Tracker mechanics** topic's.

## Document structure

The trees the artifact stages above write into, and which document owns what. The full
methodology is documented in
[2026-06-24-analysis-approach-design.md](../plans/2026-06-24-analysis-approach-design.md) — that
plan doc's own Document Structure/Writing Order sections predate the pivot recorded in
`docs/analysis/flows/README.md`; this topic and the **Analysis** stage's order above are the
current ones.

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

Not a stage's artifact — a post-mortem records how a failure got past the flow, not a step of
it. What a post-mortem is, the two rules that do not reach it, and how it is reviewed are
`CLAUDE.md`'s **Post-mortems** topic.
