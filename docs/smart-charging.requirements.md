# Smart Charging v3

## Hardware context

The following hardware constraints are relevant to this feature. Full inventory in [`spec/SYSTEM.md`](../SYSTEM.md).

| Component | Relevant constraint |
|---|---|
| Grid connection | Single-phase 230V, 40A |
| Alfen Eve Single Pro | 1-phase, 32A licence → max 7.4 kW charging |
| Tesla Model 3 LR Dual Motor | ~75 kWh usable battery |
| SMA SunnyBoy 4000TL-21 | 4.68 kWp panels, 4 kW inverter ceiling |

All power/current calculations in this spec assume single-phase 230V.

---

## Stakeholders

| Stakeholder | Role | Expectations | Concerns |
|---|---|---|---|
| EV driver | Needs the car charged and ready before departure | Car charged to target SOC before departure; plug-in reminder if forgotten | Car not ready on time; charging stops unexpectedly |
| Household energy manager | Manages household energy consumption, solar production usage, and cost | Electricity cost minimised; solar surplus fully used; CapTar peak kept under control | Monthly peak spike; cheap tariff windows missed; unnecessary grid charging; solar surplus wasted |
| System maintainer | Developer and operator of the HA/Node-RED configuration | Observable behavior; easy to debug when something goes wrong; safe to deploy changes | Silent failures (wrong sensor value, automation not triggering); hard-to-trace Node-RED logic; breaking changes after HA updates |

All three roles are currently filled by the same person, but keeping them separate makes explicit that **convenience**, **cost**, and **maintainability** are distinct concerns that can pull in different directions.

---

## Problem statement

Charging an electric vehicle without intelligence draws power from the grid at full speed regardless of solar production, electricity tariff, or monthly peak demand — maximising cost and CapTar impact.

The goal of the smart charging system is to **charge the car at the lowest possible cost** by:

1. **Maximising solar self-consumption** — solar power is always the cheapest source and should be used first
2. **Keeping the monthly peak demand low** — Belgian CapTar billing charges on peak demand, so every unnecessary peak directly increases the bill
3. **Charging during the cheapest grid tariff windows** — when solar is not available, the system uses low-tariff periods rather than peak-tariff periods

The car must always be charged to its target state of charge before the configured departure time.

---

## Goals

1. Use as much solar power as possible — solar is always the cheapest source.
2. Keep the monthly peak (capacity tariff) under control.
3. Charge cost-efficiently by preferring cheap tariff windows when grid charging is needed.
4. Charge the car to its target SOC within the available time window, cost-efficiently.

---

## Constraints

These are hard rules that must never be violated, regardless of mode or circumstance.

| # | Constraint |
|---|---|
| C1 | Charging current is always 0A or 6–32A — values of 1–5A cause Tesla charging errors and must never be sent |
| C2 | Charge limit changes only happen when the car is at home — no remote limit adjustments |
| C3 | Charging must not push net import above the effective peak limit. The effective peak limit is the lower of the current monthly peak demand and 4 kW. The charger does not use headroom created by household appliances. The absolute floor during urgency (R5) is 3.5 kW. |

---

## Definitions

**Solar surplus (W):** `charger_w − net_w`, where `charger_w` is the charger's measured output power and `net_w` is net grid import (positive = importing, negative = exporting). A positive result means solar is contributing to the charger's consumption.

**`charger_w_delta` (W):** The change in charger power that would result from a proposed current adjustment: `(candidate_amps − current_amps) × 230`. Used in R3 to project whether raising the set-point would breach the effective peak limit.

**Effective peak limit (kW):** `min(monthly_peak_demand, 4 kW)`. During urgency (R5) the floor is raised to 3.5 kW — meaning if the effective peak limit would fall below 3.5 kW, 3.5 kW is used instead.

**Minimum charging current:** 6A (IEC 61851 minimum; enforced by C1).

**`sensor.sc_ev_soc`:** The EV's current state of charge in integer percent. This is a template sensor that wraps the raw Tesla integration entity (`sensor.tesla_batterijniveau`), rounding to integer and applying the `battery` device class. All automations and integrations must reference `sensor.sc_ev_soc` — never the raw Tesla entity directly.

**`input_boolean.sc_wfh_tomorrow`:** Stores the user's work-from-home answer from the R2c actionable notification. Set to `on` when the user confirms WFH via the mobile notification; resets to `off` at midnight daily. If the user does not respond within 2 hours (by 20:00), the system treats it as `off`.

**`input_select.sc_active_profile`:** The shared helper that controls which charging mode is active. Valid states:

