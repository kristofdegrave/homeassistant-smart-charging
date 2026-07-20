# Solar & SolarOnly Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `Solar` and `SolarOnly` as selectable, working charging modes alongside the existing
`Power` mode — smoothed-surplus-driven charging (UC01/UC02), gated by an active SOC limit, selectable
via a new `select.smart_charging_mode` entity.

**Architecture:** Extends the Power-mode MVP's coordinator (M1) with: net-import smoothing (E7
extension), an SOC-Target resolver scoped to the current `Manual`-only system (E3, new), two new
stateful mode engines (`modes/solar.py`, `modes/solar_only.py` — E1), a shared amp-step rounding
helper, a new `ev_soc` adapter role (RA1 extension), and two new owned entities
(`select.smart_charging_mode`, `number.smart_charging_soc_limit_override` — C2 extension) plus a
read-only `sensor.smart_charging_active_mode`. Grid-safety (E6) and floor/cap (E8) are reused
unchanged. See the design doc: [`2026-07-20-solar-solaronly-design.md`](2026-07-20-solar-solaronly-design.md).

**Tech Stack:** Same as the Power MVP — Python ≥3.12, Home Assistant, `pytest`,
`pytest-homeassistant-custom-component` (HA harness, test-only per ADR-0009), `ruff`. Pure logic
(`modes/`, `engines/`) uses plain pytest; adapters/coordinator/entities/config-flow use the HA harness.

**Model:** Per CLAUDE.md, this is development work — execute on **Sonnet**.

---

## Conventions used throughout

Same as `2026-07-18-power-mvp.md`'s conventions section (package root, tests-mirror-1:1, canonical
states, ADR-0007 fault rule, ADR-0006 two-distinct-clamps rule, engine purity, commit-after-green,
re-check `git branch --show-current` before every commit). Additionally:

- **Stateful pure functions.** `Solar`/`SolarOnly`'s `step()` and the new smoothing function take
  their prior state and the current wall-clock time as explicit parameters and return the new state
  — never read the clock or hold state themselves (ADR-0006/0009 purity; matches the existing
  pattern `engines/signal_conditioning.py`'s NF4 fallback and `engines/cycle_invariant.py`'s floor/cap
  already established for stateless pure functions, extended here to the stateful case system-design
  §3 specifies for E7/E8-family engines).
- **`now` is injected, never `datetime.now()`-called, inside `modes/` or `engines/`** — the coordinator
  (M1) supplies it, so tests can pass fixed timestamps without monkeypatching the clock.

---

## Phase 1 — Pure engines & modes (plain pytest, no HA)

### Task 1.1: Net-import smoothing (E7 extension, R10)

Extends `engines/signal_conditioning.py` (voltage NF4 slice already ships) with a rolling mean over
the last *N* raw `net_w` samples. Stateful: the window is a parameter threaded by M1, not held inside
the function.

**Files:**
- Modify: `custom_components/smart_charging/engines/signal_conditioning.py`
- Modify: `tests/engines/test_signal_conditioning.py`

**Step 1: Write the failing tests**

```python
"""Additions: R10 net-import smoothing (window threaded as state)."""

from custom_components.smart_charging.engines.signal_conditioning import smooth_net_power


def test_window_fills_and_averages():
    window = ()
    for sample in (1000.0, 1200.0, 1100.0, 1300.0):
        smoothed, window = smooth_net_power(sample, window, size=4)
    assert smoothed == (1000.0 + 1200.0 + 1100.0 + 1300.0) / 4


def test_window_not_yet_full_averages_available_samples():
    # R10 edge case: at startup, average over what's collected so far.
    smoothed, window = smooth_net_power(1000.0, (), size=4)
    assert smoothed == 1000.0
    smoothed, window = smooth_net_power(1200.0, window, size=4)
    assert smoothed == 1100.0


def test_single_cycle_spike_does_not_move_full_window_much():
    window = (1000.0, 1000.0, 1000.0, 1000.0)
    smoothed, _ = smooth_net_power(5000.0, window, size=4)
    # One spike among 4 samples: (1000*3 + 5000) / 4 = 2000 -- moved, but the OLD value
    # (1000) is still the smoothed result read on the SAME cycle as the spike, since the
    # spike only enters the window for the cycle that reads it; the caller reads `smoothed`
    # which already includes it by construction of this function's contract (returns the
    # window WITH the new sample folded in). The "single spike doesn't move the set-point"
    # requirement is a property of the mode's amp-step rounding tolerance, not of this
    # function -- covered by the mode-level closed-loop regression (Task 1.4/1.5), not here.
    assert smoothed == 2000.0


def test_window_slides_oldest_sample_out_once_full():
    window = (1000.0, 1000.0, 1000.0, 1000.0)
    _, window = smooth_net_power(5000.0, window, size=4)
    assert window == (1000.0, 1000.0, 1000.0, 5000.0)
```

**Step 2: Run to verify failure** → `ImportError` for `smooth_net_power`.

**Step 3: Implement**

```python
# Append to engines/signal_conditioning.py

def smooth_net_power(
    raw_w: float, window: tuple[float, ...], size: int
) -> tuple[float, tuple[float, ...]]:
    """Fold `raw_w` into a rolling window and return (smoothed_mean, new_window) (R10).

    Averages over however many samples are collected so far when the window isn't
    yet full (start-up/restart edge case). The window is a plain parameter -- the
    caller (M1) threads it across cycles; this function holds no state itself.
    """
    new_window = (*window, raw_w)[-size:]
    return sum(new_window) / len(new_window), new_window
```

