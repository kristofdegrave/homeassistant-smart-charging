# Entity catalog

The single source of truth for every `sc_` entity (the [`sc_` prefix](system-overview.md#entity-naming-convention)
convention). The [glossary](system-overview.md#ubiquitous-language) stays authoritative for each
term's **meaning**; this catalog is authoritative for each entity's **binding** — its id, role,
unit, default/range, and which behaviour reads or writes it.

**How to read it:**

- **Role** — `config` (a user-set helper), `sensor` (wraps an upstream device/source entity per
  NF3), or `state` (a value the system itself maintains, including the output wrappers it writes).
- **Realizes** — the glossary term the entity binds; where a parameter has no dedicated glossary
  term, the requirement that defines it (e.g. R1) is cited instead. The catalog never re-defines a
  term — it links to it.
- **Read by / Written by** — the mechanism docs and use-cases that touch the entity (bidirectional
  traceability). Seeded here from the committed `control-cycle.md` and `resolution-rules.md`; each
  use-case task fills in its own references as it lands. `user` / `external` denote a human or an
  external source (calendar, app, vehicle) rather than a document. A name in **parentheses**, e.g.
  `(UC09)`, is a placeholder marking the use-case expected to add that reference — it is not yet a
  current reference.
- Raw upstream entities are **never** catalog rows — they appear only as the *source* noted on a
  `sensor`-role wrapper. The one platform entity used directly is `sun.sun` (see notes); it is not
  a device, so NF3 does not require a wrapper.
- Ids and defaults not already fixed in the glossary are **assigned here** and become canonical;
  defaults match the values stated in `requirements.md`.

Internal bookkeeping that is pure implementation — cooldown/hold timers, the smoothing ring
buffer, reminder/prompt "already-sent" flags, restart-after-power-loss persistence — is **not**
catalogued (it is "how", per the design doc). The catalog covers the configurable parameters, the
device-I/O wrappers, and the domain-level state and outputs the use-cases reference by name.

---

## Config entities (user-set)

Every entity in this section is `config` role, so the Role column is omitted here; entities are
grouped by functional concern.

### Core & coordinator

| Entity id | Domain | Unit | Default / range | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- |
| `input_select.sc_active_profile` | input_select | — | `Manual` / `Auto` (default `Manual`) | [profile](system-overview.md#ubiquitous-language) | resolution-rules | user |
| `input_number.sc_control_interval_s` | input_number | s | 10 | [control interval](system-overview.md#ubiquitous-language) | control-cycle | user |
| `input_number.sc_smoothing_window` | input_number | cycles | 4 | [smoothed value](system-overview.md#ubiquitous-language) (R10) | control-cycle | user |
| `input_number.sc_nominal_voltage_v` | input_number | V | 230 | [supply voltage](system-overview.md#ubiquitous-language) fallback (NF4) | control-cycle | user |

### Charger current & peak protection

| Entity id | Domain | Unit | Default / range | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- |
| `input_number.sc_min_current_a` | input_number | A | 6 (IEC 61851 floor) | [minimum charging current](system-overview.md#ubiquitous-language) (C1) | control-cycle | user |
| `input_number.sc_max_current_a` | input_number | A | 32 | charger current range, max (C1) | control-cycle | user |
| `input_number.sc_safety_margin_w` | input_number | W | no default specified | [safety margin](system-overview.md#ubiquitous-language) | control-cycle | user |
| `input_number.sc_max_peak_kw` | input_number | kW | 4 (defaults to inverter ceiling) | [maximum peak](system-overview.md#ubiquitous-language) | resolution-rules | user |
| `input_number.sc_peak_grace_min` | input_number | min | 2 | R3 peak-breach grace period | control-cycle | user |

### SOC & battery

| Entity id | Domain | Unit | Default / range | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- |
| `input_number.sc_active_soc` | input_number | % | 80 (50–100) | [active SOC limit](system-overview.md#ubiquitous-language) default (R6) | resolution-rules | user |
| `input_number.sc_battery_capacity_kwh` | input_number | kWh | 75 | EV battery capacity (R15) | — | user |

### Charging modes (Solar · SolarOnly · CapTar · Power)

| Entity id | Domain | Unit | Default / range | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- |
| `input_number.sc_solar_start_threshold_w` | input_number | W | 150 | Solar start threshold (R1) | — | user |
| `input_number.sc_solar_hold_min` | input_number | min | 5 | Solar post-surplus hold (R1) | — | user |
| `input_number.sc_solar_cooldown_min` | input_number | min | 2 | Solar-mode cooldown (R11) | — | user |
| `input_number.sc_solar_only_start_threshold_w` | input_number | W | 1300 | SolarOnly start threshold (R2) | — | user |
| `input_number.sc_captar_cooldown_min` | input_number | min | 10 | `Captar`-mode cooldown (R11) | — | user |
| `input_boolean.sc_power_respect_peak` | input_boolean | — | on | `Power` peak-protection option (R17) | — | user |

### Solar SOC step-up

| Entity id | Domain | Unit | Default / range | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- |
| `input_number.sc_max_solar_soc` | input_number | % | 100 (50–100) | [solar step-up](system-overview.md#ubiquitous-language) ceiling (R8) | resolution-rules | user |
| `input_number.sc_solar_step_pp` | input_number | pp | 5 | solar step-up size (R8) | — | user |
| `input_number.sc_solar_step_threshold_pp` | input_number | pp | 2 | solar step-up trigger gap (R8) | — | user |
| `input_number.sc_solar_step_interval_min` | input_number | min | 10 | solar step-up min interval (R8) | — | user |

### Solar-reserve cap

| Entity id | Domain | Unit | Default / range | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- |
| `input_number.sc_solar_reserve_soc` | input_number | % | 60 | [solar-reserve cap](system-overview.md#ubiquitous-language) (R9) | resolution-rules | user |
| `input_number.sc_solar_forecast_threshold_kwh` | input_number | kWh | 12 | solar-reserve forecast threshold (R9) | resolution-rules | user |

### Departure times

| Entity id | Domain | Unit | Default / range | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- |
| `input_datetime.sc_departure_<dow>` | input_datetime | time | 06:00 Mon–Fri; none Sat–Sun | [departure deadline](system-overview.md#ubiquitous-language) day-of-week default (R14) — seven entities, `mon`…`sun` | resolution-rules | user |
| `input_datetime.sc_departure_holiday` | input_datetime | time | none | departure public-holiday override (R14) | resolution-rules | user |
| `input_datetime.sc_departure_home_day` | input_datetime | time | none | departure home-day override (R14) | resolution-rules | user |

### Reminders & prompts

| Entity id | Domain | Unit | Default / range | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- |
| `input_number.sc_reminder_lead_h` | input_number | h | 8 | plug-in reminder lead time (R12) | — | user |
| `input_boolean.sc_evening_prompt_enabled` | input_boolean | — | on | evening home-day prompt enable (R13) | — | user |
| `input_datetime.sc_evening_prompt_time` | input_datetime | time | 18:00 | evening prompt time (R13) | — | user |
| `input_number.sc_prompt_timeout_h` | input_number | h | 2 | evening prompt timeout (R13) | — | user |

---

## Sensor entities (wrap an upstream source — NF3)

| Entity id | Domain | Role | Unit | Source (upstream wrapped) | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `sensor.sc_net_power_w` | sensor | sensor | W | grid net-power meter | [net import](system-overview.md#ubiquitous-language) | control-cycle | — |
| `sensor.sc_solar_power_w` | sensor | sensor | W | solar production sensor | solar power (operand of [solar surplus](system-overview.md#ubiquitous-language)) | control-cycle | — |
| `sensor.sc_charger_power_w` | sensor | sensor | W | charger power sensor | charger power (operand of [solar surplus](system-overview.md#ubiquitous-language)) | control-cycle | — |
| `sensor.sc_grid_voltage_v` | sensor | sensor | V | grid voltage sensor | [supply voltage](system-overview.md#ubiquitous-language) measured value (NF4) | control-cycle | — |
| `sensor.sc_charger_status` | sensor | sensor | enum | charger connection state | [charger status](system-overview.md#ubiquitous-language) (`disconnected`/`connected`/`charging`) | control-cycle | — |
| `sensor.sc_ev_soc` | sensor | sensor | % | vehicle state-of-charge sensor | state of charge | control-cycle, resolution-rules | — |
| `sensor.sc_monthly_peak_kw` | sensor | sensor | kW | derived from `sc_net_power_w` over the month | [monthly peak demand](system-overview.md#ubiquitous-language) | resolution-rules | — |
| `binary_sensor.sc_low_tariff` | binary_sensor | sensor | bool | installation tariff signal | [low-tariff flag](system-overview.md#ubiquitous-language) | resolution-rules | — |
| `sensor.sc_solar_forecast_kwh` | sensor | sensor | kWh | next-day forecast source (NF3) | [solar forecast](system-overview.md#ubiquitous-language) | resolution-rules | — |
| `binary_sensor.sc_car_home` | binary_sensor | sensor | bool | presence / device-tracker | car-at-home presence (R12) | — | — |
| `sensor.sc_departure_external` | sensor | sensor | time | external departure-time sensor (NF3) | [departure deadline](system-overview.md#ubiquitous-language) external override (R14) | resolution-rules | — |
| `binary_sensor.sc_home_day_external` | binary_sensor | sensor | bool | calendar / presence source (NF3) | external [home-day flag](system-overview.md#ubiquitous-language) source (R9, R13) | resolution-rules | — |
| `sensor.sc_battery_capacity_kwh` | sensor | sensor | kWh | vehicle capacity sensor (optional, NF3) | EV battery capacity, sensed (R15) | — | — |

---

## State entities (system-maintained, incl. outputs)

| Entity id | Domain | Role | Unit | Default / range | Realizes | Read by | Written by |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `input_select.sc_active_mode` | input_select | state | — | `Solar`/`SolarOnly`/`Captar`/`Power`/`Off` | [active mode](system-overview.md#ubiquitous-language) | control-cycle | user (Manual) / Auto profile (R16) |
| `input_boolean.sc_home_day` | input_boolean | state | bool | off (resets daily at midnight) | [home-day flag](system-overview.md#ubiquitous-language) | resolution-rules | external / (UC08) |
| `number.sc_charger_current` | number | state (output) | A | 0 or 6–32 | charger current set-point output (C1, NF3) | — | control-cycle |
| `number.sc_vehicle_charge_limit` | number | state (output) | % | mirrors active SOC limit | vehicle charge-limit output wrapper (R6, NF3) | — | (UC09) |

---

## Notes

- **`sun.sun`** is read directly by `resolution-rules.md` (the [sun is down](system-overview.md#ubiquitous-language)
  condition) and is the one exception to the wrap-everything rule: it is a Home Assistant platform
  entity, not a device, so NF3 does not require an `sc_` wrapper.
- **`effective peak limit`, the resolved `active SOC limit`, and the resolved `departure deadline`
  have no entity.** Each is resolved every cycle by a rule in `resolution-rules.md` (from
  `sc_max_peak_kw`/`sc_monthly_peak_kw`, from the active-SOC-limit inputs, and from the departure
  inputs respectively); they are computed values, not stored helpers. If a future use-case needs
  one materialized for observability, it would add the row and its references then.
- **Output wrappers (`number.sc_charger_current`, `number.sc_vehicle_charge_limit`)** satisfy the
  NF3 requirement that every command crosses an `sc_` wrapper; a start/stop is expressed as a 0 A
  set-point on the current wrapper.
- The `<dow>` row stands for seven concrete entities (`sc_departure_mon` … `sc_departure_sun`),
  collapsed to keep the table readable.
