"""SOC-Target engine (E3). Pure -- no HA imports.

Full R7 three-row priority table: solar-reserve cap -> solar step-up -> default.
Row 1 (R9/UC07) and row 2 (R8/UC06) are both `Auto`-only mechanisms; row 3 -- the
configured override -- is the fallback every profile shares.
"""

from dataclasses import dataclass

from ..const import PROFILE_AUTO


@dataclass(frozen=True)
class SolarStepUpState:
    """R8's lifecycle state: whether a step-up is currently applied, and its value."""

    stepped_pct: float | None = None  # None = no step-up in effect (Baseline, UC06 state model)


def resolve_solar_step_up(
    state: SolarStepUpState,
    is_solar_mode_charging: bool,
    soc: float,
    default_limit: float,
    step_threshold_pp: float,
    step_pp: float,
    max_solar_soc: float,
) -> tuple[float, SolarStepUpState]:
    """Return (row-2 value if in effect else default_limit, new_state) -- R8/UC06.

    Clears (returns to Baseline) the moment `is_solar_mode_charging` is False --
    the caller passes False both when the active mode leaves solar and on a
    disconnect (UC06's exception flow), so this function has one clearing rule,
    not two. Applies a fresh step (or a further step) whenever charging in a
    solar mode and SOC is within `step_threshold_pp` of the currently-effective
    limit (the state's own stepped value, or `default_limit` if none yet),
    clamped to `max_solar_soc` (UC06 step 3/2a).
    """
    if not is_solar_mode_charging:
        return default_limit, SolarStepUpState()

    current_limit = state.stepped_pct if state.stepped_pct is not None else default_limit

    if current_limit < max_solar_soc and soc >= current_limit - step_threshold_pp:
        new_limit = min(current_limit + step_pp, max_solar_soc)
        return new_limit, SolarStepUpState(stepped_pct=new_limit)

    return current_limit, state


def resolve_solar_reserve_active(
    profile: str,
    home_day_flag: bool,
    sun_is_down: bool,
    forecast_kwh: float,
    forecast_threshold_kwh: float,
    deadline_tomorrow_resolved: bool,
) -> bool:
    """R9/UC07's cap-activation condition -- shared by `resolve_active_soc_limit`'s
    row 1 and Auto mode-selection's row 4 (E2), per resolution-rules.md's note
    that both are "two separate effects of the same Auto decision."
    """
    return (
        profile == PROFILE_AUTO
        and home_day_flag
        and sun_is_down
        and forecast_kwh > forecast_threshold_kwh
        and not deadline_tomorrow_resolved
    )


def resolve_active_soc_limit(
    soc_limit_override: float,
    solar_reserve_active: bool,
    solar_reserve_soc: float,
    step_up_state: SolarStepUpState,
) -> float:
    """R7's three-row table: solar-reserve cap -> solar step-up -> default.

    `step_up_state` reflects whatever `resolve_solar_step_up` already computed
    this cycle (row 2's current value, if any) -- this function only applies
    the priority order, it does not itself run the step-up lifecycle.
    """
    if solar_reserve_active:
        return solar_reserve_soc
    if step_up_state.stepped_pct is not None:
        return step_up_state.stepped_pct
    return soc_limit_override
