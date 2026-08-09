"""HA-harness tests for the Vehicle-Limit Manager (M2 -- UC09/R6/ADR-0011).

Covers the skeleton constructor/echo-guard state (Task 3.1) and the disconnect-reset
reaction (Task 3.2, UC09 steps 7-8, R6 AC 3). Drives M2 through its public reaction methods
directly (not HA listener plumbing -- that is Phase 5's job).
"""

from custom_components.smart_charging.const import (
    EVENT_VEHICLE_CHARGE_LIMIT_RESET,
    ROLE_CAR_HOME,
    ROLE_CHARGER_STATUS,
    ROLE_VEHICLE_CHARGE_LIMIT,
    STATE_CONNECTED,
    STATE_DISCONNECTED,
)
from custom_components.smart_charging.managers.vehicle_limit import VehicleLimitManager


def _capture(hass, event_type):
    events = []
    hass.bus.async_listen(event_type, events.append)
    return events


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


async def test_disconnect_from_connected_resets_vehicle_to_default(hass):
    """UC09 step 8 / R6 AC 3: connected->disconnected writes the default (80%) to the vehicle."""
    m = _manager(hass, vehicle=65.0, soc_override=80.0)
    m._last_status = STATE_CONNECTED
    events = _capture(hass, EVENT_VEHICLE_CHARGE_LIMIT_RESET)
    await m.on_status_changed(STATE_DISCONNECTED)
    assert m._adapters[ROLE_VEHICLE_CHARGE_LIMIT].writes == [80.0]
    assert m._last_written_limit == 80.0  # recorded for the echo guard
    assert len(events) == 1


async def test_disconnected_non_edge_is_a_noop(hass):
    """No prior connected status -> no reset (design §5.3 edge detection)."""
    m = _manager(hass, vehicle=65.0)
    m._last_status = STATE_DISCONNECTED
    await m.on_status_changed(STATE_DISCONNECTED)
    assert m._adapters[ROLE_VEHICLE_CHARGE_LIMIT].writes == []


async def test_reset_write_failure_is_swallowed(hass):
    """A just-unplugged vehicle may be unreachable -- best-effort write (design §5.3)."""
    m = _manager(hass)
    m._last_status = STATE_CONNECTED

    async def _boom(_value):
        raise RuntimeError("vehicle offline")

    m._adapters[ROLE_VEHICLE_CHARGE_LIMIT].write = _boom
    await m.on_status_changed(STATE_DISCONNECTED)  # must not raise
