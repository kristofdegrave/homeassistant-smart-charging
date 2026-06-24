# Analysis Approach Design — Smart Charging v3

*Date: 2026-06-24*

## Context

The smart charging project is being restarted using a spec-driven, analysis-first methodology. No implementation begins until the analysis layer is complete. Archived requirements from a previous iteration exist in `docs/archive/` but are not carried forward — all documents are written fresh.

---

## Methodology

**Analysis-first, spec-driven development.**

1. Write analysis documents before writing any code.
2. Requirements describe *what* the system must do — never *how*.
3. Flows elaborate *how* each requirement is satisfied, with Mermaid diagrams.
4. Code is written only after the relevant analysis document is complete and reviewed.

---

## DDD Alignment

This methodology intentionally adopts two lightweight DDD concepts — enough to gain the benefits without the full tactical overhead:

1. **Ubiquitous Language glossary** (in `system-overview.md`) — agreed terms shared between domain expert and developer. Prevents ambiguity in requirements and flow diagrams. Every term used across documents must appear here first.

2. **Domain events** (in each flow doc) — explicit named events that *happen* in the domain (e.g. `ChargingStarted`, `PeakLimitBreached`, `DeadlineUrgencyTriggered`). Named in past tense. They make flow diagrams precise and map directly to HA automation triggers later.

Full tactical DDD (Aggregates, Repositories, Value Objects) is out of scope — this is a single bounded context with no persistence layer.

---

## Document Structure

```text
docs/analysis/
  system-overview.md    — stakeholders, problem statement, goals, hardware constraints, glossary
  requirements.md       — fresh requirements (6Cs + SMART + MoSCoW), what not how
  flows/
    00-control-cycle.md — coordinator loop: the spine everything plugs into
    01-solar-flow.md
    02-solar-only-flow.md
    03-captar-flow.md
    04-power-flow.md
    05-soc-management.md
    06-deadline-override.md
    07-wfh-logic.md
    08-flow-selection.md
```

---

## Writing Order

| Step | Document | Purpose |
|------|----------|---------|
| 1 | `system-overview.md` | Set context: who, what, why, hardware |
| 2 | `requirements.md` | Capture what the system must do (fresh, from the idea) |
| 3 | `flows/00-control-cycle.md` | Coordinator loop — the spine |
| 4 | `flows/01–04-*` | One charging mode flow per file |
| 5 | `flows/05–08-*` | Cross-cutting concerns: SOC, deadlines, WFH, flow selection |
| 6 | `requirements.md` (revisit) | Refine where flows reveal gaps or contradictions |

---

## Requirements Writing Standard

Each requirement in `requirements.md` follows this pattern:

```markdown
### R<n> — <Title>

**Priority:** Must / Should / Could / Won't  
**What:** One clear sentence describing the outcome. No implementation language.

**Acceptance criteria:**
- SMART, testable statement
- SMART, testable statement
```

### Quality checklist (6Cs)

Before marking a requirement complete, verify:

- [ ] **Clarity** — unambiguous, only one interpretation
- [ ] **Concision** — no redundant words
- [ ] **Completeness** — all conditions and edge cases covered
- [ ] **Consistency** — no contradiction with other requirements
- [ ] **Correctness** — accurately reflects the actual need
- [ ] **Concreteness** — specific and measurable, not vague

### Additional rules

- **SMART acceptance criteria** — Specific, Measurable, Achievable, Relevant, Time-bound
- **MoSCoW prioritization** — every requirement has a priority label
- **What, not how** — requirements describe outcomes; flows describe mechanisms
- **Testable** — every acceptance criterion must be verifiable

---

## Flow Document Standard

Each file in `flows/` follows this pattern:

```markdown
# <Flow Name>

## Purpose
One paragraph: what this flow does and why it exists.

## Trigger / Entry condition
When does this flow activate?

## Domain events
Named events this flow produces (past tense, PascalCase):
- `EventName` — when it occurs and what it signals

## Flow diagram
[Mermaid diagram — include domain events as named nodes]

## Steps
Numbered prose walkthrough of the diagram.

## Edge cases
Bullet list of non-happy-path scenarios.

## Requirements satisfied
Links back to requirements.md entries this flow implements.
```

---

## Diagram Format

All diagrams use **Mermaid** embedded in markdown. Renders in VS Code, GitHub, and most markdown viewers.

Preferred diagram types:
- `flowchart TD` — for decision logic and control flow
- `stateDiagram-v2` — for mode/state transitions
- `sequenceDiagram` — for time-ordered interactions (e.g. notifications)

---

## Reference

- Requirements writing guidelines: [modernrequirements.com — Good Software Requirements](https://www.modernrequirements.com/blogs/good-software-requirements/)
- Archived previous iteration: `docs/archive/`
