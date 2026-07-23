"""Plain-pytest tests for the Deadline Engine's departure-deadline resolution (E4, R14)."""

from datetime import time

from custom_components.smart_charging.engines.deadline import resolve_departure_deadline

MON_DEFAULT = time(6, 0)


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
