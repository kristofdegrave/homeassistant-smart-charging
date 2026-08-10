# `_run_cycle` Named-Step Decomposition Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Decompose the rest of `coordinator.py`'s `_run_cycle` into named units, per
[ADR-0023](../adl/0023-decompose-run-cycle-into-named-steps.md) — extending
[ADR-0012](../adl/0012-coordinator-internal-decomposition.md)'s existing `CycleContext`/
`ModeHandler`/`PeakDemandState`/`SocGateResolver` decomposition to the blocks it didn't name.
**Pure refactor — no behavior, entity, config, or event change.** ADR-0006's ten-step order, the
separate R3/C4 clamp call sites, `_peak_tracker`, and the `ModeHandler` registry lookup itself are
all untouched.

**Architecture:** Two new pure units added to the existing `coordinator_cycle.py`
(`SolarStepUpGate`, `resolve_solar_reserve_gate`); five new plain private methods added to
`SmartChargingCoordinator` in `coordinator.py`. No new module.
Full design: [`2026-08-10-run-cycle-named-steps-design.md`](2026-08-10-run-cycle-named-steps-design.md).

**Tech Stack:** Python ≥3.12, `pytest` (plain, ADR-0009 — the two new `coordinator_cycle.py` units),
`pytest-homeassistant-custom-component` (HA harness — regression only, no new HA-harness tests),
`ruff`.

**Model:** Per CLAUDE.md, this is development work — execute on **Sonnet**.

---

## Conventions used throughout

Same as the ADR-0012 implementation plan (package root, tests-mirror-1:1, canonical mode/const
names from `const.py`, engine/adapter purity boundaries, ADR-0009 harness split,
commit-after-green).

- **Named constants, no magic strings** (CLAUDE.md).
- **`git commit --author="Claude <noreply@anthropic.com>"`** with the trailer
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- Re-check `git branch --show-current` before every commit (shared checkout).
- Test docstrings name the ADR-0023 unit and the `coordinator.py` line range it replaces.
- **After every extraction task, run the full existing `tests/test_coordinator.py` suite** — it
  must keep passing unchanged. This is the regression proof this whole slice exists to satisfy;
  do not defer it to the end.
- Every new `coordinator.py` method is added *and wired into `_run_cycle` in the same task* — no
  task leaves an extracted method unused (dead code) or `_run_cycle` calling both the old inline
  block and the new method.

---

## Phase 0 — `coordinator_cycle.py`: `SolarStepUpGate`

### Task 0.1: `SolarStepUpGate`

**ADR honored:** ADR-0023 (Option A). **Test boundary:** plain pytest,
`tests/test_coordinator_cycle.py` (existing file — pure, no HA).

**Files:**
- Edit: `custom_components/smart_charging/coordinator_cycle.py`
- Test: `tests/test_coordinator_cycle.py`

**Step 1: Write the failing test**

