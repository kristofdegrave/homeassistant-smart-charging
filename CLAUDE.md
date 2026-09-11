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

Use-cases and mechanism documents validate this decomposition — they never drive it. See
`docs/plans/2026-07-07-lowy-system-design-method.md` for the rationale and the
`write-system-design` / `write-project-design` skills for the cycle.

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
- **It is not an analysis document.** The 6Cs/glossary-first protocol and `analysis-reviewer`
  do not govern it; it quotes the analysis docs as evidence rather than asserting behaviour.

**How it is reviewed.** By a fresh-agent review run interactively, weighted toward **quotation
accuracy** — a post-mortem is an argument built entirely from quotes, so a quote that is
inaccurate, truncated in a way that changes its meaning, or mined out of a context that would
undercut the point is the defect class that matters. Pick the reviewer from what the PR
actually touches (`workflow-reviewer` when it also edits `CLAUDE.md` or the pipeline).
`docs/postmortems/**` is deliberately **not** in `ai-pipeline.yml`'s path filter or
`_ai-review.yml`'s diff enumeration: the CI reviewer's six checklists are all written against
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
| `adr` | `.claude/skills/write-adr/SKILL.md` | opus | `.claude/agents/adr-reviewer.md` | opus |
| `uc` | `.claude/skills/write-use-case/SKILL.md` | opus | `.claude/agents/analysis-reviewer.md` | opus |
| `requirement` | `.claude/skills/write-requirement/SKILL.md` | opus | `.claude/agents/analysis-reviewer.md` | opus |
| `specs` | `.claude/skills/write-impl-spec/SKILL.md` | opus | `.claude/agents/impl-spec-reviewer.md` | opus |
| `documentation` | `docs/design/system-design.md` → `.claude/skills/write-system-design/SKILL.md`; `docs/design/project-plan.md` → `.claude/skills/write-project-design/SKILL.md` | opus | `.claude/agents/system-design-reviewer.md` | opus |
| `development` | `.claude/skills/develop-task/SKILL.md` | sonnet | `.claude/agents/code-reviewer.md` for `custom_components/**`; `.claude/agents/test-reviewer.md` for `tests/**` | opus |
| `testing` | `.claude/skills/write-tests/SKILL.md` | sonnet | `.claude/agents/test-reviewer.md` | opus |
| `workflow` | none — human-authored (see below) | — | `.claude/agents/workflow-reviewer.md` | opus |
| *(no context label)* | none | — | by changed path (see below) | opus |

**Reviewers always run on Opus**, regardless of the artifact type being reviewed — which is
why the review-model column reads opus in every row today. The column exists anyway: it makes
a row self-contained, and a row that ever deviates has to argue for it here. Three places must
keep matching: this column, every `*-reviewer` frontmatter's `model: opus`, and CI's
`_ai-review.yml` `model` input default — because CI self-applies the reviewer prompt and never
reads that frontmatter.

**A row is self-contained.** Nothing outside the row and the PR's changed paths is needed to
know what to delegate to. The `documentation` row in particular splits on which
`docs/design/` file the change touches, not on the issue body.

**A review column may name more than one agent.** Each is applied to the changed files under
its own tree — the rule CI already uses: a PR can touch more than one tree, so apply each
checklist to its matching files. A `development` PR therefore gets both `code-reviewer` and
`test-reviewer`.

**The `development` and `testing` rows share three language references** —
`.claude/skills/ha-integration-knowledge/` (the Home Assistant platform reference),
`.claude/skills/python-anti-patterns/` and `.claude/skills/async-python-patterns/`. They are
not a fourth column: each row's own work skill and reviewer agent say which one to read and
when, so nothing here repeats a rule those files own.

**The `workflow` row has no work file on purpose.** There is no safe path containment for
untrusted issue content outside `docs/**`, `custom_components/**` and `tests/**`, so CI
refuses to draft `workflow` issues ([ci-pipeline.md](docs/reference/ci-pipeline.md)) and a
local session hands the drafting to the human partner. Its review is still automated. What a
`workflow` author reads instead is in **Authoring AI artifacts** below.

**The no-label row routes by changed path**: `docs/adl/**` → `adr-reviewer`;
`docs/analysis/**` → `analysis-reviewer`; `docs/plans/**` → `impl-spec-reviewer`;
`docs/design/**` → `system-design-reviewer`; `custom_components/**` → `code-reviewer`;
`tests/**` → `test-reviewer`; `.github/workflows/**`, `.github/ISSUE_TEMPLATE/**`,
`.github/setup-labels.sh`, `.claude/skills/**`, `.claude/agents/**`, `docs/reference/**` and
`CLAUDE.md` → `workflow-reviewer`. This is CI's own path→agent mapping plus one deliberate
addition, `docs/design/**`, which CI does not route today although the reviewer exists.
`docs/postmortems/**` keeps its own rule from **Document structure** above: a plain
fresh-agent pass weighted to quotation accuracy, `workflow-reviewer` only when the PR also
edits `CLAUDE.md` or the pipeline.

