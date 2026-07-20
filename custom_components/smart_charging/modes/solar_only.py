"""SolarOnly charging-mode engine (E1 -- UC02). Pure -- no HA imports.

Simpler than Solar: Idle -> Charging -> Cooldown. No Hold, no grid fallback --
surplus below the start threshold stops immediately (UC02's defining difference
from its sibling UC01). No SOC-related phase either -- see Solar's module
docstring (modes/solar.py) for why that's the coordinator's job, not this
module's.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ._amp_step import round_amp_step


class SolarOnlyPhase(StrEnum):
    """The SolarOnly mode's own phases (UC02), minus SocReached -- see modes/solar.py."""

    IDLE = "idle"
    CHARGING = "charging"
    COOLDOWN = "cooldown"


@dataclass(frozen=True)
class SolarOnlyState:
    phase: SolarOnlyPhase
    phase_started_at: float = 0.0

    @classmethod
    def idle(cls) -> SolarOnlyState:
        return cls(phase=SolarOnlyPhase.IDLE)


def step(
    surplus_w: float,
    state: SolarOnlyState,
    now: float,
    start_threshold_w: float,
    min_a: float,
    cooldown_minutes: float,
    strategy: str,
    midpoint: float = 0.5,
    voltage: float = 230.0,
) -> tuple[float, SolarOnlyState]:
    """Return (desired_current, next_state) for one control cycle (UC02).

    No `max_a` parameter, for the same reason as `Solar.step()` -- E8 remains the
    single place the upper-bound invariant is enforced.
    """
    ideal_a = surplus_w / voltage

    if state.phase in (SolarOnlyPhase.IDLE, SolarOnlyPhase.COOLDOWN):
        elapsed = now - state.phase_started_at
        cooldown_done = state.phase == SolarOnlyPhase.IDLE or elapsed >= cooldown_minutes * 60
        if surplus_w >= start_threshold_w and cooldown_done:
            return round_amp_step(ideal_a, strategy, midpoint), SolarOnlyState(
                SolarOnlyPhase.CHARGING, now
            )
        if state.phase == SolarOnlyPhase.COOLDOWN and cooldown_done:
            return 0.0, SolarOnlyState.idle()
        return 0.0, state

    if state.phase == SolarOnlyPhase.CHARGING:
        if surplus_w < start_threshold_w:
            return 0.0, SolarOnlyState(SolarOnlyPhase.COOLDOWN, now)  # immediate -- no hold
        return round_amp_step(ideal_a, strategy, midpoint), state

    raise ValueError(f"unknown SolarOnlyState.phase: {state.phase!r}")
