"""Plain-pytest tests for the Cycle-Invariant engine (E8, floor/cap slice)."""

from custom_components.smart_charging.engines.cycle_invariant import apply_floor_cap


def test_in_range_passes_through():
    assert apply_floor_cap(10.0, min_a=6.0, max_a=16.0) == 10.0


def test_above_cap_clamps_to_max():
    assert apply_floor_cap(20.0, min_a=6.0, max_a=16.0) == 16.0


def test_below_min_becomes_zero_not_min():
    # C1: never command between 0 and the charger minimum -> stop instead.
    assert apply_floor_cap(4.0, min_a=6.0, max_a=16.0) == 0.0


def test_at_min_passes_through():
    assert apply_floor_cap(6.0, min_a=6.0, max_a=16.0) == 6.0


def test_at_max_passes_through():
    assert apply_floor_cap(16.0, min_a=6.0, max_a=16.0) == 16.0


def test_negative_becomes_zero():
    assert apply_floor_cap(-5.0, min_a=6.0, max_a=16.0) == 0.0


def test_zero_stays_zero():
    assert apply_floor_cap(0.0, min_a=6.0, max_a=16.0) == 0.0
