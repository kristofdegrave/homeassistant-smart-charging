"""Charging Coordinator (M1) — the control cycle (ADR-0006/0007)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CHARGEABLE_STATES,
    DEFAULT_SMOOTHING_WINDOW,
    DEFAULT_SOC_LIMIT,
    DOMAIN,
    MODE_OFF,
    MODE_POWER,
    MODE_SOLAR,
    MODE_SOLAR_ONLY,
)
from .engines.cycle_invariant import apply_floor_cap
from .engines.grid_safety import clamp_to_ceiling
from .engines.signal_conditioning import resolve_voltage, smooth_net_power
from .engines.soc_target import resolve_active_soc_limit
from .modes import power, solar, solar_only

_LOGGER = logging.getLogger(__name__)

_SOLAR_MODES = (MODE_SOLAR, MODE_SOLAR_ONLY)


@dataclass
class CycleResult:
    """Outcome of one control cycle: the amps actually written and whether it faulted."""

    commanded_current: float
    fault: bool
    active_mode: str


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
        # Single source of truth for the setpoint is the number entity, which seeds this on
        # add (restored value, else configured default). 0 A is the safe default for cycle 0.
        self.target_current: float = 0.0
        # Single source of truth for these is their owning entity (select/number), which seeds
        # them on add (restored value, else configured default). Defaults to Power (not Off) so
        # that a config entry set up before the select platform is registered (Task 6.1) keeps
        # its pre-existing Power-mode MVP behavior rather than going idle.
        self.active_mode: str = MODE_POWER
        self.soc_limit_override: float = DEFAULT_SOC_LIMIT
        self._last_active_mode: str | None = None
        self._net_window: tuple[float, ...] = ()
        self._mode_state = {
            MODE_SOLAR: solar.SolarState.idle(),
            MODE_SOLAR_ONLY: solar_only.SolarOnlyState.idle(),
        }
        self._was_faulted = False

    async def _async_update_data(self) -> CycleResult:
        try:
            return await self._run_cycle()
        except Exception as err:  # noqa: BLE001 - every failure funnels to the fault path (ADR-0007)
            self._log_fault(f"cycle exception: {err}")
            await self._safe_write_zero()
            return CycleResult(commanded_current=0.0, fault=True, active_mode=self.active_mode)

    async def _run_cycle(self) -> CycleResult:
        status = await self._adapters["charger_status"].read()
        net_w = await self._adapters["net_power"].read()
        charger_w = await self._adapters["charger_power"].read()

        # Grid voltage is the one role where None is NOT a fault (NF4).
        measured_v = None
        if "grid_voltage" in self._adapters:
            measured_v = await self._adapters["grid_voltage"].read()
        voltage = resolve_voltage(measured_v, self._config["nominal_voltage"])

        # Any required role missing -> fault (ADR-0007).
        if status is None or net_w is None or charger_w is None:
            self._log_fault("required adapter returned None")
            await self._write(0.0)
            return CycleResult(commanded_current=0.0, fault=True, active_mode=self.active_mode)

        if self.active_mode != self._last_active_mode:
            # R11: switching mode resets timers -- fresh state for both solar modes, whether or
            # not the incoming mode is one of them (a state nobody is dispatching to is inert
            # either way).
            self._mode_state = {
                MODE_SOLAR: solar.SolarState.idle(),
                MODE_SOLAR_ONLY: solar_only.SolarOnlyState.idle(),
            }
            self._last_active_mode = self.active_mode

        # ev_soc is read -- and its absence is a fault -- ONLY while a solar mode is selected AND
        # the car is connected (success-criterion 6 / S2: Power/Off must not regress to needing
        # an SOC sensor; a disconnected car is a clean idle stop, not a fault, even if its SOC
        # sensor also goes unavailable on unplug, per UC01/R7).
        ev_soc = None
        if self.active_mode in _SOLAR_MODES and status in CHARGEABLE_STATES:
            ev_soc = await self._adapters["ev_soc"].read() if "ev_soc" in self._adapters else None
            if ev_soc is None:
                self._log_fault("ev_soc required while a solar mode is active but missing/None")
                await self._write(0.0)
                return CycleResult(commanded_current=0.0, fault=True, active_mode=self.active_mode)

        # .get(): the smoothing-window option is only wired into the config entry once Task 6.1
        # threads it through __init__.py; smoothing runs every cycle regardless of mode.
        smoothing_window = self._config.get("smoothing_window", DEFAULT_SMOOTHING_WINDOW)
        smoothed_net_w, self._net_window = smooth_net_power(
            net_w, self._net_window, size=smoothing_window
        )
        active_soc_limit = resolve_active_soc_limit(self.soc_limit_override)
        now = self.hass.loop.time()  # injected, not read inside modes/engines

        if status not in CHARGEABLE_STATES:
            desired = 0.0
            # R7/R11: disconnect resets every mode's state, clearing hold/cooldown -- and, for
            # a solar mode, also ends any SOC gate (resume condition 2: unplug/replug).
            self._mode_state = {
                MODE_SOLAR: solar.SolarState.idle(),
                MODE_SOLAR_ONLY: solar_only.SolarOnlyState.idle(),
            }
        elif self.active_mode == MODE_OFF:
            desired = 0.0
        elif self.active_mode == MODE_POWER:
            desired = power.desired_current(self.target_current, status)  # unchanged, no SOC gate
        elif self.active_mode in _SOLAR_MODES and ev_soc >= active_soc_limit:
            # R7: don't resume until the gate clears. Holding the state at idle() (rather than
            # dispatching into step()) means the next cycle where this branch stops matching --
            # because soc_limit_override rose (resume condition 1) -- dispatches fresh from
            # idle(), re-checking the start threshold normally. No latch, no separate phase.
            desired = 0.0
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
                start_threshold_w=self._config["solar_start_threshold_w"],
                min_a=self._config["min_current"],
                hold_minutes=self._config["solar_hold_min"],
                cooldown_minutes=self._config["solar_cooldown_min"],
                voltage=voltage,
            )
        else:  # MODE_SOLAR_ONLY
            surplus_w = charger_w - smoothed_net_w
            desired, self._mode_state[MODE_SOLAR_ONLY] = solar_only.step(
                surplus_w,
                self._mode_state[MODE_SOLAR_ONLY],
                now,
                start_threshold_w=self._config["solar_only_start_threshold_w"],
                min_a=self._config["min_current"],
                cooldown_minutes=self._config["solar_cooldown_min"],
                strategy=self._config["solar_only_strategy"],
                midpoint=self._config["solar_only_midpoint"],
                voltage=voltage,
            )

        desired = clamp_to_ceiling(  # E6 (before E8)
            desired,
            net_w=net_w,
            charger_w=charger_w,
            voltage=voltage,
            ceiling_a=self._config["grid_ceiling_a"],
            offset_a=self._config["grid_safety_offset_a"],
        )
        desired = apply_floor_cap(  # E8 invariant last
            desired, min_a=self._config["min_current"], max_a=self._config["max_current"]
        )

        await self._write(desired)
        if self._was_faulted:
            _LOGGER.info("smart_charging recovered from fault")
            self._was_faulted = False
        return CycleResult(commanded_current=desired, fault=False, active_mode=self.active_mode)

    async def _write(self, value: float) -> None:
        await self._adapters["charger_current"].write(value)

    async def _safe_write_zero(self) -> None:
        try:
            await self._write(0.0)
        except Exception:  # noqa: BLE001 - best-effort stop
            _LOGGER.exception("smart_charging failed to write 0 A during fault")

    def _log_fault(self, reason: str) -> None:
        if not self._was_faulted:
            _LOGGER.warning("smart_charging fault: %s", reason)
            self._was_faulted = True
