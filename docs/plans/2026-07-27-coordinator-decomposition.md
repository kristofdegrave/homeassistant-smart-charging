# Coordinator Internal Decomposition Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract `CycleContext`, `PeakDemandState`, `SocGateResolver`, and a `ModeHandler` Strategy out
of `coordinator.py`'s `_run_cycle`, per [ADR-0012](../adl/0012-coordinator-internal-decomposition.md)
Option D. **Pure refactor — no behavior, entity, config, or event change.** ADR-0006's ten-step order and
the separate R3/C4 clamp call sites are untouched; `_peak_tracker` (the R3 breach-timer) is untouched.

**Architecture:** One new sibling module, `coordinator_cycle.py`, holding all four units — imported only
by `coordinator.py`, the same "private helper, one consumer" precedent `modes/_phase.py` already sets.
Full design: [`2026-07-27-coordinator-decomposition-design.md`](2026-07-27-coordinator-decomposition-design.md).

**Tech Stack:** Python ≥3.12, `pytest` (plain, ADR-0009 — every new unit is pure/HA-free),
`pytest-homeassistant-custom-component` (HA harness — regression only, no new HA-harness tests),
`ruff`.

**Model:** Per CLAUDE.md, this is development work — execute on **Sonnet**.

---

## Conventions used throughout

Same as prior plans (package root, tests-mirror-1:1, canonical mode/const names from `const.py`,
engine/adapter purity boundaries, ADR-0009 harness split, commit-after-green).

- **Named constants, no magic strings** (CLAUDE.md).
- **`git commit --author="Claude <noreply@anthropic.com>"`** with the trailer
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- Re-check `git branch --show-current` before every commit (shared checkout).
- Test docstrings name the ADR-0012 unit and, where relevant, the ADR-0006 step it replaces.
- **After every extraction task, run the full existing `tests/test_coordinator.py` suite** — it must
  keep passing unchanged. This is the regression proof this whole slice exists to satisfy; do not defer
  it to the end.

---

## Phase 0 — `CycleContext`

### Task 0.1: `CycleContext` dataclass

**ADR honored:** ADR-0012 (Option D). **Test boundary:** plain pytest, `tests/test_coordinator_cycle.py`
(new file — pure, no HA).

**Files:**
- Create: `custom_components/smart_charging/coordinator_cycle.py`
- Test: `tests/test_coordinator_cycle.py`

**Step 1: Write the failing test**

```python
"""Plain-pytest tests for the coordinator's internal cycle-decomposition units (ADR-0012)."""

from datetime import datetime

from custom_components.smart_charging.coordinator_cycle import CycleContext


def test_cycle_context_constructs_with_required_fields_and_defaults():
    ctx = CycleContext(
        status="charging", net_w=100.0, charger_w=1000.0, voltage=230.0,
        now=1.0, now_dt=datetime(2026, 7, 27, 12, 0),
    )
    assert ctx.ev_soc is None
    assert ctx.urgent is False
    assert ctx.low_tariff_active is True
```

**Step 2: Run to verify failure** — `pytest tests/test_coordinator_cycle.py -v` → `ModuleNotFoundError`.

**Step 3: Implement**

```python
"""Coordinator-internal cycle decomposition (ADR-0012): CycleContext, PeakDemandState,
SocGateResolver, and the ModeHandler Strategy. Imported only by coordinator.py. Pure -- no HA
imports (mirrors engines/ purity, ADR-0009/0010), even though these aren't engines themselves
(system-design Sec 4 rule 4: an engine may not call another engine; these call engines)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass
class CycleContext:
    """Carries one cycle's readings/derived values between _run_cycle's steps, replacing the
    loose local variables ADR-0012 flagged. Filled progressively as steps resolve each value --
    not everything is known at construction time."""

    status: str
    net_w: float
    charger_w: float
    voltage: float
    now: float
    now_dt: datetime
    ev_soc: float | None = None
    surplus_w: float = 0.0
    monthly_peak_kw: float = 0.0
    effective_peak_limit_kw: float = 0.0
    active_soc_limit: float = 0.0
    urgent: bool = False
    sun_is_up: bool = False
    sun_is_down: bool = False
    low_tariff_active: bool = True
    solar_reserve_active: bool = False
```

