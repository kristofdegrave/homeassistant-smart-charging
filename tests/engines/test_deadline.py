"""Plain-pytest tests for the Deadline Engine (E4): departure-deadline resolution
(R14) and required-current/urgency computation (R5/R15).

This module used to open with a long note explaining why its constants deviated from
docs/plans/2026-07-21-deadline-soc-management-design.md §6's literal worked example: under
the old no-next-day-rollover contract, the plan's own `NOW = 22:00` / `DEADLINE = 06:00`
pairing ("next-day 06:00 -- 8 hours remaining") could not produce a positive window, so the
tests were kept same-day to stay within that contract. Issue #1005 resolved the underlying
inconsistency in favour of the plan (and of requirements.md R15): choosing the occurrence is
now `resolve_next_occurrence`'s job, and `resolve_required_current` takes the already-chosen
datetime, so the two concerns are testable separately and the plan's cross-midnight example
is expressible. The same-day constants below are kept only because they reproduce the plan's
exact arithmetic (75 kWh * 30% / 8h / 230V = 12.228 A), not because of any date constraint.
"""

from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest

from custom_components.smart_charging.engines.deadline import (
    resolve_departure_deadline,
    resolve_next_occurrence,
    resolve_required_current,
)

MON_DEFAULT = time(6, 0)

NOW = datetime(2026, 7, 21, 22, 0)  # Tuesday 22:00

# 8 hours apart -- reproduces the plan's exact worked-example numbers.
FORMULA_NOW = datetime(2026, 7, 21, 6, 0)  # 06:00
FORMULA_DEADLINE_AT = datetime(2026, 7, 21, 14, 0)  # 14:00 -- 8 hours remaining


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
        deadline_at=None,
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
        deadline_at=FORMULA_DEADLINE_AT,
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
        deadline_at=FORMULA_DEADLINE_AT,
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
        deadline_at=FORMULA_DEADLINE_AT,
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
        deadline_at=datetime(2026, 7, 21, 22, 5),
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
        deadline_at=datetime(2026, 7, 21, 21, 0),
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
    # Issue #650: this saturation to float('inf') is this pure engine's own documented
    # contract (design doc Sec6) and must stay unchanged -- any capping to a finite,
    # meaningful value (e.g. maximum_permitted_rate_a) happens at the coordinator boundary,
    # where the result crosses into the HA-bound DeadlineUnreachableNotified event payload.
    assert result.required_a == float("inf")


