# Capability-Gated Entity Registry Disabling Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Registry-level `disabled_by` gating for `SolarSurplusSensor` (`solar_available`) and the
9 `SmartChargingDepartureTime` entities (`deadline_available`), per
[ADR-0028](../adl/0028-registry-level-disabling-for-capability-gated-entities.md); replace
`entity.py`'s `async_added_to_hass`-based label sync with a unified setup-time mechanism, applied
uniformly to every `_owned_labels`-carrying class. `captar_available` gates no entity — out of
scope, per the ADR's Context.

**Architecture:** Two new module-level functions in `entity.py` (`sync_disabled_by`,
`sync_labels`); `SmartChargingEntity.async_added_to_hass` loses its registry-write body **only
once every call site below exists** (Task 3.4, deliberately last — see Conventions); `sensor.py`/
`time.py`/`switch.py`/`number.py`/`select.py`'s `async_setup_entry` functions each gain calls to
the two new helpers. No new module, no config-entry schema change.
Full design: [`2026-08-21-capability-gated-entity-registry-disabling-design.md`](2026-08-21-capability-gated-entity-registry-disabling-design.md).

**Tech Stack:** Python ≥3.12, `pytest-homeassistant-custom-component` (HA harness, ADR-0009 — every
task here touches the entity registry), `ruff`.

**Model:** Per CLAUDE.md, this is development work — execute on **Sonnet**.

---

## Conventions used throughout

- **Named constants, no magic strings** (CLAUDE.md) — `Platform.SENSOR`/`Platform.TIME` etc.,
  never a bare `"sensor"`/`"time"` string, for `sync_disabled_by`/`sync_labels`'s `domain`
  argument.
- **`git commit --author="Claude <noreply@anthropic.com>"`** with the trailer
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- Re-check `git branch --show-current` before every commit (shared checkout).
- Test docstrings name the ADR-0028 mechanism and which capability/entity they exercise.
- **The old hook and the new mechanism coexist, on purpose, until Task 3.4.** Task 0.2 adds
  `sync_labels` and rewrites `tests/test_entity_labels.py`'s three unit-level tests to call it
  directly — those tests never depended on the hook's *body*, only on a registered `entity_id`
  existing, so rewriting them doesn't require the hook to be touched yet. `entity.py`'s hook
  keeps writing labels, unchanged, through Phases 1–3; each phase's new `sync_labels` call
  writes the identical, already-merged result redundantly. Only Task 3.4, once every
  `_owned_labels` class has its new call site, deletes the hook. **This ordering exists
  specifically so the suite never goes red waiting for a call site that doesn't exist yet** — do
  not reorder it.
- Files touched beyond the obvious per-task edits, called out so no task discovers them
  mid-implementation: `tests/test_time.py:172-296` (platform-level label assertions, driven
  through a real `async_setup_entry` call — stay green throughout per the point above, revisited
  in Task 2.1) and `tests/test_init.py:145-235` (full-setup assertions that every runtime entity
  carries `sc_runtime` and diagnostics carry none — revisited in Task 3.4 and Task 4.1).
- **After every task, run the full existing test suite for the touched file(s)** — do not defer
  to the end.

---

## Phase 0 — `entity.py`: the two setup-time helpers

### Task 0.1: `sync_disabled_by`

**ADR honored:** ADR-0028 (Option C). **Test boundary:** HA harness,
`tests/test_entity_labels.py` (existing file — the registry-sync home for `SmartChargingEntity`;
it stops being label-only after this task, so update its module docstring accordingly).

**Files:**
- Edit: `custom_components/smart_charging/entity.py`
- Edit: `tests/test_entity_labels.py`

