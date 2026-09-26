# Smart Charging — Project Guide

Smart Charging is a solar-first, capacity-tariff-aware EV charging integration for Home
Assistant, built analysis-first: behaviour is written down in `docs/analysis/**` before it is
designed or coded. Its process is layered — a **method** that travels between repositories
(`docs/reference/method/**`, the step skills, the `reviewer` agent, the work-type files), a
**profile** holding what is true of this project alone (`.claude/profile.yml` for values a
script reads, `docs/reference/profile.md` for facts with a why), and **stack packages** (the
Home Assistant and Python skills) declared in the profile. This file is the method's routing
table plus the few rules that must be known before any skill or document is chosen.

## Rules that hold before anything is chosen

- **Do not write code until the relevant analysis document exists and is complete.** Which
  documents, and in what order: the **Document structure** and **Writing order** topics.
- **Every unit of work has an issue before work starts** — no exception for small or
  typo-level changes. From that issue to the merge: the **Contribution workflow** topic.
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
each side runs on. Why the table is shaped this way, and the obligations on whoever edits it
(review model, path-map enumerations, a label rename), are
[model-selection.md](docs/reference/method/model-selection.md); the routing rule a run applies is
stated under the table.

| Context label | How the work is done | Work model | How it is reviewed | Review model |
|---|---|---|---|---|
| `adr` | work file `docs/reference/work-types/adr/implement.md`; completion bar `docs/reference/work-types/adr/done.md` | opus | completion bar `docs/reference/work-types/adr/done.md`; checklist `docs/reference/work-types/adr/review.md` | opus |
| `uc` | work file `docs/reference/work-types/uc/implement.md`; completion bar `docs/reference/work-types/uc/done.md` | opus | completion bar `docs/reference/work-types/uc/done.md`; checklist `docs/reference/work-types/uc/review.md` | opus |
| `requirement` | work file `docs/reference/work-types/requirement/implement.md`; completion bar `docs/reference/work-types/requirement/done.md` | opus | completion bar `docs/reference/work-types/requirement/done.md`; checklist `docs/reference/work-types/requirement/review.md` | opus |
| `documentation` | work file `docs/reference/work-types/documentation/implement.md`; completion bar `docs/reference/work-types/documentation/done.md` | opus | completion bar `docs/reference/work-types/documentation/done.md`; checklist `docs/reference/work-types/documentation/review.md` | opus |
| `development` | work file `docs/reference/work-types/development/implement.md`; completion bar `docs/reference/work-types/development/done.md`. The bar covers `custom_components/**` only — its preamble routes `tests/**` to the `testing` row's bar. | sonnet | For `custom_components/**`: completion bar `docs/reference/work-types/development/done.md`; checklist `docs/reference/work-types/development/review.md`. For `tests/**`: completion bar `docs/reference/work-types/testing/done.md`; checklist `docs/reference/work-types/testing/review.md`. | opus |
| `testing` | work file `docs/reference/work-types/testing/implement.md`; completion bar `docs/reference/work-types/testing/done.md` | sonnet | completion bar `docs/reference/work-types/testing/done.md`; checklist `docs/reference/work-types/testing/review.md` | opus |
| `workflow` | none — human-authored (see below) | — | checklist `docs/reference/work-types/workflow/review.md` | opus |
| *(no context label)* | none | — | by changed path — applied to every PR, labelled or not (see below) | opus |