```python
from custom_components.smart_charging.const import PROFILE_AUTO, PROFILE_MANUAL, STATE_DISCONNECTED
from custom_components.smart_charging.coordinator_cycle import SolarStepUpGate


def test_solar_step_up_gate_starts_at_default_state():
    gate = SolarStepUpGate()
    assert gate.state == SolarStepUpState()


def test_solar_step_up_gate_steps_up_when_solar_mode_charging_and_within_threshold():
    """Anchored to engines/test_soc_target.py::test_steps_up_once_within_threshold's own
    fixture values -- the gate must produce the identical resolve_solar_step_up outcome for
    an equivalent is_solar_mode_charging=True call, proving the wrapper computes the gate
    correctly, not just that it calls something."""
    gate = SolarStepUpGate()
    gate.resolve(
        profile=PROFILE_AUTO, mode_is_solar=True, status=STATE_CHARGING,
        soc=78.0, default_limit=80.0, step_threshold_pp=2.0, step_pp=5.0, max_solar_soc=100.0,
    )
    assert gate.state == SolarStepUpState(stepped_pct=85.0)


def test_solar_step_up_gate_clears_when_profile_is_manual():
    """is_solar_mode_charging's PROFILE_AUTO-only gate (R8) suppresses the step even with a
    solar mode charging within threshold -- Manual never steps up."""
    gate = SolarStepUpGate()
    gate.resolve(
        profile=PROFILE_MANUAL, mode_is_solar=True, status=STATE_CHARGING,
        soc=78.0, default_limit=80.0, step_threshold_pp=2.0, step_pp=5.0, max_solar_soc=100.0,
    )
    assert gate.state == SolarStepUpState()


def test_solar_step_up_gate_clears_when_mode_is_not_solar():
    gate = SolarStepUpGate()
    gate.resolve(
        profile=PROFILE_AUTO, mode_is_solar=False, status=STATE_CHARGING,
        soc=78.0, default_limit=80.0, step_threshold_pp=2.0, step_pp=5.0, max_solar_soc=100.0,
    )
    assert gate.state == SolarStepUpState()


def test_solar_step_up_gate_clears_when_disconnected():
    gate = SolarStepUpGate()
    gate.resolve(
        profile=PROFILE_AUTO, mode_is_solar=True, status=STATE_DISCONNECTED,
        soc=78.0, default_limit=80.0, step_threshold_pp=2.0, step_pp=5.0, max_solar_soc=100.0,
    )
    assert gate.state == SolarStepUpState()


def test_solar_step_up_gate_treats_none_soc_as_zero():
    """Mirrors coordinator.py's own `soc=ev_soc if ev_soc is not None else 0.0` -- a
    disconnected-adjacent read of None must not raise, and 0.0 never triggers a step
    (soc=0.0 is never within step_threshold_pp of any positive current_limit here)."""
    gate = SolarStepUpGate()
    gate.resolve(
        profile=PROFILE_AUTO, mode_is_solar=True, status=STATE_CHARGING,
        soc=None, default_limit=80.0, step_threshold_pp=2.0, step_pp=5.0, max_solar_soc=100.0,
    )
    assert gate.state == SolarStepUpState()
```

**Step 2: Run to verify failure** — `pytest tests/test_coordinator_cycle.py -v` →
`ImportError: cannot import name 'SolarStepUpGate'`.

**Step 3: Implement**

Add to `coordinator_cycle.py`'s `.const` import: `CHARGEABLE_STATES`, `PROFILE_AUTO`. Add the class
(see design doc §4.1) after `SocGateResolver`.

**Step 4: Run to verify pass.**

**Step 5: Regression** — `pytest tests/test_coordinator.py -v` (must still pass unchanged;
`SolarStepUpGate` is not wired into `coordinator.py` yet).

**Step 6: Commit** — `refactor: add SolarStepUpGate (ADR-0023)`.

---

## Phase 1 — `coordinator_cycle.py`: `resolve_solar_reserve_gate`

### Task 1.1: `resolve_solar_reserve_gate`

**ADR honored:** ADR-0023 (Option A). **Test boundary:** plain pytest,
`tests/test_coordinator_cycle.py`.

**Files:**
- Edit: `custom_components/smart_charging/coordinator_cycle.py`
- Test: `tests/test_coordinator_cycle.py`

**Step 1: Write the failing test**

```python
from custom_components.smart_charging.coordinator_cycle import resolve_solar_reserve_gate


def test_resolve_solar_reserve_gate_active_when_all_conditions_hold():
    """Anchored to engines/test_soc_target.py::test_reserve_active_when_all_conditions_hold's
    own fixture values."""
    assert resolve_solar_reserve_gate(
        profile=PROFILE_AUTO, home_day_flag=True, sun_is_down=True,
        forecast_kwh=15.0, forecast_threshold_kwh=12.0, deadline_tomorrow_resolved=False,
    ) is True


def test_resolve_solar_reserve_gate_treats_none_forecast_as_zero():
    """Mirrors coordinator.py's own `forecast_kwh if forecast_kwh is not None else 0.0` --
    an unmapped/unavailable forecast role must not raise and must never activate the cap."""
    assert resolve_solar_reserve_gate(
        profile=PROFILE_AUTO, home_day_flag=True, sun_is_down=True,
        forecast_kwh=None, forecast_threshold_kwh=12.0, deadline_tomorrow_resolved=False,
    ) is False


def test_resolve_solar_reserve_gate_inactive_under_manual():
    """Anchored to engines/test_soc_target.py::test_reserve_inactive_under_manual."""
    assert resolve_solar_reserve_gate(
        profile=PROFILE_MANUAL, home_day_flag=True, sun_is_down=True,
        forecast_kwh=15.0, forecast_threshold_kwh=12.0, deadline_tomorrow_resolved=False,
    ) is False
```

