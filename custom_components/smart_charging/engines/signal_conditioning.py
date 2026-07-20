"""Signal-Conditioning engine (E7). Pure — no HA imports.

NF4 supply-voltage resolution, plus R10 net-import smoothing. `smooth_net_power`
smooths `net_w` only; `solar_power` smoothing is deferred to whichever later slice
first consumes that role (see design doc §6).
"""


def resolve_voltage(measured: float | None, nominal: float) -> float:
    """Resolve supply voltage: the measured value when healthy, else nominal (NF4)."""
    if measured is None or measured <= 0:
        return nominal
    return measured


def smooth_net_power(
    raw_w: float, window: tuple[float, ...], size: int
) -> tuple[float, tuple[float, ...]]:
    """Fold `raw_w` into a rolling window and return (smoothed_mean, new_window) (R10).

    Averages over however many samples are collected so far when the window isn't
    yet full (start-up/restart edge case). The window is a plain parameter -- the
    caller (M1) threads it across cycles; this function holds no state itself.
    """
    new_window = (*window, raw_w)[-size:]
    return sum(new_window) / len(new_window), new_window
