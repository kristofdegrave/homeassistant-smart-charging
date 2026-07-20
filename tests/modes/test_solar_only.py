"""Plain-pytest tests for the SolarOnly mode engine (E1 -- UC02)."""

import pytest

from custom_components.smart_charging.modes._amp_step import ROUND_NEAREST, ROUND_UP
from custom_components.smart_charging.modes._phase import Phase
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
    assert state.phase == Phase.CHARGING
    assert desired < DEFAULTS["min_a"]  # E8 (coordinator, unchanged) floors this to 0 A


def test_idle_below_threshold():
    desired, state = step(surplus_w=500.0, state=SolarOnlyState.idle(), now=0.0, **DEFAULTS)
    assert desired == 0.0 and state.phase == Phase.IDLE


def test_starts_at_threshold_default_round_down_never_imports():
    desired, state = step(surplus_w=1380.0, state=SolarOnlyState.idle(), now=0.0, **DEFAULTS)
    # 1380 W / 230 V = 6.0 A ideal -> round_down = 6 A (no grid import).
    assert state.phase == Phase.CHARGING
    assert desired == 6.0


def test_immediate_stop_no_hold_no_grid_fallback():
    state = SolarOnlyState.idle()
    _, state = step(surplus_w=1400.0, state=state, now=0.0, **DEFAULTS)
    desired, state = step(surplus_w=500.0, state=state, now=10.0, **DEFAULTS)
    assert desired == 0.0
    assert state.phase == Phase.COOLDOWN  # not "hold" -- SolarOnly has no hold phase


def test_round_up_strategy_configured():
    desired, state = step(
        surplus_w=1450.0,  # 6.3 A ideal
        state=SolarOnlyState.idle(),
        now=0.0,
        **{**DEFAULTS, "strategy": ROUND_UP},
    )
    assert desired == 7.0


def test_round_nearest_strategy_threaded_through():
    # 6.55 A ideal @ configured midpoint 0.5 -> rounds up to 7 A (UC02 3c, "pendel" case).
    desired, state = step(
        surplus_w=1506.5,
        state=SolarOnlyState.idle(),
        now=0.0,
        **{**DEFAULTS, "strategy": ROUND_NEAREST},
    )
    assert desired == 7.0
    assert state.phase == Phase.CHARGING


def test_cooldown_blocks_restart_until_elapsed():
    state = SolarOnlyState.idle()
    _, state = step(surplus_w=1400.0, state=state, now=0.0, **DEFAULTS)
    _, state = step(surplus_w=500.0, state=state, now=10.0, **DEFAULTS)  # -> cooldown @ t=10
    desired, state = step(surplus_w=1400.0, state=state, now=10.0 + 60, **DEFAULTS)
    assert desired == 0.0 and state.phase == Phase.COOLDOWN
    desired, state = step(surplus_w=1400.0, state=state, now=10.0 + 2 * 60 + 1, **DEFAULTS)
    assert state.phase == Phase.CHARGING


def test_cooldown_elapses_into_idle_without_qualifying_surplus():
    # UC02's state table (Cooldown row): cooldown elapsed & surplus < start threshold -> Idle.
    state = SolarOnlyState.idle()
    _, state = step(surplus_w=1400.0, state=state, now=0.0, **DEFAULTS)  # -> charging
    _, state = step(surplus_w=500.0, state=state, now=10.0, **DEFAULTS)  # -> cooldown @ t=10
    desired, state = step(surplus_w=500.0, state=state, now=10.0 + 2 * 60 + 1, **DEFAULTS)
    assert desired == 0.0
    assert state.phase == Phase.IDLE


def test_non_default_voltage_changes_ideal_current():
    desired, state = step(
        surplus_w=1380.0, state=SolarOnlyState.idle(), now=0.0, **{**DEFAULTS, "voltage": 240.0}
    )
    # 1380 W / 240 V = 5.75 A ideal -> round_down = 5 A.
    assert desired == 5.0
    assert state.phase == Phase.CHARGING


def test_unknown_phase_raises_value_error():
    bad_state = SolarOnlyState(phase="bogus")
    with pytest.raises(ValueError, match="unknown SolarOnlyState.phase"):
        step(surplus_w=1400.0, state=bad_state, now=0.0, **DEFAULTS)
