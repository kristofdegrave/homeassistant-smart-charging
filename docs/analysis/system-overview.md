# Smart Charging v3 — System Overview

This document sets the context for the smart charging integration: the hardware it controls, the people it serves, the problem it solves, the goals it pursues, how its pieces fit together, the shared vocabulary used across every analysis document, and what is explicitly out of scope.

It is the first document in the analysis layer. The Ubiquitous Language glossary below is authoritative: every domain term used in `requirements.md` and the flow documents must be defined here first.

---

## Hardware context

The integration is hardware-agnostic. It controls any charger and EV — and, when present, a solar installation — through a set of **configurable parameters**; no specific make or model is assumed. A solar installation is **optional**: it is declared through the solar capability (see `capability` in the glossary, R18), and an installation without solar simply runs the `Captar`, `Power`, and `Off` modes. This release targets single-phase installations, so all power and current calculations assume single-phase voltage (Amperes convert to watts as `A × V`, where `V` is the supply voltage — the measured grid voltage when a healthy reading is available, otherwise a configurable nominal voltage, default 230 V); three-phase support is deferred.

The parameters the system reasons over:

| Parameter              | Meaning                                             | Relevant constraint                                                                                                                                                                                                                                |
|------------------------|-----------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Grid supply ceiling    | Maximum current the whole-house connection can draw | The charger shares this ceiling with all household load.                                                                                                                                                                                           |
| Charger current range  | The minimum and maximum charging current set-point  | Set-point ranges from the minimum (default 6 A, the IEC 61851 floor — see C1) to the configured maximum; below the minimum is not usable.                                                                                                          |
| EV battery capacity    | Usable battery capacity of the connected car        | Feeds the deadline energy calculation; configured to match the actual car.                                                                                                                                                                         |
| Solar inverter ceiling | Maximum power the solar inverter can deliver        | Solar surplus available to the charger never exceeds this ceiling, which is why the effective peak limit is capped at the inverter ceiling — there is no benefit to allowing a higher monthly peak than the most the solar system can ever offset. |

**Reference setup (example only).** The figures used throughout these documents are grounded in one concrete installation, but they are illustrative defaults, not architectural assumptions: single-phase 230 V / 40 A grid connection; charger with a 6–32 A range (7.4 kW); ~75 kWh EV battery; 4 kW solar inverter ceiling. Where a later document cites a number like "4 kW" or "6 A", read it as "the configured value, which in the reference setup is 4 kW / 6 A".

---

## Stakeholders

Three roles drive the design. All three are currently filled by the same person, but they are kept separate because their concerns — **convenience**, **cost**, and **maintainability** — can pull in different directions, and naming them makes those trade-offs explicit.

| Stakeholder                  | Needs                                                                                             | Concerns                                                                                                                 |
|------------------------------|---------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------|
| **EV driver**                | The car charged to its active SOC limit before departure; a reminder if it was left unplugged.    | Car not ready on time; charging stops unexpectedly.                                                                      |
| **Household energy manager** | Electricity cost minimised; solar surplus fully used; the CapTar monthly peak kept under control. | A monthly peak spike; low-tariff periods missed; unnecessary grid charging; wasted solar surplus.                        |
| **System maintainer**        | Observable behaviour; easy to debug; safe to deploy changes.                                      | Silent failures (wrong sensor value, automation not firing); hard-to-trace logic; breakage after Home Assistant updates. |

---

## Problem statement

Charging an EV without intelligence draws power from the grid at full speed regardless of solar production, electricity tariff, or monthly peak demand. This maximises both cost and CapTar impact: solar surplus is exported instead of self-consumed, expensive high-tariff energy is bought even when low-tariff periods are available, and every uncontrolled charging session can raise the monthly peak that the capacity tariff bills against.

The smart charging system must charge the car at the lowest possible cost while still guaranteeing it reaches its active SOC limit before the configured departure time.

---

## Goals

