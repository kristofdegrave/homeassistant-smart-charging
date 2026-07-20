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
    desired, state = step(surplus_w=2300.0, state=state, now=cooldown_start + 30, **DEFAULTS)
    assert desired == 0.0
    assert state.phase == "cooldown"  # still within the 2 min cooldown
    desired, state = step(
        surplus_w=2300.0, state=state, now=cooldown_start + 2 * 60 + 1, **DEFAULTS
    )
    assert state.phase == "charging"
