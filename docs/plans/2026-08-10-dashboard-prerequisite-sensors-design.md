# Design: dashboard-prerequisite diagnostic sensors (#602)

Issue: #602. Branch: `feature/dashboard-prerequisite-sensors`.

## Scope

Implement the four diagnostic sensors that `entity-catalog.md`'s "Diagnostic outputs" table
already documents but `sensor.py` has never built:

- `sensor.smart_charging_solar_surplus_w`
- `sensor.smart_charging_time_to_full`
- `sensor.smart_charging_peak_headroom_a`
- `sensor.smart_charging_adapter_readings` (ADR-0021, Accepted)

This is the last of the three prerequisites the 2026-08-10 sequencing note
(`docs/plans/2026-08-10-runtime-dashboard-sequencing.md`) named before the C5 (runtime
dashboard) implementation spec can be written — the catalog and ADR-0022 halves are already
merged. Nothing here decides new behavior: every formula and semantic already exists in
`entity-catalog.md`, `control-cycle.md`, ADR-0021, or `system-overview.md`'s glossary. This
doc only maps each to a concrete `CycleResult` field, a `sensor.py` class, and a coordinator
write site.

Out of scope: the dashboard YAML/registration itself (C5, tracked separately under #601), and
`solar_power` (no adapter implements that role yet — `adapter_readings` only mirrors roles
actually wired, per ADR-0021's Context).

## Success criteria

- All four entities appear via `async_setup_entry`, each `entity_category: diagnostic`
  (ADR-0004 population, matching the five sensors already in `sensor.py`).
- Each's object_id is pinned via `_object_id_suffix` (ADR-0013): `solar_surplus_w`,
  `time_to_full`, `peak_headroom_a`, `adapter_readings`.
- Values match `entity-catalog.md`'s stated formulas exactly (test anchors below).
- `adapter_readings`' attributes hold one key per currently-wired *read* adapter role,
  `None` when that role's own reading is unavailable this cycle (ADR-0007 semantics), without
  the entity itself going unavailable (ADR-0021 Consequences).
- No new adapter reads — every value is sourced from reads the coordinator already performs
  for control logic (ADR-0021's Decision: "no extra adapter reads").

## Control-flow mapping

All four are computed inside `_run_cycle` (ADR-0006) and carried out via `CycleResult`
(the same push-per-cycle path `monthly_peak_kw`/`effective_peak_limit_kw`/`active_soc_limit`
already use — no Store write; `DataUpdateCoordinator` publishes `CycleResult` as
`coordinator.data` and each sensor's `native_value` reads its own field off it, per the
existing `_CoordinatorFieldSensor` pattern). ADR-0021's Consequences describe this as "written
through RA3's Store" in the abstract sense of "the same step-10 push as the other owned
diagnostic entities" — in this codebase that push mechanism is `CycleResult`, not a `Store`
write call; the Store (ADR-0018) is the *read* path for owned control entities
(`self._store.read(...)`, `_read_owned_entities`), not how coordinator diagnostics reach
sensors.

| Sensor | Source values (already read/computed in `_run_cycle`) | Formula | Test anchor |
| --- | --- | --- | --- |
| `solar_surplus_w` | `charger_w`, `smoothed_net_w` | `charger_w - smoothed_net_w` (identical to the existing local `surplus_w`, coordinator.py:288) | entity-catalog.md:151 |
| `time_to_full` | `ev_battery_capacity_kwh` (config), `ev_soc`, `active_soc_limit`, `charger_current` (ROLE_CHARGER_CURRENT read), `voltage` | `energy_needed_kwh = capacity_kwh * (active_soc_limit - ev_soc) / 100` (same shape as `engines/deadline.py`'s `energy_needed_kwh`); minutes `= energy_needed_kwh * 1000 / (charger_current * voltage) * 60`; unavailable (`None`) when `charger_current == 0`; `0` when `ev_soc >= active_soc_limit` | entity-catalog.md:152 |
| `peak_headroom_a` | `net_w`, `charger_w`, `voltage`, `effective_peak_limit_kw`, `safety_margin_w` (config) | identical to `engines/billing_protection.apply_peak_clamp`'s internal `headroom_a`: `baseline_w = net_w - charger_w`; `target_w = effective_peak_limit_kw * 1000 - safety_margin_w`; `headroom_a = floor((target_w - baseline_w) / voltage)` | entity-catalog.md:153, control-cycle.md step 5 |
| `adapter_readings` | every *read* role currently in `self._adapters` (excludes `ROLE_NOTIFICATION_TARGET`, write-only) | state = `now_dt` (timestamp of the read); attributes = `{role: last_value_or_None}` | entity-catalog.md:154, ADR-0021 |

`peak_headroom_a` duplicates `apply_peak_clamp`'s arithmetic rather than having that function
return it, to avoid changing a control-path function's signature/return contract for a
display-only need — `apply_peak_clamp` is exercised by its own pytest suite (ADR-0009) and
stays untouched; the sensor's own test anchors the duplicated formula directly against
`entity-catalog.md`/`control-cycle.md`, not against `apply_peak_clamp`'s internals.

`time_to_full`'s minutes formula: `energy_needed_kwh` (kWh) → Wh via `*1000`; charger power at
the current set-point is `charger_current * voltage` (W); hours `= Wh / W`; minutes `= hours *
60`. Matches `system-overview.md`'s glossary entry (added in #596) including both edge cases.

`adapter_readings`' role set is read from `self._adapters.keys()` minus
`ROLE_NOTIFICATION_TARGET` at read time (not a fixed list), so a future adapter addition (e.g.
`solar_power`) is picked up automatically with no code change here, matching ADR-0021's
Context ("does not need to be revisited when [the wired-role set] happens"). A role's value is
`None` when this cycle's read for it returned `None`, without affecting `fault`/other fields —
matching ADR-0007 (grid voltage is already `None`-tolerant in `_run_cycle`; the other required
roles fault the whole cycle on `None`, in which case `adapter_readings` still reports whichever
optional roles *did* read successfully this cycle, e.g. `ev_soc`, `grid_voltage`).

## `CycleResult` fields added

```python
solar_surplus_w: float = 0.0
time_to_full_min: float | None = None
peak_headroom_a: float = 0.0
adapter_readings: dict[str, float | str | None] = field(default_factory=dict)
adapter_readings_at: datetime | None = None
```

`adapter_readings_at` backs the sensor's `native_value` (the timestamp); `adapter_readings`
backs `extra_state_attributes`. Both are set together, every cycle that reaches the point in
`_run_cycle` where the relevant adapters have been read (i.e. every cycle that doesn't fault
before that point) — the early-fault return paths (missing `status`/`net_w`/`charger_w`) leave
both at their dataclass defaults (`{}` / `None`), which the sensor's `native_value` renders the
same way `EffectivePeakLimitSensor` renders `None` when `coordinator.data` doesn't yet carry
the field.

## Entities added (`sensor.py`)

Four new classes, following the existing `_CoordinatorFieldSensor` pattern for
`solar_surplus_w` and `peak_headroom_a`, plus two with bespoke `native_value` (`time_to_full`
because `None` is a real value distinct from "no data yet"; `adapter_readings` because it also
needs `extra_state_attributes`):

```python
class SolarSurplusSensor(_CoordinatorFieldSensor):
    _attr_translation_key = "solar_surplus_w"
    _object_id_suffix = "solar_surplus_w"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _coordinator_field = "solar_surplus_w"

class TimeToFullSensor(_CoordinatorPushMixin, SensorEntity):
    _attr_translation_key = "time_to_full"
    _object_id_suffix = "time_to_full"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        return getattr(data, "time_to_full_min", None) if data is not None else None

class PeakHeadroomSensor(_CoordinatorFieldSensor):
    _attr_translation_key = "peak_headroom_a"
    _object_id_suffix = "peak_headroom_a"
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _coordinator_field = "peak_headroom_a"

class AdapterReadingsSensor(_CoordinatorPushMixin, SensorEntity):
    _attr_translation_key = "adapter_readings"
    _object_id_suffix = "adapter_readings"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> datetime | None:
        data = self.coordinator.data
        return getattr(data, "adapter_readings_at", None) if data is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        return dict(getattr(data, "adapter_readings", {})) if data is not None else {}
```

Registered in `async_setup_entry` alongside the existing five.

## Testing approach (ADR-0009)

Coordinator + entities are HA-harness territory (existing `test_sensor.py`/`test_coordinator.py`
pattern: `SimpleNamespace(data=...)` for pure sensor unit tests, a real coordinator cycle for
the formula tests). Split:

- **`sensor.py` unit tests** (HA harness, `SimpleNamespace` coordinator, mirrors the
  `EffectivePeakLimitSensor`/`ActiveSocLimitSensor` tests already in `test_sensor.py`): reads
  its own field, `None`-defaults when `coordinator.data` is `None` or lacks the field,
  `unique_id` scoping, `adapter_readings`' `extra_state_attributes` reflects the dict.
- **Coordinator formula tests** (HA harness, `test_coordinator.py`, a real `_run_cycle`):
  `solar_surplus_w`/`peak_headroom_a`/`time_to_full_min` match hand-computed expected values
  for representative inputs; `time_to_full_min is None` when `charger_current == 0`;
  `time_to_full_min == 0` when `ev_soc >= active_soc_limit`; `adapter_readings` contains every
  wired read-role key, excludes `notification_target`, and a role whose adapter returns `None`
  this cycle shows up as `None` without faulting the cycle.

No new pure-logic (`engines/`) module — `peak_headroom_a`'s arithmetic is short enough to
inline in `_run_cycle` directly (matching how `surplus_w` already is), not worth extracting
into `engines/` for a single call site.

## Packaging

`strings.json` + `translations/en.json` + `translations/nl.json` (T5.2's pattern) each get four
new `entity.sensor.<key>.name` entries: `solar_surplus_w` → "Solar surplus",
`time_to_full` → "Time to full charge", `peak_headroom_a` → "Peak headroom",
`adapter_readings` → "Adapter readings".

## Deferrals

- Per-role recorder history for an individual `adapter_readings` attribute — ADR-0021's Decision
  already defers this explicitly ("if a future dashboard need requires that for one specific
  role, applying Option A's mechanism to just that one role ... is the appropriate follow-up
  then, not a blanket decision now"). Not revisited here.
- `solar_power` role — no adapter implements it yet; `adapter_readings` will pick it up
  automatically once one exists, no code change needed in this slice.
