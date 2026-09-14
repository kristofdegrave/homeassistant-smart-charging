# Smart Charging — Project Guide

## Methodology: Analysis-first, spec-driven development

**Do not write code until the relevant analysis document exists and is complete.**

The full methodology is documented in [docs/plans/2026-06-24-analysis-approach-design.md](docs/plans/2026-06-24-analysis-approach-design.md) — that plan doc's own Document Structure/Writing Order sections predate the pivot recorded in `docs/analysis/flows/README.md`; this file's own Document structure/Writing order sections below are the current ones.

---

## Document structure

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

```text
docs/design/
  system-design.md    — volatility-based service decomposition (Löwy's Method): static + dynamic architecture
  project-plan.md      — implementation task breakdown derived mechanically from system-design.md
```

See `docs/plans/2026-07-07-lowy-system-design-method.md` for the rationale, and the
`documentation` row of the **Model selection** table below for the cycle — its work file and
completion bar, which route onward, own how each of these two documents is written and what
"finished" means for it, including the Method's own discipline about what may drive a
decomposition.

```text
docs/adl/
  template.md            — ADR template (Nygard + Considered options)
  0001-...md, 0002-...md — one file per architectural decision, sequential, never renumbered
```

```text
docs/postmortems/
  YYYY-MM-DD-<slug>.md — one dated analysis per shipped failure
```

A post-mortem is a **snapshot of reasoning at a date**, not a source of truth for behaviour. It
is never kept current, never cited as the reason a rule exists (the rule's own reference doc
says that), and never consulted to answer "what does the system do" — the analysis docs own
that. Its job is to explain how a specific failure got past a specific process, so the changes
it recommends can be argued from evidence. Once those changes land, it stays as the record of
why and is not revised.

Two rules that apply elsewhere deliberately do **not** apply here:

- **Tracking refs are required, not forbidden.** The *Review protocol for analysis documents*
  section below forbids PR numbers and issue statuses in analysis-doc and ADR bodies, because
  they rot. That rule does not reach this directory: a post-mortem's entire evidentiary value
  is the specific PRs, issues, commits and review comments it cites, at the dates it cites
  them — don't "fix" these.
- **It is not an analysis document.** The 6Cs/glossary-first protocol and the analysis
  tree's own review checklist do not govern it; it quotes the analysis docs as evidence
  rather than asserting behaviour.

**How it is reviewed.** By a fresh-agent review run interactively, weighted toward **quotation
accuracy** — a post-mortem is an argument built entirely from quotes, so a quote that is
inaccurate, truncated in a way that changes its meaning, or mined out of a context that would
undercut the point is the defect class that matters. Pick the reviewer from what the PR
actually touches (the `workflow` checklist when it also edits `CLAUDE.md` or the pipeline).
`docs/postmortems/**` is deliberately **not** in `ai-pipeline.yml`'s path filter or
`_ai-review.yml`'s diff enumeration: the reviewer checklists are all written against
artifacts that assert behaviour, and none fits a narrative document. A post-mortem-only PR
therefore gets no CI AI review at all — by design, and stated here so it doesn't read as an
oversight (see [ci-pipeline.md](docs/reference/ci-pipeline.md)).

---

## Writing order

1. `system-overview.md`
2. `requirements.md` (fresh from idea — not from archive)
3. `control-cycle.md`, then `resolution-rules.md`, then `entity-catalog.md`, then `use-cases/`
   one at a time
4. Revisit `requirements.md` after use-cases reveal gaps
5. Once the relevant use-cases are stable, `design/system-design.md` (volatility-based
   decomposition), then `design/project-plan.md` — before opening ADRs for the structural
   decisions the design surfaces

---

## Model selection

One row per context label: how the work is done, how it is reviewed, and the model each side
runs on.

