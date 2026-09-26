"""Signal-Conditioning engine (E7). Pure — no HA imports.

NF4 supply-voltage resolution, plus R10 net-import smoothing. `smooth_net_power`
smooths `net_w` only; `solar_power` smoothing is deferred to whichever later slice
first consumes that role. `smooth_household_baseline` is R10's separate smoothing path for the
solar modes' own surplus (issue #1329) -- see its own docstring.
"""

from dataclasses import dataclass


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


@dataclass(frozen=True)
class HouseholdWindow:
    """`smooth_household_baseline`'s own threaded state: the rolling window `smooth_net_power`
    maintains, plus whether the PREVIOUS call froze it on a command-changed cycle.
    `deferred_previous` caps that freeze at one cycle in a row -- the same reason
    `BaselineDebouncer.deferred_previous` (ADR-0039) caps its own: a mode that adjusts its own
    request most cycles (Solar tracking a drifting surplus) would otherwise make every reading a
    command-changed one and freeze the window indefinitely, so a genuinely moving surplus would
    never be tracked at all."""

    samples: tuple[float, ...] = ()
    deferred_previous: bool = False


def smooth_household_baseline(
    raw_baseline_w: float, state: HouseholdWindow, size: int, *, command_changed: bool
) -> tuple[float, HouseholdWindow]:
    """Fold `net_w - charger_w` into the same rolling-window mean `smooth_net_power` computes,
    except on a cycle whose own command changed (issue #1329, R10's steady-input criterion).

    The solar modes set their rate from `charger_w` netted against a mean of *net* import
    (`_run_cycle`'s old `surplus_w = charger_w - smoothed_net_w`), and that mean is built from
    `net_w` samples taken while the charger was drawing whatever it was set to on each of those
    earlier cycles -- not what it draws now. Averaging `net_w` alone therefore always carries
    some of the charger's own past actuation, at currents that keep drifting as the loop reacts
    to its own output, and the set-point never settles (modelled in the issue against the real
    `modes/solar.py`). Subtracting `charger_w` from each *sample* before it is averaged --
    rather than from the average afterwards -- removes that history: `net_w - charger_w` is the
    household's own load, independent of whatever the charger drew on the cycle it was read.

    That per-sample subtraction reads the same stale `charger_w` a step can leave behind for one
    cycle (ADR-0039's field condition, issue #990) -- and, unlike the raw R3 clamp, one that
    would otherwise change what it feeds the window rather than only what it briefly overstates:
    a reading taken on a cycle whose command changed is partly a measurement of this
    integration's own actuation, and folding it in biases the mean away from the true household
    baseline for as long as it sits in the window. `command_changed` -- the same signal
    `debounce_baseline_w` already reads via `_run_cycle`'s own `self._command_stepped`, ADR-0039
    -- gates that fold exactly as it gates R3's: on such a cycle (capped at one in a row, see
    `HouseholdWindow.deferred_previous`) the window is left untouched and its already-established
    mean stands for one more cycle, rather than admitting a sample that would need to age back
    out again before the household baseline reasserts itself. An empty window has no such mean to
    fall back on -- the very first reading of a connection is always folded in, mirroring
    `debounce_baseline_w`'s own `tracker.accepted_w is None` case. `size == 1` has no history to
    protect either (`smooth_net_power` keeps only the newest sample at that size regardless), so
    the freeze never applies there -- a `size == 1` caller wants the current cycle's own reading,
    same as R10's own smoothing does at that size.
    """
    if size > 1 and command_changed and state.samples and not state.deferred_previous:
        mean = sum(state.samples) / len(state.samples)
        return mean, HouseholdWindow(state.samples, deferred_previous=True)
    smoothed, new_samples = smooth_net_power(raw_baseline_w, state.samples, size)
    return smoothed, HouseholdWindow(new_samples, deferred_previous=False)
