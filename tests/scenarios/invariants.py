"""The shared per-cycle invariant set every scenario is judged by (ADR-0037, epic #996).
Test-only -- product code takes no dependency on this module (ADR-0037's Consequences).

An invariant earns a place here only if it compares the plant's *true* values -- which the
coordinator under test cannot see -- against a limit, never a value the clamp under test itself
produced (ADR-0037's invariant-oracle rule). Growing this set is deliberately incremental
(ADR-0037's Decision): the first two members are C4 (the grid supply ceiling) and R3 (the
effective peak limit, wherever it applies); a later scenario adds the next one it needs.

A scenario wires the invariants it needs into `ScenarioRunner.run`'s `judge` callback (see
`runner.py`) -- which ones apply, and against which limit, is the scenario's own call (R3 only
applies with the CapTar capability present and, in `Power`, its own option enabled -- C3, R17 --
which this module has no way to know on its own); this module only states each invariant's rule
and reports the first cycle that breaks it.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from tests.scenarios.runner import CycleTrace, format_trace

_CONTEXT_RADIUS = 2  # cycles of context preceding the violating one in a failure message.


class InvariantViolation(AssertionError):
    """Raised by `check_c4`/`check_r3` (and anything built on `_judge`) naming the first cycle
    of a scenario's trace that broke an invariant, with the surrounding cycles' context.
    Subclasses `AssertionError` so `pytest.raises`/`pytest.mark.xfail(raises=...)` catch it
    exactly like any other test assertion -- a scenario's own assertion IS the invariant set,
    judged here rather than restated per scenario."""


def _violation_message(
    label: str, limit_name: str, trace: list[CycleTrace], index: int, target_w: float
) -> str:
    t = trace[index]
    lo = max(0, index - _CONTEXT_RADIUS)
    hi = min(len(trace), index + _CONTEXT_RADIUS + 1)
    headroom_w = target_w - t.reading.true_import_w
    return (
        f"{label} breach at step {t.index}: true import {t.reading.true_import_w} W > "
        f"{limit_name} {target_w} W (headroom {headroom_w} W) -- commanded "
        f"{t.commanded_current_a} A, true draw {t.reading.true_draw_a} A, reported charger "
        f"{t.reading.reported_charger_w} W, active_mode {t.active_mode!r}, faulted {t.faulted}\n"
        f"{format_trace(trace[lo:hi], target_w=target_w)}"
    )


def _household_reaction_allowed(trace: list[CycleTrace], index: int, target_w: float) -> bool:
    """C4's own one-cycle reaction allowance: a breach on a step where the household load itself
    increased -- and is the sole cause of the breach -- is not a violation, since the previous
    control cycle's command could not have foreseen it (C4's own row,
    `docs/analysis/requirements.md#constraints`: "a sudden swing cannot trip the main fuse before
    the next control cycle reacts"). Narrowed to only the breach the change itself caused: a
    decrease is never exempted, and nor is an increase that would still have breached against the
    PREVIOUS cycle's household reading (`true_charger_w` unchanged, `household_w` rolled back one
    cycle) -- such a breach was there already and the change is not what "could not have [been]
    foreseen". Household load alone already above the limit while the charger draws 0 A is the
    same allowance's other named case -- there is no commanded current left to react with, so
    causation does not apply to it.

    R3's own criteria state the identical one-cycle bound (`docs/analysis/requirements.md#r3--
    captar-peak-protection`), not merely a borrowed allowance -- `check_r3` below composes this
    same function rather than restating it."""
    t = trace[index]
    household_increased = index > 0 and t.reading.household_w > trace[index - 1].reading.household_w
    caused_by_the_increase = index > 0 and (
        t.reading.true_charger_w + trace[index - 1].reading.household_w <= target_w
    )
    household_alone_above = t.reading.true_draw_a == 0.0
    return (household_increased and caused_by_the_increase) or household_alone_above


def _case_a_deferred(trace: list[CycleTrace], index: int) -> bool:
    """R3's case (a) (`docs/analysis/requirements.md#r3--captar-peak-protection`): the household
    baseline reading taken at `index` is deferred -- the most recently accepted one stands in its
    place -- when the current the System set on the previous control cycle differed from the one
    it set before that, since such a reading partly measures the System's own actuation rather
    than the household. Never two cycles running: case (a) does not apply on a cycle immediately
    following one it already deferred, which is what the recursive `not _case_a_deferred(...,
    index - 1)` term below encodes."""
    if index < 2:
        return False
    commanded_changed = trace[index - 1].commanded_current_a != trace[index - 2].commanded_current_a
    return commanded_changed and not _case_a_deferred(trace, index - 1)


def _deferred_reaction_allowed(trace: list[CycleTrace], index: int, target_w: float) -> bool:
    """R3's own allowance beyond the shared same-cycle one above: a household increase at
    `index - 1` whose own reading was itself deferred by case (a) (`_case_a_deferred`) reaches
    the clamp one control cycle later than usual, so the breach it causes lands at `index`
    rather than at `index - 1` -- R3's own criterion that "a [household increase large enough to
    breach the effective peak limit minus the safety margin] is deferred by at most one control
    cycle" (case (b) never defers a headroom-decreasing reading, and case (a) never defers two
    cycles in a row), just the one cycle the deferral itself already cost rather than a second
    one.

    Exempted only where the deferral is itself the breach's sole cause -- the same cause check
    the shared same-cycle allowance applies (`_household_reaction_allowed`): the reading the
    deferral stood in for was taken at `index - 2` (two cycles before the breach, one before the
    deferred cycle), so `index`'s true charger draw against THAT cycle's household reading must
    still clear the target. A household increase and a case-(a) deferral landing on the right
    cycles is not by itself proof the deferral is what caused the breach -- a command written
    from an over-granted current (a debounce bypass, a clamp defect) can land on those same
    cycles without the deferral contributing anything, and must not be hidden behind it.

    Case (b)'s deferral is deliberately not modelled here: R3's own criterion caps a breaching
    increase's deferral at one control cycle (case (b) never defers a headroom-*decreasing*
    reading, and case (a) never defers two cycles in a row), so no reading can ever reach a
    breaching headroom by way of case (b) alone and needs an allowance against this check."""
    if index < 2:
        return False
    previous = index - 1
    household_increased_at_previous = (
        trace[previous].reading.household_w > trace[previous - 1].reading.household_w
    )
    caused_by_the_deferral = (
        trace[index].reading.true_charger_w + trace[index - 2].reading.household_w <= target_w
    )
    return (
        household_increased_at_previous
        and _case_a_deferred(trace, previous)
        and caused_by_the_deferral
    )


def _grace_period_allowed(
    trace: list[CycleTrace],
    index: int,
    *,
    target_w: float,
    min_current_a: float,
    grace_period_s: float,
    control_interval_s: float,
) -> bool:
    """R3's own grace period (`docs/analysis/requirements.md#r3--captar-peak-protection`): once
    the clamp already holds at the minimum charging current, a continuous breach is sanctioned
    for the configured grace period before the clamp force-stops to 0 A -- "a momentary breach
    does not stop charging".

    Counted only on a cycle that BOTH draws the minimum current AND genuinely breaches
    (`true_import_w > target_w`) -- matching the product's own timer, which starts on the first
    REQUEST-side breaching cycle (`apply_peak_clamp`'s `is_breaching`,
    `engines/billing_protection.py` ~:176-181), never merely on the charger sitting at the
    minimum for some unrelated reason (Power's own target current, or a prior, already-ended
    breach) before a genuine breach even begins -- such cycles must not consume a grace budget
    they were never charged against.

    The run counted is the WHOLE contiguous stretch of such cycles ending at `index` -- it is
    never broken, or restarted, by a household change partway through it: R3's "continuously" is
    about true import staying over target, and `apply_peak_clamp`'s own timer does not reset on
    a household change either, whatever the household does meanwhile (a mid-run wiggle is still
    the same, continuing breach).

    The cap: `apply_peak_clamp` is evaluated once per control cycle and holds the command at
    `min_current_a` for every cycle its own timer has not yet reached `grace_period_s`; the
    number of commanded-minimum cycles before the force-stop command is the smallest integer `j`
    with `j * control_interval_s >= grace_period_s`, i.e. `ceil(grace_period_s /
    control_interval_s)`. The plant's one-cycle write lag shifts WHEN those commands are seen as
    true draw, including the force-stop's own 0 A, but shifts the whole window rather than adding
    a cycle to it, so the true-draw run is capped at that same number -- EXTENDED, though, by the
    run's own leading cycle(s) the product's timer could not yet have counted:

    - the charger already sitting at `min_current_a` on its own account (Power's own target
      current, not yet any clamp reaction) when a household jump lands on that same cycle --
      true draw happens to already equal `min_current_a` by coincidence, one cycle before the
      clamp's own reaction to the jump could possibly reach true draw (the plant's one-cycle
      write lag); that leading cycle is the shared same-cycle allowance's own cycle
      (`_household_reaction_allowed`), not a cycle the product's own timer has started on yet;
    - a case-(a) deferral (`_deferred_reaction_allowed`) delaying when a household increase
      reaches true draw by one control cycle delays, by that same cycle, when true draw first
      reaches the minimum and genuinely breaches -- which is one cycle later than the product's
      own request-side timer (gated on the request, not the lagged true draw) may already have
      started counting from.

    At most two such leading cycles can stack (a same-cycle reaction, then one cycle later a
    deferred one) -- `_household_reaction_allowed`/`_deferred_reaction_allowed` are checked,
    forwards from the run's own first cycle, for up to two cycles, and the cap is extended by
    one for each that holds, stopping at the first that does not: a cycle deeper in the run that
    merely happens to satisfy one of those checks is not a leading cycle the product's timer
    missed, and must not extend the cap (the mid-run-wiggle case above only ever reaches this
    point because the run is never broken on it; its own household change is never close enough
    to the run's start to extend anything here).

    A 0 A cycle (the force-stop itself, or any other cycle the charger is not drawing the
    minimum) ends the counted run: a faithful reading of R3's "continuously", not a gap -- the
    force-stop cycle's own 0 A draw is a genuine, if momentary, end to the breach, so a breach
    that resumes immediately afterward is a fresh occurrence re-arming a fresh, fully-budgeted
    grace period -- exactly as a later, unrelated occurrence would -- rather than the same breach
    continuing through it. This also matches the product's own `apply_peak_clamp`, which resets
    `tracker.breached_since` to `None` on any non-breaching cycle, including its own force-stop
    write -- the oracle's reset-on-0A behaviour is read off the same mechanism it judges (from
    the trace alone, never the product function itself, per ADR-0037), not an independent design
    choice that happens to agree with it."""

    def _breaching_at_minimum(i: int) -> bool:
        t = trace[i]
        return t.reading.true_draw_a == min_current_a and t.reading.true_import_w > target_w

    if not _breaching_at_minimum(index):
        return False

    run_length = 1
    i = index - 1
    while i >= 0 and _breaching_at_minimum(i):
        run_length += 1
        i -= 1
    run_start = i + 1

    extension = 0
    for offset in range(min(2, run_length)):
        leading_index = run_start + offset
        if _household_reaction_allowed(
            trace, leading_index, target_w
        ) or _deferred_reaction_allowed(trace, leading_index, target_w):
            extension += 1
        else:
            break

    max_cycles = math.ceil(grace_period_s / control_interval_s) + extension
    return run_length <= max_cycles


ReactionAllowed = Callable[[list[CycleTrace], int], bool]


def _judge(
    trace: list[CycleTrace],
    *,
    target_w: float,
    label: str,
    limit_name: str,
    reaction_allowed: ReactionAllowed,
) -> None:
    for index, t in enumerate(trace):
        if t.reading.true_import_w <= target_w:
            continue
        if reaction_allowed(trace, index):
            continue
        raise InvariantViolation(_violation_message(label, limit_name, trace, index, target_w))


def check_c4(trace: list[CycleTrace], *, ceiling_w: float) -> None:
    """C4 (`docs/analysis/requirements.md#constraints`): true import never exceeds the grid
    supply ceiling on any step, except the reaction allowance that row itself states --
    `_household_reaction_allowed` above; C4 has no further allowance of its own. Unconditional:
    C4 "applies in every mode and under every capability declaration" (C4's own row), so a
    scenario always wires this one in."""
    _judge(
        trace,
        target_w=ceiling_w,
        label="C4",
        limit_name="grid supply ceiling",
        reaction_allowed=lambda t, index: _household_reaction_allowed(t, index, ceiling_w),
    )


def check_r3(
    trace: list[CycleTrace],
    *,
    effective_peak_limit_w: float,
    min_current_a: float,
    grace_period_s: float,
    control_interval_s: float,
) -> None:
    """R3 (`docs/analysis/requirements.md#r3--captar-peak-protection`): true import never
    exceeds the effective peak limit minus its safety margin -- `effective_peak_limit_w` is that
    target, resolved by the caller from R3's criteria and the entry's own options alone, never by
    calling a product function (ADR-0037's invariant-oracle rule: the oracle must be independent
    of the code it judges). Only wired in by a scenario where R3 applies at all (CapTar present,
    and in `Power` its own option enabled -- C3, R17); this invariant does not gate on that
    itself, since it has no view of the entry's capabilities.

    Three allowances, computed from the trace and `min_current_a`/`grace_period_s`/
    `control_interval_s` alone -- none of them C4's to share beyond the first:

    - the same-cycle household-change allowance C4 also has (`_household_reaction_allowed`) --
      R3's own criteria state the identical one-cycle bound C4's "cannot trip the main fuse
      before the next control cycle reacts" row does, not merely a borrowed one;
    - one cycle further, when that same-cycle reading was itself deferred by R3's case (a)
      (`_deferred_reaction_allowed`) -- R3's own criterion that a breaching increase "is deferred
      by at most one control cycle" (case (b) never defers a headroom-decreasing reading, and
      case (a) never defers two cycles in a row), since the deferral itself already spent the
      first cycle. Gated by the same cause check as the allowance above, against the reading the
      deferral stood in for, so an over-grant from something other than the deferral itself (a
      debounce bypass, a clamp defect) cannot hide behind it. Case (b) needs no allowance here,
      per that function's own docstring;
    - the grace period at the minimum charging current (`_grace_period_allowed`) -- R3's own
      stop condition rides out a continuous breach for the configured grace period once already
      at the minimum current, capped at `ceil(grace_period_s / control_interval_s)` consecutive
      cycles that are both at the minimum and genuinely breaching, extended by the run's own
      leading cycle(s) the product's timer could not yet have counted (that function's own
      docstring derives both the cap and the extension from `apply_peak_clamp`'s timer).
    """

    def _r3_reaction_allowed(t: list[CycleTrace], index: int) -> bool:
        return (
            _household_reaction_allowed(t, index, effective_peak_limit_w)
            or _deferred_reaction_allowed(t, index, effective_peak_limit_w)
            or _grace_period_allowed(
                t,
                index,
                target_w=effective_peak_limit_w,
                min_current_a=min_current_a,
                grace_period_s=grace_period_s,
                control_interval_s=control_interval_s,
            )
        )

    _judge(
        trace,
        target_w=effective_peak_limit_w,
        label="R3",
        limit_name="effective peak limit",
        reaction_allowed=_r3_reaction_allowed,
    )


Invariant = Callable[[list[CycleTrace]], None]


def judge_all(trace: list[CycleTrace], invariants: list[Invariant]) -> None:
    """Run every invariant in `invariants` against `trace`, in order -- the first one that raises
    wins, and that is the ONLY one that gets to report: a cycle that would break more than one
    invariant is reported under whichever one appears earlier in `invariants`, and the others are
    never even evaluated against it. A scenario wiring more than one invariant can build
    `ScenarioRunner.run`'s own `judge` callback from this, composing its invariant set in one
    place rather than chaining calls itself -- though it may compose `judge` by hand instead
    (T1's own `judge`, which composes a harness-only mode guard ahead of `check_c4`). A scenario
    wiring both C4 and R3 therefore lists C4 first: R3 only ever applies where C4 does too (R3
    needs the CapTar capability; C4 runs regardless, C3), so a cycle that breaks both is always a
    C4 violation first and foremost -- the grid supply ceiling is the harder, unconditional limit
    (C3's own row) -- and ordering R3 first would misreport it as R3's instead
    (`test_invariants.py`'s own ordering tests prove the list decides it, not any precedence
    baked into either check)."""
    for invariant in invariants:
        invariant(trace)