| Context label | How the work is done | Work model | How it is reviewed | Review model |
|---|---|---|---|---|
| `adr` | work file `docs/reference/work-types/adr/implement.md`; completion bar `docs/reference/work-types/adr/done.md`; entry point `.claude/skills/write-adr/SKILL.md` | opus | completion bar `docs/reference/work-types/adr/done.md`; checklist `docs/reference/work-types/adr/review.md` | opus |
| `uc` | work file `docs/reference/work-types/uc/implement.md`; completion bar `docs/reference/work-types/uc/done.md`; entry point `.claude/skills/write-use-case/SKILL.md` | opus | completion bar `docs/reference/work-types/uc/done.md`; checklist `docs/reference/work-types/uc/review.md` | opus |
| `requirement` | work file `docs/reference/work-types/requirement/implement.md`; completion bar `docs/reference/work-types/requirement/done.md`; entry point `.claude/skills/write-requirement/SKILL.md` | opus | completion bar `docs/reference/work-types/requirement/done.md`; checklist `docs/reference/work-types/requirement/review.md` | opus |
| `specs` | work file `docs/reference/work-types/specs/implement.md`; completion bar `docs/reference/work-types/specs/done.md`; entry point `.claude/skills/write-impl-spec/SKILL.md` | opus | completion bar `docs/reference/work-types/specs/done.md`; checklist `docs/reference/work-types/specs/review.md` | opus |
| `documentation` | work file `docs/reference/work-types/documentation/implement.md`; completion bar `docs/reference/work-types/documentation/done.md`; entry points `.claude/skills/write-system-design/SKILL.md` and `.claude/skills/write-project-design/SKILL.md` | opus | completion bar `docs/reference/work-types/documentation/done.md`; checklist `docs/reference/work-types/documentation/review.md` | opus |
| `development` | work file `docs/reference/work-types/development/implement.md`; completion bar `docs/reference/work-types/development/done.md`; entry point `.claude/skills/develop-task/SKILL.md`. The bar covers `custom_components/**` only — its preamble routes `tests/**` to the `testing` row's bar. | sonnet | For `custom_components/**`: completion bar `docs/reference/work-types/development/done.md`; checklist `docs/reference/work-types/development/review.md`. For `tests/**`: completion bar `docs/reference/work-types/testing/done.md`; checklist `docs/reference/work-types/testing/review.md`. | opus |
| `testing` | work file `docs/reference/work-types/testing/implement.md`; completion bar `docs/reference/work-types/testing/done.md`; entry point `.claude/skills/write-tests/SKILL.md` | sonnet | completion bar `docs/reference/work-types/testing/done.md`; checklist `docs/reference/work-types/testing/review.md` | opus |
| `workflow` | none — human-authored (see below) | — | checklist `docs/reference/work-types/workflow/review.md` | opus |
| *(no context label)* | none | — | by changed path — applied to every PR, labelled or not (see below) | opus |

**Reviewers always run on Opus**, regardless of the artifact type being reviewed — which is
why the review-model column reads opus in every row today. The column exists anyway: it makes
a row self-contained, and a row that ever deviates has to argue for it here. Three places must
keep matching: this column, every reviewer agent definition's frontmatter `model: opus`, and
CI's `_ai-review.yml` `model` input default — because CI self-applies the reviewer prompt and
never reads that frontmatter.

**A cell that names more than one file labels each role**, in either column. Four roles exist:
the **work file** holds how the artifact is written; the **completion bar** holds what must be
true of the finished artifact; the **entry point** is the skill a run or CI reaches the work
file by name through; the **checklist** holds what only a reviewer can check — how to read the
change, and the checks about the change rather than the artifact.

**A role may be named more than once in one cell** where the work type genuinely has more than
one of that thing — and only the **entry point** does today. `documentation` is reached by two
skills, one per document, and both lead to the same work file, so the cell names both and no
rule for choosing between them is needed: whichever fires has already selected itself by its own
`description`.

