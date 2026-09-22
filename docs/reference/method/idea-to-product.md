# From idea to product — the default flow

[contribution-workflow.md](contribution-workflow.md) covers one unit of work, from its issue
to its merge. This document covers the whole route an idea takes to a shipped result that has
been seen working: the **stages** in order, the **artifact** each produces, the **gate** that
must hold before the next one starts, and the **skills** used at each. It is the method's
default flow — what a project follows unless its profile says otherwise — and the document a
ported project reads first.

## How the stages are read

### The profile's deviations apply over this document

Before following a stage, read [profile.md](../profile.md)'s **Flow**. It states either that this
project follows the flow as written, or one `###` per deviation — a stage removed, added or
reordered, a gate changed — each with its why. A deviation applies over the stage it names; the
contract for how one is written is that section's, and the method check refuses a deviation
whose work type this project does not enable.

### A stage whose work type the profile does not enable is skipped

Each artifact stage below carries the context label of the work type that produces its
artifact — two labels where two work types write into one tree, as **Analysis** carries `uc`
and `requirement`. A stage none of whose work types is in `.claude/profile.yml`'s
`work_types.enabled` is skipped, with no deviation needed — its gate then holds vacuously, and
the next stage's gate is the one that has to hold; a stage with one of two enabled runs for
that one alone. The stages that carry no work type — Capture, Brainstorm,
Route, Decompose, Verify live, Close — are the flow's spine: a project that wants them changed
changes the method, since a deviation has no work type to name. One enabled work type has no
stage the other way round: `workflow` work changes the method's own tooling — a skill, a
reference document, the pipeline — so it is not a step an idea passes through; a `workflow`
issue is filed at **Decompose** like any other child and runs the chain, outside the artifact
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

The issue-first rule under `CLAUDE.md`'s **Rules that hold before anything is chosen**; here
it means the `idea` issue is the first thing that exists, not the epic.

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
  is filed (**Decompose** below). One entry per settled question. A single-artifact idea, which
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

**New behaviour** → the artifact chain, as far as the idea reaches: an `adr` if a structural
decision surfaced (`CLAUDE.md`'s **Architecture Decision Records** topic has the bar for that
— and the **ADR** stage is entered the moment one does, **Brainstorm** included, which is why
it is re-entrant), `requirement` and/or `uc`, design, then the spec and the task issues the
**Decompose** stage's closing step produces.

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

## 4. Decompose

Every issue a strand gets is filed here — the epic, the issues the artifact stages run
against, and one child per task of the spec. A strand that needs no epic files one issue and
stops; which strands those are is the first bullet set below.

The stage is **entered twice, with the artifact stages in between**, the way the **ADR** stage
below is: the issues those stages run against have to exist before they start, and the spec has
to derive from what they merged. The **opening pass** runs straight after **Route**; the
**closing step** runs once **Design** has merged. An issue that surfaces after both still
belongs here — the opening pass says where it attaches.

### The opening pass: the epic, and the issues the artifact stages run against

Where the bullets below call for an epic, it is filed first, Size only. If the idea started
as an issue, link it from the epic body and close the idea issue once it is fully captured —
never relabel the idea issue as the epic, because an epic stays open tracking children long
after the idea itself is decomposed. The brainstormed decisions move into its body under
*Decisions so far* (**Brainstorm** above).

Whether the strand needs an epic at all is settled here, and written on the issue so it is not
re-argued:

- **New behaviour**: always an epic, so there is always a body for the spec.
- **Bug track**: an epic only when brainstorming yields more than one slice. A one-slice fix
  goes straight from the routed issue to work.
- **A single-artifact idea**: no epic, so no spec and no closing step — one issue, filed
  directly (`file-task-issue`), and the stage ends there.

Everything already decidable is filed now: the `adr` issue if a structural decision surfaced,
and any already-scoped `uc`, `requirement`, `documentation` or `workflow` issue. Anything that
surfaces later and belongs to the strand — a bug found mid-implementation, a follow-up — is
attached as a sub-issue too; belonging to an epic does not require a drafter-facing context
label, and `file-task-issue` covers which label such a child takes.

**Epic membership and ordering are native GitHub relationships, not body text** — sub-issues
for membership, blocked-by edges for order.
[contribution-workflow.md](contribution-workflow.md)'s **Issue conventions** owns that rule
and the label/field rules that apply to every child; the `gh` commands that create the edges
are in [tracker-mechanics.md](tracker-mechanics.md).

Milestone and priority are not yet standardized. Note urgency in the epic body rather than
inventing a scheme ad hoc.

### The closing step: the epic body is the spec, and its children are the tasks

Once **Design** has merged, the spec for one build slice is written into the epic's body and
the children are cut from it. Four steps, each finishing before the next starts. This list is
the order; the mechanics of running each one — the scratch file, the dispatch, the `gh` calls,
the per-child filing checklist — are `file-task-issue`'s.

