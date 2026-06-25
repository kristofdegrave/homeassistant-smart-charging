# Use-Cases Design — Smart Charging v3

*Date: 2026-06-25*

## Context

`system-overview.md` and `requirements.md` are complete. The original methodology
([2026-06-24-analysis-approach-design.md](2026-06-24-analysis-approach-design.md))
planned a `flows/` layer to elaborate *how* each requirement is satisfied, but those
flows were never written (only `flows/README.md` exists, all entries "Planned").

This document decides how to add a **behaviour layer** between requirements and code,
applying use-case best practices from six reference articles
(ArgonDigital, UW CPED checklist, TechCanvass, the Medium "flow of use cases" article,
and Tony Heap's BDD reinterpretation).

---

## Key insight driving the design

Every reference frames use-cases as tools for **actor-driven, interactive** systems —
a human pursues a goal, the system responds. The UW CPED checklist explicitly positions
them as "people-centric, not automation-focused."

But Smart Charging is mostly an **autonomous control loop**: the primary trigger for
Solar / SolarOnly / CapTar / Power behaviour is a timer firing every control interval
and sensor-state changes — not a person. Forcing one human-actor use-case per requirement
would be an anti-pattern (ArgonDigital: don't split identical/non-interactive interactions).

**Resolution:** use-cases document only the **goal-oriented behaviours**; the system's
internal **mechanism** is documented with artifacts matched to its nature. Scenario bodies
use **Given/When/Then** (Heap's BDD mapping), which is event-anchored and fits a control
loop far better than human-narrated "user clicks…" flows — and doubles as a testable spec.

---

## Decision 1 — Use-cases replace the planned `flows/` layer

The seven mode/concern flows dissolve into use-cases. Only genuinely mechanism-level
pieces remain as separate docs. One behaviour layer, not three (requirements + use-cases +
flows would triple the consistency burden for a single-maintainer project, with no sunk
cost to preserve since flows were never written).

## Decision 2 — Final analysis-layer structure

```text
docs/analysis/
  system-overview.md      — stakeholders, problem, goals, hardware, glossary  (exists)
  requirements.md         — what the system must do (6Cs + SMART + MoSCoW)    (exists)
  use-cases/              — goal-oriented behaviours (NEW)
    README.md             — inventory index
    UC01..UC10-*.md
  control-cycle.md        — the control pipeline: read → smooth → dispatch → clamp → set (NEW)
  resolution-rules.md     — shared priority-ordered lookups, as decision tables (NEW)
  entity-catalog.md       — single source of truth for sc_ entity bindings (NEW)
```

Every requirement maps to exactly one home:

| Home | Requirements |
|------|--------------|
| Use-cases | R1, R2, R4, R5, R6, R8, R9, R12, R13, R17 |
| `control-cycle.md` | R3 (peak clamp), R10 (smoothing), NF4 (voltage conversion), R11 (rapid-cycling invariant) |
| `resolution-rules.md` | R7 (active SOC limit), R14 (departure time), R16 (Auto mode-selection), effective peak limit |
| Already in `system-overview.md` | NF1–NF3 architecture |
| Already in `requirements.md` | C1–C3 constraints, R15 (battery-capacity parameter) |

`R15` is a configuration parameter feeding UC05's deadline calculation, not a behaviour.
`R11` is a cross-cutting invariant referenced by every charging use-case.
`entity-catalog.md` is not a requirement home — it realizes the `sc_` entity-naming convention
from `system-overview.md` and binds the entities every other doc references (see Decision 5).

## Decision 3 — Use-case inventory

| UC | Goal | Primary actor | Reqs |
|----|------|---------------|------|
| UC01 | Charge from solar surplus (incl. grid fallback) | Household energy manager | R1 |
| UC02 | Charge from solar only | Household energy manager | R2 |
| UC03 | Charge cost-efficiently from the grid | Household energy manager | R4 |
| UC04 | Charge at maximum power | EV driver | R17 |
| UC05 | Guarantee the car is ready by departure | EV driver | R5 |
| UC06 | Store abundant solar by stepping up the limit | Household energy manager | R8 |
| UC07 | Reserve capacity for tomorrow's solar | Household energy manager | R9 |
| UC08 | Plan tomorrow's home day (evening prompt) | EV driver | R13 |
| UC09 | Keep the charge limit in sync with the car | EV driver | R6 |
| UC10 | Remind me to plug in | EV driver | R12 |

### Modeling judgment calls

- **UC05 is a cross-cutting override** (`«extend»`). It modifies UC01/UC02/UC03 rather than
  being a standalone charging session, but it is a clear EV-driver goal, so it is documented
  as its own use-case and marked as an extension. UC01/02/03 each carry an "Extended by UC05
  when the deadline is at risk" relationship rather than duplicating the deadline logic.
- **The Auto profile (R16) is a resolution rule, not a use-case.** It is a priority-ordered
  decision (conditions → mode) with no human actor pursuing a goal, so it lives as a decision
  table in `resolution-rules.md`. The `Manual` profile needs no documentation (the user/external
  source sets the mode directly).
- **`Off` mode** is the null behaviour — not a use-case.

## Decision 4 — Mode mechanism lives inside the mode use-case

The archived `process-flow.md` captured each mode as a state machine (Solar:
`IDLE → COOLDOWN → CHARGING → HOLD`, with restart hysteresis and hold/cooldown timers).
Dissolving the `flows/` layer must not lose this. The state machine and the mode's set-point
rule are **observable behaviour, not implementation**, so they belong to the mode use-case:
each of UC01–UC04 carries a `stateDiagram-v2` and a **State model** subsection (states,
transition conditions, set-point rule). The Given/When/Then scenarios describe the observable
transitions; the state diagram is authoritative for the state set.

**No shared set-point formula is extracted.** Solar/SolarOnly use *incremental* convergence
toward net import = 0 W on smoothed readings, while CapTar computes *absolute* headroom below the
effective peak limit on raw readings — genuinely different control laws, not one rule with
parameters. The only shared primitives are amps↔watts conversion (NF4) and the min/peak clamps
(C1, R3), which already live in `control-cycle.md` / `requirements.md`; modes reference them
rather than restating them.

## Decision 5 — `entity-catalog.md` is the single source of truth for `sc_` entities

The `sc_` wrapper entities are currently scattered as prose inside the `system-overview.md`
glossary. For a hardware-agnostic system whose entire design rests on those wrappers — and to make
the eventual spec/code step implementable — they are consolidated into one table:
`entity-catalog.md`, a mechanism doc alongside `control-cycle.md` and `resolution-rules.md`.

This introduces no new "how": the glossary already treats `sc_` entity names as ubiquitous
language. The glossary stays authoritative for each **term's meaning**; the catalog is
authoritative for each entity's **binding** (id, unit, default, and which behaviour reads or writes
it). The catalog's *Realizes* column links each row back to its glossary term; it never restates
the definition.

**Use-cases reference it by domain language, not by entity id.** GWT scenarios speak in glossary
terms ("the active SOC limit", "charger status"); the entity binding lives only in the catalog,
keyed by its *Read by* / *Written by* columns. This keeps GWT at the "what" level and keeps the
entity↔behaviour mapping in exactly one place; the dev/codegen step joins a use-case to its
entities through those columns.

**Populated incrementally.** Created with every entity row and its static columns, with *Read by* /
*Written by* seeded from the already-written `control-cycle.md` and `resolution-rules.md`. Each
subsequent use-case task updates those two columns for the entities it touches — so the mapping is
always current without a big-bang pass.

---

## Document templates

### Use-case template (`use-cases/UCnn-*.md`)

```markdown
# UCnn — <Goal as active verb phrase>

**Primary actor:** …
**Stakeholders & interests:** … (who cares about this goal and why)
**Scope / level:** sea-level (single user goal, one outcome)

## Preconditions
- Testable state statements (e.g. "Car is connected at home"), not actions.

## Trigger
The event that starts the use-case (usually a domain event, timer, or sensor change).

## Main success scenario
Given … (preconditions)
When … (trigger + actor/system actions)
Then … (system responses + postconditions)

## Alternate flows
Recoverable deviations — goal still achievable. Numbered to the basic-flow step they
branch from (e.g. 4a, 4b). Each as its own Given/When/Then.

## Exception flows
System-level failures where the goal is NOT met and intervention is needed.

## Postconditions
- Testable end state, joined with And/Or.

## State model  *(stateful behaviours only — all four modes; lighter for UC08/UC10)*
The states the behaviour moves through and the transitions between them, each transition
labelled with its threshold/timer condition. For charging states, state the **set-point rule**
— how the desired current is computed (e.g. Solar nudges current toward net import = 0 W on
smoothed readings; CapTar takes absolute headroom below the effective peak limit on raw
readings). The `stateDiagram-v2` in the Diagram section is authoritative for the state set.

## Domain events produced
- `EventName` — past-tense PascalCase — when it occurs and what it signals.

## Diagram
[Mermaid — `stateDiagram-v2` for stateful modes; `flowchart TD` for decision logic;
`sequenceDiagram` for actor-driven prompts/notifications]

## Requirements satisfied
Links to requirements.md entries (traceability).

## Relationships
«extend» / «include» links (e.g. "Extended by UC05 when deadline at risk";
shared resolution-rules references).
```

**Given/When/Then mapping (Heap, BDD):** Given = preconditions · When = trigger + actions ·
Then = system responses + postconditions. Used for main, alternate, and exception flows alike.

**Anti-patterns to avoid (ArgonDigital / Medium flow article):**
- No design/implementation detail ("what, not how"); no UI specifics.
- Don't split functionally identical interactions into separate use-cases.
- Pre/postconditions must be verifiable statements.
- One statement per line; always name the subject (Actor or System); active voice.
- Extract shared steps (the priority-ordered resolutions) into `resolution-rules.md`
  rather than duplicating them across use-cases.

**What "how" means here (so the State model isn't mistaken for it):** for an autonomous
behaviour the state set, transitions, thresholds, and set-point rule *are* the observable
behaviour contract — they are "what". The excluded "how" is the code / HA realization: the
Python module, which timer helper holds a cooldown, how state is persisted across restarts.
Those never appear in a use-case.

### `control-cycle.md`

Keeps the existing flow-document standard from CLAUDE.md verbatim:

> Purpose → Trigger → Domain events → Mermaid diagram → Steps → Edge cases → Requirements satisfied

Covers the coordinator spine that every use-case plugs into: read sensors → smooth (R10) →
dispatch to active mode module → apply peak-protection clamp (R3) → set charger current,
with voltage-aware conversion (NF4) and the rapid-cycling invariant (R11).

### `resolution-rules.md`

One decision table per resolution, each stating its priority order and requirement link:

- **Active SOC limit** (R7): solar-reserve cap → solar step-up → default.
- **Departure time** (R14): external sensor → public-holiday/home-day override → day-of-week default.
- **Effective peak limit**: `min(monthly_peak_demand, maximum_peak)`, rising to maximum peak under urgency.
- **Auto mode-selection** (R16): conditions → active mode, including Solar→CapTar escalation and revert.

### `entity-catalog.md`

One row per `sc_` entity, harvested from the `system-overview.md` glossary and `requirements.md`:

| Entity id | Domain | Role | Unit | Default / range | Realizes (glossary term) | Read by | Written by |

- **Role** — `config` (user-set helper), `sensor` (wraps an upstream entity), `state` (internal). For a `sensor` row, note the upstream entity it wraps (or "configured").
- **Realizes** — links to the glossary term the entity binds; never re-defines it.
- **Read by / Written by** — the use-cases and mechanism docs that touch the entity; bidirectional traceability, populated incrementally as each doc lands.
- Raw upstream entities are never catalog rows — they appear only as the source noted on a `sensor`-role wrapper.

---

## Writing order

1. `control-cycle.md` — the spine every use-case references.
2. `resolution-rules.md` — the shared lookups use-cases reference.
3. `entity-catalog.md` — the `sc_` entity bindings every use-case references (seed *Read by* / *Written by* from steps 1–2).
4. `use-cases/README.md` — inventory index.
5. `UC01` → `UC10` — one at a time (each updates the catalog's *Read by* / *Written by*).
6. Revisit `requirements.md` where use-cases reveal gaps or contradictions.

## Review protocol (per CLAUDE.md)

- Each document is reviewed by a **fresh, separate Opus agent** — never inline.
- Review checks cross-document consistency (glossary terms, requirement IDs), requirement
  coverage (every UC satisfies its claimed reqs; every req reachable from a UC or mechanism doc).
- Commit after approval with `docs: review and refine <filename>`.

## Follow-up

- `flows/README.md` and the `flows/` references in CLAUDE.md and
  `2026-06-24-analysis-approach-design.md` are superseded by this structure and should be
  updated when the first documents land (tracked as part of the implementation plan, not here).

---

## References

- ArgonDigital — Best practices with use cases
- UW CPED — When to write use cases (checklist)
- TechCanvass — How to write use cases (Cockburn / Jacobson / RUP templates)
- Medium (Chaitanya) — How to write the flow of use cases (basic / alternate / exception)
- Tony Heap (its-all-design) — BDD: use cases re-invented (Given/When/Then mapping)
