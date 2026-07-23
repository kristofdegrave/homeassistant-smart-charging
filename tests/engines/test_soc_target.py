"""Plain-pytest tests for the SOC-Target engine (E3): full R7 three-row resolution,
R8's solar step-up lifecycle, and R9's solar-reserve trigger."""

from custom_components.smart_charging.engines.soc_target import (
    SolarStepUpState,
    resolve_active_soc_limit,
    resolve_solar_reserve_active,
    resolve_solar_step_up,
)

# --- resolve_active_soc_limit: priority order ---


def test_row1_reserve_wins_over_everything():
    state = SolarStepUpState(stepped_pct=90.0)
    assert (
        resolve_active_soc_limit(
            80.0, solar_reserve_active=True, solar_reserve_soc=60.0, step_up_state=state
        )
        == 60.0
    )


def test_row2_step_up_wins_over_default_when_reserve_inactive():
    state = SolarStepUpState(stepped_pct=90.0)
    assert (
        resolve_active_soc_limit(
            80.0, solar_reserve_active=False, solar_reserve_soc=60.0, step_up_state=state
        )
        == 90.0
    )


def test_row3_default_when_neither_reserve_nor_step_up():
    assert (
        resolve_active_soc_limit(
            80.0,
            solar_reserve_active=False,
            solar_reserve_soc=60.0,
            step_up_state=SolarStepUpState(),
        )
        == 80.0
    )


def test_tracks_a_changed_override():
    assert (
        resolve_active_soc_limit(
            65.0,
            solar_reserve_active=False,
            solar_reserve_soc=60.0,
            step_up_state=SolarStepUpState(),
        )
        == 65.0
    )


# --- resolve_solar_step_up: lifecycle (R8/UC06) ---


def test_no_step_while_soc_outside_threshold():
    limit, state = resolve_solar_step_up(
        SolarStepUpState(),
        is_solar_mode_charging=True,
        soc=70.0,
        default_limit=80.0,
        step_threshold_pp=2.0,
        step_pp=5.0,
        max_solar_soc=100.0,
    )
    assert limit == 80.0
    assert state.stepped_pct is None


def test_steps_up_once_within_threshold():
    limit, state = resolve_solar_step_up(
        SolarStepUpState(),
        is_solar_mode_charging=True,
        soc=78.5,
        default_limit=80.0,
        step_threshold_pp=2.0,
        step_pp=5.0,
        max_solar_soc=100.0,
    )
    assert limit == 85.0
    assert state.stepped_pct == 85.0


def test_further_step_clamps_to_maximum():
    limit, state = resolve_solar_step_up(
        SolarStepUpState(stepped_pct=98.0),
        is_solar_mode_charging=True,
        soc=97.0,
        default_limit=80.0,
        step_threshold_pp=2.0,
        step_pp=5.0,
        max_solar_soc=100.0,
    )
    assert limit == 100.0  # 98 + 5 = 103, clamped (2a)
    assert state.stepped_pct == 100.0


def test_no_further_step_once_already_at_maximum():
    limit, state = resolve_solar_step_up(
        SolarStepUpState(stepped_pct=100.0),
        is_solar_mode_charging=True,
        soc=99.0,
        default_limit=80.0,
        step_threshold_pp=2.0,
        step_pp=5.0,
        max_solar_soc=100.0,
    )
    assert limit == 100.0
    assert state.stepped_pct == 100.0


def test_step_up_preserved_when_still_solar_charging_outside_threshold_again():
    # SOC moved away from the new limit -- still no reset (only leaving solar/disconnect resets).
    limit, state = resolve_solar_step_up(
        SolarStepUpState(stepped_pct=85.0),
        is_solar_mode_charging=True,
        soc=81.0,
        default_limit=80.0,
        step_threshold_pp=2.0,
        step_pp=5.0,
        max_solar_soc=100.0,
    )
    assert limit == 85.0
    assert state.stepped_pct == 85.0


def test_clears_when_no_longer_solar_charging():
    # UC06 exception flow: active mode leaves solar (Auto escalation, manual switch) or
    # disconnect -- the caller passes is_solar_mode_charging=False for both.
    limit, state = resolve_solar_step_up(
        SolarStepUpState(stepped_pct=85.0),
        is_solar_mode_charging=False,
        soc=81.0,
        default_limit=80.0,
        step_threshold_pp=2.0,
        step_pp=5.0,
        max_solar_soc=100.0,
    )
    assert limit == 80.0
    assert state.stepped_pct is None


# --- resolve_solar_reserve_active: R9/UC07's five-way AND ---


def test_reserve_active_when_all_conditions_hold():
    assert (
        resolve_solar_reserve_active(
            profile="Auto",
            home_day_flag=True,
            sun_is_down=True,
            forecast_kwh=15.0,
            forecast_threshold_kwh=12.0,
            deadline_tomorrow_resolved=False,
        )
        is True
    )


def test_reserve_inactive_under_manual():
    assert (
        resolve_solar_reserve_active(
            profile="Manual",
            home_day_flag=True,
            sun_is_down=True,
            forecast_kwh=15.0,
            forecast_threshold_kwh=12.0,
            deadline_tomorrow_resolved=False,
        )
        is False
    )


def test_reserve_inactive_when_deadline_resolved_for_tomorrow():
    # R9/UC07: mutually exclusive with a departure deadline resolved for tomorrow.
    assert (
        resolve_solar_reserve_active(
            profile="Auto",
            home_day_flag=True,
            sun_is_down=True,
            forecast_kwh=15.0,
            forecast_threshold_kwh=12.0,
            deadline_tomorrow_resolved=True,
        )
        is False
    )


def test_reserve_inactive_when_forecast_at_or_below_threshold():
    assert (
        resolve_solar_reserve_active(
            profile="Auto",
            home_day_flag=True,
            sun_is_down=True,
            forecast_kwh=12.0,
            forecast_threshold_kwh=12.0,
            deadline_tomorrow_resolved=False,
        )
        is False
    )


def test_reserve_inactive_when_home_day_flag_clear():
    assert (
        resolve_solar_reserve_active(
            profile="Auto",
            home_day_flag=False,
            sun_is_down=True,
            forecast_kwh=15.0,
            forecast_threshold_kwh=12.0,
            deadline_tomorrow_resolved=False,
        )
        is False
    )


def test_reserve_inactive_while_sun_is_up():
    assert (
        resolve_solar_reserve_active(
            profile="Auto",
            home_day_flag=True,
            sun_is_down=False,
            forecast_kwh=15.0,
            forecast_threshold_kwh=12.0,
            deadline_tomorrow_resolved=False,
        )
        is False
    )