1. **The body is drafted**, and it is **derived** — see *Derive, don't design* below. Nothing
   else has to be written first, and no child exists yet to be cut from it.
2. **One fresh-agent pass over that body**, against the [decomposition
   checklist](decomposition-checklist.md), while the decomposition is still cheap to change.
   Its findings are fixed in the body.
3. **The human partner reads the fixed body** and says to go on. The pass is one agent run
   followed by that read — not repeated, and carrying no round cap, so a finding it raises is
   answered before the read rather than in a later round.
4. **The children are filed**, in build order, one issue per task.

**Derive, don't design.** The body turns one approved slice of `project-plan.md` into concrete
files, functions and tests, citing the analysis documents and the ADRs rather than restating or
overriding them. A service or call direction the design does not already name is not invented
here: it is an issue against the design document, run through that document's own issue-first
cycle, and the draft resumes after. Before writing a **behavioural** rule into the body, read
the document that owns it and act on which of three cases it is:

- **It says the same thing** — a duplicate. Cut it and cite the source.
- **No document says it** — the body would hold the only copy. Keep the text exactly as it
  stands, say so out loud on the issue, and open an issue against the document that should own
  it; the text becomes a citation once that document states the rule, never a deletion here. A
  decision, a file layout, a signature or a test boundary appears only here by construction and
  is not this case.
- **It says something different** — stop. No wording of the body resolves it; take it to the
  owning document.

**What the body carries**, and nothing another document owns:

- **Scope**, its success criteria, and the deliberate deferrals — a safety-relevant deferral
  stated out loud as a known deviation.
- **The decisions this slice makes** and the concrete structure they land in — files, classes,
  signatures — with a table mapping every piece to its named service in `system-design.md`.
- **Install-time config** the slice adds, and its packaging where it ships something.
- **The testing approach**, opening by naming the testing seam the tasks' failing tests drive
  through — one the suite already has over one the slice would add, and one seam for the whole
  slice where one reaches every task. Named up front, the seam is what every task's test is
  written against; found per task, each task invents its own.
- **One entry per task**, in build order.

**A task is a vertical, demoable slice**: a narrow end-to-end path through every layer it
touches, sized to one context window, and observable on its own once deployed. Layer-shaped
tasks ("the adapter ticket", "the entity ticket") are the anti-pattern — they cannot be demoed
and cannot be verified live. Each entry carries these keys, one item per key:

- **Files and test** — the exact paths, and the concrete failing test the task starts from.
- **Test boundary** — which harness that failing test drives through.
- **Blocked by** — the ids of the tasks it cannot start before, or `none`, stated either way so
  the filer can tell an empty set from an omission.
- **Sources** — the documents the entry was cut from.
- **Verify live** — one item per observable: the entity id and the value with its unit, or
  `none` and why in one line. Written now, not after deployment — a list written once the build
  exists is written from what the build produced rather than from what the task promised, and
  nothing downstream can tell those two apart.

Each child issue is then filed with that entry as its body, its context label and board fields,
its native sub-issue edge to the epic, a blocked-by edge per id the entry names, and the
anchored `Source:` lines naming the entry's sources, per
[contribution-workflow.md](contribution-workflow.md)'s **Issue conventions**.

### Artifact: the epic, and one issue per task

Or the single issue, where the idea is one artifact. The opening pass leaves the epic and the
issues the artifact stages run against; the closing step leaves the spec in the epic's body and
one child per task.

### Gate: the decomposition is reviewed and read, and every issue is filed with its edges

The opening pass's own gate is that nothing downstream starts without an issue to run against.
The closing step's is the pass of step 2 and the human read of step 3, both complete before any
child is filed, and then every task in the body having an issue — each with one context label,
its board fields, its `Source:` lines, its sub-issue edge and its blocked-by edges, the rules
being **Issue conventions**'. The **Implementation** stage starts from those issues and from
nothing else.

### Skills

`file-task-issue`; `brainstorming` — scoping the slice boundary and the deferrals before the
body is drafted; `writing-plans` — deriving the task entries and their build order.

## 5. ADR

The first artifact stage, and a **re-entrant** one: it is entered at the first point a
structural decision surfaces — usually Brainstorm — and entered again whenever a later stage
surfaces another, Design being the usual case. Whether a decision is architectural at all, the
calibration test and the two carve-outs are `CLAUDE.md`'s **Architecture Decision Records
(ADRs)** topic; once merged, the ADR is edited only as the `adr` work file permits and
otherwise superseded, per the same topic.

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

### Gate: a change touching shipped behaviour has an epic carrying its spec before `needs-approval`

