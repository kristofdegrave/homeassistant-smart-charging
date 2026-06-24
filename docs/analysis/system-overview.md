# Smart Charging v3 — System Overview

*Created: 2026-06-24*

---

## Purpose of this document

This document sets the context for the smart charging system: who it serves, what problem it solves, what hardware it runs on, and what success looks like. All subsequent analysis documents build on the definitions established here.

---

## Hardware context

All power and current calculations in this system assume **single-phase 230 V**.

| Component | Specification | Constraint |
|-----------|---------------|------------|
| Grid connection | Single-phase, 230 V, 40 A | Maximum 9.2 kW grid draw |
| EV charger | Alfen Eve Single Pro-line, 1-phase, 32 A licence | Maximum 7.4 kW charging output |
| Electric vehicle | Tesla Model 3 LR Dual Motor | ~75 kWh usable battery |
| Solar inverter | SMA SunnyBoy 4000TL-21, 4.68 kWp panels | 4 kW inverter output ceiling |

The solar inverter ceiling (4 kW) and charger maximum (7.4 kW) together mean the charger can be fully solar-powered only at the inverter peak, and partial solar coverage is the common case.

---

## Stakeholders

| Stakeholder | Role | Primary concern |
|-------------|------|-----------------|
| EV driver | Needs the car charged and ready before each departure | Car reaches target SOC before configured departure time; plug-in reminder if forgotten |
| Household energy manager | Manages electricity cost, solar self-consumption, and monthly peak demand | Electricity cost minimised; solar surplus fully used; CapTar peak kept low |
| System maintainer | Develops, deploys, and operates the HA integration | Observable behaviour; safe to change; clear failure modes |

All three roles are currently filled by the same person. They are kept separate because **convenience**, **cost**, and **maintainability** are distinct concerns that can and do pull in different directions. An analysis that conflates them risks optimising for one at the expense of another.

---

## Problem statement

An unmanaged EV charger draws at full rated power from the grid regardless of:

- how much solar is being produced at that moment
- whether the current time is in a cheap or expensive tariff window
- what the household's monthly peak demand already is

This maximises electricity cost and CapTar impact. The problem is not that EV charging is expensive — it is that it is *unnecessarily* expensive because it is blind to conditions that could make it cheaper.

---

## Goals

The system has four goals, in priority order:

1. **Maximise solar self-consumption.** Solar power is always the cheapest available source. The system should use as much solar surplus as the charger can absorb before drawing from the grid.

2. **Protect the monthly CapTar peak.** Belgian capacity tariff billing charges on the highest 15-minute average import recorded in the month. Every unnecessary peak directly and permanently raises the monthly bill.

3. **Charge cost-efficiently when grid charging is unavoidable.** When solar is insufficient, the system should prefer cheap-tariff windows (weekday nights, weekends) over peak-tariff periods.

4. **Always meet the departure SOC target.** The car must reach its configured state-of-charge target before the configured departure time, regardless of which charging strategy is in effect.

Goals 1–3 concern cost. Goal 4 is a reliability constraint: the cost optimisation strategy must not leave the driver with an underpowered car.

---

## Charging profiles

The system operates in one of five named profiles at any given time. The active profile is set externally via `input_select.sc_active_profile` — the integration executes the selected profile but does not choose between them (see Out of scope).

| Profile | Behaviour summary |
|---------|-------------------|
| `Solar` | Charge when solar surplus ≥ 150 W; grid fallback allowed at minimum current |
| `SolarOnly` | Charge only when solar surplus ≥ 1300 W; no grid fallback |
| `Captar` | Charge within peak limit during cheap-tariff windows |
| `Power` | Charge at a fixed configured current; no solar or peak rules |
| `Off` | Charging disabled; charger set to 0 A |

---

## Key entities

All integration entities follow the `sc_` naming convention. Raw hardware entities (Tesla integration, Alfen charger) are never referenced directly — always accessed through `sc_` wrapper sensors.

| Entity | Type | Purpose |
|--------|------|---------|
| `sensor.sc_ev_soc` | Sensor | EV state of charge (0–100 %); wraps raw Tesla entity |
| `sensor.sc_charger_status` | Sensor | Normalised charger state: `disconnected` / `connected` / `charging` |
| `input_select.sc_active_profile` | Input select | Active charging profile; read each control cycle |
| `input_boolean.sc_wfh_tomorrow` | Input boolean | Work-from-home flag; set by evening notification |
| `input_number.sc_active_soc` | Input number | Default charge target SOC (50–100 %, default 80 %) |
| `input_number.sc_max_solar_soc` | Input number | Maximum SOC the solar step-up may reach (80–100 %, default 100 %) |
| `input_number.sc_ev_battery_capacity_kwh` | Input number | Usable battery capacity in kWh (default 75) |
| `input_datetime.sc_departure_time_weekday` | Input datetime | Departure time Monday–Friday (default 06:00) |
| `input_datetime.sc_departure_time_weekend` | Input datetime | Departure time Saturday–Sunday (default 10:00) |
| `input_number.sc_control_interval_s` | Input number | Coordinator poll interval in seconds (default 10) |
| `input_number.sc_power_mode_amps` | Input number | Fixed charging current for Power profile (6–32 A, default 15) |

---

## Key terms

**Solar surplus (W):** `charger_w − net_w`, where `net_w` is net grid import (positive = importing, negative = exporting). A positive surplus means solar is covering part or all of the charger's load.

**Effective peak limit (kW):** `min(monthly_peak_demand_kw, 4)`. During deadline urgency, the floor is raised to 3.5 kW — if the effective limit would fall below 3.5 kW, 3.5 kW is used instead.

**Active SOC limit (%):** The charge target in effect at a given moment. Resolves in this priority order: WFH night cap (60 %) → solar step-up value → default target (`sc_active_soc`).

**Control cycle:** One execution of the coordinator loop. Runs every `sc_control_interval_s` seconds (default: 10 s). All timing expressed as a number of cycles in the flow documents resolves to `n × control_interval` seconds at runtime.

---

## Hard constraints

These rules can never be violated, regardless of profile, urgency, or any other condition.

| ID | Constraint |
|----|------------|
| C1 | Charging current is always 0 A or 6–32 A. Values of 1–5 A cause Tesla charging errors and must never be sent. |
| C2 | Charge limit changes only happen when the car is at home. No remote limit adjustments. |
| C3 | The charger must never push net grid import above the effective peak limit. This check uses raw (unsmoothed) sensor values. |

---

## Out of scope

- **Profile selection automation.** The HA automation or script that decides *when* to switch `input_select.sc_active_profile` (based on time, SOC, solar forecast, WFH status, departure time) is a separate HA configuration concern. The integration only executes the selected profile.
- **Eco mode.** A fully automatic day→Solar / night→Captar mode is deferred. When built, it will be implemented as a profile-selection automation, not as a new profile inside the integration.
- **Public holiday awareness.** Departure time currently selects weekday vs. weekend only. Public holiday detection is deferred until a calendar source is agreed.
- **Multi-charger support.** The integration is designed for one charger on one single-phase circuit.