Update the module docstring: remove "R10 smoothing of net/solar power is deferred to a later
slice" and replace with "R10: `smooth_net_power` smooths `net_w` only; `solar_power` smoothing is
deferred to whichever later slice first consumes that role (see design doc §6)."

**Step 4: Run** → PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/engines/signal_conditioning.py tests/engines/test_signal_conditioning.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add net-import smoothing to Signal-Conditioning engine (E7, R10)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 1.2: SOC-Target engine (E3, row-3-only)

New module. Resolves the active SOC limit. Full R7 has three priority rows; rows 1–2 are
structurally inert without `Auto`/UC06 (design doc §5) — this is the complete, correct behavior for
the system as it exists, not a stub.

**Files:**
- Create: `custom_components/smart_charging/engines/soc_target.py`
- Test: `tests/engines/test_soc_target.py`

**Step 1: Failing tests**

```python
"""Plain-pytest tests for the SOC-Target engine (E3, row-3-only slice)."""

from custom_components.smart_charging.engines.soc_target import resolve_active_soc_limit


def test_resolves_to_the_configured_override():
    assert resolve_active_soc_limit(soc_limit_override=80.0) == 80.0


def test_tracks_a_changed_override():
    assert resolve_active_soc_limit(soc_limit_override=65.0) == 65.0
```

**Step 2: Run** → `ImportError`.

**Step 3: Implement**

```python
"""SOC-Target engine (E3). Pure -- no HA imports.

Full R7 has three priority rows (solar-reserve cap -> solar step-up -> default).
Rows 1-2 require the Auto profile (E2) and the solar step-up mechanism (UC06/R8),
neither of which exists yet -- row 1 can structurally never match without Auto
(R7's own note: "under Manual, row 1 never matches"), and row 2 has no step-up
mechanism to trigger it. Row 3 -- the configured override -- is therefore the
COMPLETE resolution for the system as it currently exists, not a stub; rows 1-2
are added here (not as a new service) once E2/UC06 land.
"""


def resolve_active_soc_limit(soc_limit_override: float) -> float:
    """Return the active SOC limit (R7, row 3: the configured default/override)."""
    return soc_limit_override
```

**Step 4: Run** → PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/engines/soc_target.py tests/engines/test_soc_target.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add SOC-Target engine (E3), row-3-only resolution

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 1.3: Shared amp-step rounding helper

Pure helper shared by `Solar` (fixed `round_up`) and `SolarOnly` (configurable). Not an Engine of its
own — a utility inside E1's `modes/` home (design doc §6).

**Files:**
- Create: `custom_components/smart_charging/modes/_amp_step.py`
- Test: `tests/modes/test_amp_step.py`

**Step 1: Failing tests**

```python
"""Plain-pytest tests for the shared amp-step rounding helper."""

from custom_components.smart_charging.modes._amp_step import round_amp_step


def test_round_up_uses_all_surplus_accepting_grid_topup():
    # 10.4 A ideal -> 11 A (Solar's fixed strategy; R1).
    assert round_amp_step(10.4, strategy="round_up") == 11.0


def test_round_down_never_imports():
    # 10.9 A ideal -> 10 A (SolarOnly default; R2).
    assert round_amp_step(10.9, strategy="round_down") == 10.0


def test_round_nearest_below_midpoint_rounds_down():
    assert round_amp_step(10.4, strategy="round_nearest", midpoint=0.5) == 10.0


def test_round_nearest_above_midpoint_rounds_up():
    assert round_amp_step(10.6, strategy="round_nearest", midpoint=0.5) == 11.0


def test_round_nearest_at_configured_midpoint_rounds_up():
    # "Pendel" edge case (R2, 3c): at the exact configured midpoint, this call rounds up;
    # a caller feeding the same 10.5 ideal every cycle will see the set-point oscillate
    # only if the *ideal* value itself flickers around the midpoint from sensor noise --
    # this function is a pure per-call rounding rule and does not dampen that (by design,
    # per UC02's "not actively dampened" note).
    assert round_amp_step(10.5, strategy="round_nearest", midpoint=0.5) == 11.0


def test_round_nearest_custom_midpoint():
    # A 30% midpoint means anything above ideal-floor+0.3 rounds up.
    assert round_amp_step(10.2, strategy="round_nearest", midpoint=0.3) == 11.0
    assert round_amp_step(10.29, strategy="round_nearest", midpoint=0.3) == 10.0
```

**Step 2: Run** → `ImportError`.

**Step 3: Implement**