1. **Maximise solar self-consumption** — solar is always the cheapest source and is used before any grid power.
2. **Keep the monthly peak (CapTar) under control** — avoid raising the billed peak demand through unnecessary charging spikes.
3. **Charge cost-efficiently from the grid** — when grid power is needed, prefer low-tariff periods (when the low-tariff flag is active) over high-tariff periods.
4. **Meet the departure deadline whenever physically possible** — the car reaches its active SOC limit by the configured departure time, escalating charging current (and accepting high-tariff cost) as needed — but only up to the effective peak limit. CapTar peak protection is the hard ceiling: if even the maximum permitted current cannot make the deadline, the system charges as fast as that ceiling allows rather than breaching the peak.

These goals are ordered by preference but bounded by goal 4: cost optimisation never overrides the deadline guarantee. That guarantee is itself bounded by the effective peak limit — during urgency the limit rises to the configured maximum peak, and charging current escalates up to it (less the safety margin) but never beyond. Its strength is therefore configurable: the maximum peak sets how aggressively the system may chase the deadline, trading CapTar cost against deadline confidence.

---

## How it fits together

At runtime the integration is a single control loop. The **active profile** decides *which mode* is active; the **coordinator** then executes that mode on every control cycle — reading sensors, smoothing them, asking the active mode module for a desired charger current, and finally clamping that current with peak protection before applying it. Every input and output crosses an `sc_` wrapper entity, which is what keeps the integration hardware-agnostic.

This is the orientation map; flow `00-control-cycle.md` details the loop and the per-mode flows detail each mode module.

```mermaid
flowchart TD
    Profile["Active profile<br/>(Manual / Auto)"] -->|selects| Mode["Active mode"]
    subgraph Cycle["Control cycle — every control interval"]
        direction TB
        Read["Read sensors"] --> Smooth["Smooth<br/>(rolling mean, N cycles)"]
        Smooth --> Dispatch["Dispatch to active mode module"]
        Mode -.-> Dispatch
        Dispatch --> Desired["Desired charger current"]
        Desired --> Peak["Peak protection"]
        Peak --> Set["Set charger current"]
    end
```

---

## Ubiquitous Language

Shared vocabulary for all analysis documents. Every domain term used in requirements or flows must be defined here. Entries are grouped thematically: domain concepts first, then entity-naming conventions.

### Domain concepts

**`solar surplus`** — Solar power available to the charger after all other household consumption, computed as `charger_w − net_w` where `net_w` is net grid import (positive = importing, negative = exporting); a positive surplus means solar is feeding the charger. Unit: watts (W).

**`net import`** — Net power flowing from the grid into the house, equal to `net_w`; positive means importing from the grid, negative means exporting to the grid. Unit: watts (W).

**`supply voltage`** — The single-phase voltage used to convert between amperes and watts (`watts = A × supply voltage`): the measured grid voltage when a healthy reading is available, otherwise a configurable nominal voltage (default 230 V). Using the live value keeps current-derived thresholds (e.g. the minimum charging current) accurate as grid voltage drifts. Unit: volts (V).

**`monthly peak demand`** — The highest 15-minute average net import recorded so far in the current calendar month; the value CapTar bills against and one operand of the effective peak limit. Resets at the start of each month. Unit: kilowatts (kW).

**`maximum peak`** — The highest monthly peak demand the system is ever willing to create, a configurable parameter (reference setup: 4 kW, defaulting to the solar inverter ceiling from the Hardware context — there is no benefit to a peak higher than the most solar can ever offset). It is the upper operand of the effective peak limit and the single ceiling that deadline urgency may raise the limit to. Unit: kilowatts (kW).

**`effective peak limit`** — The ceiling on net import that charging keeps a safety margin below and must never exceed. Normally `min(monthly_peak_demand, maximum_peak)`, so ordinary charging never raises the billed monthly peak beyond what is already incurred. During deadline urgency the limit rises to the maximum peak, allowing the deadline to push the monthly peak up to — but never beyond — that ceiling (see R5). Unit: kilowatts (kW).

