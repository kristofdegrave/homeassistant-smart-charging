"""Plain-pytest tests for the Peak-Demand Tracker (E5, part 2/2).

Takes an ALREADY-SMOOTHED (15-minute-average) kW reading -- smoothing itself is
the coordinator's job (it calls E7's smooth_net_power with its own window; see
Task 5.1), not this module's, since an engine may not import another engine."""

from custom_components.smart_charging.engines.peak_demand_tracker import (
    update_monthly_peak_demand,
)


def test_bootstraps_from_the_first_reading_not_zero():
    kw, month = update_monthly_peak_demand(
        smoothed_kw=1.5,
        current_month=(2026, 7),
        tracked_kw=0.0,
        tracked_month=None,
    )
    assert kw == 1.5  # first sample IS the peak so far -- no artificial 0 floor
    assert month == (2026, 7)


def test_tracks_the_running_maximum_within_a_month():
    kw, month = update_monthly_peak_demand(
        smoothed_kw=1.0,
        current_month=(2026, 7),
        tracked_kw=0.0,
        tracked_month=None,
    )
    assert kw == 1.0
    kw, month = update_monthly_peak_demand(
        smoothed_kw=0.5,
        current_month=(2026, 7),
        tracked_kw=kw,
        tracked_month=month,
    )
    assert kw == 1.0  # a lower reading does not lower the tracked peak


def test_resets_on_a_month_change_to_the_new_months_own_reading():
    kw, month = update_monthly_peak_demand(
        smoothed_kw=0.8,
        current_month=(2026, 8),
        tracked_kw=3.5,
        tracked_month=(2026, 7),
    )
    assert kw == 0.8  # NOT 0 kW and NOT the carried-over 3.5 kW
    assert month == (2026, 8)