**No row branches in the *How the work is done* column.** A work type whose work splits between
two artifacts names one work file and one completion bar like every other row, and those files
route onward inside `docs/reference/work-types/` — `documentation` is the case. What a row may
still split by is a **tree**, in the review column, where the split is what the union routing
below is for and so cannot move into a file — `development` is the case, and each tree is its
own sentence, so `;` never has to mean two things in one cell. A sentence may also state a
named file's scope, as `development`'s work column does for its bar. (`work-types/README.md`
describes that tree's shape. Nothing in this table resolves through it: a row names its files
literally, and this pointer is for a reader wanting the shape, never a step in reaching a file.)

**The checklist is a file; who applies it varies — `.claude/agents/reviewer.md` locally, CI's
own review worker there.** That agent holds
nothing type-specific — only the untrusted-data rule, how to resolve a checklist and a bar from
this table, what to do when one cannot be read, and the output and anchoring contract every
review shares. So a row names a `docs/reference/work-types/<label>/review.md` and the generic
agent is spawned against it. The column names the file, and whoever dispatches follows what
it says rather than a reviewer they know of from elsewhere. Locally that agent is spawned
against the file; CI has no agent to spawn and its own worker self-applies the same file, so
"who applies it" varies while the file does not.

**Where a review is scoped to a tree's files, the criteria come from that tree.** The
criteria belong to the artifact, not to the label that dispatched the reviewer — so a tree's
files get that tree's checklist and bar whichever row reached them, and a checklist shared by
two rows (`uc` and `requirement`) is one file with the other row pointing at it. This says
nothing about *which* reviewers run, and it does not narrow a label-selected reviewer's
whole-change scope: that reviewer has no tree of its own, which is exactly what makes it an
addition, and the union rule below governs it unchanged. `development`'s `tests/**` branch is
the same rule in its other shape: rather than a file of its own pointing elsewhere, the row
names the `testing` row's checklist and bar outright for that tree — so the row stays
self-contained, and `tests/**` has one source of truth however it was reached.

**The completion bar is one file named in both columns, and that is deliberate.** It is the
only per-type fact with two readers: the author self-checks against it before requesting
review, and the reviewer applies it as criteria. Naming it twice duplicates a *route*, not a
rule — the alternative is the author and the reviewer each holding their own wording of the
same bar, which is the drift this split exists to remove. A row whose type has no separate bar
simply names none, and its work file carries what "done" means.

**Two rows may share one bar.** `uc` and `requirement` do: they share a reviewer, and that
reviewer is dispatched over one tree that also holds documents belonging to neither label, so a
bar per label would leave those with none. Each row still names a path in its own label's
directory, so the row stays self-contained and label-keyed; the `requirement` one routes to the
shared file rather than restating it. A shared reviewer alone does not earn this: the argument
is that the reviewed tree is wider than either label, so splitting the bar would leave part of
it unjudged. The converse — one work type needing more than one bar, because its artifacts are
judged on disjoint criteria — is settled inside its own completion bar and never in the row:
`documentation`'s bar routes to one per document.

**A row is self-contained.** Nothing outside the row and the change's own files is needed to
know what to delegate to — a row names its files outright, and where a work type splits further
that is settled inside those files rather than by anything a run has to resolve here. Reviewer
dispatch additionally resolves the linked issue's label, per the union rule below — that is the
one input outside the row, and it only ever adds a reviewer.

**A review column may name more than one checklist.** Each is applied to the changed files
under its own tree — the rule CI already uses: a PR can touch more than one tree, so apply each
checklist to its matching files. A `development` PR therefore gets both the `development`
checklist, over its code, and the `testing` one, over its tests.

**Label and path both route, and neither overrides the other.** They answer different
questions: the label says what kind of work this is, the changed paths say what it actually
touched, and they come apart whenever a change is *about* one artifact type but *lives* in
another's tree — common for `workflow` work, which edits whichever file holds the rule. So a
PR gets the union: every tree's checklist from the no-label row's path map, **plus** the label
row's where it names one those paths did not already select. A row that names a checklist
**for a tree** — as `development` does, its own `review.md` for `custom_components/**` and the
`testing` row's for `tests/**` — names nothing when that tree has no changed files: a code-only
`development` PR resolves the `development` checklist and no more, and a tests-only one
resolves the `testing` checklist and no code bar. Only a row whose checklist carries no tree
qualifier adds one this way. An issue carrying more than one context label — which the filing
conventions assume against and CI's drafter refuses — contributes each of those rows rather
than forcing a choice between them.

