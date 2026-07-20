# Solar & SolarOnly Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `Solar` and `SolarOnly` as selectable, working charging modes alongside the existing
`Power` mode — smoothed-surplus-driven charging (UC01/UC02), gated by an active SOC limit, selectable
via a new `select.smart_charging_mode` entity whose option list is itself gated by a new
**Solar installed** config-time toggle (R18, scoped — design doc §3/§4).

**Architecture:** Extends the Power-mode MVP's coordinator (M1) with: net-import smoothing (E7
extension), an SOC-Target resolver scoped to the current `Manual`-only system (E3, new), two new
stateful mode engines (`modes/solar.py`, `modes/solar_only.py` — E1), a shared amp-step rounding
helper, a new `ev_soc` adapter role (RA1 extension), a new `CONF_SOLAR_INSTALLED` data-bucket toggle
that gates `ev_soc`'s requiredness and the mode selector's options, and two new owned entities
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
    # A 30% midpoint means anything below ideal-floor+0.3 rounds down, at/above rounds up.
    assert round_amp_step(10.2, strategy="round_nearest", midpoint=0.3) == 10.0
    assert round_amp_step(10.4, strategy="round_nearest", midpoint=0.3) == 11.0
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


def test_deterministic_given_identical_inputs():
    # A per-call sanity check only: step() is a pure function, so identical inputs at
    # two different `now`s (mid-charging, no phase transition in between) yield the
    # same output. This is NOT the closed-loop no-oscillation regression E1 calls for
    # (a mode must hold steady when its own draw is part of the net_w it reads back) --
    # that needs a feedback model (commanded current -> charger_w -> net_w -> next
    # surplus_w) and lives in the Task 6.2 end-to-end suite instead, where the real
    # adapter/coordinator wiring makes that feedback loop meaningful to construct.
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


```

**No SOC-related phase or test here.** SOC-gating is entirely the coordinator's responsibility (M1,
Task 5.1) — per R7's own framing, a mode "has no opinion on *why* the limit is where it is," so
`SolarState` only ever has `idle`/`charging`/`hold`/`cooldown`. The coordinator forces a gated mode's
state back to `idle()` for as long as the SOC gate holds and simply stops calling `step()` at all;
the mode never sees the reason. This also means both of R7's resume conditions (the limit rising, or
unplug/replug) are exercised at the coordinator level (Task 5.1's tests), not here — see the design
doc §5's "Where the SOC gate itself lives" note for the reasoning. (An earlier draft of this task had
a mode-level `soc_reached()` phase with no way back out of it, which could never resume charging
after a limit increase or a reconnect — removed for that reason.)

**Step 2: Run** → `ImportError`.

**Step 3: Implement**

```python
"""Solar charging-mode engine (E1 -- UC01). Pure -- no HA imports (ADR-0006/0009).

State machine: Idle -> Charging -> Hold -> Cooldown, per UC01's state model, MINUS
the SocReached phase UC01's own diagram draws -- that transition is entirely the
coordinator's responsibility (M1), not this module's (see design doc §5's "Where
the SOC gate itself lives"): a mode "has no opinion on why the limit is where it
is" (R7), so it is never told SOC was reached at all -- the coordinator simply
stops calling step() and holds this state at idle() for as long as the gate holds.
State is a small frozen dataclass threaded by the coordinator -- this module holds
nothing itself; `now` (seconds, monotonic) is always injected.
"""

from __future__ import annotations

from dataclasses import dataclass

from ._amp_step import round_amp_step


@dataclass(frozen=True)
class SolarState:
    phase: str  # "idle" | "charging" | "hold" | "cooldown"
    phase_started_at: float = 0.0

    @classmethod
    def idle(cls) -> "SolarState":
        return cls(phase="idle")


