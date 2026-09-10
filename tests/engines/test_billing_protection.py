"""Plain-pytest tests for the Billing-Protection Engine (E5 -- UC03, R3, R5).

Row 1 (deadline urgency) is added by this suite -- row 2 (min(max(operand, floor), max),
#754/R3) is only reached when urgent=False. The operand merge (resolve_monthly_peak_operand,
ADR-0032) is covered separately, both alone and run through the row-2 clamp."""

from custom_components.smart_charging.engines.billing_protection import (
    BaselineDebouncer,
    PeakBreachTracker,
    apply_peak_clamp,
    debounce_baseline_w,
    resolve_effective_peak_limit,
    resolve_monthly_peak_operand,
)
from custom_components.smart_charging.engines.cycle_invariant import apply_floor_cap

DEFAULTS = dict(voltage=230.0, safety_margin_w=250.0, min_a=6.0, grace_period_s=120.0)


def test_unmapped_external_rests_on_the_internal_value_alone():
    # R3 AC9: no external reading (unmapped role) -- the operand is the internal value as-is.
    assert resolve_monthly_peak_operand(2.0, None) == 2.0


def test_external_above_internal_wins():
    # R3 AC8: a higher external reading raises the operand above the internally-tracked peak.
    assert resolve_monthly_peak_operand(2.0, 4.09) == 4.09


def test_internal_above_external_wins():
    # ADR-0032 D-2: the merge only ever raises the operand, never lowers it below the
    # internally-tracked peak.
    assert resolve_monthly_peak_operand(5.0, 4.09) == 5.0


def test_a_genuine_zero_external_reading_is_a_value_not_an_absence():
    # Pins the returned value for a genuine 0.0 reading. is None is the intent-preserving
    # guard even though max()'s own behavior would happen to agree with a truthiness check
    # here, since a monthly peak in kW is never negative.
    assert resolve_monthly_peak_operand(2.0, 0.0) == 2.0


def test_merged_operand_still_clamped_to_the_maximum_peak():
    # Both ends of resolve_effective_peak_limit's existing min(max(operand, floor), max)
    # nesting stay intact when fed the merged operand -- an external reading above max_peak_kw
    # still resolves down to max_peak_kw, same as an internal reading would.
    operand = resolve_monthly_peak_operand(2.0, 9.0)
    assert (
        resolve_effective_peak_limit(
            monthly_peak_kw=operand, max_peak_kw=4.0, peak_floor_kw=2.5, urgent=False
        )
        == 4.0
    )


def test_merged_operand_still_raised_to_the_floor():
    # An external reading that beats the internal value but still sits below peak_floor_kw
    # resolves to the floor -- the merge raises the operand, it does not escape the floor half
    # of the clamp either.
    operand = resolve_monthly_peak_operand(0.5, 1.0)
    assert (
        resolve_effective_peak_limit(
            monthly_peak_kw=operand, max_peak_kw=4.0, peak_floor_kw=2.5, urgent=False
        )
        == 2.5
    )


def test_effective_peak_limit_is_the_lesser_of_monthly_peak_and_maximum():
    # peak_floor_kw=0.0 here -- these cases are about the min(monthly, max) half of the
    # formula, not the floor, so the floor is set low enough to never bind.
    assert (
        resolve_effective_peak_limit(
            monthly_peak_kw=3.0, max_peak_kw=4.0, peak_floor_kw=0.0, urgent=False
        )
        == 3.0
    )
    assert (
        resolve_effective_peak_limit(
            monthly_peak_kw=5.0, max_peak_kw=4.0, peak_floor_kw=0.0, urgent=False
        )
        == 4.0
    )


def test_urgency_raises_to_the_maximum_peak_regardless_of_monthly_peak():
    assert (
        resolve_effective_peak_limit(
            monthly_peak_kw=1.0, max_peak_kw=4.0, peak_floor_kw=0.0, urgent=True
        )
        == 4.0
    )


def test_urgency_never_exceeds_the_maximum_peak():
    # monthly_peak_kw exceeds max_peak_kw here so this is discriminating on its own --
    # row 2 (min) would return 10.0 without row 1's raise-to-maximum behavior.
    assert (
        resolve_effective_peak_limit(
            monthly_peak_kw=10.0, max_peak_kw=4.0, peak_floor_kw=0.0, urgent=True
        )
        == 4.0
    )


def test_low_monthly_peak_is_raised_to_the_floor():
    # #754: a low or not-yet-established monthly peak must not resolve the effective peak
    # limit down to near 0 kW and block Captar/Power charging.
    assert (
        resolve_effective_peak_limit(
            monthly_peak_kw=0.5, max_peak_kw=4.0, peak_floor_kw=2.5, urgent=False
        )
        == 2.5
    )


def test_monthly_peak_above_the_floor_is_unaffected_by_it():
    # Regression check -- the floor must never raise the limit above the pre-floor
    # min(monthly, max) result when monthly is already above the floor.
    assert (
        resolve_effective_peak_limit(
            monthly_peak_kw=3.0, max_peak_kw=4.0, peak_floor_kw=2.5, urgent=False
        )
        == 3.0
    )


def test_floor_never_raises_the_limit_above_the_maximum_peak():
    # max() is applied before min(): a floor set above maximum_peak must still be
    # clamped down to maximum_peak, not returned as-is.
    assert (
        resolve_effective_peak_limit(
            monthly_peak_kw=0.5, max_peak_kw=4.0, peak_floor_kw=10.0, urgent=False
        )
        == 4.0
    )


