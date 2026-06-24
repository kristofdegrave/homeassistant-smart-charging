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

## Flow document standard

Each flow doc: Purpose → Trigger → Mermaid diagram → Steps → Edge cases → Requirements satisfied.

Preferred Mermaid types: `flowchart TD`, `stateDiagram-v2`, `sequenceDiagram`.