The two halves are scoped differently, and have to be. A path-selected reviewer sees the
changed files under its own tree. A label-selected one has no tree of its own — that is what
made it an addition rather than a duplicate — so it sees the change as a whole, and reviews it
as the kind of work the label says it is.

Where a tree states its own reviewer rule, that rule governs **that tree's files** and nothing
else: `docs/postmortems/**` is the standing case, and **Document structure** above states it. A
whole-change reviewer the label added still runs — it simply sees the change minus that tree's
files. And the rule never suppresses a reviewer the path map selected for some *other* changed
tree: a PR touching both a post-mortem and a skill still gets the skill reviewed. Adding a file
must never subtract a reviewer, which a whole-change suppression would let it do.

Path routing is the half that must never be skipped — it is what guarantees no changed tree
goes unreviewed, and it is also the half that cannot be steered: the label is resolved from the
PR body, which on a fork PR is written by whoever opened it, so the worst a crafted body can do
is add a reviewer, never remove one. A reference that cannot be resolved — a deleted or
transferred issue, a number that never existed, a failed lookup — is treated exactly like no
reference at all, so the path half still stands alone rather than the run aborting. The label
row is the addition: it brings the checklist written for this kind of work even when the change
landed somewhere else. A `workflow` PR editing `docs/plans/**` therefore gets the `specs`
checklist for the file and the `workflow` checklist for the subject, and a `development` PR
that also edits a workflow file gets the `workflow` checklist on that file rather than nothing.

**The `development` and `testing` rows share three language references** —
`.claude/skills/ha-integration-knowledge/` (the Home Assistant platform reference),
`.claude/skills/python-anti-patterns/` and `.claude/skills/async-python-patterns/`. They are
not a fourth column: each row's own work file or skill, and its checklist and bar, say which
one to read and when, so nothing here repeats a rule those files own.

**The `workflow` row has no work file on purpose.** A drafted label is contained by the tree
its drafts write, and `workflow` changes land in the files that instruct future runs, so there
is no tree to contain one in — CI therefore refuses to draft `workflow` issues and a local
session hands the drafting to the human partner. The containment rule and the tree each label
gets are [ci-pipeline.md](docs/reference/ci-pipeline.md)'s; they narrow as work types migrate,
so they are routed from here rather than restated. Its review is still automated, and its
checklist is the one file in its `docs/reference/work-types/workflow/` directory: with no bar
beside it, that file carries the whole of the criteria rather than only what a bar cannot.
What a `workflow` author reads instead is in **Authoring AI artifacts** below.

**The no-label row routes by changed path**, for every PR and not only an unlabelled one:
`docs/adl/**` → `docs/reference/work-types/adr/review.md`;
`docs/analysis/**` → `docs/reference/work-types/uc/review.md`;
`docs/plans/**` → `docs/reference/work-types/specs/review.md`;
`docs/design/**` → `docs/reference/work-types/documentation/review.md`;
`custom_components/**` → `docs/reference/work-types/development/review.md`;
`tests/**` → `docs/reference/work-types/testing/review.md`;
`.github/workflows/**`, `.github/ISSUE_TEMPLATE/**`,
`.github/setup-labels.sh`, `.claude/skills/**`, `.claude/agents/**`, `docs/reference/**` and
`CLAUDE.md` → `docs/reference/work-types/workflow/review.md`. Every entry names a checklist
file, which the generic `reviewer` agent applies. `docs/analysis/**` names the `uc` checklist because that tree
is wider than either label sharing it — `requirement`'s file points at the same one. This list **is** CI's mapping — the review worker resolves it from
here rather than carrying its own copy. One entry, `docs/design/**`, is routed by this
rule but cannot be seen: it is in neither the pipeline's path filter nor the review worker's
diff enumeration, so the reviewer is reachable in principle and unreached in practice.
`docs/postmortems/**` keeps its own rule from **Document structure** above: a plain
fresh-agent pass weighted to quotation accuracy, the `workflow` checklist only when the PR
also edits `CLAUDE.md` or the pipeline.