def step(
    surplus_w: float,
    state: SolarState,
    now: float,
    start_threshold_w: float,
    min_a: float,
    hold_minutes: float,
    cooldown_minutes: float,
    voltage: float = 230.0,
) -> tuple[float, SolarState]:
    """Return (desired_current, next_state) for one control cycle (UC01).

    `min_a` is used to decide grid-fallback vs. hold/stop transitions (R1's own
    set-point rule reads the minimum); the floor/cap invariant itself is still
    applied once, downstream, by the coordinator's E8 stage. There is no `max_a`
    parameter: this function never produces a value above the maximum on its own
    (the ideal current is bounded by the surplus itself, not clamped here), and E8
    remains the single place the upper bound is enforced -- avoiding a second,
    redundant clamp site for the same invariant.
    """
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
    cooldown_minutes=2.0,
    strategy="round_down",
    midpoint=0.5,
)

# NOTE (reconciling with the design doc's minor finding): at nominal 230 V, 1300 W is
# 5.65 A -- below the 6 A minimum (which needs 1380 W). Surplus in 1300-1379 W therefore
# enters "charging" per this threshold but is floored to 0 A by the coordinator's E8
# stage downstream, in slight tension with UC02's "threshold chosen so the minimum can
# be met from solar alone." The boundary test below pins this down explicitly rather
# than leaving it implicit; if this executor pass or the review after it decides the gap
# is worth closing, the fix is raising the default threshold to 1380 W (E8's floor stays
# the actual invariant either way -- this is a threshold-tuning question, not a bug).


def test_at_exactly_the_default_threshold_ideal_current_is_below_minimum():
    # Documents the 1300 W vs 1380 W boundary gap above rather than hiding it.
    desired, state = step(surplus_w=1300.0, state=SolarOnlyState.idle(), now=0.0, **DEFAULTS)
    assert state.phase == "charging"
    assert desired < DEFAULTS["min_a"]  # E8 (coordinator, unchanged) floors this to 0 A


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


```

**No SOC-related phase or test here** — same reasoning as `Solar` (Task 1.4): SOC-gating is the
coordinator's job (Task 5.1), so `SolarOnlyState` only has `idle`/`charging`/`cooldown`.

**Step 2: Run** → `ImportError`.

**Step 3: Implement**

```python
"""SolarOnly charging-mode engine (E1 -- UC02). Pure -- no HA imports.

Simpler than Solar: Idle -> Charging -> Cooldown. No Hold, no grid fallback --
surplus below the start threshold stops immediately (UC02's defining difference
from its sibling UC01). No SOC-related phase either -- see Solar's module
docstring (modes/solar.py) for why that's the coordinator's job, not this
module's.
"""

from __future__ import annotations

from dataclasses import dataclass

from ._amp_step import round_amp_step


@dataclass(frozen=True)
class SolarOnlyState:
    phase: str  # "idle" | "charging" | "cooldown"
    phase_started_at: float = 0.0

    @classmethod
    def idle(cls) -> "SolarOnlyState":
        return cls(phase="idle")


def step(
    surplus_w: float,
    state: SolarOnlyState,
    now: float,
    start_threshold_w: float,
    min_a: float,
    cooldown_minutes: float,
    strategy: str,
    midpoint: float = 0.5,
    voltage: float = 230.0,
) -> tuple[float, SolarOnlyState]:
    """Return (desired_current, next_state) for one control cycle (UC02).

    No `max_a` parameter, for the same reason as `Solar.step()` -- E8 remains the
    single place the upper-bound invariant is enforced.
    """
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

`ev_soc` is **optional at the factory level** — the same pattern `grid_voltage` already uses —
**not** an unconditionally-required role like `net_power`/`charger_power`. This is what lets an
existing Power-MVP config entry (which has no `ev_soc_entity` in its data) load unchanged with no
migration (design doc §8/§9): the role is simply absent from the built adapter set, which only
matters once `Solar`/`SolarOnly` is selected (Task 5.1 makes a *missing* `ev_soc` role a fault only
while one of those two modes is active — unlike `grid_voltage`, whose absence is never a fault at
all, NF4).

