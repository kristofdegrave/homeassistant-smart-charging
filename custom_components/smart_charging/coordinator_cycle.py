"""Coordinator-internal cycle decomposition (ADR-0012): CycleContext, PeakDemandState,
SocGateResolver, and the ModeHandler Strategy. Imported only by coordinator.py. Pure -- no HA
imports (mirrors engines/ purity, ADR-0009/0010), even though these aren't engines themselves
(system-design Sec 4 rule 4: an engine may not call another engine; these call engines)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .engines.peak_demand_tracker import update_monthly_peak_demand
from .engines.signal_conditioning import smooth_net_power
from .engines.soc_target import SolarStepUpState, resolve_active_soc_limit

_WATTS_PER_KILOWATT = 1000.0


@dataclass  # deliberately not frozen -- steps mutate fields in place as each value resolves
class CycleContext:
    """Carries one cycle's readings/derived values between _run_cycle's steps, replacing the
    loose local variables ADR-0012 flagged. Filled progressively as steps resolve each value --
    not everything is known at construction time."""

    status: str
    net_w: float  # raw, not the smoothed reading (coordinator.py's separate smoothed_net_w)
    charger_w: float
    voltage: float
    now: float
    now_dt: datetime | None  # None only in the Task 3.3 dry-run construction
    ev_soc: float | None = None
    surplus_w: float = 0.0
    monthly_peak_kw: float = 0.0
    effective_peak_limit_kw: float = 0.0
    active_soc_limit: float = 0.0
    urgent: bool = False
    sun_is_up: bool = False
    sun_is_down: bool = False
    low_tariff_active: bool = True
    solar_reserve_active: bool = False


@dataclass  # deliberately not frozen -- update() mutates window/tracked_kw/tracked_month in place
class PeakDemandState:
    """Owns the coordinator's monthly-peak-demand bookkeeping (project-plan E5 / Power-MVP Task
    1.3), replacing the three loose _peak_window/_peak_tracked_kw/_peak_tracked_month fields
    ADR-0012 flagged. Distinct from _peak_tracker (PeakBreachTracker, the R3 clamp's own
    breach-timer state) -- untouched by this decision, still threaded through the step-7 clamp
    call directly."""

    window: tuple[float, ...] = ()
    tracked_kw: float = 0.0
    tracked_month: tuple[int, int] | None = None

    def update(self, net_w: float, now_dt: datetime, *, window_size: int) -> float:
        """Fold `net_w` into the smoothing window and return the running monthly-peak kW.

        A month rollover resets the smoothing window too, not just tracked_kw (design doc
        Sec 6.4) -- else this cycle's "smoothed" reading would partly reflect last month.
        """
        current_month = (now_dt.year, now_dt.month)
        if current_month != self.tracked_month:
            self.window = ()
        smoothed_w, self.window = smooth_net_power(net_w, self.window, size=window_size)
        self.tracked_kw, self.tracked_month = update_monthly_peak_demand(
            smoothed_w / _WATTS_PER_KILOWATT, current_month, self.tracked_kw, self.tracked_month
        )
        return self.tracked_kw


class SocGateResolver:
    """Owns SOC-limit resolution + change detection (ADR-0012), replacing the inline
    resolve_active_soc_limit call + _last_active_soc_limit comparison. Pure -- no hass.bus
    access; the coordinator still fires ActiveSocLimitChanged itself on a reported change
    (ADR-0009/0010 boundary: HA I/O stays coordinator-side)."""

    def __init__(self) -> None:
        self._last_limit: float | None = None

    def resolve(
        self,
        override: float,
        *,
        solar_reserve_active: bool,
        solar_reserve_soc: float,
        step_up_state: SolarStepUpState,
    ) -> tuple[float, bool]:
        """Return (this cycle's active SOC limit, whether it changed from the last resolve()).

        The first call always reports changed=True -- there is no prior resolve() to compare
        against, mirroring the old code's None-vs-float first-cycle behavior.
        """
        limit = resolve_active_soc_limit(
            override,
            solar_reserve_active=solar_reserve_active,
            solar_reserve_soc=solar_reserve_soc,
            step_up_state=step_up_state,
        )
        changed = limit != self._last_limit
        self._last_limit = limit
        return limit, changed
