"""The shared per-cycle invariant set every scenario is judged by (ADR-0037, epic #996).
Test-only -- product code takes no dependency on this module (ADR-0037's Consequences).

An invariant earns a place here only if it compares the plant's *true* values -- which the
coordinator under test cannot see -- against a limit, never a value the clamp under test itself
produced (ADR-0037's invariant-oracle rule). Growing this set is deliberately incremental
(ADR-0037's Decision): the first member is C4 (the grid supply ceiling); R3 (the effective peak
limit, wherever it applies) and further members follow as later scenarios need them.

A scenario wires the invariants it needs into `ScenarioRunner.run`'s `judge` callback (see
`runner.py`) -- which ones apply, and against which limit, is the scenario's own call; this
module only states each invariant's rule and reports the first cycle that breaks it.
"""

from __future__ import annotations

from collections.abc import Callable

from tests.scenarios.runner import CycleTrace, format_trace

_CONTEXT_RADIUS = 2  # cycles of context preceding the violating one in a failure message.


class InvariantViolation(AssertionError):
    """Raised by `check_c4` (and anything built on `_judge`) naming the first cycle
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
    causation does not apply to it."""
    t = trace[index]
    household_increased = index > 0 and t.reading.household_w > trace[index - 1].reading.household_w
    caused_by_the_increase = index > 0 and (
        t.reading.true_charger_w + trace[index - 1].reading.household_w <= target_w
    )
    household_alone_above = t.reading.true_draw_a == 0.0
    return (household_increased and caused_by_the_increase) or household_alone_above


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


Invariant = Callable[[list[CycleTrace]], None]


def judge_all(trace: list[CycleTrace], invariants: list[Invariant]) -> None:
    """Run every invariant in `invariants` against `trace`, in order -- the first one that raises
    wins, and that is the ONLY one that gets to report: a cycle that would break more than one
    invariant is reported under whichever one appears earlier in `invariants`, and the others are
    never even evaluated against it. A scenario wiring more than one invariant can build
    `ScenarioRunner.run`'s own `judge` callback from this, composing its invariant set in one
    place rather than chaining calls itself -- though it may compose `judge` by hand instead
    (T1's own `judge`, which composes a harness-only mode guard ahead of `check_c4`). When a
    scenario wires more than one invariant, list the harder, unconditional limit
    first -- C4 (the grid supply ceiling, in force in every mode and under every capability
    declaration) ahead of any narrower, conditionally-applicable one -- so a cycle that breaks
    both is reported under the limit that always applies, not a narrower one that happens to
    apply too (`test_invariants.py`'s own ordering tests prove the list decides it, not any
    precedence baked into an individual check)."""
    for invariant in invariants:
        invariant(trace)
