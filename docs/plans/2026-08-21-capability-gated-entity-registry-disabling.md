# Capability-Gated Entity Registry Disabling Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Registry-level `disabled_by` gating for `SolarSurplusSensor` (`solar_available`) and the
9 `SmartChargingDepartureTime` entities (`deadline_available`), per
[ADR-0028](../adl/0028-registry-level-disabling-for-capability-gated-entities.md); replace
`entity.py`'s `async_added_to_hass`-based label sync with a unified setup-time mechanism, applied
uniformly to every `_owned_labels`-carrying class. `captar_available` gates no entity — out of
scope, per the ADR's Context.

**Architecture:** Two new module-level functions in `entity.py` (`sync_disabled_by`,
`sync_labels`); `SmartChargingEntity.async_added_to_hass` loses its registry-write body;
`sensor.py`/`time.py`/`switch.py`/`number.py`/`select.py`'s `async_setup_entry` functions each
gain calls to the two new helpers. No new module, no config-entry schema change.
Full design: [`2026-08-21-capability-gated-entity-registry-disabling-design.md`](2026-08-21-capability-gated-entity-registry-disabling-design.md).

**Tech Stack:** Python ≥3.12, `pytest-homeassistant-custom-component` (HA harness, ADR-0009 — every
task here touches the entity registry), `ruff`.

**Model:** Per CLAUDE.md, this is development work — execute on **Sonnet**.

---

## Conventions used throughout

- **Named constants, no magic strings** (CLAUDE.md) — `Platform.SENSOR`/`Platform.TIME` etc.,
  never a bare `"sensor"`/`"time"` string, for the `sync_disabled_by` platform argument.
- **`git commit --author="Claude <noreply@anthropic.com>"`** with the trailer
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- Re-check `git branch --show-current` before every commit (shared checkout).
- Test docstrings name the ADR-0028 mechanism and which capability/entity they exercise.
- `tests/test_entity_labels.py`'s existing tests call `entity.async_added_to_hass()` directly to
  exercise the label sync — since that sync moves out of the hook, these become tests of
  `sync_labels()` called against a registry directly (T1 rewrites them; this is expected
  test churn, not a regression).
- **After every task, run the full existing test suite for the touched file(s)** — do not defer
  to the end.

---

## Phase 0 — `entity.py`: the two setup-time helpers

### Task 0.1: `sync_disabled_by`

**ADR honored:** ADR-0028 (Option C). **Test boundary:** HA harness,
`tests/test_entity_labels.py` (existing file — the registry-sync home for `SmartChargingEntity`;
rename/extend rather than create a new file, since it's no longer label-only).

**Files:**
- Edit: `custom_components/smart_charging/entity.py`
- Edit: `tests/test_entity_labels.py`

**Step 1: Write the failing tests**
- `test_sync_disabled_by_disables_when_capability_absent`: a `_LabelledEntity`-style fixture
  already registered (`disabled_by=None`); call `sync_disabled_by(registry, platform, unique_id,
  capability_met=False)`; assert `disabled_by == RegistryEntryDisabler.INTEGRATION`.
- `test_sync_disabled_by_reenables_when_capability_returns`: same fixture, pre-set
  `disabled_by=RegistryEntryDisabler.INTEGRATION`; call with `capability_met=True`; assert
  `disabled_by is None`.
- `test_sync_disabled_by_never_overrides_user_disable`: fixture pre-set
  `disabled_by=RegistryEntryDisabler.USER`; call with both `capability_met=True` and `False` in
  turn; assert `disabled_by` stays `USER` after each.
- `test_sync_disabled_by_is_idempotent`: call twice with the same `capability_met`; assert no
  second state change (compare `registry.async_get(entity_id)` before/after the second call).
- `test_sync_disabled_by_noop_when_not_yet_registered`: call with a `unique_id` that has no
  registry row; assert no exception and no registry mutation.

**Step 2: Minimal implementation** — add `sync_disabled_by` to `entity.py`, per the design doc §2.1.

**Step 3: Verify green** — `pytest tests/test_entity_labels.py -v`.

**Step 4: Commit** — `feat: add sync_disabled_by registry helper (ADR-0028)`.

### Task 0.2: `sync_labels`, and retire the `async_added_to_hass` registry write

**ADR honored:** ADR-0028 (Option C). **Test boundary:** HA harness, `tests/test_entity_labels.py`.

**Files:**
- Edit: `custom_components/smart_charging/entity.py`
- Edit: `tests/test_entity_labels.py`

**Step 1: Write the failing tests**
- `test_sync_labels_applies_owned_labels`: registered entity, no labels; call
  `sync_labels(registry, entity_id, owned_labels=frozenset({LABEL_SC_RUNTIME}),
  manageable_labels=frozenset())`; assert the label is present.
- `test_sync_labels_removes_label_when_owned_labels_drops_it`: entity already carrying
  `LABEL_SC_RUNTIME`; call with `owned_labels=frozenset()`,
  `manageable_labels=frozenset({LABEL_SC_RUNTIME})`; assert the label is gone.
- `test_sync_labels_merges_with_a_users_own_label`: entity carrying a user-added label plus
  `LABEL_SC_RUNTIME`; call with `owned_labels=frozenset({LABEL_SC_RUNTIME})`; assert both the
  user's label and `LABEL_SC_RUNTIME` survive (migrates
  `test_owned_labels_merge_with_a_users_own_label`).
