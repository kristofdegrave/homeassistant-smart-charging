"""Plain-pytest tests for the shared amp-step rounding helper."""

import pytest

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


def test_whole_number_ideal_is_unchanged_by_every_strategy():
    assert round_amp_step(10.0, strategy="round_up") == 10.0
    assert round_amp_step(10.0, strategy="round_down") == 10.0
    assert round_amp_step(10.0, strategy="round_nearest", midpoint=0.5) == 10.0


def test_unknown_strategy_raises():
    with pytest.raises(ValueError):
        round_amp_step(10.4, strategy="bogus")