**Step 4: Run to verify pass**, then commit:

```bash
git add custom_components/smart_charging/coordinator_cycle.py tests/test_coordinator_cycle.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add CycleContext (ADR-0012 coordinator decomposition, part 1/4)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Phase 1 — `PeakDemandState`

### Task 1.1: `PeakDemandState.update`

**ADR honored:** ADR-0012. **Test boundary:** plain pytest (wraps `engines/peak_demand_tracker.py` +
`engines/signal_conditioning.py`, both already pure).

**Files:**
- Modify: `custom_components/smart_charging/coordinator_cycle.py`
- Modify: `tests/test_coordinator_cycle.py`

**Step 1: Write the failing tests**

```python
from datetime import datetime

from custom_components.smart_charging.coordinator_cycle import PeakDemandState


def test_peak_demand_state_accumulates_within_same_month():
    state = PeakDemandState()
    state.update(2000.0, datetime(2026, 7, 1, 0, 0), window_size=1)
    peak = state.update(1000.0, datetime(2026, 7, 2, 0, 0), window_size=1)
    assert peak == 2.0  # kW -- max(2.0, 1.0)


def test_peak_demand_state_resets_window_and_tracked_kw_on_month_rollover():
    state = PeakDemandState()
    state.update(5000.0, datetime(2026, 7, 31, 0, 0), window_size=1)
    peak = state.update(1000.0, datetime(2026, 8, 1, 0, 0), window_size=1)
    assert peak == 1.0  # not max(5.0, 1.0) -- rollover resets to this cycle's own reading
    assert state.window == ()
```

**Step 2: Run to verify failure.**

**Step 3: Implement** (append to `coordinator_cycle.py`, using the module's existing engine imports):

```python
from .engines.peak_demand_tracker import update_monthly_peak_demand
from .engines.signal_conditioning import smooth_net_power


@dataclass
class PeakDemandState:
    """Owns the coordinator's monthly-peak-demand bookkeeping (E5, Task 1.3), replacing the three
    loose _peak_window/_peak_tracked_kw/_peak_tracked_month fields ADR-0012 flagged. Distinct from
    _peak_tracker (PeakBreachTracker, the R3 clamp's own breach-timer state) -- untouched by this
    decision, still threaded through the step-7 clamp call directly."""

    window: tuple[float, ...] = ()
    tracked_kw: float = 0.0
    tracked_month: tuple[int, int] | None = None

    def update(self, net_w: float, now_dt: datetime, *, window_size: int) -> float:
        current_month = (now_dt.year, now_dt.month)
        if current_month != self.tracked_month:
            # Month rollover resets the smoothing window too, not just tracked_kw (design doc
            # Sec 6.4) -- else this cycle's "smoothed" reading would partly reflect last month.
            self.window = ()
        smoothed_w, self.window = smooth_net_power(net_w, self.window, size=window_size)
        self.tracked_kw, self.tracked_month = update_monthly_peak_demand(
            smoothed_w / 1000.0, current_month, self.tracked_kw, self.tracked_month
        )
        return self.tracked_kw
```

**Step 4: Verify pass, commit:**

```bash
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add PeakDemandState (ADR-0012 coordinator decomposition, part 2/4)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

### Task 1.2: Wire `coordinator.py` to `PeakDemandState`

**Test boundary:** HA harness — `tests/test_coordinator.py` (existing suite; no new tests, must keep
passing unchanged — this is the regression proof).

**Files:** Modify: `custom_components/smart_charging/coordinator.py`