| Value | Meaning |
|---|---|
| `Solar` | Charge from solar surplus ≥ 150 W; grid fallback allowed |
| `SolarOnly` | Charge from solar surplus ≥ 1300 W only; no grid fallback |
| `Captar` | Charge within peak limit; prefer cheap-tariff windows |
| `Power` | Charge at a fixed configured current; no solar or CapTar rules |
| `Off` | Charging disabled; charger set to 0A |

**Sun is down:** `sun.sun` state is `below_horizon`.

---

## Requirements

### R1 — Solar-first charging

The behaviour differs by solar mode:

| Mode | Start threshold (smoothed surplus) | Grid fallback |
|---|---|---|
| Solar | ≥ 150 W | Allowed — charges at minimum 6A even if surplus is below 6A equivalent |
| SolarOnly | ≥ 1300 W (≈ 5.65A; proxy for sustaining 6A from solar alone) | Not allowed — charger stops if surplus drops below threshold |

In both modes the system shall set the charger current to the maximum value that keeps net import at or below 0 W (fully self-consumed), rounded down to the nearest integer ampere, subject to C1 and C3.

Solar surplus always takes priority over grid charging — the system shall never reduce charger current below what solar surplus supports in order to shift load to the grid.

**Acceptance criteria:**

- **Solar:** When smoothed solar surplus ≥ 150 W, charging starts within one control cycle (≤10 s) unless a cooldown or stop condition (R7) prevents it.
- **SolarOnly:** When smoothed solar surplus ≥ 1300 W, charging starts within one control cycle (≤10 s) unless a cooldown or stop condition (R7) prevents it. When surplus drops below 1300 W, the charger stops immediately (no 5-minute hold).
- **Solar:** When smoothed solar surplus drops to 0 W, the system holds minimum current for 5 minutes before stopping (R7).
- The charger current never pushes net import above 0 W while in either solar mode, except within sensor noise bounds (±1 reading cycle).

---

### R2 — Target SOC management

#### R2a — Default target

The default charge limit is configurable (`input_number.sc_active_soc`, range 50–100%, default 80%).

#### R2b — Solar step-up

When solar charging is active and the car's SOC comes within 2% of the current charge limit, the system shall raise the limit by 5 percentage points, up to a configurable maximum (`input_number.sc_max_solar_soc`, range 80–100%, default 100%).

If raising by 5% would exceed `sc_max_solar_soc`, the limit is set to `sc_max_solar_soc` and no further step-ups occur.

When the car's SOC reaches `sc_max_solar_soc`, the charger stops (0A). No further charging occurs until the car disconnects or the mode changes.

Examples:
- SOC reaches 78% while limit is 80% → limit becomes 85%
- SOC reaches 83% while limit is 85% → limit becomes 90%
- … up to `sc_max_solar_soc`

**Cooldown:** Minimum 10 minutes between consecutive step-ups. Prevents rapid cycling when SOC reading fluctuates around the threshold.

**Revert conditions** (snap back to default target `sc_active_soc`):
- Car disconnects
- Charging mode switches to Captar

Switching between Solar and SolarOnly does not revert the step-up — both are solar modes and the raised limit remains valid.

#### R2c — Work-from-home solar reservation

If the user will work from home the next day and the solar forecast is sufficient, night charging is capped to leave room for solar charging during the day.

**Detection:**

- At **18:00** each evening, a mobile notification asks whether the user will work from home tomorrow.
- User answers yes/no via actionable notification. A "yes" sets `input_boolean.sc_wfh_tomorrow` to `on`.
- If the user does not respond within **2 hours** (by 20:00), `input_boolean.sc_wfh_tomorrow` remains `off` and no cap is applied.
- `input_boolean.sc_wfh_tomorrow` resets to `off` at midnight daily.

**Conditions to activate:**

- User answered yes (WFH tomorrow)
- Solar forecast for tomorrow > **12 kWh**

**Effect:**

- Night charge ceiling = **60%** — active from sunset (`sun.sun` = `below_horizon`) until sunrise the next day.
- The cap persists all night including during cheap tariff — the intent is to leave room for solar the next day.
- During the day, the cap is lifted and normal solar logic (R2a/R2b) applies.
- The WFH flag resets at 00:00 and the notification fires again each evening.

**Interaction with grid charging:**

- When WFH reservation is active, cheap-tariff grid charging is suppressed at night.
- Urgency (R5) overrides this — if the car genuinely cannot make the deadline, grid charging is still used.

#### R2d — Active SOC limit

