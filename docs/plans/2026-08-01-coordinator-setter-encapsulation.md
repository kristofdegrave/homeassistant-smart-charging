# Coordinator Setter-Method Encapsulation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `set_active_mode`, `set_active_profile`, `set_target_current`, and
`set_soc_limit_override` to `SmartChargingCoordinator`, per
[ADR-0014](../adl/0014-state-mutation-encapsulation.md), and switch `select.py`/`number.py`'s four
write sites to call them instead of assigning the coordinator's fields directly. **Pure
boundary refactor**, with two deliberate observable exceptions (design doc §2, criteria 2 and 6):
the two numeric setters clamp out-of-range input at the coordinator's own field (mostly redundant
with the entities' own validation, §7), and `TargetCurrentNumber`/`SocLimitOverrideNumber`'s
`__init__` now also clamp their config-flow-sourced `default` — a path where the clamp was
genuinely missing before, for both fields, not just one.

**Architecture:** Four new methods on the existing `SmartChargingCoordinator` class in
`coordinator.py` — no new module. Full design:
[`2026-08-01-coordinator-setter-encapsulation-design.md`](2026-08-01-coordinator-setter-encapsulation-design.md).

**Tech Stack:** Python ≥3.12, `pytest-homeassistant-custom-component` (HA harness — every test
here, since `SmartChargingCoordinator` is HA-coupled per ADR-0006/0009), `ruff`.

**Model:** Per CLAUDE.md, this is development work — execute on **Sonnet**.

---

## Conventions used throughout

- **Named constants, no magic strings** (CLAUDE.md) — `SOC_LIMIT_OVERRIDE_MIN`/`MAX` replace the
  bare `50.0`/`100.0` literals in `number.py`.
- **`git commit --author="Claude <noreply@anthropic.com>"`** with the trailer
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- Re-check `git branch --show-current` before every commit (shared checkout).
- Test docstrings name ADR-0014 and the field the setter owns.
- **After every task, run the full existing test suite** (`tests/test_select.py`,
  `tests/test_number.py`, `tests/test_coordinator.py`, plus the three end-to-end suites,
  `tests/test_init.py`, and `tests/benchmarks/test_coordinator_perf.py`) — it must keep passing
  unchanged. Do not defer this to the end.
- **Genuine red before green.** `tests/test_select.py`'s and `tests/test_number.py`'s stub
  coordinators (`_StubCoordinator`, `_StubProfileCoordinator`) currently hold each field as a bare
  attribute — a plain Python object accepts an arbitrary attribute assignment whether or not
  `__init__` declared it, so simply calling the entity and asserting the resulting value would
  still pass even if the entity kept assigning the attribute directly (nothing forces the call
  site to actually change). Each task instead converts the one field it owns on the relevant stub
  into a read-only `@property` backed by a private attribute (`_active_mode`, `_target_current`,
  ...), so direct assignment through the old code path raises `AttributeError` -- a real failing
  test -- and only the new setter method can write it. On this plan's Python ≥3.12 stack the
  actual message is `AttributeError: property '<name>' of '<ClassName>' object has no setter`
  (the pre-3.11 wording was `can't set attribute '<name>'` -- don't pattern-match on the older
  message).

---

## Task 0: Correct ADR-0014's status (already done)

**ADR honored:** ADR-0014. **Test boundary:** none — documentation fix.

**Files:** `docs/adl/0014-state-mutation-encapsulation.md`, `docs/adl/README.md` — already edited
while authoring this plan's paired design doc; nothing left to do here.

ADR-0014 merged (#421) still marked `Status: Proposed` — an oversight from before merge (ADR-0012
had the same gap, fixed in its own implementation-spec PR, #386; ADR-0013 is also `Proposed`, but
correctly so — it hasn't landed an implementation spec yet, and its README row already says
`Proposed` — untouched). Both files on disk already read `Status: Accepted` / the corrected
`README.md` row and title before Task 1 starts — an executing agent should confirm this (one grep)
rather than expect a diff to make here. These edits land in the same commit as Task 1 below,
alongside the design/plan docs themselves.

---

## Task 1: `set_active_mode` + `ModeSelect`

