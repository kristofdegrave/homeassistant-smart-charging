"""Billing-Protection Engine (E5, part 1/2). Pure -- no HA imports (ADR-0006/0009).

The full two-row effective-peak-limit resolution (`resolution-rules.md`): row 1
raises to the maximum peak under deadline urgency (R5/C3, fed by the Deadline
Engine, E4); row 2 (unchanged) is min(monthly, max), reached only when
`urgent=False`. Also the R3 peak clamp with its grace-period breach tracker
(Sec 6.2). The Peak-Demand Tracker is a SEPARATE sibling module,
`engines/peak_demand_tracker.py` (Task 1.3) -- ADR-0010's Decision names both
modules explicitly and states they "stay two sibling modules ... their
relationship is recorded by project-plan task E5 bundling them, not by a
directory."
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def resolve_effective_peak_limit(monthly_peak_kw: float, max_peak_kw: float, urgent: bool) -> float:
    """Row 1: urgent -> max_peak_kw (R5/C3). Row 2 (unchanged): min(monthly, max)."""
    if urgent:
        return max_peak_kw
    return min(monthly_peak_kw, max_peak_kw)


@dataclass(frozen=True)
class PeakBreachTracker:
    """R3's grace-period state: when a sustained at-minimum breach began, if any."""

    breached_since: float | None = None


def apply_peak_clamp(
    desired_current: float,
    net_w: float,
    charger_w: float,
    voltage: float,
    effective_peak_limit_kw: float,
    safety_margin_w: float,
    min_a: float,
    grace_period_s: float,
    tracker: PeakBreachTracker,
    now: float,
) -> tuple[float, PeakBreachTracker, bool]:
    """Return (clamped_current, new_tracker, force_stop) -- the R3 peak clamp.

    Solves from the baseline actually flowing (`net_w - charger_w`), the same
    raw-reading approach E6's grid-safety clamp uses, so a breach cannot hide
    behind the request. The breach timer is gated on the REQUEST, not the
    clamped result: only when the mode is actually asking for at least `min_a`
    (it wants to charge) AND the available headroom is below `min_a` does a
    breach start/continue. A request already below `min_a` (Off, an
    idle/cooldown/SOC-gated mode, or a disconnect all request 0 A) can never
    start or extend the timer, regardless of headroom -- R3's own wording
    requires the charger to be "already at the minimum charging current" before
    a sustained shortfall counts as a stop condition. `force_stop=True` only
    once that request-gated breach has held continuously for `grace_period_s`.
    Until then, a momentary breach holds at `min_a` rather than the (sub-`min_a`,
    possibly negative) floored headroom -- E8's floor/cap stage turns anything
    below `min_a` into an immediate stop, so returning the raw headroom here
    would zero the charger out every breaching cycle and the grace period would
    never have a chance to elapse (R3: "a momentary breach does not stop
    charging").
    """
    baseline_w = net_w - charger_w
    target_w = effective_peak_limit_kw * 1000.0 - safety_margin_w
    headroom_a = math.floor((target_w - baseline_w) / voltage)
    clamped = min(desired_current, float(headroom_a))

    is_breaching = desired_current >= min_a and headroom_a < min_a
    if is_breaching:
        breached_since = tracker.breached_since if tracker.breached_since is not None else now
        if now - breached_since >= grace_period_s:
            return 0.0, PeakBreachTracker(breached_since=None), True
        return min_a, PeakBreachTracker(breached_since=breached_since), False

    return clamped, PeakBreachTracker(breached_since=None), False
