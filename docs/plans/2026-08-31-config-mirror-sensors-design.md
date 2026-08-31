# Design: config-value mirror diagnostic sensors (#888)

Derives from [ADR-0031](../adl/0031-config-values-as-disabled-by-default-diagnostic-sensors.md)
(Accepted) and the 35 `sensor.smart_charging_<key>` rows merged into
[`entity-catalog.md`](../analysis/entity-catalog.md) (#887). Extends `project-plan.md`'s **C3 —
Diagnostic output entities** slice: C3's own text describes its sensors as "owned entities the
Coordinator writes," which fits the nine sensors already in `sensor.py` but not these 35, which are
sourced from the config entry, not the coordinator. ADR-0031 is the gate that authorizes this
sub-family within C3's broader "diagnostic output entities" remit — the same way the
2026-08-10 dashboard-prerequisite-sensors slice extended C3 for `coordinator.data`-sourced sensors.
No new service, call direction, or volatility beyond what ADR-0031 already decided; this doc adds
only the concrete file/class/test shape.

## Scope

Add 35 read-only `sensor.smart_charging_<key>` entities, `entity_category=DIAGNOSTIC`,
`_attr_entity_registry_enabled_default = False` — one per `config-options` row in
`entity-catalog.md` except `control_interval_s` (31), plus the four `config-data` capability
booleans (4). Every id, unit, and source requirement/glossary link is already fixed by
`entity-catalog.md`; this doc does not re-decide any of them.

**Out of scope** (ADR-0031's own carve-outs, not renegotiated here): `control_interval_s`,
entity-role mappings, state-translation tables.

## Success criteria

- All 35 sensors register under the existing single "Smart Charging" device with the exact
  `entity_id` `entity-catalog.md` documents (ADR-0013 pinned `object_id`), each `disabled_by
  = RegistryEntryDisabler.INTEGRATION`-equivalent at first registration (via
  `entity_registry_enabled_default = False`), `entity_category = DIAGNOSTIC`.
- Each sensor's `native_value` matches its source config value at entry setup/reload — never
  recomputed mid-cycle (entity-catalog.md: "sourced from the config entry, not recomputed each
  cycle").
- `ruff check .` / `ruff format --check .` clean; full HA-harness suite green.

## A structural gap this design closes: `SmartChargingConfig` isn't reachable from `sensor.py`

`SmartChargingConfig` (`config.py`) is built once in `__init__.py` and passed to
`SmartChargingCoordinator(..., config=config, ...)`, which stores it as `self._config` — private,
and never read by any platform file. `SmartChargingRuntimeData` (`__init__.py`) does expose a few
*individual* resolved values today (`min_current`, `max_current`, `default_target_current`,
`default_soc_limit`, read by `number.py`), but not the whole `SmartChargingConfig` object, and nine
existing sensors in `sensor.py` only ever read `coordinator.data` (`CycleResult`), never `config`.

**T0** (below) adds one new field, `config: SmartChargingConfig`, to `SmartChargingRuntimeData` and
passes the same already-constructed `config` object through at its one construction site
(`__init__.py`'s `entry.runtime_data = SmartChargingRuntimeData(...)`). This is the minimal change
that avoids two worse alternatives: reaching into `coordinator._config` (breaks the module's own
privacy boundary) or re-resolving each value a second time in `sensor.py` with its own
`opts.get(CONF_X, DEFAULT_X)` calls (recreates exactly the double-resolution problem
`SmartChargingConfig` was introduced to eliminate, per `config.py`'s own docstring).

## Three source buckets — not all 35 values come from `SmartChargingConfig`

`SmartChargingConfig`'s field list (`config.py`) is scoped to "every config-entry option
`coordinator.py`/`coordinator_cycle.py` read during a control cycle" — five of the 35 mirrored
values are never read by the coordinator and are absent from that dataclass entirely:

| Value | Why it's absent from `SmartChargingConfig` | Read from |
| --- | --- | --- |
| `deadline_available` | Not read by the coordinator/control-cycle at all | `entry.data.get(CONF_DEADLINE_AVAILABLE, DEFAULT_DEADLINE_AVAILABLE)` |
| `notifications_available` | Same | `entry.data.get(CONF_NOTIFICATIONS_AVAILABLE, DEFAULT_NOTIFICATIONS_AVAILABLE)` |
| `reminder_lead_h` | Consumed only by `config_flow.py` today (UC10 plug-in reminder logic not yet built) | `entry.options.get(CONF_REMINDER_LEAD_H, DEFAULT_REMINDER_LEAD_H)` |
| `deadline_notice_enabled` | Consumed only by `config_flow.py` today (UC05 logic not yet built) | `entry.options.get(CONF_DEADLINE_NOTICE_ENABLED, DEFAULT_DEADLINE_NOTICE_ENABLED)` |
| `plug_in_reminder_enabled` | Consumed only by `config_flow.py` today (UC10 logic not yet built) | `entry.options.get(CONF_PLUG_IN_REMINDER_ENABLED, DEFAULT_PLUG_IN_REMINDER_ENABLED)` |

The other 30 (26 `config-options` + `solar_available`/`captar_available`, which **are** in
`SmartChargingConfig`, plus `evening_prompt_enabled`/`evening_prompt_time`, present per
`config.py`'s own docstring exception) read from `entry.runtime_data.config.<field>`.

This is a fact about the current codebase, not a new design choice: a future task that folds these
five into `SmartChargingConfig` (as `__init__.py`'s own comment at the `NotificationManager`
construction site already flags as a tracked follow-up for three of them) would let a later spec
collapse this to one source bucket — out of scope here since `SmartChargingConfig`'s own field list
is owned by `config.py`/`__init__.py`, not this slice.

## Catalog id ≠ `SmartChargingConfig` field name / `CONF_*` value, for six rows

`entity-catalog.md`'s row id is meant to equal the row's config key, but six pre-existing rows
(predating ADR-0031, not introduced by it) actually document a more descriptive id than the real
stored key:

| Catalog id (→ sensor object_id) | Real `CONF_*` value / `SmartChargingConfig` field |
| --- | --- |
| `min_current_a` | `min_current` |
| `max_current_a` | `max_current` |
| `grid_supply_ceiling_a` | `grid_ceiling_a` |
| `nominal_voltage_v` | `nominal_voltage` |
| `solar_only_rounding_strategy` | `solar_only_strategy` |
| `solar_only_rounding_midpoint_pct` | `solar_only_midpoint` |

This is a pre-existing catalog/code naming drift, unrelated to ADR-0031, not something this slice
corrects (out of scope — a documentation-only fix would go through the catalog's own review cycle).
The sensor's `entity_id`/`object_id_suffix`/`translation_key` use the **catalog's** documented id
(the committed, user-facing contract); its **implementation** reads the field name in the right
column above. The mapping table below is authoritative for every row so `develop-task` never has
to guess.

## `_ConfigMirrorSensor` shape

A single concrete class, data-driven from a declarative spec list — not 35 hand-written
subclasses (`_CoordinatorFieldSensor`'s per-field subclass shape doesn't fit here: these sensors
share one behavior — hold a value resolved once at construction — where `_CoordinatorFieldSensor`'s
subclasses each need their own `_coordinator_value` because they read a *different* `CycleResult`
field every cycle. That per-cycle re-read has no equivalent here.):

```python
@dataclass(frozen=True)
class _ConfigMirrorSpec:
    object_id_suffix: str        # == translation_key == entity-catalog.md's documented id
    unit: str | None
    device_class: SensorDeviceClass | None
    value: Any                    # already resolved by async_setup_entry, per the three buckets above


class _ConfigMirrorSensor(SmartChargingEntity, SensorEntity):
    """Diagnostic (ADR-0031): read-only mirror of one config-entry value, resolved once at
    entry setup/reload from the entry's own config -- never recomputed mid-cycle, unlike
    _CoordinatorFieldSensor's per-cycle CycleResult reads."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, entry_id: str, spec: _ConfigMirrorSpec) -> None:
        self._object_id_suffix = spec.object_id_suffix
        super().__init__(entry_id)
        self._attr_translation_key = spec.object_id_suffix
        self._attr_native_unit_of_measurement = spec.unit
        self._attr_device_class = spec.device_class
        self._attr_native_value = _format(spec.value)  # bool -> "on"/"off", else as-is
```

`_format` maps a Python `bool` to `STATE_ON`/`STATE_OFF` (`homeassistant.const`) for the 8
boolean-valued mirrors (`solar_available`, `captar_available`, `deadline_available`,
`notifications_available`, `power_respect_peak`, `deadline_notice_enabled`,
`plug_in_reminder_enabled`, `evening_prompt_enabled`); every other value passes through unchanged
(numeric, the `solar_only_strategy` enum string, or the `evening_prompt_time` `"HH:MM"` string).

**No `state_class`.** These are static/rarely-changing configuration values, not periodic
measurements — setting `SensorStateClass.MEASUREMENT` would misrepresent them to HA's long-term
statistics engine, which expects a value that changes on its own over time. None of the 35 sets it,
matching `ActiveModeSensor`/`TimeToFullSensor`'s existing precedent (unitful diagnostic sensors
with no `state_class`) over `MonthlyPeakSensor`/`PeakHeadroomSensor`'s (cycle-computed,
`MEASUREMENT`).

**`device_class`**: set only where an exact, unambiguous HA device class exists and the unit
already implies it — `CURRENT` (ampere values), `POWER` (watt/kilowatt values), `VOLTAGE` (the one
volt value). Left unset for kWh/percentage/minutes/hours/pp/enum/time-of-day/boolean values, matching
existing sensors like `TimeToFullSensor` (minutes, no device_class).

## Full mapping table (35 rows)

`object_id_suffix` doubles as `translation_key`, per the class shape above. `Source` — `config.X`
means `entry.runtime_data.config.X`; `data.X`/`opts.X` mean `entry.data.get(CONF_X, DEFAULT_X)` /
`entry.options.get(CONF_X, DEFAULT_X)`.

| object_id_suffix | Source | Unit | device_class |
| --- | --- | --- | --- |
| `solar_available` | `config.solar_available` | — | — |
| `captar_available` | `config.captar_available` | — | — |
| `deadline_available` | `data.CONF_DEADLINE_AVAILABLE` | — | — |
| `notifications_available` | `data.CONF_NOTIFICATIONS_AVAILABLE` | — | — |
| `smoothing_window` | `config.smoothing_window` | `"cycles"` | — |
| `grid_supply_ceiling_a` | `config.grid_ceiling_a` | `UnitOfElectricCurrent.AMPERE` | `CURRENT` |
| `grid_safety_offset_a` | `config.grid_safety_offset_a` | `UnitOfElectricCurrent.AMPERE` | `CURRENT` |
| `nominal_voltage_v` | `config.nominal_voltage` | `UnitOfElectricPotential.VOLT` | `VOLTAGE` |
| `min_current_a` | `config.min_current` | `UnitOfElectricCurrent.AMPERE` | `CURRENT` |
| `max_current_a` | `config.max_current` | `UnitOfElectricCurrent.AMPERE` | `CURRENT` |
| `safety_margin_w` | `config.safety_margin_w` | `UnitOfPower.WATT` | `POWER` |
| `max_peak_kw` | `config.max_peak_kw` | `UnitOfPower.KILO_WATT` | `POWER` |
| `peak_floor_kw` | `config.peak_floor_kw` | `UnitOfPower.KILO_WATT` | `POWER` |
| `peak_grace_min` | `config.peak_grace_min` | `UnitOfTime.MINUTES` | — |
| `captar_cooldown_min` | `config.captar_cooldown_min` | `UnitOfTime.MINUTES` | — |
| `power_respect_peak` | `config.power_respect_peak` | — | — |
| `power_cooldown_min` | `config.power_cooldown_min` | `UnitOfTime.MINUTES` | — |
| `ev_battery_capacity_kwh` | `config.ev_battery_capacity_kwh` | `UnitOfEnergy.KILO_WATT_HOUR` | — |
| `solar_start_threshold_w` | `config.solar_start_threshold_w` | `UnitOfPower.WATT` | `POWER` |
| `solar_hold_min` | `config.solar_hold_min` | `UnitOfTime.MINUTES` | — |
| `solar_cooldown_min` | `config.solar_cooldown_min` | `UnitOfTime.MINUTES` | — |
| `solar_restart_debounce_min` | `config.solar_restart_debounce_min` | `UnitOfTime.MINUTES` | — |
| `solar_only_start_threshold_w` | `config.solar_only_start_threshold_w` | `UnitOfPower.WATT` | `POWER` |
| `solar_only_hold_min` | `config.solar_only_hold_min` | `UnitOfTime.MINUTES` | — |
| `solar_only_rounding_strategy` | `config.solar_only_strategy` | — | — |
| `solar_only_rounding_midpoint_pct` | `config.solar_only_midpoint` | `PERCENTAGE` | — |
| `max_solar_soc` | `config.max_solar_soc` | `PERCENTAGE` | — |
| `solar_step_pp` | `config.solar_step_pp` | `"pp"` | — |
| `solar_step_threshold_pp` | `config.solar_step_threshold_pp` | `"pp"` | — |
| `solar_forecast_threshold_kwh` | `config.solar_forecast_threshold_kwh` | `UnitOfEnergy.KILO_WATT_HOUR` | — |
| `reminder_lead_h` | `opts.CONF_REMINDER_LEAD_H` | `UnitOfTime.HOURS` | — |
| `deadline_notice_enabled` | `opts.CONF_DEADLINE_NOTICE_ENABLED` | — | — |
| `plug_in_reminder_enabled` | `opts.CONF_PLUG_IN_REMINDER_ENABLED` | — | — |
| `evening_prompt_enabled` | `config.evening_prompt_enabled` | — | — |
| `evening_prompt_time` | `config.evening_prompt_time` | — | — |

## Mapping to `system-design.md` services

| Piece | Service |
| --- | --- |
| `_ConfigMirrorSensor`, `_ConfigMirrorSpec`, `async_setup_entry`'s 35-entry spec list (`sensor.py`) | C3 — Diagnostic output entities (extended scope, ADR-0031 gate) |
| `SmartChargingRuntimeData.config` field (`__init__.py`) | C4 — Install-time config flow / options flow's own domain (config resolution), not a new service |

## Testing approach (ADR-0009)

HA harness throughout — every task touches `__init__.py`/`sensor.py` entity registration.

## Packaging

`strings.json`, `translations/en.json`, `translations/nl.json` gain 35
`entity.sensor.<object_id_suffix>.name` entries, matching the existing nine sensors' style
(English + Dutch).

## Deferrals

- Folding the five entry.data/entry.options-sourced values into `SmartChargingConfig` (noted as a
  tracked follow-up already in `__init__.py`'s own comment for three of them) — out of scope; this
  slice reads them from their current, real location instead of moving them.
- Reconciling the six catalog-id/config-key naming mismatches — pre-existing, out of scope, a
  documentation-only fix for a future catalog pass.
- No safety-relevant behavior is deferred: these are read-only entities with no write path and no
  control-cycle interaction.
