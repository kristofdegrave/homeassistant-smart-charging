"""Coordinator-internal cycle decomposition (ADR-0012): CycleContext, PeakDemandState,
SocGateResolver, and the ModeHandler Strategy. Imported only by coordinator.py. Pure -- no HA
imports (mirrors engines/ purity, ADR-0009/0010), even though these aren't engines themselves
(system-design Sec 4 rule 4: an engine may not call another engine; these call engines)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from .const import (
    CONF_CAPTAR_COOLDOWN_MIN,
    CONF_MAX_CURRENT,
    CONF_MIN_CURRENT,
    CONF_SOLAR_COOLDOWN_MIN,
    CONF_SOLAR_HOLD_MIN,
    CONF_SOLAR_ONLY_MIDPOINT,
    CONF_SOLAR_ONLY_START_THRESHOLD_W,
    CONF_SOLAR_ONLY_STRATEGY,
    CONF_SOLAR_START_THRESHOLD_W,
    DEFAULT_CAPTAR_COOLDOWN_MIN,
)
from .engines.peak_demand_tracker import update_monthly_peak_demand
from .engines.signal_conditioning import smooth_net_power
from .modes import captar, power, solar, solar_only

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


class ModeHandler(Protocol):
    """One thin adapter per mode module, wrapping its existing pure step()/desired_current()
    unchanged (ADR-0012) -- this decision only changes how the coordinator looks one up, not
    any mode module's own logic."""

    def desired_current(self, ctx: CycleContext, state: Any) -> tuple[float, Any]:
        """Return (desired_current_a, new_state); does not mutate ctx or state in place."""
        ...


class _OffModeHandler:
    """Off mode has no modes/*.py module of its own to wrap -- commands 0 A unconditionally
    and passes state through unchanged, mirroring today's MODE_OFF branch, which never
    touches per-mode state (design doc Sec 3.4)."""

    def desired_current(self, ctx: CycleContext, state: Any) -> tuple[float, Any]:
        return 0.0, state


class _PowerModeHandler:
    """Wraps modes/power.py::desired_current unchanged. power.desired_current reads the
    coordinator's own mutable target_current (set externally by the number entity), not
    anything on CycleContext -- so this handler takes a zero-arg getter bound at construction
    (design doc Sec 3.4) rather than duplicating that value onto CycleContext each cycle."""

    def __init__(self, target_current_getter: Callable[[], float]) -> None:
        self._target_current_getter = target_current_getter

    def desired_current(self, ctx: CycleContext, state: Any) -> tuple[float, Any]:
        return power.desired_current(self._target_current_getter(), ctx.status), state


class _SolarModeHandler:
    """Wraps modes/solar.py::step unchanged."""

    def __init__(self, config: Mapping[str, Any]) -> None:
        self._config = config

    def desired_current(
        self, ctx: CycleContext, state: solar.SolarState
    ) -> tuple[float, solar.SolarState]:
        return solar.step(
            ctx.surplus_w,
            state,
            ctx.now,
            start_threshold_w=self._config[CONF_SOLAR_START_THRESHOLD_W],
            min_a=self._config[CONF_MIN_CURRENT],
            hold_minutes=self._config[CONF_SOLAR_HOLD_MIN],
            cooldown_minutes=self._config[CONF_SOLAR_COOLDOWN_MIN],
            voltage=ctx.voltage,
        )


class _SolarOnlyModeHandler:
    """Wraps modes/solar_only.py::step unchanged."""

    def __init__(self, config: Mapping[str, Any]) -> None:
        self._config = config

    def desired_current(
        self, ctx: CycleContext, state: solar_only.SolarOnlyState
    ) -> tuple[float, solar_only.SolarOnlyState]:
        return solar_only.step(
            ctx.surplus_w,
            state,
            ctx.now,
            start_threshold_w=self._config[CONF_SOLAR_ONLY_START_THRESHOLD_W],
            min_a=self._config[CONF_MIN_CURRENT],
            cooldown_minutes=self._config[CONF_SOLAR_COOLDOWN_MIN],
            strategy=self._config[CONF_SOLAR_ONLY_STRATEGY],
            midpoint=self._config[CONF_SOLAR_ONLY_MIDPOINT],
            voltage=ctx.voltage,
        )


class _CaptarModeHandler:
    """Wraps modes/captar.py::step unchanged."""

    def __init__(self, config: Mapping[str, Any]) -> None:
        self._config = config

    def desired_current(
        self, ctx: CycleContext, state: captar.CaptarState
    ) -> tuple[float, captar.CaptarState]:
        return captar.step(
            state,
            ctx.now,
            max_a=self._config[CONF_MAX_CURRENT],
            cooldown_minutes=self._config.get(
                CONF_CAPTAR_COOLDOWN_MIN, DEFAULT_CAPTAR_COOLDOWN_MIN
            ),
        )