**Step 1: Failing test** — extend the existing factory test:

```python
# Add to tests/adapters/test_factory.py

async def test_factory_builds_ev_soc_role_when_configured(hass):
    data = _data()
    data[CONF_EV_SOC_ENTITY] = "sensor.ev_soc"
    adapters = build_adapters(hass, data)
    assert isinstance(adapters["ev_soc"], NumericReadAdapter)


async def test_ev_soc_role_absent_when_not_configured(hass):
    # An existing Power-MVP entry predates this field entirely (design doc §8/§9) --
    # build_adapters must not KeyError on it.
    adapters = build_adapters(hass, _data())
    assert "ev_soc" not in adapters
```

(Add `CONF_EV_SOC_ENTITY` to the test's imports.)

**Step 2: Run** → `KeyError`/`AttributeError` (constant doesn't exist).

**Step 3: Implement**

```python
# const.py -- append to the DATA block
CONF_EV_SOC_ENTITY = "ev_soc_entity"
```

```python
# adapters/factory.py -- add to build_adapters, OPTIONAL like grid_voltage (not required
# at the factory level -- Task 5.1 makes its absence a fault only when Solar/SolarOnly is
# the active mode, not unconditionally at setup)
if data.get(CONF_EV_SOC_ENTITY):
    adapters["ev_soc"] = NumericReadAdapter(hass, data[CONF_EV_SOC_ENTITY])
```

**Step 4: Run** → PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/const.py custom_components/smart_charging/adapters/factory.py tests/adapters/test_factory.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add ev_soc adapter role (RA1 extension)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

> **⎔ Phase 2 checkpoint:** `pytest tests/adapters -v` green; `ev_soc` resolves through the factory
> when configured, and is cleanly absent (no `KeyError`) when it isn't — unlike the always-required
> roles, this one's requiredness is conditional on the active mode (Task 5.1), not on the factory.

---

## Phase 3 — Config/options flow (C4 extension)

### Task 3.1: New config keys

**Files:** Modify `custom_components/smart_charging/const.py`

**Step 1: Append**

```python
# --- DATA addition ---
# CONF_EV_SOC_ENTITY already added in Task 2.1.
CONF_SOLAR_INSTALLED = "solar_installed"  # bool, default False -- design doc §3, R18 scoped

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
async def test_ev_soc_is_optional_when_solar_not_installed(hass):
    # Design doc §3/§8: with the Solar-installed toggle left False (its default), ev_soc
    # is optional -- an install without it still produces a valid entry.
    result = await _run_user_flow(hass, omit=[CONF_EV_SOC_ENTITY])
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert CONF_EV_SOC_ENTITY not in result["data"]
    assert result["data"][CONF_SOLAR_INSTALLED] is False


async def test_solar_installed_true_requires_ev_soc(hass):
    # Design doc §3: flipping Solar installed to True without mapping ev_soc must be
    # rejected by the flow itself (config-time guard), not deferred to a runtime fault.
    result = await _run_user_flow(
        hass, overrides={CONF_SOLAR_INSTALLED: True}, omit=[CONF_EV_SOC_ENTITY]
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"][CONF_EV_SOC_ENTITY] == "required_when_solar_installed"


async def test_solar_installed_true_with_ev_soc_succeeds(hass):
    result = await _run_user_flow(
        hass,
        overrides={CONF_SOLAR_INSTALLED: True, CONF_EV_SOC_ENTITY: "sensor.ev_soc"},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_SOLAR_INSTALLED] is True
    assert result["data"][CONF_EV_SOC_ENTITY] == "sensor.ev_soc"


async def test_pre_toggle_entry_defaults_solar_installed_false(hass):
    # An entry created before this task predates CONF_SOLAR_INSTALLED entirely --
    # reading it must default to False, not KeyError (design doc §8).
    entry = MockConfigEntry(domain=DOMAIN, data=_data(), options=_options())
    assert entry.data.get(CONF_SOLAR_INSTALLED, False) is False


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

**Step 3: Implement** — add `vol.Optional(CONF_SOLAR_INSTALLED, default=False): bool` and
`vol.Optional(CONF_EV_SOC_ENTITY): _entity("sensor")` to `MAPPING_SCHEMA`; in the flow's
`async_step_user` validation (same place the existing required-role checks live), reject the
submission with `errors[CONF_EV_SOC_ENTITY] = "required_when_solar_installed"` when
`user_input[CONF_SOLAR_INSTALLED]` is `True` and `CONF_EV_SOC_ENTITY` is missing/blank — `ev_soc`
itself stays optional at the schema level (§3/Task 2.1's reasoning: existing entries and a
solar-less installation both need a valid entry without it); the toggle is what turns that into a
hard requirement, not the schema. Add the eight new options fields (with their `DEFAULT_*`
constants) to `OPTION_KEYS` and `_threshold_schema()`; `CONF_SOLAR_ONLY_STRATEGY` uses
`vol.In(["round_up", "round_down", "round_nearest"])`.

**Step 4: Run** → PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/config_flow.py tests/test_config_flow.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: extend config/options flow with Solar-installed toggle, ev_soc + Solar/SolarOnly settings

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

> **⎔ Phase 3 checkpoint:** a full install flow produces a valid entry whether or not `ev_soc` is
> mapped, provided `Solar installed` stays `False`; flipping it `True` without `ev_soc` is rejected
> by the form itself; every new threshold + `default_soc_limit` seeds into options; the options
> flow round-trips each new field without touching data; no migration is needed for an entry that
> predates these fields (`data`/`options` reads fall back to their default).

---

## Phase 4 — Owned entities (C2 extension)

> **Forward reference, same as the Power MVP's precedent (`TargetCurrentNumber`/coordinator):**
> these entities read/write `coordinator.active_mode` and `coordinator.soc_limit_override` before
> Task 5.1 (Phase 5) actually implements that contract on the coordinator. The unit tests below
> stub it out (`_StubCoordinator`), so this ordering is safe — but keep the attribute names
> (`active_mode`, `soc_limit_override`) identical to what Task 5.1 defines.

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
    entity = ModeSelect(entry_id="abc", coordinator=coord, solar_installed=True)
    await entity.async_select_option("Solar")
    assert coord.active_mode == "Solar"
    assert coord.refreshed is True
    assert entity.current_option == "Solar"


async def test_restores_last_selection(hass):
    # Simulate a restored state of "SolarOnly" via async_get_last_state -- follow the
    # RestoreEntity pattern used by TargetCurrentNumber (number.py) for a select entity.
    ...


def test_options_are_off_power_only_when_solar_not_installed():
    # Design doc §3/§4: Solar installed defaults to False, so the selector must not
    # offer Solar/SolarOnly at all until the toggle is flipped.
    entity = ModeSelect(entry_id="abc", coordinator=_StubCoordinator(), solar_installed=False)
    assert entity.options == ["Off", "Power"]


def test_options_include_solar_modes_when_solar_installed():
    entity = ModeSelect(entry_id="abc", coordinator=_StubCoordinator(), solar_installed=True)
    assert entity.options == ["Off", "Power", "Solar", "SolarOnly"]
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

from .const import CONF_SOLAR_INSTALLED, DOMAIN
from .entity import SmartChargingEntity

BASE_MODE_OPTIONS = ["Off", "Power"]
SOLAR_MODE_OPTIONS = ["Solar", "SolarOnly"]


class ModeSelect(SmartChargingEntity, RestoreEntity, SelectEntity):
    """User-set active charging mode. Option list is gated by Solar installed (design doc §3/§4,
    R18 scoped) -- Solar/SolarOnly are only offered when that config-time toggle is True."""

    _attr_translation_key = "mode"

    def __init__(self, entry_id: str, coordinator, solar_installed: bool) -> None:
        super().__init__(entry_id)
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_mode"
        self._attr_options = (
            BASE_MODE_OPTIONS + SOLAR_MODE_OPTIONS if solar_installed else list(BASE_MODE_OPTIONS)
        )
        self._attr_current_option = "Off"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in self._attr_options:
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
    solar_installed = entry.data.get(CONF_SOLAR_INSTALLED, False)
    async_add_entities(
        [ModeSelect(entry_id=entry.entry_id, coordinator=coordinator, solar_installed=solar_installed)]
    )
```

**Step 4: Run** → PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/select.py tests/test_select.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add select.smart_charging_mode entity, gated by Solar installed (C2)

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

async def test_soc_at_or_above_limit_forces_zero_and_holds_solar_states_at_idle(hass, ...):
    """ev_soc >= soc_limit_override -> 0 A even with ample surplus, for both Solar and
    SolarOnly; the mode's threaded state is held at idle() while the gate holds (not a
    latched "soc_reached" phase -- there is no such phase, see modes/solar.py)."""

async def test_resumes_when_the_soc_limit_rises_above_current_soc(hass, ...):
    """R7 resume condition 1: with active_mode="Solar" gated at 0 A (ev_soc >= limit),
    raising soc_limit_override above the current ev_soc lets the NEXT cycle dispatch to
    solar.step() again from idle() -- charging resumes once surplus qualifies, without a
    mode switch or a disconnect."""

async def test_resumes_after_disconnect_and_reconnect_while_still_at_the_limit(hass, ...):
    """R7 resume condition 2: gated at the limit, then charger_status leaves
    connected/charging and comes back -- every mode's state resets to idle() on the
    disconnect (existing R11 reset path), so a reconnect re-arms fresh even though
    soc_limit_override never changed."""

async def test_power_and_off_ignore_soc_entirely(hass, ...):
    """With active_mode="Power" (or "Off") and no ev_soc configured at all (factory
    omits the role -- Task 2.1), the cycle runs normally -- ev_soc is read/required only
    while Solar/SolarOnly is active. Power's existing MVP behavior (charges regardless
    of SOC) is unchanged (success-criterion 6)."""

async def test_missing_ev_soc_faults_only_while_a_solar_mode_is_selected(hass, ...):
    """active_mode="Solar" with the ev_soc role unmapped (or reading None) -> fault, 0 A;
    the same missing role under active_mode="Power" does not fault."""

async def test_mode_switch_resets_the_incoming_modes_state(hass, ...):
    """Solar's Hold/Cooldown state does not leak into a fresh Solar selection after
    switching away and back (R11 mode-switch reset)."""

async def test_grid_ceiling_still_clamps_a_solar_request(hass, ...):
    """E6 (unchanged) still reduces a Solar-mode request that would breach the ceiling."""

async def test_power_mode_behavior_unchanged(hass, ...):
    """Existing Power-mode MVP tests continue to pass verbatim."""
```

**Step 2: Run** → FAIL (dispatch doesn't exist yet).

**Step 3: Implement** — sketch (full code follows the existing `_run_cycle` structure). The SOC gate
lives here, in the coordinator, **not** inside `Solar`/`SolarOnly`'s state machines (design doc §5)
— those modes have no SOC-related phase at all, so "resuming" is just the coordinator resuming its
own dispatch, which needs no special-case logic beyond holding the mode's state at `idle()` while
gated:

```python
# coordinator.py -- additions

from .engines.signal_conditioning import resolve_voltage, smooth_net_power
from .engines.soc_target import resolve_active_soc_limit
from .modes import power, solar, solar_only

_SOLAR_MODES = ("Solar", "SolarOnly")

# __init__: add self._net_window: tuple[float, ...] = (); self._mode_state = {
#   "Solar": solar.SolarState.idle(), "SolarOnly": solar_only.SolarOnlyState.idle(),
# }; self.active_mode: str = "Off"; self.soc_limit_override: float = DEFAULT_SOC_LIMIT;
# self._last_active_mode: str | None = None (to detect a switch).

# In _run_cycle, after reading status/net_w/charger_w/voltage as today:

if self.active_mode != self._last_active_mode:
    # R11: switching mode resets timers -- fresh state for both solar modes, whether or
    # not the incoming mode is one of them (simplest correct behavior: a state nobody
    # is dispatching to is inert either way).
    self._mode_state = {
        "Solar": solar.SolarState.idle(),
        "SolarOnly": solar_only.SolarOnlyState.idle(),
    }
    self._last_active_mode = self.active_mode

# ev_soc is read -- and its absence is a fault -- ONLY while a solar mode is selected
# (success-criterion 6 / S2: Power/Off must not regress to needing an SOC sensor).
ev_soc = None
if self.active_mode in _SOLAR_MODES:
    ev_soc = await self._adapters["ev_soc"].read() if "ev_soc" in self._adapters else None
    if ev_soc is None:
        self._log_fault("ev_soc required while a solar mode is active but missing/None")
        await self._write(0.0)
        return CycleResult(commanded_current=0.0, fault=True, active_mode=self.active_mode)

smoothed_net_w, self._net_window = smooth_net_power(
    net_w, self._net_window, size=self._config["smoothing_window"]
)
active_soc_limit = resolve_active_soc_limit(self.soc_limit_override)
now = self.hass.loop.time()  # injected, not read inside modes/engines

if status not in CHARGEABLE_STATES:
    desired = 0.0
    # R7/R11: disconnect resets every mode's state, clearing hold/cooldown -- and,
    # for a solar mode, also ends any SOC gate (resume condition 2: unplug/replug).
    self._mode_state = {
        "Solar": solar.SolarState.idle(),
        "SolarOnly": solar_only.SolarOnlyState.idle(),
    }
elif self.active_mode == "Off":
    desired = 0.0
elif self.active_mode == "Power":
    desired = power.desired_current(self.target_current, status)  # unchanged -- no SOC gate
elif self.active_mode in _SOLAR_MODES and ev_soc >= active_soc_limit:
    # R7: don't resume until the gate clears. Holding the state at idle() (rather than
    # dispatching into step()) means the NEXT cycle where this branch stops matching --
    # because soc_limit_override rose (resume condition 1) -- dispatches fresh from
    # idle(), re-checking the start threshold normally. No latch, no separate phase.
    desired = 0.0
    self._mode_state[self.active_mode] = (
        solar.SolarState.idle() if self.active_mode == "Solar" else solar_only.SolarOnlyState.idle()
    )
elif self.active_mode == "Solar":
    surplus_w = charger_w - smoothed_net_w
    desired, self._mode_state["Solar"] = solar.step(
        surplus_w, self._mode_state["Solar"], now,
        start_threshold_w=self._config["solar_start_threshold_w"],
        min_a=self._config["min_current"],
        hold_minutes=self._config["solar_hold_min"],
        cooldown_minutes=self._config["solar_cooldown_min"], voltage=voltage,
    )
elif self.active_mode == "SolarOnly":
    surplus_w = charger_w - smoothed_net_w
    desired, self._mode_state["SolarOnly"] = solar_only.step(
        surplus_w, self._mode_state["SolarOnly"], now,
        start_threshold_w=self._config["solar_only_start_threshold_w"],
        min_a=self._config["min_current"],
        cooldown_minutes=self._config["solar_cooldown_min"],
        strategy=self._config["solar_only_strategy"],
        midpoint=self._config["solar_only_midpoint"], voltage=voltage,
    )

# ... unchanged from here: clamp_to_ceiling (E6), apply_floor_cap (E8), write, return.
# CycleResult gains an `active_mode: str` field so sensor.py's ActiveModeSensor can read it.
```

Note the disconnect branch's mode-state reset is written twice above (the explicit mode-switch check,
and the disconnect branch) — that duplication is intentional and small enough to leave inline rather
than extracting a helper for two call sites; if a third reset path appears later, factor it out then.

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