The effective charge limit at any moment resolves in this priority order:

| Priority | Condition | Value |
|---|---|---|
| 1 | WFH reservation active and `sun.sun` = `below_horizon` | 60% (night cap) |
| 2 | Solar step-up in effect | Stepped-up value (85%–100%) |
| 3 | Default | `sc_active_soc` (default 80%) |

The WFH cap only applies at night. During the day, solar logic (R2a/R2b) takes over regardless of WFH reservation.

---

### R3 — Monthly peak management

The system shall limit the charger current so that `net_w + charger_w_delta` does not exceed the effective peak limit (as defined in the Definitions section and C3).

This check shall use **raw (unsmoothed)** sensor values — smoothed values (R6) must not be used here, because smoothing introduces lag that can allow a peak breach to persist for up to one smoothing window (40 s).

**Acceptance criteria:**

- In any 10-second control cycle, the charger current set-point never results in net import exceeding the effective peak limit, based on the most recent raw sensor reading.
- When the effective peak limit would be breached at the minimum charging current (6A), the charger is stopped immediately (0A).

---

### R4 — Cost-efficient grid charging

**Grid charging mode** is active only when solar surplus is 0 W — meaning the charger is running entirely on grid power with no solar contribution. Partial solar coverage (e.g. solar covers 3A of a 6A session) is handled within Solar/SolarOnly mode and does not trigger grid charging mode; the system simply maximises the solar contribution at the current set-point.

When grid charging mode is active, the system selects the cheapest available source in priority order:

| Priority | Source | Condition |
|---|---|---|
| 1 | Solar surplus | Always preferred |
| 2 | Cheap tariff window (weekdays 22:00–07:00, weekends all day) | Only when WFH reservation is not active |
| 3 | Peak tariff | Only if urgency (R5) demands it |

When no charging source is available or permitted, the charger outputs 0A.

---

### R5 — Deadline override

If the car cannot reach its active SOC limit by the configured departure time at the **current charger output** (A × 230V), the system shall increase the charging current to the minimum value that makes the deadline reachable, subject to C1 and C3.

**Required current calculation:**

`active_soc_limit` is the **active SOC limit (R2d)**. `current_soc` is read from `sensor.sc_ev_soc` (see Definitions). `ev_battery_capacity_kwh` is read from `input_number.sc_ev_battery_capacity_kwh` (R9).

```text
energy_needed_kwh = (active_soc_limit - current_soc) / 100 × ev_battery_capacity_kwh
hours_remaining   = (departure_datetime - now).total_seconds() / 3600
required_power_kw = energy_needed_kwh / hours_remaining
required_amps     = ceil(required_power_kw × 1000 / 230)
```

The system sets the charger to `max(required_amps, 6)`, capped at `min(32, peak_headroom_amps)` (C3).

If the required current exceeds the peak headroom even at minimum (6A), the system charges at 6A and emits a warning — it cannot guarantee the deadline.

**Additional rules:**

- Peak tariff is acceptable during deadline override.
- The effective peak limit (C3) is never violated, even during override.
- The WFH reservation cap is **not** bypassed — if the active SOC limit is 60% (WFH night cap), urgency only escalates current to reach 60%, not 80%. The cap sets the target; urgency only accelerates the current to meet it.

---

### R6 — Sensor smoothing

Net power (`net_w`) and solar power (`solar_w`) readings shall be smoothed using a rolling average over the last **4 readings** (~40 seconds at 10-second poll rate) before use in charging current calculations (R1, R4, R5).

Smoothing shall be bypassed for peak protection decisions (R3) — raw sensor values apply there.

**Acceptance criteria:**

- A sudden 500 W spike in `net_w` lasting one reading cycle (10 s) does not change the charger set-point.
- A sustained 500 W change in `net_w` lasting 40 s does change the charger set-point within the next control cycle.

---

### R7 — Hysteresis / rapid cycling prevention

To prevent Tesla charging errors from rapid start/stop cycles:

| Event | Solar / SolarOnly | Captar |
|---|---|---|
| First plug-in → start | Immediate | Immediate |
| Restart after stop → start | 2 min of smoothed surplus ≥ 230 W | Wait 2 min |
| Stop condition met | Hold at 6A for 5 min, then stop | Stop immediately (0A) |
| After stop → restart allowed | After 2 min cooldown | After 10 min cooldown |

**Mode transitions:** When the active profile changes (e.g. Solar → Captar), all R7 timers reset. The incoming mode starts fresh — no hold periods or cooldowns are inherited from the outgoing mode.