**Step 1: Write the failing tests**
- `test_sync_disabled_by_disables_when_capability_absent`: register a `_LabelledEntity`-style
  fixture (`disabled_by=None`); call `sync_disabled_by(registry, domain, unique_id,
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

**Step 2: Minimal implementation** — add `sync_disabled_by` to `entity.py`, per the design doc
§2.1 (keyed on `domain`/`unique_id`, guards both a missing `entity_id` and a missing registry
entry).

**Step 3: Verify green** — `pytest tests/test_entity_labels.py -v`.

**Step 4: Commit** — `feat: add sync_disabled_by registry helper (ADR-0028)`.

### Task 0.2: `sync_labels`

**ADR honored:** ADR-0028 (Option C). **Test boundary:** HA harness, `tests/test_entity_labels.py`.

**Files:**
- Edit: `custom_components/smart_charging/entity.py`
- Edit: `tests/test_entity_labels.py`

**Step 1: Write the failing tests, and rewrite the three existing hook-driven ones**
- `test_sync_labels_applies_owned_labels`: register an entity with no labels (via
  `MockEntityPlatform.async_add_entities`, same as today — this only needs a real registry row,
  not the hook); call `sync_labels(registry, domain, unique_id,
  owned_labels=frozenset({LABEL_SC_RUNTIME}))`; assert the label is present. Replaces
  `test_owned_labels_applied_on_add`.
- `test_sync_labels_removes_label_when_owned_labels_drops_it`: entity already carrying
  `LABEL_SC_RUNTIME`; call with `owned_labels=frozenset()`,
  `manageable_labels=frozenset({LABEL_SC_RUNTIME})`; assert the label is gone.
- `test_sync_labels_merges_with_a_users_own_label`: entity carrying a user-added label plus
  `LABEL_SC_RUNTIME`; call `sync_labels(registry, domain, unique_id,
  owned_labels=frozenset({LABEL_SC_RUNTIME}))` (relying on `manageable_labels`'s default);
  assert both the user's label and `LABEL_SC_RUNTIME` survive. Replaces
  `test_owned_labels_merge_with_a_users_own_label`.
- `test_sync_labels_noop_with_no_owned_or_manageable_labels`: call with both frozenset empty;
  assert no registry write occurs. Replaces `test_default_owned_labels_is_empty`.
- `test_sync_labels_noop_when_not_yet_registered`: call with a `unique_id` that has no registry
  row; assert no exception and no registry mutation (mirrors Task 0.1's equivalent case).
- Leave `test_async_added_to_hass_still_delegates_restore_state` untouched — it tests
  `_RestoringLabelledEntity`'s own override, not the hook, and stays a valid MRO regression guard
  through every later task including Task 3.4.

**Step 2: Minimal implementation** — add `sync_labels` to `entity.py`, per the design doc §2.2.
**Do not touch `SmartChargingEntity.async_added_to_hass` in this task** — the hook keeps writing
labels unchanged until Task 3.4 (Conventions, above).

**Step 3: Verify green** — `pytest tests/test_entity_labels.py -v`, then the full suite (the hook
is untouched, so nothing else should move).

**Step 4: Commit** — `feat: add sync_labels registry helper (ADR-0028)`.

---

## Phase 1 — `sensor.py`: `SolarSurplusSensor`

### Task 1.1: capability-gate `SolarSurplusSensor`

**ADR honored:** ADR-0028. **Test boundary:** HA harness, `tests/test_sensor.py`.

**Files:**
- Edit: `custom_components/smart_charging/sensor.py`
- Edit: `tests/test_sensor.py`

**Step 1: Update existing call sites, then write the failing tests**
- First, add `solar_available=True` explicitly to every existing `SolarSurplusSensor(...)`
  construction in `tests/test_sensor.py` (the direct constructions, the parametrized-loop ones,
  and the full-setup ones) — this is a required, mechanical pass, not incidental clean-up: the
  new `= False` constructor default (matching `ModeSelect`'s own convention) would otherwise
  silently disable the sensor in every one of those pre-existing tests. Run the suite after this
  step alone; it must still be green before writing any new test.
- `test_solar_surplus_sensor_disabled_by_default_when_solar_unavailable`: set up the sensor
  platform with `solar_available=False` on a fresh config entry; assert the registered entity's
  `disabled_by == RegistryEntryDisabler.INTEGRATION` immediately after first setup.
- `test_solar_surplus_sensor_enabled_when_solar_available`: same, `solar_available=True`; assert
  `disabled_by is None`.
- `test_solar_surplus_sensor_reenables_on_reload_when_capability_returns`: set up with
  `solar_available=False`, reload the entry with `solar_available=True`; assert `disabled_by`
  clears.
- `test_solar_surplus_sensor_disables_on_reload_when_capability_removed`: reverse of the above.
- `test_solar_surplus_sensor_config_read_matches_other_platforms`: assert `async_setup_entry`
  resolves the flag via `entry.data.get(CONF_SOLAR_AVAILABLE, ...)`, not via
  `entry.runtime_data.coordinator._config` — a regression guard against the private-attribute
  access path this task must not introduce (design doc §3.1).

**Step 2: Minimal implementation** — add `solar_available: bool = False` to
`SolarSurplusSensor.__init__`, setting `_attr_entity_registry_enabled_default`; wire the
`sync_disabled_by` call into `async_setup_entry` before `async_add_entities`, reading the flag
via `entry.data.get(CONF_SOLAR_AVAILABLE, DEFAULT_SOLAR_AVAILABLE)`, per the design doc §3.1. No
`sync_labels` call for this sensor (it carries no `_owned_labels`). Do not touch
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
  entity exercising both mechanisms together (design doc §5). This must pass whether or not the
  entity was added to hass this reload, proving `sync_labels`'s unique_id-keyed lookup (§2.2)
  actually works for the disabled case, not just the enabled one.
- `test_departure_time_user_disable_survives_capability_toggle`: set `deadline_available=True`,
  then simulate a user-initiated `disabled_by=RegistryEntryDisabler.USER`; reload with
  `deadline_available=False` then `True` again; assert `disabled_by` stays `USER` throughout, and
  the label still correctly tracks `deadline_available` (per the design's Decision — labels are
  independent of `disabled_by`).
- `test_departure_time_restored_value_survives_disable_cycle`: set a non-default time, reload
  with `deadline_available=False` (disabling it), reload again with `True`; assert the entity's
  value is still the previously-set time, not its R14 constructor default — documents the actual
  (safe) `RestoreEntity` behavior as a passing assertion, not a TODO. (Corrected mid-task from
  this task's original `does_not_survive`/"accepted risk" framing once empirical testing showed
  the value actually survives; see ADR-0028's Context and issue #804.)
- Re-run `tests/test_time.py:172-296`'s existing platform-level label assertions unchanged — they
  must still pass (the hook is still active; this task additionally wires the new `sync_labels`
  call, which writes the identical result).

**Step 2: Minimal implementation** — add `_attr_entity_registry_enabled_default` alongside the
existing `_owned_labels` assignment in `SmartChargingDepartureTime.__init__`; wire
`sync_disabled_by` (before `async_add_entities`) and `sync_labels` (after, passing each
instance's own `_owned_labels`) into `async_setup_entry`, per the design doc §3.2. Do **not**
touch `SmartChargingEntity.async_added_to_hass` yet.

**Step 3: Verify green** — `pytest tests/test_time.py -v`, then the full suite.

**Step 4: Commit** — `feat: gate SmartChargingDepartureTime's registry state on deadline_available (ADR-0028)`.

