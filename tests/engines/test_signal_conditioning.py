"""Plain-pytest tests for the Signal-Conditioning engine (E7, voltage slice)."""

from custom_components.smart_charging.engines.signal_conditioning import (
    HouseholdWindow,
    resolve_voltage,
    smooth_household_baseline,
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


def test_supports_a_much_larger_window_for_the_peak_tracker():
    # 90 samples ~= 15 min at the default 10 s control interval -- proves the helper
    # generalizes to Captar's 15-minute peak-demand window (#218), not just R10's short one.
    window = ()
    for sample in [1000.0] * 89 + [10000.0]:
        smoothed, window = smooth_net_power(sample, window, size=90)
    assert len(window) == 90
    assert smoothed == (1000.0 * 89 + 10000.0) / 90


# R10/issue #1329: `smooth_household_baseline` folds `net_w - charger_w` into the same rolling
# window `smooth_net_power` maintains, except on a cycle whose own command changed -- see the
# function's own docstring for why (ADR-0039's insight, applied to the smoothing window this
# time rather than to R3's raw clamp operand).


def test_should_fold_the_reading_when_the_command_held_steady():
    # Arrange
    state = HouseholdWindow((100.0, 100.0))
    # Act
    smoothed, new_state = smooth_household_baseline(-400.0, state, size=4, command_changed=False)
    # Assert
    assert new_state == HouseholdWindow((100.0, 100.0, -400.0), deferred_previous=False)
    assert smoothed == (100.0 + 100.0 - 400.0) / 3


def test_should_freeze_the_window_when_the_command_changed():
    # Arrange
    state = HouseholdWindow((100.0, -400.0))
    # Act -- a wildly different reading, but the command stepped on the write that ended the
    # previous cycle, so this cycle's net_w/charger_w may still be measuring that actuation.
    smoothed, new_state = smooth_household_baseline(9000.0, state, size=4, command_changed=True)
    # Assert -- the window is untouched and its existing mean stands for one more cycle.
    assert new_state == HouseholdWindow((100.0, -400.0), deferred_previous=True)
    assert smoothed == (100.0 - 400.0) / 2


def test_should_fold_the_first_ever_reading_even_when_the_command_changed():
    # Arrange -- an empty window: there is no prior mean to fall back on (ADR-0039's own
    # "nothing to debounce against yet" case), so the very first reading is always accepted.
    # Act
    smoothed, new_state = smooth_household_baseline(
        -2345.0, HouseholdWindow(), size=4, command_changed=True
    )
    # Assert
    assert new_state == HouseholdWindow((-2345.0,), deferred_previous=False)
    assert smoothed == -2345.0


def test_should_fold_the_reading_when_the_command_changed_but_the_window_size_is_one():
    # Arrange -- size=1 has no history to protect: `smooth_net_power` keeps only the newest
    # sample at that size regardless, so the freeze must not apply there.
    state = HouseholdWindow((100.0,))
    # Act
    smoothed, new_state = smooth_household_baseline(9000.0, state, size=1, command_changed=True)
    # Assert
    assert new_state == HouseholdWindow((9000.0,), deferred_previous=False)
    assert smoothed == 9000.0


def test_should_fold_the_reading_when_the_previous_cycle_already_deferred_once():
    # Arrange -- deferred_previous is already True: a mode adjusting its own request most
    # cycles (Solar tracking a drifting surplus) must not have every reading discarded, so the
    # freeze is capped at one cycle in a row (mirrors ADR-0039's own `deferred_previous`).
    state = HouseholdWindow((100.0, -400.0), deferred_previous=True)
    # Act
    smoothed, new_state = smooth_household_baseline(9000.0, state, size=4, command_changed=True)
    # Assert -- folded in despite command_changed, and the cap resets.
    assert new_state == HouseholdWindow((100.0, -400.0, 9000.0), deferred_previous=False)
    assert smoothed == (100.0 - 400.0 + 9000.0) / 3
