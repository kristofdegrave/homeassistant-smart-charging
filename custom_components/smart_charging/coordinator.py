"""Charging Coordinator (M1) — the control cycle (ADR-0006/0007)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .engines.cycle_invariant import apply_floor_cap
from .engines.grid_safety import clamp_to_ceiling
from .engines.signal_conditioning import resolve_voltage
from .modes import power

_LOGGER = logging.getLogger(__name__)


@dataclass
class CycleResult:
    commanded_current: float
    fault: bool


class SmartChargingCoordinator(DataUpdateCoordinator[CycleResult]):
    """Runs the Power-mode control cycle every interval."""

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
        self._was_faulted = False

    async def _async_update_data(self) -> CycleResult:
        try:
            return await self._run_cycle()
        except Exception as err:  # noqa: BLE001 - every failure funnels to the fault path (ADR-0007)
            self._log_fault(f"cycle exception: {err}")
            await self._safe_write_zero()
            return CycleResult(commanded_current=0.0, fault=True)

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
            return CycleResult(commanded_current=0.0, fault=True)

        desired = power.desired_current(self.target_current, status)  # E1
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
        return CycleResult(commanded_current=desired, fault=False)

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
