# Smart Charging — Project Guide

## Methodology: Analysis-first, spec-driven development

**Do not write code until the relevant analysis document exists and is complete.**

The full methodology is documented in [docs/plans/2026-06-24-analysis-approach-design.md](docs/plans/2026-06-24-analysis-approach-design.md).

---

## Document structure

```text
docs/analysis/
  system-overview.md    — stakeholders, problem, goals, hardware
  requirements.md       — what the system must do (6Cs + SMART + MoSCoW)
  flows/
    00-control-cycle.md — start here: coordinator loop
    01-solar-flow.md
    02-solar-only-flow.md
    03-captar-flow.md
    04-power-flow.md
    05-soc-management.md
    06-deadline-override.md
    07-wfh-logic.md
    08-flow-selection.md
```

Previous iteration archived at `docs/archive/` — do not use as source of truth.

```text
docs/design/
  system-design.md    — volatility-based service decomposition (Löwy's Method): static + dynamic architecture
  project-plan.md      — implementation task breakdown derived mechanically from system-design.md
```

Use cases and flows validate this decomposition — they never drive it. See
`docs/plans/2026-07-07-lowy-system-design-method.md` for the rationale and the
`write-system-design` / `write-project-design` skills for the cycle.

```text
docs/adl/
  template.md            — ADR template (Nygard + Considered options)
  0001-...md, 0002-...md — one file per architectural decision, sequential, never renumbered
```

---

## Writing order

1. `system-overview.md`
2. `requirements.md` (fresh from idea — not from archive)
3. `flows/` one at a time, starting with `00-control-cycle.md`
4. Revisit `requirements.md` after flows reveal gaps
5. Once the relevant use-cases/flows are stable, `design/system-design.md` (volatility-based
   decomposition), then `design/project-plan.md` — before opening ADRs for the structural
   decisions the design surfaces

---

## Model selection

- **Analysis work** (`docs/analysis/`) → use **Opus**
- **System/project design** (`docs/design/`) → use **Opus**
- **Architecture decisions** (`docs/adl/`) → use **Opus**
- **Implementation specs / TDD plans** (`docs/plans/`) → use **Opus**
- **Development work** (`custom_components/`, `tests/`) → use **Sonnet**
- **Review agents** (`*-reviewer`, e.g. analysis-reviewer, adr-reviewer, system-design-reviewer, impl-spec-reviewer, test-reviewer, code-reviewer, workflow-reviewer) → use **Opus**, regardless of the artifact type being reviewed. Each agent's own `.claude/agents/*.md` frontmatter must say `model: opus`; CI's `_ai-review.yml` `model` input must default to `opus` — both must keep matching this rule, since CI self-applies the reviewer prompt and never reads that frontmatter.

---

## Contribution workflow

Every unit of work — a doc, an ADR, a design, or code — follows one universal lifecycle:
issue → isolated worktree → PR against `main` → review → fix/reply/resolve → loop (capped at
3 rounds) → `needs-approval` → manual merge → worktree cleanup. Full steps, git identity, and
issue/branch conventions:
[docs/reference/contribution-workflow.md](docs/reference/contribution-workflow.md). Two
related references sit just outside that lifecycle: what happens before an issue exists
([docs/reference/idea-to-issues.md](docs/reference/idea-to-issues.md), epic decomposition) and
the completion bar an author self-checks before opening the PR
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
2. **Domain events** — each flow doc lists the events it produces (past tense, PascalCase, e.g. `ChargingStarted`). Shown as named nodes in Mermaid diagrams. Map directly to HA automation triggers.

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

Context labels, project-board Size/Estimate fields, the anchored `Plan:` line task issues must
carry, and branch naming — see
[docs/reference/contribution-workflow.md](docs/reference/contribution-workflow.md). Epic-first
filing for multi-artifact strands — see
[docs/reference/idea-to-issues.md](docs/reference/idea-to-issues.md).

---

## Flow document standard

Each flow doc: Purpose → Trigger → **Domain events** → Mermaid diagram → Steps → Edge cases → Requirements satisfied.

Preferred Mermaid types: `flowchart TD`, `stateDiagram-v2`, `sequenceDiagram`.

---

## Authoring AI artifacts (skills, agents, CI worker prompts)

When writing or changing a skill (`.claude/skills/`), an agent definition
(`.claude/agents/`), or a CI worker prompt (`.github/workflows/_ai-*.yml`), follow
[docs/reference/ai-authoring-token-efficiency.md](docs/reference/ai-authoring-token-efficiency.md) —
the per-artifact checklists that keep these lean by construction (single source of truth per
fact, scoped reads, bound the loop not the turn). Quality and review-integrity rules above
always win over any token saving.
