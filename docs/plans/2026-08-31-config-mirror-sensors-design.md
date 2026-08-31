# Design: config-value mirror diagnostic sensors (#888)

Derives from [ADR-0031](../adl/0031-config-values-as-disabled-by-default-diagnostic-sensors.md)
(Accepted) and the 35 `sensor.smart_charging_<key>` rows merged into
[`entity-catalog.md`](../analysis/entity-catalog.md) (#887). Sits under `project-plan.md`'s **C3 —
Diagnostic output entities** slice, but genuinely extends its service definition, not just its
entity count: C3's own text describes its sensors as "owned entities the Coordinator **writes**"
via M1/the Store (`project-plan.md:371-379`) — true of the nine sensors already in `sensor.py`, and
still true of the 2026-08-10 dashboard-prerequisite-sensors slice, which stayed inside that
definition (that design's own words: "M1 still computes, C3's sensors still only read
`coordinator.data`" — it added sensors, not a new source). These 35 are different: sourced from the
config entry, never written by M1, never touching the Store. This is the first slice to widen C3
beyond "Coordinator-written," and ADR-0031 (Accepted, whose Consequences explicitly call for this
impl spec) is the gate that authorizes that widening — recorded here plainly as a deviation from
C3's current text, not implied by a precedent that in fact stayed inside it. No new service,
adapter, or call direction beyond what ADR-0031 already decided; this doc adds only the concrete
file/class/test shape and flags the one service-definition point a future `project-plan.md` pass
should reconcile.

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
  cycle") — **and** stays correct across a reload after an options change (ADR-0008), since
  `_ConfigMirrorSensor`'s value is only ever set from the freshly-resolved config each reload, not
  cached from a prior one.
- None of the 35 carries `LABEL_SC_RUNTIME` — `_owned_labels` defaults to `frozenset()`
  (`entity.py`) and `_ConfigMirrorSensor` never overrides it, so ADR-0031's "never on the runtime
  dashboard" claim holds structurally, not just by omission.
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
`coordinator.py`/`coordinator_cycle.py` read during a control cycle" — **six** of the 35 mirrored
values are never read by the coordinator and are absent from that dataclass entirely:

| Value | Why it's absent from `SmartChargingConfig` | Read from |
| --- | --- | --- |
| `deadline_available` | Not read by the coordinator/control-cycle at all | `entry.data.get(CONF_DEADLINE_AVAILABLE, DEFAULT_DEADLINE_AVAILABLE)` |
| `notifications_available` | Same | `entry.data.get(CONF_NOTIFICATIONS_AVAILABLE, DEFAULT_NOTIFICATIONS_AVAILABLE)` |
| `power_cooldown_min` | Not read by the coordinator/control-cycle either — resolved nowhere outside `config_flow.py` today, despite `captar_cooldown_min`/`solar_cooldown_min` (its siblings) being present | `entry.options.get(CONF_POWER_COOLDOWN_MIN, DEFAULT_POWER_COOLDOWN_MIN)` |
| `reminder_lead_h` | Consumed only by `config_flow.py` today (UC10 plug-in reminder logic not yet built) | `entry.options.get(CONF_REMINDER_LEAD_H, DEFAULT_REMINDER_LEAD_H)` |
| `deadline_notice_enabled` | Consumed only by `config_flow.py` today (UC05 logic not yet built) | `entry.options.get(CONF_DEADLINE_NOTICE_ENABLED, DEFAULT_DEADLINE_NOTICE_ENABLED)` |
| `plug_in_reminder_enabled` | Consumed only by `config_flow.py` today (UC10 logic not yet built) | `entry.options.get(CONF_PLUG_IN_REMINDER_ENABLED, DEFAULT_PLUG_IN_REMINDER_ENABLED)` |

The other 29 (25 `config-options` + `solar_available`/`captar_available`, which **are** in
`SmartChargingConfig`, plus `evening_prompt_enabled`/`evening_prompt_time`, present per
`config.py`'s own docstring exception) read from `entry.runtime_data.config.<field>`.

This is a fact about the current codebase, not a new design choice. `__init__.py`'s own comment at
the `NotificationManager` construction site flags a tracked follow-up to fold *its* three config
values onto `SmartChargingConfig` — but those three are `evening_prompt_enabled`,
`solar_forecast_threshold_kwh`, and `evening_prompt_time`, all **already** `SmartChargingConfig`
fields today; that comment says nothing about the six above, and no existing tracked follow-up
covers them. A future task that folds all six into `SmartChargingConfig` would let a later spec
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
corrects. Unlike the 6-row `power_cooldown_min`-style gap above, this one is worth resolving
*before* build rather than deferring: per ADR-0013, an `object_id` is expensive to change once
shipped (breaks users' automations/dashboards), and none of these 35 sensors exist yet — today the
"fix" is a six-line edit to `entity-catalog.md`'s existing rows (renaming the `Id` column to the
real `CONF_*`/field value), the cheapest this will ever be. This design deliberately does **not**
take that path: the catalog's fuller spelling (`min_current_a`, not `min_current`) is consistent
with every *other* row in the catalog, which already includes a unit suffix even where the code's
own key doesn't (`grid_supply_ceiling_a`/`grid_safety_offset_a` sit side by side in the same table,
and only the first diverges from its `CONF_*` value) — renaming the six to match the bare code key
would make the catalog *less* internally consistent, not more. The sensor's
`entity_id`/`object_id_suffix`/`translation_key` therefore use the **catalog's** documented id;
its **implementation** reads the field name in the right column above. The mapping table below is
authoritative for every row so `develop-task` never has to guess. This reasoning is recorded here,
not silently assumed, precisely because ADR-0013 forecloses revisiting it casually later.

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
        self._attr_native_value = _format_mirror_value(spec.value)  # bool -> "on"/"off", else as-is
```

`_format_mirror_value` maps a Python `bool` to `STATE_ON`/`STATE_OFF` (`homeassistant.const`) for the 8
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
| `power_cooldown_min` | `opts.CONF_POWER_COOLDOWN_MIN` | `UnitOfTime.MINUTES` | — |
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
| `evening_prompt_time` | `config.evening_prompt_time` | — (see note) | — |

`evening_prompt_time`'s unit deliberately diverges from `entity-catalog.md`'s `time` column: the
value is a plain `"HH:MM"` string (not a `datetime`), so no HA unit/`SensorDeviceClass.TIMESTAMP`
applies — the catalog's `time` describes the *value's meaning*, not an HA unit constant to set.

## Mapping to `system-design.md` services

| Piece | Service |
| --- | --- |
| `_ConfigMirrorSensor`, `_ConfigMirrorSpec`, `async_setup_entry`'s 35-entry spec list (`sensor.py`) | C3 — Diagnostic output entities (extended scope, ADR-0031 gate — see Scope above; none of the 35 are "written" in C3's original sense, since none touch the Store or an M1 write path) |
| `SmartChargingRuntimeData.config` field (`__init__.py`) | No named service — `__init__.py`'s `async_setup_entry` is the composition root, not a `system-design.md` service; C4 owns *resolving* config values, not the runtime-data wiring that exposes an already-resolved object to platform files |

## Testing approach (ADR-0009)

Per task, not a single blanket boundary: T0–T4 and T6 touch `__init__.py`/`sensor.py` entity
registration and config-entry data, so HA harness; T5 (translation files) and
`_format_mirror_value` (pure `bool → STATE_ON`/`STATE_OFF` mapping, no HA dependency) are plain
pytest, matching `tests/test_translations.py`'s existing precedent for translation-key coverage.

## Packaging

`strings.json`, `translations/en.json`, `translations/nl.json` gain 35
`entity.sensor.<object_id_suffix>.name` entries, matching the existing nine sensors' style
(English + Dutch).

## Deferrals

- Folding the six entry.data/entry.options-sourced values into `SmartChargingConfig` — out of
  scope; no existing tracked follow-up covers these six specifically (the one `__init__.py`
  comment that mentions a `SmartChargingConfig`-folding follow-up is about `NotificationManager`'s
  three *already*-present fields, not these six — see the source-buckets section above). This
  slice reads the six from their current, real location instead of moving them.
- `SmartChargingRuntimeData` now carries both the new `config` field and four scalars
  (`min_current`, `max_current`, `default_target_current`, `default_soc_limit`) that duplicate
  `config.min_current`/`config.max_current`. De-duplicating those four onto `config` is a
  follow-up, not this slice — `number.py` keeps reading its existing fields unchanged.
- Reconciling the six catalog-id/config-key naming mismatches from a *different* section above
  (`min_current_a` vs. `min_current`, etc.) — deliberately **not** deferred; resolved in this
  design by keeping the catalog's fuller spelling as the sensor id (see that section's reasoning).
- `entity-catalog.md`'s "How to read it" preamble already carries the ADR-0031 config-mirror
  caveat (added in #887, before this spec) — no further catalog-preamble follow-up needed here.
- No safety-relevant behavior is deferred: these are read-only entities with no write path and no
  control-cycle interaction.
