"""Billing-Protection Engine (E5, part 1/2). Pure -- no HA imports (ADR-0006/0009).

The full two-row effective-peak-limit resolution (`resolution-rules.md`): row 1
raises to the maximum peak under deadline urgency (R5/C3, fed by the Deadline
Engine, E4); row 2 is min(max(operand, floor), max) (R3, #754), reached only
when `urgent=False` -- the peak floor keeps a low or not-yet-established
monthly peak (early in a billing month, or right after the monthly reset) from
resolving the effective peak limit down to near 0 kW and blocking
Captar/Power charging, while max() is applied before min() so the floor can
never raise the limit above the maximum peak. The operand itself is the
internally-tracked monthly peak merged with an optional external reading
(ADR-0030/ADR-0032) -- see `resolve_monthly_peak_operand` below. Also the R3
peak clamp with its grace-period breach tracker (Sec 6.2). The Peak-Demand
Tracker is a SEPARATE sibling module, `engines/peak_demand_tracker.py` --
ADR-0010's Decision names both modules explicitly and states they "stay two
sibling modules ... their relationship is recorded by project-plan task E5
bundling them, not by a directory."
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def resolve_monthly_peak_operand(internal_kw: float, external_kw: float | None) -> float:
    """Merge the internally-tracked monthly peak with an optional external reading
    (ADR-0030/ADR-0032 D-2): the operand `resolve_effective_peak_limit` clamps against.

    Unmapped (`external_kw is None`) rests on the internal value alone (R3 AC9); mapped, the
    higher of the two wins (R3 AC8) -- the merge only ever raises the operand, it never lowers
    it below the internally-tracked peak. `is None`, not truthiness: a genuine `0.0` external
    reading is a value, not a stand-in for "absent".
    """
    if external_kw is None:
        return internal_kw
    return max(internal_kw, external_kw)


def resolve_effective_peak_limit(
    monthly_peak_kw: float, max_peak_kw: float, peak_floor_kw: float, urgent: bool
) -> float:
    """Row 1: urgent -> max_peak_kw (R5/C3). Row 2: min(max(monthly, floor), max) (R3, #754)
    -- the floor is applied via max() before the max_peak_kw clamp via min(), so it can raise
    a low/not-yet-established monthly peak but never raise the result above max_peak_kw."""
    if urgent:
        return max_peak_kw
    return min(max(monthly_peak_kw, peak_floor_kw), max_peak_kw)


@dataclass(frozen=True)
class PeakBreachTracker:
    """R3's grace-period state: when a sustained at-minimum breach began, if any."""

    breached_since: float | None = None


@dataclass(frozen=True)
class BaselineDebouncer:
    """Issue #990's headroom-increase debounce state: the last accepted `baseline_w`
    (`net_w - charger_w`) and how many consecutive cycles a lower (more headroom) raw
    reading has now held without yet being accepted."""

    accepted_w: float | None = None
    pending_cycles: int = 0


def debounce_baseline_w(
    raw_baseline_w: float,
    tracker: BaselineDebouncer,
    debounce_cycles: int,
) -> tuple[float, BaselineDebouncer]:
    """Issue #990: the charger's own power sensor (slow Modbus poll) can still report the
    prior, higher value for one extra coordinator cycle after a current step-down, while the
    net meter (fast) already reflects the drop -- transiently swinging `baseline_w` (and, via
    it, `peak_headroom_a`/`solar_surplus_w`) artificially low. A lower `raw_baseline_w` than
    the last accepted reading INCREASES headroom (more permissive) and is only accepted once a
    below-accepted reading has been seen on `debounce_cycles` consecutive calls -- not
    necessarily the same value each time; the newest raw reading at that point is what gets
    committed (e.g. 500 -> -1500 (1st pending call) -> -4000 (2nd) commits -4000, not -1500). A
    `raw_baseline_w` at or above the last accepted reading DECREASES (or holds) headroom -- the
    safety-conservative direction -- and always applies immediately, same as the very first
    call (`tracker.accepted_w is None`, nothing to debounce against yet). The mirror-image
    transient (a current step-UP: net_w rises immediately, charger_w stale-low, baseline
    transiently too HIGH) is accepted immediately by the same "at or above" rule and becomes
    the new `accepted_w` -- an accepted trade-off: it costs one extra cycle of understated
    headroom/`solar_surplus_w` once the true, lower baseline reasserts itself, but never an
    unsafe one.
    """
    if tracker.accepted_w is None or raw_baseline_w >= tracker.accepted_w:
        return raw_baseline_w, BaselineDebouncer(accepted_w=raw_baseline_w, pending_cycles=0)

    pending_cycles = tracker.pending_cycles + 1
    if pending_cycles >= debounce_cycles:
        return raw_baseline_w, BaselineDebouncer(accepted_w=raw_baseline_w, pending_cycles=0)
    return tracker.accepted_w, BaselineDebouncer(
        accepted_w=tracker.accepted_w, pending_cycles=pending_cycles
    )


def apply_peak_clamp(
    desired_current: float,
    baseline_w: float,
    voltage: float,
    effective_peak_limit_kw: float,
    safety_margin_w: float,
    min_a: float,
    grace_period_s: float,
    tracker: PeakBreachTracker,
    now: float,
) -> tuple[float, PeakBreachTracker, bool]:
    """Return (clamped_current, new_tracker, force_stop) -- the R3 peak clamp.

    Solves from the baseline actually flowing (`net_w - charger_w`, resolved by the caller --
    issue #990: after `debounce_baseline_w`, so a transient stale-sensor reading cannot inflate
    headroom for even one cycle), the same raw-reading approach E6's grid-safety clamp uses, so
    a breach cannot hide behind the request. The breach timer is gated on the REQUEST, not the
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