**Step 2: Run to verify failure.**

**Step 3: Implement** — add `resolve_solar_reserve_active` to `coordinator_cycle.py`'s
`.engines.soc_target` import; add the function (see design doc §4.2) after `SolarStepUpGate`.

**Step 4: Run to verify pass.**

**Step 5: Regression** — `pytest tests/test_coordinator.py -v` (must still pass unchanged).

**Step 6: Commit** — `refactor: add resolve_solar_reserve_gate (ADR-0023)`.

---

## Phase 2 — Wire `SolarStepUpGate` into `coordinator.py`

### Task 2.1: Replace `self._step_up_state` with `self._step_up_gate`

**ADR honored:** ADR-0023. **Test boundary:** HA harness, `tests/test_coordinator.py` (existing —
regression only, no new tests this task).

**Files:**
- Edit: `custom_components/smart_charging/coordinator.py`

**Step 1:** No new test — this task is proven by the existing suite passing unchanged (design doc
§2's success criterion 6). Confirm `tests/test_coordinator.py` and any other file referencing
`coordinator._step_up_state` directly first:

```bash
grep -rn "_step_up_state" custom_components/ tests/
```

If any test reaches into `coordinator._step_up_state` directly (rather than only through
`resolve_solar_step_up`'s observable effect on `commanded_current`/`active_soc_limit`), update
that reference to `coordinator._step_up_gate.state` in this same task — a mechanical rename, not a
behavior change, the same pattern the ADR-0012 plan used for `MonthlyPeakSensor`'s
`_peak_tracked_kw`/`_peak_tracked_month` references.

**Step 2: Implement**
- `__init__`: replace `self._step_up_state: SolarStepUpState = SolarStepUpState()` with
  `self._step_up_gate = SolarStepUpGate()`. Add `SolarStepUpGate` to the `.coordinator_cycle`
  import.
- Replace the `_, self._step_up_state = resolve_solar_step_up(...)` call (`:311-326`) with the
  `self._step_up_gate.resolve(...)` call from design doc §4.1.
- Replace `step_up_state=self._step_up_state` in the `SocGateResolver.resolve(...)` call
  (`:388`) with `step_up_state=self._step_up_gate.state`.
- Remove the now-unused `resolve_solar_step_up` import from `coordinator.py` if nothing else
  there calls it (confirm with a grep before removing).

**Step 3: Run the full regression suite** — `pytest tests/test_coordinator.py -v` — must pass
unchanged. Pay particular attention to any R8 step-up test (search
`test_coordinator.py`/`test_solar_end_to_end.py` for `step_up`/`stepped_pct`) — these exercise
exactly this call site.

**Step 4: Commit** — `refactor: wire SolarStepUpGate into coordinator._run_cycle (ADR-0023)`.

---

## Phase 3 — Wire `resolve_solar_reserve_gate` into `coordinator.py`

### Task 3.1: Replace the inline `resolve_solar_reserve_active` call

**ADR honored:** ADR-0023. **Test boundary:** HA harness, `tests/test_coordinator.py` (regression
only).

**Files:**
- Edit: `custom_components/smart_charging/coordinator.py`

**Step 1:** No new test — proven by the existing suite.

**Step 2: Implement** — replace the `solar_reserve_active = resolve_solar_reserve_active(...)`
call (`:373-382`) with `ctx.solar_reserve_active = resolve_solar_reserve_gate(...)` (design doc
§3.2's excerpt), reading `ctx.solar_reserve_active` at the `SocGateResolver.resolve(...)` call
site (`:386`) instead of the local `solar_reserve_active` variable. Add `resolve_solar_reserve_gate`
to the `.coordinator_cycle` import; remove the now-unused `resolve_solar_reserve_active` import
from `.engines.soc_target` if nothing else in `coordinator.py` calls it.

**Step 3: Run the full regression suite** — must pass unchanged. Pay particular attention to any
R9 reserve-cap test (search for `reserve` in `test_coordinator.py`/`test_solar_end_to_end.py`).

**Step 4: Commit** — `refactor: wire resolve_solar_reserve_gate into coordinator._run_cycle (ADR-0023)`.

---

## Phase 4 — `_read_cycle_inputs`

### Task 4.1: Extract the initial adapter reads + voltage resolution + first fault check

**ADR honored:** ADR-0023. **Test boundary:** HA harness, `tests/test_coordinator.py` (regression
only — this task adds the method and its ADR-0007 sentinel convention, proven by existing fault
tests, e.g. `test_end_to_end_disconnect_forces_zero_and_fault`-style tests that drive a missing
required adapter).

**Files:**
- Edit: `custom_components/smart_charging/coordinator.py`

**Step 1:** No new test — the sentinel-return convention (§3.1's success criterion 2) is proven
by every existing "required adapter is None" fault test continuing to fault identically. Before
implementing, locate and note those tests (search `test_coordinator.py` for
`required adapter returned None` or a `None`-returning adapter fixture) so Step 3 explicitly
confirms they still pass.

**Step 2: Implement** — add `_read_cycle_inputs` (design doc §3.1) as a new method; replace
`_run_cycle:216-230` with the "`_run_cycle` becomes" snippet from §3.1.

**Step 3: Run the full regression suite**, explicitly re-running the fault tests noted in Step 1
in isolation first (`pytest tests/test_coordinator.py -k fault -v` or equivalent), then the full
suite.

**Step 4: Commit** — `refactor: extract _read_cycle_inputs from _run_cycle (ADR-0023)`.

---

## Phase 5 — `_resolve_deadline_and_reserve`

### Task 5.1: Extract the R14/R9 read-and-resolve block

**ADR honored:** ADR-0023. **Test boundary:** HA harness, `tests/test_coordinator.py` (regression
only).

**Files:**
- Edit: `custom_components/smart_charging/coordinator.py`

**Step 1:** No new test — proven by the existing suite, particularly any test driving
`ROLE_DEPARTURE_EXTERNAL`, `ROLE_SUN`, `ROLE_LOW_TARIFF`, or `ROLE_SOLAR_FORECAST` (search
`test_deadline_soc_management_end_to_end.py`).

**Step 2: Implement** — add `_resolve_deadline_and_reserve` (design doc §3.2, depends on Task
3.1's `resolve_solar_reserve_gate` already being wired); replace `_run_cycle:328-383` with the
"`_run_cycle` becomes" snippet from §3.2. `resolve_deadline_for` is now a value returned from
this method rather than a closure defined inline in `_run_cycle` — `_run_cycle` no longer defines
it itself, only receives and later calls it (Task 6.1 needs it too).

**Step 3: Run the full regression suite**, particularly `test_deadline_soc_management_end_to_end.py`
and any test asserting on `ActiveSocLimitChanged`'s firing (this method's output feeds directly
into the very next line, `SocGateResolver.resolve`).

**Step 4: Commit** — `refactor: extract _resolve_deadline_and_reserve from _run_cycle (ADR-0023)`.

---

## Phase 6 — `_read_deadline_urgency_inputs`

### Task 6.1: Extract the R5/R14/R15 adapter reads

**ADR honored:** ADR-0023. **Test boundary:** HA harness, `tests/test_coordinator.py` (regression
only).

**Files:**
- Edit: `custom_components/smart_charging/coordinator.py`

**Step 1:** No new test — proven by the existing suite, particularly any test driving
`ROLE_EV_BATTERY_CAPACITY` or asserting on `DeadlineUnreachableNotified`/required-current values
(search `test_deadline_soc_management_end_to_end.py`).

**Step 2: Implement** — add `_read_deadline_urgency_inputs` (design doc §3.3); replace
`_run_cycle:417-435` with the "`_run_cycle` becomes" snippet from §3.3, passing in the
`resolve_deadline_for` value Task 5.1's method now returns.

**Step 3: Run the full regression suite.**

**Step 4: Commit** — `refactor: extract _read_deadline_urgency_inputs from _run_cycle (ADR-0023)`.

---

## Phase 7 — `_dispatch_mode`

### Task 7.1: Extract the disconnect/Off/Power/SOC-gated-stop dispatch branches

**ADR honored:** ADR-0023 (does not touch ADR-0012's `ModeHandler` lookup itself). **Test
boundary:** HA harness, `tests/test_coordinator.py` (regression only — this is the highest-risk
extraction; every mode-dispatch test in the suite exercises it).

**Files:**
- Edit: `custom_components/smart_charging/coordinator.py`

**Step 1:** No new test — before implementing, run
`pytest tests/test_coordinator.py -k "dispatch or mode or soc_gated or idle" -v` (or equivalent)
to establish the current-green baseline for this region specifically.

**Step 2: Implement** — add `_dispatch_mode` (design doc §3.4); replace `_run_cycle:502-531` with
`desired = self._dispatch_mode(ctx, ev_soc=ev_soc, active_soc_limit=active_soc_limit)`.

**Step 3: Run the full regression suite**, then specifically re-run the Step 1 subset to confirm
identical pass/fail status (not just "still green overall" — this extraction has five branches,
and a single misordered `if`/`elif` here would silently change which branch a given test hits).

**Step 4: Commit** — `refactor: extract _dispatch_mode from _run_cycle (ADR-0023)`.

---

## Phase 8 — `_apply_clamps`

### Task 8.1: Extract the R3/C4 clamp calls and the floor/cap invariant

**ADR honored:** ADR-0023 (does not touch ADR-0006's clamp separation or the R17 opt-out — only
the call sites get a name). **Test boundary:** HA harness, `tests/test_coordinator.py` (regression
only — the second highest-risk extraction; ADR-0012's own implementation plan flagged this exact
region for a stale-line-reference mistake during its own review).

**Files:**
- Edit: `custom_components/smart_charging/coordinator.py`

**Step 1:** No new test — before implementing, run
`pytest tests/test_coordinator.py -k "peak or clamp or ceiling or floor or captar" -v` (or
equivalent) to establish the current-green baseline.

**Step 2: Implement** — add `_apply_clamps` (design doc §3.5); replace `_run_cycle:533-566` with
`desired = self._apply_clamps(desired, net_w=net_w, charger_w=charger_w, voltage=voltage, effective_peak_limit_kw=effective_peak_limit_kw, now=now)`.

**Step 3: Run the full regression suite**, then re-run the Step 1 subset. **Explicitly re-read**
the resulting `_apply_clamps` method and confirm: the R3 call and the C4 call are still two
distinct calls to `apply_peak_clamp`/`clamp_to_ceiling` respectively; only the R3 call is guarded
by the `power_respect_peak` opt-out; `self._peak_tracker` is still threaded through exactly the R3
call, not duplicated or dropped. This is the explicit byte-for-byte check design doc §6 and
ADR-0012's own precedent both call for — do not rely on green tests alone here.

**Step 4: Commit** — `refactor: extract _apply_clamps from _run_cycle (ADR-0023)`.

---

## Phase 9 — Final verification

### Task 9.1: Full regression pass and `_run_cycle` audit

**ADR honored:** ADR-0006, ADR-0009, ADR-0012, ADR-0023. **Test boundary:** HA harness, full
suite.

**Files:** none changed — verification only.

**Step 1:** `pytest tests/` (the entire suite, not just `test_coordinator.py`) — must pass in
full.

**Step 2:** `ruff check` and `ruff format --check` on `coordinator.py` and `coordinator_cycle.py`.

**Step 3:** Read the final `_run_cycle` top to bottom and confirm, against
[ADR-0006](../adl/0006-coordinator-and-data-flow.md)'s ten-step list:
- The sequence is still a literal, named, top-to-bottom list of calls with no reordering.
- The R3 clamp and C4 clamp remain two distinct calls, only R3 gated by the R17 opt-out
  (`_apply_clamps`, Task 8.1).
- `_reset_mode_state_if_changed()` is still called exactly twice, at the same two points.
- The two in-cycle fault paths (`_read_cycle_inputs` returning `None`; the ev_soc-missing check)
  still each construct and return their own `CycleResult` directly in `_run_cycle` — no extracted
  method returns a `CycleResult` itself (ADR-0023's stated requirement, design doc §2 criterion 2).
- `_mode_desired_current` (the baseline dry-run helper) is untouched and still uses the same
  `ModeHandler` registry `_dispatch_mode` now also uses.

**Step 4:** No commit — this task is a verification gate before the plan is reported done. If
Step 3 finds a discrepancy, fix it in a follow-up commit on the same branch and re-run Steps 1-3.

**Step 5: Report** — plan complete; ADR-0023 fully implemented, no behavior change, full suite
green.
