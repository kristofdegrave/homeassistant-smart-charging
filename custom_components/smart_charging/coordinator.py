"""Charging Coordinator (M1) — the control cycle (ADR-0006/0007)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CHARGEABLE_STATES,
    CONF_CAPTAR_COOLDOWN_MIN,
    CONF_GRID_CEILING_A,
    CONF_GRID_SAFETY_OFFSET_A,
    CONF_MAX_CURRENT,
    CONF_MAX_PEAK_KW,
    CONF_MIN_CURRENT,
    CONF_NOMINAL_VOLTAGE,
    CONF_PEAK_GRACE_MIN,
    CONF_PEAK_WINDOW_SIZE,
    CONF_POWER_RESPECT_PEAK,
    CONF_SAFETY_MARGIN_W,
    CONF_SMOOTHING_WINDOW,
    CONF_SOLAR_COOLDOWN_MIN,
    CONF_SOLAR_HOLD_MIN,
    CONF_SOLAR_ONLY_MIDPOINT,
    CONF_SOLAR_ONLY_START_THRESHOLD_W,
    CONF_SOLAR_ONLY_STRATEGY,
    CONF_SOLAR_START_THRESHOLD_W,
    DEFAULT_CAPTAR_COOLDOWN_MIN,
    DEFAULT_MAX_PEAK_KW,
    DEFAULT_PEAK_GRACE_MIN,
    DEFAULT_POWER_RESPECT_PEAK,
    DEFAULT_SAFETY_MARGIN_W,
    DEFAULT_SMOOTHING_WINDOW,
    DEFAULT_SOC_LIMIT,
    DOMAIN,
    MODE_CAPTAR,
    MODE_OFF,
    MODE_POWER,
    MODE_SOLAR,
    MODE_SOLAR_ONLY,
    PEAK_WINDOW_SECONDS,
    ROLE_CHARGER_CURRENT,
    ROLE_CHARGER_POWER,
    ROLE_CHARGER_STATUS,
    ROLE_EV_SOC,
    ROLE_GRID_VOLTAGE,
    ROLE_NET_POWER,
)
from .engines.billing_protection import (
    PeakBreachTracker,
    apply_peak_clamp,
    resolve_effective_peak_limit,
)
from .engines.cycle_invariant import apply_floor_cap
from .engines.grid_safety import clamp_to_ceiling
from .engines.peak_demand_tracker import update_monthly_peak_demand
from .engines.signal_conditioning import resolve_voltage, smooth_net_power
from .engines.soc_target import SolarStepUpState, resolve_active_soc_limit
from .modes import captar, power, solar, solar_only
from .modes._phase import Phase

_LOGGER = logging.getLogger(__name__)

_SOC_GATED_MODES = (MODE_SOLAR, MODE_SOLAR_ONLY, MODE_CAPTAR)


def _fresh_mode_state() -> dict:
    """R7/R11: the idle state every mode with one resets to -- disconnect, mode switch,
    and the SOC gate all rebuild from this same shape."""
    return {
        MODE_SOLAR: solar.SolarState.idle(),
        MODE_SOLAR_ONLY: solar_only.SolarOnlyState.idle(),
        MODE_CAPTAR: captar.CaptarState.idle(),
    }


@dataclass
class CycleResult:
    """Outcome of one control cycle: the amps actually written and whether it faulted."""

    commanded_current: float
    fault: bool
    active_mode: str
    monthly_peak_kw: float = 0.0
    effective_peak_limit_kw: float = 0.0


class SmartChargingCoordinator(DataUpdateCoordinator[CycleResult]):
    """Runs the control cycle every interval, dispatching to the active mode (M1)."""

    def __init__(self, hass: HomeAssistant, *, adapters, config, interval_s: int) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval_s),
        )
        self._adapters = adapters
        self._config = config
        self._interval_s = interval_s
        # Single source of truth for the setpoint is the number entity, which seeds this on
        # add (restored value, else configured default). 0 A is the safe default for cycle 0.
        self.target_current: float = 0.0
        # Single source of truth for these is their owning entity (select/number), which seeds
        # them on add (restored value, else configured default) before the first refresh --
        # this MODE_POWER default only matters for a coordinator instance never wired to a
        # select entity (e.g. a unit test constructing one directly).
        self.active_mode: str = MODE_POWER
        self.soc_limit_override: float = DEFAULT_SOC_LIMIT
        # Task 5.1 (Phase 5) replaces this placeholder wiring with the real R7/R8/R9 inputs;
        # for now it reproduces today's row-3-only behavior (E3, Task 1.2).
        self._step_up_state: SolarStepUpState = SolarStepUpState()
        self._last_active_mode: str | None = None
        self._net_window: tuple[float, ...] = ()
        self._mode_state = _fresh_mode_state()
        self._was_faulted = False
        # M1's OWN 15-minute window (E5, Task 1.3), distinct from R10's `_net_window` above --
        # a MonthlyPeakSensor restore may seed `_peak_tracked_kw`/`_peak_tracked_month` before
        # the first cycle (Task 4.2); the window itself is deliberately never persisted (design
        # doc Sec 6.4), so it always starts empty here.
        self._peak_window: tuple[float, ...] = ()
        self._peak_tracked_kw: float = 0.0
        self._peak_tracked_month: tuple[int, int] | None = None
        self._peak_tracker = PeakBreachTracker()

    async def _async_update_data(self) -> CycleResult:
        try:
            return await self._run_cycle()
        except Exception as err:  # noqa: BLE001 - every failure funnels to the fault path (ADR-0007)
            self._log_fault(f"cycle exception: {err}")
            await self._safe_write_zero()
            return CycleResult(commanded_current=0.0, fault=True, active_mode=self.active_mode)

    async def _run_cycle(self) -> CycleResult:
        status = await self._adapters[ROLE_CHARGER_STATUS].read()
        net_w = await self._adapters[ROLE_NET_POWER].read()
        charger_w = await self._adapters[ROLE_CHARGER_POWER].read()

        # Grid voltage is the one role where None is NOT a fault (NF4).
        measured_v = None
        if ROLE_GRID_VOLTAGE in self._adapters:
            measured_v = await self._adapters[ROLE_GRID_VOLTAGE].read()
        voltage = resolve_voltage(measured_v, self._config[CONF_NOMINAL_VOLTAGE])

        # Any required role missing -> fault (ADR-0007).
        if status is None or net_w is None or charger_w is None:
            self._log_fault("required adapter returned None")
            await self._write(0.0)
            return CycleResult(commanded_current=0.0, fault=True, active_mode=self.active_mode)

        # Peak-Demand Tracker (E5, Task 1.3) + effective-peak-limit resolution (E5, Task 1.2) --
        # runs every cycle regardless of mode (R3's bookkeeping is not Captar-specific). Uses
        # real wall-clock (dt_util.now()) for month rollover, distinct from the monotonic `now`
        # the mode state machines use below.
        now_dt = dt_util.now()
        current_month = (now_dt.year, now_dt.month)
        if current_month != self._peak_tracked_month:
            # Month rollover resets the SMOOTHING WINDOW too, not just the tracked value --
            # otherwise this cycle's "smoothed" reading would still partly reflect last month's
            # raw samples (design doc Sec 6.4's month-rollover note).
            self._peak_window = ()
        peak_window_size = self._config.get(
            CONF_PEAK_WINDOW_SIZE, max(1, round(PEAK_WINDOW_SECONDS / self._interval_s))
        )
        smoothed_peak_w, self._peak_window = smooth_net_power(
            net_w, self._peak_window, size=peak_window_size
        )
        monthly_peak_kw, self._peak_tracked_month = update_monthly_peak_demand(
            smoothed_peak_w / 1000.0,
            current_month,
            self._peak_tracked_kw,
            self._peak_tracked_month,
        )
        self._peak_tracked_kw = monthly_peak_kw
        effective_peak_limit_kw = resolve_effective_peak_limit(
            monthly_peak_kw, self._config.get(CONF_MAX_PEAK_KW, DEFAULT_MAX_PEAK_KW)
        )

        if self.active_mode != self._last_active_mode:
            # R11: switching mode resets timers -- fresh state for every mode with one, whether
            # or not the incoming mode is one of them (a state nobody is dispatching to is inert
            # either way).
            self._mode_state = _fresh_mode_state()
            self._last_active_mode = self.active_mode

        # ev_soc is read -- and its absence is a fault -- ONLY while a solar mode or Captar is
        # selected AND the car is connected (success-criterion 6 / S2: Power/Off must not regress
        # to needing an SOC sensor; a disconnected car is a clean idle stop, not a fault, even if
        # its SOC sensor also goes unavailable on unplug, per UC01/R7).
        ev_soc = None
        if self.active_mode in _SOC_GATED_MODES and status in CHARGEABLE_STATES:
            ev_soc = (
                await self._adapters[ROLE_EV_SOC].read() if ROLE_EV_SOC in self._adapters else None
            )
            if ev_soc is None:
                self._log_fault("ev_soc required while a solar mode is active but missing/None")
                await self._write(0.0)
                return CycleResult(
                    commanded_current=0.0,
                    fault=True,
                    active_mode=self.active_mode,
                    monthly_peak_kw=monthly_peak_kw,
                    effective_peak_limit_kw=effective_peak_limit_kw,
                )

        # .get(): the smoothing-window option is only wired into the config entry once Task 6.1
        # threads it through __init__.py; smoothing runs every cycle regardless of mode.
        smoothing_window = self._config.get(CONF_SMOOTHING_WINDOW, DEFAULT_SMOOTHING_WINDOW)
        smoothed_net_w, self._net_window = smooth_net_power(
            net_w, self._net_window, size=smoothing_window
        )
        # solar_reserve_active/solar_reserve_soc are placeholders (row 1 always inactive) --
        # Task 5.1 replaces them with the real resolve_solar_reserve_active/CONF_SOLAR_RESERVE_SOC
        # values; self._step_up_state is likewise only reset here, never populated by
        # resolve_solar_step_up until that same task wires it in.
        active_soc_limit = resolve_active_soc_limit(
            self.soc_limit_override,
            solar_reserve_active=False,
            solar_reserve_soc=0.0,
            step_up_state=self._step_up_state,
        )
        now = self.hass.loop.time()  # injected, not read inside modes/engines

        if status not in CHARGEABLE_STATES:
            desired = 0.0
            # R7/R11: disconnect resets every mode's state, clearing hold/cooldown -- and, for
            # a solar mode or Captar, also ends any SOC gate (resume condition 2: unplug/replug).
            self._mode_state = _fresh_mode_state()
        elif self.active_mode == MODE_OFF:
            desired = 0.0
        elif self.active_mode == MODE_POWER:
            desired = power.desired_current(self.target_current, status)  # unchanged, no SOC gate
        elif self.active_mode in _SOC_GATED_MODES and ev_soc >= active_soc_limit:
            # R7: don't resume until the gate clears. Holding the state at idle() (rather than
            # dispatching into step()) means the next cycle where this branch stops matching --
            # because soc_limit_override rose (resume condition 1) -- dispatches fresh from
            # idle(), re-checking the start threshold normally. No latch, no separate phase.
            desired = 0.0
            if self.active_mode == MODE_CAPTAR:
                self._mode_state[MODE_CAPTAR] = captar.CaptarState.idle()
            else:
                self._mode_state[self.active_mode] = (
                    solar.SolarState.idle()
                    if self.active_mode == MODE_SOLAR
                    else solar_only.SolarOnlyState.idle()
                )
        elif self.active_mode == MODE_SOLAR:
            surplus_w = charger_w - smoothed_net_w
            desired, self._mode_state[MODE_SOLAR] = solar.step(
                surplus_w,
                self._mode_state[MODE_SOLAR],
                now,
                start_threshold_w=self._config[CONF_SOLAR_START_THRESHOLD_W],
                min_a=self._config[CONF_MIN_CURRENT],
                hold_minutes=self._config[CONF_SOLAR_HOLD_MIN],
                cooldown_minutes=self._config[CONF_SOLAR_COOLDOWN_MIN],
                voltage=voltage,
            )
        elif self.active_mode == MODE_SOLAR_ONLY:
            surplus_w = charger_w - smoothed_net_w
            desired, self._mode_state[MODE_SOLAR_ONLY] = solar_only.step(
                surplus_w,
                self._mode_state[MODE_SOLAR_ONLY],
                now,
                start_threshold_w=self._config[CONF_SOLAR_ONLY_START_THRESHOLD_W],
                min_a=self._config[CONF_MIN_CURRENT],
                cooldown_minutes=self._config[CONF_SOLAR_COOLDOWN_MIN],
                strategy=self._config[CONF_SOLAR_ONLY_STRATEGY],
                midpoint=self._config[CONF_SOLAR_ONLY_MIDPOINT],
                voltage=voltage,
            )
        else:  # MODE_CAPTAR
            desired, self._mode_state[MODE_CAPTAR] = captar.step(
                self._mode_state[MODE_CAPTAR],
                now,
                max_a=self._config[CONF_MAX_CURRENT],
                cooldown_minutes=self._config.get(
                    CONF_CAPTAR_COOLDOWN_MIN, DEFAULT_CAPTAR_COOLDOWN_MIN
                ),
            )

        # R3 peak clamp (E5) -- skippable only for Power via its own R17 opt-out (design doc
        # Sec 7). `desired` here is the already-computed mode request from dispatch above --
        # apply_peak_clamp's breach timer only starts/continues when `desired >= min_a`, so the
        # disconnect/Off/SOC-gated branches above (all `desired = 0.0`) can never trip
        # force_stop this cycle, regardless of headroom.
        power_respect_peak = self._config.get(CONF_POWER_RESPECT_PEAK, DEFAULT_POWER_RESPECT_PEAK)
        if not (self.active_mode == MODE_POWER and not power_respect_peak):
            desired, self._peak_tracker, force_stop = apply_peak_clamp(
                desired,
                net_w=net_w,
                charger_w=charger_w,
                voltage=voltage,
                effective_peak_limit_kw=effective_peak_limit_kw,
                safety_margin_w=self._config.get(CONF_SAFETY_MARGIN_W, DEFAULT_SAFETY_MARGIN_W),
                min_a=self._config[CONF_MIN_CURRENT],
                grace_period_s=self._config.get(CONF_PEAK_GRACE_MIN, DEFAULT_PEAK_GRACE_MIN) * 60,
                tracker=self._peak_tracker,
                now=now,
            )
            if force_stop and self.active_mode == MODE_CAPTAR:
                desired = 0.0
                self._mode_state[MODE_CAPTAR] = captar.CaptarState(Phase.COOLDOWN, now)

        desired = clamp_to_ceiling(  # E6 (before E8)
            desired,
            net_w=net_w,
            charger_w=charger_w,
            voltage=voltage,
            ceiling_a=self._config[CONF_GRID_CEILING_A],
            offset_a=self._config[CONF_GRID_SAFETY_OFFSET_A],
        )
        desired = apply_floor_cap(  # E8 invariant last
            desired, min_a=self._config[CONF_MIN_CURRENT], max_a=self._config[CONF_MAX_CURRENT]
        )

        await self._write(desired)
        if self._was_faulted:
            _LOGGER.info("smart_charging recovered from fault")
            self._was_faulted = False
        return CycleResult(
            commanded_current=desired,
            fault=False,
            active_mode=self.active_mode,
            monthly_peak_kw=monthly_peak_kw,
            effective_peak_limit_kw=effective_peak_limit_kw,
        )

    async def _write(self, value: float) -> None:
        await self._adapters[ROLE_CHARGER_CURRENT].write(value)

    async def _safe_write_zero(self) -> None:
        try:
            await self._write(0.0)
        except Exception:  # noqa: BLE001 - best-effort stop
            _LOGGER.exception("smart_charging failed to write 0 A during fault")

    def _log_fault(self, reason: str) -> None:
        if not self._was_faulted:
            _LOGGER.warning("smart_charging fault: %s", reason)
            self._was_faulted = True