def test_no_urgency_when_soc_already_at_or_above_limit_even_if_deadline_passed():
    # Reviewer finding (PR #350): a passed deadline must not report urgency/unreachability
    # when there's nothing left to charge -- the caller (Auto row 1: SOC >= limit -> Off)
    # happens to gate on this first, but the signal itself should be correct on its own.
    result = resolve_required_current(
        deadline_at=datetime(2026, 7, 21, 21, 0),
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
        deadline_at=datetime(2026, 7, 21, 7, 0),
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
        deadline_at=datetime(2026, 7, 21, 7, 0),
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


# --- Next-occurrence resolution (R15, issue #1005) ---------------------------------------


def test_next_occurrence_is_today_when_departure_time_still_ahead():
    assert resolve_next_occurrence(
        deadline_today=time(23, 0),
        deadline_tomorrow=time(6, 0),
        now=NOW,  # 22:00
    ) == datetime(2026, 7, 21, 23, 0)


def test_next_occurrence_rolls_to_tomorrow_once_todays_departure_time_has_passed():
    # THE #1005 REGRESSION. 07:00 against an afternoon `now` used to resolve as a deadline
    # 8 hours in the PAST, saturating required_a to infinity and pinning `urgent` True for
    # the rest of the day. R15: judged as the next day's occurrence instead.
    assert resolve_next_occurrence(
        deadline_today=time(7, 0),
        deadline_tomorrow=time(7, 0),
        now=datetime(2026, 7, 21, 15, 0),
    ) == datetime(2026, 7, 22, 7, 0)


def test_next_occurrence_uses_tomorrows_own_departure_time_not_todays():
    # R14's terminal row is a day-of-week default, so the rolled-over occurrence must come
    # from tomorrow's resolution -- not today's time stamped onto tomorrow's date.
    assert resolve_next_occurrence(
        deadline_today=time(7, 0),
        deadline_tomorrow=time(9, 30),
        now=datetime(2026, 7, 21, 15, 0),
    ) == datetime(2026, 7, 22, 9, 30)


def test_next_occurrence_is_none_when_todays_has_passed_and_tomorrow_has_no_deadline():
    # A passed departure time must not be dragged forward onto a day R14 resolves as
    # "no deadline" -- urgency simply does not apply.
    assert (
        resolve_next_occurrence(
            deadline_today=time(7, 0),
            deadline_tomorrow=None,
            now=datetime(2026, 7, 21, 15, 0),
        )
        is None
    )


def test_next_occurrence_falls_to_tomorrow_when_today_has_no_deadline():
    assert resolve_next_occurrence(
        deadline_today=None,
        deadline_tomorrow=time(6, 0),
        now=datetime(2026, 7, 21, 15, 0),
    ) == datetime(2026, 7, 22, 6, 0)


def test_next_occurrence_is_none_when_neither_day_resolves_a_deadline():
    assert resolve_next_occurrence(deadline_today=None, deadline_tomorrow=None, now=NOW) is None


def test_next_occurrence_treats_a_departure_time_exactly_now_as_passed():
    # A zero-length window leaves no time to charge in, and would hand
    # resolve_required_current a division by zero -- roll it to tomorrow.
    assert resolve_next_occurrence(
        deadline_today=time(22, 0),
        deadline_tomorrow=time(6, 0),
        now=NOW,  # 22:00 exactly
    ) == datetime(2026, 7, 22, 6, 0)


def test_next_occurrence_spans_midnight_for_the_plans_own_worked_example():
    # docs/plans/2026-07-21-deadline-soc-management-design.md Sec 6's literal pairing --
    # plug in at 22:00 against an 06:00 departure -- now resolves to the 8-hour window the
    # plan always described, instead of a 16-hour-negative one.
    occurrence = resolve_next_occurrence(
        deadline_today=time(6, 0), deadline_tomorrow=time(6, 0), now=NOW
    )
    assert occurrence == datetime(2026, 7, 22, 6, 0)
    assert (occurrence - NOW).total_seconds() / 3600 == 8.0


def test_overnight_deadline_is_urgent_only_on_the_real_remaining_window():
    # End-to-end over both functions: the plan's 22:00 -> 06:00 case charging 75 kWh * 30%
    # over 8 hours needs 12.228 A, which is urgent against a 6 A baseline but reachable --
    # NOT the infinite, always-unreachable figure the old same-day contract produced.
    result = resolve_required_current(
        deadline_at=resolve_next_occurrence(
            deadline_today=time(6, 0), deadline_tomorrow=time(6, 0), now=NOW
        ),
        now=NOW,
        soc=50.0,
        active_soc_limit=80.0,
        ev_battery_capacity_kwh=75.0,
        voltage=230.0,
        baseline_desired_a=6.0,
        maximum_permitted_rate_a=32.0,
    )
    assert result.required_a == pytest.approx(12.228, abs=0.01)
    assert result.urgent is True
    assert result.unreachable is False


# --- DST: the window spans midnight now, so it straddles the transition ------------------

BRUSSELS = ZoneInfo("Europe/Brussels")
# Europe's spring-forward: 2026-03-29 02:00 CET -> 03:00 CEST. An overnight window ending
# after it therefore contains one hour less than the wall clock suggests.
SPRING_FORWARD_EVE = datetime(2026, 3, 28, 23, 0, tzinfo=BRUSSELS)


def test_required_current_counts_the_lost_hour_across_spring_forward():
    """The remaining window must be an ABSOLUTE duration, not wall-clock arithmetic.

    23:00 the evening before spring-forward to 07:00 the next morning is 7 real hours, not 8 --
    the clocks jump 02:00 -> 03:00 in between. Subtracting two aware datetimes does NOT give
    this for free: CPython short-circuits when both share a tzinfo object and returns the plain
    field difference, so an implementation that merely stamps tzinfo onto the occurrence still
    computes 8 hours and understates required_a by ~12%, in the permissive direction, on one of
    the nights urgency matters most.
    """
    occurrence = resolve_next_occurrence(
        deadline_today=None, deadline_tomorrow=time(7, 0), now=SPRING_FORWARD_EVE
    )
    assert occurrence == datetime(2026, 3, 29, 7, 0, tzinfo=BRUSSELS)

    result = resolve_required_current(
        deadline_at=occurrence,
        now=SPRING_FORWARD_EVE,
        soc=50.0,
        active_soc_limit=80.0,
        ev_battery_capacity_kwh=75.0,
        voltage=230.0,
        baseline_desired_a=6.0,
        maximum_permitted_rate_a=32.0,
    )
    # 22.5 kWh over the REAL 7 h = 3214.3 W -> 13.975 A. Over a wall-clock 8 h it would be
    # 12.228 A -- the same figure the same-day worked example produces, which is exactly how
    # this class of bug hides.
    assert result.required_a == pytest.approx(22.5 * 1000 / 7 / 230.0, abs=1e-3)
    assert result.required_a == pytest.approx(13.975, abs=0.01)


def test_required_current_counts_the_repeated_hour_across_fall_back():
    """The mirror case: 2026-10-25 03:00 CEST -> 02:00 CET, so the same overnight window holds
    one hour MORE than the wall clock suggests, and required_a is correspondingly lower."""
    now = datetime(2026, 10, 24, 23, 0, tzinfo=BRUSSELS)
    occurrence = resolve_next_occurrence(deadline_today=None, deadline_tomorrow=time(7, 0), now=now)
    result = resolve_required_current(
        deadline_at=occurrence,
        now=now,
        soc=50.0,
        active_soc_limit=80.0,
        ev_battery_capacity_kwh=75.0,
        voltage=230.0,
        baseline_desired_a=6.0,
        maximum_permitted_rate_a=32.0,
    )
    assert result.required_a == pytest.approx(22.5 * 1000 / 9 / 230.0, abs=1e-3)


def test_naive_datetimes_are_left_alone_rather_than_assuming_a_machine_timezone():
    """A naive pair keeps plain subtraction -- `astimezone()` on a naive datetime would assume
    the machine's local zone, which this pure engine has no business knowing."""
    result = resolve_required_current(
        deadline_at=datetime(2026, 3, 29, 7, 0),
        now=datetime(2026, 3, 28, 23, 0),
        soc=50.0,
        active_soc_limit=80.0,
        ev_battery_capacity_kwh=75.0,
        voltage=230.0,
        baseline_desired_a=6.0,
        maximum_permitted_rate_a=32.0,
    )
    assert result.required_a == pytest.approx(22.5 * 1000 / 8 / 230.0, abs=1e-3)


def test_next_occurrence_comparison_stays_wall_clock_across_the_transition():
    """R15 asks whether the departure time is "earlier in the day than the current time" -- a
    wall-clock question. On the transition day itself, an 07:00 departure is still ahead of a
    01:00 `now` even though only 5 real hours separate them."""
    now = datetime(2026, 3, 29, 1, 0, tzinfo=BRUSSELS)
    assert resolve_next_occurrence(
        deadline_today=time(7, 0), deadline_tomorrow=time(7, 0), now=now
    ) == datetime(2026, 3, 29, 7, 0, tzinfo=BRUSSELS)