```python
"""Shared amp-step rounding helper for the solar modes (R1/R2).

Not an Engine of its own -- a pure utility both `modes/solar.py` and
`modes/solar_only.py` call with their own strategy, keeping the rounding math out
of each mode's state-machine logic without coupling the two modes together (NF2).
"""

import math


def round_amp_step(ideal_a: float, strategy: str, midpoint: float = 0.5) -> float:
    """Convert a continuous ideal current into a whole-ampere set-point.

    `round_up` -- ceiling (accepts a bounded grid top-up; Solar's fixed strategy, R1).
    `round_down` -- floor (never imports; SolarOnly's default, R2).
    `round_nearest` -- whichever whole ampere is closer, using `midpoint` as the
    fractional threshold at/above which the value rounds up (R2, "pendel" case).
    """
    if strategy == "round_up":
        return math.ceil(ideal_a)
    if strategy == "round_down":
        return math.floor(ideal_a)
    if strategy == "round_nearest":
        floor_a = math.floor(ideal_a)
        fraction = ideal_a - floor_a
        return floor_a + 1.0 if fraction >= midpoint else floor_a
    raise ValueError(f"unknown amp-step rounding strategy: {strategy!r}")
```

**Step 4: Run** → PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/modes/_amp_step.py tests/modes/test_amp_step.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add shared amp-step rounding helper (R1/R2)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 1.4: Solar mode engine (E1 — UC01)

Stateful state machine: `Idle → Charging → Hold → Cooldown → SocReached`, per UC01's state model.
State is a small dataclass threaded by M1 (never HA-held).

**Files:**
- Create: `custom_components/smart_charging/modes/solar.py`
- Test: `tests/modes/test_solar.py`

**Step 1: Failing tests**

```python
"""Plain-pytest tests for the Solar mode engine (E1 -- UC01)."""

from custom_components.smart_charging.modes.solar import SolarState, step

DEFAULTS = dict(
    start_threshold_w=150.0,
    min_a=6.0,
    max_a=16.0,
    hold_minutes=5.0,
    cooldown_minutes=2.0,
)


def test_idle_stays_idle_below_start_threshold():
    desired, state = step(surplus_w=100.0, state=SolarState.idle(), now=0.0, **DEFAULTS)
    assert desired == 0.0
    assert state.phase == "idle"


def test_starts_charging_at_start_threshold_rounding_up():
    # 150 W @ 230 V = 0.652 A -> rounds UP (fixed) to 1 A, then floored to min_a by
    # the coordinator's E8 stage -- this engine returns its own ideal-to-amp-step
    # result unclamped by min/max (that stays E8's job per the design's control-flow
    # ordering); here we assert the mode's own arithmetic only.
    desired, state = step(surplus_w=150.0, state=SolarState.idle(), now=0.0, **DEFAULTS)
    assert state.phase == "charging"
    assert desired >= 1.0


def test_closed_loop_no_oscillation_when_own_draw_is_in_net_w():
    # Regression E1 calls for: a mode must hold steady, not oscillate, when its own
    # charging draw is itself part of the net_w the surplus formula reads. Feeding a
    # *constant* surplus across cycles (as a stabilized closed loop would present it)
    # must yield the same set-point every cycle, not drift.
    state = SolarState.idle()
    desired1, state = step(surplus_w=2300.0, state=state, now=0.0, **DEFAULTS)
    desired2, state = step(surplus_w=2300.0, state=state, now=10.0, **DEFAULTS)
    assert desired1 == desired2


def test_grid_fallback_below_minimum_current():
    # Surplus at/above start threshold but below the minimum-current equivalent power
    # -> hold at minimum, drawing the shortfall from the grid (3a).
    state = SolarState.idle()
    _, state = step(surplus_w=200.0, state=state, now=0.0, **DEFAULTS)
    desired, state = step(surplus_w=200.0, state=state, now=10.0, **DEFAULTS)
    assert desired == DEFAULTS["min_a"]
    assert state.phase == "charging"  # grid fallback is a set-point condition, not a state


def test_post_surplus_hold_then_resume_within_period():
    state = SolarState.idle()
    _, state = step(surplus_w=2300.0, state=state, now=0.0, **DEFAULTS)  # -> charging
    _, state = step(surplus_w=50.0, state=state, now=10.0, **DEFAULTS)  # -> hold
    assert state.phase == "hold"
    desired, state = step(surplus_w=2300.0, state=state, now=60.0, **DEFAULTS)  # within 5 min
    assert state.phase == "charging"
    assert desired > 0.0


def test_post_surplus_hold_elapses_into_cooldown_then_idle():
    state = SolarState.idle()
    _, state = step(surplus_w=2300.0, state=state, now=0.0, **DEFAULTS)  # -> charging
    _, state = step(surplus_w=50.0, state=state, now=10.0, **DEFAULTS)  # -> hold @ t=10
    desired, state = step(surplus_w=50.0, state=state, now=10.0 + 5 * 60, **DEFAULTS)
    assert desired == 0.0
    assert state.phase == "cooldown"


def test_cooldown_blocks_restart_until_elapsed():
    state = SolarState.idle()
    _, state = step(surplus_w=2300.0, state=state, now=0.0, **DEFAULTS)
    _, state = step(surplus_w=50.0, state=state, now=10.0, **DEFAULTS)  # -> hold
    _, state = step(surplus_w=50.0, state=state, now=10.0 + 5 * 60, **DEFAULTS)  # -> cooldown
    cooldown_start = 10.0 + 5 * 60
    desired, state = step(
        surplus_w=2300.0, state=state, now=cooldown_start + 30, **DEFAULTS
    )
    assert desired == 0.0
    assert state.phase == "cooldown"  # still within the 2 min cooldown
    desired, state = step(
        surplus_w=2300.0, state=state, now=cooldown_start + 2 * 60 + 1, **DEFAULTS
    )
    assert state.phase == "charging"


def test_soc_reached_forces_stop_and_latches():
    # SOC-gating itself is the coordinator's job (it doesn't call step() at all once
    # reached), but SolarState exposes an explicit soc_reached() transition so the
    # coordinator can latch the phase for the active_mode sensor / next-cycle logic.
    state = SolarState.idle()
    _, state = step(surplus_w=2300.0, state=state, now=0.0, **DEFAULTS)
    state = state.soc_reached()
    assert state.phase == "soc_reached"
```

