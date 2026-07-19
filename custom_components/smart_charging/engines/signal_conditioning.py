"""Signal-Conditioning engine (E7). Pure — no HA imports.

MVP slice: NF4 supply-voltage resolution only. Missing/unhealthy grid voltage is
NOT a fault (ADR-0007) — it falls back to the configured nominal voltage.
R10 smoothing of net/solar power is deferred to a later slice.
"""


def resolve_voltage(measured: float | None, nominal: float) -> float:
    """Resolve supply voltage: the measured value when healthy, else nominal (NF4)."""
    if measured is None or measured <= 0:
        return nominal
    return measured