**`peak headroom`** — The additional charging current the charger may draw before net import would reach the safety target (`effective peak limit − safety margin`); expressed in amperes for set-point calculations. Unit: amperes (A).

**`safety margin`** — A configurable buffer held in reserve below the effective peak limit; the charger targets `effective peak limit − safety margin` rather than the limit itself, so measurement noise and control-loop response lag cannot push the real 15-minute net import past the billed peak. A larger margin trades a little charging speed for stronger peak-breach protection. Unit: watts (W).

**`CapTar`** — Capacity tariff; the Belgian distribution-grid billing component charged on the highest 15-minute average net import (monthly peak demand) rather than total energy, which is why every avoidable peak directly raises the bill.

**`coordinator`** — The single control loop at the heart of the integration. Each control cycle it reads sensors, smooths them, dispatches to the active mode module for a desired charger current, applies peak protection, and sets the charger current. It executes whichever mode is active and contains no logic for *choosing* the mode (NF1); choosing is the profile's responsibility. Detailed in `control-cycle.md`.

**`control cycle`** — One iteration of the coordinator loop: read sensors, smooth, dispatch to the active mode module, apply peak protection, set charger current. Runs every control interval (configurable, default 10 s).

**`control interval`** — The time between consecutive control cycles, configured via `input_number.sc_control_interval_s` (default 10 s); every duration expressed as a number of control cycles resolves to `n × control_interval` seconds at runtime.

**`active SOC limit`** — The charge-limit target in effect at a given moment, resolved in priority order: (1) the solar-reserve cap (configurable, default 60 %) when the home-day flag is set and the sun is below the horizon, (2) the solar step-up value (configurable range, default ceiling `sc_max_solar_soc` 100 %) when a step-up is in effect, otherwise (3) the default `sc_active_soc` (configurable, default 80 %). Unit: percent (%).

**`solar forecast`** — The predicted solar energy yield for the next day, read from a configured forecast sensor (NF3); compared against a configurable threshold to decide whether the solar-reserve cap applies. Unit: kilowatt-hours (kWh).

**`solar step-up`** — The mechanism that raises the active SOC limit by a configurable step (default 5 percentage points, up to `sc_max_solar_soc`) when solar charging is active and SOC comes within a configurable threshold (default 2 %) of the current limit, so abundant solar is stored rather than exported. Unit: percentage points (pp).

**`low-tariff flag`** — A configurable boolean signal the installation provides, indicating that grid energy is currently at the low tariff; used instead of a hard-coded schedule, which keeps the system tariff-agnostic. CapTar-mode grid charging is permitted only while this flag is active.

**`urgency`** — Deadline urgency; the condition where the car cannot reach its active SOC limit by the configured departure time at the current charger output, triggering an escalation of charging current (accepting high tariff if needed) up to — but not beyond — the effective peak limit, which itself rises to the maximum peak during urgency. See R5.

**`departure deadline`** — The time by which the car must reach its active SOC limit on a given day, resolved in priority order: an external departure-time sensor, then a public-holiday or home-day override, then the per-day-of-week default. By default weekends, public holidays, and home days have no deadline; a day with no departure time imposes no deadline at all. See R14.

**`charger status`** — The normalised charger connection state exposed via `sensor.sc_charger_status`, mapped to one of three canonical values: `disconnected` (no vehicle), `connected` (plugged in, not drawing current), `charging` (plugged in and drawing current).

**`smoothed value`** — A sensor reading averaged over the last *N* control cycles (configurable, default 4) — a rolling mean of `net_w` or `solar_w` — used for charging-current decisions to reject transient spikes; peak protection deliberately bypasses smoothing and uses raw readings to avoid lag.

**`raw value`** — An unsmoothed, most-recent sensor reading; used by peak protection (R3) so a peak breach cannot persist for up to one smoothing window.