**A `requirement` or `uc` change that touches shipped behaviour does not get
`needs-approval` until an epic whose body carries the spec exists for it.** Without it, an
analysis document can merge describing behaviour the code does not have.
The review loop applies that label automatically on a clean verdict and knows nothing about
child issues ([ci-pipeline.md](ci-pipeline.md)), so on a CI-driven PR the same condition is
checked by whoever approves the merge. The epic is the earliest artifact that can
carry that obligation — a `development`/`testing` child cannot, because it is cut from that
epic's body by the decomposition, so none exists until the spec has been written into it.
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

The **Decompose** stage's closing step derives from one slice of `project-plan.md` and never
re-decomposes the system — the rule is that step's, *Derive, don't design*. So a design change
that adds or reshapes a slice is merged before the spec for that slice is drafted, and a
structural decision the design surfaced has its ADR first (the **ADR** stage's gate).

### Skills

`domain-driven-design` — the strategic-design vocabulary the decomposition is argued in.

## 8. Implementation

One task of the epic body per issue, TDD one behaviour at a time, against the files the
`development` row names. The row's work file carries the loop itself, the pre-commit
self-check and the stack references it sends the author to; its bar, and the **Definition of
Done** the contribution workflow names, carry what a finished task must show, the Runtime
check included. Stack skills are the work file's to name, never
this document's.

### Artifact: the task's code and its tests, one PR per task

Each PR closes its task issue and carries `Part of` for the epic.

### Gate: the Definition of Done, Runtime check included

The floor is `CLAUDE.md`'s **Definition of Done** topic, plus the `development` bar the row
names. A task whose diff changes observable runtime behaviour carries the Runtime check
section; that topic says which diffs do.

### Skills

`test-driven-development`, `verification-before-completion`, `receiving-code-review`.

## 9. Tests

Test-authoring work with a task of its own in the epic body — a suite the spec calls for that
no implementation task carries, a harness, a regression test for a verified defect — under the
`testing` work type. It runs interleaved with **Implementation**, task by task in that body's
build order, not after it: a strand whose spec folds every test into its implementation tasks
has no issues at this stage, and a project that does not enable `testing` skips it, the
**Implementation** stage's bar then carrying the tests.

### Artifact: the task's tests, one PR per task

In the harness the task entry names for them.

### Gate: the Definition of Done, in the harness matched to what is tested

The same floor as the **Implementation** stage — `CLAUDE.md`'s **Definition of Done** topic —
plus the `testing` bar the row names; which harness a test belongs in is the tier taxonomy the
topic cites.

### Skills

`test-driven-development`, `verification-before-completion`, `receiving-code-review`.

## 10. Verify live

A slice is not finished when it merges; it is finished when it has been observed working on
the real installation — otherwise every later slice is built on a foundation nobody has seen
run. The slice is the vertical one the **Decompose** stage above cuts a child issue to, and
the list this pass is driven against is that task's.

What that pass must produce, when it blocks the next slice, and how it differs from the
pre-merge runtime-verified self-check is the **Verify live** bar in
[definition-of-done.md](definition-of-done.md).

### Artifact: the observation, as a comment on the epic

Or on the task issue where the work has no epic — the bar says which.

### Gate: the first slice of a strand is verified live before slice two starts

The bar's own rule; here it is what stops the **Implementation** stage of the next slice. It
binds the **first** slice of a strand and no other, which is what keeps it compatible with
[contribution-workflow.md](contribution-workflow.md)'s **Parallel work and forward
dependencies**: the strand pauses once, to see its foundation run, and from the second slice on
the tasks proceed in parallel against pinned contracts as that rule allows.

### Skills

None of the method's: the list comes from the spec, and the pass is run by the author of
the merged slice against the running installation.

## 11. Close

When every child is closed and its slice verified live, close the epic with a summary of what
shipped. The originating idea issue is already closed — that happened at **Decompose**, once the
strand was fully captured. The first condition is surfaced, not watched for, by the `cleanup`
run that follows the last child's merge; the second, verify live, and the close itself stay
the human partner's.

### Artifact: the closed epic, with its summary

What shipped, in the epic's closing comment; the idea issue was closed at **Decompose**.

### Gate: every child closed and every slice verified live

An epic closed over an unverified slice hides exactly the gap the **Verify live** stage
exists to surface.

### Skills

None of the method's; the commands are `CLAUDE.md`'s **Tracker mechanics** topic's.

## Document structure

The trees the artifact stages above write into, and which document owns what. This topic and
the **Analysis** stage's order above are the current statement of both —
`docs/analysis/flows/README.md` records the pivot that made them so.

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

Which row owns how each is written, what "finished" means for it, and why the phase exists at
all is the **Design** stage above.

### The architecture decision log

```text
docs/adl/
  template.md            — ADR template (Summary + Nygard + Considered options)
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