Adding or renaming a context label means updating this table too — see
[ci-pipeline.md](docs/reference/ci-pipeline.md)'s **Label vocabulary sync** for every other
place the same vocabulary is baked in.

---

## Contribution workflow

Every unit of work — a doc, an ADR, a design, or code — follows one universal lifecycle:
issue → isolated worktree → PR against `main` → review → fix/reply/resolve → loop (capped at
3 rounds interactively, 2 in CI) → `needs-approval` → manual merge → worktree cleanup. Two
actors run this lifecycle, each with its own reference doc — read whichever matches who's
acting:

- **Interactive Claude session** (this session, doing the work directly): full steps, git
  identity, and issue/branch conventions in
  [docs/reference/contribution-workflow.md](docs/reference/contribution-workflow.md).
- **The GitHub Actions AI pipeline** (`_ai-draft.yml`/`_ai-review.yml`/`_ai-fix.yml`, triggered
  by `needs-draft`/`needs-review`/`needs-work` labels): same lifecycle, `github-actions[bot]`
  as the actor, in [docs/reference/ci-pipeline.md](docs/reference/ci-pipeline.md). An
  interactive session never self-applies those trigger labels — see that doc.

Two related references sit just outside this lifecycle: the stages either side of it
([docs/reference/idea-to-issues.md](docs/reference/idea-to-issues.md) — idea, two-track
routing, spec, slicing into sub-issues, and verifying a shipped slice live) and the
completion bar an author self-checks before opening the PR
([docs/reference/definition-of-done.md](docs/reference/definition-of-done.md), also covering
commit message conventions). The artifact-specific sections below (analysis docs, ADRs) layer
their own template/quality-check steps on top of these; they never replace them.

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

- **Step 1 (draft)**: draft against the applicable template.
- **6Cs self-check**, done before step 3's fresh-agent review: Clarity, Concision,
  Completeness, Consistency, Correctness, Concreteness. Confirm every domain term used
  already exists in the `system-overview.md` glossary; if not, **add it to the glossary
  first**.
- **Step 3's reviewer** is `analysis-reviewer`, checking:
  - **Cross-document consistency** — consistent with all other analysis documents
    (system-overview, requirements, mechanism docs, other use-cases). Terms match the
    glossary; requirement IDs match what the document references.
  - **Requirement coverage** — the document satisfies every requirement it claims, and every
    requirement is reachable from at least one document.
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

- **Step 1 (draft)**: draft against `docs/adl/template.md`, numbering sequentially and
  listing every option seriously considered, not just the chosen one. Never renumber; a
  decision that changes is superseded by a new ADR, never edited in place.
- **Step 3's reviewer** is `adr-reviewer`, checking the ADR against existing ADRs (no silent
  contradictions — supersede, don't edit, a prior decision) and against the analysis/design
  docs it touches.
- No tracking refs (PR numbers, issue status) in the ADR body — see the analysis-doc section
  above; the rule applies equally here.

---

## Issue conventions

Context labels, project-board Size/Estimate fields, and branch naming — see
[docs/reference/contribution-workflow.md](docs/reference/contribution-workflow.md), which also
points to [docs/reference/ci-pipeline.md](docs/reference/ci-pipeline.md) for the anchored
`Plan:` line's exact required format. Epics and their children use GitHub's **native**
parent/sub-issue and blocked-by relationships, which `gh` supports directly — never re-derive
a body-text convention for them; the commands are in that same **Issue conventions** section.
Epic-first filing for multi-artifact strands — see
[docs/reference/idea-to-issues.md](docs/reference/idea-to-issues.md).

---

## Flow document standard

Applies to `control-cycle.md` (the one remaining flow document): Purpose → Trigger → **Domain events** → Mermaid diagram → Steps → Edge cases → Requirements satisfied.

Preferred Mermaid types: `flowchart TD`, `stateDiagram-v2`, `sequenceDiagram`.

---

## Authoring AI artifacts (skills, agents, CI worker prompts)

When writing or changing a skill (`.claude/skills/`), an agent definition
(`.claude/agents/`), or a CI worker prompt (`.github/workflows/_ai-*.yml`), follow
[docs/reference/ai-authoring-token-efficiency.md](docs/reference/ai-authoring-token-efficiency.md) —
the per-artifact checklists that keep these lean by construction (single source of truth per
fact, scoped reads, bound the loop not the turn). Quality and review-integrity rules above
always win over any token saving.