def test_monthly_peak_equal_to_the_floor_resolves_to_the_floor():
    # Boundary case: monthly_peak_kw == peak_floor_kw. max(monthly, floor) must still take
    # this (either) value, not fall through to a `>`-only comparison that would miss equality.
    assert (
        resolve_effective_peak_limit(
            monthly_peak_kw=2.5, max_peak_kw=4.0, peak_floor_kw=2.5, urgent=False
        )
        == 2.5
    )


def test_floor_equal_to_the_maximum_peak_resolves_to_the_maximum_peak():
    # Boundary case: peak_floor_kw == max_peak_kw. min(max(monthly, floor), max) must still
    # take this (either) value, not fall through to a `>`-only comparison that would miss
    # equality.
    assert (
        resolve_effective_peak_limit(
            monthly_peak_kw=0.5, max_peak_kw=4.0, peak_floor_kw=4.0, urgent=False
        )
        == 4.0
    )


def test_urgency_ignores_the_peak_floor_too():
    # Regression check -- row 1 (urgent) is unchanged by #754: still max_peak_kw regardless
    # of monthly peak or floor.
    assert (
        resolve_effective_peak_limit(
            monthly_peak_kw=0.1, max_peak_kw=4.0, peak_floor_kw=2.5, urgent=True
        )
        == 4.0
    )


def test_clamp_reduces_to_available_headroom():
    # 3 kW limit, 250 W margin -> target 2750 W. Baseline (net-charger) = 1000 W.
    # Headroom = (2750 - 1000) / 230 = 7.6 A -> floor 7 A.
    desired, tracker, force_stop = apply_peak_clamp(
        desired_current=32.0,
        baseline_w=1000.0,  # baseline 1000 W + a charging draw already flowing on both sides
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
        baseline_w=2900.0,
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
        baseline_w=1370.0,
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
        baseline_w=2900.0,
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
        baseline_w=2900.0,
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
        baseline_w=2900.0,
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
        baseline_w=2900.0,
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
        baseline_w=2900.0,
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
        baseline_w=500.0,
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
        baseline_w=0.0,
        effective_peak_limit_kw=4.0,
        tracker=tracker,
        now=0.0,
        **DEFAULTS,
    )
    assert desired == 6.0  # ample headroom -- clamp never raises the request


def test_debounce_first_reading_ever_applies_immediately():
    # No accepted baseline yet -- nothing to debounce against (issue #990).
    baseline_w, tracker = debounce_baseline_w(500.0, BaselineDebouncer(), debounce_cycles=2)
    assert baseline_w == 500.0
    assert tracker.accepted_w == 500.0
    assert tracker.pending_cycles == 0


def test_debounce_a_higher_baseline_reading_applies_immediately():
    # Higher baseline_w -> less headroom -- the safety-conservative direction always applies
    # immediately, same cycle it's read.
    tracker = BaselineDebouncer(accepted_w=500.0)
    baseline_w, tracker = debounce_baseline_w(800.0, tracker, debounce_cycles=2)
    assert baseline_w == 800.0
    assert tracker.accepted_w == 800.0
    assert tracker.pending_cycles == 0


def test_debounce_an_equal_baseline_reading_applies_immediately():
    tracker = BaselineDebouncer(accepted_w=500.0)
    baseline_w, tracker = debounce_baseline_w(500.0, tracker, debounce_cycles=2)
    assert baseline_w == 500.0
    assert tracker.pending_cycles == 0


def test_debounce_holds_a_lower_baseline_reading_until_it_persists():
    # Issue #990's actual failure scenario: a charger current step-down where the fast net
    # meter already reflects the drop but the slow-polled charger_power sensor still reports
    # the prior, higher value for one extra cycle -- baseline_w plunges (net_w - charger_w)
    # for that one cycle, inflating peak_headroom_a/solar_surplus_w. The clamp must not grant
    # that headroom increase on the very first low reading.
    tracker = BaselineDebouncer(accepted_w=500.0)
    baseline_w, tracker = debounce_baseline_w(-1500.0, tracker, debounce_cycles=2)
    assert baseline_w == 500.0  # holds the prior, safety-conservative value
    assert tracker.accepted_w == 500.0
    assert tracker.pending_cycles == 1


def test_debounce_accepts_a_lower_baseline_once_it_holds_for_the_debounce_window():
    # A genuine, sustained drop (e.g. real solar surplus) is accepted once it has held for
    # `debounce_cycles` consecutive readings -- not suppressed forever.
    tracker = BaselineDebouncer(accepted_w=500.0, pending_cycles=1)
    baseline_w, tracker = debounce_baseline_w(-1500.0, tracker, debounce_cycles=2)
    assert baseline_w == -1500.0
    assert tracker.accepted_w == -1500.0
    assert tracker.pending_cycles == 0


def test_debounce_a_worsening_reading_mid_pending_resets_the_pending_count():
    # The lower reading doesn't hold -- baseline_w recovers (or worsens further) before the
    # debounce window elapses. The stale pending count must not carry over once a
    # not-lower reading is accepted immediately.
    tracker = BaselineDebouncer(accepted_w=500.0, pending_cycles=1)
    baseline_w, tracker = debounce_baseline_w(500.0, tracker, debounce_cycles=2)
    assert baseline_w == 500.0
    assert tracker.pending_cycles == 0


def test_debounce_commits_the_newest_pending_value_not_the_one_that_started_the_count():
    # The count is "how many consecutive cycles has a below-accepted reading been seen", not
    # "has this exact value been stable" -- a still-dropping reading commits at whatever value
    # it has reached once the window elapses, not the first below-accepted value observed.
    tracker = BaselineDebouncer(accepted_w=500.0, pending_cycles=1)  # pending since -1500.0
    baseline_w, tracker = debounce_baseline_w(-4000.0, tracker, debounce_cycles=2)
    assert baseline_w == -4000.0
    assert tracker.accepted_w == -4000.0
    assert tracker.pending_cycles == 0
