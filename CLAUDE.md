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

---

## Model selection

- **Analysis work** (`docs/analysis/`) → use **Opus**
- **Architecture decisions** (`docs/adl/`) → use **Opus**
- **Development work** (`custom_components/`, `tests/`) → use **Sonnet**

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

Every **new** analysis document — and every **change** to an existing one (`docs/analysis/**`) — must go through this cycle before it is committed:

0. **Open (or link) a GitHub issue** describing the intent and scope, before drafting — required for a new document or any change that affects a requirement's acceptance criteria, a use-case's behavior, or a state model. Skip this step only for typo-level or pure-wording edits that don't change behavior. Reference the issue in the eventual commit/PR (`Closes #N`).
1. **Draft** against the applicable template.
2. **6Cs self-check** — Clarity, Concision, Completeness, Consistency, Correctness, Concreteness. Confirm every domain term used already exists in the `system-overview.md` glossary; if not, **add it to the glossary first**.
3. **Fresh-agent review** — always spin up a dedicated, separate **Opus** agent for the review; **never review inline** in the main session. The review checks:
   - **Cross-document consistency** — consistent with all other analysis documents (system-overview, requirements, mechanism docs, other use-cases). Terms match the glossary; requirement IDs match what the document references.
   - **Requirement coverage** — the document satisfies every requirement it claims, and every requirement is reachable from at least one document.
4. **Address** the review feedback in the draft.
5. **Manual review** — present the addressed draft to the human partner and get their explicit approval **before** committing. The fresh-agent review does not replace this; **both are always required**.
6. **Commit** once approved, with `docs: review and refine <filename>`.
7. **Stop and report** — after each committed document, report status and wait before starting the next.

**Merge policy:** no pull request is ever auto-merged. Every PR — including CI-drafted ones — requires the human partner's **explicit manual approval** before merge (enforced by `CODEOWNERS` + branch protection). CI may draft and review a PR, but never merges or self-approves it, and neither does the assistant.

**Branch naming:** `<type>/<N>` — the type matches the artifact, and `N` is the artifact's own
sequential number, not the GitHub issue number: `adr/0003` for ADR-0003, `uc/04` for UC04. Determine
the number (next sequential integer for that artifact type) before creating the branch, so the
branch name is stable from the start. For artifact types with no sequential number of their own
(e.g. a `requirements.md`/`system-overview.md` change spanning several Rnn/Cnn entries), fall back
to `docs/<issue-number>`. Extend the numbered pattern to any future numbered artifact type (one
issue, one branch, one PR) rather than inventing a new scheme.

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

Use the `write-adr` skill for the full cycle. In short:

0. **Open (or link) a GitHub issue** describing the decision to be made, before drafting.
1. **Draft** against `docs/adl/template.md`, numbering sequentially and listing every
   option seriously considered, not just the chosen one.
2. **Review** — a fresh, separate agent (Opus) checks the ADR against existing ADRs
   (no silent contradictions; supersede, don't edit, a prior decision) and against the
   analysis/design docs it touches.
3. **Manual review** — human partner's explicit approval before commit.
4. **Commit** (`docs: add ADR-NNNN <slug>`), referencing the issue from step 0.
5. **Stop and report** — status before starting the next ADR.

---

## Flow document standard

Each flow doc: Purpose → Trigger → **Domain events** → Mermaid diagram → Steps → Edge cases → Requirements satisfied.

Preferred Mermaid types: `flowchart TD`, `stateDiagram-v2`, `sequenceDiagram`.