**ADR honored:** ADR-0014. **Test boundary:** HA harness (`tests/test_select.py`,
`tests/test_coordinator.py`).

**Files:**
- Edit: `custom_components/smart_charging/coordinator.py`
- Edit: `custom_components/smart_charging/select.py`
- Edit: `tests/test_select.py`, `tests/test_coordinator.py`

**Step 1: Write the failing tests**

In `tests/test_coordinator.py` (near the other coordinator-behavior tests):

```python
async def test_set_active_mode_sets_the_field(hass):
    """ADR-0014: set_active_mode is the coordinator's own boundary for active_mode -- no
    clamp (SelectEntity's own options list already gates the enum), just encapsulation."""
    coord = SmartChargingCoordinator(hass, adapters=_adapters(), config=_config(), interval_s=30)
    coord.set_active_mode(MODE_SOLAR)
    assert coord.active_mode == MODE_SOLAR
```

In `tests/test_select.py`, convert `_StubCoordinator.active_mode` to a read-only property so
direct assignment from `select.py`'s current code genuinely fails:

```python
class _StubCoordinator:
    def __init__(self):
        self._active_mode = None
        self.refreshed = False

    @property
    def active_mode(self):
        return self._active_mode

    def set_active_mode(self, mode):
        self._active_mode = mode

    async def async_request_refresh(self):
        self.refreshed = True
```

**Step 2: Run to verify failure** —
`pytest tests/test_coordinator.py tests/test_select.py -v`:
- `test_set_active_mode_sets_the_field` fails: `AttributeError: 'SmartChargingCoordinator' object
  has no attribute 'set_active_mode'`.
- Every `_StubCoordinator`-based `ModeSelect` test in `tests/test_select.py` now fails too, since
  `select.py` still assigns `self._coordinator.active_mode = ...` directly against a stub whose
  `active_mode` has no setter: `test_select_option_pushes_to_coordinator` (:22),
  `test_restores_last_selection` (:33), `test_restore_rejects_solar_option_when_solar_not_installed`
  (:45), `test_restore_rejects_captar_option_when_captar_not_available` (:57),
  `test_added_to_hass_seeds_coordinator_with_default_when_no_restored_state` (:69) — this is the
  genuine red for the call-site half of this task; if any of these five stays green, the stub
  conversion didn't take.

**Step 3: Implement**

In `coordinator.py`, next to `_reset_mode_state_if_changed`:

```python
def set_active_mode(self, mode: str) -> None:
    """Coordinator's own boundary for `active_mode` (ADR-0014) -- the intended write path for
    select.py; the field itself stays a plain writable attribute (design doc §2, criterion 1).
    No range to clamp: `SelectEntity`'s own `options` list already rejects any value outside
    the enum before this is ever called."""
    self.active_mode = mode
```

In `select.py`'s `ModeSelect`:

```python
# async_added_to_hass, was: self._coordinator.active_mode = self._attr_current_option
self._coordinator.set_active_mode(self._attr_current_option)

# async_select_option, was: self._coordinator.active_mode = option  # coordinator resets mode-state (M1, Task 5.1)
self._coordinator.set_active_mode(option)  # coordinator resets mode-state (M1, Task 5.1)
```

