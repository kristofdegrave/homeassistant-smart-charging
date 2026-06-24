# Smart Charging v3 — System Overview

This document sets the context for the smart charging integration: the hardware it controls, the people it serves, the problem it solves, the goals it pursues, the shared vocabulary used across every analysis document, and what is explicitly out of scope.

It is the first document in the analysis layer. The Ubiquitous Language glossary below is authoritative: every domain term used in `requirements.md` and the flow documents must be defined here first.

---

## Hardware context

The integration is hardware-agnostic. It controls any charger, EV, and solar installation through a set of **configurable parameters**; no specific make or model is assumed. This release targets single-phase installations, so all power and current calculations assume single-phase voltage (Amperes convert to watts as `A × V`, where `V` is the supply voltage — the measured grid voltage when a healthy reading is available, otherwise a configurable nominal voltage, default 230 V); three-phase support is deferred.

The parameters the system reasons over:

| Parameter | Meaning | Relevant constraint |
|---|---|---|
| Grid supply ceiling | Maximum current the whole-house connection can draw | The charger shares this ceiling with all household load. |
| Charger current range | The minimum and maximum charging current set-point | Set-point ranges from the minimum (default 6 A, the IEC 61851 floor — see C1) to the configured maximum; below the minimum is not usable. |
| EV battery capacity | Usable battery capacity of the connected car | Feeds the deadline energy calculation; configured to match the actual car. |
| Solar inverter ceiling | Maximum power the solar inverter can deliver | Solar surplus available to the charger never exceeds this ceiling, which is why the effective peak limit is capped at the inverter ceiling — there is no benefit to allowing a higher monthly peak than the most the solar system can ever offset. |

**Reference setup (example only).** The figures used throughout these documents are grounded in one concrete installation, but they are illustrative defaults, not architectural assumptions: single-phase 230 V / 40 A grid connection; charger with a 6–32 A range (7.4 kW); ~75 kWh EV battery; 4 kW solar inverter ceiling. Where a later document cites a number like "4 kW" or "6 A", read it as "the configured value, which in the reference setup is 4 kW / 6 A".

---

## Stakeholders

Three roles drive the design. All three are currently filled by the same person, but they are kept separate because their concerns — **convenience**, **cost**, and **maintainability** — can pull in different directions, and naming them makes those trade-offs explicit.

| Stakeholder | Needs | Concerns |
|---|---|---|
| **EV driver** | The car charged to its active SOC limit before departure; a reminder if it was left unplugged. | Car not ready on time; charging stops unexpectedly. |
| **Household energy manager** | Electricity cost minimised; solar surplus fully used; the CapTar monthly peak kept under control. | A monthly peak spike; low-tariff periods missed; unnecessary grid charging; wasted solar surplus. |
| **System maintainer** | Observable behaviour; easy to debug; safe to deploy changes. | Silent failures (wrong sensor value, automation not firing); hard-to-trace logic; breakage after Home Assistant updates. |

---

## Problem statement

Charging an EV without intelligence draws power from the grid at full speed regardless of solar production, electricity tariff, or monthly peak demand. This maximises both cost and CapTar impact: solar surplus is exported instead of self-consumed, expensive peak-tariff energy is bought even while the low-tariff flag is active, and every uncontrolled charging session can raise the monthly peak that the capacity tariff bills against.

The smart charging system must charge the car at the lowest possible cost while still guaranteeing it reaches its active SOC limit before the configured departure time.

---

## Goals

1. **Maximise solar self-consumption** — solar is always the cheapest source and is used before any grid power.
2. **Keep the monthly peak (CapTar) under control** — avoid raising the billed peak demand through unnecessary charging spikes.
3. **Charge cost-efficiently from the grid** — when grid power is needed, prefer low-tariff periods (when the low-tariff flag is active) over peak-tariff periods.
4. **Meet the departure deadline whenever physically possible** — the car reaches its active SOC limit by the configured departure time, escalating charging current (and accepting peak-tariff cost) as needed — but only up to the effective peak limit. CapTar peak protection is the hard ceiling: if even the maximum permitted current cannot make the deadline, the system charges as fast as that ceiling allows rather than breaching the peak.

