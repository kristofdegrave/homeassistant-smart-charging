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

_CONTEXT_RADIUS = 2  # cycles of context either side of the violating one in a failure message.


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
    """The one-cycle reaction allowance C4 and R3 share: a breach on a step where the household
    load itself increased -- and is the sole cause of the breach -- is not a violation, since the
    previous control cycle's command could not have foreseen it (C4's own row,
    `docs/analysis/requirements.md#constraints`: "a sudden swing cannot trip the main fuse before
    the next control cycle reacts"; R3's own criteria, `#r3--captar-peak-protection`, defer such
    a reading by exactly the same one cycle). Narrowed to only the breach the change itself
    caused: a decrease is never exempted, and nor is an increase that would still have breached
    against the PREVIOUS cycle's household reading (`true_charger_w` unchanged, `household_w`
    rolled back one cycle) -- such a breach was there already and the change is not what
    "could not have [been] foreseen". Household load alone already above the limit while the
    charger draws 0 A is the same allowance's other named case -- there is no commanded current
    left to react with, so causation does not apply to it."""
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


def _deferred_reaction_allowed(trace: list[CycleTrace], index: int) -> bool:
    """R3's own allowance beyond the shared same-cycle one above: a household increase at
    `index - 1` whose own reading was itself deferred by case (a) (`_case_a_deferred`) reaches
    the clamp one control cycle later than usual, so the breach it causes lands at `index`
    rather than at `index - 1` -- still "deferred by at most one control cycle" overall (R3's own
    criteria), just the one cycle the deferral itself already cost rather than a second one.
    Case (b)'s deferral is deliberately not modelled here: it only ever defers a headroom-
    *increasing* reading (more conservative, never less) -- it can delay the clamp granting
    extra current, never cause it to under-react to an increase, so it cannot itself produce a
    sanctioned over-limit breach and needs no allowance against this check."""
    if index < 2:
        return False
    previous = index - 1
    household_increased_at_previous = (
        trace[previous].reading.household_w > trace[previous - 1].reading.household_w
    )
    return household_increased_at_previous and _case_a_deferred(trace, previous)


def _grace_period_allowed(
    trace: list[CycleTrace],
    index: int,
    *,
    min_current_a: float,
    grace_period_s: float,
    control_interval_s: float,
) -> bool:
    """R3's own grace period (`docs/analysis/requirements.md#r3--captar-peak-protection`): once
    the clamp already holds at the minimum charging current, a continuous breach is sanctioned
    for the configured grace period before the clamp force-stops to 0 A -- "a momentary breach
    does not stop charging". Counted on `true_draw_a` (ground truth), never the command, so a
    scenario cannot engineer the allowance by writing `min_current_a` without actually drawing
    it. The plant's true draw lags the command it is read from by one cycle (`plant.py`), so the
    breach the grace-period hold itself produced is still on the trace for one cycle after the
    grace period elapses and the clamp's 0 A write fires -- that write has not yet reached true
    draw -- hence the `+ 1` below."""
    if trace[index].reading.true_draw_a != min_current_a:
        return False
    run_length = 1
    i = index - 1
    while i >= 0 and trace[i].reading.true_draw_a == min_current_a:
        run_length += 1
        i -= 1
    max_cycles = math.floor(grace_period_s / control_interval_s) + 1
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
      (`_deferred_reaction_allowed`) -- still "deferred by at most one control cycle" overall,
      since the deferral itself already spent the first cycle. Case (b) needs no allowance here,
      per that function's own docstring;
    - the grace period at the minimum charging current (`_grace_period_allowed`) -- R3's own
      stop condition rides out a continuous breach for the configured grace period once already
      at the minimum current, plus the one further cycle the plant's lag costs the 0 A write
      that ends it.
    """

    def _r3_reaction_allowed(t: list[CycleTrace], index: int) -> bool:
        return (
            _household_reaction_allowed(t, index, effective_peak_limit_w)
            or _deferred_reaction_allowed(t, index)
            or _grace_period_allowed(
                t,
                index,
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
    never even evaluated against it. `ScenarioRunner.run`'s own `judge` callback is normally built
    from this, so a scenario composes its invariant set in one place rather than chaining calls
    itself. A scenario wiring both C4 and R3 therefore lists C4 first: R3 only ever applies
    where C4 does too (R3 needs the CapTar capability; C4 runs regardless, C3), so a cycle that
    breaks both is always a C4 violation first and foremost -- the grid supply ceiling is the
    harder, unconditional limit (C3's own row) -- and ordering R3 first would misreport it as
    R3's instead (`test_invariants.py`'s own ordering test proves this)."""
    for invariant in invariants:
        invariant(trace)
