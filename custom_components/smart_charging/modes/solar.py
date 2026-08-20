"""Solar charging-mode engine (E1 -- UC01). Pure -- no HA imports (ADR-0006/0009).

State machine: Idle -> [Debouncing] -> Charging -> Hold -> Cooldown, per UC01's state
model, MINUS the SocReached phase UC01's own diagram draws -- that transition is
entirely the coordinator's responsibility (M1), not this module's (see design doc
§5's "Where the SOC gate itself lives"): a mode "has no opinion on why the limit is
where it is" (R7), so it is never told SOC was reached at all -- the coordinator
simply stops calling step() and holds this state at idle() for as long as the gate
holds. State is a small frozen dataclass threaded by the coordinator -- this module
holds nothing itself; `now` (seconds, monotonic) is always injected.

`Debouncing` (R11/UC01 2b, issue #757) is a sub-state of Idle: `has_charged` is the
coordinator's own has-charged flag, read-only here -- this module has no opinion on
*when* that flag is set (the coordinator flips it after observing a fresh
Idle/Debouncing -> Charging transition) or *why* it's cleared (disconnect/restart,
never a mode switch or reaching the SOC limit -- both the coordinator's concern,
same "has no opinion" shape as R7's SOC limit above). Before the flag is set, a
threshold crossing while Idle starts charging immediately; once set, it must hold
for `debounce_minutes` first. A resume straight from `Cooldown` with the threshold
already met is exempt -- it never passes through `Idle` at all, so there is no
crossing to debounce.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..const import ROUND_UP
from ._amp_step import round_amp_step
from ._mode_state import ModeState, cooldown_done, unknown_phase_error
from ._phase import Phase


@dataclass(frozen=True)
class SolarState(ModeState):
    """No fields of its own -- `@dataclass(frozen=True)` is re-declared (rather than a
    bare `class SolarState(ModeState): pass`) so `SolarState` keeps its own frozen
    `__setattr__`/`__eq__`/`__hash__`, exact dataclass parity with the prior shape."""


def step(
    surplus_w: float,
    state: SolarState,
    now: float,
    start_threshold_w: float,
    min_a: float,
    hold_minutes: float,
    cooldown_minutes: float,
    debounce_minutes: float,
    has_charged: bool = False,
    voltage: float = 230.0,
) -> tuple[float, SolarState]:
    """Return (desired_current, next_state) for one control cycle (UC01).

    `min_a` is used to decide grid-fallback vs. hold/stop transitions (R1's own
    set-point rule reads the minimum); the floor/cap invariant itself is still
    applied once, downstream, by the coordinator's E8 stage. There is no `max_a`
    parameter: this function does not clamp the upper bound at all (a large
    surplus yields a large ideal current, uncapped here) -- E8 remains the single
    place the upper bound is enforced, avoiding a second, redundant clamp site for
    the same invariant.

    `has_charged` defaults to False (the connection's first-ever start, immediate,
    no debounce) -- see the module docstring for who owns setting/clearing it.
    """
    ideal_a = surplus_w / voltage

    if state.phase == Phase.COOLDOWN:
        if not cooldown_done(state, now, cooldown_minutes):
            return 0.0, state
        if surplus_w >= start_threshold_w:
            # Already met the moment Cooldown elapses -- never passes through Idle,
            # so no debounce applies here regardless of has_charged (UC01 2b's exemption).
            return _charging_setpoint(ideal_a, min_a), SolarState(Phase.CHARGING, now)
        return 0.0, SolarState.idle()

    if state.phase == Phase.IDLE:
        if surplus_w < start_threshold_w:
            return 0.0, state
        if not has_charged:
            return _charging_setpoint(ideal_a, min_a), SolarState(Phase.CHARGING, now)
        return 0.0, SolarState(Phase.DEBOUNCING, now)  # RestartDebounceStarted (UC01 2b)

    if state.phase == Phase.DEBOUNCING:
        if surplus_w < start_threshold_w:
            # Blip below threshold before the debounce elapsed -- discard the timer,
            # a fresh crossing later starts a fresh one (R11).
            return 0.0, SolarState.idle()
        if now - state.phase_started_at >= debounce_minutes * 60:
            return _charging_setpoint(ideal_a, min_a), SolarState(Phase.CHARGING, now)
        return 0.0, state

    if state.phase == Phase.CHARGING:
        if surplus_w < start_threshold_w:
            return min_a, SolarState(Phase.HOLD, now)
        return _charging_setpoint(ideal_a, min_a), state

    if state.phase == Phase.HOLD:
        if surplus_w >= start_threshold_w:
            return _charging_setpoint(ideal_a, min_a), SolarState(Phase.CHARGING, now)
        if now - state.phase_started_at >= hold_minutes * 60:
            return 0.0, SolarState(Phase.COOLDOWN, now)
        return min_a, state

    raise unknown_phase_error(state)


def _charging_setpoint(ideal_a: float, min_a: float) -> float:
    """Round up (fixed, R1), floored at the minimum current (grid fallback)."""
    return max(round_amp_step(ideal_a, strategy=ROUND_UP), min_a)
