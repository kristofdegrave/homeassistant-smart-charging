"""SolarOnly charging-mode engine (E1 -- UC02). Pure -- no HA imports.

Simpler than Solar: Idle -> Charging -> Cooldown. No Hold, no grid fallback --
surplus below the start threshold stops immediately (UC02's defining difference
from its sibling UC01). No SOC-related phase either -- see Solar's module
docstring (modes/solar.py) for why that's the coordinator's job, not this
module's.

No `min_a` parameter, unlike `Solar.step()`: `SolarOnly` has no grid fallback (UC02
3a), so a below-minimum ideal current is requested as-is and floored to 0 A by the
coordinator's E8 stage (`apply_floor_cap`) downstream, the same as every other mode.
"""

from __future__ import annotations

from dataclasses import dataclass

from ._amp_step import round_amp_step
from ._mode_state import ModeState, cooldown_done, unknown_phase_error
from ._phase import Phase


@dataclass(frozen=True)
class SolarOnlyState(ModeState):
    """No fields of its own -- see `SolarState`'s docstring (`modes/solar.py`) for why
    `@dataclass(frozen=True)` is re-declared rather than a bare subclass."""


def step(
    surplus_w: float,
    state: SolarOnlyState,
    now: float,
    start_threshold_w: float,
    cooldown_minutes: float,
    strategy: str,
    midpoint: float = 0.5,
    voltage: float = 230.0,
) -> tuple[float, SolarOnlyState]:
    """Return (desired_current, next_state) for one control cycle (UC02).

    No `max_a` parameter, for the same reason as `Solar.step()` -- E8 remains the
    single place the upper-bound invariant is enforced. Same story for the
    lower bound -- see the module docstring's `min_a` note.
    """
    ideal_a = surplus_w / voltage

    if state.phase in (Phase.IDLE, Phase.COOLDOWN):
        is_cooldown_done = cooldown_done(state, now, cooldown_minutes)
        if surplus_w >= start_threshold_w and is_cooldown_done:
            return round_amp_step(ideal_a, strategy, midpoint), SolarOnlyState(Phase.CHARGING, now)
        if state.phase == Phase.COOLDOWN and is_cooldown_done:
            return 0.0, SolarOnlyState.idle()
        return 0.0, state

    if state.phase == Phase.CHARGING:
        if surplus_w < start_threshold_w:
            return 0.0, SolarOnlyState(Phase.COOLDOWN, now)  # immediate -- no hold
        return round_amp_step(ideal_a, strategy, midpoint), state

    raise unknown_phase_error(state)
