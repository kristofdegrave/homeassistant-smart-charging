"""Deadline engine (E4). Pure -- no HA imports.

Departure-deadline resolution (R14): a four-row priority table -- external sensor ->
holiday override -> home-day override -> day-of-week default. Any row, including the
terminal default, may resolve to `None` ("no deadline").

`resolve_next_occurrence` turns R14's per-day resolutions into the single *next* occurrence
the urgency criteria are judged against (requirements.md R15: "never an occurrence that has
already passed today"), and `resolve_required_current` implements R5/R15's required-current
formula and the Normal/Urgent/Unreachable state boundaries (UC05's state model) against
that already-resolved datetime.

Splitting the two is what fixes issue #1005. `resolve_required_current` used to take a bare
`time` and combine it with `now`'s own calendar date, with no next-day rollover: a departure
time earlier in the day than `now` then produced a negative remaining window, saturating
`required_a` to infinity and pinning `urgent` True for the rest of the day (and, under `Auto`,
pinning mode selection to its urgent row). Choosing the occurrence is now a separate,
explicitly two-day decision, and the formula only ever sees a concrete datetime.
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta


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


def resolve_next_occurrence(
    deadline_today: time | None,
    deadline_tomorrow: time | None,
    now: datetime,
) -> datetime | None:
    """The next occurrence of the departure deadline, or None when none is resolved.

    requirements.md R15: "The deadline every criterion above is judged against is the next
    occurrence of the departure deadline (R14) -- never an occurrence that has already passed
    today. A departure time earlier in the day than the current time therefore never engages
    urgency or the unreachable notification on that basis alone; it is judged as the next
    day's occurrence, with the full time remaining until then."

    Both arguments are R14's four-row table already evaluated for their own day -- today's and
    tomorrow's. Two separate resolutions are required, not one time-of-day reused across two
    dates: the table's terminal row is a *day-of-week* default, so tomorrow's occurrence may be
    a different time of day, or absent entirely while today's exists (and vice versa).

    A deadline falling exactly on `now` counts as passed and rolls to tomorrow's occurrence --
    it leaves no time to charge in, and treating it as current would hand
    `resolve_required_current` a zero-length window.

    The occurrence is stamped with `now`'s own tzinfo, so an aware `now` yields an aware
    occurrence and the subtraction in `resolve_required_current` is a true absolute duration
    rather than wall-clock arithmetic. That matters because the window this returns routinely
    straddles 02:00 now that it can span midnight: on spring-forward, naive arithmetic would
    report 8h where 7h remain, understating `required_a` by ~12% on the one night urgency is
    most likely to matter. A naive `now` still works (tzinfo None combines to a naive
    occurrence) -- both sides simply stay in whichever domain the caller chose.

    R5's missed-deadline hold -- the one documented case that keeps pursuing the occurrence
    that has just elapsed -- is deliberately not modelled here; it is a separate, stateful
    mechanism (issue #1006) and cannot be inferred from these two readings alone.
    """
    if deadline_today is not None:
        today_at = datetime.combine(now.date(), deadline_today, tzinfo=now.tzinfo)
        if today_at > now:
            return today_at
    if deadline_tomorrow is not None:
        return datetime.combine(
            now.date() + timedelta(days=1), deadline_tomorrow, tzinfo=now.tzinfo
        )
    return None


@dataclass(frozen=True)
class RequiredCurrentResult:
    """Result of resolving the current required to meet a departure deadline."""

    required_a: float | None  # None when no deadline is resolved (urgency never applies)
    urgent: bool  # required_a > baseline_desired_a
    unreachable: bool  # required_a > maximum_permitted_rate_a


def resolve_required_current(
    deadline_at: datetime | None,
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
        time_remaining = deadline_at - now
        required_a = energy_needed / time_remaining, W -> A via `voltage`

    `deadline_at` is the already-chosen next occurrence (`resolve_next_occurrence`), not a
    bare time-of-day this function has to guess a date for -- see the module docstring for why
    that guess was wrong.

    `urgent` = required_a > baseline_desired_a (the mode rows 3-5 of Auto mode-selection
    would otherwise pick, or the Manual mode itself -- the caller resolves
    `baseline_desired_a`, this function only compares). `unreachable` = required_a >
    maximum_permitted_rate_a even so.
    """
    if deadline_at is None:
        return RequiredCurrentResult(required_a=None, urgent=False, unreachable=False)

    remaining_hours = (deadline_at - now).total_seconds() / 3600
    energy_needed_kwh = ev_battery_capacity_kwh * (active_soc_limit - soc) / 100

    if energy_needed_kwh <= 0:
        # SOC already at/above the active limit -- nothing left to charge, so a passed
        # or imminent deadline carries no urgency regardless of time remaining.
        required_a = 0.0
    elif remaining_hours <= 0:
        # Defensive only: `resolve_next_occurrence` never returns a datetime at or before
        # `now`, so the control cycle cannot reach this. Kept because this is a public pure
        # function -- an elapsed `deadline_at` passed in directly still saturates to maximum
        # urgency rather than raising ZeroDivisionError.
        required_a = float("inf")
    else:
        power_w = (energy_needed_kwh * 1000) / remaining_hours
        required_a = power_w / voltage

    return RequiredCurrentResult(
        required_a=required_a,
        urgent=required_a > baseline_desired_a,
        unreachable=required_a > maximum_permitted_rate_a,
    )
