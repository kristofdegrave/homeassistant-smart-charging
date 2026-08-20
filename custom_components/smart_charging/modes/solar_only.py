"""SolarOnly charging-mode engine (E1 -- UC02). Pure -- no HA imports.

Idle -> Charging -> Hold -> Cooldown, mirroring `Solar`'s state shape (modes/solar.py) --
but per R2/UC02 3a, SolarOnly's Hold set-point is the flat `min_a` every cycle, never a
recomputed ideal current: unlike `Solar`, SolarOnly has no ongoing grid fallback while
`Charging` (UC02 3a), so there is no "ideal current, floored at the minimum" rule to
re-apply during the hold -- the hold itself is the one bounded exception to this mode's
otherwise strict zero-grid-import guarantee (issue #755), not a continuation of a
set-point rule that doesn't exist here. No SOC-related phase either -- see Solar's
module docstring for why that's the coordinator's job, not this module's.

`min_a` (new, issue #755) is used only for the Hold set-point/transition -- unlike
`Solar.step()`, it plays no role in the `Charging` set-point itself: `SolarOnly` still
has no grid fallback while charging (UC02 3a), so a below-minimum ideal current there is
requested as-is and floored to 0 A by the coordinator's E8 stage (`apply_floor_cap`)
downstream, the same as every other mode.
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
    min_a: float,
    hold_minutes: float,
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
            return min_a, SolarOnlyState(Phase.HOLD, now)
        return round_amp_step(ideal_a, strategy, midpoint), state

    if state.phase == Phase.HOLD:
        if surplus_w >= start_threshold_w:
            return round_amp_step(ideal_a, strategy, midpoint), SolarOnlyState(Phase.CHARGING, now)
        if now - state.phase_started_at >= hold_minutes * 60:
            return 0.0, SolarOnlyState(Phase.COOLDOWN, now)
        return min_a, state  # flat min_a -- no recomputed ideal, unlike Solar's own Hold (R2)

    raise unknown_phase_error(state)
