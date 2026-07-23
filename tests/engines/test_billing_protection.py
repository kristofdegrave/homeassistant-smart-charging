"""Plain-pytest tests for the Billing-Protection Engine (E5 -- UC03, R3, R5).

Row 1 (deadline urgency) is added by this suite -- row 2 (unchanged) is only
reached when urgent=False."""

from custom_components.smart_charging.engines.billing_protection import (
    PeakBreachTracker,
    apply_peak_clamp,
    resolve_effective_peak_limit,
)
from custom_components.smart_charging.engines.cycle_invariant import apply_floor_cap

DEFAULTS = dict(voltage=230.0, safety_margin_w=250.0, min_a=6.0, grace_period_s=120.0)


def test_effective_peak_limit_is_the_lesser_of_monthly_peak_and_maximum():
    assert resolve_effective_peak_limit(monthly_peak_kw=3.0, max_peak_kw=4.0, urgent=False) == 3.0
    assert resolve_effective_peak_limit(monthly_peak_kw=5.0, max_peak_kw=4.0, urgent=False) == 4.0


def test_urgency_raises_to_the_maximum_peak_regardless_of_monthly_peak():
    assert resolve_effective_peak_limit(monthly_peak_kw=1.0, max_peak_kw=4.0, urgent=True) == 4.0


def test_urgency_never_exceeds_the_maximum_peak():
    # monthly_peak_kw exceeds max_peak_kw here so this is discriminating on its own --
    # row 2 (min) would return 10.0 without row 1's raise-to-maximum behavior.
    assert resolve_effective_peak_limit(monthly_peak_kw=10.0, max_peak_kw=4.0, urgent=True) == 4.0


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
    # can't" breach, not just an idle cycle. The clamp holds at min_a during the
    # grace window -- returning the raw (sub-min_a) headroom instead would make E8's
    # floor/cap stage zero the charger out every cycle, defeating the grace period.
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
    assert desired == DEFAULTS["min_a"]
    assert not force_stop
    assert tracker.breached_since == 0.0  # grace timer started, not yet elapsed
    assert apply_floor_cap(desired, min_a=DEFAULTS["min_a"], max_a=32.0) == DEFAULTS["min_a"]


def test_headroom_exactly_at_minimum_is_not_a_breach():
    # 3 kW limit, 250 W margin -> target 2750 W. Baseline 1370 W leaves
    # headroom = floor((2750 - 1370) / 230) = 6 A == min_a -- charging AT the
    # minimum is achievable, so this must not count as "can't charge."
    tracker = PeakBreachTracker(breached_since=None)
    desired, tracker, force_stop = apply_peak_clamp(
        desired_current=32.0,
        net_w=1370.0,
        charger_w=0.0,
        effective_peak_limit_kw=3.0,
        tracker=tracker,
        now=0.0,
        **DEFAULTS,
    )
    assert desired == DEFAULTS["min_a"]
    assert not force_stop
    assert tracker.breached_since is None


def test_breach_just_short_of_grace_period_does_not_fire():
    tracker = PeakBreachTracker(breached_since=0.0)
    desired, tracker, force_stop = apply_peak_clamp(
        desired_current=32.0,
        net_w=2900.0,
        charger_w=0.0,
        effective_peak_limit_kw=3.0,
        tracker=tracker,
        now=119.0,
        **DEFAULTS,
    )
    assert desired == DEFAULTS["min_a"]
    assert not force_stop
    assert tracker.breached_since == 0.0  # original start time preserved, not reset


def test_continuing_breach_preserves_the_original_start_time():
    tracker = PeakBreachTracker(breached_since=0.0)
    _, tracker, _ = apply_peak_clamp(
        desired_current=32.0,
        net_w=2900.0,
        charger_w=0.0,
        effective_peak_limit_kw=3.0,
        tracker=tracker,
        now=60.0,
        **DEFAULTS,
    )
    assert tracker.breached_since == 0.0  # not bumped to 60.0


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
