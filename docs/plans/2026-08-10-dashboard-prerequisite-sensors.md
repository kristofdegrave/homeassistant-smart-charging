# TDD plan: dashboard-prerequisite diagnostic sensors (#602)

Derived from `docs/plans/2026-08-10-dashboard-prerequisite-sensors-design.md`. Branch:
`feature/dashboard-prerequisite-sensors`. Test boundary throughout: HA harness (ADR-0009) —
every task touches `coordinator.py`, `sensor.py`, or their entity-registration tests.

## T1 — `CycleResult` fields + `solar_surplus_w`

- Failing test (`tests/test_coordinator.py`): a `_run_cycle` with known `charger_w`/`net_w`
  asserts `result.solar_surplus_w == charger_w - net_w` (raw `net_w`, **not** the smoothed
  local — assert this with a case where smoothing would give a different answer, e.g. a
  smoothing window primed with a different prior value) for at least two cases (surplus
  positive, surplus negative/importing).
- Add `OWNED_SUFFIX_SOLAR_SURPLUS_W = "solar_surplus_w"` to `const.py`.
- Add `solar_surplus_w: float = 0.0` to `CycleResult` (`coordinator.py`). Compute it from raw
  `net_w`/`charger_w` (a new local, distinct from the existing smoothed `surplus_w`) right
  after both are read (~coordinator.py:218). Set on every `CycleResult(...)` construction site
  reached after that point (the required-role-`None` fault return at ~230 is before this point
  and keeps the `0.0` default; the `ev_soc`-missing fault return at ~274 and the normal
  end-of-cycle result at ~572 both set it).
- Failing test (`tests/test_sensor.py`): `SolarSurplusSensor` reads `solar_surplus_w` off
  `coordinator.data`, defaults to `None` when `data is None`, `unique_id ==
  "<entry_id>_solar_surplus_w"`.
- Add `SolarSurplusSensor(_CoordinatorFieldSensor)` to `sensor.py` (translation_key
  `solar_surplus_w`, `_object_id_suffix = OWNED_SUFFIX_SOLAR_SURPLUS_W`, `UnitOfPower.WATT`).
  Register in `async_setup_entry`.
- Green, commit: `feat: add solar_surplus_w diagnostic sensor (#602)`.

## T2 — `peak_headroom_a`

- Failing test (`tests/test_coordinator.py`): a `_run_cycle` with known `net_w`, `charger_w`,
  `voltage`, `effective_peak_limit_kw`, `safety_margin_w` asserts `result.peak_headroom_a ==
  floor((effective_peak_limit_kw*1000 - safety_margin_w - (net_w - charger_w)) / voltage)` —
  hand-computed per the design doc's formula, cross-checked against
  `entity-catalog.md:153`/`control-cycle.md` step 5.
- Add `OWNED_SUFFIX_PEAK_HEADROOM_A = "peak_headroom_a"` to `const.py`.
- Add `peak_headroom_a: float = 0.0` to `CycleResult`; compute it in `_run_cycle` right after
  `effective_peak_limit_kw`'s final (non-provisional) resolution (coordinator.py ~476-484, so it
  reflects the same `urgent`-aware value the R3 clamp itself uses that cycle), using
  `self._config.get(CONF_SAFETY_MARGIN_W, DEFAULT_SAFETY_MARGIN_W)`. Set on every
  `CycleResult(...)` construction reached after that point (the normal end-of-cycle result at
  ~572; the two earlier fault returns are before this point and keep the `0.0` default).
- Failing test (`tests/test_sensor.py`): `PeakHeadroomSensor` mirrors the
  `EffectivePeakLimitSensor` test shape (`native_value`, `None`-default, `unique_id`).
- Add `PeakHeadroomSensor(_CoordinatorFieldSensor)` (`_object_id_suffix =
  OWNED_SUFFIX_PEAK_HEADROOM_A`, `UnitOfElectricCurrent.AMPERE`). Register.
- Green, commit: `feat: add peak_headroom_a diagnostic sensor (#602)`.

## T3 — `time_to_full`