**`grid fallback`** — In Solar mode, charging at the minimum charging current using grid power when solar surplus alone cannot sustain it; permitted in Solar mode, explicitly excluded in SolarOnly mode.

**`charging mode` (mode)** — The concrete behaviour the coordinator executes at a given moment: `Solar`, `SolarOnly`, `Captar`, `Power`, or `Off`. A set provided by the integration; which of them are *available* depends on the installation's capabilities (see `capability`, R18). The coordinator reads the active mode and dispatches to the matching module; it contains no logic for *choosing* the mode (NF1).

**`capability`** — A hardware feature the installation has, declared by configuration, that determines which modes and behaviours are available. This release recognises the **solar capability** (a solar PV installation is present, `input_boolean.sc_solar_available`, default present). When it is absent, the `Solar` and `SolarOnly` modes, the solar SOC step-up, and the solar-reserve cap are all unavailable, and the `Auto` profile never selects a solar mode; `Captar`, `Power`, and `Off` remain. The concept is extensible so further capabilities (e.g. a home battery) can be added later, each gating the modes and behaviours that depend on that hardware, without changing existing modes (NF2). See R18.

**`active mode`** — The mode currently in effect, exposed via `input_select.sc_active_mode`.

**`profile`** — An extensible, higher-level strategy that determines which mode is active over time. This release ships two built-in profiles: `Manual` (the user selects the active mode directly) and `Auto` (the system selects it). The concept is deliberately designed so additional profiles can be added later and, in future, so users could define their own profiles with custom behaviour. A profile *sets* the active mode; it is not itself a mode. Selected via `input_select.sc_active_profile`. NF1 holds: profiles decide the mode, the coordinator only executes it.

**`Auto` profile** — The built-in profile that automatically selects the active mode over time from observable conditions (time of day, SOC, solar forecast, low-tariff flag, departure deadline, home-day flag) and escalates between modes when circumstances demand it — for example, switching from `Solar` to `Captar` when deadline urgency requires grid charging that solar surplus alone cannot satisfy.

**`home-day flag`** — A boolean flag indicating the car will be home during the next day's daylight hours (e.g. a work-from-home day, weekend, or holiday), so it could absorb solar then. While set it enables the solar-reserve cap. Read via an `sc_` helper and reset each day; its source is configurable — set by the evening prompt (R13) or by an external source such as a calendar or presence sensor.

**`solar-reserve cap`** — A configurable lower overnight active SOC limit (default 60 %) applied while the sun is down when the home-day flag is set and the next-day solar forecast exceeds a configurable threshold (default 12 kWh), reserving battery room for the following day's solar; low-tariff grid charging is suppressed while the cap is active.

**`minimum charging current`** — The lowest current the charger may be set to other than 0 A (configurable, default 6 A — the IEC 61851 floor; reference setup: 6 A); enforced by C1.

**`sun is down`** — The condition `sun.sun` state equals `below_horizon`.

### Entity naming convention

**`sc_` prefix** — The namespace prefix on every helper and sensor owned by this integration, following `<domain>.sc_<descriptive_name>` (e.g. `input_number.sc_active_soc`); it prevents collisions with unrelated helpers and makes every smart-charging entity findable in the Home Assistant UI. Raw upstream entities (e.g. `sensor.tesla_batterijniveau`) are never referenced directly — they are always wrapped in an `sc_` sensor.

---

## Out of scope

- **User-defined custom profiles** — letting users author their own profiles with bespoke behaviour is a future capability. The two-layer mode/profile model is designed to make it possible, but no authoring mechanism is provided this release.
- **EV battery-capacity lookup** — a built-in database (vendor/model/variant → capacity) or external API to populate battery capacity automatically is deferred; for now capacity is configured or read from a sensor (R15).
- **Three-phase support** — all calculations assume single-phase this release (see Hardware context); three-phase is deferred.
- **Home battery integration** — deferred. The capability model (R18) is deliberately designed to accommodate a future home-battery capability, but no battery-aware behaviour ships this release.
