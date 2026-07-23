"""Deadline engine (E4). Pure -- no HA imports.

Departure-deadline resolution (R14): a four-row priority table -- external sensor ->
holiday override -> home-day override -> day-of-week default. Any row, including the
terminal default, may resolve to `None` ("no deadline").

`resolve_required_current` implements R5/R15's required-current formula and the
Normal/Urgent/Unreachable state boundaries (UC05's state model). It combines `deadline`
with `now`'s own calendar date -- no next-day rollover -- per
docs/plans/2026-07-21-deadline-soc-management-design.md §6: a same-day deadline already in
the past saturates (`required_a` reflects maximum urgency) rather than raising
`ZeroDivisionError`, since the control cycle resolves the deadline fresh often enough that
`now` never legitimately outruns it by more than one control interval.
"""

from dataclasses import dataclass
from datetime import datetime, time


def resolve_departure_deadline(
    external_configured: bool,
    external: time | None,
    is_holiday: bool,
    holiday_override: time | None,
    home_day_flag: bool,
    home_day_override: time | None,
    day_of_week_default: time | None,
) -> time | None:
    """R14's four-row table: external sensor -> holiday -> home-day -> day-of-week
    default. Any row, including the terminal default, may resolve to None ("no
    deadline"). Public-holiday wins over home-day when both apply (requirements.md
    R14, second bullet).

    `external_configured` is distinct from `external` being None: the
    `departure_external` adapter role is optional (NF3) -- when it is not mapped
    at all, row 1 must never match, falling through to row 2, exactly like every
    other optional role in this system. When it IS mapped, its current reading
    (including None, "sensor currently reports no deadline") wins outright, per
    R14's "external sensor ... takes precedence over all configured values." The
    coordinator (not this function) knows whether the role was configured (§10).
    """
    if external_configured:
        return external
    if is_holiday:
        return holiday_override
    if home_day_flag:
        return home_day_override
    return day_of_week_default


@dataclass(frozen=True)
class RequiredCurrentResult:
    """Result of resolving the current required to meet a departure deadline."""

    required_a: float | None  # None when no deadline is resolved (urgency never applies)
    urgent: bool  # required_a > baseline_desired_a
    unreachable: bool  # required_a > maximum_permitted_rate_a


def resolve_required_current(
    deadline: time | None,
    now: datetime,
    soc: float,
    active_soc_limit: float,
    ev_battery_capacity_kwh: float,
    voltage: float,
    baseline_desired_a: float,
    maximum_permitted_rate_a: float,
) -> RequiredCurrentResult:
    """R5/R15's required-current formula (resolution-rules.md 'Required current for the
    departure deadline'):

        energy_needed = capacity * (limit - soc) / 100
        time_remaining = deadline - now
        required_a = energy_needed / time_remaining, W -> A via `voltage`

    `urgent` = required_a > baseline_desired_a (the mode rows 3-5 of Auto mode-selection
    would otherwise pick, or the Manual mode itself -- the caller resolves
    `baseline_desired_a`, this function only compares). `unreachable` = required_a >
    maximum_permitted_rate_a even so.
    """
    if deadline is None:
        return RequiredCurrentResult(required_a=None, urgent=False, unreachable=False)

    deadline_dt = datetime.combine(now.date(), deadline)
    remaining_hours = (deadline_dt - now).total_seconds() / 3600
    energy_needed_kwh = ev_battery_capacity_kwh * (active_soc_limit - soc) / 100

    if energy_needed_kwh <= 0:
        # SOC already at/above the active limit -- nothing left to charge, so a passed
        # or imminent deadline carries no urgency regardless of time remaining.
        required_a = 0.0
    elif remaining_hours <= 0:
        # Deadline already passed today -- saturate to maximum urgency instead of
        # dividing by zero/negative (design doc §6).
        required_a = float("inf")
    else:
        power_w = (energy_needed_kwh * 1000) / remaining_hours
        required_a = power_w / voltage

    return RequiredCurrentResult(
        required_a=required_a,
        urgent=required_a > baseline_desired_a,
        unreachable=required_a > maximum_permitted_rate_a,
    )