---

## Phase 3 — Call-site move for the five non-gated classes, then retire the hook

### Task 3.1: `HomeDaySwitch`

**ADR honored:** ADR-0028 (Consequences — uniform application). **Test boundary:** HA harness,
`tests/test_switch.py`.

**Files:**
- Edit: `custom_components/smart_charging/switch.py`
- Edit: `tests/test_switch.py`

**Step 1: Write the failing test** — `test_home_day_switch_carries_runtime_label_after_setup`:
build a `MockConfigEntry` with `runtime_data` populated the same way `switch.py`'s
`async_setup_entry` expects (mirror the existing `test_init.py` full-setup fixture rather than
`test_switch.py`'s current direct `MockEntityPlatform` construction, since this test must exercise
`async_setup_entry` itself, not just the entity class); call `async_setup_entry`; assert
`LABEL_SC_RUNTIME` is present on the registered entity — the same outcome
`test_entity_labels.py` used to prove generically, now asserted at the platform level to confirm
the call-site move didn't drop it for this specific entity.

**Step 2: Minimal implementation** — call `sync_labels` in `switch.py`'s `async_setup_entry`,
after `async_add_entities`. The old hook is still present and still fires too (Conventions) — both
writes are redundant, not conflicting.

**Step 3: Verify green** — `pytest tests/test_switch.py -v`.

