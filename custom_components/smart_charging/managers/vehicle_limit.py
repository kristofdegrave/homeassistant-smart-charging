"""Vehicle-Limit Manager (M2, V12) -- bidirectional vehicle charge-limit sync (UC09/R6).

A Manager (system-design §4 rule 5 / ADR-0011): triggered by HA state changes and the
ActiveSocLimitChanged event, it reads inputs through adapters and writes the vehicle
through the vehicle_charge_limit adapter / adopts manual changes into
number.smart_charging_soc_limit_override. It NEVER calls or is called by the Coordinator.
No control-cycle logic, no clamps, no set-point -- see
docs/plans/2026-07-21-vehicle-limit-manager-design.md.

Homed under `managers/` per ADR-0015; `soc_limit_override` is reached through RA3's Store
(ADR-0018), never a coordinator reference, setter, or event.

Task 3.2 scope adds the disconnect-reset reaction (UC09 steps 7-8, R6 AC 3). Manual adoption
and the System->vehicle write are added by the plan's later tasks (3.3/4.1).
"""

from __future__ import annotations

import logging

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from ..adapters.base import Adapter
from ..adapters.store import Store
from ..const import (
    ATTR_ENTRY_ID,
    ATTR_LIMIT,
    CHARGEABLE_STATES,
    EVENT_VEHICLE_CHARGE_LIMIT_RESET,
    OWNED_SUFFIX_SOC_LIMIT_OVERRIDE,
    ROLE_VEHICLE_CHARGE_LIMIT,
    STATE_DISCONNECTED,
)

_LOGGER = logging.getLogger(__name__)


class VehicleLimitManager:
    """Vehicle-Limit Manager (M2). Holds the adapter map and the echo-guard state.

    `_last_written_limit` (design §6) records the value this Manager itself last wrote to
    the vehicle, so a subsequent vehicle-side report equal to it is recognised as an echo
    of our own write rather than a manual change. `_last_status` backs the disconnect-edge
    detection (design §5.3) -- an unknown/unavailable status reading (`None`) never
    overwrites it, so a transient dropout between two real readings can't erase the edge.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        adapters: dict[str, Adapter],
        entry_id: str,
        store: Store,
    ) -> None:
        self._hass = hass
        self._adapters = adapters
        self._entry_id = entry_id
        self._store = store
        self._last_written_limit: float | None = None
        self._last_status: str | None = None

    async def on_status_changed(self, status: str | None) -> None:
        """React to a canonical charger-status change (design §5.3). Disconnect edge -> reset.

        `status is None` (unregistered/unknown/unavailable read) is not a canonical state --
        it leaves `_last_status` untouched rather than being treated as "not connected", so a
        transient dropout between two real readings can't mask a genuine disconnect edge.
        """
        if status is None:
            return
        was_connected = self._last_status in CHARGEABLE_STATES
        self._last_status = status
        if status == STATE_DISCONNECTED and was_connected:
            await self._reset_to_default()

    async def _reset_to_default(self) -> None:
        default = await self._store.read(Platform.NUMBER, OWNED_SUFFIX_SOC_LIMIT_OVERRIDE, float)
        if default is None:
            _LOGGER.debug("soc_limit_override unavailable -- skipping disconnect reset")
            return
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
        self._hass.bus.async_fire(event_type, {ATTR_ENTRY_ID: self._entry_id, ATTR_LIMIT: limit})
