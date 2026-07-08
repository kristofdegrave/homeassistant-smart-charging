# Entity catalog

The single source of truth for every `sc_` entity this integration owns (the
[`sc_` prefix](system-overview.md#entity-naming-convention) convention) and every
[adapter role](system-overview.md#ubiquitous-language) through which it reaches hardware I/O
(NF3). The [glossary](system-overview.md#ubiquitous-language) stays authoritative for each
term's **meaning**; this catalog is authoritative for each entity's or role's **binding** — its
id or role name, unit, default/range, and which behaviour reads or writes it.

Entities and adapter roles are organized by **configuration area** (General · EV · Solar ·
Notification · Deadline / urgency), each divided into functional subgroups. A subgroup lists
every row of that concern regardless of role; the **Role** column distinguishes them.

**How to read it:**

- **Role** — `config` (a user-set helper; a real, `sc_`-prefixed HA entity), `adapter role` (an
  internal, code-level role that reads or writes one piece of hardware I/O; mapped to the user's
  real upstream entity during config flow — not an HA entity itself, NF3), or `state` (a value the
  system itself maintains as a real, `sc_`-prefixed HA entity, e.g. the active mode selector).
- **Id** — for a `config` or `state` row, the real Home Assistant entity id (`sc_`-prefixed); for
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

| Id | Role | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- |
| `input_boolean.sc_solar_available` | config | — | on (present) | [capability](system-overview.md#ubiquitous-language) — solar (R18) | resolution-rules, UC01, UC02, UC06, (UC07) | user |

> Extensible: a future capability (e.g. a home battery) would add one row here and gate its own modes/behaviours (R18, NF2).

### Core & coordinator

| Id | Role | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- |
| `input_select.sc_active_profile` | config | — | `Manual` / `Auto` (default `Manual`) | [profile](system-overview.md#ubiquitous-language) | resolution-rules | user |
| `input_number.sc_control_interval_s` | config | s | 10 | [control interval](system-overview.md#ubiquitous-language) | control-cycle | user |
| `input_number.sc_smoothing_window` | config | cycles | 4 | [smoothed value](system-overview.md#ubiquitous-language) (R10) | control-cycle | user |
| `input_select.sc_active_mode` | state | — | `Solar`/`SolarOnly`/`Captar`/`Power`/`Off` | [active mode](system-overview.md#ubiquitous-language) | control-cycle | user (Manual) / Auto profile (R16) |

### Installation

| Id | Role | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- |
| `input_number.sc_grid_supply_ceiling_a` | config | A | 40 (reference setup) | [grid supply ceiling](system-overview.md#ubiquitous-language) (C4) | control-cycle | user |
| `input_number.sc_grid_safety_offset_a` | config | A | 2 (larger with solar/battery) | [grid safety offset](system-overview.md#ubiquitous-language) (C4) | control-cycle | user |
| `input_number.sc_nominal_voltage_v` | config | V | 230 | [supply voltage](system-overview.md#ubiquitous-language) fallback (NF4) | control-cycle | user |
| `grid_voltage` | adapter role | V | mapped to the installation's grid voltage sensor (NF3) | [supply voltage](system-overview.md#ubiquitous-language) measured value (NF4) | control-cycle | — |
| `net_power` | adapter role | W | mapped to the installation's grid net-power meter (NF3) | [net import](system-overview.md#ubiquitous-language) | control-cycle, UC01, UC02 | — |
| `low_tariff` | adapter role | bool | mapped to the installation's tariff signal (NF3; optional — treated as always `on` when not configured — single-tariff installation) | [low-tariff flag](system-overview.md#ubiquitous-language) | resolution-rules | — |

> `Read by` lists only behaviours that read a value **directly**. `net_power` (and `charger_power` below) are read directly by UC01/UC02, whose set-point rule converges the smoothed value toward 0 W. `Captar` (UC03) references net import only through the R3 peak clamp in `control-cycle.md` (already listed), not as a direct read, so UC03 is deliberately absent here.

### Charger

| Id | Role | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- |
| `input_number.sc_min_current_a` | config | A | 6 (IEC 61851 floor) | [minimum charging current](system-overview.md#ubiquitous-language) (C1) | control-cycle, UC01, UC02, UC03, UC04 | user |
| `input_number.sc_max_current_a` | config | A | 32 | [maximum charging current](system-overview.md#ubiquitous-language) (C1) | control-cycle, UC01, UC02, UC03, UC04, UC05 | user |
| `charger_power` | adapter role | W | mapped to the charger's power sensor (NF3) | charger power (operand of [solar surplus](system-overview.md#ubiquitous-language)) | control-cycle, UC01, UC02 | — |
| `charger_status` | adapter role | enum | mapped to the charger's connection-state entity, with a user-supplied state-translation table (NF3) | [charger status](system-overview.md#ubiquitous-language) (`disconnected`/`connected`/`charging`) | control-cycle, UC01, UC02, UC03, UC04, UC05 | — |
| `charger_current` | adapter role (write) | A | 0 or 6–32; mapped to the charger's current set-point entity (NF3) | charger current set-point output (C1, NF3) | — | control-cycle |

### Peak protection

| Id | Role | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- |
| `input_number.sc_safety_margin_w` | config | W | 250 | [safety margin](system-overview.md#ubiquitous-language) | control-cycle | user |
| `input_number.sc_max_peak_kw` | config | kW | 4 (defaults to inverter ceiling) | [maximum peak](system-overview.md#ubiquitous-language) | resolution-rules | user |
| `input_number.sc_peak_grace_min` | config | min | 2 | R3 peak-breach grace period | control-cycle | user |
| `sensor.sc_monthly_peak_kw` | state | kW | derived from the `net_power` adapter role over the month | [monthly peak demand](system-overview.md#ubiquitous-language) | resolution-rules | — |
| `input_number.sc_captar_cooldown_min` | config | min | 10 | `Captar`-mode cooldown (R11) | UC03 | user |

### `Power` mode

| Id | Role | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- |
| `input_number.sc_power_target_current_a` | config | A | 10 (min–max charging current) | [Power target current](system-overview.md#ubiquitous-language) (R17) | UC04 | user |
| `input_boolean.sc_power_respect_peak` | config | — | on | `Power` peak-protection option (R17) | UC04 | user |
| `input_number.sc_power_cooldown_min` | config | min | 10 | `Power`-mode cooldown (R11) | UC04 | user |

---

## EV configuration

### SOC & battery

| Id | Role | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- |
| `input_number.sc_active_soc` | config | % | 80 (50–100) | [active SOC limit](system-overview.md#ubiquitous-language) default (R6) | resolution-rules | user |
| `input_number.sc_battery_capacity_kwh` | config | kWh | 75 | EV battery capacity (R15) | resolution-rules | user |
| `ev_soc` | adapter role | % | mapped to the vehicle's state-of-charge sensor (NF3) | state of charge | control-cycle, resolution-rules, UC01, UC02, UC03, UC04, UC05, UC06 | — |
| `battery_capacity` | adapter role | kWh | mapped to the vehicle's capacity sensor, when available (optional, NF3) | EV battery capacity, sensed (R15) | resolution-rules | — |
| `car_home` | adapter role | bool | mapped to a presence / device-tracker entity (NF3) | car-at-home presence (R12) | — | — |
| `vehicle_charge_limit` | adapter role (write) | % | mirrors active SOC limit; mapped to the vehicle's charge-limit entity (NF3) | vehicle charge-limit output role (R6, NF3) | — | (UC09) |

---

## Solar configuration

*All entities in this area are conditional on the solar capability (`sc_solar_available`, R18); when it is off they are not required.*

### `Solar` mode

| Id | Role | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- |
| `input_number.sc_solar_start_threshold_w` | config | W | 150 | [solar start threshold](system-overview.md#ubiquitous-language) (R1) | UC01 | user |
| `input_number.sc_solar_hold_min` | config | min | 5 | [post-surplus hold](system-overview.md#ubiquitous-language) (R1) | UC01 | user |
| `input_number.sc_solar_cooldown_min` | config | min | 2 | [solar-mode cooldown](system-overview.md#ubiquitous-language) (R11) — shared with `SolarOnly` | UC01, UC02 | user |
| `solar_power` | adapter role | W | mapped to the installation's solar production sensor (NF3) | solar production reading (smoothed per R10; not an operand of [solar surplus](system-overview.md#ubiquitous-language), which is `charger_w − net_w`) | control-cycle | — |

### `SolarOnly` mode

| Id | Role | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- |
| `input_number.sc_solar_only_start_threshold_w` | config | W | 1300 | [solar start threshold](system-overview.md#ubiquitous-language) — SolarOnly instance (R2) | UC02 | user |
| `input_select.sc_solar_only_rounding_strategy` | config | — | `round_down` / `round_up` / `nearest` (= round to nearest) (default `round_down`) | [amp-step rounding](system-overview.md#ubiquitous-language) strategy (R2) | UC02 | user |
| `input_number.sc_solar_only_rounding_midpoint_pct` | config | % | 50 (0–100) | [amp-step rounding](system-overview.md#ubiquitous-language) midpoint — `nearest` strategy only (R2) | UC02 | user |

Also uses `input_number.sc_solar_cooldown_min` (see `Solar` mode) — R11 applies one cooldown to both solar modes.

### Solar SOC step-up

| Id | Role | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- |
| `input_number.sc_max_solar_soc` | config | % | 100 (50–100) | [solar step-up](system-overview.md#ubiquitous-language) ceiling (R8) | resolution-rules, UC06 | user |
| `input_number.sc_solar_step_pp` | config | pp | 5 | solar step-up size (R8) | UC06 | user |
| `input_number.sc_solar_step_threshold_pp` | config | pp | 2 | solar step-up trigger gap (R8) | UC06 | user |

### Solar-reserve cap

| Id | Role | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- |
| `input_number.sc_solar_reserve_soc` | config | % | 60 | [solar-reserve cap](system-overview.md#ubiquitous-language) (R9) | resolution-rules, UC07 | user |
| `input_number.sc_solar_forecast_threshold_kwh` | config | kWh | 12 | solar-reserve forecast threshold (R9) | resolution-rules, UC07 | user |
| `solar_forecast` | adapter role | kWh | mapped to a next-day forecast source (NF3) | [solar forecast](system-overview.md#ubiquitous-language) | resolution-rules, UC07 | — |

---

## Notification configuration

### Reminders & prompts

| Id | Role | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- |
| `input_number.sc_reminder_lead_h` | config | h | 8 | plug-in reminder lead time (R12) | — | user |
| `input_boolean.sc_evening_prompt_enabled` | config | — | on | evening home-day prompt enable (UC08) | — | user |
| `input_datetime.sc_evening_prompt_time` | config | time | 18:00 | evening prompt time (UC08) | — | user |
| `input_number.sc_prompt_timeout_h` | config | h | 2 | evening prompt timeout (UC08) | — | user |

---

## Deadline / urgency configuration

### Departure times

| Id | Role | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- |
| `input_datetime.sc_departure_<dow>` | config | time | 06:00 Mon–Fri; none Sat–Sun | [departure deadline](system-overview.md#ubiquitous-language) day-of-week default (R14) — seven entities, `mon`…`sun` | resolution-rules | user |
| `input_datetime.sc_departure_holiday` | config | time | none | departure public-holiday override (R14) | resolution-rules | user |
| `input_datetime.sc_departure_home_day` | config | time | none | departure home-day override (R14) | resolution-rules | user |
| `departure_external` | adapter role | time | mapped to an external departure-time sensor (NF3) | [departure deadline](system-overview.md#ubiquitous-language) external override (R14) | resolution-rules | — |

### Home day

| Id | Role | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- |
| `home_day_external` | adapter role | bool | mapped to a calendar / presence source (NF3) | external [home-day flag](system-overview.md#ubiquitous-language) source (R13) | resolution-rules | — |
| `input_boolean.sc_home_day` | state | bool | off (resets daily at midnight) | [home-day flag](system-overview.md#ubiquitous-language) (R13) | resolution-rules, UC07 | user (UC08) |

The home-day flag drives the solar-reserve cap (R9) and the home-day departure override (R14). How it is set is deliberately left open (R13) — currently via the evening prompt (UC08) or an external source (NF3).

---

## Notes

- **`sun.sun`** is read directly by `resolution-rules.md` (the [sun is down](system-overview.md#ubiquitous-language)
  condition) and is the one exception to the map-everything rule: it is a Home Assistant platform
  entity, not a device, so NF3 does not require an adapter role for it.
- **`effective peak limit`, the resolved `active SOC limit`, and the resolved `departure deadline`
  have no entity.** Each is resolved every cycle by a rule in `resolution-rules.md` (from
  `sc_max_peak_kw`/`sc_monthly_peak_kw`, from the active-SOC-limit inputs, and from the departure
  inputs respectively); they are computed values, not stored helpers. If a future use-case needs
  one materialized for observability, it would add the row and its references then.
- **Output adapter roles (`charger_current`, `vehicle_charge_limit`)** satisfy the NF3 requirement
  that every command crosses an adapter role; a start/stop is expressed as a 0 A set-point on the
  `charger_current` role.
- **Solar-dependent entities are conditional on the solar capability (R18).** When
  `sc_solar_available` is off, everything under *Solar configuration* plus the solar sensors is not
  required, and the `Auto` rule skips the solar mode accordingly.
- **The `sc_active_mode` selector offers only the modes available under the current capabilities
  (R18).** Without the solar capability, `Solar` and `SolarOnly` are not offered for manual
  selection; `Captar`, `Power`, and `Off` are always offered. This is where R18's manual-availability
  criterion is realized (the `Manual` profile itself needs no rule — the user sets the mode directly).
- The `<dow>` row stands for seven concrete entities (`sc_departure_mon` … `sc_departure_sun`),
  collapsed to keep the table readable.
- **Cross-area entities.** `car_home` (EV) is also read by the plug-in reminder;
  the home-day entities (Deadline / urgency) also drive the solar-reserve cap (R9, Solar); how they
  are set is deliberately left open (R13) — currently via the evening prompt (UC08, Notification) or
  an external source. They are filed under their primary area to avoid duplicate rows.
