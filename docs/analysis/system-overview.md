# Smart Charging v3 — System Overview

This document sets the context for the smart charging integration: the hardware it controls, the people it serves, the problem it solves, the goals it pursues, the shared vocabulary used across every analysis document, and what is explicitly out of scope.

It is the first document in the analysis layer. The Ubiquitous Language glossary below is authoritative: every domain term used in `requirements.md` and the flow documents must be defined here first.

---

## Hardware context

All power and current calculations assume single-phase 230 V. Amperes convert to watts as `A × 230`.

| Component | Specification | Relevant constraint |
|---|---|---|
| Grid connection | Single-phase 230 V, 40 A | Whole-house supply ceiling is 40 A; the charger shares it with all household load. |
| Charger — Alfen Eve Single Pro | 1-phase, max 32 A (7.4 kW) | Charging current set-point ranges 6–32 A; below 6 A is not usable (see C1). |
| EV — Tesla Model 3 LR Dual Motor | ~75 kWh usable battery | Battery capacity feeds the deadline energy calculation; configurable to match the actual car. |
| Solar — SMA SunnyBoy 4000TL-21 | 4.68 kWp panels, 4 kW inverter ceiling | Solar production is capped at the 4 kW inverter ceiling, so surplus available to the charger never exceeds ~4 kW. |

The 4 kW inverter ceiling is the reason the effective peak limit is capped at 4 kW: there is no benefit to allowing a higher monthly peak than the most the solar system can ever offset.

---

## Stakeholders

Three roles drive the design. All three are currently filled by the same person, but they are kept separate because their concerns — **convenience**, **cost**, and **maintainability** — can pull in different directions, and naming them makes those trade-offs explicit.

| Stakeholder | Needs | Concerns |
|---|---|---|
| **EV driver** | The car charged to its target SOC before departure; a reminder if it was left unplugged. | Car not ready on time; charging stops unexpectedly. |
| **Household energy manager** | Electricity cost minimised; solar surplus fully used; the CapTar monthly peak kept under control. | A monthly peak spike; cheap-tariff windows missed; unnecessary grid charging; wasted solar surplus. |
| **System maintainer** | Observable behaviour; easy to debug; safe to deploy changes. | Silent failures (wrong sensor value, automation not firing); hard-to-trace logic; breakage after Home Assistant updates. |

---

## Problem statement

Charging an EV without intelligence draws power from the grid at full speed regardless of solar production, electricity tariff, or monthly peak demand. This maximises both cost and CapTar impact: solar surplus is exported instead of self-consumed, expensive peak-tariff energy is bought when cheap windows are available, and every uncontrolled charging session can raise the monthly peak that the capacity tariff bills against.

The smart charging system must charge the car at the lowest possible cost while still guaranteeing it reaches its target SOC before the configured departure time.

---

## Goals

1. **Maximise solar self-consumption** — solar is always the cheapest source and is used before any grid power.
2. **Keep the monthly peak (CapTar) under control** — avoid raising the billed peak demand through unnecessary charging spikes.
3. **Charge cost-efficiently from the grid** — when grid power is needed, prefer cheap-tariff windows over peak-tariff periods.
4. **Always meet the departure deadline** — the car reaches its active SOC limit by the configured departure time, even when that requires accepting peak-tariff cost.

These goals are ordered by preference but bounded by goal 4: cost optimisation never overrides the deadline guarantee.

---

## Ubiquitous Language

Shared vocabulary for all analysis documents. Every domain term used in requirements or flows must be defined here. Entries are alphabetised within groupings: domain concepts first, then entity-naming conventions.

### Domain concepts

**`solar surplus`** — Solar power available to the charger after all other household consumption, computed as `charger_w − net_w` where `net_w` is net grid import (positive = importing, negative = exporting); a positive surplus means solar is feeding the charger. Unit: watts (W).

**`net import`** — Net power flowing from the grid into the house, equal to `net_w`; positive means importing from the grid, negative means exporting to the grid. Unit: watts (W).

**`effective peak limit`** — The ceiling on net import that charging must never exceed, equal to `min(monthly_peak_demand, 4 kW)`; during deadline urgency the floor is raised so the limit is never below 3.5 kW. The charger does not consume headroom freed up by other household appliances. Unit: kilowatts (kW).

