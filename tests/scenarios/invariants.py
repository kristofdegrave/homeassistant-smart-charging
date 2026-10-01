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
        f"{format_trace(trace[lo:hi])}"
    )


def _reaction_allowed(trace: list[CycleTrace], index: int) -> bool:
    """The reaction allowance both invariants below share: a breach on a step where the
    household load itself changed is not a violation -- the previous control cycle's command
    could not have foreseen it (C4's own row, `docs/analysis/requirements.md#constraints`:
    "a sudden swing cannot trip the main fuse before the next control cycle reacts"; R3's own
    criteria, `#r3--captar-peak-protection`, defer such a reading by exactly the same one
    cycle). Household load alone already above the limit while the charger draws 0 A is the
    same allowance's other named case -- there is no commanded current left to react with."""
    t = trace[index]
    household_changed = index > 0 and t.reading.household_w != trace[index - 1].reading.household_w
    household_alone_above = t.reading.true_draw_a == 0.0
    return household_changed or household_alone_above


def _judge(trace: list[CycleTrace], *, target_w: float, label: str, limit_name: str) -> None:
    for index, t in enumerate(trace):
        if t.reading.true_import_w <= target_w:
            continue
        if _reaction_allowed(trace, index):
            continue
        raise InvariantViolation(_violation_message(label, limit_name, trace, index, target_w))


def check_c4(trace: list[CycleTrace], *, ceiling_w: float) -> None:
    """C4 (`docs/analysis/requirements.md#constraints`): true import never exceeds the grid
    supply ceiling on any step, except the reaction allowance that row itself states --
    `_reaction_allowed` above. Unconditional: C4 "applies in every mode and under every
    capability declaration" (C4's own row), so a scenario always wires this one in."""
    _judge(trace, target_w=ceiling_w, label="C4", limit_name="grid supply ceiling")


def check_r3(trace: list[CycleTrace], *, effective_peak_limit_w: float) -> None:
    """R3 (`docs/analysis/requirements.md#r3--captar-peak-protection`): true import never
    exceeds the effective peak limit minus its safety margin -- `effective_peak_limit_w` is
    that target, already resolved by the caller from the entry's own options the same way the
    coordinator resolves it (`resolve_monthly_peak_operand`/`resolve_effective_peak_limit`,
    `engines/billing_protection.py`), never restated here. Only wired in by a scenario where R3
    applies at all (CapTar present, and in `Power` its own option enabled -- C3, R17); this
    invariant does not gate on that itself, since it has no view of the entry's capabilities.

    The reaction allowance is the same one C4 uses: R3's own criteria defer a household-driven
    reading by at most one control cycle before the accepted baseline catches up, exactly
    mirroring C4's "the next control cycle reacts" bound. R3's own grace-period/deferral
    mechanics beyond that one-cycle bound (the sustained-breach-before-force-stop allowance, the
    headroom-increase debounce) are not modeled here -- no scenario wired into this invariant yet
    needs them; a later one that does grows this function the same way the set grows (ADR-0037)."""
    _judge(
        trace,
        target_w=effective_peak_limit_w,
        label="R3",
        limit_name="effective peak limit",
    )


Invariant = Callable[[list[CycleTrace]], None]


def judge_all(trace: list[CycleTrace], invariants: list[Invariant]) -> None:
    """Run every invariant in `invariants` against `trace`, in order -- the first one that
    raises wins; `ScenarioRunner.run`'s own `judge` callback is normally built from this, so a
    scenario composes its invariant set in one place rather than chaining calls itself."""
    for invariant in invariants:
        invariant(trace)
