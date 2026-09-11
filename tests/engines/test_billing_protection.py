"""Plain-pytest tests for the Billing-Protection Engine (E5 -- UC03, R3, R5).

Row 1 (deadline urgency) is added by this suite -- row 2 (min(max(operand, floor), max),
#754/R3) is only reached when urgent=False. The operand merge (resolve_monthly_peak_operand,
ADR-0032) is covered separately, both alone and run through the row-2 clamp.

Also `debounce_baseline_w`, which decides which household-baseline reading the R3 clamp is
allowed to solve from (R3's two deferral cases, ADR-0039): its direction rules and the
command-changed gate one call at a time, then a closed-loop section at the end of the file
that drives it together with `apply_peak_clamp` against a lagging charger reading."""

from collections.abc import Callable

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
    baseline_w, tracker = debounce_baseline_w(
        500.0, BaselineDebouncer(), debounce_cycles=2, command_changed=False
    )
    assert baseline_w == 500.0
    assert tracker.accepted_w == 500.0
    assert tracker.pending_cycles == 0


def test_debounce_a_higher_baseline_reading_applies_immediately():
    # Higher baseline_w -> less headroom -- the safety-conservative direction always applies
    # immediately, same cycle it's read.
    tracker = BaselineDebouncer(accepted_w=500.0)
    baseline_w, tracker = debounce_baseline_w(
        800.0, tracker, debounce_cycles=2, command_changed=False
    )
    assert baseline_w == 800.0
    assert tracker.accepted_w == 800.0
    assert tracker.pending_cycles == 0


def test_debounce_an_equal_baseline_reading_applies_immediately():
    tracker = BaselineDebouncer(accepted_w=500.0)
    baseline_w, tracker = debounce_baseline_w(
        500.0, tracker, debounce_cycles=2, command_changed=False
    )
    assert baseline_w == 500.0
    assert tracker.pending_cycles == 0


def test_debounce_holds_a_lower_baseline_reading_until_it_persists():
    # Issue #990's actual failure scenario: a charger current step-down where the fast net
    # meter already reflects the drop but the slow-polled charger_power sensor still reports
    # the prior, higher value for one extra cycle -- baseline_w plunges (net_w - charger_w)
    # for that one cycle, inflating peak_headroom_a/solar_surplus_w. The clamp must not grant
    # that headroom increase on the very first low reading.
    tracker = BaselineDebouncer(accepted_w=500.0)
    baseline_w, tracker = debounce_baseline_w(
        -1500.0, tracker, debounce_cycles=2, command_changed=False
    )
    assert baseline_w == 500.0  # holds the prior, safety-conservative value
    assert tracker.accepted_w == 500.0
    assert tracker.pending_cycles == 1


def test_debounce_accepts_a_lower_baseline_once_it_holds_for_the_debounce_window():
    # A genuine, sustained drop (e.g. real solar surplus) is accepted once it has held for
    # `debounce_cycles` consecutive readings -- not suppressed forever.
    tracker = BaselineDebouncer(accepted_w=500.0, pending_cycles=1)
    baseline_w, tracker = debounce_baseline_w(
        -1500.0, tracker, debounce_cycles=2, command_changed=False
    )
    assert baseline_w == -1500.0
    assert tracker.accepted_w == -1500.0
    assert tracker.pending_cycles == 0


def test_debounce_a_worsening_reading_mid_pending_resets_the_pending_count():
    # The lower reading doesn't hold -- baseline_w recovers (or worsens further) before the
    # debounce window elapses. The stale pending count must not carry over once a
    # not-lower reading is accepted immediately.
    tracker = BaselineDebouncer(accepted_w=500.0, pending_cycles=1)
    baseline_w, tracker = debounce_baseline_w(
        500.0, tracker, debounce_cycles=2, command_changed=False
    )
    assert baseline_w == 500.0
    assert tracker.pending_cycles == 0


def test_debounce_commits_the_newest_pending_value_not_the_one_that_started_the_count():
    # The count is "how many consecutive cycles has a below-accepted reading been seen", not
    # "has this exact value been stable" -- a still-dropping reading commits at whatever value
    # it has reached once the window elapses, not the first below-accepted value observed.
    tracker = BaselineDebouncer(accepted_w=500.0, pending_cycles=1)  # pending since -1500.0
    baseline_w, tracker = debounce_baseline_w(
        -4000.0, tracker, debounce_cycles=2, command_changed=False
    )
    assert baseline_w == -4000.0
    assert tracker.accepted_w == -4000.0
    assert tracker.pending_cycles == 0


def test_debounce_discards_a_higher_reading_taken_on_the_commands_own_step():
    # ADR-0039: the step-UP transient. A current step-up makes net_w rise on the cycle it
    # happens while charger_w still reports the previous draw, so the baseline reads high for
    # reasons that have nothing to do with the household. Without the gate this was committed
    # immediately by the "at or above" rule and then actuated.
    tracker = BaselineDebouncer(accepted_w=986.0)
    baseline_w, tracker = debounce_baseline_w(
        2310.0, tracker, debounce_cycles=2, command_changed=True
    )
    assert baseline_w == 986.0
    assert tracker.accepted_w == 986.0