**Step 2: Run** → `ImportError`.

**Step 3: Implement**

```python
"""Solar charging-mode engine (E1 -- UC01). Pure -- no HA imports (ADR-0006/0009).

State machine: Idle -> Charging -> Hold -> Cooldown -> SocReached, per UC01's state
model. State is a small frozen dataclass threaded by the coordinator (M1) -- this
module holds nothing itself; `now` (seconds, monotonic) is always injected.
"""

from __future__ import annotations

from dataclasses import dataclass

from ._amp_step import round_amp_step


@dataclass(frozen=True)
class SolarState:
    phase: str  # "idle" | "charging" | "hold" | "cooldown" | "soc_reached"
    phase_started_at: float = 0.0

    @classmethod
    def idle(cls) -> "SolarState":
        return cls(phase="idle")

    def soc_reached(self) -> "SolarState":
        return SolarState(phase="soc_reached")


def step(
    surplus_w: float,
    state: SolarState,
    now: float,
    start_threshold_w: float,
    min_a: float,
    max_a: float,
    hold_minutes: float,
    cooldown_minutes: float,
    voltage: float = 230.0,
) -> tuple[float, SolarState]:
    """Return (desired_current, next_state) for one control cycle (UC01).

    `min_a`/`max_a` are used only to decide grid-fallback vs. hold/stop transitions
    (R1's own set-point rule reads the minimum); the floor/cap invariant itself is
    still applied once, downstream, by the coordinator's E8 stage -- this function
    does not re-clamp to `max_a` beyond what `round_amp_step` already returns from a
    bounded ideal.
    """
    if state.phase == "soc_reached":
        return 0.0, state

    ideal_a = surplus_w / voltage

    if state.phase in ("idle", "cooldown"):
        elapsed = now - state.phase_started_at
        cooldown_done = state.phase == "idle" or elapsed >= cooldown_minutes * 60
        if surplus_w >= start_threshold_w and cooldown_done:
            return _charging_setpoint(ideal_a, min_a), SolarState("charging", now)
        if state.phase == "idle":
            return 0.0, state
        return 0.0, state  # still cooling down

    if state.phase == "charging":
        if surplus_w < start_threshold_w:
            return min_a, SolarState("hold", now)
        return _charging_setpoint(ideal_a, min_a), state

    if state.phase == "hold":
        if surplus_w >= start_threshold_w:
            return _charging_setpoint(ideal_a, min_a), SolarState("charging", now)
        if now - state.phase_started_at >= hold_minutes * 60:
            return 0.0, SolarState("cooldown", now)
        return min_a, state

    raise ValueError(f"unknown SolarState.phase: {state.phase!r}")


def _charging_setpoint(ideal_a: float, min_a: float) -> float:
    """Round up (fixed, R1), floored at the minimum current (grid fallback)."""
    return max(round_amp_step(ideal_a, strategy="round_up"), min_a)
```

**Step 4: Run** → PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/modes/solar.py tests/modes/test_solar.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add Solar mode engine (E1) state machine per UC01

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 1.5: SolarOnly mode engine (E1 — UC02)

Simpler state machine than `Solar`: `Idle → Charging → Cooldown → SocReached` — no `Hold`, no grid
fallback, configurable rounding strategy.

**Files:**
- Create: `custom_components/smart_charging/modes/solar_only.py`
- Test: `tests/modes/test_solar_only.py`

**Step 1: Failing tests**

```python
"""Plain-pytest tests for the SolarOnly mode engine (E1 -- UC02)."""

from custom_components.smart_charging.modes.solar_only import SolarOnlyState, step

DEFAULTS = dict(
    start_threshold_w=1300.0,
    min_a=6.0,
    max_a=16.0,
    cooldown_minutes=2.0,
    strategy="round_down",
    midpoint=0.5,
)


def test_idle_below_threshold():
    desired, state = step(surplus_w=500.0, state=SolarOnlyState.idle(), now=0.0, **DEFAULTS)
    assert desired == 0.0 and state.phase == "idle"


def test_starts_at_threshold_default_round_down_never_imports():
    desired, state = step(surplus_w=1380.0, state=SolarOnlyState.idle(), now=0.0, **DEFAULTS)
    # 1380 W / 230 V = 6.0 A ideal -> round_down = 6 A (no grid import).
    assert state.phase == "charging"
    assert desired == 6.0


def test_immediate_stop_no_hold_no_grid_fallback():
    state = SolarOnlyState.idle()
    _, state = step(surplus_w=1400.0, state=state, now=0.0, **DEFAULTS)
    desired, state = step(surplus_w=500.0, state=state, now=10.0, **DEFAULTS)
    assert desired == 0.0
    assert state.phase == "cooldown"  # not "hold" -- SolarOnly has no hold phase


def test_round_up_strategy_configured():
    desired, state = step(
        surplus_w=1450.0,  # 6.3 A ideal
        state=SolarOnlyState.idle(),
        now=0.0,
        **{**DEFAULTS, "strategy": "round_up"},
    )
    assert desired == 7.0


def test_cooldown_blocks_restart_until_elapsed():
    state = SolarOnlyState.idle()
    _, state = step(surplus_w=1400.0, state=state, now=0.0, **DEFAULTS)
    _, state = step(surplus_w=500.0, state=state, now=10.0, **DEFAULTS)  # -> cooldown @ t=10
    desired, state = step(surplus_w=1400.0, state=state, now=10.0 + 60, **DEFAULTS)
    assert desired == 0.0 and state.phase == "cooldown"
    desired, state = step(surplus_w=1400.0, state=state, now=10.0 + 2 * 60 + 1, **DEFAULTS)
    assert state.phase == "charging"


def test_soc_reached_latches():
    state = SolarOnlyState.idle()
    _, state = step(surplus_w=1400.0, state=state, now=0.0, **DEFAULTS)
    state = state.soc_reached()
    desired, state = step(surplus_w=1400.0, state=state, now=1.0, **DEFAULTS)
    assert desired == 0.0 and state.phase == "soc_reached"
```

