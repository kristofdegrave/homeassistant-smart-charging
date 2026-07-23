"""Deadline engine (E4). Pure -- no HA imports.

Departure-deadline resolution (R14): a four-row priority table -- external sensor ->
holiday override -> home-day override -> day-of-week default. Any row, including the
terminal default, may resolve to `None` ("no deadline").
"""

from datetime import time


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