These goals are ordered by preference but bounded by goal 4: cost optimisation never overrides the deadline guarantee. That guarantee is itself bounded by the effective peak limit — deadline urgency raises charging current up to that limit (raising the limit to its urgency floor) but never beyond it. Its strength is therefore configurable: the urgency floor sets how aggressively the system may chase the deadline, trading CapTar cost against deadline confidence.

---

## Ubiquitous Language

Shared vocabulary for all analysis documents. Every domain term used in requirements or flows must be defined here. Entries are grouped thematically: domain concepts first, then entity-naming conventions.

### Domain concepts

**`solar surplus`** — Solar power available to the charger after all other household consumption, computed as `charger_w − net_w` where `net_w` is net grid import (positive = importing, negative = exporting); a positive surplus means solar is feeding the charger. Unit: watts (W).

**`net import`** — Net power flowing from the grid into the house, equal to `net_w`; positive means importing from the grid, negative means exporting to the grid. Unit: watts (W).

**`supply voltage`** — The single-phase voltage used to convert between amperes and watts (`watts = A × supply voltage`): the measured grid voltage when a healthy reading is available, otherwise a configurable nominal voltage (default 230 V). Using the live value keeps current-derived thresholds (e.g. the minimum charging current) accurate as grid voltage drifts. Unit: volts (V).

**`monthly peak demand`** — The highest 15-minute average net import recorded so far in the current calendar month; the value CapTar bills against and one operand of the effective peak limit. Resets at the start of each month. Unit: kilowatts (kW).

**`solar inverter ceiling`** — The maximum power the solar inverter can deliver (a configurable parameter — see Hardware context; reference setup: 4 kW); it caps both solar surplus and, as the other operand of the effective peak limit, the peak the system will ever target. Unit: kilowatts (kW).

**`effective peak limit`** — The ceiling on net import that charging must never exceed, equal to `min(monthly_peak_demand, solar_inverter_ceiling)` (reference setup: 4 kW). A configurable urgency floor applies during deadline urgency (reference setup: 3.5 kW): if `monthly_peak_demand` has been driven low enough that the normal limit would fall below this floor, the limit is held at the floor instead, so urgency can still charge meaningfully. The floor sets how aggressively the system may chase the deadline. Unit: kilowatts (kW).

**`peak headroom`** — The additional charging current the charger may draw before net import would reach the safety target (`effective peak limit − safety margin`); expressed in amperes for set-point calculations. Unit: amperes (A).

**`safety margin`** — A configurable buffer held in reserve below the effective peak limit; the charger targets `effective peak limit − safety margin` rather than the limit itself, so measurement noise and control-loop response lag cannot push the real 15-minute net import past the billed peak. A larger margin trades a little charging speed for stronger peak-breach protection. Unit: watts (W).

**`CapTar`** — Capacity tariff; the Belgian distribution-grid billing component charged on the highest 15-minute average net import (monthly peak demand) rather than total energy, which is why every avoidable peak directly raises the bill.

**`control cycle`** — One iteration of the coordinator loop: read sensors, smooth, dispatch to the active mode module, apply peak protection, set charger current. Runs every control interval (configurable, default 10 s).

**`control interval`** — The time between consecutive control cycles, configured via `input_number.sc_control_interval_s` (default 10 s); every duration expressed as a number of control cycles resolves to `n × control_interval` seconds at runtime.

**`active SOC limit`** — The charge-limit target in effect at a given moment, resolved in priority order: (1) the WFH night cap (configurable, default 60 %) when the reservation is active and the sun is below the horizon, (2) the solar step-up value (configurable range, default ceiling `sc_max_solar_soc` 100 %) when a step-up is in effect, otherwise (3) the default `sc_active_soc` (configurable, default 80 %). Unit: percent (%).

**`solar step-up`** — The mechanism that raises the active SOC limit by a configurable step (default 5 percentage points, up to `sc_max_solar_soc`) when solar charging is active and SOC comes within a configurable threshold (default 2 %) of the current limit, so abundant solar is stored rather than exported. Unit: percentage points (pp).

**`low-tariff flag`** — A configurable boolean signal the installation provides, indicating that grid energy is currently at the low tariff; used instead of a hard-coded schedule, which keeps the system tariff-agnostic. CapTar-mode grid charging is permitted only while this flag is active.

