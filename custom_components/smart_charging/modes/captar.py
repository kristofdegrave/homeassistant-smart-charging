"""Captar charging-mode engine (E1 -- UC03). Pure -- no HA imports (ADR-0006/0009).

Simplest of the mode state machines: Idle -> Charging -> Cooldown. No Hold (no
surplus threshold to ride out -- R4) and no SOC-related phase (design doc Sec 5:
the coordinator gates on SOC, this module never sees why it isn't dispatched).
Unlike Solar/SolarOnly, the transition INTO cooldown is not decided here either --
a sustained R3 breach is detected by the Billing-Protection engine (E5), and the
coordinator forces `state` to `cooldown(now)` when that happens (design doc Sec
6.3): "the clamp decides the set-point this cycle, not the mode" (UC03). This
module only knows how to sit in cooldown and re-arm once it elapses, and to
request the maximum current whenever it is actually dispatched.
State is a small frozen dataclass threaded by the coordinator -- this module
holds nothing itself; `now` (seconds, monotonic) is always injected.
"""

from __future__ import annotations

from dataclasses import dataclass

from ._phase import Phase


@dataclass(frozen=True)
class CaptarState:
    phase: Phase
    phase_started_at: float = 0.0

    @classmethod
    def idle(cls) -> CaptarState:
        return cls(phase=Phase.IDLE)


def step(
    state: CaptarState, now: float, max_a: float, cooldown_minutes: float
) -> tuple[float, CaptarState]:
    """Return (desired_current, next_state) for one control cycle (UC03).

    Always requests `max_a` once charging -- E5's peak clamp and E6's
    grid-ceiling clamp (both downstream, in the coordinator) are what actually
    bound the request each cycle; there is no `min_a` floor concept here the way
    Solar's grid-fallback has one, since Captar's own request is already at the
    ceiling by design.
    """
    if state.phase in (Phase.IDLE, Phase.COOLDOWN):
        elapsed = now - state.phase_started_at
        cooldown_done = state.phase == Phase.IDLE or elapsed >= cooldown_minutes * 60
        if cooldown_done:
            return max_a, CaptarState(Phase.CHARGING, now)
        return 0.0, state
    if state.phase == Phase.CHARGING:
        return max_a, state  # coordinator may still force a cooldown transition
    raise ValueError(f"unknown CaptarState.phase: {state.phase!r}")