**The no-label row routes by changed path**, for every PR and not only an unlabelled one:
`docs/adl/**` → `docs/reference/work-types/adr/review.md`;
`docs/analysis/**` → `docs/reference/work-types/uc/review.md`;
`docs/design/**` → `docs/reference/work-types/documentation/review.md`;
`custom_components/**` → `docs/reference/work-types/development/review.md`;
`tests/**` → `docs/reference/work-types/testing/review.md`;
`.github/workflows/**`, `.github/ISSUE_TEMPLATE/**`,
`.github/setup-labels.sh`, `.github/profile-env.sh`, `.github/check-*`, `.github/test-check-*`,
`.github/hooks/**`, `.claude/hooks/**`, `.claude/settings.json`, `.claude/skills/**`,
`.claude/agents/**`, `.claude/profile.yml`, `docs/reference/**` and `CLAUDE.md` →
`docs/reference/work-types/workflow/review.md`. Every entry names a checklist
file, which the generic `reviewer` agent applies. This list **is** CI's mapping — the review
worker resolves it from here rather than carrying its own copy. The same set is enumerated in
`ai-pipeline.yml`'s path filter, `_ai-review.yml`'s diff enumeration and `.claude/profile.yml`'s
`review.path_map` — which is the **source** of the other three: of the *set*, not of the
routing, which resolves from this list as the sentence above says. Adding a tree still means
adding it in all four, but no longer means remembering to: `.github/check-path-map.py` fails the
PR naming each enumeration still missing it. Why the three are verified rather than generated,
and how each omission would fail if one ever shipped, are in the document this section routes
to and the CI document it routes onward to. `docs/postmortems/**` keeps its
own rule from the **Post-mortems** topic: a plain fresh-agent pass weighted to quotation
accuracy, the `workflow` checklist only when the PR also edits `CLAUDE.md` or another file the
list routes to it.

**Label and path both route, and neither overrides the other.** So a
PR gets the union: every tree's checklist from the no-label row's path map, **plus** the label
row's where it names one those paths did not already select. A row that names a checklist
**for a tree** — as `development` does, its own `review.md` for `custom_components/**` and the
`testing` row's for `tests/**` — names nothing when that tree has no changed files: a code-only
`development` PR resolves the `development` checklist and no more, and a tests-only one
resolves the `testing` checklist and no code bar. Only a row whose checklist carries no tree
qualifier adds one this way. An issue carrying more than one context label — which the filing
conventions assume against — contributes each of those rows rather than forcing a choice between them. A reference that cannot be resolved — a deleted or
transferred issue, a number that never existed, a failed lookup — is treated exactly like no
reference at all, so the path half still stands alone rather than the run aborting.

**A review column may name more than one checklist.** Each is applied to the changed files
under its own tree: a PR can touch more than one tree, so apply each checklist to its
matching files. A `development` PR therefore gets both the `development`
checklist, over its code, and the `testing` one, over its tests.

**Where a review is scoped to a tree's files, the criteria come from that tree.** The
criteria belong to the artifact, not to the label that dispatched the reviewer — so a tree's
files get that tree's checklist and bar whichever row reached them, and a checklist shared by
two rows (`uc` and `requirement`) is one file with the other row pointing at it. This says
nothing about *which* reviewers run, and it does not narrow a label-selected reviewer's
whole-change scope: that reviewer has no tree of its own, which is exactly what makes it an
addition, and the union rule above governs it unchanged. `development`'s `tests/**` branch is
the same rule in its other shape: rather than a file of its own pointing elsewhere, the row
names the `testing` row's checklist and bar outright for that tree — so the row stays
self-contained, and `tests/**` has one source of truth however it was reached.

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

One entry per **topic**: what a pointer of the form `` `CLAUDE.md`'s **Topic** `` resolves to,
naming the document — or the `##` heading in it — that owns the topic. The pointer convention
and the shape a routed document is heading for are stated once, in the **Authoring AI
artifacts** document.

