"""Plain-pytest tests for the Solar mode engine (E1 -- UC01)."""

import pytest

from custom_components.smart_charging.modes._phase import Phase
from custom_components.smart_charging.modes.solar import SolarState, step

DEFAULTS = dict(
    start_threshold_w=150.0,
    min_a=6.0,
    hold_minutes=5.0,
    cooldown_minutes=2.0,
    debounce_minutes=1.0,
)


def test_idle_stays_idle_below_start_threshold():
    desired, state = step(surplus_w=100.0, state=SolarState.idle(), now=0.0, **DEFAULTS)
    assert desired == 0.0
    assert state.phase == Phase.IDLE


def test_starts_charging_at_start_threshold_rounding_up():
    # 150 W @ 230 V = 0.652 A -> rounds UP (fixed) to 1 A, then floored to min_a=6.0
    # by this engine's own grid-fallback rule (R1's set-point rule, not E8's separate
    # upper-bound clamp -- see _charging_setpoint).
    desired, state = step(surplus_w=150.0, state=SolarState.idle(), now=0.0, **DEFAULTS)
    assert state.phase == Phase.CHARGING
    assert desired == 6.0


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
    # 2300 W @ 230 V = 10.0 A ideal, comfortably above min_a=6.0 -> the grid-fallback
    # floor doesn't mask the round-up arithmetic here, unlike the threshold test above.
    assert desired1 == desired2 == 10.0


def test_grid_fallback_below_minimum_current():
    # Surplus at/above start threshold but below the minimum-current equivalent power
    # -> hold at minimum, drawing the shortfall from the grid (3a).
    state = SolarState.idle()
    _, state = step(surplus_w=200.0, state=state, now=0.0, **DEFAULTS)
    desired, state = step(surplus_w=200.0, state=state, now=10.0, **DEFAULTS)
    assert desired == DEFAULTS["min_a"]
    assert state.phase == Phase.CHARGING  # grid fallback is a set-point condition, not a state


def test_post_surplus_hold_then_resume_within_period():
    state = SolarState.idle()
    _, state = step(surplus_w=2300.0, state=state, now=0.0, **DEFAULTS)  # -> charging
    _, state = step(surplus_w=50.0, state=state, now=10.0, **DEFAULTS)  # -> hold
    assert state.phase == Phase.HOLD
    desired, state = step(surplus_w=2300.0, state=state, now=60.0, **DEFAULTS)  # within 5 min
    assert state.phase == Phase.CHARGING
    assert desired > 0.0


def test_post_surplus_hold_elapses_into_cooldown_then_idle():
    state = SolarState.idle()
    _, state = step(surplus_w=2300.0, state=state, now=0.0, **DEFAULTS)  # -> charging
    _, state = step(surplus_w=50.0, state=state, now=10.0, **DEFAULTS)  # -> hold @ t=10
    desired, state = step(surplus_w=50.0, state=state, now=10.0 + 5 * 60, **DEFAULTS)
    assert desired == 0.0
    assert state.phase == Phase.COOLDOWN


def test_cooldown_blocks_restart_until_elapsed():
    state = SolarState.idle()
    _, state = step(surplus_w=2300.0, state=state, now=0.0, **DEFAULTS)
    _, state = step(surplus_w=50.0, state=state, now=10.0, **DEFAULTS)  # -> hold
    _, state = step(surplus_w=50.0, state=state, now=10.0 + 5 * 60, **DEFAULTS)  # -> cooldown
    cooldown_start = 10.0 + 5 * 60
    desired, state = step(surplus_w=2300.0, state=state, now=cooldown_start + 30, **DEFAULTS)
    assert desired == 0.0
    assert state.phase == Phase.COOLDOWN  # still within the 2 min cooldown
    desired, state = step(
        surplus_w=2300.0, state=state, now=cooldown_start + 2 * 60 + 1, **DEFAULTS
    )
    assert state.phase == Phase.CHARGING