**Step 2: Run** → `ImportError`.

**Step 3: Implement**

```python
"""SolarOnly charging-mode engine (E1 -- UC02). Pure -- no HA imports.

Simpler than Solar: Idle -> Charging -> Cooldown -> SocReached. No Hold, no grid
fallback -- surplus below the start threshold stops immediately (UC02's defining
difference from its sibling UC01).
"""

from __future__ import annotations

from dataclasses import dataclass

from ._amp_step import round_amp_step


@dataclass(frozen=True)
class SolarOnlyState:
    phase: str  # "idle" | "charging" | "cooldown" | "soc_reached"
    phase_started_at: float = 0.0

    @classmethod
    def idle(cls) -> "SolarOnlyState":
        return cls(phase="idle")

    def soc_reached(self) -> "SolarOnlyState":
        return SolarOnlyState(phase="soc_reached")


def step(
    surplus_w: float,
    state: SolarOnlyState,
    now: float,
    start_threshold_w: float,
    min_a: float,
    max_a: float,
    cooldown_minutes: float,
    strategy: str,
    midpoint: float = 0.5,
    voltage: float = 230.0,
) -> tuple[float, SolarOnlyState]:
    """Return (desired_current, next_state) for one control cycle (UC02)."""
    if state.phase == "soc_reached":
        return 0.0, state

    ideal_a = surplus_w / voltage

    if state.phase in ("idle", "cooldown"):
        elapsed = now - state.phase_started_at
        cooldown_done = state.phase == "idle" or elapsed >= cooldown_minutes * 60
        if surplus_w >= start_threshold_w and cooldown_done:
            return round_amp_step(ideal_a, strategy, midpoint), SolarOnlyState("charging", now)
        return 0.0, state

    if state.phase == "charging":
        if surplus_w < start_threshold_w:
            return 0.0, SolarOnlyState("cooldown", now)  # immediate -- no hold
        return round_amp_step(ideal_a, strategy, midpoint), state

    raise ValueError(f"unknown SolarOnlyState.phase: {state.phase!r}")
```

**Step 4: Run** → PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/modes/solar_only.py tests/modes/test_solar_only.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add SolarOnly mode engine (E1) state machine per UC02

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

> **⎔ Phase 1 checkpoint:** `pytest tests/modes tests/engines -v` all green; grep-confirm no
> `import homeassistant` under `modes/` or `engines/`. Every UC01/UC02 acceptance criterion in R1/R2
> has a corresponding test above.

---

## Phase 2 — Adapters (HA harness, RA1 extension)

### Task 2.1: `ev_soc` adapter role

**Files:**
- Modify: `custom_components/smart_charging/const.py` (add `CONF_EV_SOC_ENTITY`)
- Modify: `custom_components/smart_charging/adapters/factory.py`
- Modify: `tests/adapters/test_factory.py`

**Step 1: Failing test** — extend the existing factory test:

```python
# Add to tests/adapters/test_factory.py

async def test_factory_builds_ev_soc_role(hass):
    data = _data()
    data[CONF_EV_SOC_ENTITY] = "sensor.ev_soc"
    adapters = build_adapters(hass, data)
    assert isinstance(adapters["ev_soc"], NumericReadAdapter)
```