def test_debounce_discards_a_lower_reading_taken_on_the_commands_own_step():
    # The gate is direction-blind (ADR-0039): the step-DOWN transient is discarded by the same
    # rule rather than merely counted towards the pending window.
    tracker = BaselineDebouncer(accepted_w=986.0)
    baseline_w, tracker = debounce_baseline_w(
        -339.0, tracker, debounce_cycles=2, command_changed=True
    )
    assert baseline_w == 986.0
    assert tracker.pending_cycles == 0  # not advanced -- a discarded reading is a non-observation


def test_debounce_carries_a_pending_count_through_a_discarded_cycle():
    # A genuine sustained drop that straddles a step still needs `debounce_cycles` readings
    # taken while the command held steady -- the discarded cycle neither advances nor resets it.
    tracker = BaselineDebouncer(accepted_w=986.0, pending_cycles=1)
    baseline_w, tracker = debounce_baseline_w(
        -1500.0, tracker, debounce_cycles=2, command_changed=True
    )
    assert baseline_w == 986.0
    assert tracker.pending_cycles == 1
    baseline_w, tracker = debounce_baseline_w(
        -1500.0, tracker, debounce_cycles=2, command_changed=False
    )
    assert baseline_w == -1500.0  # the steady-command reading completes the window


def test_debounce_accepts_the_first_ever_reading_even_on_a_step():
    # Nothing to fall back on -- the gate must not strand the tracker with no accepted value.
    baseline_w, tracker = debounce_baseline_w(
        986.0, BaselineDebouncer(), debounce_cycles=2, command_changed=True
    )
    assert baseline_w == 986.0
    assert tracker.accepted_w == 986.0


def test_debounce_case_a_never_defers_two_consecutive_cycles():
    # R3: "never on two consecutive cycles, case (a) not applying at all on a control cycle
    # immediately following one it deferred". Without this cap a mode whose own request moves
    # every cycle (Solar tracking a drifting surplus) makes every reading a command-changed one
    # and freezes the baseline indefinitely -- the bound R3 states would not hold.
    tracker = BaselineDebouncer(accepted_w=986.0)
    baseline_w, tracker = debounce_baseline_w(
        2310.0, tracker, debounce_cycles=2, command_changed=True
    )
    assert baseline_w == 986.0  # deferred
    baseline_w, tracker = debounce_baseline_w(
        2310.0, tracker, debounce_cycles=2, command_changed=True
    )
    assert baseline_w == 2310.0, "case (a) deferred two cycles running"
    assert tracker.accepted_w == 2310.0


def test_debounce_defers_a_breaching_increase_by_exactly_one_cycle():
    # R3: "A household increase large enough to breach ... is deferred by at most one control
    # cycle". A headroom-DECREASING reading arriving on a command-changed cycle is the only way
    # a breach can be deferred at all -- case (b) never defers one.
    tracker = BaselineDebouncer(accepted_w=986.0)
    baseline_w, tracker = debounce_baseline_w(
        3600.0, tracker, debounce_cycles=2, command_changed=True
    )
    assert baseline_w == 986.0  # the breach is not seen this cycle
    baseline_w, tracker = debounce_baseline_w(
        3600.0, tracker, debounce_cycles=2, command_changed=False
    )
    assert baseline_w == 3600.0  # and is acted on the very next one


def test_debounce_worst_case_interleave_never_exceeds_three_deferrals():
    # R3: "No run of consecutive deferrals exceeds 3 control cycles. That worst case needs case
    # (a) to apply on alternate cycles throughout a case-(b) sequence." Built from a clean
    # tracker rather than a seeded pending count, so it demonstrates the bound itself.
    tracker = BaselineDebouncer(accepted_w=986.0)
    accepted_on = None
    for cycle in range(6):
        baseline_w, tracker = debounce_baseline_w(
            200.0, tracker, debounce_cycles=2, command_changed=True
        )
        if baseline_w == 200.0:
            accepted_on = cycle
            break
    assert accepted_on == 3, f"accepted on cycle {accepted_on}, i.e. {accepted_on} deferrals"


# --- Closed-loop stability (issue #1034, ADR-0039) ---------------------------------------
# The tests above exercise debounce_baseline_w one call at a time, against a baseline_w the
# test supplies. These drive it in the feedback loop it actually sits in: the clamp's own
# output becomes the charger's draw, which becomes the next cycle's readings. That is the
# only arrangement in which the step-UP transient debounce_baseline_w's docstring accepts as
# "one extra cycle of understated headroom" can be observed for what it is -- the transient is
# itself actuated, so it manufactures the next one.
#
# Placement: ADR-0009's plain-pytest tier, since this calls only pure functions and imports no
# HA. ADR-0039's Consequences record it as "a tier-1 stand-in, not a substitute" for ADR-0037's
# scenario/timeline tier -- when that tier exists, a lag-driven oscillation scenario belongs
# there and this block can go.

