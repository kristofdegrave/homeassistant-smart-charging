# Entity catalog

The single source of truth for every entity this integration owns, every config-entry value it
reads, and every [adapter role](system-overview.md#ubiquitous-language) through which it reaches
hardware I/O (NF3). Per [ADR-0004](../adl/0004-owned-vs-mapped-entities.md), the integration's
owned **control and diagnostic** entities are **native platform entities** under the
`smart_charging_` prefix (e.g. `select.smart_charging_profile`,
`sensor.smart_charging_active_mode`), following the
[entity-naming convention](system-overview.md#entity-naming-convention). Per
[ADR-0005](../adl/0005-config-entry-structure-and-interval.md) (Accepted), declared capabilities
(R18) and every install-time threshold, default, or the control interval are **not** entities at
all: they live in the config entry as **data** (capabilities — set at initial setup, changed only
via the reconfigure flow) or **options** (thresholds/defaults/control interval — changeable
anytime via Configure), and this catalog lists them by their **config key**, not an entity id (see
Notes). Two runtime helper values remain an open question under ADR-0004 and
keep the legacy `sc_` `input_*` helper-entity form for now (see Notes). The
[glossary](system-overview.md#ubiquitous-language) stays authoritative for each
term's **meaning**; this catalog is authoritative for each entity's, config key's, or role's
**binding** — its id/key or role name, unit, default/range, and which behaviour reads or writes
it.

Entities and adapter roles are organized by **configuration area** (General · EV · Solar ·
Notification · Deadline / urgency), each divided into functional subgroups. A subgroup lists
every row of that concern regardless of role; the **Role** column distinguishes them.

**How to read it:**

- **Role** — `config` (a user-set entity — a native owned entity, or one of the two
  still-open legacy `sc_` runtime helpers, see Notes), `config-data` / `config-options` (a
  config-entry value per ADR-0005 — a declared capability or an install-time threshold/default —
  with **no entity id at all**), `adapter role` (an internal, code-level role that reads or writes
  one piece of hardware I/O; mapped to the user's real upstream entity during config flow — not an
  HA entity itself, NF3), or `state` (a value the system itself maintains, or that the user sets
  directly, on a real owned HA entity — e.g. the mode selector or a diagnostic readout). Owned
  control/diagnostic entities are native `smart_charging_`-prefixed platform entities.
- **Setup** — for a `config` or `state` row the user sets directly, whether it is
  [install-time or runtime configuration](system-overview.md#ubiquitous-language) (R19); for a
  `config-data` / `config-options` row, the config-entry bucket itself (`data` or `options`, ADR-0005)
  stands in for this classification, since R19's install-time/runtime axis applies to entities. Like
  install-time configuration, a `config-data`/`config-options` row is never presented on the runtime
  dashboard (R19) — it is reached only through the config or reconfigure flow.
  `—` marks `adapter role` rows (a code-level mapping, not a catalogued entity) and `state` rows
  that are pure system-computed status (e.g. the monthly peak demand), neither of which carries a
  runtime/install-time classification.
- **Id** — for a `config` or `state` row, the real Home Assistant entity id —
  `smart_charging_`-prefixed for the owned control/diagnostic entities, still legacy `sc_`-prefixed
  for the two open runtime helpers (see Notes); for a `config-data` / `config-options` row, the
  **config key** (no entity id, ADR-0005); for
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
| `solar_available` | config-data | data | — | on (present) | [capability](system-overview.md#ubiquitous-language) — solar (R18) | resolution-rules, UC01, UC02, UC06, (UC07) | user (reconfigure flow) |
| `captar_available` | config-data | data | — | on (present) | [capability](system-overview.md#ubiquitous-language) — CapTar (R18) | resolution-rules, UC03 | user (reconfigure flow) |
| `deadline_available` | config-data | data | — | on (present) | [deadline capability](system-overview.md#ubiquitous-language) (R18) | resolution-rules, UC05, UC07, UC10, UC11 | user (reconfigure flow) |

> Extensible: a future capability (e.g. a home battery) would add one row here and gate its own modes/behaviours (R18, NF2).
>
> **Reconfigure-flow timing note.** R18 requires a capability change to take effect "within the next control cycle." The reconfigure flow reloads the config entry, which restarts the coordinator — the new capability set is therefore in force from the coordinator's first cycle after the reload, satisfying R18 rather than conflicting with it.

### Core & coordinator

| Id | Role | Setup | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `select.smart_charging_profile` | config | runtime | — | `Manual` / `Auto` (default `Manual`) | [profile](system-overview.md#ubiquitous-language) | control-cycle, resolution-rules, UC11 | user, UC11 |
| `control_interval_s` | config-options | options | s | 10 | [control interval](system-overview.md#ubiquitous-language) | control-cycle | user (anytime) |
| `smoothing_window` | config-options | options | cycles | 4 | [smoothed value](system-overview.md#ubiquitous-language) (R10) | control-cycle | user (anytime) |
| `select.smart_charging_mode` | state | runtime | — | `Solar`/`SolarOnly`/`Captar`/`Power`/`Off` | [active mode](system-overview.md#ubiquitous-language) — the `Manual` profile's mode-override selection | control-cycle, UC11 | user (Manual), UC11 |

### Installation

| Id | Role | Setup | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `grid_supply_ceiling_a` | config-options | options | A | 40 (reference setup) | [grid supply ceiling](system-overview.md#ubiquitous-language) (C4) | control-cycle | user (anytime) |
| `grid_safety_offset_a` | config-options | options | A | 2 (larger with solar/battery) | [grid safety offset](system-overview.md#ubiquitous-language) (C4) | control-cycle | user (anytime) |
| `nominal_voltage_v` | config-options | options | V | 230 | [supply voltage](system-overview.md#ubiquitous-language) fallback (NF4) | control-cycle | user (anytime) |
| `grid_voltage` | adapter role | — | V | mapped to the installation's grid voltage sensor (NF3) | [supply voltage](system-overview.md#ubiquitous-language) measured value (NF4) | control-cycle | — |
| `net_power` | adapter role | — | W | mapped to the installation's grid net-power meter (NF3) | [net import](system-overview.md#ubiquitous-language) | control-cycle, UC01, UC02, UC11 | — |
| `low_tariff` | adapter role | — | bool | mapped to the installation's tariff signal (NF3; optional — treated as always `on` when not configured — single-tariff installation) | [low-tariff flag](system-overview.md#ubiquitous-language) | resolution-rules | — |

> `Read by` lists only behaviours that read a value **directly**. `net_power` (and `charger_power` below) are read directly by UC01/UC02, whose set-point rule converges the smoothed value toward 0 W. `Captar` (UC03) references net import only through the R3 peak clamp in `control-cycle.md` (already listed), not as a direct read, so UC03 is deliberately absent here.

### Charger

| Id | Role | Setup | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `min_current_a` | config-options | options | A | 6 (IEC 61851 floor) | [minimum charging current](system-overview.md#ubiquitous-language) (C1) | control-cycle, UC01, UC02, UC03, UC04 | user (anytime) |
| `max_current_a` | config-options | options | A | 32 | [maximum charging current](system-overview.md#ubiquitous-language) (C1) | control-cycle, UC01, UC02, UC03, UC04, UC05 | user (anytime) |
| `charger_power` | adapter role | — | W | mapped to the charger's power sensor (NF3) | charger power (operand of [solar surplus](system-overview.md#ubiquitous-language)) | control-cycle, UC01, UC02, UC11 | — |
| `charger_status` | adapter role | — | enum | mapped to the charger's connection-state entity, with a user-supplied state-translation table (NF3) | [charger status](system-overview.md#ubiquitous-language) (`disconnected`/`connected`/`charging`) | control-cycle, UC01, UC02, UC03, UC04, UC05, UC08, UC09, UC10, UC11 | — |
| `charger_current` | adapter role (read/write) | — | A | 0 or 6–32; mapped to the charger's current set-point entity (NF3) | charger current set-point output (C1, NF3) | UC11 (reads back the current set-point for display) | control-cycle |

### Peak protection

| Id | Role | Setup | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `safety_margin_w` | config-options | options | W | 250 | [safety margin](system-overview.md#ubiquitous-language) | control-cycle | user (anytime) |
| `max_peak_kw` | config-options | options | kW | 4 (defaults to inverter ceiling) | [maximum peak](system-overview.md#ubiquitous-language) | resolution-rules | user (anytime) |
| `peak_grace_min` | config-options | options | min | 2 | R3 peak-breach grace period | control-cycle | user (anytime) |
| `sensor.smart_charging_monthly_peak_kw` | state | — | kW | derived from the `net_power` adapter role over the month | [monthly peak demand](system-overview.md#ubiquitous-language) | resolution-rules | — |
| `captar_cooldown_min` | config-options | options | min | 10 | `Captar`-mode cooldown (R11) | UC03 | user (anytime) |

### `Power` mode

| Id | Role | Setup | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `input_number.sc_power_target_current_a` | config | runtime | A | 10 (min–max charging current) | [Power target current](system-overview.md#ubiquitous-language) (R17) | UC04, UC11 | user, UC11 |
| `power_respect_peak` | config-options | options | — | on | `Power` peak-protection option (R17) | UC04 | user (anytime) |
| `power_cooldown_min` | config-options | options | min | 10 | `Power`-mode cooldown (R11) | UC04 | user (anytime) |

### Diagnostic outputs

System-written native `sensor` entities (ADR-0004) that surface, as read-only diagnostic readouts, values the coordinator computes each cycle. They are exposed for observability; they are still computed each cycle, not stored config helpers.

| Id | Role | Setup | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `sensor.smart_charging_active_mode` | state | — | — | resolved active mode: equals `select.smart_charging_mode` under `Manual`, `Auto`'s selection under `Auto` | [active mode](system-overview.md#ubiquitous-language) — the resolved value in effect | UC11 | control-cycle (resolved from the `Manual` selector or `Auto` selection) |
| `sensor.smart_charging_desired_current` | state | — | A | the active mode module's desired charger current, before the peak/grid clamps | desired charger current (control-cycle step 4) | (UC11) | control-cycle |
| `sensor.smart_charging_effective_peak_limit` | state | — | kW | `min(monthly_peak_demand, maximum_peak)`, raised to the maximum peak during urgency (R5); resolved per `resolution-rules.md` | [effective peak limit](system-overview.md#ubiquitous-language) | (UC11) | control-cycle |
| `sensor.smart_charging_active_soc_limit` | state | — | % | resolved active SOC limit per `resolution-rules.md` (Active SOC limit table): solar-reserve cap → solar step-up → default; the entity `ActiveSocLimitChanged` fires on (ADR-0011) | [active SOC limit](system-overview.md#ubiquitous-language) — the resolved value in effect | UC09, (UC11) | control-cycle |
| `sensor.smart_charging_status` | state | — | — | `OK` / `Fault` (ADR-0007) | integration health status (ADR-0007) | (UC11) | control-cycle |
| `sensor.smart_charging_solar_surplus_w` | state | — | W | `charger_power − net_power`, computed fresh each control cycle, never stored | [solar surplus](system-overview.md#ubiquitous-language) | UC11 | control-cycle |
| `sensor.smart_charging_time_to_full` | state | — | min | derived from EV battery capacity (R15), `ev_soc`, the active SOC limit, and the current `charger_current` set-point; unavailable while `charger_current` is 0 A, zero once state of charge is at or above the active SOC limit | [time to full charge](system-overview.md#ubiquitous-language) | (UC11) | control-cycle |
| `sensor.smart_charging_peak_headroom_a` | state | — | A | `(effective peak limit − safety margin − net import) ÷ supply voltage`, the same raw-reading target the R3 peak-protection clamp holds; resolved per `control-cycle.md` step 5 (the effective peak limit itself is resolved per `resolution-rules.md`) | [peak headroom](system-overview.md#ubiquitous-language) | (UC11) | control-cycle |
| `sensor.smart_charging_adapter_readings` | state | — | — | state is the timestamp of the last successful control-cycle read; `extra_state_attributes` hold one key per currently-wired *read* adapter role, `None` when that role's own reading is unavailable (ADR-0007 semantics), without the entity itself becoming unavailable; per ADR-0021 | adapter-role readings, dashboard-bindable (ADR-0021) | (UC11) | control-cycle |

---

## EV configuration

### SOC & battery

| Id | Role | Setup | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `number.smart_charging_soc_limit_override` | config | runtime | % | 80 (50–100) | [active SOC limit](system-overview.md#ubiquitous-language) default (R6) | resolution-rules, UC09, UC11 | user, UC09 (manual-change adoption), UC11 |
| `ev_battery_capacity_kwh` | config-options | options | kWh | 75 | EV battery capacity (R15) | resolution-rules, control-cycle | user (anytime) |
| `ev_soc` | adapter role | — | % | mapped to the vehicle's state-of-charge sensor (NF3) | state of charge | control-cycle, resolution-rules, UC01, UC02, UC03, UC04, UC05, UC06, (UC11) | — |
| `ev_battery_capacity` | adapter role | — | kWh | mapped to the vehicle's capacity sensor, when available (optional, NF3) | EV battery capacity, sensed (R15) | resolution-rules, control-cycle | — |
| `car_home` | adapter role | — | bool | mapped to a presence / device-tracker entity (NF3) | car-at-home presence (R12) | UC09 | — |
| `vehicle_charge_limit` | adapter role (read/write) | — | % | mirrors active SOC limit; mapped to the vehicle's charge-limit entity (NF3) | vehicle charge-limit output role (R6, NF3) | UC09 | UC09 |

---

## Solar configuration

*All rows in this area are conditional on the solar capability (`solar_available`, R18); when it is off they are not required.*

### `Solar` mode

| Id | Role | Setup | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `solar_start_threshold_w` | config-options | options | W | 150 | [solar start threshold](system-overview.md#ubiquitous-language) (R1) | UC01 | user (anytime) |
| `solar_hold_min` | config-options | options | min | 5 | [post-surplus hold](system-overview.md#ubiquitous-language) (R1) | UC01 | user (anytime) |
| `solar_cooldown_min` | config-options | options | min | 2 | [solar-mode cooldown](system-overview.md#ubiquitous-language) (R11) — shared with `SolarOnly` | UC01, UC02 | user (anytime) |
| `solar_power` | adapter role | — | W | mapped to the installation's solar production sensor (NF3) | solar production reading (smoothed per R10; not an operand of [solar surplus](system-overview.md#ubiquitous-language), which is `charger_w − net_w`) | control-cycle | — |

### `SolarOnly` mode

| Id | Role | Setup | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `solar_only_start_threshold_w` | config-options | options | W | 1300 | [solar start threshold](system-overview.md#ubiquitous-language) — SolarOnly instance (R2) | UC02 | user (anytime) |
| `solar_only_rounding_strategy` | config-options | options | — | `round_down` / `round_up` / `nearest` (= round to nearest) (default `round_down`) | [amp-step rounding](system-overview.md#ubiquitous-language) strategy (R2) | UC02 | user (anytime) |
| `solar_only_rounding_midpoint_pct` | config-options | options | % | 50 (0–100) | [amp-step rounding](system-overview.md#ubiquitous-language) midpoint — `nearest` strategy only (R2) | UC02 | user (anytime) |

Also uses `solar_cooldown_min` (see `Solar` mode) — R11 applies one cooldown to both solar modes.

### Solar SOC step-up

| Id | Role | Setup | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `max_solar_soc` | config-options | options | % | 100 (50–100) | [solar step-up](system-overview.md#ubiquitous-language) ceiling (R8) | resolution-rules, UC06 | user (anytime) |
| `solar_step_pp` | config-options | options | pp | 5 | solar step-up size (R8) | UC06 | user (anytime) |
| `solar_step_threshold_pp` | config-options | options | pp | 2 | solar step-up trigger gap (R8) | UC06 | user (anytime) |

### Solar-reserve cap

| Id | Role | Setup | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `input_number.sc_solar_reserve_soc` | config | runtime | % | 60 | [solar-reserve cap](system-overview.md#ubiquitous-language) (R9) | resolution-rules, UC07, UC11 (omitted when the solar capability is off) | user, UC11 |
| `solar_forecast_threshold_kwh` | config-options | options | kWh | 12 | solar-reserve forecast threshold (R9) | resolution-rules, UC07, UC08 | user (anytime) |
| `solar_forecast` | adapter role | — | kWh | mapped to a next-day forecast source (NF3) | [solar forecast](system-overview.md#ubiquitous-language) | resolution-rules, UC07, UC08, (UC11) | — |

---

## Notification configuration

### Reminders & prompts

| Id | Role | Setup | Unit | Default / range / source | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `prompt_timeout_h` | config-options | options | h | 2 | evening prompt timeout (R13) | — | user (anytime) |
| `reminder_lead_h` | config-options | options | h | 8 | plug-in reminder lead time (R12) | UC10 | user (anytime) |
| `evening_prompt_enabled` | config-options | options | — | on | evening home-day prompt enable (UC08) | UC08 | user (anytime) |
| `evening_prompt_time` | config-options | options | time | 18:00 | evening prompt time (UC08) | UC08 | user (anytime) |
| `binary_sensor.smart_charging_plug_in_reminder` | state | — | bool | `on` while a plug-in reminder is currently due (car home, disconnected, below the active SOC limit, within the lead time of the next departure) | plug-in reminder (R12) | (UC11) | (UC10) |

---

## Deadline / urgency configuration

### Departure times

*All rows in this subgroup are conditional on the [deadline capability](system-overview.md#ubiquitous-language)
(`deadline_available`, R18); when it is off they are neither offered nor required, and no
departure deadline is ever resolved. The Home day subgroup below is **not** gated by it — the
home-day flag also drives the solar-reserve cap (R9).*

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

The home-day flag drives the solar-reserve cap (R9) and, while the deadline capability is present (R18), the home-day departure override (R14). How it is set is deliberately left open (R13) — currently via the evening prompt (UC08) or an external source (NF3).

> **Id note.** ADR-0004 illustratively named this owned switch `switch.smart_charging_wfh`. This catalog deliberately uses `switch.smart_charging_home_day` to match the settled "home-day flag" ubiquitous-language term (broader than work-from-home — also weekends and holidays); the ADR's `wfh` was an illustrative example, not a binding id.

---

## Notes

- **Runtime target vs. install-time/config-entry bound — judgment calls.** Where a value isn't a
  clear-cut match for either of R19's own entity examples, this catalog draws the line as follows:
  an SOC **target** the active-SOC-limit resolution can select as the effective limit
  (`number.smart_charging_soc_limit_override`, `sc_solar_reserve_soc`) is a runtime entity, since
  the household changes what SOC it currently wants and the two remain open under ADR-0004 (see
  below). An SOC **ceiling/bound** on top of a target (`max_solar_soc`, a step-up ceiling, not
  itself selectable as the active limit) is a config-entry **options** value, alongside other
  bounds (`min_current_a`, `max_current_a`) — same reasoning ADR-0005 applies to thresholds
  generally. Likewise, a behavioural/algorithm choice that is set once and rarely revisited
  (`solar_only_rounding_strategy`, `power_respect_peak`, `evening_prompt_enabled`) is a
  config-entry options value, distinct from a value the household dials in for the current session
  (`sc_power_target_current_a`, still an open runtime-entity question under ADR-0004). For values
  ADR-0005's own text does not individually enumerate (e.g. `grid_supply_ceiling_a`,
  `grid_safety_offset_a`, `nominal_voltage_v`), the rule this catalog applies is ADR-0005's own
  Consequences test: does changing the value need to re-validate entity/role resolution? If not,
  it is an options value, regardless of whether it also reads as a set-once installation fact.
- **`sun.sun`** is read directly by `resolution-rules.md` (the [sun is down](system-overview.md#ubiquitous-language)
  condition) and is the one exception to the map-everything rule: it is a Home Assistant platform
  entity, not a device, so NF3 does not require an adapter role for it.
- **The `effective peak limit` and the resolved `active SOC limit` are each now surfaced as a
  diagnostic sensor, but are still computed every cycle; the resolved `departure deadline` still
  has no entity.** Each is resolved every cycle by a rule in `resolution-rules.md` (the effective
  peak limit from `max_peak_kw`/`sensor.smart_charging_monthly_peak_kw`, the active SOC limit
  from the active-SOC-limit inputs, the departure deadline from the departure inputs); they are
  computed values, not stored helpers. The effective peak limit's and the active SOC limit's
  computed values are exposed read-only for observability as
  `sensor.smart_charging_effective_peak_limit` and `sensor.smart_charging_active_soc_limit`
  (Diagnostic outputs) — readouts of the computation, not stored inputs. The active SOC limit's
  readout additionally serves as the entity the `ActiveSocLimitChanged` domain event fires on
  (ADR-0011), the single cross-cycle change signal [UC09](use-cases/UC09-sync-charge-limit-with-car.md)
  consumes to sync the vehicle. If a future use-case needs the resolved departure deadline
  materialized likewise, it would add the row and its references then. The
  [missed-deadline hold](system-overview.md#ubiquitous-language) (R5, `resolution-rules.md`) is
  likewise **deliberately not materialized**, even though [UC07](use-cases/UC07-reserve-capacity-for-tomorrow.md)
  reads it across a use-case boundary: it is coordinator-internal session state with no configuration
  input and no consumer outside the resolution rules, and — unlike the plug-in reminder's de-dup
  condition, whose `binary_sensor` exists for the dashboard (R19) — no requirement asks for it to be
  observable. A future use-case or dashboard row needing it would add the row then.
- **`solar surplus`, `time to full charge`, and `peak headroom` are each now surfaced as a
  diagnostic sensor, added for the UC11 dashboard build (`docs/plans/2026-07-08-runtime-dashboard-design.md`
  Decisions 3–4).** Like the effective peak limit and active SOC limit above, each is computed
  fresh every control cycle, never stored: `sensor.smart_charging_solar_surplus_w` from
  `charger_power − net_power`; `sensor.smart_charging_time_to_full` from the EV battery capacity,
  `ev_soc`, the active SOC limit, and `charger_current`; `sensor.smart_charging_peak_headroom_a`
  from the effective peak limit, safety margin, and net import — the same raw-reading target the
  R3 peak-protection clamp (`control-cycle.md` step 5) holds, converted to amperes via supply
  voltage. None of the three drives a control decision —
  they exist purely for dashboard observability (R19). `charger_current` and `net_power` already
  had `UC11` in their own `Read by` column before this revision (the dashboard's status tiles read
  them back directly), so neither needed a change here.
- **`sensor.smart_charging_adapter_readings`** (ADR-0021) mirrors every currently-wired *read*
  adapter role's current value as an attribute, giving a dashboard something to bind to for
  hardware-I/O values that have no HA entity of their own (adapter roles are code-level, NF3, not
  catalogued entities). Unlike the three sensors above, its own entity row doesn't restate which
  roles it covers — that set is whichever `ROLE_*` constants `adapters/factory.py` wires at a
  given time (ADR-0021's Context), so this catalog would drift the moment a role is added or
  removed if it tried to enumerate them here. Adding `UC11` to a role's own `Read by` column
  (as already done for `ev_soc`/`solar_forecast`, and already present for `charger_power`/
  `charger_status`/`charger_current`/`net_power`) stays reserved for roles the dashboard's status
  tiles actually display directly — the sensor exists for general observability, not only for
  the dashboard, so being one of its mirrored attributes doesn't by itself earn a role a `UC11`
  reference.
- **Output adapter roles (`charger_current`, `vehicle_charge_limit`)** satisfy the NF3 requirement
  that every command crosses an adapter role; a start/stop is expressed as a 0 A set-point on the
  `charger_current` role. Both are read/write: `vehicle_charge_limit` is read back by UC09 to
  detect a change the user made directly on the vehicle (R6), and `charger_current` is read back
  by UC11 to display the currently applied set-point on the dashboard (R19) — neither read-back
  changes the command-only nature of `control-cycle`'s own use of these roles.
- **Solar-dependent entities are conditional on the solar capability (R18).** When
  `solar_available` is off, everything under *Solar configuration* plus the solar sensors is not
  required, and the `Auto` rule skips the solar mode accordingly.
- **Captar-dependent rows are conditional on the CapTar capability (R18).** When
  `captar_available` is off, `captar_cooldown_min` is not required, and the `Auto` rule skips
  `Captar` accordingly.
- **Deadline-dependent rows are conditional on the deadline capability (R18).** When
  `deadline_available` is off, the *Departure times* subgroup and `reminder_lead_h` are not
  required and `binary_sensor.smart_charging_plug_in_reminder` never turns on (R18 is authoritative
  for the full behavioural consequence). Two binding-level notes this catalog is authoritative for:
  `ev_battery_capacity_kwh` / the `ev_battery_capacity` role still resolve but feed nothing that
  affects charging behaviour, since the required-current computation is their only consumer that
  changes a control decision — `sensor.smart_charging_time_to_full` (Diagnostic outputs) also
  reads them, but only to render a display value, never to alter what the coordinator charges at.
  `requirements.md`'s R15/R18 wording ("its only consumer") predates this sensor and is now
  imprecise in the same way; tracked as a wording follow-up for whoever next touches R15/R18,
  not corrected here since this catalog-only change has no mandate to edit requirement text.
  The *Home day* subgroup and
  `evening_prompt_*` are **not** gated, because the home-day flag independently drives the
  solar-reserve cap (R9). Unlike the solar and CapTar capabilities, this one removes no option from
  `select.smart_charging_mode`.
- **The `select.smart_charging_mode` selector offers only the modes available under the current
  capabilities (R18).** Without the solar capability, `Solar` and `SolarOnly` are not offered for
  manual selection; without the CapTar capability, `Captar` is not offered for manual selection.
  `Power` and `Off` are always offered. This is where R18's manual-availability criterion is
  realized (the `Manual` profile itself needs no rule — the user sets the mode directly, and
  `sensor.smart_charging_active_mode` reflects that selection as the resolved active mode).
- The `<dow>` row stands for seven concrete entities
  (`time.smart_charging_departure_mon` … `time.smart_charging_departure_sun`),
  collapsed to keep the table readable.
- **Cross-area entities.** `car_home` (EV) is also read by the plug-in reminder
  (`binary_sensor.smart_charging_plug_in_reminder`, Notification);
  the home-day entities (Deadline / urgency) also drive the solar-reserve cap (R9, Solar); how they
  are set is deliberately left open (R13) — currently via the evening prompt (UC08, Notification) or
  an external source. They are filed under their primary area to avoid duplicate rows.
- **Owned entities vs. config-entry data/options — ADR-0005 resolution.** Per
  [ADR-0004](../adl/0004-owned-vs-mapped-entities.md), only the integration's owned **control and
  diagnostic** entities are native `smart_charging_` platform entities (the
  `select`/`number`/`time`/`switch`/`sensor`/`binary_sensor` rows above). Per
  [ADR-0005](../adl/0005-config-entry-structure-and-interval.md) (Accepted), every declared
  capability (`solar_available`, `captar_available`, `deadline_available`) is config-entry **data**
  — set at initial setup, changed only via the reconfigure flow — and every install-time threshold,
  default, or the control interval (`control_interval_s`, `grid_supply_ceiling_a`, `max_peak_kw`,
  `min_current_a`/`max_current_a`, the `solar_*` thresholds, `prompt_timeout_h`,
  `reminder_lead_h`, `evening_prompt_*`, and the rest of the `config-options` rows above) is
  config-entry **options** — changeable anytime via Configure. Neither bucket has an entity id;
  this catalog lists them by config key instead. Two runtime user-set values remain an **open
  question under ADR-0004** — ADR-0005's Decision text enumerates only mappings/tables/capabilities
  (data) and thresholds/defaults/the control interval (options), and assigns neither of these two;
  they stay a user-set runtime-entity question that ADR-0004's own follow-up owns — and keep the
  legacy `sc_` helper-entity form for now, pending a decision on whether they join the owned-entity
  list: `sc_power_target_current_a`,
  `sc_solar_reserve_soc`.
