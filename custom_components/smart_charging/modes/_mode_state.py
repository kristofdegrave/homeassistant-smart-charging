"""Shared frozen state-dataclass base and helpers for the mode engines (E1, issue #507).

Every mode engine (`solar.py`, `solar_only.py`, `captar.py`) threads a small frozen
dataclass of exactly the same shape -- `phase` + `phase_started_at` -- and repeats the
same cooldown-elapsed expression and "unknown phase" `ValueError`. This module factors
both out without coupling the engines' own transition logic together (NF2, same
rationale as `_phase.py`'s own docstring): each module still defines its own `step()`
and its own transition rules; only the state shape and these two small expressions
are shared.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self

from ._phase import Phase


@dataclass(frozen=True)
class ModeState:
    """Base shape threaded by every mode engine. `now` (seconds, monotonic) is always
    injected into `step()`, never read from this state."""

    phase: Phase
    phase_started_at: float = 0.0

    @classmethod
    def idle(cls) -> Self:
        return cls(phase=Phase.IDLE)


def cooldown_done(state: ModeState, now: float, cooldown_minutes: float) -> bool:
    """True once a Cooldown phase has elapsed `cooldown_minutes` -- or immediately for
    Idle, which is never itself cooling down."""
    if state.phase == Phase.IDLE:
        return True
    return now - state.phase_started_at >= cooldown_minutes * 60


def unknown_phase_error(state: ModeState) -> ValueError:
    """The `unknown <ClassName>.phase: ...` message every engine's `step()` raises for
    a phase its own state machine doesn't recognize -- `type(state).__name__` keeps the
    class name in the message specific to the calling engine's own state type."""
    return ValueError(f"unknown {type(state).__name__}.phase: {state.phase!r}")