_LOOP_VOLTAGE = 220.82  # measured, from the live install in #1034
_LOOP_HOUSE_W = 986.0  # steady household baseline, the term the clamp is meant to solve around
_LOOP_LIMIT_KW = 4.0
_LOOP_MAX_A = 32.0


_LOOP_MIN_A = 6.0
_LOOP_SAFETY_MARGIN_W = 250.0
_LOOP_TARGET_W = _LOOP_LIMIT_KW * 1000 - _LOOP_SAFETY_MARGIN_W


def _closed_loop(cycles: int, house_w: Callable[[int], float]) -> list[tuple[float, float]]:
    """(commanded_a, net_w) per cycle, with Captar's own always-max_a request as the input.

    Models two properties of the real install and nothing else: the net meter reflects a change
    in charger draw on the cycle it happens, while the charger's own power sensor (slow Modbus
    poll) still reports the previous cycle's value. `house_w` scripts the only exogenous term,
    so any movement the script does not explain originates inside the clamp.

    `command_changed` is derived here the same way the coordinator derives it -- this cycle's
    commanded current differs from the one the lagging sensor is still reporting.
    """
    commanded = 6.0
    previous = commanded
    debouncer = BaselineDebouncer()
    breach = PeakBreachTracker()
    history: list[tuple[float, float]] = []
    for cycle in range(cycles):
        net_w = house_w(cycle) + commanded * _LOOP_VOLTAGE
        charger_w = previous * _LOOP_VOLTAGE  # one cycle behind the true draw
        baseline_w, debouncer = debounce_baseline_w(
            net_w - charger_w,
            debouncer,
            debounce_cycles=2,
            command_changed=commanded != previous,
        )
        desired, breach, _ = apply_peak_clamp(
            _LOOP_MAX_A,
            baseline_w,
            voltage=_LOOP_VOLTAGE,
            effective_peak_limit_kw=_LOOP_LIMIT_KW,
            safety_margin_w=_LOOP_SAFETY_MARGIN_W,
            min_a=_LOOP_MIN_A,
            grace_period_s=120.0,
            tracker=breach,
            now=float(cycle * 10),
        )
        previous = commanded
        commanded = apply_floor_cap(desired, min_a=_LOOP_MIN_A, max_a=_LOOP_MAX_A)
        history.append((commanded, net_w))
    return history


def test_closed_loop_settles_when_the_charger_power_reading_lags_a_step():
    # Issue #1034: with a steady household baseline and a steady peak limit, the commanded
    # current must reach a value and stay there. Nothing in the simulated world moves, so a
    # current that keeps changing is the clamp oscillating against its own actuation. Before
    # ADR-0039 this ran [12, 6, 6, 12, 6, 6, ...] indefinitely -- a 3-cycle limit cycle.
    history = _closed_loop(12, lambda _cycle: _LOOP_HOUSE_W)
    currents = [a for a, _ in history]
    assert currents[-4:] == [currents[-1]] * 4, f"did not settle: {currents}"
    # Pin the settled value, not just that it stopped moving: an over-conservative or stuck
    # current would satisfy the assertion above. floor((3750 - 986) / 220.82) = 12 A.
    assert currents[-1] == 12.0, f"settled on the wrong current: {currents}"
    # And the safety property the whole clamp exists for, not only the stability one.
    assert all(net <= _LOOP_TARGET_W for _a, net in history), f"exceeded target: {history}"


def test_closed_loop_still_reacts_to_a_real_household_step_on_the_cycle_it_happens():
    # ADR-0039's reason for discarding on the command's own step rather than debouncing both
    # directions (Option B): a household load arriving while the command is steady is a
    # trustworthy reading, so the clamp must still act on it in the same cycle rather than one
    # later. `target_w` is 4.0 kW - 250 W = 3750 W.
    step_cycle = 6
    history = _closed_loop(12, lambda cycle: _LOOP_HOUSE_W if cycle < step_cycle else 2200.0)
    before = history[step_cycle - 1][0]
    assert history[step_cycle][0] < before, f"did not react on the step cycle: {history}"
    # `net_w` on the step cycle itself is unavoidably household + whatever the charger was
    # already drawing -- the clamp commands the charger, not the house, so the reading it
    # reacts to is the one that already exceeded. What it owes is that the reaction lands
    # within that same cycle, so every LATER cycle is back under target.
    assert all(net <= _LOOP_TARGET_W for _a, net in history[step_cycle + 1 :]), (
        f"stayed over: {history}"
    )
    settled = [a for a, _ in history[-4:]]
    assert settled == [settled[0]] * 4, f"did not re-settle after the step: {history}"
