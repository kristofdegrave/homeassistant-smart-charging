# Smart Charging v3 — Analysis Documents Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Write the full analysis layer for the smart charging v3 project — system overview, requirements, and flow diagrams — before any code is written.

**Architecture:** Three-layer structure: system-overview (context) → requirements (what) → flows (how). Requirements are written fresh from the idea; archived docs in `docs/archive/` may be consulted as reference but are not copied. Each flow document contains a Mermaid diagram.

**Methodology:** Full design in `docs/plans/2026-06-24-analysis-approach-design.md`. Project guide in `CLAUDE.md`. Requirements quality standard: https://www.modernrequirements.com/blogs/good-software-requirements/

---

## Task 1: System Overview

**Files:**
- Create: `docs/analysis/system-overview.md`

**Step 1: Write the document**

Content must cover:
- **Hardware context** — grid connection, charger specs, EV specs, solar inverter specs (single-phase 230V, 40A grid; Alfen Eve 32A; Tesla Model 3 LR ~75kWh; SMA 4kWp / 4kW ceiling)
- **Stakeholders** — EV driver (car ready on time), Energy manager (cost minimised, solar used, peak controlled), System maintainer (observable, debuggable, safe to change). All three roles are currently one person but are kept separate because convenience, cost, and maintainability can pull in different directions.
- **Problem statement** — unmanaged EV charging draws full grid power regardless of solar, tariff, or peak demand
- **Goals** — maximise solar self-consumption, keep CapTar peak low, charge during cheap tariff windows, always meet departure SOC target
- **Ubiquitous Language glossary** — define every domain term used across all documents. Each entry: term, definition in one sentence, unit/type where applicable. Seed list: `solar surplus`, `effective peak limit`, `CapTar`, `control cycle`, `active SOC limit`, `cheap-tariff window`, `urgency`, `charger status`, `smoothed value`. Add any additional terms that emerge while writing.
- **Out of scope** — mode-selection automation (separate HA concern), Eco mode (deferred)

**Step 2: Self-review against 6Cs**
- Is every claim clear and unambiguous?
- Is there anything missing that a developer would need to understand the system?
- Are there any contradictions?

**Step 3: Commit**
```bash
git add docs/analysis/system-overview.md
git commit -m "docs: add system overview for smart charging v3"
```

---

## Task 2: Requirements

**Files:**
- Create: `docs/analysis/requirements.md`

**Step 1: Write the document structure**

Header:
```markdown
# Smart Charging v3 — Requirements

Requirements derived fresh from the system overview. Each requirement describes *what* the system must do, never *how*.

**Priority key:** Must = non-negotiable / Should = important but not blocking / Could = nice to have / Won't = explicitly out of scope

---
```

**Step 2: Write functional requirements**

Write one requirement block per concern. Use this template for each:

```markdown
### R<n> — <Title>

**Priority:** Must / Should / Could / Won't
**What:** One sentence. Subject + verb + observable outcome. No implementation language.

**Acceptance criteria:**
- [ ] Specific, measurable condition that can be verified
- [ ] Another verifiable condition
```

Requirements to write (derive the acceptance criteria fresh — do not copy from archive):

| ID | Title | Priority |
|----|-------|----------|
| R1 | Solar-first charging | Must |
| R2 | Solar-only charging | Must |
| R3 | Capacity tariff (CapTar) peak protection | Must |
| R4 | Cost-efficient grid charging | Must |
| R5 | Departure deadline guarantee | Must |
| R6 | SOC target management | Must |
| R7 | Solar SOC step-up | Should |
| R8 | Work-from-home night charging cap | Should |
| R9 | Sensor smoothing | Must |
| R10 | Rapid cycling prevention | Must |
| R11 | Plug-in reminder notification | Should |
| R12 | WFH evening notification | Should |
| R13 | Configurable departure times | Must |
| R14 | Configurable EV battery capacity | Must |

**Step 3: Write non-functional requirements**

| ID | Title | Priority |
|----|-------|----------|
| NF1 | Mode selection owned by HA, not integration | Must |
| NF2 | One module per charging mode | Must |
| NF3 | All sensor access via `sc_` wrapper entities | Must |

**Step 4: Write constraints section**

Hard rules that can never be violated regardless of mode:
- C1: Charging current is 0A or 6–32A (1–5A causes Tesla errors)
- C2: Charge limit changes only when car is at home
- C3: Net import must never exceed effective peak limit

**Step 5: Self-review 6Cs checklist for every requirement**
- [ ] Clarity — one interpretation only
- [ ] Concision — no redundant words
- [ ] Completeness — all conditions covered
- [ ] Consistency — no contradictions between requirements
- [ ] Correctness — reflects actual need
- [ ] Concreteness — measurable, not vague

**Step 6: Commit**
```bash
git add docs/analysis/requirements.md
git commit -m "docs: add fresh requirements for smart charging v3"
```

---

## Task 3: Control Cycle Flow

**Files:**
- Create: `docs/analysis/flows/00-control-cycle.md`

