"""Plain-pytest tests for the Billing-Protection Engine (E5 -- UC03, R3).

Row-2-only effective-peak-limit resolution (deadline urgency, row 1, is
structurally inert without the Deadline Engine, E4 -- its own epic)."""

from custom_components.smart_charging.engines.billing_protection import (
    PeakBreachTracker,
    apply_peak_clamp,
    resolve_effective_peak_limit,
)

DEFAULTS = dict(voltage=230.0, safety_margin_w=250.0, min_a=6.0, grace_period_s=120.0)


def test_effective_peak_limit_is_the_lesser_of_monthly_peak_and_maximum():
    assert resolve_effective_peak_limit(monthly_peak_kw=3.0, max_peak_kw=4.0) == 3.0
    assert resolve_effective_peak_limit(monthly_peak_kw=5.0, max_peak_kw=4.0) == 4.0


def test_clamp_reduces_to_available_headroom():
    # 3 kW limit, 250 W margin -> target 2750 W. Baseline (net-charger) = 1000 W.
    # Headroom = (2750 - 1000) / 230 = 7.6 A -> floor 7 A.
    desired, tracker, force_stop = apply_peak_clamp(
        desired_current=32.0,
        net_w=1000.0 + 32.0 * 230.0,  # baseline 1000 W + a charging draw already flowing
        charger_w=32.0 * 230.0,
        effective_peak_limit_kw=3.0,
        tracker=PeakBreachTracker(breached_since=None),
        now=0.0,
        **DEFAULTS,
    )
    assert desired == 7.0
    assert not force_stop
    assert tracker.breached_since is None


def test_momentary_breach_at_minimum_does_not_stop():
    # Baseline alone (2900 W) leaves < min_a of headroom under a 3 kW limit, and the
    # mode IS requesting >= min_a (32 A) -- this is a genuine "wants to charge but
    # can't" breach, not just an idle cycle.
    tracker = PeakBreachTracker(breached_since=None)
    desired, tracker, force_stop = apply_peak_clamp(
        desired_current=32.0,
        net_w=2900.0,
        charger_w=0.0,
        effective_peak_limit_kw=3.0,
        tracker=tracker,
        now=0.0,
        **DEFAULTS,
    )
    assert desired < DEFAULTS["min_a"]
    assert not force_stop
    assert tracker.breached_since == 0.0  # grace timer started, not yet elapsed


def test_a_zero_request_never_starts_the_breach_timer_even_with_no_headroom():
    # R3's stop condition requires the charger to be "already at the minimum
    # charging current" (requirements.md R3) -- a mode requesting 0 A (Off, an
    # idle/cooldown/SOC-gated mode, or a disconnect) must never accrue a breach,
    # no matter how little headroom remains. Without this guard, Captar's own
    # cooldown phase (which requests 0 A every cycle) would re-trigger force_stop
    # every grace period and never let its 10-minute cooldown complete (R11).
    tracker = PeakBreachTracker(breached_since=None)
    desired, tracker, force_stop = apply_peak_clamp(
        desired_current=0.0,
        net_w=2900.0,
        charger_w=0.0,
        effective_peak_limit_kw=3.0,
        tracker=tracker,
        now=0.0,
        **DEFAULTS,
    )
    assert desired <= 0.0
    assert not force_stop
    assert tracker.breached_since is None  # never started


def test_a_zero_request_clears_an_in_progress_breach_timer():
    # If the mode stops requesting current mid-breach (e.g. the coordinator just
    # gated it to 0 A for an unrelated reason), the timer must not keep running
    # from a now-irrelevant prior cycle.
    tracker = PeakBreachTracker(breached_since=0.0)
    desired, tracker, force_stop = apply_peak_clamp(
        desired_current=0.0,
        net_w=2900.0,
        charger_w=0.0,
        effective_peak_limit_kw=3.0,
        tracker=tracker,
        now=60.0,
        **DEFAULTS,
    )
    assert not force_stop
    assert tracker.breached_since is None


def test_sustained_breach_at_minimum_forces_stop_after_grace_period():
    tracker = PeakBreachTracker(breached_since=0.0)  # breach already timing since t=0
    desired, tracker, force_stop = apply_peak_clamp(
        desired_current=32.0,
        net_w=2900.0,
        charger_w=0.0,
        effective_peak_limit_kw=3.0,
        tracker=tracker,
        now=120.0,
        **DEFAULTS,
    )
    assert desired == 0.0
    assert force_stop
    assert tracker.breached_since is None  # tracker resets once it has fired


def test_breach_clearing_before_grace_period_resets_tracker():
    tracker = PeakBreachTracker(breached_since=0.0)
    # Headroom recovers (baseline drops) before the grace period elapses.
    desired, tracker, force_stop = apply_peak_clamp(
        desired_current=10.0,
        net_w=500.0,
        charger_w=0.0,
        effective_peak_limit_kw=3.0,
        tracker=tracker,
        now=60.0,
        **DEFAULTS,
    )
    assert desired >= DEFAULTS["min_a"]
    assert not force_stop
    assert tracker.breached_since is None


def test_clamp_never_returns_more_than_requested():
    tracker = PeakBreachTracker(breached_since=None)
    desired, _, _ = apply_peak_clamp(
        desired_current=6.0,
        net_w=0.0,
        charger_w=0.0,
        effective_peak_limit_kw=4.0,
        tracker=tracker,
        now=0.0,
        **DEFAULTS,
    )
    assert desired == 6.0  # ample headroom -- clamp never raises the request
