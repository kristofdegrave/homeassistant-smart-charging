"""Cycle-Invariant engine (E8). Pure — no HA imports.

MVP slice: the C1 floor/cap invariant only. The commanded current is always 0 A
or within [min, max]; a value below the charger minimum becomes a stop (0 A),
never a between-0-and-min guess. R11 cooldown/hold is deferred to a later slice.
"""


def apply_floor_cap(desired_current: float, min_a: float, max_a: float) -> float:
    """Return a current that is 0 A or within ``[min_a, max_a]`` (C1)."""
    if desired_current < min_a:
        return 0.0
    if desired_current > max_a:
        return max_a
    return desired_current