**Step 4: Commit** — `refactor: move HomeDaySwitch's label sync to setup time (ADR-0028)`.

### Task 3.2: `TargetCurrentNumber`, `SocLimitOverrideNumber`

**ADR honored:** ADR-0028. **Test boundary:** HA harness, `tests/test_number.py`.

**Files:**
- Edit: `custom_components/smart_charging/number.py`
- Edit: `tests/test_number.py`

**Step 1: Write the failing tests** — one per entity, same `async_setup_entry`-through-a-real-
`MockConfigEntry` shape as Task 3.1's.

**Step 2: Minimal implementation** — call `sync_labels` for both entities in `number.py`'s
`async_setup_entry`, after `async_add_entities`.

**Step 3: Verify green** — `pytest tests/test_number.py -v`.

**Step 4: Commit** — `refactor: move number entities' label sync to setup time (ADR-0028)`.

### Task 3.3: `ModeSelect`, `ProfileSelect`

**ADR honored:** ADR-0028. **Test boundary:** HA harness, `tests/test_select.py`.

**Files:**
- Edit: `custom_components/smart_charging/select.py`
- Edit: `tests/test_select.py`

**Step 1: Write the failing tests** — one per entity, same `async_setup_entry`-through-a-real-
`MockConfigEntry` shape as Task 3.1's.

**Step 2: Minimal implementation** — call `sync_labels` for both entities in `select.py`'s
`async_setup_entry`, after `async_add_entities`.

**Step 3: Verify green** — `pytest tests/test_select.py -v`.

**Step 4: Commit** — `refactor: move select entities' label sync to setup time (ADR-0028)`.

### Task 3.4: Retire `SmartChargingEntity.async_added_to_hass`'s registry write

**ADR honored:** ADR-0028 (Option C). **Test boundary:** HA harness, `tests/test_entity_labels.py`
+ `tests/test_init.py`.

Every `_owned_labels`-carrying class now has its own `sync_labels` call site (Tasks 2.1, 3.1–3.3);
`SolarSurplusSensor` never needed one. This task is safe only now.

**Files:**
- Edit: `custom_components/smart_charging/entity.py`

**Step 1: Confirm the tests that must stay green without the hook** — no new test is written for
this task; `tests/test_init.py:145-235`'s full-setup assertions (every runtime entity carries
`sc_runtime`, diagnostics carry none) are the proof the deletion is safe, since they exercise the
real `async_setup_entry` path for every affected entity.

**Step 2: Delete `entity.py:49-74`'s `async_added_to_hass` method entirely** (not a pass-through
stub — see design doc §2.3 for why a stub would be pointless).

**Step 3: Verify green** — `pytest tests/test_entity_labels.py tests/test_init.py -v`, then the
full suite.

**Step 4: Commit** — `refactor: retire SmartChargingEntity's hook-based label sync (ADR-0028)`.

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
4. Add or update a `tests/test_init.py` case exercising the design doc §6 integration checkpoint
   directly if one doesn't already cover it: a full `async_setup_entry` → `async_unload_entry` →
   `async_setup_entry` cycle (options-flow reload, ADR-0008) with a capability flip in between,
   asserting the final registry state matches the design doc §5 table.
5. Confirm `ruff check .` and `ruff format --check .` both pass.
6. File a follow-up issue for the design doc §4 dashboard-tile deferral (`dashboard.py`'s static
   Power-flow tile for `sensor.smart_charging_solar_surplus_w`) rather than letting it go
   unrecorded.

**Step 4: Commit** (only if step 4 above adds/changes a test) — otherwise this task closes with
no commit, just the verification record in the PR description.