**Step 4: Run to verify pass**, then run the full suite, then commit (the ADR-0014/README status
fix, Task 0, lands in the earlier commit that adds this design doc + TDD plan themselves — not
part of this task's own diff):

```
git commit --author="Claude <noreply@anthropic.com>" -m "$(cat <<'EOF'
Add SmartChargingCoordinator.set_active_mode (ADR-0014 T1)

ModeSelect now calls the coordinator's own setter instead of assigning
active_mode directly, closing the external-mutation gap ADR-0014 named.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `set_active_profile` + `ProfileSelect`

**ADR honored:** ADR-0014. **Test boundary:** HA harness (`tests/test_select.py`,
`tests/test_coordinator.py`). Same shape as Task 1, applied to `active_profile`.

**Files:**
- Edit: `custom_components/smart_charging/coordinator.py`
- Edit: `custom_components/smart_charging/select.py`
- Edit: `tests/test_select.py`, `tests/test_coordinator.py`

**Step 1: Write the failing tests**

```python
async def test_set_active_profile_sets_the_field(hass):
    """ADR-0014: set_active_profile is the coordinator's own boundary for active_profile."""
    coord = SmartChargingCoordinator(hass, adapters=_adapters(), config=_config(), interval_s=30)
    coord.set_active_profile(PROFILE_AUTO)
    assert coord.active_profile == PROFILE_AUTO
```

`ProfileSelect`'s tests use their own, separate stub class, `_StubProfileCoordinator`
(`tests/test_select.py:112-120` — distinct from `ModeSelect`'s `_StubCoordinator`; the two entities
do not share a stub). Its existing docstring (`:113`, `"""HA-harness test for the profile selector
(C2, R16)."""`) is misplaced -- a class docstring describing the test module, not the stub -- leave
it as-is; this task doesn't touch it. Convert `active_profile` to a read-only property, same
pattern as Task 1:

```python
class _StubProfileCoordinator:
    """HA-harness test for the profile selector (C2, R16)."""

    def __init__(self):
        self._active_profile = None
        self.refreshed = False

    @property
    def active_profile(self):
        return self._active_profile

    def set_active_profile(self, profile):
        self._active_profile = profile

    async def async_request_refresh(self):
        self.refreshed = True
```

**Step 2: Run to verify failure** — the new coordinator test fails with `AttributeError` (no
`set_active_profile` yet); every `_StubProfileCoordinator`-based test fails too (direct assignment
against the now-read-only property): `test_select_auto_pushes_to_coordinator_and_refreshes` (:129),
`test_restores_prior_selection_across_restart` (:140),
`test_restore_rejects_unknown_option_falls_back_to_manual` (:154),
`test_profile_added_to_hass_seeds_coordinator_with_default_when_no_restored_state` (:169).

**Step 3: Implement** — `set_active_profile` on the coordinator (same shape as `set_active_mode`),
`ProfileSelect`'s two call sites (`select.py:89,93`) switch to it.

**Step 4: Run to verify pass**, full suite, commit (same message shape as Task 1, `T2`).

---

## Task 3: `set_target_current` + `TargetCurrentNumber` + config-flow-default clamp fix

**ADR honored:** ADR-0014. **Test boundary:** HA harness (`tests/test_number.py`,
`tests/test_coordinator.py`).

**Files:**
- Edit: `custom_components/smart_charging/coordinator.py`
- Edit: `custom_components/smart_charging/number.py`
- Edit: `tests/test_number.py`, `tests/test_coordinator.py`

**Step 1: Write the failing tests**

```python
async def test_set_target_current_clamps_below_minimum(hass):
    """ADR-0014: the coordinator's own clamp -- reachable by any caller, not just
    TargetCurrentNumber's own native_min_value/native_max_value."""
    coord = SmartChargingCoordinator(hass, adapters=_adapters(), config=_config(), interval_s=30)
    coord.set_target_current(0.0)  # _config()'s CONF_MIN_CURRENT is 6.0
    assert coord.target_current == 6.0


async def test_set_target_current_clamps_above_maximum(hass):
    coord = SmartChargingCoordinator(hass, adapters=_adapters(), config=_config(), interval_s=30)
    coord.set_target_current(99.0)  # _config()'s CONF_MAX_CURRENT is 16.0
    assert coord.target_current == 16.0


async def test_set_target_current_passes_through_in_range_value(hass):
    coord = SmartChargingCoordinator(hass, adapters=_adapters(), config=_config(), interval_s=30)
    coord.set_target_current(10.0)
    assert coord.target_current == 10.0
```

Also add a test for the config-flow-default clamp fix (symmetric with Task 4's SOC fix, found by
fresh-agent review — `config_flow.py:170` validates `default_target_current` with
`vol.Coerce(float)` only, no `[min_a, max_a]` range):

```python
def test_init_clamps_out_of_range_default_target_current():
    """config_flow validates default_target_current with vol.Coerce(float) only, no
    [min_a, max_a] range -- an out-of-range configured default must clamp here too."""
    entity = TargetCurrentNumber(
        entry_id="abc", coordinator=_StubCoordinator(), min_a=6.0, max_a=16.0, default=99.0
    )
    assert entity.native_value == 16.0
```

`tests/test_number.py` has one `_StubCoordinator` class shared by both `TargetCurrentNumber` and
`SocLimitOverrideNumber` tests (`tests/test_number.py:16-23` — unlike `test_select.py`'s two
separate stubs, Task 2's lesson). Convert `target_current` to a read-only property (no clamp in
the stub -- it has no `_config`; it mirrors the coordinator's field, not its validation):

```python
    @property
    def target_current(self):
        return self._target_current

    def set_target_current(self, value):
        self._target_current = value
```

(`self._target_current = None` replaces `self.target_current = None` in `__init__`.)

**Step 2: Run to verify failure** — the three new `set_target_current` coordinator tests fail with
`AttributeError` (no `set_target_current` yet); `test_init_clamps_out_of_range_default_target_current`
fails because `entity.native_value == 99.0` today (no clamp on `default`); every `_StubCoordinator`-
based `TargetCurrentNumber` test fails too (direct assignment against the now-read-only property):
`test_set_value_pushes_to_coordinator` (`tests/test_number.py:26`),
`test_added_to_hass_seeds_coordinator_with_default_when_no_restored_state` (:50),
`test_added_to_hass_restores_previous_value_and_seeds_coordinator` (:61).

**Step 3: Implement**

```python
def set_target_current(self, value: float) -> None:
    """Coordinator's own boundary for `target_current` (ADR-0014). Clamps to the configured
    `[CONF_MIN_CURRENT, CONF_MAX_CURRENT]` bound -- previously enforced only by
    `TargetCurrentNumber`'s own native_min_value/native_max_value, bypassable by any other
    caller writing the field directly. Never the write path for a commanded stop -- ADR-0007's
    fault path writes 0 A via `self._write(0.0)` directly, not through this field."""
    self.target_current = min(
        max(value, self._config[CONF_MIN_CURRENT]), self._config[CONF_MAX_CURRENT]
    )
```

`number.py`'s `TargetCurrentNumber`:

```python
# __init__, was: self._attr_native_value = default
# config_flow validates default_target_current with vol.Coerce(float) only, no [min_a, max_a]
# range -- clamp here so an out-of-range configured default can't diverge the entity's display
# from the coordinator's own (now also clamped) field (symmetric with Task 4's SOC fix).
self._attr_native_value = min(max(default, min_a), max_a)

# async_added_to_hass, was: self._coordinator.target_current = self._attr_native_value
self._coordinator.set_target_current(self._attr_native_value)

# async_set_native_value, was: self._coordinator.target_current = value
self._coordinator.set_target_current(value)
```

**Step 4: Run to verify pass**, full suite (including the existing
`test_set_value_pushes_to_coordinator` — still passes, since 12.0 is already in
`[min_a=6.0, max_a=16.0]` in that test's own entity construction), commit (`T3`).

---

## Task 4: `set_soc_limit_override` + named SOC bounds + `SocLimitOverrideNumber` + config-flow-default clamp fix

**ADR honored:** ADR-0014. **Test boundary:** HA harness (`tests/test_number.py`,
`tests/test_coordinator.py`).

**Files:**
- Edit: `custom_components/smart_charging/const.py`
- Edit: `custom_components/smart_charging/coordinator.py`
- Edit: `custom_components/smart_charging/number.py`
- Edit: `tests/test_number.py`, `tests/test_coordinator.py`

**Step 1: Write the failing tests**

```python
async def test_set_soc_limit_override_clamps_below_minimum(hass):
    """ADR-0014: the coordinator's own clamp, using the new named SOC_LIMIT_OVERRIDE_MIN/MAX
    constants shared with SocLimitOverrideNumber's own bounds."""
    coord = SmartChargingCoordinator(hass, adapters=_adapters(), config=_config(), interval_s=30)
    coord.set_soc_limit_override(10.0)
    assert coord.soc_limit_override == SOC_LIMIT_OVERRIDE_MIN


async def test_set_soc_limit_override_clamps_above_maximum(hass):
    coord = SmartChargingCoordinator(hass, adapters=_adapters(), config=_config(), interval_s=30)
    coord.set_soc_limit_override(150.0)
    assert coord.soc_limit_override == SOC_LIMIT_OVERRIDE_MAX
```

In `tests/test_number.py`, convert the shared `_StubCoordinator`'s `soc_limit_override` to a
read-only property (same stub class Task 3 already touched for `target_current`; this task
converts `soc_limit_override` on it, the second of the class's two fields):

```python
    @property
    def soc_limit_override(self):
        return self._soc_limit_override

    def set_soc_limit_override(self, value):
        self._soc_limit_override = value
```

(`self._soc_limit_override = None` replaces `self.soc_limit_override = None` in `__init__` --
same rename Task 3 applied to `target_current`.)

Also add a new test for the config-flow-default clamp fix (config_flow validates
`default_soc_limit` with `vol.Coerce(float)` only, no 50-100 range, so an out-of-range configured
default must not reach the entity's displayed value un-clamped either, or it would silently
diverge from the coordinator's own now-clamped field):

```python
def test_init_clamps_out_of_range_default_soc_limit():
    """config_flow validates default_soc_limit with vol.Coerce(float) only, no 50-100 range --
    an out-of-range configured default must clamp here too."""
    entity = SocLimitOverrideNumber(entry_id="abc", coordinator=_StubCoordinator(), default=30.0)
    assert entity.native_value == SOC_LIMIT_OVERRIDE_MIN
```

This new test and `test_set_soc_limit_override_clamps_*` (`tests/test_coordinator.py`) need
`SOC_LIMIT_OVERRIDE_MIN`/`SOC_LIMIT_OVERRIDE_MAX` imported from
`custom_components.smart_charging.const` in both files -- `tests/test_number.py` today imports
only from `custom_components.smart_charging.number` (`:10-13`), so this adds a new
`from custom_components.smart_charging.const import ...` line; `tests/test_coordinator.py` already
has a large `from custom_components.smart_charging.const import (...)` block (`:8-57`) to extend.

**Step 2: Run to verify failure** — the two new `set_soc_limit_override` coordinator tests fail
with `AttributeError` (no `set_soc_limit_override` yet); `test_init_clamps_out_of_range_default_soc_limit`
fails because `entity.native_value == 30.0` today (no clamp on `default`); every
`_StubCoordinator`-based `SocLimitOverrideNumber` test fails too (direct assignment against the
now-read-only property): `test_soc_limit_override_set_value_pushes_to_coordinator`
(`tests/test_number.py:89`),
`test_soc_limit_override_added_to_hass_seeds_default_when_no_restored_state` (:109),
`test_soc_limit_override_added_to_hass_restores_previous_value_and_seeds_coordinator` (:120),
`test_soc_limit_override_added_to_hass_clamps_restored_value_above_max` (:148),
`test_soc_limit_override_added_to_hass_clamps_restored_value_below_min` (:174).

**Step 3: Implement**

In `const.py`, near `DEFAULT_SOC_LIMIT`:

```python
SOC_LIMIT_OVERRIDE_MIN = 50.0  # percent (R6) -- shared by number.py's own bounds and the
SOC_LIMIT_OVERRIDE_MAX = 100.0  # coordinator's set_soc_limit_override clamp (single source of truth)
```

`DEFAULT_SOC_LIMIT`'s own comment ("range enforced by config_flow/number entity") is stale as of
this task -- `config_flow` does not enforce the range (only `vol.Coerce(float)`); only the number
entity did, and only on restore, before this task's `__init__` clamp. Correct it to "range enforced
by `SocLimitOverrideNumber`" (now true for restore, default, and set alike).

In `coordinator.py` (add `SOC_LIMIT_OVERRIDE_MIN`/`SOC_LIMIT_OVERRIDE_MAX` to the existing
`from .const import (...)` block):

```python
def set_soc_limit_override(self, value: float) -> None:
    """Coordinator's own boundary for `soc_limit_override` (ADR-0014). Clamps to
    `[SOC_LIMIT_OVERRIDE_MIN, SOC_LIMIT_OVERRIDE_MAX]` -- the same bound
    `SocLimitOverrideNumber` already enforces on its own restored value, now also enforced at
    the coordinator's own field."""
    self.soc_limit_override = min(
        max(value, SOC_LIMIT_OVERRIDE_MIN), SOC_LIMIT_OVERRIDE_MAX
    )
```

In `number.py`'s `SocLimitOverrideNumber`: replace the bare `_attr_native_min_value = 50.0` /
`_attr_native_max_value = 100.0` (`number.py:63-64`) with `SOC_LIMIT_OVERRIDE_MIN`/
`SOC_LIMIT_OVERRIDE_MAX` (imported from `const.py`); its two write sites switch:

```python
# async_added_to_hass, was: self._coordinator.soc_limit_override = self._attr_native_value
self._coordinator.set_soc_limit_override(self._attr_native_value)

# async_set_native_value, was: self._coordinator.soc_limit_override = value
self._coordinator.set_soc_limit_override(value)
```

**Config-flow-default clamp fix** (`number.py:70`'s `__init__` currently assigns `default` to
`_attr_native_value` un-clamped, while `async_added_to_hass` already clamps a *restored* value the
same way, two lines below -- `config_flow` doesn't range-validate `default_soc_limit` either, so
nothing upstream catches an out-of-range configured default before it reaches here):

```python
def __init__(self, entry_id: str, coordinator, default: float) -> None:
    super().__init__(entry_id)
    self._coordinator = coordinator
    self._attr_unique_id = f"{entry_id}_soc_limit_override"
    # config_flow validates default_soc_limit with vol.Coerce(float) only, no 50-100 range --
    # clamp here the same way async_added_to_hass already clamps a restored value, so an
    # out-of-range configured default can't diverge the entity's display from the coordinator's
    # own (now also clamped) field.
    self._attr_native_value = min(
        max(default, SOC_LIMIT_OVERRIDE_MIN), SOC_LIMIT_OVERRIDE_MAX
    )
```

**Step 4: Run to verify pass**, full suite — including
`test_soc_limit_override_added_to_hass_clamps_restored_value_above_max`/`_below_min`
(`tests/test_number.py`), which exercise the *entity's* clamp on restore; confirm they still pass
unchanged now that the value also passes through the coordinator's own clamp on the way in (both
clamps agree, since they share the same constants — no double-clamping surprise). Commit (`T4`).

---

## Task 5: Regression + untouched-code check

**ADR honored:** ADR-0014. **Test boundary:** full existing suite, HA harness.

**Files:** none changed — verification only.

**Step 1:** Run the complete suite: `pytest tests/ -q`. Every test must pass, with no new
skips/xfails.

**Step 2:** `ruff check .` and `ruff format --check .` clean (both — CLAUDE.md/memory: pair check
with format --check).

**Step 3: Explicit untouched-code check** (design doc §2.5) — read the post-refactor
`coordinator.py` and confirm:
- `coordinator.py`'s internal `self.active_mode = select_mode(...)` (Auto's own mode-selection,
  `:464` before this slice's edits shift line numbers) is still a direct assignment, not routed
  through `set_active_mode` — this is the coordinator's own internal write, out of scope per
  ADR-0014, and must not have been changed by habit while touching nearby code.
- `_reset_mode_state_if_changed` (the method, not a specific line range — Tasks 1-4 add methods
  above it in the file, shifting its line numbers) is unchanged in body.
- No test file's *assertions* changed beyond what Tasks 1-4 added — the pre-existing direct
  `coordinator.active_mode = .../coordinator.target_current = .../coordinator.soc_limit_override
  = ...` assignments (137 sites, design doc §1) in `tests/test_coordinator.py`,
  `tests/test_solar_end_to_end.py`, `tests/test_captar_end_to_end.py`,
  `tests/test_deadline_soc_management_end_to_end.py`, `tests/test_init.py`, and
  `tests/benchmarks/test_coordinator_perf.py` are untouched (design doc §7 — deliberately out of
  scope; these construct the real `SmartChargingCoordinator`, not the entity-level stubs Tasks
  1-4 touched, so they are a different category of write than what this slice encapsulates).

**Step 4:** No commit — this task is a verification checkpoint. If any check fails, fix in the
task that introduced the regression (re-open that task), not here.