def test_cooldown_elapses_into_idle_without_qualifying_surplus():
    state = SolarState.idle()
    _, state = step(surplus_w=2300.0, state=state, now=0.0, **DEFAULTS)  # -> charging
    _, state = step(surplus_w=50.0, state=state, now=10.0, **DEFAULTS)  # -> hold
    _, state = step(surplus_w=50.0, state=state, now=10.0 + 5 * 60, **DEFAULTS)  # -> cooldown
    cooldown_start = 10.0 + 5 * 60
    desired, state = step(surplus_w=50.0, state=state, now=cooldown_start + 2 * 60 + 1, **DEFAULTS)
    assert desired == 0.0
    assert state.phase == Phase.IDLE


def test_non_default_voltage_changes_ideal_current():
    # 3220 W @ 460 V = 7.0 A ideal, above min_a=6.0 -> the grid-fallback floor
    # doesn't mask the voltage division.
    desired, state = step(
        surplus_w=3220.0, state=SolarState.idle(), now=0.0, voltage=460.0, **DEFAULTS
    )
    assert desired == 7.0


def test_unknown_phase_raises_value_error():
    with pytest.raises(ValueError, match="unknown SolarState.phase"):
        step(surplus_w=0.0, state=SolarState("bogus"), now=0.0, **DEFAULTS)


# --- has-charged flag / restart debounce (R11, issue #757) ---


def test_connections_first_start_is_immediate_no_debounce():
    # Before the has-charged flag is ever set, Idle starts charging as soon as the
    # threshold is met, with no debounce (system-overview.md's `restart debounce` entry).
    desired, state = step(
        surplus_w=2300.0, state=SolarState.idle(), now=0.0, has_charged=False, **DEFAULTS
    )
    assert state.phase == Phase.CHARGING
    assert desired > 0.0


def test_later_idle_crossing_debounces_once_has_charged_is_set():
    # UC01 2b: once has_charged is True, a threshold crossing while dwelling in Idle must
    # hold for the restart debounce period before charging actually starts.
    state = SolarState.idle()
    desired, state = step(surplus_w=2300.0, state=state, now=0.0, has_charged=True, **DEFAULTS)
    assert state.phase == Phase.DEBOUNCING
    assert desired == 0.0
    # Still below the debounce period (1 min) -- stays Debouncing.
    desired, state = step(surplus_w=2300.0, state=state, now=30.0, has_charged=True, **DEFAULTS)
    assert state.phase == Phase.DEBOUNCING
    assert desired == 0.0
    # Debounce period elapsed with surplus still at/above threshold -> Charging.
    desired, state = step(surplus_w=2300.0, state=state, now=60.0, has_charged=True, **DEFAULTS)
    assert state.phase == Phase.CHARGING
    assert desired > 0.0


def test_debounce_resets_to_idle_on_drop_below_threshold():
    # UC01 2b: a blip below the threshold before the debounce elapses discards the timer --
    # the System remains Idle, not Debouncing, and a fresh crossing starts a fresh timer.
    state = SolarState.idle()
    _, state = step(surplus_w=2300.0, state=state, now=0.0, has_charged=True, **DEFAULTS)
    assert state.phase == Phase.DEBOUNCING
    desired, state = step(surplus_w=50.0, state=state, now=10.0, has_charged=True, **DEFAULTS)
    assert desired == 0.0
    assert state.phase == Phase.IDLE


def test_cooldown_elapsed_resume_at_threshold_is_immediate_even_when_has_charged():
    # UC01 2b's exemption: a resume straight from Cooldown, with the threshold already met
    # the moment cooldown elapses, never passes through Idle -- so no debounce applies,
    # regardless of has_charged.
    state = SolarState.idle()
    _, state = step(
        surplus_w=2300.0, state=state, now=0.0, has_charged=False, **DEFAULTS
    )  # charging
    _, state = step(surplus_w=50.0, state=state, now=10.0, has_charged=True, **DEFAULTS)  # hold
    cooldown_enter = 10.0 + 5 * 60
    _, state = step(surplus_w=50.0, state=state, now=cooldown_enter, has_charged=True, **DEFAULTS)
    assert state.phase == Phase.COOLDOWN
    cooldown_elapsed = cooldown_enter + 2 * 60 + 1
    desired, state = step(
        surplus_w=2300.0, state=state, now=cooldown_elapsed, has_charged=True, **DEFAULTS
    )
    assert state.phase == Phase.CHARGING
    assert desired > 0.0