**`peak headroom`** — The additional power the charger may draw without breaching the effective peak limit, expressed in amperes for set-point calculations. Unit: amperes (A).

**`CapTar`** — Capacity tariff; the Belgian distribution-grid billing component charged on the highest 15-minute average net import (monthly peak demand) rather than total energy, which is why every avoidable peak directly raises the bill.

**`control cycle`** — One iteration of the coordinator loop: read sensors, smooth, dispatch to the active mode module, apply peak protection, set charger current. Runs every control interval (configurable, default 10 s).

**`control interval`** — The time between consecutive control cycles, configured via `input_number.sc_control_interval_s` (default 10 s); every duration expressed as a number of control cycles resolves to `n × control_interval` seconds at runtime.

**`active SOC limit`** — The charge-limit target in effect at a given moment, resolved in priority order: (1) WFH night cap of 60 % when the reservation is active and the sun is below the horizon, (2) the solar step-up value (85–100 %) when a step-up is in effect, otherwise (3) the default `sc_active_soc` (default 80 %). Unit: percent (%).

**`solar step-up`** — The mechanism that raises the active SOC limit by 5 percentage points (up to `sc_max_solar_soc`) when solar charging is active and SOC comes within 2 % of the current limit, so abundant solar is stored rather than exported. Unit: percentage points (pp).

**`cheap-tariff window`** — The period when grid energy is at the low tariff: weekdays 22:00–07:00 and weekends all day; CapTar-mode grid charging is permitted only inside this window.

**`urgency`** — Deadline urgency; the condition where the car cannot reach its active SOC limit by the configured departure time at the current charger output, triggering an escalation of charging current (accepting peak tariff if needed) up to — but not beyond — the active SOC limit. See R5.

**`departure deadline`** — The configured time by which the car must reach its active SOC limit; the weekday time applies Monday–Friday and the weekend time applies Saturday, Sunday, and public holidays.

**`charger status`** — The normalised charger connection state exposed via `sensor.sc_charger_status`, mapped to one of three canonical values: `disconnected` (no vehicle), `connected` (plugged in, not drawing current), `charging` (plugged in and drawing current).

**`smoothed value`** — A sensor reading averaged over the last 4 control cycles (a rolling mean of `net_w` or `solar_w`) used for charging-current decisions to reject transient spikes; peak protection deliberately bypasses smoothing and uses raw readings to avoid lag.

**`raw value`** — An unsmoothed, most-recent sensor reading; used by peak protection (R3) so a peak breach cannot persist for up to one smoothing window.

**`grid fallback`** — In Solar mode, charging at the minimum current (6 A) using grid power when solar surplus alone cannot sustain it; permitted in Solar mode, explicitly excluded in SolarOnly mode.

**`charging mode` / `active profile`** — The behaviour the integration executes, selected via `input_select.sc_active_profile`: `Solar`, `SolarOnly`, `Captar`, `Power`, or `Off`. The coordinator reads this helper and dispatches to the matching module; deciding *when* to switch profiles is out of scope (NF1).

**`WFH night cap`** — A 60 % active SOC limit applied overnight when the user has confirmed they will work from home tomorrow and the next-day solar forecast exceeds 12 kWh, reserving battery room for solar charging the following day; cheap-tariff grid charging is suppressed while the cap is active.

**`minimum charging current`** — 6 A, the lowest current the charger may be set to other than 0 A (IEC 61851 minimum); enforced by C1.

**`sun is down`** — The condition `sun.sun` state equals `below_horizon`.

### Entity naming convention

**`sc_` prefix** — The namespace prefix on every helper and sensor owned by this integration, following `<domain>.sc_<descriptive_name>` (e.g. `input_number.sc_active_soc`); it prevents collisions with unrelated helpers and makes every smart-charging entity findable in the Home Assistant UI. Raw upstream entities (e.g. `sensor.tesla_batterijniveau`) are never referenced directly — they are always wrapped in an `sc_` sensor.

---

## Out of scope

- **Mode-selection automation** — the Home Assistant automation that decides *when* to switch `input_select.sc_active_profile` (based on time, SOC, solar forecast, WFH flag, and departure time) is a separate HA configuration concern. The integration only executes the selected mode; it contains no mode-selection logic (NF1).
- **`Eco` mode** — fully automatic day→Solar, night→Captar switching is deferred; it will be covered by the mode-selection automation when that is built.