- `test_sync_labels_noop_with_no_owned_or_manageable_labels`: call with both frozenset empty;
  assert no registry write occurs (migrates `test_default_owned_labels_is_empty`'s intent).
- `test_async_added_to_hass_no_longer_writes_registry`: replaces
  `test_owned_labels_applied_on_add` — construct a `_LabelledEntity`, call
  `await entity.async_added_to_hass()` directly (no registry `sync_labels` call), assert the
  registry's labels are **unchanged** (proving the hook is now a pure pass-through).
- `test_async_added_to_hass_still_delegates_restore_state`: unchanged, already asserts the MRO
  delegation this task must not break.

**Step 2: Minimal implementation** — add `sync_labels`; delete the registry-write body of
`SmartChargingEntity.async_added_to_hass`, leaving the `await super().async_added_to_hass()`
delegation.

**Step 3: Verify green** — `pytest tests/test_entity_labels.py -v`.

**Step 4: Commit** — `feat: add sync_labels registry helper, retire hook-based sync (ADR-0028)`.

---

## Phase 1 — `sensor.py`: `SolarSurplusSensor`

### Task 1.1: capability-gate `SolarSurplusSensor`

**ADR honored:** ADR-0028. **Test boundary:** HA harness, `tests/test_sensor.py`.

**Files:**
- Edit: `custom_components/smart_charging/sensor.py`
- Edit: `tests/test_sensor.py`

**Step 1: Write the failing tests**
- `test_solar_surplus_sensor_disabled_by_default_when_solar_unavailable`: set up the sensor
  platform with `solar_available=False` on a fresh config entry; assert the registered entity's
  `disabled_by == RegistryEntryDisabler.INTEGRATION` immediately after first setup.
- `test_solar_surplus_sensor_enabled_when_solar_available`: same, `solar_available=True`; assert
  `disabled_by is None`.
- `test_solar_surplus_sensor_reenables_on_reload_when_capability_returns`: set up with
  `solar_available=False`, reload the entry with `solar_available=True`; assert `disabled_by`
  clears.
- `test_solar_surplus_sensor_disables_on_reload_when_capability_removed`: reverse of the above.
- `test_solar_surplus_sensor_sync_labels_is_a_noop`: assert no label appears on the entity after
  setup (it has no `_owned_labels`) — the explicit "no bug here" case the design doc calls for.

**Step 2: Minimal implementation** — add `solar_available: bool` to `SolarSurplusSensor.__init__`,
setting `_attr_entity_registry_enabled_default`; wire `sync_disabled_by`/`sync_labels` calls into
`async_setup_entry` around `async_add_entities`, per the design doc §3.1. Do not touch
`MonthlyPeakSensor`/`EffectivePeakLimitSensor`/`PeakHeadroomSensor`.

**Step 3: Verify green** — `pytest tests/test_sensor.py -v`.

**Step 4: Commit** — `feat: gate SolarSurplusSensor's registry state on solar_available (ADR-0028)`.

---

## Phase 2 — `time.py`: `SmartChargingDepartureTime`

### Task 2.1: capability-gate `SmartChargingDepartureTime`'s registry state

**ADR honored:** ADR-0028. **Test boundary:** HA harness, `tests/test_time.py`.

**Files:**
- Edit: `custom_components/smart_charging/time.py`
- Edit: `tests/test_time.py`

**Step 1: Write the failing tests**
- `test_departure_time_disabled_by_default_when_deadline_unavailable`: fresh setup,
  `deadline_available=False`; assert every one of the 9 entities has
  `disabled_by == RegistryEntryDisabler.INTEGRATION`.
- `test_departure_time_enabled_when_deadline_available`: `deadline_available=True`; assert
  `disabled_by is None` for all 9.
- `test_departure_time_label_and_disabled_by_both_reflect_capability`: `deadline_available=False`;
  assert **both** `disabled_by == INTEGRATION` **and** `LABEL_SC_RUNTIME` is absent — the one
  entity exercising both mechanisms together (design doc §5).
- `test_departure_time_user_disable_survives_capability_toggle`: set `deadline_available=True`,
  then simulate a user-initiated `disabled_by=RegistryEntryDisabler.USER`; reload with
  `deadline_available=False` then `True` again; assert `disabled_by` stays `USER` throughout, and
  the label still correctly tracks `deadline_available` (per the design's Decision — labels are
  independent of `disabled_by`).
- `test_departure_time_restored_value_does_not_survive_disable_cycle`: set a non-default time,
  reload with `deadline_available=False` (disabling it), reload again with `True`; assert the
  entity's value is back to its R14 constructor default, **not** the previously-set time —
  documents the accepted risk (design doc §4) as a passing assertion, not a TODO.

**Step 2: Minimal implementation** — add `_attr_entity_registry_enabled_default` alongside the
existing `_owned_labels` assignment in `SmartChargingDepartureTime.__init__`; wire
`sync_disabled_by` (before) and `sync_labels` (after, using each instance's own labels) into
`async_setup_entry`, per the design doc §3.2.

**Step 3: Verify green** — `pytest tests/test_time.py -v`.

**Step 4: Commit** — `feat: gate SmartChargingDepartureTime's registry state on deadline_available (ADR-0028)`.

---

## Phase 3 — Call-site move for the five non-gated classes

### Task 3.1: `HomeDaySwitch`

**ADR honored:** ADR-0028 (Consequences — uniform application). **Test boundary:** HA harness,
`tests/test_switch.py`.

**Files:**
- Edit: `custom_components/smart_charging/switch.py`
- Edit: `tests/test_switch.py`

**Step 1: Write the failing test** — `test_home_day_switch_carries_runtime_label_after_setup`:
set up the switch platform; assert `LABEL_SC_RUNTIME` is present on the entity — same outcome
`test_entity_labels.py` used to prove generically, now asserted at the platform level to confirm
the call-site move didn't drop it for this specific entity.

**Step 2: Minimal implementation** — call `sync_labels` in `switch.py`'s `async_setup_entry`,
after `async_add_entities`.

**Step 3: Verify green** — `pytest tests/test_switch.py -v`.

**Step 4: Commit** — `refactor: move HomeDaySwitch's label sync to setup time (ADR-0028)`.

### Task 3.2: `TargetCurrentNumber`, `SocLimitOverrideNumber`

**ADR honored:** ADR-0028. **Test boundary:** HA harness, `tests/test_number.py`.

**Files:**
- Edit: `custom_components/smart_charging/number.py`
- Edit: `tests/test_number.py`

**Step 1: Write the failing tests** — one per entity, same shape as Task 3.1's.

**Step 2: Minimal implementation** — call `sync_labels` for both entities in `number.py`'s
`async_setup_entry`, after `async_add_entities`.

**Step 3: Verify green** — `pytest tests/test_number.py -v`.

**Step 4: Commit** — `refactor: move number entities' label sync to setup time (ADR-0028)`.

### Task 3.3: `ModeSelect`, `ProfileSelect`

**ADR honored:** ADR-0028. **Test boundary:** HA harness, `tests/test_select.py`.

**Files:**
- Edit: `custom_components/smart_charging/select.py`
- Edit: `tests/test_select.py`

**Step 1: Write the failing tests** — one per entity, same shape as Task 3.1's.

**Step 2: Minimal implementation** — call `sync_labels` for both entities in `select.py`'s
`async_setup_entry`, after `async_add_entities`.

**Step 3: Verify green** — `pytest tests/test_select.py -v`.

**Step 4: Commit** — `refactor: move select entities' label sync to setup time (ADR-0028)`.

---

## Phase 4 — Final verification

### Task 4.1: Full regression + ADR-0028 audit

**ADR honored:** ADR-0028 (all). **Test boundary:** HA harness, full suite.

**Steps:**
1. Run the full test suite (`pytest`); confirm no test outside the files this plan touched
   changed behavior.
2. Re-read ADR-0028's Consequences bullet-by-bullet against the actual diff — confirm every file
   named there was touched exactly as described and nothing else was.
3. Confirm `MonthlyPeakSensor`/`EffectivePeakLimitSensor`/`PeakHeadroomSensor` have zero diff in
   `sensor.py` (the out-of-scope guard from the design doc §1).
4. Confirm `ruff check .` and `ruff format --check .` both pass.

**Step 4: Commit** (only if the audit finds something to fix) — otherwise this task closes with
no commit, just the verification record in the PR description.
