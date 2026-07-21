"""Peak-Demand Tracker (E5, part 2/2). Pure -- no HA imports (ADR-0006/0009).

A sibling module to billing_protection.py (ADR-0010: "the V6 pair ... stays two
sibling modules ... their relationship is recorded by project-plan task E5
bundling them, not by a directory"). Deliberately does NOT import
signal_conditioning.smooth_net_power -- an engine may not call another engine
(system-design Sec 4 rule 4). The coordinator (M1) is responsible for smoothing
net_power over its OWN dedicated ~15-minute window (distinct from R10's short
window) before calling this function; see design doc Sec 6.4 and plan Task 5.1.
"""

from __future__ import annotations


def update_monthly_peak_demand(
    smoothed_kw: float,
    current_month: tuple[int, int],
    tracked_kw: float,
    tracked_month: tuple[int, int] | None,
) -> tuple[float, tuple[int, int]]:
    """Return (monthly_peak_kw, new_tracked_month) -- the running monthly-peak max.

    `current_month` is `(year, month)`, computed by the coordinator from real
    wall-clock time -- this function stays pure. A month change resets the
    running peak to *this cycle's* own smoothed reading, not to 0 kW: a fresh
    month's peak starts accumulating immediately from whatever the household is
    actually drawing, not from an artificial floor (design doc Sec 6.4's
    bootstrap note -- which also explains why this alone does not guarantee
    immediate charging headroom on a cold start).
    """
    if tracked_month != current_month:
        return smoothed_kw, current_month
    return max(tracked_kw, smoothed_kw), current_month
