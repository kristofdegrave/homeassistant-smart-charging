"""Power charging mode (E1). Pure — no HA imports (ADR-0006/0009)."""

from ..const import CHARGEABLE_STATES


def desired_current(target_current: float, status: str) -> float:
    """Return the desired charger current for Power mode.

    Commands the user's target current when a car is present (canonical status
    ``connected`` or ``charging``); otherwise commands 0 A.
    """
    if status in CHARGEABLE_STATES:
        return target_current
    return 0.0