**Stop conditions:**

- Solar: stop when smoothed solar surplus drops to 0 W (charger is fully grid-fed). Hold at 6A for 5 minutes first to ride out cloud cover.
- SolarOnly: stop immediately when smoothed solar surplus drops below 1300 W. No hold period — grid fallback is not permitted in this mode.
- Captar: stop immediately when net import at current set-point would breach the effective peak limit (C3).

**Rationale:** Solar holds for 5 minutes to ride out cloud cover; SolarOnly stops immediately because grid fallback is explicitly excluded; Captar stops immediately because waiting increases the monthly peak further.

The 10-minute Captar cooldown must always run to completion — it may not be shortened even if conditions change (e.g. cheap tariff window starts during the cooldown). Its purpose is to prevent the Tesla from entering a charging error state due to rapid start/stop cycles, not to align with any tariff window. The DSO measures peak demand over 15-minute windows, so a 10-minute cooldown ensures at most one Captar session per measurement window.

---

### R8 — Proactive plug-in reminder

The system shall send a single mobile notification when all of the following conditions are met simultaneously:

- The car is at home (`device_tracker` state = `home`)
- The charger is not connected (no vehicle detected)
- Car SOC is below the active SOC target (R2d)
- The current time is within the first control cycle where `now >= departure_time − 8h` (i.e. the first poll at or past the 8-hour mark, not an exact match)

**Deduplication:** If a notification was already sent for the current departure window and the car is still not connected, no repeat notification is sent until the car has been connected and disconnected again (i.e. the condition resets on connection).

**Purpose:** Catches the "forgot to plug in" scenario. Complements the watchdog that covers "plugged in but not charging".

---

### R9 — Configurable departure times

Default departure times are configurable rather than hardcoded:

| Setting | Entity | Default | Description |
|---|---|---|---|
| Weekday departure | `input_datetime.sc_departure_time_weekday` | 06:00 | Typical weekday departure time |
| Weekend/holiday departure | `input_datetime.sc_departure_time_weekend` | 10:00 | Typical weekend departure time |
| EV battery capacity | `input_number.sc_ev_battery_capacity_kwh` | 75 | Usable battery capacity in kWh — used by R5 deadline calculation |

The system shall use the weekday departure time on Monday–Friday and the weekend departure time on Saturday, Sunday, and public holidays.

---

## Non-functional requirements

### NF1 — Mode selection is owned by HA, not the integration

The active charging mode is communicated to the integration via `input_select.sc_active_profile`. The integration coordinator reads this helper and delegates to the corresponding flow module; it shall contain no mode-selection logic itself.

**Out of scope:** The HA automation or script that decides *when* to switch modes (based on time, SOC, solar forecast, WFH flag, departure time, etc.) is not part of this integration. It is a separate HA configuration concern.

**Rationale:** Keeping mode-selection logic out of the integration means the integration only needs to know how to execute a given mode — not when to use it. This makes the integration simpler to test and decoupled from household-specific scheduling decisions.

### NF2 — One module per charging mode

Each charging mode shall be implemented as a separate, self-contained Python module under `custom_components/smart_charging/flow/`. Cross-mode logic inside a single module is not permitted.

The four modes and their modules:

| Mode | Module | Behaviour |
|---|---|---|
| Solar | `flow/solar.py` | Charge from solar surplus ≥ 150 W; grid fallback allowed at minimum current |
| SolarOnly | `flow/solar_only.py` | Charge from solar surplus ≥ 1300 W only; no grid fallback |
| Captar | `flow/captar.py` | Charge within peak limit; cheap-tariff windows preferred |
| Power | `flow/power.py` | Charge at a configured fixed current (e.g. 15A); no solar or CapTar rules apply |

**Rationale:** A per-mode module is simpler to read, test, and replace independently. A single monolithic module with nested branches for all modes has been the primary maintainability problem in v2.

**Acceptance criteria:**

- `flow/` contains exactly four modules, one per mode as listed above.
- The coordinator reads `input_select.sc_active_profile` and calls the corresponding module — it contains no charging current logic itself.
- Each module contains no references to another module's logic.

---

## Out of scope (this integration)

- Mode-selection automation — the HA automation that decides when to switch `input_select.sc_active_profile` is a separate HA configuration concern (see NF1).
- `Eco` mode (fully automatic day→Solar, night→Captar) — deferred; covered by the mode-selection automation when it is built.

## Future scope

- Public holiday awareness for R9 — departure time currently uses weekday/weekend only; public holiday detection deferred until a calendar source is agreed.