**Step 1:** In `__init__`, replace `self._peak_window`/`self._peak_tracked_kw`/`self._peak_tracked_month`
with `self._peak_demand = PeakDemandState()`. Import `PeakDemandState` from `.coordinator_cycle`.

**Step 2:** In `_run_cycle`, replace the inline month-rollover/smoothing/`update_monthly_peak_demand`
block (current lines ~224-243) with:

```python
monthly_peak_kw = self._peak_demand.update(net_w, now_dt, window_size=peak_window_size)
```

**Step 3: Run the full existing suite** — `pytest tests/test_coordinator.py -v` — must pass unchanged.

**Step 4: Commit:**

```bash
git commit --author="Claude <noreply@anthropic.com>" -m "refactor: wire coordinator.py to PeakDemandState (ADR-0012)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Phase 2 — `SocGateResolver`

### Task 2.1: `SocGateResolver.resolve`

**Test boundary:** plain pytest.

**Step 1: Write the failing tests**

```python
from custom_components.smart_charging.coordinator_cycle import SocGateResolver
from custom_components.smart_charging.engines.soc_target import SolarStepUpState


def test_soc_gate_resolver_first_call_always_reports_changed():
    resolver = SocGateResolver()
    limit, changed = resolver.resolve(
        80.0, solar_reserve_active=False, solar_reserve_soc=60.0,
        step_up_state=SolarStepUpState(),
    )
    assert changed is True


def test_soc_gate_resolver_reports_unchanged_when_limit_is_stable():
    resolver = SocGateResolver()
    resolver.resolve(80.0, solar_reserve_active=False, solar_reserve_soc=60.0, step_up_state=SolarStepUpState())
    limit, changed = resolver.resolve(
        80.0, solar_reserve_active=False, solar_reserve_soc=60.0, step_up_state=SolarStepUpState()
    )
    assert changed is False
    assert limit == 80.0


def test_soc_gate_resolver_reports_changed_when_limit_moves():
    resolver = SocGateResolver()
    resolver.resolve(80.0, solar_reserve_active=False, solar_reserve_soc=60.0, step_up_state=SolarStepUpState())
    _, changed = resolver.resolve(
        80.0, solar_reserve_active=True, solar_reserve_soc=60.0, step_up_state=SolarStepUpState()
    )
    assert changed is True
```

**Step 2: Run to verify failure.**

**Step 3: Implement** (append to `coordinator_cycle.py`):

```python
from .engines.soc_target import SolarStepUpState, resolve_active_soc_limit


class SocGateResolver:
    """Owns SOC-limit resolution + change detection (ADR-0012), replacing the inline
    resolve_active_soc_limit call + _last_active_soc_limit comparison. Pure -- no hass.bus access;
    the coordinator still fires ActiveSocLimitChanged itself on a reported change (ADR-0009/0010
    boundary: HA I/O stays coordinator-side)."""

    def __init__(self) -> None:
        self._last_limit: float | None = None

    def resolve(
        self,
        override: float,
        *,
        solar_reserve_active: bool,
        solar_reserve_soc: float,
        step_up_state: SolarStepUpState,
    ) -> tuple[float, bool]:
        limit = resolve_active_soc_limit(
            override,
            solar_reserve_active=solar_reserve_active,
            solar_reserve_soc=solar_reserve_soc,
            step_up_state=step_up_state,
        )
        changed = limit != self._last_limit
        self._last_limit = limit
        return limit, changed
```

**Step 4: Verify pass, commit:**

```bash
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add SocGateResolver (ADR-0012 coordinator decomposition, part 3/4)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

### Task 2.2: Wire `coordinator.py` to `SocGateResolver`

**Test boundary:** HA harness — existing `tests/test_coordinator.py`, unchanged.

**Step 1:** In `__init__`, replace `self._last_active_soc_limit: float | None = None` with
`self._soc_gate = SocGateResolver()`. Import from `.coordinator_cycle`.

**Step 2:** In `_run_cycle`, replace:

```python
active_soc_limit = resolve_active_soc_limit(...)
if active_soc_limit != self._last_active_soc_limit:
    self.hass.bus.async_fire(EVENT_ACTIVE_SOC_LIMIT_CHANGED, {ATTR_ACTIVE_SOC_LIMIT: active_soc_limit})
self._last_active_soc_limit = active_soc_limit
```

with:

```python
active_soc_limit, soc_limit_changed = self._soc_gate.resolve(
    self.soc_limit_override,
    solar_reserve_active=solar_reserve_active,
    solar_reserve_soc=self._config.get(CONF_SOLAR_RESERVE_SOC, DEFAULT_SOLAR_RESERVE_SOC),
    step_up_state=self._step_up_state,
)
if soc_limit_changed:
    self.hass.bus.async_fire(EVENT_ACTIVE_SOC_LIMIT_CHANGED, {ATTR_ACTIVE_SOC_LIMIT: active_soc_limit})
```

**Step 3: Run the full existing suite, must pass unchanged. Commit:**

```bash
git commit --author="Claude <noreply@anthropic.com>" -m "refactor: wire coordinator.py to SocGateResolver (ADR-0012)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Phase 3 — `ModeHandler` Strategy

### Task 3.1: `ModeHandler` protocol + the five per-mode adapters

**Test boundary:** plain pytest — each handler delegates to its wrapped `modes/*.py` function, whose own
behavior is already covered by `tests/modes/`; these tests only prove correct delegation, not re-derive
mode behavior.

**Step 1: Write the failing tests** (one per handler; `_SolarModeHandler` shown, others follow the same
shape against `modes.solar_only`/`modes.captar`/`modes.power`/no-op for off):

```python
from custom_components.smart_charging.coordinator_cycle import CycleContext, _SolarModeHandler
from custom_components.smart_charging.modes import solar


def test_solar_mode_handler_delegates_to_modes_solar_step():
    config = {
        "solar_start_threshold_w": 500, "min_current": 6,
        "solar_hold_min": 5, "solar_cooldown_min": 10,
    }
    handler = _SolarModeHandler(config)
    ctx = CycleContext(status="charging", net_w=0, charger_w=0, voltage=230.0, now=1.0, now_dt=None, surplus_w=1000.0)
    current, new_state = handler.desired_current(ctx, solar.SolarState.idle())
    expected_current, expected_state = solar.step(
        1000.0, solar.SolarState.idle(), 1.0,
        start_threshold_w=500, min_a=6, hold_minutes=5, cooldown_minutes=10, voltage=230.0,
    )
    assert (current, new_state) == (expected_current, expected_state)
```

Use the real `const.py` `CONF_*` keys in the actual implementation/tests, not the string literals shown
here (illustrative only — replace with named constants per CLAUDE.md).

**Step 2: Run to verify failure.**

**Step 3: Implement** (append to `coordinator_cycle.py`):

```python
from .const import (
    CONF_CAPTAR_COOLDOWN_MIN, CONF_MAX_CURRENT, CONF_MIN_CURRENT,
    CONF_SOLAR_COOLDOWN_MIN, CONF_SOLAR_HOLD_MIN, CONF_SOLAR_ONLY_MIDPOINT,
    CONF_SOLAR_ONLY_START_THRESHOLD_W, CONF_SOLAR_ONLY_STRATEGY, CONF_SOLAR_START_THRESHOLD_W,
    DEFAULT_CAPTAR_COOLDOWN_MIN,
)
from .modes import captar, power, solar, solar_only


class ModeHandler(Protocol):
    """One thin adapter per mode module, wrapping its existing pure step()/desired_current()
    unchanged (ADR-0012) -- this decision only changes how the coordinator looks one up."""

    def desired_current(self, ctx: CycleContext, state: Any) -> tuple[float, Any]: ...


class _OffModeHandler:
    def desired_current(self, ctx: CycleContext, state: Any) -> tuple[float, Any]:
        return 0.0, state


class _PowerModeHandler:
    def __init__(self, target_current_getter) -> None:
        self._target_current_getter = target_current_getter  # coordinator.target_current is mutable

    def desired_current(self, ctx: CycleContext, state: Any) -> tuple[float, Any]:
        return power.desired_current(self._target_current_getter(), ctx.status), state


class _SolarModeHandler:
    def __init__(self, config) -> None:
        self._config = config

    def desired_current(self, ctx: CycleContext, state: solar.SolarState) -> tuple[float, solar.SolarState]:
        return solar.step(
            ctx.surplus_w, state, ctx.now,
            start_threshold_w=self._config[CONF_SOLAR_START_THRESHOLD_W],
            min_a=self._config[CONF_MIN_CURRENT],
            hold_minutes=self._config[CONF_SOLAR_HOLD_MIN],
            cooldown_minutes=self._config[CONF_SOLAR_COOLDOWN_MIN],
            voltage=ctx.voltage,
        )


class _SolarOnlyModeHandler:
    def __init__(self, config) -> None:
        self._config = config

    def desired_current(self, ctx: CycleContext, state: solar_only.SolarOnlyState) -> tuple[float, solar_only.SolarOnlyState]:
        return solar_only.step(
            ctx.surplus_w, state, ctx.now,
            start_threshold_w=self._config[CONF_SOLAR_ONLY_START_THRESHOLD_W],
            min_a=self._config[CONF_MIN_CURRENT],
            cooldown_minutes=self._config[CONF_SOLAR_COOLDOWN_MIN],
            strategy=self._config[CONF_SOLAR_ONLY_STRATEGY],
            midpoint=self._config[CONF_SOLAR_ONLY_MIDPOINT],
            voltage=ctx.voltage,
        )


class _CaptarModeHandler:
    def __init__(self, config) -> None:
        self._config = config

    def desired_current(self, ctx: CycleContext, state: captar.CaptarState) -> tuple[float, captar.CaptarState]:
        return captar.step(
            state, ctx.now,
            max_a=self._config[CONF_MAX_CURRENT],
            cooldown_minutes=self._config.get(CONF_CAPTAR_COOLDOWN_MIN, DEFAULT_CAPTAR_COOLDOWN_MIN),
        )
```

*Note on `_PowerModeHandler`:* `power.desired_current` reads the coordinator's own mutable
`target_current` (set externally by the number entity), not anything on `CycleContext` — the handler
takes a zero-arg getter bound at construction (`lambda: self.target_current`) rather than duplicating
that value onto `CycleContext` each cycle, since it isn't itself part of "this cycle's readings," it's
coordinator-owned mutable state read fresh.

**Step 4: Verify pass, commit:**

```bash
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add ModeHandler Strategy + per-mode adapters (ADR-0012 coordinator decomposition, part 4/4)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

### Task 3.2: Wire `coordinator.py`'s real dispatch to the `ModeHandler` registry

**Test boundary:** HA harness — existing `tests/test_coordinator.py`, unchanged.

**Step 1:** In `__init__`, after `self._config = config`, build:

```python
self._mode_handlers: dict[str, ModeHandler] = {
    MODE_OFF: _OffModeHandler(),
    MODE_POWER: _PowerModeHandler(lambda: self.target_current),
    MODE_SOLAR: _SolarModeHandler(config),
    MODE_SOLAR_ONLY: _SolarOnlyModeHandler(config),
    MODE_CAPTAR: _CaptarModeHandler(config),
}
```

**Step 2:** In `_run_cycle`, the disconnect/`MODE_OFF`/SOC-gated-stop `if/elif` branches (current
~500-522) stay exactly as they are — they decide *whether* to dispatch, which ADR-0012 leaves in the
coordinator. Replace only the final `elif self.active_mode == MODE_SOLAR: ... elif ... else: # MODE_CAPTAR`
chain (current ~523-554) with:

```python
else:
    ctx.surplus_w = surplus_w  # (or however CycleContext was populated earlier in this task's diff)
    desired, self._mode_state[self.active_mode] = self._mode_handlers[
        self.active_mode
    ].desired_current(ctx, self._mode_state[self.active_mode])
```

(`MODE_POWER`'s own branch, current line ~507-508, can also collapse into this lookup once `ctx` is
populated, since `_PowerModeHandler` reproduces it exactly — do so only if it doesn't disturb the
disconnect/SOC-gate guard ordering; if it does, leave `MODE_POWER` as its own branch calling the same
handler explicitly. Either is fine; note which was chosen in the commit message.)

**Step 3: Run the full existing suite, must pass unchanged. Commit:**

```bash
git commit --author="Claude <noreply@anthropic.com>" -m "refactor: wire coordinator.py real dispatch to ModeHandler registry (ADR-0012)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

### Task 3.3: Unify `_mode_desired_current` (the Task 5.2 dry-run) onto the same registry

**Test boundary:** HA harness — existing `tests/test_coordinator.py`, unchanged (this method has no
tests of its own beyond what already exercises it through Task 5.2's baseline-mode comparison).

**Step 1:** Replace `_mode_desired_current`'s entire `if/elif` body with:

```python
def _mode_desired_current(self, mode, *, status, ev_soc, active_soc_limit, surplus_w, voltage, now) -> float:
    if status not in CHARGEABLE_STATES:
        return 0.0
    if mode in _SOC_GATED_MODES and ev_soc >= active_soc_limit:
        return 0.0
    ctx = CycleContext(
        status=status, net_w=0.0, charger_w=0.0, voltage=voltage, now=now, now_dt=None,
        ev_soc=ev_soc, surplus_w=surplus_w, active_soc_limit=active_soc_limit,
    )
    current, _ = self._mode_handlers[mode].desired_current(ctx, self._mode_state.get(mode))
    return current
```

(`net_w`/`charger_w` are irrelevant to every `ModeHandler.desired_current` — none of the five reads them
off `ctx` — so `0.0` placeholders are safe; confirm this holds during implementation and note it in the
commit message if any handler needs updating to not depend on them.)

**Step 2: Run the full existing suite, must pass unchanged. Commit:**

```bash
git commit --author="Claude <noreply@anthropic.com>" -m "refactor: unify baseline-mode dry-run onto ModeHandler registry, remove duplicate dispatch chain (ADR-0012)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Phase 4 — Final regression + cleanup

### Task 4.1: Full-suite regression + dead-code sweep

**Test boundary:** HA harness (full suite) + plain pytest (full suite).

**Step 1:** Run the entire test suite: `pytest tests/ -v`. All must pass, with zero new or changed test
expectations anywhere outside `tests/test_coordinator_cycle.py`.

**Step 2:** `ruff check .` and `ruff format --check .` — both clean.

**Step 3:** Confirm no dead code remains: the three old peak-tracking fields, `_last_active_soc_limit`,
and the old inline `if/elif` chains are fully removed from `coordinator.py` (grep to confirm).

**Step 4:** Commit any final cleanup:

```bash
git commit --author="Claude <noreply@anthropic.com>" -m "chore: remove dead pre-decomposition state from coordinator.py (ADR-0012)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Summary

| Phase | Unit | New file/tests | Coordinator wiring |
| --- | --- | --- | --- |
| 0 | `CycleContext` | `coordinator_cycle.py` + `tests/test_coordinator_cycle.py` (pure) | n/a (data carrier) |
| 1 | `PeakDemandState` | same | Task 1.2 |
| 2 | `SocGateResolver` | same | Task 2.2 |
| 3 | `ModeHandler` × 5 | same | Tasks 3.2/3.3 |
| 4 | — | — | Regression + cleanup |

Every wiring task runs the full existing `tests/test_coordinator.py` suite before its commit — that
suite passing unchanged, throughout, is the acceptance criterion for this entire slice.
