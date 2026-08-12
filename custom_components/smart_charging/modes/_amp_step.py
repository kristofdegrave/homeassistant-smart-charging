"""Shared amp-step rounding helper for the solar modes (R1/R2).

Not an Engine of its own -- a pure utility both `modes/solar.py` and
`modes/solar_only.py` call with their own strategy, keeping the rounding math out
of each mode's state-machine logic without coupling the two modes together (NF2).
"""

import math

# Strategy constants live in const.py, not here -- imported only for this
# module's own comparisons below; other call sites should import from `..const` directly.
from ..const import ROUND_DOWN, ROUND_NEAREST, ROUND_UP


def round_amp_step(ideal_a: float, strategy: str, midpoint: float = 0.5) -> float:
    """Convert a continuous ideal current into a whole-ampere set-point.

    `round_up` -- ceiling (accepts a bounded grid top-up; Solar's fixed strategy, R1).
    `round_down` -- floor (never imports; SolarOnly's default, R2).
    `round_nearest` -- whichever whole ampere is closer, using `midpoint` as the
    fractional threshold at/above which the value rounds up (R2, "pendel" case).
    """
    if strategy == ROUND_UP:
        return float(math.ceil(ideal_a))
    if strategy == ROUND_DOWN:
        return float(math.floor(ideal_a))
    if strategy == ROUND_NEAREST:
        floor_a = math.floor(ideal_a)
        fraction = ideal_a - floor_a
        return float(floor_a + 1) if fraction >= midpoint else float(floor_a)
    raise ValueError(f"unknown amp-step rounding strategy: {strategy!r}")
