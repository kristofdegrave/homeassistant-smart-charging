# Smart Charging — Project Guide

Smart Charging is a solar-first, capacity-tariff-aware EV charging integration for Home
Assistant, built analysis-first: behaviour is written down in `docs/analysis/**` before it is
designed or coded. Its process is layered — a **method** that travels between repositories
(`docs/reference/**`, the step skills, the `reviewer` agent, the work-type files), a
**profile** holding what is true of this project alone (`.claude/profile.yml` for values a
script reads, `docs/reference/profile.md` for facts with a why), and **stack packages** (the
Home Assistant and Python skills) declared in the profile. This file is the method's routing
table plus the few rules that must be known before any skill or document is chosen.

## Rules that hold before anything is chosen

- **Do not write code until the relevant analysis document exists and is complete.** Which
  documents, and in what order: the **Document structure** and **Writing order** topics.
- **Every unit of work has an issue before work starts** — no exception for small or
  typo-level changes. From that issue to the merge: the **Contribution workflow** topic.
- **Never self-apply `needs-draft`, `needs-review` or `needs-work`.** They are CI's triggers
  and the human partner's go-signal; an interactive session runs review and fix locally. The
  rule and its reasons are the exit-labels rule under **Contribution workflow**.
- **Destructive git is refused mechanically.** Committing and pushing on a task branch is
  standing-authorized; what that excludes is refused by a `PreToolUse` guard
  (`.claude/hooks/block-destructive-git.sh`, wired in `.claude/settings.json`). The
  commit-and-push rule under **Contribution workflow** defines both, and the script is the
  authority on what it refuses — read it when a git command comes back refused.

Only rules of this kind survive here: the two early process failures — a PR reaching the human
without `needs-approval`, and a PR opened only once all the work was done — were cured by a
skill owning the step, not by prose in this file.

## Model selection

One row per enabled context label: how the work is done, how it is reviewed, and the model
each side runs on. Why the table is shaped this way is
[model-selection.md](docs/reference/model-selection.md); the routing rule a run applies is
stated under the table.

| Context label | How the work is done | Work model | How it is reviewed | Review model |
|---|---|---|---|---|
| `adr` | work file `docs/reference/work-types/adr/implement.md`; completion bar `docs/reference/work-types/adr/done.md` | opus | completion bar `docs/reference/work-types/adr/done.md`; checklist `docs/reference/work-types/adr/review.md` | opus |
| `uc` | work file `docs/reference/work-types/uc/implement.md`; completion bar `docs/reference/work-types/uc/done.md` | opus | completion bar `docs/reference/work-types/uc/done.md`; checklist `docs/reference/work-types/uc/review.md` | opus |
| `requirement` | work file `docs/reference/work-types/requirement/implement.md`; completion bar `docs/reference/work-types/requirement/done.md` | opus | completion bar `docs/reference/work-types/requirement/done.md`; checklist `docs/reference/work-types/requirement/review.md` | opus |
| `specs` | work file `docs/reference/work-types/specs/implement.md`; completion bar `docs/reference/work-types/specs/done.md` | opus | completion bar `docs/reference/work-types/specs/done.md`; checklist `docs/reference/work-types/specs/review.md` | opus |
| `documentation` | work file `docs/reference/work-types/documentation/implement.md`; completion bar `docs/reference/work-types/documentation/done.md` | opus | completion bar `docs/reference/work-types/documentation/done.md`; checklist `docs/reference/work-types/documentation/review.md` | opus |
| `development` | work file `docs/reference/work-types/development/implement.md`; completion bar `docs/reference/work-types/development/done.md`. The bar covers `custom_components/**` only — its preamble routes `tests/**` to the `testing` row's bar. | sonnet | For `custom_components/**`: completion bar `docs/reference/work-types/development/done.md`; checklist `docs/reference/work-types/development/review.md`. For `tests/**`: completion bar `docs/reference/work-types/testing/done.md`; checklist `docs/reference/work-types/testing/review.md`. | opus |
| `testing` | work file `docs/reference/work-types/testing/implement.md`; completion bar `docs/reference/work-types/testing/done.md` | sonnet | completion bar `docs/reference/work-types/testing/done.md`; checklist `docs/reference/work-types/testing/review.md` | opus |
| `workflow` | none — human-authored (see below) | — | checklist `docs/reference/work-types/workflow/review.md` | opus |
| *(no context label)* | none | — | by changed path — applied to every PR, labelled or not (see below) | opus |

**The no-label row routes by changed path**, for every PR and not only an unlabelled one:
`docs/adl/**` → `docs/reference/work-types/adr/review.md`;
`docs/analysis/**` → `docs/reference/work-types/uc/review.md`;
`docs/plans/**` → `docs/reference/work-types/specs/review.md`;
`docs/design/**` → `docs/reference/work-types/documentation/review.md`;
`custom_components/**` → `docs/reference/work-types/development/review.md`;
`tests/**` → `docs/reference/work-types/testing/review.md`;
`.github/workflows/**`, `.github/ISSUE_TEMPLATE/**`,
`.github/setup-labels.sh`, `.github/profile-env.sh`, `.claude/skills/**`, `.claude/agents/**`,
`.claude/profile.yml`, `docs/reference/**` and `CLAUDE.md` → `docs/reference/work-types/workflow/review.md`. Every entry names a checklist
file, which the generic `reviewer` agent applies. This list **is** CI's mapping — the review
worker resolves it from here rather than carrying its own copy. `docs/postmortems/**` keeps its
own rule from the **Post-mortems** topic: a plain fresh-agent pass weighted to quotation
accuracy, the `workflow` checklist only when the PR also edits `CLAUDE.md` or the pipeline.

