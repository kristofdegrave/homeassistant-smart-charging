"""Vehicle-Limit Manager (M2, V12) -- bidirectional vehicle charge-limit sync (UC09/R6).

A Manager (system-design §4 rule 5 / ADR-0011): triggered by HA state changes and the
ActiveSocLimitChanged event, it reads inputs through adapters and writes the vehicle
through the vehicle_charge_limit adapter / adopts manual changes into
number.smart_charging_soc_limit_override. It NEVER calls or is called by the Coordinator.
No control-cycle logic, no clamps, no set-point -- see design 2026-07-21-vehicle-limit-manager.

Task 3.2 scope adds the disconnect-reset reaction (UC09 steps 7-8, R6 AC 3). Manual adoption
and the System->vehicle write are added by the plan's later tasks (3.3/4.1).
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from homeassistant.core import HomeAssistant

from ..const import (
    CHARGEABLE_STATES,
    EVENT_VEHICLE_CHARGE_LIMIT_RESET,
    ROLE_VEHICLE_CHARGE_LIMIT,
    STATE_DISCONNECTED,
)

_LOGGER = logging.getLogger(__name__)


class VehicleLimitManager:
    """Vehicle-Limit Manager (M2). Holds the adapter map and the echo-guard state.

    `_last_written_limit` (design §6) records the value this Manager itself last wrote to
    the vehicle, so a subsequent vehicle-side report equal to it is recognised as an echo
    of our own write rather than a manual change. `_last_status` backs the disconnect-edge
    detection (design §5.3).
    """

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        adapters: dict,
        entry_id: str,
        get_default_soc_limit: Callable[[], float],
        set_default_soc_limit: Callable[[float], None] | None = None,
    ) -> None:
        self._hass = hass
        self._adapters = adapters
        self._entry_id = entry_id
        self._get_default_soc_limit = get_default_soc_limit
        self._set_default_soc_limit = set_default_soc_limit
        self._last_written_limit: float | None = None
        self._last_status: str | None = None

    async def on_status_changed(self, status: str | None) -> None:
        """React to a canonical charger-status change (design §5.3). Disconnect edge -> reset."""
        was_connected = self._last_status in CHARGEABLE_STATES
        self._last_status = status
        if status == STATE_DISCONNECTED and was_connected:
            await self._reset_to_default()

    async def _reset_to_default(self) -> None:
        default = float(self._get_default_soc_limit())
        if await self._write_vehicle(default):
            self._fire(EVENT_VEHICLE_CHARGE_LIMIT_RESET, default)

    async def _write_vehicle(self, value: float) -> bool:
        """Best-effort write to the vehicle; records the value for the echo guard. Returns
        success."""
        adapter = self._adapters.get(ROLE_VEHICLE_CHARGE_LIMIT)
        if adapter is None:
            return False
        try:
            await adapter.write(value)
        except Exception as err:  # noqa: BLE001 - a just-unplugged vehicle may be unreachable (§5.3)
            _LOGGER.debug("vehicle_charge_limit write failed: %s", err)
            return False
        self._last_written_limit = value
        return True

    def _fire(self, event_type: str, limit: float) -> None:
        self._hass.bus.async_fire(event_type, {"entry_id": self._entry_id, "limit": limit})
