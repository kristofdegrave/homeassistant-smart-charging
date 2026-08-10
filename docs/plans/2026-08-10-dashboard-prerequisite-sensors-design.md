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

All four belong to `project-plan.md`'s **C3** ("diagnostic output entities") — the same
service `system-design.md` already names for `MonthlyPeakSensor`/`EffectivePeakLimitSensor`/
`ActiveSocLimitSensor`. Nothing here adds a new service or a new call direction: M1 still
computes, C3's sensors still only read `coordinator.data`.

Out of scope: the dashboard YAML/registration itself (C5, tracked separately under #601), and
`solar_power` (no adapter implements that role yet — `adapter_readings` only mirrors roles
actually wired, per ADR-0021's Context).

## Success criteria

- All four entities appear via `async_setup_entry` (ADR-0004 owned-entity population). None of
  the five existing diagnostic sensors sets `entity_category`, and this slice does not
  retrofit that — except `adapter_readings`, where ADR-0021's Option C explicitly requires
  `entity_category: diagnostic`; that one gets `_attr_entity_category = EntityCategory.DIAGNOSTIC`.
- Each's object_id is pinned via `_object_id_suffix` (ADR-0013): `solar_surplus_w`,
  `time_to_full`, `peak_headroom_a`, `adapter_readings`.
- Values match `entity-catalog.md`'s stated formulas exactly (test anchors below).
- `adapter_readings`' attributes hold one key per currently-wired *read* adapter role, `None`
  for a role never yet successfully read (ADR-0007-style "unavailable" semantics), without the
  entity itself going unavailable, and the whole blob survives a faulted cycle (ADR-0021
  Consequences) — see the persisted role-readings cache below.
- No *new per-cycle* adapter reads for `solar_surplus_w`/`peak_headroom_a`/`adapter_readings`.
  `time_to_full` is the one disclosed exception (see its row below) — it needs the EV battery
  capacity role read unconditionally each cycle instead of only inside the deadline branch, a
  deliberate, minor widening of "no new reads" rather than a silent one.

## Control-flow mapping

All four are computed inside `_run_cycle` (ADR-0006) and carried out via `CycleResult` (the
same push-per-cycle path `monthly_peak_kw`/`effective_peak_limit_kw`/`active_soc_limit`
already use; `DataUpdateCoordinator` publishes `CycleResult` as `coordinator.data` and each
sensor's `native_value` reads its own field off it). ADR-0021's Consequences say the
coordinator "must be updated to write this entity's attributes through RA3's Store
(ADR-0018)" — this is a **disclosed deviation**, not followed literally: `Store.write()`
(`adapters/store.py`) only issues `number`/`switch` HA service calls for owned *control*
entities, and structurally cannot carry a sensor's state plus an attribute dict. Every
existing diagnostic sensor (`MonthlyPeakSensor`, `EffectivePeakLimitSensor`,
`ActiveSocLimitSensor`) already reaches its entity via `CycleResult`, not a `Store` write;
`adapter_readings` follows that same, already-established path instead of ADR-0021's literal
wording.

| Sensor | Source values | Formula | Test anchor |
| --- | --- | --- | --- |
| `solar_surplus_w` | `charger_w`, raw `net_w` | `charger_w - net_w` (raw, per entity-catalog.md/glossary — deliberately **not** the smoothed `surplus_w` local at coordinator.py:288, which is R10's control-path conditioning, a distinct quantity from the glossary's "solar surplus") | entity-catalog.md:151, system-overview.md glossary |
| `time_to_full` | `effective_battery_capacity_kwh` (R15's sensed-value-preferred capacity, coordinator.py:420-431 — see disclosed-deviation note below), `ev_soc`, `active_soc_limit`, this cycle's own commanded current (`desired`, the mode's resolved set-point before the R3/C4 clamps and floor/cap — matches the glossary's "charger's current set-point"), `voltage` | `energy_needed_kwh = capacity_kwh * (active_soc_limit - ev_soc) / 100` (same shape as `engines/deadline.py`'s `energy_needed_kwh`); minutes `= energy_needed_kwh * 1000 / (commanded_current * voltage) * 60`; unavailable (`None`) when `commanded_current == 0`; `0` when `ev_soc >= active_soc_limit` | entity-catalog.md:152 |
| `peak_headroom_a` | `net_w`, `charger_w`, `voltage`, `effective_peak_limit_kw`, `safety_margin_w` (config) | identical to `engines/billing_protection.apply_peak_clamp`'s internal `headroom_a`: `baseline_w = net_w - charger_w`; `target_w = effective_peak_limit_kw * 1000 - safety_margin_w`; `headroom_a = floor((target_w - baseline_w) / voltage)` | entity-catalog.md:153, control-cycle.md step 5 |
| `adapter_readings` | the persisted role-readings cache (below) | state = cache's last-updated timestamp; attributes = a copy of the cache, filtered to currently-wired roles | entity-catalog.md:154, ADR-0021 |

`peak_headroom_a` duplicates `apply_peak_clamp`'s arithmetic rather than having that function
return it, to avoid changing a control-path function's signature/return contract for a
display-only need — `apply_peak_clamp` is exercised by its own pytest suite (ADR-0009) and
stays untouched; the sensor's own test anchors the duplicated formula directly against
`entity-catalog.md`/`control-cycle.md`, not against `apply_peak_clamp`'s internals. Its
`0.0` default (dataclass default, same shape as `monthly_peak_kw`/`effective_peak_limit_kw`)
reads as "no headroom" on a cycle that faults before this field is set, which is an accepted,
pre-existing convention this slice follows rather than introduces — `None` would read as
"unknown" but none of the three existing float diagnostics distinguish the two either.

**`time_to_full`'s disclosed deviation:** `effective_battery_capacity_kwh` (R15) is currently
only computed inside `_run_cycle`'s `if deadline_resolvable:` branch (coordinator.py:420-431),
because that is the only place today that needs it. Gating `time_to_full` behind that branch
would make it unavailable whenever the departure deadline isn't configured/resolvable — a
worse dashboard experience than the value it exists to provide, and not something
`entity-catalog.md`'s row conditions on. This slice promotes the `ROLE_EV_BATTERY_CAPACITY`
read + R15 resolution (coordinator.py:420-425's read/fallback logic) to run unconditionally
every cycle, once, ahead of the deadline branch, and the deadline branch reuses that already-
resolved value instead of computing it again. This is the one adapter role this slice reads on
every cycle where it previously read conditionally — a deliberate, minor widening of "no new
adapter reads," not a silent one, and justified because R15 already treats this role as
continuously available whenever mapped, not deadline-specific.

**`adapter_readings`'s persisted cache:** ADR-0021's Option C calls for "that role's **most
recently read value**", which single-cycle reads cannot provide — most wired roles
(`charger_current`, `car_home`, `home_day_external`, `vehicle_charge_limit`, and several
conditionally-read ones) aren't read on every cycle. The coordinator gains a persisted
instance dict, `self._role_readings: dict[str, Any]` (same lifetime/pattern as
`self._net_window`/`self._peak_demand` — created in `__init__`, mutated across cycles, never
reset), updated at every point in `_run_cycle` where a role is already read (no new reads:
`status`, `net_w`, `charger_w`, `measured_v`, `ev_soc`, and the promoted battery-capacity read
above all update it inline where they already happen) plus a `self._role_readings_at:
datetime | None`, set to `now_dt` whenever any read updates the cache this cycle. Every
`CycleResult(...)` construction site — including the two early-fault returns — sets
`adapter_readings=dict(self._role_readings)` and `adapter_readings_at=self._role_readings_at`,
so a faulted cycle still reports whichever roles were read before the fault, and never resets
the blob to empty once populated. `adapter_readings`'s dict is filtered to keys still present
in `self._adapters` minus `ROLES_ADAPTER_READINGS_EXCLUDED` (new frozenset in `const.py`:
`{ROLE_NOTIFICATION_TARGET}` today — an explicit constant, not a `read()`-duck-typing check,
since `NotifyAdapter` also exposes a `read()` and `ROLE_VEHICLE_CHARGE_LIMIT` is read/write) at
render time, so a role that stops being wired disappears from the dict on its next cycle even
though the cache still holds its stale value internally. A role in `self._adapters` but never
yet present in the cache renders as `None` (ADR-0007-style "unavailable", not yet observed —
correct on the very first cycle after startup, before any read has happened).

## `CycleResult` fields added

```python
solar_surplus_w: float = 0.0
time_to_full_min: float | None = None
peak_headroom_a: float = 0.0
adapter_readings: dict[str, Any] = field(default_factory=dict)
adapter_readings_at: datetime | None = None
```

`adapter_readings_at` backs the sensor's `native_value` (the timestamp); `adapter_readings`
backs `extra_state_attributes`. Unlike the other three fields, both are set from
`self._role_readings`/`self._role_readings_at` (above) at **every** `CycleResult(...)`
construction site, including the two early-fault returns — never left at the bare dataclass
default once the coordinator has completed at least one successful read, per ADR-0021's
"last successful read" wording.

### Write-site table

`_run_cycle` has four `CycleResult(...)` construction sites. What each new field receives at
each:

| Site (coordinator.py) | `solar_surplus_w` | `peak_headroom_a` | `time_to_full_min` | `adapter_readings`/`_at` |
| --- | --- | --- | --- | --- |
| ~212 (pre-adapter-read guard; unreachable in practice today) | default `0.0` | default `0.0` | default `None` | cache (empty at startup) |
| ~230 (required-role `None` → fault) | default `0.0` (not yet computed) | default `0.0` | default `None` | cache (whatever was read before the fault, e.g. `measured_v`) |
| ~274 (`ev_soc` required-but-missing → fault) | computed value (already available) | default `0.0` (not yet computed) | default `None` (soc unknown) | cache |
| ~572 (normal end-of-cycle result) | computed value | computed value | computed value | cache |

## Entities added (`sensor.py`)

Four new classes. `_CoordinatorFieldSensor`'s shared `native_value` already handles a field
that is `None`, `0`, or absent identically to a bespoke property (`_field_default` only
substitutes when the attribute is *absent* from `coordinator.data`, never when it's present
and `0`/`None`) — confirmed against `sensor.py:41-54` — so `TimeToFullSensor` does **not**
need a bespoke class; only `AdapterReadingsSensor` does, because it also needs
`extra_state_attributes`, which `_CoordinatorFieldSensor` has no hook for. Object-id suffixes
use named constants (`const.py`), matching `ActiveSocLimitSensor`'s `OWNED_SUFFIX_*` pattern,
not bare string literals:

```python
class SolarSurplusSensor(_CoordinatorFieldSensor):
    _attr_translation_key = "solar_surplus_w"
    _object_id_suffix = OWNED_SUFFIX_SOLAR_SURPLUS_W
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _coordinator_field = "solar_surplus_w"

class TimeToFullSensor(_CoordinatorFieldSensor):
    _attr_translation_key = "time_to_full"
    _object_id_suffix = OWNED_SUFFIX_TIME_TO_FULL
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _coordinator_field = "time_to_full_min"

class PeakHeadroomSensor(_CoordinatorFieldSensor):
    _attr_translation_key = "peak_headroom_a"
    _object_id_suffix = OWNED_SUFFIX_PEAK_HEADROOM_A
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _coordinator_field = "peak_headroom_a"

class AdapterReadingsSensor(_CoordinatorPushMixin, SensorEntity):
    _attr_translation_key = "adapter_readings"
    _object_id_suffix = OWNED_SUFFIX_ADAPTER_READINGS
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC  # ADR-0021's Option C requires this

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
  `solar_surplus_w` uses raw `net_w`, not smoothed; `peak_headroom_a`/`time_to_full_min` match
  hand-computed expected values for representative inputs; `time_to_full_min is None` when the
  commanded current is `0`; `time_to_full_min == 0` when `ev_soc >= active_soc_limit`;
  `adapter_readings` contains every currently-wired role key, excludes
  `ROLES_ADAPTER_READINGS_EXCLUDED`, a role whose adapter returns `None` this cycle shows up as
  `None` without faulting the cycle, and — the cache behavior — a role read on cycle 1 but not
  re-read on cycle 2 still shows cycle 1's value in cycle 2's `adapter_readings`, and a role
  never yet read shows `None`. A cycle that faults (missing required role) still returns a
  non-empty `adapter_readings` reflecting whatever was read before the fault, not `{}`.
- **Entity-registration checkpoint** (HA harness, `test_sensor.py` or a config-entry setup
  test): all nine `sensor.smart_charging_*` entities register via `async_setup_entry` with no
  duplicate `unique_id`/`object_id` (ADR-0013) — a concrete assertion, not a manual step.

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
- `sensor.smart_charging_desired_current` (`entity-catalog.md:147`) — also documented but
  unbuilt; out of scope for this slice, still an open item for whichever follow-up builds it.
- `adapter_readings` excludes `car_home`, `vehicle_charge_limit`, and `home_day_external`
  (via `ROLES_ADAPTER_READINGS_EXCLUDED`, discovered during implementation review) — these
  roles are read by `VehicleLimitManager`/`NotificationManager` (M2/M3), never by the
  coordinator's own `_run_cycle`, so there is no in-cycle "most recently read value" to
  mirror without either a second, duplicate read (violating "no new adapter reads") or
  threading those managers' own reads into this cache (a cross-manager coupling out of
  #602's scope). Surfacing them is a follow-up for whichever slice next needs them on the
  dashboard, not resolved here.