**Label and path both route, and neither overrides the other.** So a
PR gets the union: every tree's checklist from the no-label row's path map, **plus** the label
row's where it names one those paths did not already select. A row that names a checklist
**for a tree** — as `development` does, its own `review.md` for `custom_components/**` and the
`testing` row's for `tests/**` — names nothing when that tree has no changed files: a code-only
`development` PR resolves the `development` checklist and no more, and a tests-only one
resolves the `testing` checklist and no code bar. Only a row whose checklist carries no tree
qualifier adds one this way. An issue carrying more than one context label — which the filing
conventions assume against and CI's drafter refuses — contributes each of those rows rather
than forcing a choice between them. A reference that cannot be resolved — a deleted or
transferred issue, a number that never existed, a failed lookup — is treated exactly like no
reference at all, so the path half still stands alone rather than the run aborting.

**A review column may name more than one checklist.** Each is applied to the changed files
under its own tree — the rule CI already uses: a PR can touch more than one tree, so apply each
checklist to its matching files.

The two halves are scoped differently, and have to be. A path-selected reviewer sees the
changed files under its own tree. A label-selected one has no tree of its own — that is what
made it an addition rather than a duplicate — so it sees the change as a whole, and reviews it
as the kind of work the label says it is.

Where a tree states its own reviewer rule, that rule governs **that tree's files** and nothing
else: `docs/postmortems/**` is the standing case, and the **Post-mortems** topic states it. A
whole-change reviewer the label added still runs — it simply sees the change minus that tree's
files. And the rule never suppresses a reviewer the path map selected for some *other* changed
tree: a PR touching both a post-mortem and a skill still gets the skill reviewed.

## Routing table

One entry per **topic**. A skill or agent writes `` `CLAUDE.md`'s **Topic** ``; the pointer
resolves to the entry here, the entry names the `##` heading that owns the topic, and every
`###` beneath that heading is one rule, addressed through the topic rather than by name. The
convention is stated once, in the **Authoring AI artifacts** document.

| Topic | Owner |
|---|---|
| **Contribution workflow** | [contribution-workflow.md](docs/reference/contribution-workflow.md) — the six-step chain (issue → worktree → PR against `main` → review → fix → clean up) and its rulebook, for an interactive session; the chain runs unattended from the step it is entered at until a clean pass or the review cap, and only **Clean up** is the human's to invoke. [ci-pipeline.md](docs/reference/ci-pipeline.md) — the same lifecycle run by CI, `github-actions[bot]` as the actor. Either side of the lifecycle — idea, routing, spec, slicing into issues, verifying a shipped slice live — is [idea-to-issues.md](docs/reference/idea-to-issues.md); the floor an author self-checks before the PR is the **Definition of Done** topic. |
| **Issue conventions** | [contribution-workflow.md#issue-conventions](docs/reference/contribution-workflow.md#issue-conventions) — context and kind labels, board Size/Estimate, the anchored `Plan:` line, epics as native sub-issues, branch naming. |
| **Definition of Done** | [definition-of-done.md](docs/reference/definition-of-done.md) — the project-wide floor an author self-checks before opening the PR, and commit message conventions; it routes to a row's per-type completion bar. |
| **Tracker mechanics** | [tracker-mechanics.md](docs/reference/tracker-mechanics.md) — the concrete `gh` commands, with their rate-limit failure modes, REST fallbacks and Windows/Git Bash quirks. Read it before typing one, and again when a call is refused, silently no-ops, or must be trusted without a read-back. Mechanics only: when to file and what a label means are **Contribution workflow** and **Issue conventions**. |
| **Project profile** | [profile.md](docs/reference/profile.md) and `.claude/profile.yml` — repository, board and ids, labels, enabled work types, path map, review cap, dependency pins, git identity, merge strategy, flow deviations. |
| **Research sources** | [profile.md#research-sources](docs/reference/profile.md#research-sources) — this project's primary sources, highest trust first; the `research` skill carries the procedure. |
| **Document structure** | [idea-to-issues.md#document-structure](docs/reference/idea-to-issues.md#document-structure) — what lives in `docs/analysis/`, `docs/design/`, `docs/adl/` and `docs/postmortems/`, and which document owns what. |
| **Writing order** | [idea-to-issues.md#writing-order](docs/reference/idea-to-issues.md#writing-order) |
| **Requirements standard** | [idea-to-issues.md#requirements-standard](docs/reference/idea-to-issues.md#requirements-standard) — what not how, MoSCoW, SMART, the 6Cs. |
| **DDD alignment (lightweight)** | [idea-to-issues.md#ddd-alignment-lightweight](docs/reference/idea-to-issues.md#ddd-alignment-lightweight) — glossary-first, domain events. |
| **Review protocol for analysis documents** | [idea-to-issues.md#review-protocol-for-analysis-documents](docs/reference/idea-to-issues.md#review-protocol-for-analysis-documents) — the `uc`/`requirement` additions to the lifecycle; no tracking refs in a document body, ADRs included. |
| **Flow document standard** | [idea-to-issues.md#flow-document-standard](docs/reference/idea-to-issues.md#flow-document-standard) |
| **Architecture Decision Records (ADRs)** | [work-types/adr/done.md#architecture-decision-records-adrs](docs/reference/work-types/adr/done.md#architecture-decision-records-adrs) — every architectural decision is captured as an ADR before the work that depends on it is committed; the worthiness test and its two carve-outs. |
| **Post-mortems** | [contribution-workflow.md#post-mortems](docs/reference/contribution-workflow.md#post-mortems) — a dated snapshot of reasoning, never a source of truth; how it is reviewed. |
| **Authoring AI artifacts** | [ai-authoring.md](docs/reference/ai-authoring.md) — how a skill, agent definition or CI worker prompt is written; quality and review-integrity rules always win over any token saving. |
