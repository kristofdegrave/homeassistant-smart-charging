# Entity catalog

The single source of truth for every entity this integration owns and every
[adapter role](system-overview.md#ubiquitous-language) through which it reaches hardware I/O
(NF3). Per [ADR-0004](../adl/0004-owned-vs-mapped-entities.md), the integration's owned
**control and diagnostic** entities are **native platform entities** under the
`smart_charging_` prefix (e.g. `select.smart_charging_profile`,
`sensor.smart_charging_active_mode`), following the
[entity-naming convention](system-overview.md#entity-naming-convention); the remaining
**install-time / tuning** helper rows are still `input_*` helper entities under the legacy
`sc_` prefix, pending the separate ADR-0005 reconciliation (see Notes). The
[glossary](system-overview.md#ubiquitous-language) stays authoritative for each
term's **meaning**; this catalog is authoritative for each entity's or role's **binding** — its
id or role name, unit, default/range, and which behaviour reads or writes it.

Entities and adapter roles are organized by **configuration area** (General · EV · Solar ·
Notification · Deadline / urgency), each divided into functional subgroups. A subgroup lists
every row of that concern regardless of role; the **Role** column distinguishes them.

**How to read it:**

- **Role** — `config` (a user-set helper entity), `adapter role` (an
  internal, code-level role that reads or writes one piece of hardware I/O; mapped to the user's
  real upstream entity during config flow — not an HA entity itself, NF3), or `state` (a value the
  system itself maintains, or that the user sets directly, on a real owned HA entity — e.g. the
  mode selector or a diagnostic readout). Owned control/diagnostic entities are native
  `smart_charging_`-prefixed platform entities; the install-time/tuning helpers remain
  `input_*.sc_*` (see preamble and Notes).
- **Setup** — whether the row is [install-time or runtime configuration](system-overview.md#ubiquitous-language)
  (R19): every `config` row gets a classification, as does a `state` row the user sets directly
  (e.g. the active mode selector, the home-day flag); `—` marks `adapter role` rows (a code-level
  mapping, not a catalogued entity) and `state` rows that are pure system-computed status
  (e.g. the monthly peak demand), neither of which carries a runtime/install-time classification.
- **Id** — for a `config` or `state` row, the real Home Assistant entity id —
  `smart_charging_`-prefixed for the owned control/diagnostic entities, still `sc_`-prefixed for
  the install-time/tuning helpers pending ADR-0005; for
  an `adapter role` row, the internal role name — it names a code-level role, not an HA entity.
- **Default / range / source** — for a `config` row, its default and range; for an `adapter role`
  row, the upstream entity or source it is mapped to (NF3); for a `state` row, the value's range
  or how it is derived.
- **Realizes** — the glossary term the entity or role binds; where a parameter has no dedicated
  glossary term, the requirement that defines it (e.g. R1) is cited instead. The catalog never
  re-defines a term — it links to it.
- **Read by / Written by** — the mechanism docs and use-cases that touch the entity or role
  (bidirectional traceability). Seeded here from the committed `control-cycle.md` and
  `resolution-rules.md`; each use-case task fills in its own references as it lands. `user` /
  `external` denote a human or an external source (calendar, app, vehicle) rather than a document.
  A name in **parentheses**, e.g. `(UC09)`, is a placeholder marking the use-case expected to add
  that reference — it is not yet a current reference.
- Raw upstream entities are **never** catalog rows — an `adapter role` row names the upstream
  entity/source only as the mapping target, not as an owned identifier. The one platform entity
  used directly is `sun.sun` (see notes); it is not a device, so NF3 does not require an adapter
  role for it.
- Ids, role names, and defaults not already fixed in the glossary are **assigned here** and become
  canonical; defaults match the values stated in `requirements.md`.

Internal bookkeeping that is pure implementation — cooldown/hold timers, the smoothing ring
buffer, reminder/prompt "already-sent" flags, restart-after-power-loss persistence — is **not**
catalogued (it is "how", per the design doc). The catalog covers the configurable parameters, the
device-I/O adapter roles, and the domain-level state and outputs the use-cases reference by name.

---

## General configuration

### Capabilities

| Id | Role | Setup | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `input_boolean.sc_solar_available` | config | install-time | — | on (present) | [capability](system-overview.md#ubiquitous-language) — solar (R18) | resolution-rules, UC01, UC02, UC06, (UC07) | user |

> Extensible: a future capability (e.g. a home battery) would add one row here and gate its own modes/behaviours (R18, NF2).

### Core & coordinator

| Id | Role | Setup | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `select.smart_charging_profile` | config | runtime | — | `Manual` / `Auto` (default `Manual`) | [profile](system-overview.md#ubiquitous-language) | control-cycle, resolution-rules, UC11 | user, UC11 |
| `input_number.sc_control_interval_s` | config | install-time | s | 10 | [control interval](system-overview.md#ubiquitous-language) | control-cycle | user |
| `input_number.sc_smoothing_window` | config | install-time | cycles | 4 | [smoothed value](system-overview.md#ubiquitous-language) (R10) | control-cycle | user |
| `select.smart_charging_mode` | state | runtime | — | `Solar`/`SolarOnly`/`Captar`/`Power`/`Off` | [active mode](system-overview.md#ubiquitous-language) — the `Manual` profile's mode-override selection | control-cycle, UC11 | user (Manual), UC11 |

### Installation

| Id | Role | Setup | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `input_number.sc_grid_supply_ceiling_a` | config | install-time | A | 40 (reference setup) | [grid supply ceiling](system-overview.md#ubiquitous-language) (C4) | control-cycle | user |
| `input_number.sc_grid_safety_offset_a` | config | install-time | A | 2 (larger with solar/battery) | [grid safety offset](system-overview.md#ubiquitous-language) (C4) | control-cycle | user |
| `input_number.sc_nominal_voltage_v` | config | install-time | V | 230 | [supply voltage](system-overview.md#ubiquitous-language) fallback (NF4) | control-cycle | user |
| `grid_voltage` | adapter role | — | V | mapped to the installation's grid voltage sensor (NF3) | [supply voltage](system-overview.md#ubiquitous-language) measured value (NF4) | control-cycle | — |
| `net_power` | adapter role | — | W | mapped to the installation's grid net-power meter (NF3) | [net import](system-overview.md#ubiquitous-language) | control-cycle, UC01, UC02, UC11 | — |
| `low_tariff` | adapter role | — | bool | mapped to the installation's tariff signal (NF3; optional — treated as always `on` when not configured — single-tariff installation) | [low-tariff flag](system-overview.md#ubiquitous-language) | resolution-rules | — |

> `Read by` lists only behaviours that read a value **directly**. `net_power` (and `charger_power` below) are read directly by UC01/UC02, whose set-point rule converges the smoothed value toward 0 W. `Captar` (UC03) references net import only through the R3 peak clamp in `control-cycle.md` (already listed), not as a direct read, so UC03 is deliberately absent here.

### Charger

| Id | Role | Setup | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `input_number.sc_min_current_a` | config | install-time | A | 6 (IEC 61851 floor) | [minimum charging current](system-overview.md#ubiquitous-language) (C1) | control-cycle, UC01, UC02, UC03, UC04 | user |
| `input_number.sc_max_current_a` | config | install-time | A | 32 | [maximum charging current](system-overview.md#ubiquitous-language) (C1) | control-cycle, UC01, UC02, UC03, UC04, UC05 | user |
| `charger_power` | adapter role | — | W | mapped to the charger's power sensor (NF3) | charger power (operand of [solar surplus](system-overview.md#ubiquitous-language)) | control-cycle, UC01, UC02, UC11 | — |
| `charger_status` | adapter role | — | enum | mapped to the charger's connection-state entity, with a user-supplied state-translation table (NF3) | [charger status](system-overview.md#ubiquitous-language) (`disconnected`/`connected`/`charging`) | control-cycle, UC01, UC02, UC03, UC04, UC05, UC08, UC09, UC10, UC11 | — |
| `charger_current` | adapter role (read/write) | — | A | 0 or 6–32; mapped to the charger's current set-point entity (NF3) | charger current set-point output (C1, NF3) | UC11 (reads back the current set-point for display) | control-cycle |

### Peak protection

| Id | Role | Setup | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `input_number.sc_safety_margin_w` | config | install-time | W | 250 | [safety margin](system-overview.md#ubiquitous-language) | control-cycle | user |
| `input_number.sc_max_peak_kw` | config | install-time | kW | 4 (defaults to inverter ceiling) | [maximum peak](system-overview.md#ubiquitous-language) | resolution-rules | user |
| `input_number.sc_peak_grace_min` | config | install-time | min | 2 | R3 peak-breach grace period | control-cycle | user |
| `sensor.smart_charging_monthly_peak_kw` | state | — | kW | derived from the `net_power` adapter role over the month | [monthly peak demand](system-overview.md#ubiquitous-language) | resolution-rules | — |
| `input_number.sc_captar_cooldown_min` | config | install-time | min | 10 | `Captar`-mode cooldown (R11) | UC03 | user |

### `Power` mode

| Id | Role | Setup | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `input_number.sc_power_target_current_a` | config | runtime | A | 10 (min–max charging current) | [Power target current](system-overview.md#ubiquitous-language) (R17) | UC04, UC11 | user, UC11 |
| `input_boolean.sc_power_respect_peak` | config | install-time | — | on | `Power` peak-protection option (R17) | UC04 | user |
| `input_number.sc_power_cooldown_min` | config | install-time | min | 10 | `Power`-mode cooldown (R11) | UC04 | user |

### Diagnostic outputs

System-written native `sensor` entities (ADR-0004) that surface, as read-only diagnostic readouts, values the coordinator computes each cycle. They are exposed for observability; they are still computed each cycle, not stored config helpers.

| Id | Role | Setup | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `sensor.smart_charging_active_mode` | state | — | — | resolved active mode: equals `select.smart_charging_mode` under `Manual`, `Auto`'s selection under `Auto` | [active mode](system-overview.md#ubiquitous-language) — the resolved value in effect | UC11 | control-cycle (resolved from the `Manual` selector or `Auto` selection) |
| `sensor.smart_charging_desired_current` | state | — | A | the active mode module's desired charger current, before the peak/grid clamps | desired charger current (control-cycle step 4) | (UC11) | control-cycle |
| `sensor.smart_charging_effective_peak_limit` | state | — | kW | `min(monthly_peak_demand, maximum_peak)`, raised to the maximum peak during urgency (R5); resolved per `resolution-rules.md` | [effective peak limit](system-overview.md#ubiquitous-language) | (UC11) | control-cycle |
| `sensor.smart_charging_status` | state | — | — | `OK` / `Fault` (ADR-0007) | integration health status (ADR-0007) | (UC11) | control-cycle |

---

## EV configuration

### SOC & battery

| Id | Role | Setup | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `number.smart_charging_soc_limit_override` | config | runtime | % | 80 (50–100) | [active SOC limit](system-overview.md#ubiquitous-language) default (R6) | resolution-rules, UC09, UC11 | user, UC09 (manual-change adoption), UC11 |
| `input_number.sc_battery_capacity_kwh` | config | install-time | kWh | 75 | EV battery capacity (R15) | resolution-rules | user |
| `ev_soc` | adapter role | — | % | mapped to the vehicle's state-of-charge sensor (NF3) | state of charge | control-cycle, resolution-rules, UC01, UC02, UC03, UC04, UC05, UC06 | — |
| `battery_capacity` | adapter role | — | kWh | mapped to the vehicle's capacity sensor, when available (optional, NF3) | EV battery capacity, sensed (R15) | resolution-rules | — |
| `car_home` | adapter role | — | bool | mapped to a presence / device-tracker entity (NF3) | car-at-home presence (R12) | UC09 | — |
| `vehicle_charge_limit` | adapter role (read/write) | — | % | mirrors active SOC limit; mapped to the vehicle's charge-limit entity (NF3) | vehicle charge-limit output role (R6, NF3) | UC09 | UC09 |

---

## Solar configuration

*All entities in this area are conditional on the solar capability (`sc_solar_available`, R18); when it is off they are not required.*

### `Solar` mode

| Id | Role | Setup | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `input_number.sc_solar_start_threshold_w` | config | install-time | W | 150 | [solar start threshold](system-overview.md#ubiquitous-language) (R1) | UC01 | user |
| `input_number.sc_solar_hold_min` | config | install-time | min | 5 | [post-surplus hold](system-overview.md#ubiquitous-language) (R1) | UC01 | user |
| `input_number.sc_solar_cooldown_min` | config | install-time | min | 2 | [solar-mode cooldown](system-overview.md#ubiquitous-language) (R11) — shared with `SolarOnly` | UC01, UC02 | user |
| `solar_power` | adapter role | — | W | mapped to the installation's solar production sensor (NF3) | solar production reading (smoothed per R10; not an operand of [solar surplus](system-overview.md#ubiquitous-language), which is `charger_w − net_w`) | control-cycle | — |

### `SolarOnly` mode

| Id | Role | Setup | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `input_number.sc_solar_only_start_threshold_w` | config | install-time | W | 1300 | [solar start threshold](system-overview.md#ubiquitous-language) — SolarOnly instance (R2) | UC02 | user |
| `input_select.sc_solar_only_rounding_strategy` | config | install-time | — | `round_down` / `round_up` / `nearest` (= round to nearest) (default `round_down`) | [amp-step rounding](system-overview.md#ubiquitous-language) strategy (R2) | UC02 | user |
| `input_number.sc_solar_only_rounding_midpoint_pct` | config | install-time | % | 50 (0–100) | [amp-step rounding](system-overview.md#ubiquitous-language) midpoint — `nearest` strategy only (R2) | UC02 | user |

Also uses `input_number.sc_solar_cooldown_min` (see `Solar` mode) — R11 applies one cooldown to both solar modes.

### Solar SOC step-up

| Id | Role | Setup | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `input_number.sc_max_solar_soc` | config | install-time | % | 100 (50–100) | [solar step-up](system-overview.md#ubiquitous-language) ceiling (R8) | resolution-rules, UC06 | user |
| `input_number.sc_solar_step_pp` | config | install-time | pp | 5 | solar step-up size (R8) | UC06 | user |
| `input_number.sc_solar_step_threshold_pp` | config | install-time | pp | 2 | solar step-up trigger gap (R8) | UC06 | user |

### Solar-reserve cap

| Id | Role | Setup | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `input_number.sc_solar_reserve_soc` | config | runtime | % | 60 | [solar-reserve cap](system-overview.md#ubiquitous-language) (R9) | resolution-rules, UC07, UC11 (omitted when the solar capability is off) | user, UC11 |
| `input_number.sc_solar_forecast_threshold_kwh` | config | install-time | kWh | 12 | solar-reserve forecast threshold (R9) | resolution-rules, UC07, UC08 | user |
| `solar_forecast` | adapter role | — | kWh | mapped to a next-day forecast source (NF3) | [solar forecast](system-overview.md#ubiquitous-language) | resolution-rules, UC07, UC08 | — |

---

## Notification configuration

### Reminders & prompts

| Id | Role | Setup | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `input_number.sc_prompt_timeout_h` | config | install-time | h | 2 | evening prompt timeout (R13) | — | user |
| `input_number.sc_reminder_lead_h` | config | install-time | h | 8 | plug-in reminder lead time (R12) | UC10 | user |
| `input_boolean.sc_evening_prompt_enabled` | config | install-time | — | on | evening home-day prompt enable (UC08) | UC08 | user |
| `input_datetime.sc_evening_prompt_time` | config | install-time | time | 18:00 | evening prompt time (UC08) | UC08 | user |
| `binary_sensor.smart_charging_plug_in_reminder` | state | — | bool | `on` while a plug-in reminder is currently due (car home, disconnected, below the active SOC limit, within the lead time of the next departure) | plug-in reminder (R12) | (UC11) | (UC10) |

---

## Deadline / urgency configuration

### Departure times

| Id | Role | Setup | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `time.smart_charging_departure_<dow>` | config | runtime | time | 06:00 Mon–Fri; none Sat–Sun | [departure deadline](system-overview.md#ubiquitous-language) day-of-week default (R14) — seven entities, `mon`…`sun` | resolution-rules, UC11 | user, UC11 |
| `time.smart_charging_departure_holiday` | config | runtime | time | none | departure public-holiday override (R14) | resolution-rules, UC11 | user, UC11 |
| `time.smart_charging_departure_home_day` | config | runtime | time | none | departure home-day override (R14) | resolution-rules, UC11 | user, UC11 |
| `departure_external` | adapter role | — | time | mapped to an external departure-time sensor (NF3) | [departure deadline](system-overview.md#ubiquitous-language) external override (R14) | resolution-rules | — |

### Home day

| Id | Role | Setup | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `home_day_external` | adapter role | — | bool | mapped to a calendar / presence source (NF3) | external [home-day flag](system-overview.md#ubiquitous-language) source (R9, R13) | resolution-rules, UC08 | — |
| `switch.smart_charging_home_day` | state | runtime | bool | off (resets daily at midnight) | [home-day flag](system-overview.md#ubiquitous-language) | resolution-rules, UC08, UC11 | UC08, UC11 |

The home-day flag drives the solar-reserve cap (R9) and the home-day departure override (R14). How it is set is deliberately left open (R13) — currently via the evening prompt (UC08) or an external source (NF3).

> **Id note.** ADR-0004 illustratively named this owned switch `switch.smart_charging_wfh`. This catalog deliberately uses `switch.smart_charging_home_day` to match the settled "home-day flag" ubiquitous-language term (broader than work-from-home — also weekends and holidays); the ADR's `wfh` was an illustrative example, not a binding id.

---

## Notes

- **Runtime vs. install-time judgment calls.** Where a `config` entity isn't a clear-cut match for
  either of R19's own examples, this catalog draws the line as follows: an SOC **target** the
  active-SOC-limit resolution can select as the effective limit
  (`number.smart_charging_soc_limit_override`,
  `sc_solar_reserve_soc`) is runtime, since the household changes what SOC it currently wants;
  an SOC **ceiling/bound** on top of a target (`sc_max_solar_soc`, a step-up ceiling, not itself
  selectable as the active limit) is install-time, alongside other bounds (`sc_min_current_a`,
  `sc_max_current_a`). Likewise, a behavioural/algorithm choice that is set once and rarely
  revisited (`sc_solar_only_rounding_strategy`, `sc_power_respect_peak`,
  `sc_evening_prompt_enabled`) is install-time, distinct from a value the household dials in for
  the current session (`sc_power_target_current_a`).
- **`sun.sun`** is read directly by `resolution-rules.md` (the [sun is down](system-overview.md#ubiquitous-language)
  condition) and is the one exception to the map-everything rule: it is a Home Assistant platform
  entity, not a device, so NF3 does not require an adapter role for it.
- **The `effective peak limit` is now surfaced as a diagnostic sensor, but is still computed
  every cycle; the resolved `active SOC limit` and resolved `departure deadline` still have no
  entity.** Each is resolved every cycle by a rule in `resolution-rules.md` (the effective peak
  limit from `sc_max_peak_kw`/`sensor.smart_charging_monthly_peak_kw`, the active SOC limit from
  the active-SOC-limit inputs, the departure deadline from the departure inputs); they are computed
  values, not stored helpers. The effective peak limit's computed value is exposed read-only for
  observability as `sensor.smart_charging_effective_peak_limit` (Diagnostic outputs) — a readout of
  the computation, not a stored input. If a future use-case needs the resolved active SOC limit or
  departure deadline materialized likewise, it would add the row and its references then.
- **Output adapter roles (`charger_current`, `vehicle_charge_limit`)** satisfy the NF3 requirement
  that every command crosses an adapter role; a start/stop is expressed as a 0 A set-point on the
  `charger_current` role. Both are read/write: `vehicle_charge_limit` is read back by UC09 to
  detect a change the user made directly on the vehicle (R6), and `charger_current` is read back
  by UC11 to display the currently applied set-point on the dashboard (R19) — neither read-back
  changes the command-only nature of `control-cycle`'s own use of these roles.
- **Solar-dependent entities are conditional on the solar capability (R18).** When
  `sc_solar_available` is off, everything under *Solar configuration* plus the solar sensors is not
  required, and the `Auto` rule skips the solar mode accordingly.
- **The `select.smart_charging_mode` selector offers only the modes available under the current
  capabilities (R18).** Without the solar capability, `Solar` and `SolarOnly` are not offered for
  manual selection; `Captar`, `Power`, and `Off` are always offered. This is where R18's
  manual-availability criterion is realized (the `Manual` profile itself needs no rule — the user
  sets the mode directly, and `sensor.smart_charging_active_mode` reflects that selection as the
  resolved active mode).
- The `<dow>` row stands for seven concrete entities
  (`time.smart_charging_departure_mon` … `time.smart_charging_departure_sun`),
  collapsed to keep the table readable.
- **Cross-area entities.** `car_home` (EV) is also read by the plug-in reminder
  (`binary_sensor.smart_charging_plug_in_reminder`, Notification);
  the home-day entities (Deadline / urgency) also drive the solar-reserve cap (R9, Solar); how they
  are set is deliberately left open (R13) — currently via the evening prompt (UC08, Notification) or
  an external source. They are filed under their primary area to avoid duplicate rows.
- **Owned entities vs. install-time/tuning helpers — ADR-0005 follow-up.** This catalog revision
  (per ADR-0004) moved only the integration's owned **control and diagnostic** entities to native
  `smart_charging_` platform entities (the `select`/`number`/`time`/`switch`/`sensor`/`binary_sensor`
  rows above). Every install-time / tuning threshold and the capability flag are **unchanged here**
  and stay as `input_*.sc_*` helpers (e.g. `sc_solar_available`, `sc_control_interval_s`,
  `sc_grid_supply_ceiling_a`, `sc_max_peak_kw`, `sc_min_current_a`/`sc_max_current_a`, the
  `sc_solar_*` thresholds, `sc_prompt_timeout_h`, `sc_reminder_lead_h`, `sc_evening_prompt_*`).
  A few runtime user-set values also intentionally stay `sc_` for now because ADR-0004 does not
  enumerate them among the owned native entities — `sc_power_target_current_a`,
  `sc_solar_reserve_soc`. Whether any of these helper rows should instead become config-entry
  data/options rather than entities is a **separate ADR-0005 catalog reconciliation, tracked
  separately** — it is out of scope for this revision.
