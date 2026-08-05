"""HA-harness tests for the Vehicle-Limit Manager (M2 -- UC09/R6/ADR-0011).

Task 3.1 scope: the skeleton constructor and the echo-guard state only. Drives M2 through
its public reaction methods directly (not HA listener plumbing -- that is Phase 5's job);
this task adds no reaction methods yet, so the one test here only exercises construction.
"""

from custom_components.smart_charging.const import (
    ROLE_CAR_HOME,
    ROLE_CHARGER_STATUS,
    ROLE_VEHICLE_CHARGE_LIMIT,
    STATE_CONNECTED,
)
from custom_components.smart_charging.managers.vehicle_limit import VehicleLimitManager


class _RWAdapter:
    def __init__(self, value=None):
        self.value = value
        self.writes = []

    async def read(self):
        return self.value

    async def write(self, value):
        self.writes.append(value)
        self.value = value


class _ReadAdapter:
    def __init__(self, value):
        self.value = value

    async def read(self):
        return self.value


def _manager(hass, *, vehicle=80.0, home=True, status=STATE_CONNECTED, soc_override=80.0):
    adapters = {
        ROLE_VEHICLE_CHARGE_LIMIT: _RWAdapter(vehicle),
        ROLE_CAR_HOME: _ReadAdapter(home),
        ROLE_CHARGER_STATUS: _ReadAdapter(status),
    }
    return VehicleLimitManager(
        hass, adapters=adapters, entry_id="abc", get_default_soc_limit=lambda: soc_override
    )


async def test_manager_starts_with_no_recorded_write(hass):
    """UC09 design §6: the echo guard initialises empty -- nothing written yet."""
    m = _manager(hass)
    assert m._last_written_limit is None
