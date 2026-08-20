"""Plain-pytest tests for the SolarOnly mode engine (E1 -- UC02)."""

import pytest

from custom_components.smart_charging.const import ROUND_DOWN, ROUND_NEAREST, ROUND_UP
from custom_components.smart_charging.modes._phase import Phase
from custom_components.smart_charging.modes.solar_only import SolarOnlyState, step

DEFAULTS = dict(
    start_threshold_w=1300.0,
    min_a=6.0,
    hold_minutes=1.0,
    cooldown_minutes=2.0,
    strategy=ROUND_DOWN,
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
#
# `min_a` is *not* one of this module's own parameters (issue #501): unlike `Solar`,
# `SolarOnly` has no grid fallback (UC02 3a/step()'s own docstring) so it never floors
# a below-minimum ideal current up to the minimum itself -- E8 (the coordinator's
# `apply_floor_cap`, downstream) is the only place that touches the minimum for this
# mode, and it floors down to 0 A, not up.
# MINIMUM_CURRENT_A mirrors E8's configured min_a; this module never sees it -- it exists
# only so the test below can spell out *why* 5.0 A (not 6.0 A) is below the minimum.
MINIMUM_CURRENT_A = 6.0


def test_at_exactly_the_default_threshold_ideal_current_is_below_minimum():
    # Documents the 1300 W vs 1380 W boundary gap above rather than hiding it.
    desired, state = step(surplus_w=1300.0, state=SolarOnlyState.idle(), now=0.0, **DEFAULTS)
    assert state.phase == Phase.CHARGING
    # 1300 W / 230 V = 5.652 A ideal -> round_down = 5.0 A, below MINIMUM_CURRENT_A.
    assert desired == 5.0
    assert desired < MINIMUM_CURRENT_A  # E8 (coordinator, unchanged) floors this to 0 A


def test_idle_below_threshold():
    desired, state = step(surplus_w=500.0, state=SolarOnlyState.idle(), now=0.0, **DEFAULTS)
    assert desired == 0.0 and state.phase == Phase.IDLE


def test_starts_at_threshold_default_round_down_never_imports():
    desired, state = step(surplus_w=1380.0, state=SolarOnlyState.idle(), now=0.0, **DEFAULTS)
    # 1380 W / 230 V = 6.0 A ideal -> round_down = 6 A (no grid import).
    assert state.phase == Phase.CHARGING
    assert desired == 6.0


def test_surplus_drop_enters_hold_not_immediate_stop():
    # R2/UC02 3a (post-#749): SolarOnly no longer stops immediately -- it holds at min_a
    # first, drawing any shortfall from the grid for the bounded hold period.
    state = SolarOnlyState.idle()
    _, state = step(surplus_w=1400.0, state=state, now=0.0, **DEFAULTS)  # -> charging
    desired, state = step(surplus_w=500.0, state=state, now=10.0, **DEFAULTS)
    assert state.phase == Phase.HOLD
    assert desired == DEFAULTS["min_a"]  # flat min_a -- no grid fallback, unlike Solar's hold


def test_hold_set_point_is_flat_min_a_not_recomputed_ideal():
    # The one behavioral difference from Solar's Hold (issue #755): SolarOnly has no
    # ongoing grid fallback, so its hold set-point never recomputes an ideal current --
    # it's always the flat minimum, regardless of how much surplus remains during hold.
    state = SolarOnlyState.idle()
    _, state = step(surplus_w=1400.0, state=state, now=0.0, **DEFAULTS)  # -> charging
    _, state = step(surplus_w=800.0, state=state, now=10.0, **DEFAULTS)  # -> hold, surplus > 0
    assert state.phase == Phase.HOLD
    desired, state = step(surplus_w=800.0, state=state, now=20.0, **DEFAULTS)
    assert desired == DEFAULTS["min_a"]  # not round_down(800/230)=3.0 -- flat min_a while holding
    assert state.phase == Phase.HOLD


def test_hold_then_resume_within_period():
    state = SolarOnlyState.idle()
    _, state = step(surplus_w=1400.0, state=state, now=0.0, **DEFAULTS)  # -> charging
    _, state = step(surplus_w=500.0, state=state, now=10.0, **DEFAULTS)  # -> hold
    assert state.phase == Phase.HOLD
    desired, state = step(surplus_w=1400.0, state=state, now=30.0, **DEFAULTS)  # within 1 min
    assert state.phase == Phase.CHARGING
    assert desired > 0.0


def test_hold_elapses_into_cooldown_then_idle():
    state = SolarOnlyState.idle()
    _, state = step(surplus_w=1400.0, state=state, now=0.0, **DEFAULTS)  # -> charging
    _, state = step(surplus_w=500.0, state=state, now=10.0, **DEFAULTS)  # -> hold @ t=10
    desired, state = step(surplus_w=500.0, state=state, now=10.0 + 60, **DEFAULTS)
    assert desired == 0.0
    assert state.phase == Phase.COOLDOWN


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
    _, state = step(surplus_w=1400.0, state=state, now=0.0, **DEFAULTS)  # -> charging
    _, state = step(surplus_w=500.0, state=state, now=10.0, **DEFAULTS)  # -> hold @ t=10
    _, state = step(surplus_w=500.0, state=state, now=10.0 + 60, **DEFAULTS)  # hold elapses
    cooldown_start = 10.0 + 60
    desired, state = step(surplus_w=1400.0, state=state, now=cooldown_start + 30, **DEFAULTS)
    assert desired == 0.0
    assert state.phase == Phase.COOLDOWN  # still within the 2 min cooldown
    desired, state = step(
        surplus_w=1400.0, state=state, now=cooldown_start + 2 * 60 + 1, **DEFAULTS
    )
    assert state.phase == Phase.CHARGING


def test_cooldown_elapses_into_idle_without_qualifying_surplus():
    # UC02's state table (Cooldown row): cooldown elapsed & surplus < start threshold -> Idle.
    state = SolarOnlyState.idle()
    _, state = step(surplus_w=1400.0, state=state, now=0.0, **DEFAULTS)  # -> charging
    _, state = step(surplus_w=500.0, state=state, now=10.0, **DEFAULTS)  # -> hold @ t=10
    _, state = step(surplus_w=500.0, state=state, now=10.0 + 60, **DEFAULTS)  # hold elapses
    cooldown_start = 10.0 + 60
    desired, state = step(surplus_w=500.0, state=state, now=cooldown_start + 2 * 60 + 1, **DEFAULTS)
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
