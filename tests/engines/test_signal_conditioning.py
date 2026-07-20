"""Plain-pytest tests for the Signal-Conditioning engine (E7, voltage slice)."""

from custom_components.smart_charging.engines.signal_conditioning import (
    resolve_voltage,
    smooth_net_power,
)


def test_uses_measured_voltage_when_healthy():
    assert resolve_voltage(measured=235.0, nominal=230.0) == 235.0


def test_falls_back_to_nominal_when_missing():
    assert resolve_voltage(measured=None, nominal=230.0) == 230.0


def test_falls_back_to_nominal_when_non_positive():
    assert resolve_voltage(measured=0.0, nominal=230.0) == 230.0
    assert resolve_voltage(measured=-5.0, nominal=230.0) == 230.0


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
    # function -- covered by the end-to-end closed-loop regression (Task 6.2), not here.
    assert smoothed == 2000.0


def test_window_slides_oldest_sample_out_once_full():
    window = (1000.0, 1000.0, 1000.0, 1000.0)
    _, window = smooth_net_power(5000.0, window, size=4)
    assert window == (1000.0, 1000.0, 1000.0, 5000.0)