**Step 1: Write the document**

This is the spine — the coordinator loop that runs every N seconds (configurable, default 10s).

Structure:
```markdown
# Flow 00 — Control Cycle

## Purpose
## Trigger / Entry condition
## Domain events
## Flow diagram
[Mermaid flowchart TD]
## Steps
## Edge cases
## Requirements satisfied
```

Domain events to identify: `ControlCycleExecuted`, `ChargerCurrentSet`, `ModeDispatched`. Add others that emerge.

The flow must show:
1. Read sensors (raw values)
2. Apply smoothing (except for peak check)
3. Determine active profile (`input_select.sc_active_profile`)
4. Dispatch to mode module
5. Apply peak protection check (raw values, C3)
6. Set charger current
7. Wait for next cycle

**Step 2: Draw the Mermaid diagram**

Use `flowchart TD`. Include decision diamonds for: active profile selection, peak protection check, charger connected check.

**Step 3: Commit**
```bash
git add docs/analysis/flows/00-control-cycle.md
git commit -m "docs: add control cycle flow"
```

---

## Task 4: Solar Flow

**Files:**
- Create: `docs/analysis/flows/01-solar-flow.md`

**Step 1: Write the document**

Domain events to identify: `SolarChargingStarted`, `SolarChargingHeld`, `SolarChargingStopped`, `GridFallbackActivated`. Add others that emerge.

Cover:
- Trigger: active profile = `Solar`, charger connected
- Smoothed surplus ≥ 150W → start charging
- Set current to maximise self-consumption (net import ≤ 0W)
- Grid fallback at minimum 6A when surplus drops below threshold
- Hold at 6A for 5 minutes before stopping (cloud cover ride-out)
- Cooldown: 2 minutes before restart after a stop

Draw Mermaid `flowchart TD` showing the surplus check, current calculation, hold timer, and stop condition.

**Step 2: Commit**
```bash
git add docs/analysis/flows/01-solar-flow.md
git commit -m "docs: add solar flow"
```

---

## Task 5: Solar-Only Flow

**Files:**
- Create: `docs/analysis/flows/02-solar-only-flow.md`

**Step 1: Write the document**

Domain events to identify: `SolarOnlyChargingStarted`, `SolarOnlyChargingStopped`. Reuse events from Solar flow where behaviour is identical; only add new events where Solar-Only differs.

Key differences from Solar flow:
- Start threshold: smoothed surplus ≥ 1300W (≈ 5.65A proxy for sustaining 6A from solar)
- No grid fallback — stops immediately when surplus drops below 1300W
- No 5-minute hold — stops immediately
- Cooldown: 2 minutes before restart

Draw Mermaid diagram. Highlight the differences from Solar flow in the steps section.

**Step 2: Commit**
```bash
git add docs/analysis/flows/02-solar-only-flow.md
git commit -m "docs: add solar-only flow"
```

---

## Task 6: CapTar Flow

**Files:**
- Create: `docs/analysis/flows/03-captar-flow.md`

**Step 1: Write the document**

Domain events to identify: `CaptarChargingStarted`, `CaptarChargingStopped`, `CaptarCooldownStarted`, `ChargingSuppressedByWFHCap`. Add others that emerge.

Cover:
- Trigger: active profile = `Captar`, charger connected
- Only active during cheap-tariff windows (weekdays 22:00–07:00, weekends all day)
- Set current to maximum that keeps net import ≤ effective peak limit
- Stop immediately if minimum current (6A) would breach peak limit
- WFH night cap suppresses charging (unless deadline urgency applies)
- 10-minute cooldown before restart (prevents Tesla errors and aligns with DSO 15-min measurement windows)

Draw Mermaid diagram with tariff window check, WFH suppression check, peak headroom calculation, and stop/cooldown path.

**Step 2: Commit**
```bash
git add docs/analysis/flows/03-captar-flow.md
git commit -m "docs: add captar flow"
```

---

## Task 7: Power Flow

**Files:**
- Create: `docs/analysis/flows/04-power-flow.md`

**Step 1: Write the document**

Domain events to identify: `PowerModeChargingStarted`, `PowerModeChargingStopped`.

Cover:
- Trigger: active profile = `Power`, charger connected
- Set current to fixed value from `input_number.sc_power_mode_amps`
- No solar tracking, no peak rules, no tariff windows
- Still subject to C1 (6–32A range) and C3 (peak limit — handled by coordinator, not this module)

Draw simple Mermaid diagram.

**Step 2: Commit**
```bash
git add docs/analysis/flows/04-power-flow.md
git commit -m "docs: add power flow"
```

---

## Task 8: SOC Management Flow

**Files:**
- Create: `docs/analysis/flows/05-soc-management.md`

**Step 1: Write the document**

Domain events to identify: `SolarSOCStepUpApplied`, `SolarSOCStepUpReverted`, `SOCLimitResolved`.

Cover three sub-flows:

