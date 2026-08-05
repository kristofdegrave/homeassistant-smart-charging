"""Vehicle-Limit Manager (M2, V12) -- bidirectional vehicle charge-limit sync (UC09/R6).

A Manager (system-design §4 rule 5 / ADR-0011): triggered by HA state changes and the
ActiveSocLimitChanged event, it reads inputs through adapters and writes the vehicle
through the vehicle_charge_limit adapter / adopts manual changes into
number.smart_charging_soc_limit_override. It NEVER calls or is called by the Coordinator.
No control-cycle logic, no clamps, no set-point -- see design 2026-07-21-vehicle-limit-manager.

Task 3.1 scope: the constructor and the echo-guard state only (design §6). The reaction
methods (manual adoption, disconnect reset, System->vehicle write) are added by the plan's
later tasks (3.2/3.3/4.1), which read/write `_last_written_limit` and `_last_status`.
"""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.core import HomeAssistant


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