- Failing test (`tests/test_coordinator.py`): promoting `ROLE_EV_BATTERY_CAPACITY`'s read +
  R15 fallback (coordinator.py:420-425's read/fallback logic) to run unconditionally, ahead of
  `if deadline_resolvable:`, does not change `result`'s existing deadline-related fields for a
  cycle where the deadline branch's own tests already pass — a regression guard, not new
  behavior.
- Move the `effective_battery_capacity_kwh` read/resolution (coordinator.py:420-425) out of
  the `if deadline_resolvable:` block to run unconditionally just before it; the deadline
  branch keeps using the resulting local instead of computing it itself.
- Failing tests (`tests/test_coordinator.py`), three cases:
  1. Normal: known `effective_battery_capacity_kwh`, `ev_soc`, `active_soc_limit`, and this
     cycle's own commanded current (`desired`, before the R3/C4 clamps) → `result.time_to_full_min`
     matches the hand-computed minutes formula.
  2. Commanded current `== 0` → `result.time_to_full_min is None`.
  3. `ev_soc >= active_soc_limit` → `result.time_to_full_min == 0`.
- Add `time_to_full_min: float | None = None` to `CycleResult`; compute it in `_run_cycle`
  right after `desired` (the mode's resolved current, pre-clamp) is known — this is near the
  end of `_run_cycle`, alongside where `peak_headroom_a`/`solar_surplus_w` are already final,
  not near coordinator.py:394. Set on the normal end-of-cycle `CycleResult(...)` (~572); the
  two earlier fault returns keep the `None` default (soc/capacity not yet known at those
  points).
- Failing test (`tests/test_sensor.py`): `TimeToFullSensor` — reads `time_to_full_min` off
  `coordinator.data`; `None`-default when `data is None` or the field is absent (same shared
  behavior `_CoordinatorFieldSensor` already gives `EffectivePeakLimitSensor`; confirmed its
  `_field_default` only substitutes when the attribute is absent, never when present as `0` or
  `None` — no bespoke class needed); `unique_id`.
- Add `TimeToFullSensor(_CoordinatorFieldSensor)` to `sensor.py` (`_object_id_suffix =
  OWNED_SUFFIX_TIME_TO_FULL`, `UnitOfTime.MINUTES`, `_coordinator_field = "time_to_full_min"`).
  Add `OWNED_SUFFIX_TIME_TO_FULL = "time_to_full"` to `const.py`. Register.
- Green, commit: `feat: add time_to_full diagnostic sensor (#602)`.

## T4 — `adapter_readings`

- Add `ROLES_ADAPTER_READINGS_EXCLUDED = frozenset({ROLE_NOTIFICATION_TARGET})` to `const.py`
  (explicit constant, not a `read()`-duck-typing check — `NotifyAdapter` also has a `read()`
  and `ROLE_VEHICLE_CHARGE_LIMIT` is read/write, so neither works as a filter).
- Add `OWNED_SUFFIX_ADAPTER_READINGS = "adapter_readings"` to `const.py`.
- In `SmartChargingCoordinator.__init__`, add `self._role_readings: dict[str, Any] = {}` and
  `self._role_readings_at: datetime | None = None` (same persisted-across-cycles lifetime as
  `self._net_window`/`self._peak_demand`).
- Failing test (`tests/test_coordinator.py`): after a `_run_cycle` that reads `status`, `net_w`,
  `charger_w` (and `measured_v`/`ev_soc` when wired), `self._role_readings` (via a test seam or
  by asserting on the returned `result.adapter_readings`, whichever T1-T3 already established)
  contains those roles' values.
- At every point in `_run_cycle` that already reads a role — `status`
  (`ROLE_CHARGER_STATUS`), `net_w` (`ROLE_NET_POWER`), `charger_w` (`ROLE_CHARGER_POWER`),
  `measured_v` (`ROLE_GRID_VOLTAGE`, when present), `ev_soc` (`ROLE_EV_SOC`, when read), and
  T3's promoted `effective_battery_capacity_kwh` read (`ROLE_EV_BATTERY_CAPACITY`) — also write
  that role's value into `self._role_readings[ROLE_...]` and set `self._role_readings_at =
  now_dt`. No new reads added beyond T3's already-disclosed one.
- Failing test (`tests/test_coordinator.py`): a role wired but not read on a given cycle (e.g.
  `ev_soc` when the car isn't connected) keeps its prior cycle's cached value in
  `result.adapter_readings` rather than disappearing or going `None`; a role never yet read
  renders `None`; a role no longer present in `self._adapters` (unwired) is absent from
  `result.adapter_readings` even though it may still be in the internal cache. A cycle that
  faults on a required role (missing `status`/`net_w`/`charger_w`) still returns a
  `result.adapter_readings` reflecting whatever was cached before the fault, not `{}`.
- Add `adapter_readings: dict[str, Any] = field(default_factory=dict)` and
  `adapter_readings_at: datetime | None = None` to `CycleResult`. At **every**
  `CycleResult(...)` construction site (~212, ~230, ~274, ~572), set
  `adapter_readings={role: self._role_readings.get(role) for role in self._adapters if role
  not in ROLES_ADAPTER_READINGS_EXCLUDED}` and `adapter_readings_at=self._role_readings_at`.
- Failing test (`tests/test_sensor.py`): `AdapterReadingsSensor` — `native_value` reads
  `adapter_readings_at`; `extra_state_attributes` reads `adapter_readings` (defaults to `{}`
  when `data is None`); `unique_id`; `device_class == SensorDeviceClass.TIMESTAMP`;
  `entity_category == EntityCategory.DIAGNOSTIC`.
- Add `AdapterReadingsSensor(_CoordinatorPushMixin, SensorEntity)` to `sensor.py`
  (`_object_id_suffix = OWNED_SUFFIX_ADAPTER_READINGS`, `_attr_entity_category =
  EntityCategory.DIAGNOSTIC`). Register.
- Green, commit: `feat: add adapter_readings diagnostic sensor (ADR-0021, #602)`.

## T5 — Translations

- Add `entity.sensor.{solar_surplus_w,time_to_full,peak_headroom_a,adapter_readings}.name` to
  `strings.json`, `translations/en.json`, `translations/nl.json` (Dutch names, matching the
  existing four sensors' translation style).
- No test (translation content, not behavior) — verify with `ruff check .` /
  `ruff format --check .` and a manual read-through for the Dutch wording, per T5.2's precedent.
- Commit: `feat: translate dashboard-prerequisite sensor names (#602)`.

## T6 — Integration checkpoint

- Failing test (`tests/test_sensor.py` or a config-entry setup test): `async_setup_entry`
  registers all nine `sensor.smart_charging_*` entities with no duplicate `unique_id` and no
  duplicate `_object_id_suffix` (ADR-0013) — a concrete assertion over the entities list, not a
  manual step.
- Full HA-harness suite green (`pytest tests/`), `ruff check .`, `ruff format --check .`.
- Report status; this closes #602 (both halves — catalog row already merged via #605).