(Add `CONF_EV_SOC_ENTITY` to the test's imports.)

**Step 2: Run** → `KeyError`/`AttributeError` (constant doesn't exist).

**Step 3: Implement**

```python
# const.py -- append to the DATA block
CONF_EV_SOC_ENTITY = "ev_soc_entity"
```

```python
# adapters/factory.py -- add to build_adapters, required role (no None-safe .get; a
# missing ev_soc reading is the ADR-0007 fault signal like any other required role)
"ev_soc": NumericReadAdapter(hass, data[CONF_EV_SOC_ENTITY]),
```

**Step 4: Run** → PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/const.py custom_components/smart_charging/adapters/factory.py tests/adapters/test_factory.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add ev_soc adapter role (RA1 extension)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

> **⎔ Phase 2 checkpoint:** `pytest tests/adapters -v` green; `ev_soc` resolves through the factory
> like every other required role.

---

## Phase 3 — Config/options flow (C4 extension)

### Task 3.1: New config keys

**Files:** Modify `custom_components/smart_charging/const.py`

**Step 1: Append**

```python
# --- DATA addition ---
# CONF_EV_SOC_ENTITY already added in Task 2.1.

# --- OPTIONS additions ---
CONF_SMOOTHING_WINDOW = "smoothing_window"
CONF_SOLAR_START_THRESHOLD_W = "solar_start_threshold_w"
CONF_SOLAR_ONLY_START_THRESHOLD_W = "solar_only_start_threshold_w"
CONF_SOLAR_HOLD_MIN = "solar_hold_min"
CONF_SOLAR_COOLDOWN_MIN = "solar_cooldown_min"
CONF_SOLAR_ONLY_STRATEGY = "solar_only_strategy"  # "round_up" | "round_down" | "round_nearest"
CONF_SOLAR_ONLY_MIDPOINT = "solar_only_midpoint"
CONF_DEFAULT_SOC_LIMIT = "default_soc_limit"

DEFAULT_SMOOTHING_WINDOW = 4
DEFAULT_SOLAR_START_THRESHOLD_W = 150.0
DEFAULT_SOLAR_ONLY_START_THRESHOLD_W = 1300.0
DEFAULT_SOLAR_HOLD_MIN = 5.0
DEFAULT_SOLAR_COOLDOWN_MIN = 2.0
DEFAULT_SOLAR_ONLY_STRATEGY = "round_down"
DEFAULT_SOLAR_ONLY_MIDPOINT = 0.5
DEFAULT_SOC_LIMIT = 80.0
```

**Step 2: Commit** (constants only)

```bash
git add custom_components/smart_charging/const.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add config keys for Solar/SolarOnly thresholds + SOC limit

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 3.2: Extend the config/options flow

**Files:**
- Modify: `custom_components/smart_charging/config_flow.py`
- Modify: `tests/test_config_flow.py`

**Step 1: Failing tests** — extend the existing ADR-0005 flow test with the new fields (add
`CONF_EV_SOC_ENTITY: "sensor.ev_soc"` to the submitted `user_input`, assert it lands in `data`), plus:

```python
async def test_solar_thresholds_seeded_into_options_with_defaults(hass):
    # ... run the user flow with the new fields omitted from user_input where they have
    # defaults (e.g. leave solar_only_strategy unset) ...
    result = await _run_user_flow(hass)  # helper wrapping the Step-1 flow
    assert result["options"][CONF_SOLAR_ONLY_STRATEGY] == DEFAULT_SOLAR_ONLY_STRATEGY
    assert result["options"][CONF_DEFAULT_SOC_LIMIT] == DEFAULT_SOC_LIMIT


async def test_options_flow_edits_solar_thresholds(hass):
    entry = await _create_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**_current_options(entry), CONF_SOLAR_START_THRESHOLD_W: 200.0}
    )
    assert entry.options[CONF_SOLAR_START_THRESHOLD_W] == 200.0
```

**Step 2: Run** → FAIL (fields don't exist yet).

**Step 3: Implement** — add `vol.Required(CONF_EV_SOC_ENTITY): _entity("sensor")` to
`MAPPING_SCHEMA`; add the eight new options fields (with their `DEFAULT_*` constants) to
`OPTION_KEYS` and `_threshold_schema()`; `CONF_SOLAR_ONLY_STRATEGY` uses
`vol.In(["round_up", "round_down", "round_nearest"])`.

**Step 4: Run** → PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/config_flow.py tests/test_config_flow.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: extend config/options flow with ev_soc + Solar/SolarOnly settings

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

> **⎔ Phase 3 checkpoint:** a full install flow produces an entry with `ev_soc` in data and every new
> threshold + `default_soc_limit` in options; the options flow round-trips each new field without
> touching data.

---

## Phase 4 — Owned entities (C2 extension)

### Task 4.1: `select.smart_charging_mode`

**Files:**
- Create: `custom_components/smart_charging/select.py`
- Test: `tests/test_select.py`

**Step 1: Failing test**

```python
"""HA-harness test for the mode selector (C2)."""

from custom_components.smart_charging.select import ModeSelect


class _StubCoordinator:
    def __init__(self):
        self.active_mode = None
        self.refreshed = False

    async def async_request_refresh(self):
        self.refreshed = True


async def test_select_option_pushes_to_coordinator_and_resets_state(hass):
    coord = _StubCoordinator()
    entity = ModeSelect(entry_id="abc", coordinator=coord)
    await entity.async_select_option("Solar")
    assert coord.active_mode == "Solar"
    assert coord.refreshed is True
    assert entity.current_option == "Solar"


async def test_restores_last_selection(hass):
    # Simulate a restored state of "SolarOnly" via async_get_last_state -- follow the
    # RestoreEntity pattern used by TargetCurrentNumber (number.py) for a select entity.
    ...