Adding or renaming a context label means updating this table too — see
[ci-pipeline.md](docs/reference/ci-pipeline.md)'s **Label vocabulary sync** for every other
place the same vocabulary is baked in.

---

## Contribution workflow

Every unit of work — a doc, an ADR, a design, or code — follows one universal lifecycle:
issue → isolated worktree → PR against `main` → review → fix/reply/resolve → loop (round-capped;
each reference doc below states its own actor's cap) → `needs-approval` → manual merge →
worktree cleanup. Two actors run this lifecycle, each with its own reference doc — read
whichever matches who's acting:

- **Interactive Claude session** (this session, doing the work directly): full steps, git
  identity, and issue/branch conventions in
  [docs/reference/contribution-workflow.md](docs/reference/contribution-workflow.md).
- **The GitHub Actions AI pipeline** (`_ai-draft.yml`/`_ai-review.yml`/`_ai-fix.yml`, triggered
  by `needs-draft`/`needs-review`/`needs-work` labels): same lifecycle, `github-actions[bot]`
  as the actor, in [docs/reference/ci-pipeline.md](docs/reference/ci-pipeline.md). An
  interactive session never self-applies those trigger labels — see that doc.

An interactive session runs the step ranges through their own skills: steps 1–2 `implement`,
3–4 `review`, 5 `fix` (with `resolve-review-thread`), 7 `finalize-pr-review`; step 0 is
`file-task-issue`. Step 8's manual comments are handled like step 5; step 6's loop and step 9
stay with the human partner.

Two related references sit just outside this lifecycle: the stages either side of it
([docs/reference/idea-to-issues.md](docs/reference/idea-to-issues.md) — idea, two-track
routing, spec, slicing into sub-issues, and verifying a shipped slice live) and the
**Definition of Done** an author self-checks before opening the PR
([docs/reference/definition-of-done.md](docs/reference/definition-of-done.md), also covering
commit message conventions) — the project-wide floor, distinct from a row's per-type
*completion bar*, which that document routes to. The artifact-specific sections below (analysis docs, ADRs) layer
their own template/quality-check steps on top of these; they never replace them.

Committing and pushing on a task branch is standing-authorized; the destructive git commands
that authorization excludes are refused mechanically by a `PreToolUse` guard
(`.claude/hooks/block-destructive-git.sh`, wired in `.claude/settings.json`). The interactive
reference doc's **Commit & push authorization** section defines both, and the guard script
itself is the authority on exactly what it refuses and when — read it when a git command comes
back refused.

---

## Requirements standard

- Describe **what**, never **how**
- MoSCoW priority on every requirement
- SMART acceptance criteria
- 6Cs quality check: Clarity, Concision, Completeness, Consistency, Correctness, Concreteness
- Reference: [modernrequirements.com — Good Software Requirements](https://www.modernrequirements.com/blogs/good-software-requirements/)

---

## DDD alignment (lightweight)

Two DDD concepts are intentionally adopted:

1. **Ubiquitous Language glossary** — lives in `system-overview.md`. Every domain term used across documents must be defined here first.
2. **Domain events** — each use-case and mechanism document lists the events it produces (past tense, PascalCase, e.g. `ChargingStarted`). Shown as named nodes in Mermaid diagrams. Map directly to HA automation triggers.

Full tactical DDD (Aggregates, Repositories, Value Objects) is out of scope.

---

## Review protocol for analysis documents

New or changed documents under `docs/analysis/**` follow the
[Contribution workflow](docs/reference/contribution-workflow.md), with these artifact-specific
additions:

- **Step 1 (draft)** and **step 3's review**: the `uc` and `requirement` rows of the **Model
  selection** table above name the files, and they are their only home — don't restate them
  here. Each row's work file carries how that artifact is written (the template, the numbering,
  the propagation step); the completion bar carries what must be true of the finished
  document — the 6Cs pass, the glossary-first check, cross-document consistency, requirement
  coverage — and both the author's self-check and the reviewer's criteria are that one file. It
  is one bar serving both rows, for the reason stated under the table, and it is written to
  cover this whole tree: a change touching only a document neither row owns — a mechanism
  document, or the glossary — is judged by that same bar, which carries a section for that kind
  of document.
- **Never reference PR numbers or issue tracking statuses** (e.g. "PR #30, still open",
  "issue #29, resolved", "has landed") inside the document body. These are ephemeral
  repo-management facts that rot as PRs merge and issues close and don't belong in a document
  meant to record durable reasoning — describe the underlying fact directly instead (e.g.
  "has since been reworded", not "issue #29 has since reworded"). This applies to ADRs too.

---

## Architecture Decision Records (ADRs)

**Every architectural decision must be captured as an ADR before the work that depends on it is committed.** See `docs/adl/0001-use-architecture-decision-records.md` for the rationale and template choice.

An **architectural decision** is a choice about structure that would be expensive to
reverse or that materially constrains future options — e.g. how integration entities
map to hardware, where a boundary/abstraction layer sits, the shape of a config-entry
schema, which library or protocol to depend on, a change to the coordinator/control-loop
structure. It is **not** an ADR-worthy decision to pick a variable name, a log message,
or a one-off implementation detail with no lasting structural consequence — when in
doubt, ask whether a future contributor would benefit from knowing *why*, not just
*what*.

For a borderline case, a calibration test: would reversing or swapping this choice touch
more than one module, or a contract other code depends on? It supplements, not
overrides, the categories above — a *product-code* choice there (e.g. a library the
shipped integration depends on, a config-entry schema shape) stays architectural even
when well encapsulated; the two carve-outs below narrow that for their own categories.
Serious deliberation alone isn't proof either way — weigh it against the reach test and
the *why*-a-future-contributor-benefits question. Two recurring categories:

- **Test, CI, or dev-tooling choices** (a benchmarking library, a measurement helper, a
  lint tool) are not architectural unless the *product* code itself takes a structural
  dependency on them — a library used only inside `tests/` belongs in a PR description,
  not an ADR. What this carve-out excludes is **which tool or library a script happens to
  call**. It does not extend to the *structure* of the test and automation apparatus
  itself, which stays ADR-worthy even though no product code depends on it. Exactly two
  things sit on that side, and nothing else does:
  - the **CI/automation pipeline's own structure** — trust boundaries, job topology,
    review-loop caps;
  - the **test-tier taxonomy** — which tier a test belongs in, what a passing suite is
    allowed to mean, and where a contributor is expected to put a new test (see ADR-0009
    and ADR-0037).

  The line between the two halves is **who is bound by the choice**, not which directory
  the code implementing it sits in: a taxonomy binds every future test and every future
  reviewer, while a measurement library binds nothing beyond the files that import it.
  So a test-only fixture or simulator's *internals* fall on the library side of that line
  however elaborate they get, while the tier it belongs to falls on the taxonomy side.
- **Domain/business rules** (a formula, a precedence order, which values are surfaced) —
  even when seriously debated — are not architectural; they belong in
  `docs/analysis/requirements.md` or `docs/analysis/resolution-rules.md`, not an ADR.
  Surfacing, renaming, or mirroring an existing config value or computed reading as an
  entity is not, on its own, a structural boundary change and doesn't escape this
  carve-out.

This tightened bar applies to new decisions; it does not retroactively make an existing
Accepted ADR non-architectural — supersede it instead if a past decision no longer holds
(per `docs/adl/template.md`), never edit it in place to remove it. If an Accepted ADR's
Consequences state a forward-looking bar for future decisions in a category one of the
carve-outs above now excludes, this carve-out governs going forward and that ADR should
be superseded to say so, rather than the conflict being left implicit.

Use the `write-adr` skill for the full cycle. Follows the
[Contribution workflow](docs/reference/contribution-workflow.md), with these artifact-specific
additions:

- **Step 1 (draft)** and **step 3's review**: the `adr` row of the **Model selection** table
  above names the files, and they are their only home — don't restate them here. The work file
  carries how an ADR is written (the template, the numbering and never-renumber rules, the
  immutability rule); the completion bar carries what must be true of the finished record, and
  both the author's self-check and the reviewer's criteria are that one file. The worthiness
  test above is reached from the bar rather than repeated in it.
- No tracking refs (PR numbers, issue status) in the ADR body — see the analysis-doc section
  above; the rule applies equally here.

---

## Issue conventions

Context labels, project-board Size/Estimate fields, and branch naming — see
[docs/reference/contribution-workflow.md](docs/reference/contribution-workflow.md), which also
points to [docs/reference/ci-pipeline.md](docs/reference/ci-pipeline.md) for the anchored
`Plan:` line's exact required format, and to its **Label vocabulary sync** section for every
CI-side place the context-label vocabulary is baked into and must move with it. Epics and
their children use GitHub's **native** parent/sub-issue and blocked-by relationships, which `gh`
supports directly — never re-derive a body-text convention for them; the commands are in
**Tracker mechanics** below.
Epic-first filing for multi-artifact strands — see
[docs/reference/idea-to-issues.md](docs/reference/idea-to-issues.md).

---

## Tracker mechanics

The concrete `gh` commands for driving this project's tracker — filing, board fields, issue
relationships, comments, PRs, review threads, labels — are in
[docs/reference/tracker-mechanics.md](docs/reference/tracker-mechanics.md). Read it before
typing any of them, and again whenever a `gh` call comes back refused, appears to succeed
without taking effect, or has to be trusted without a read-back: it covers rate-limit failure
modes, REST fallbacks, and Windows/Git Bash argument quirks. It is mechanics only — *when* to
file and what a label means stay with **Contribution workflow** and **Issue conventions**.

---

## Flow document standard

Applies to `control-cycle.md` (the one remaining flow document): Purpose → Trigger → **Domain events** → Mermaid diagram → Steps → Edge cases → Requirements satisfied.

Preferred Mermaid types: `flowchart TD`, `stateDiagram-v2`, `sequenceDiagram`.

---

## Research sources

When an external fact blocks a decision — what Home Assistant does in some case, how a
dependency behaves, what a device's API returns — these are this project's primary sources,
highest trust first. The `research` skill carries the generic procedure and routes here for
the list.

1. **Home Assistant** — `developers.home-assistant.io` for the documented contract, and the
   `homeassistant` package source at the version pinned in `requirements-test.txt` for what
   the code actually does.
2. **Library source** — a dependency's published source at the version the file that pins it
   names (`requirements-test.txt` for test and dev dependencies; the integration manifest's
   `requirements` array for anything the shipped integration depends on), not its README. A
   changelog entry counts only as a pointer to the commit that made the change.
3. **Device / vendor API docs** — the manufacturer's own specification for a charger,
   inverter, meter or tariff provider this project integrates with (the hardware is listed in
   `docs/analysis/system-overview.md`); a captured response from the real device outranks the
   specification.

---

## Authoring AI artifacts (skills, agents, CI worker prompts)

When writing or changing a skill (`.claude/skills/`), an agent definition
(`.claude/agents/`), or a CI worker prompt (`.github/workflows/_ai-*.yml`), follow
[docs/reference/ai-authoring.md](docs/reference/ai-authoring.md) — the vocabulary for this
artifact class's failure modes, and the per-artifact checklists that keep these lean by
construction (single source of truth per fact, scoped reads, bound the loop not the turn).
Quality and review-integrity rules above always win over any token saving.