**Active SOC limit resolution (priority order):**
1. WFH night cap active + sun below horizon → 60%
2. Solar step-up in effect → stepped-up value (85–100%)
3. Default → `input_number.sc_active_soc` (default 80%)

**Solar step-up:**
- Trigger: solar charging active, SOC within 2% of current limit
- Raise limit by 5pp, up to `input_number.sc_max_solar_soc` (default 100%)
- 10-minute cooldown between step-ups
- Revert conditions: car disconnects, mode switches to Captar

Draw `stateDiagram-v2` for SOC limit state (default → stepped-up → reverted).

**Step 2: Commit**
```bash
git add docs/analysis/flows/05-soc-management.md
git commit -m "docs: add SOC management flow"
```

---

## Task 9: Deadline Override Flow

**Files:**
- Create: `docs/analysis/flows/06-deadline-override.md`

**Step 1: Write the document**

Domain events to identify: `DeadlineUrgencyTriggered`, `DeadlineUnreachableWarned`.

Cover:
- When: car cannot reach active SOC limit by departure time at current rate
- Calculation:
  ```
  energy_needed_kwh = (active_soc_limit - current_soc) / 100 × battery_capacity_kwh
  hours_remaining   = (departure_datetime - now) / 3600
  required_power_kw = energy_needed_kwh / hours_remaining
  required_amps     = ceil(required_power_kw × 1000 / 230)
  ```
- Set charger to `max(required_amps, 6)`, capped at peak headroom
- Peak tariff acceptable during override
- WFH cap is NOT bypassed — urgency only reaches the active limit, not a higher one
- If 6A still can't meet deadline: charge at 6A, emit warning

Draw `flowchart TD` showing the deadline check → calculation → apply → warning path.

**Step 2: Commit**
```bash
git add docs/analysis/flows/06-deadline-override.md
git commit -m "docs: add deadline override flow"
```

---

## Task 10: WFH Logic Flow

**Files:**
- Create: `docs/analysis/flows/07-wfh-logic.md`

**Step 1: Write the document**

Domain events to identify: `WFHConfirmed`, `WFHNotificationSent`, `WFHNightCapActivated`, `WFHNightCapLifted`.

Cover two sub-flows:

**Evening notification (18:00 daily):**
- Send actionable notification: "Working from home tomorrow?"
- Yes → set `input_boolean.sc_wfh_tomorrow = on`
- No response by 20:00 → treat as `off`
- Flag resets at midnight

**Night cap activation:**
- Conditions: WFH flag = on AND solar forecast tomorrow > 12 kWh AND sun below horizon
- Effect: active SOC limit capped at 60% until sunrise
- Cheap-tariff grid charging suppressed during cap
- Deadline urgency can override the cap to reach 60% (but not beyond)

Draw `sequenceDiagram` for the notification flow. Draw `flowchart TD` for cap activation logic.

**Step 2: Commit**
```bash
git add docs/analysis/flows/07-wfh-logic.md
git commit -m "docs: add WFH logic flow"
```

---

## Task 11: Flow Selection Flow

**Files:**
- Create: `docs/analysis/flows/08-flow-selection.md`

**Step 1: Write the document**

Domain events to identify: `ActiveProfileChanged`, `SolarProfileSelected`, `CaptarProfileSelected`. These are the events that *trigger* profile changes — useful for HA automation design.

This describes how `input_select.sc_active_profile` gets its value — the HA automation layer that decides *when* to switch modes. This is out of scope for the integration itself (NF1) but needs to be analysed so the integration is designed correctly.

Cover the decision logic:
- Solar forecast available + sun up → prefer Solar or SolarOnly
- Night + cheap tariff window → prefer Captar
- WFH reservation active at night → suppress Captar, prefer Off or low-current
- User override always wins
- Eco mode (auto day→Solar, night→Captar) — deferred, covered by this automation when built

Draw `stateDiagram-v2` for the profile state machine showing all valid transitions.

**Step 2: Commit**
```bash
git add docs/analysis/flows/08-flow-selection.md
git commit -m "docs: add flow selection analysis"
```

---

## Task 12: Revisit Requirements

**Files:**
- Modify: `docs/analysis/requirements.md`

**Step 1: Review gaps**

After writing all flows, re-read `requirements.md` and check:
- Do the flows reveal any missing requirements?
- Do any acceptance criteria need sharpening now that the flows are concrete?
- Are there any contradictions between requirements and flows?

Common gaps to check:
- Off mode (explicit requirement needed?)
- Charger status normalisation (`sensor.sc_charger_status`)
- Control interval configurability
- Plug-in reminder deduplication logic

**Step 2: Update requirements**

Add, refine, or mark requirements as needs-flow-doc where applicable.

**Step 3: Commit**
```bash
git add docs/analysis/requirements.md
git commit -m "docs: refine requirements after flow analysis"
```

---

## Done

All analysis documents are complete. The project is ready for implementation planning.

Next step: run the `brainstorming` skill on the first implementation task (starting with the coordinator + control cycle module).
