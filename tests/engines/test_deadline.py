"""Plain-pytest tests for the Deadline Engine (E4): departure-deadline resolution
(R14) and required-current/urgency computation (R5/R15).

Deviation from the plan's literal worked-example constants (see
docs/plans/2026-07-21-deadline-soc-management-design.md §6): the design doc's own prose is
explicit that `resolve_required_current` combines `deadline` with `now`'s own calendar date
(no next-day rollover) -- "a same-day deadline in the past ... saturates". Under that
contract, the plan's literal `NOW = datetime(2026, 7, 21, 22, 0)` / `DEADLINE = time(6, 0)`
pairing (commented "next-day 06:00 -- 8 hours remaining") cannot produce a positive
8-hour remaining window: combined with `now`'s date, 06:00 the same day is *before* 22:00,
i.e. already passed, which is indistinguishable from the plan's own
"already passed" test using `deadline=time(21, 0)` against the same `now`. Both tests
cannot pass together under one same-day, no-rollover rule -- a plan inconsistency, not a
bug in this test file. Resolved here (per project convention: implement the truthful,
task-scoped contract and record the deviation) by keeping `NOW = 22:00` for the two tests
that depend on same-day evening semantics (`test_unreachable_...`,
`test_deadline_already_passed_...`) and using a same-day morning/afternoon pair
(`FORMULA_NOW` / `FORMULA_DEADLINE`, still 8 hours apart) for the worked-example/
normal/urgent group, so every test stays within one same-day, no-rollover semantics while
preserving the plan's exact energy/current arithmetic (75 kWh * 30% / 8h / 230V = 12.228 A).
"""

from datetime import datetime, time

import pytest

from custom_components.smart_charging.engines.deadline import (
    resolve_departure_deadline,
    resolve_required_current,
)

MON_DEFAULT = time(6, 0)

NOW = datetime(2026, 7, 21, 22, 0)  # 22:00

# Same-day, 8 hours apart -- avoids the cross-midnight ambiguity noted above while
# reproducing the plan's exact worked-example numbers.
FORMULA_NOW = datetime(2026, 7, 21, 6, 0)  # 06:00
FORMULA_DEADLINE = time(14, 0)  # 14:00 -- 8 hours remaining


def test_external_sensor_wins_over_everything():
    assert resolve_departure_deadline(
        external_configured=True,
        external=time(7, 30),
        is_holiday=True,
        holiday_override=time(9, 0),
        home_day_flag=True,
        home_day_override=time(10, 0),
        day_of_week_default=MON_DEFAULT,
    ) == time(7, 30)


def test_external_sensor_configured_and_currently_no_deadline_still_wins():
    # R14: the external sensor takes precedence over all configured values, including
    # when it currently reads "no deadline" -- row 2 (holiday) must NOT be consulted.
    assert (
        resolve_departure_deadline(
            external_configured=True,
            external=None,
            is_holiday=True,
            holiday_override=time(9, 0),
            home_day_flag=True,
            home_day_override=time(10, 0),
            day_of_week_default=MON_DEFAULT,
        )
        is None
    )


def test_external_sensor_not_configured_falls_through_to_holiday():
    assert resolve_departure_deadline(
        external_configured=False,
        external=None,
        is_holiday=True,
        holiday_override=time(9, 0),
        home_day_flag=True,
        home_day_override=time(10, 0),
        day_of_week_default=MON_DEFAULT,
    ) == time(9, 0)


def test_holiday_wins_over_home_day_when_both_apply():
    assert resolve_departure_deadline(
        external_configured=False,
        external=None,
        is_holiday=True,
        holiday_override=time(9, 0),
        home_day_flag=True,
        home_day_override=time(10, 0),
        day_of_week_default=MON_DEFAULT,
    ) == time(9, 0)


def test_home_day_wins_when_not_a_holiday():
    assert resolve_departure_deadline(
        external_configured=False,
        external=None,
        is_holiday=False,
        holiday_override=time(9, 0),
        home_day_flag=True,
        home_day_override=time(10, 0),
        day_of_week_default=MON_DEFAULT,
    ) == time(10, 0)


def test_falls_through_to_day_of_week_default():
    assert (
        resolve_departure_deadline(
            external_configured=False,
            external=None,
            is_holiday=False,
            holiday_override=None,
            home_day_flag=False,
            home_day_override=None,
            day_of_week_default=MON_DEFAULT,
        )
        == MON_DEFAULT
    )


def test_day_of_week_default_may_be_no_deadline():
    # Weekend default (requirements.md R14: "no deadline Sat-Sun").
    assert (
        resolve_departure_deadline(
            external_configured=False,
            external=None,
            is_holiday=False,
            holiday_override=None,
            home_day_flag=False,
            home_day_override=None,
            day_of_week_default=None,
        )
        is None
    )


def test_holiday_override_itself_may_resolve_to_no_deadline():
    assert (
        resolve_departure_deadline(
            external_configured=False,
            external=None,
            is_holiday=True,
            holiday_override=None,
            home_day_flag=False,
            home_day_override=None,
            day_of_week_default=MON_DEFAULT,
        )
        is None
    )