| Topic | Owner |
|---|---|
| **Idea-to-product flow** | [idea-to-product.md](docs/reference/method/idea-to-product.md) — the method's default flow from a captured idea to its closed epic: the stages, each with its artifact, its gate and its skills, and how a stage is skipped or deviated from; this project's deviations are `profile.md`'s **Flow**. |
| **Contribution workflow** | [contribution-workflow.md](docs/reference/method/contribution-workflow.md) — the chain (file the issue → implement → review → fix → clean up) and its rulebook, for an interactive session; it runs unattended from the step it is entered at until a clean pass or the review cap; only **Clean up** is never reached by the chain running onward — it starts from the human stating that the merge happened. [ci-pipeline.md](docs/reference/method/ci-pipeline.md) — how the same lifecycle would run as CI jobs, and the repository's own CI checks. The stages either side of it are the **Idea-to-product flow** topic; the floor before the PR is the **Definition of Done** topic. |
| **Issue conventions** | [contribution-workflow.md#issue-conventions](docs/reference/method/contribution-workflow.md#issue-conventions) — context and kind labels, board Size/Estimate, epics as native sub-issues, branch naming. |
| **Decomposition checklist** | [decomposition-checklist.md](docs/reference/method/decomposition-checklist.md) — the criteria a fresh agent applies to an epic body in the one pass the **Idea-to-product flow**'s closing step runs before any child is filed; that step owns when the pass runs and what the body must contain. |
| **Definition of Done** | [definition-of-done.md](docs/reference/method/definition-of-done.md) — the project-wide floor an author self-checks before opening the PR, and commit message conventions; it routes to a row's per-type completion bar. |
| **Tracker mechanics** | [tracker-mechanics.md](docs/reference/method/tracker-mechanics.md) — the concrete `gh` commands, with their rate-limit failure modes, REST fallbacks and Windows/Git Bash quirks. Read it before typing one, and again when a call is refused, silently no-ops, or must be trusted without a read-back. Mechanics only: when to file and what a label means are **Contribution workflow** and **Issue conventions**. |
| **Project profile** | [profile.md](docs/reference/profile.md) and `.claude/profile.yml` — repository, board and ids, labels, enabled work types, path map, review cap, word budgets, dependency pins, git identity, merge strategy, flow deviations. |
| **Research sources** | [profile.md#research-sources](docs/reference/profile.md#research-sources) — this project's primary sources, highest trust first; the `research` skill carries the procedure. |
| **Document structure** | [idea-to-product.md#document-structure](docs/reference/method/idea-to-product.md#document-structure) — what lives in `docs/analysis/`, `docs/design/`, `docs/adl/` and `docs/postmortems/`, and which document owns what. |
| **Writing order** | [idea-to-product.md#analysis-first-in-this-order](docs/reference/method/idea-to-product.md#analysis-first-in-this-order) — a rule of the flow's **Analysis** stage; the design documents follow at its **Design** stage. |
| **Requirements standard** | [idea-to-product.md#what-never-how--moscow-smart-and-the-6cs](docs/reference/method/idea-to-product.md#what-never-how--moscow-smart-and-the-6cs) — a rule of the **Analysis** stage: what not how, MoSCoW, SMART, the 6Cs. |
| **DDD alignment (lightweight)** | [idea-to-product.md#two-ddd-concepts-adopted-tactical-ddd-out-of-scope](docs/reference/method/idea-to-product.md#two-ddd-concepts-adopted-tactical-ddd-out-of-scope) — a rule of the **Analysis** stage: glossary-first, domain events. |
| **Review protocol for analysis documents** | [idea-to-product.md#the-draft-and-the-review-come-from-the-uc-and-requirement-rows](docs/reference/method/idea-to-product.md#the-draft-and-the-review-come-from-the-uc-and-requirement-rows) — that rule of the **Analysis** stage and the two that follow it: no tracking refs in a document body, ADRs included; the implementation-spec gate on `needs-approval`. |
| **Flow document standard** | [idea-to-product.md#section-order-and-mermaid-types](docs/reference/method/idea-to-product.md#section-order-and-mermaid-types) — a rule of the **Analysis** stage. |
| **Architecture Decision Records (ADRs)** | [work-types/adr/done.md#architecture-decision-records-adrs](docs/reference/work-types/adr/done.md#architecture-decision-records-adrs) — every architectural decision is captured as an ADR before the work that depends on it is committed; the worthiness test and its two carve-outs. |
| **Post-mortems** | [contribution-workflow.md#post-mortems](docs/reference/method/contribution-workflow.md#post-mortems) — a dated snapshot of reasoning, never a source of truth; how it is reviewed. |
| **Authoring AI artifacts** | [ai-authoring.md](docs/reference/method/ai-authoring.md) — how a skill or agent definition is written; quality and review-integrity rules always win over any token saving. |
