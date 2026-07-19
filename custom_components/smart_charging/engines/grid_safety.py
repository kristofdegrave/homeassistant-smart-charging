"""Grid-Safety engine (E6). Pure — no HA imports.

Enforces the C4 grid-supply-ceiling clamp: the charger current is reduced so that
total grid import stays within ``ceiling_a - offset_a`` (the fuse rating minus the
configured safety margin). No opt-out (ADR-0006): this must always run, and stay a
distinct call site from any peak clamp.
"""

import math


def clamp_to_ceiling(
    desired_current: float,
    net_w: float,
    charger_w: float,
    voltage: float,
    ceiling_a: float,
    offset_a: float,
) -> float:
    """Clamp ``desired_current`` (A) so grid import stays within ``ceiling_a - offset_a`` (A).

    Solves from the baseline actually flowing (``net_w - charger_w``), not the
    requested current, so a breach cannot hide behind the request. The headroom is
    computed against ``ceiling_a - offset_a`` — the C4 safety margin keeps the enforced
    limit below the fuse rating — and floored to a whole ampere so an EVSE that rounds
    the setpoint up cannot overshoot it. May return a value below the charger minimum
    (or negative) when the household baseline alone approaches/exceeds the ceiling; the
    cycle-invariant stage (E8) turns an un-chargeable result into a clean stop.
    """
    baseline_w = net_w - charger_w
    headroom_a = math.floor((ceiling_a - offset_a) - baseline_w / voltage)
    return min(desired_current, float(headroom_a))