**`urgency`** — Deadline urgency; the condition where the car cannot reach its active SOC limit by the configured departure time at the current charger output, triggering an escalation of charging current (accepting peak tariff if needed) up to — but not beyond — the effective peak limit. See R5.

**`departure deadline`** — The configured time by which the car must reach its active SOC limit; the weekday time applies Monday–Friday and the weekend time applies Saturday, Sunday, and public holidays.

**`charger status`** — The normalised charger connection state exposed via `sensor.sc_charger_status`, mapped to one of three canonical values: `disconnected` (no vehicle), `connected` (plugged in, not drawing current), `charging` (plugged in and drawing current).

**`smoothed value`** — A sensor reading averaged over the last *N* control cycles (configurable, default 4) — a rolling mean of `net_w` or `solar_w` — used for charging-current decisions to reject transient spikes; peak protection deliberately bypasses smoothing and uses raw readings to avoid lag.

**`raw value`** — An unsmoothed, most-recent sensor reading; used by peak protection (R3) so a peak breach cannot persist for up to one smoothing window.

**`grid fallback`** — In Solar mode, charging at the minimum charging current using grid power when solar surplus alone cannot sustain it; permitted in Solar mode, explicitly excluded in SolarOnly mode.

**`charging mode` (mode)** — The concrete behaviour the coordinator executes at a given moment: `Solar`, `SolarOnly`, `Captar`, `Power`, or `Off`. A fixed set provided by the integration. The coordinator reads the active mode and dispatches to the matching module; it contains no logic for *choosing* the mode (NF1).

**`active mode`** — The mode currently in effect, exposed via `input_select.sc_active_mode`.

**`profile`** — An extensible, higher-level strategy that determines which mode is active over time. This release ships two built-in profiles: `Manual` (the user selects the active mode directly) and `Auto` (the system selects it). The concept is deliberately designed so additional profiles can be added later — `Eco` is the first deferred candidate (see Out of scope) — and, in future, so users could define their own profiles with custom behaviour. A profile *sets* the active mode; it is not itself a mode. Selected via `input_select.sc_active_profile`. NF1 holds: profiles decide the mode, the coordinator only executes it.

**`Auto` profile** — The built-in profile that automatically selects the active mode over time from observable conditions (time of day, SOC, solar forecast, low-tariff flag, departure deadline, WFH reservation) and escalates between modes when circumstances demand it — for example, switching from `Solar` to `Captar` when deadline urgency requires grid charging that solar surplus alone cannot satisfy.

**`WFH reservation`** — The recorded confirmation that the user will work from home the next day, captured the previous evening (see R12) and reset each day; while active it enables the WFH night cap. Held in an `sc_` helper.

**`WFH night cap`** — A configurable active SOC limit (default 60 %) applied overnight when the user has confirmed they will work from home tomorrow and the next-day solar forecast exceeds a configurable threshold (default 12 kWh), reserving battery room for solar charging the following day; low-tariff grid charging is suppressed while the cap is active.

**`minimum charging current`** — The lowest current the charger may be set to other than 0 A (configurable, default 6 A — the IEC 61851 floor; reference setup: 6 A); enforced by C1.

**`sun is down`** — The condition `sun.sun` state equals `below_horizon`.

### Entity naming convention

**`sc_` prefix** — The namespace prefix on every helper and sensor owned by this integration, following `<domain>.sc_<descriptive_name>` (e.g. `input_number.sc_active_soc`); it prevents collisions with unrelated helpers and makes every smart-charging entity findable in the Home Assistant UI. Raw upstream entities (e.g. `sensor.tesla_batterijniveau`) are never referenced directly — they are always wrapped in an `sc_` sensor.

---

## Out of scope

- **`Eco` profile** — a profile beyond `Auto` that applies a richer cost/comfort strategy (e.g. forecast-driven day→`Solar`, night→`Captar` scheduling) is deferred. The `profile` concept is built to accept it later without rework; this release ships only the `Manual` and `Auto` profiles.
- **User-defined custom profiles** — letting users author their own profiles with bespoke behaviour is a future capability. The two-layer mode/profile model is designed to make it possible, but no authoring mechanism is provided this release.
- **Three-phase support** — all calculations assume single-phase this release (see Hardware context); three-phase is deferred.
