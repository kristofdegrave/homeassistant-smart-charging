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

---

## Writing order

1. `system-overview.md`
2. `requirements.md` (fresh from idea — not from archive)
3. `flows/` one at a time, starting with `00-control-cycle.md`
4. Revisit `requirements.md` after flows reveal gaps

---

## Model selection

- **Analysis work** (`docs/analysis/`) → use **Opus**
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

1. **Draft** against the applicable template.
2. **6Cs self-check** — Clarity, Concision, Completeness, Consistency, Correctness, Concreteness. Confirm every domain term used already exists in the `system-overview.md` glossary; if not, **add it to the glossary first**.
3. **Fresh-agent review** — always spin up a dedicated, separate **Opus** agent for the review; **never review inline** in the main session. The review checks:
   - **Cross-document consistency** — consistent with all other analysis documents (system-overview, requirements, mechanism docs, other use-cases). Terms match the glossary; requirement IDs match what the document references.
   - **Requirement coverage** — the document satisfies every requirement it claims, and every requirement is reachable from at least one document.
4. **Address** the review feedback in the draft.
5. **Commit** once approved, with `docs: review and refine <filename>`.
6. **Stop and report** — after each committed document, report status and wait before starting the next.

---

## Flow document standard

Each flow doc: Purpose → Trigger → **Domain events** → Mermaid diagram → Steps → Edge cases → Requirements satisfied.

Preferred Mermaid types: `flowchart TD`, `stateDiagram-v2`, `sequenceDiagram`.
