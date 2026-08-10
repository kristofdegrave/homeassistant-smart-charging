# TDD plan: dashboard-prerequisite diagnostic sensors (#602)

Derived from `docs/plans/2026-08-10-dashboard-prerequisite-sensors-design.md`. Branch:
`feature/dashboard-prerequisite-sensors`. Test boundary throughout: HA harness (ADR-0009) —
every task touches `coordinator.py`, `sensor.py`, or their entity-registration tests.

## T1 — `CycleResult` fields + `solar_surplus_w`

- Failing test (`tests/test_coordinator.py`): a `_run_cycle` with known `charger_w`/`net_w`
  asserts `result.solar_surplus_w == charger_w - smoothed_net_w` for at least two cases
  (surplus positive, surplus negative/importing).
- Add `solar_surplus_w: float = 0.0` to `CycleResult` (`coordinator.py`). Set it from the
  already-computed `surplus_w` local at every `CycleResult(...)` construction site that reaches
  that point in `_run_cycle` (the two early-fault returns before `surplus_w` exists keep the
  default).
- Failing test (`tests/test_sensor.py`): `SolarSurplusSensor` reads `solar_surplus_w` off
  `coordinator.data`, defaults to `None` when `data is None`, `unique_id ==
  "<entry_id>_solar_surplus_w"`.
- Add `SolarSurplusSensor(_CoordinatorFieldSensor)` to `sensor.py` (translation_key/
  object_id_suffix `solar_surplus_w`, `UnitOfPower.WATT`). Register in `async_setup_entry`.
- Green, commit: `feat: add solar_surplus_w diagnostic sensor (#602)`.

## T2 — `peak_headroom_a`

- Failing test (`tests/test_coordinator.py`): a `_run_cycle` with known `net_w`, `charger_w`,
  `voltage`, `effective_peak_limit_kw`, `safety_margin_w` asserts `result.peak_headroom_a ==
  floor((effective_peak_limit_kw*1000 - safety_margin_w - (net_w - charger_w)) / voltage)` —
  hand-computed per the design doc's formula, cross-checked against
  `entity-catalog.md:153`/`control-cycle.md` step 5.
- Add `peak_headroom_a: float = 0.0` to `CycleResult`; compute it in `_run_cycle` right after
  `effective_peak_limit_kw`'s final (non-provisional) resolution (coordinator.py ~476-484, so it
  reflects the same `urgent`-aware value the R3 clamp itself uses that cycle), using
  `self._config.get(CONF_SAFETY_MARGIN_W, DEFAULT_SAFETY_MARGIN_W)`. Set on every
  `CycleResult(...)` construction reached after that point.
- Failing test (`tests/test_sensor.py`): `PeakHeadroomSensor` mirrors the
  `EffectivePeakLimitSensor` test shape (`native_value`, `None`-default, `unique_id`).
- Add `PeakHeadroomSensor(_CoordinatorFieldSensor)` (`UnitOfElectricCurrent.AMPERE`). Register.
- Green, commit: `feat: add peak_headroom_a diagnostic sensor (#602)`.

## T3 — `time_to_full`

- Failing tests (`tests/test_coordinator.py`), three cases:
  1. Normal: known `capacity_kwh`, `ev_soc`, `active_soc_limit`, `charger_current`, `voltage` →
     `result.time_to_full_min` matches the hand-computed minutes formula.
  2. `charger_current == 0` → `result.time_to_full_min is None`.
  3. `ev_soc >= active_soc_limit` → `result.time_to_full_min == 0`.
- Add `time_to_full_min: float | None = None` to `CycleResult`; compute in `_run_cycle` once
  `active_soc_limit` is resolved (after coordinator.py:394) and `charger_current` has been read
  (read `ROLE_CHARGER_CURRENT` there if not already read earlier in the cycle — check for an
  existing read of this role before adding a new one, per the design doc's "no extra adapter
  reads" constraint; if the mode dispatch further down already reads it for the write step,
  reuse that value instead of reading twice).
- Failing test (`tests/test_sensor.py`): `TimeToFullSensor` — reads `time_to_full_min` off
  `coordinator.data`; `None`-default when `data is None` (same as the other three); `unique_id`.
- Add `TimeToFullSensor(_CoordinatorPushMixin, SensorEntity)` (bespoke `native_value`, per the
  design doc — `_CoordinatorFieldSensor`'s shared `None`-default already matches, so this can
  reuse `_CoordinatorFieldSensor` too if its default-handling covers the "0 is a real value"
  case, which it does: `_field_default` only applies when the attribute is *absent*, not when
  it's `0` or `None` — confirm this before assuming a bespoke class is needed; if
  `_CoordinatorFieldSensor` suffices, use it and drop the bespoke subclass from the design).
  `UnitOfTime.MINUTES`. Register.
- Green, commit: `feat: add time_to_full diagnostic sensor (#602)`.

## T4 — `adapter_readings`

- Failing test (`tests/test_coordinator.py`): a `_run_cycle` with a known set of wired adapters
  (including `ROLE_NOTIFICATION_TARGET` if the test fixture wires one) asserts
  `result.adapter_readings` contains one key per wired *read* role, excludes
  `notification_target`, and a role whose fake adapter returns `None` this cycle shows up as
  `None` in the dict without `result.fault` being `True`. Also assert
  `result.adapter_readings_at` equals `now_dt` for that cycle.
- Add `adapter_readings: dict[str, Any] = field(default_factory=dict)` and
  `adapter_readings_at: datetime | None = None` to `CycleResult`. In `_run_cycle`, after the
  early-fault gates, build the dict from `self._adapters` (excluding
  `ROLE_NOTIFICATION_TARGET`) — reuse each role's value already read earlier in the cycle where
  one exists (`status`, `net_w`, `charger_w`, `voltage`/`measured_v`, `ev_soc`); for any wired
  role not already read this cycle by that point, read it fresh (this is the one role, if any,
  where "no extra adapter reads" can't be honored literally — note in a code comment which role
  this applies to once the actual wired-role set for this cycle is known, and confirm during
  implementation whether any such role remains after reusing T1-T3's reads).
- Failing test (`tests/test_sensor.py`): `AdapterReadingsSensor` — `native_value` reads
  `adapter_readings_at`; `extra_state_attributes` reads `adapter_readings` (defaults to `{}`
  when `data is None`); `unique_id`; `device_class == SensorDeviceClass.TIMESTAMP`.
- Add `AdapterReadingsSensor(_CoordinatorPushMixin, SensorEntity)` to `sensor.py`. Register.
- Green, commit: `feat: add adapter_readings diagnostic sensor (ADR-0021, #602)`.

## T5 — Translations

- Add `entity.sensor.{solar_surplus_w,time_to_full,peak_headroom_a,adapter_readings}.name` to
  `strings.json`, `translations/en.json`, `translations/nl.json` (Dutch names, matching the
  existing four sensors' translation style).
- No test (translation content, not behavior) — verify with `ruff check .` /
  `ruff format --check .` and a manual read-through for the Dutch wording, per T5.2's precedent.
- Commit: `docs: translate dashboard-prerequisite sensor names (#602)`.

## T6 — Integration checkpoint

- Full HA-harness suite green (`pytest tests/`), `ruff check .`, `ruff format --check .`.
- Manual sanity check: confirm all nine `sensor.smart_charging_*` entities register with no
  duplicate `unique_id`/`object_id` collisions (ADR-0013) in a live HA dev instance if one is
  available; otherwise rely on the entity-registration tests in T1-T4.
- Report status; this closes #602 (both halves — catalog row already merged via #605).