```

**Step 2: Run** → `ImportError`.

**Step 3: Implement**

```python
"""Mode selector entity (C2). ADR-0004 native naming."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .entity import SmartChargingEntity

MODE_OPTIONS = ["Off", "Power", "Solar", "SolarOnly"]


class ModeSelect(SmartChargingEntity, RestoreEntity, SelectEntity):
    """User-set active charging mode. Static option list this slice (R18 deferred)."""

    _attr_translation_key = "mode"
    _attr_options = MODE_OPTIONS

    def __init__(self, entry_id: str, coordinator) -> None:
        super().__init__(entry_id)
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_mode"
        self._attr_current_option = "Off"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in MODE_OPTIONS:
            self._attr_current_option = last.state
        self._coordinator.active_mode = self._attr_current_option

    async def async_select_option(self, option: str) -> None:
        self._attr_current_option = option
        self._coordinator.active_mode = option  # coordinator resets mode-state (M1, Task 5.1)
        await self._coordinator.async_request_refresh()
        self.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([ModeSelect(entry_id=entry.entry_id, coordinator=coordinator)])
```

**Step 4: Run** → PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/select.py tests/test_select.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add select.smart_charging_mode entity (C2)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 4.2: `number.smart_charging_soc_limit_override`

Mirrors `TargetCurrentNumber` exactly (bounds 50–100, default from options `CONF_DEFAULT_SOC_LIMIT`).

**Files:**
- Modify: `custom_components/smart_charging/number.py` (add a second entity class)
- Modify: `tests/test_number.py`

**Step 1: Failing test** — same shape as `test_set_value_pushes_to_coordinator` but asserting
`coordinator.soc_limit_override` and bounds `50.0`–`100.0`.

**Step 2: Run** → `ImportError`.

**Step 3: Implement** — add `SocLimitOverrideNumber(SmartChargingEntity, RestoreNumber)` alongside
`TargetCurrentNumber`, and add it to `async_setup_entry`'s `async_add_entities` list.

**Step 4: Run** → PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/number.py tests/test_number.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add soc_limit_override number entity (C2)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 4.3: `sensor.smart_charging_active_mode`

Read-only diagnostic (C3-shaped) — mirrors the existing `sensor.smart_charging_status` pattern.

**Files:**
- Modify: `custom_components/smart_charging/sensor.py`
- Modify: `tests/test_sensor.py`

**Step 1: Failing test** — a sensor whose `native_value` reflects `coordinator.data.active_mode`
(or equivalent) after a refresh.

**Step 2: Run** → FAIL. **Step 3: Implement** — add `ActiveModeSensor` alongside the existing status
sensor, reading the resolved mode off the coordinator's last cycle result.

**Step 4: Run** → PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/sensor.py tests/test_sensor.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add sensor.smart_charging_active_mode read-only diagnostic

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

> **⎔ Phase 4 checkpoint:** all three entities restore state correctly; the selector's write path
> reaches the coordinator; `pytest tests/test_select.py tests/test_number.py tests/test_sensor.py -v`
> green.

---

## Phase 5 — Coordinator (M1 extension)

### Task 5.1: Wire smoothing, SOC gate, mode dispatch, and state reset

The largest task: extends `_run_cycle` to read `ev_soc`, smooth `net_w`, resolve the active SOC
limit, dispatch to the active mode (threading each mode's own state, resetting it on a mode switch),
and gate on SOC — all **before** the existing E6/E8 stages, which are untouched.

**Files:**
- Modify: `custom_components/smart_charging/coordinator.py`
- Modify: `tests/test_coordinator.py`

**Step 1: Failing tests** — extend the existing HA-harness coordinator suite with (at minimum):

```python
async def test_dispatches_to_solar_when_selected(hass, ...):
    """With active_mode="Solar" and sufficient surplus, one cycle starts charging."""

async def test_dispatches_to_solar_only_when_selected(hass, ...):
    """Same shape for SolarOnly."""

async def test_soc_at_or_above_limit_forces_zero_regardless_of_mode(hass, ...):
    """ev_soc >= soc_limit_override -> 0 A even with ample surplus."""

async def test_mode_switch_resets_the_incoming_modes_state(hass, ...):
    """Solar's Hold/Cooldown state does not leak into a fresh Solar selection after
    switching away and back (R11 mode-switch reset)."""

async def test_grid_ceiling_still_clamps_a_solar_request(hass, ...):
    """E6 (unchanged) still reduces a Solar-mode request that would breach the ceiling."""

async def test_power_mode_behavior_unchanged(hass, ...):
    """Existing Power-mode MVP tests continue to pass verbatim."""
```

**Step 2: Run** → FAIL (dispatch doesn't exist yet).

**Step 3: Implement** — sketch (full code follows the existing `_run_cycle` structure):

```python
# coordinator.py -- additions

from .engines.signal_conditioning import resolve_voltage, smooth_net_power
from .engines.soc_target import resolve_active_soc_limit
from .modes import power, solar, solar_only

# __init__: add self._net_window: tuple[float, ...] = (); self._mode_state = {}
#   (dict keyed by mode name, e.g. {"Solar": SolarState.idle(), "SolarOnly": SolarOnlyState.idle()})
# and self.active_mode: str = "Off"; self.soc_limit_override: float = DEFAULT_SOC_LIMIT;
# self._last_active_mode: str | None = None (to detect a switch).

# In _run_cycle, after reading status/net_w/charger_w/voltage as today, add:
ev_soc = await self._adapters["ev_soc"].read()
if ev_soc is None:
    # required role -> fault, same as any other (ADR-0007)
    ...

smoothed_net_w, self._net_window = smooth_net_power(
    net_w, self._net_window, size=self._config["smoothing_window"]
)
active_soc_limit = resolve_active_soc_limit(self.soc_limit_override)

if self.active_mode != self._last_active_mode:
    self._mode_state = {  # R11: switching mode resets timers -- fresh state for the new mode
        "Solar": solar.SolarState.idle(),
        "SolarOnly": solar_only.SolarOnlyState.idle(),
    }
    self._last_active_mode = self.active_mode

now = self.hass.loop.time()  # injected, not read inside modes/engines

if status not in CHARGEABLE_STATES or ev_soc >= active_soc_limit:
    desired = 0.0
    if ev_soc >= active_soc_limit:
        for key, state in self._mode_state.items():
            if hasattr(state, "soc_reached"):
                self._mode_state[key] = state.soc_reached()
elif self.active_mode == "Off":
    desired = 0.0
elif self.active_mode == "Power":
    desired = power.desired_current(self.target_current, status)
elif self.active_mode == "Solar":
    surplus_w = charger_w - smoothed_net_w
    desired, self._mode_state["Solar"] = solar.step(
        surplus_w, self._mode_state["Solar"], now,
        start_threshold_w=self._config["solar_start_threshold_w"],
        min_a=self._config["min_current"], max_a=self._config["max_current"],
        hold_minutes=self._config["solar_hold_min"],
        cooldown_minutes=self._config["solar_cooldown_min"], voltage=voltage,
    )
elif self.active_mode == "SolarOnly":
    surplus_w = charger_w - smoothed_net_w
    desired, self._mode_state["SolarOnly"] = solar_only.step(
        surplus_w, self._mode_state["SolarOnly"], now,
        start_threshold_w=self._config["solar_only_start_threshold_w"],
        min_a=self._config["min_current"], max_a=self._config["max_current"],
        cooldown_minutes=self._config["solar_cooldown_min"],
        strategy=self._config["solar_only_strategy"],
        midpoint=self._config["solar_only_midpoint"], voltage=voltage,
    )

# ... unchanged from here: clamp_to_ceiling (E6), apply_floor_cap (E8), write, return.
# CycleResult gains an `active_mode: str` field so sensor.py's ActiveModeSensor can read it.
```

**Step 4: Run** → PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/coordinator.py tests/test_coordinator.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: wire Solar/SolarOnly dispatch, SOC gate, and smoothing into M1

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

> **⎔ Phase 5 checkpoint:** the full ordered cycle (read → smooth → resolve SOC → dispatch → E6 → E8
> → write) runs for all four modes against a mocked hardware state; grid ceiling and floor/cap still
> apply unconditionally; a mode switch demonstrably resets state; the existing Power-mode regression
> suite is unchanged and green.

---

## Phase 6 — Integration wiring & docs

### Task 6.1: Register the `select` platform + seed new coordinator fields

**Files:**
- Modify: `custom_components/smart_charging/__init__.py` (add `Platform.SELECT` to the forwarded
  platforms list; pass the new options into the coordinator's `config` dict)
- Modify: `tests/test_init.py`

**Step 1: Failing test** — setup produces a `select.smart_charging_mode` entity alongside the
existing `number`/`sensor` entities. **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** →
PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/__init__.py tests/test_init.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: register select platform and thread Solar/SolarOnly config

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 6.2: End-to-end HA-harness regression per UC01/UC02

**Files:** Create `tests/test_solar_end_to_end.py`

**Step 1–4:** One test per UC01/UC02 main-success-scenario + each alternate flow (2a cooldown-block,
3a grid-fallback, 3b post-surplus-hold for UC01; 3a immediate-stop, 3b round-up, 3c round-nearest for
UC02), driven through `hass.config_entries` + a full `async_update_data()` cycle against mocked
entity states — not calling `modes.solar.step` directly (that's Phase 1's job; this suite proves the
wiring). **Step 5: Commit.**

```bash
git add tests/test_solar_end_to_end.py
git commit --author="Claude <noreply@anthropic.com>" -m "test: add end-to-end HA-harness regression for UC01/UC02

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 6.3: Translations, strings, README

**Files:**
- Modify: `custom_components/smart_charging/strings.json` + `translations/en.json` (new
  `select.mode` options/name, `number.soc_limit_override`, `sensor.active_mode`, new config/options
  field labels)
- Modify: `README.md` (Configuration table: add EV SOC entity row and the new threshold options;
  move `Solar`/`SolarOnly` from "Deferred" to the feature list; update the status banner)

**Step 1: Run `python -m script.hassfest` (or the project's validation task) to confirm strings
completeness. Step 2: Commit.**

```bash
git add custom_components/smart_charging/strings.json custom_components/smart_charging/translations/en.json README.md
git commit --author="Claude <noreply@anthropic.com>" -m "docs: translations + README for Solar/SolarOnly modes

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

> **⎔ Phase 6 / slice checkpoint:** `ruff check . && ruff format --check . && pytest -q` all green;
> HACS/hassfest validation passes; a manual HA install can select `Solar` or `SolarOnly` from the new
> selector and observe correct start/stop/hold/cooldown behavior against a real or simulated solar
> feed, with the existing `Power` mode and grid-ceiling safety behavior unchanged.
