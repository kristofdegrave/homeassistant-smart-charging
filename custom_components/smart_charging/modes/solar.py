"""Solar charging-mode engine (E1 -- UC01). Pure -- no HA imports (ADR-0006/0009).

State machine: Idle -> Charging -> Hold -> Cooldown, per UC01's state model, MINUS
the SocReached phase UC01's own diagram draws -- that transition is entirely the
coordinator's responsibility (M1), not this module's (see design doc §5's "Where
the SOC gate itself lives"): a mode "has no opinion on why the limit is where it
is" (R7), so it is never told SOC was reached at all -- the coordinator simply
stops calling step() and holds this state at idle() for as long as the gate holds.
State is a small frozen dataclass threaded by the coordinator -- this module holds
nothing itself; `now` (seconds, monotonic) is always injected.
"""

from __future__ import annotations

from dataclasses import dataclass

from ._amp_step import ROUND_UP, round_amp_step
from ._phase import Phase


@dataclass(frozen=True)
class SolarState:
    phase: Phase
    phase_started_at: float = 0.0

    @classmethod
    def idle(cls) -> SolarState:
        return cls(phase=Phase.IDLE)


def step(
    surplus_w: float,
    state: SolarState,
    now: float,
    start_threshold_w: float,
    min_a: float,
    hold_minutes: float,
    cooldown_minutes: float,
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
    """
    ideal_a = surplus_w / voltage

    if state.phase in (Phase.IDLE, Phase.COOLDOWN):
        elapsed = now - state.phase_started_at
        cooldown_done = state.phase == Phase.IDLE or elapsed >= cooldown_minutes * 60
        if surplus_w >= start_threshold_w and cooldown_done:
            return _charging_setpoint(ideal_a, min_a), SolarState(Phase.CHARGING, now)
        if state.phase == Phase.COOLDOWN and cooldown_done:
            return 0.0, SolarState.idle()
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

    raise ValueError(f"unknown SolarState.phase: {state.phase!r}")


def _charging_setpoint(ideal_a: float, min_a: float) -> float:
    """Round up (fixed, R1), floored at the minimum current (grid fallback)."""
    return max(round_amp_step(ideal_a, strategy=ROUND_UP), min_a)