def test_home_day_override_itself_may_resolve_to_no_deadline():
    assert (
        resolve_departure_deadline(
            external_configured=False,
            external=None,
            is_holiday=False,
            holiday_override=None,
            home_day_flag=True,
            home_day_override=None,
            day_of_week_default=MON_DEFAULT,
        )
        is None
    )


def test_no_deadline_never_urgent():
    result = resolve_required_current(
        deadline=None,
        now=NOW,
        soc=50.0,
        active_soc_limit=80.0,
        ev_battery_capacity_kwh=75.0,
        voltage=230.0,
        baseline_desired_a=6.0,
        maximum_permitted_rate_a=32.0,
    )
    assert result.required_a is None
    assert result.urgent is False
    assert result.unreachable is False


def test_required_current_formula_worked_example():
    # energy = 75 kWh * (80-50)/100 = 22.5 kWh over 8h -> 2812.5 W -> /230V = 12.228... A
    result = resolve_required_current(
        deadline=FORMULA_DEADLINE,
        now=FORMULA_NOW,
        soc=50.0,
        active_soc_limit=80.0,
        ev_battery_capacity_kwh=75.0,
        voltage=230.0,
        baseline_desired_a=6.0,
        maximum_permitted_rate_a=32.0,
    )
    assert result.required_a == pytest.approx(12.228, abs=0.01)


def test_normal_when_required_at_or_below_baseline():
    result = resolve_required_current(
        deadline=FORMULA_DEADLINE,
        now=FORMULA_NOW,
        soc=79.0,
        active_soc_limit=80.0,
        ev_battery_capacity_kwh=75.0,
        voltage=230.0,
        baseline_desired_a=6.0,
        maximum_permitted_rate_a=32.0,
    )
    assert result.urgent is False
    assert result.unreachable is False


def test_urgent_when_required_between_baseline_and_max_rate():
    result = resolve_required_current(
        deadline=FORMULA_DEADLINE,
        now=FORMULA_NOW,
        soc=50.0,
        active_soc_limit=80.0,
        ev_battery_capacity_kwh=75.0,
        voltage=230.0,
        baseline_desired_a=6.0,
        maximum_permitted_rate_a=32.0,
    )
    assert result.urgent is True
    assert result.unreachable is False


def test_unreachable_when_required_exceeds_max_rate():
    result = resolve_required_current(
        deadline=time(22, 5),
        now=NOW,
        soc=10.0,
        active_soc_limit=80.0,
        ev_battery_capacity_kwh=75.0,
        voltage=230.0,
        baseline_desired_a=6.0,
        maximum_permitted_rate_a=32.0,
    )
    assert result.unreachable is True


def test_deadline_already_passed_saturates_instead_of_dividing_by_zero():
    result = resolve_required_current(
        deadline=time(21, 0),
        now=NOW,
        soc=50.0,
        active_soc_limit=80.0,
        ev_battery_capacity_kwh=75.0,
        voltage=230.0,
        baseline_desired_a=6.0,
        maximum_permitted_rate_a=32.0,
    )
    assert result.unreachable is True  # deadline in the past -> max urgency, not an exception
    assert result.urgent is True  # Unreachable is a subset of Urgent (resolution-rules.md)


def test_no_urgency_when_soc_already_at_or_above_limit_even_if_deadline_passed():
    # Reviewer finding (PR #350): a passed deadline must not report urgency/unreachability
    # when there's nothing left to charge -- the caller (Auto row 1: SOC >= limit -> Off)
    # happens to gate on this first, but the signal itself should be correct on its own.
    result = resolve_required_current(
        deadline=time(21, 0),
        now=NOW,
        soc=80.0,
        active_soc_limit=80.0,
        ev_battery_capacity_kwh=75.0,
        voltage=230.0,
        baseline_desired_a=6.0,
        maximum_permitted_rate_a=32.0,
    )
    assert result.required_a == 0.0
    assert result.urgent is False
    assert result.unreachable is False


def test_boundary_required_equals_baseline_is_not_urgent():
    # Strict '>' per resolution-rules.md: required_a == baseline_desired_a is Normal.
    result = resolve_required_current(
        deadline=time(7, 0),
        now=datetime(2026, 7, 21, 6, 0),
        soc=79.0,
        active_soc_limit=80.0,
        ev_battery_capacity_kwh=60.0,
        voltage=100.0,
        baseline_desired_a=6.0,
        maximum_permitted_rate_a=32.0,
    )
    assert result.required_a == pytest.approx(6.0)
    assert result.urgent is False


def test_boundary_required_equals_maximum_rate_is_still_reachable():
    # Strict '>' per resolution-rules.md: required_a == maximum_permitted_rate_a is Urgent,
    # not Unreachable.
    result = resolve_required_current(
        deadline=time(7, 0),
        now=datetime(2026, 7, 21, 6, 0),
        soc=70.0,
        active_soc_limit=80.0,
        ev_battery_capacity_kwh=32.0,
        voltage=100.0,
        baseline_desired_a=6.0,
        maximum_permitted_rate_a=32.0,
    )
    assert result.required_a == pytest.approx(32.0)
    assert result.urgent is True
    assert result.unreachable is False
