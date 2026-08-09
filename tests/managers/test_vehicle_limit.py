"""HA-harness tests for the Vehicle-Limit Manager (M2 -- UC09/R6/ADR-0011).

Covers the skeleton constructor/echo-guard state (Task 3.1, corrected to ADR-0018's Store
access shape) and the disconnect-reset reaction (Task 3.2, UC09 steps 7-8, R6 AC 3). Drives
M2 through its public reaction methods directly (not HA listener plumbing -- that is Phase
5's job).
"""

from homeassistant.const import Platform
from pytest_homeassistant_custom_component.common import async_capture_events

from custom_components.smart_charging.const import (
    ATTR_ENTRY_ID,
    ATTR_LIMIT,
    EVENT_VEHICLE_CHARGE_LIMIT_RESET,
    OWNED_SUFFIX_SOC_LIMIT_OVERRIDE,
    ROLE_CAR_HOME,
    ROLE_CHARGER_STATUS,
    ROLE_VEHICLE_CHARGE_LIMIT,
    STATE_CHARGING,
    STATE_CONNECTED,
    STATE_DISCONNECTED,
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


class _FakeStore:
    """Stands in for adapters/store.py's Store (ADR-0018) -- mirrors the double in
    tests/test_coordinator.py."""

    def __init__(self, values):
        self._values = values
        self.writes = []

    async def read(self, entity_domain, unique_id_suffix, value_type):
        return self._values.get((entity_domain, unique_id_suffix))


def _manager(hass, *, vehicle=80.0, home=True, status=STATE_CONNECTED, soc_override=80.0):
    adapters = {
        ROLE_VEHICLE_CHARGE_LIMIT: _RWAdapter(vehicle),
        ROLE_CAR_HOME: _ReadAdapter(home),
        ROLE_CHARGER_STATUS: _ReadAdapter(status),
    }
    store = _FakeStore({(Platform.NUMBER, OWNED_SUFFIX_SOC_LIMIT_OVERRIDE): soc_override})
    return VehicleLimitManager(hass, adapters=adapters, entry_id="abc", store=store)


def _manager_without_vehicle_adapter(hass, *, soc_override=80.0):
    """No ROLE_VEHICLE_CHARGE_LIMIT entry -- design success-criterion 6, M2 stays inert."""
    adapters = {
        ROLE_CAR_HOME: _ReadAdapter(True),
        ROLE_CHARGER_STATUS: _ReadAdapter(STATE_CONNECTED),
    }
    store = _FakeStore({(Platform.NUMBER, OWNED_SUFFIX_SOC_LIMIT_OVERRIDE): soc_override})
    return VehicleLimitManager(hass, adapters=adapters, entry_id="abc", store=store)


async def test_manager_starts_with_no_recorded_write(hass):
    """UC09 design §6: the echo guard initialises empty -- nothing written yet."""
    m = _manager(hass)
    assert m._last_written_limit is None


async def test_manager_starts_with_no_recorded_status(hass):
    """Disconnect detection is edge-based (design §5.3) -- nothing observed yet."""
    m = _manager(hass)
    assert m._last_status is None


async def test_disconnect_from_connected_resets_vehicle_to_default(hass):
    """UC09 step 8 / R6 AC 3: connected->disconnected writes the default (80%) to the vehicle."""
    m = _manager(hass, vehicle=65.0, soc_override=80.0)
    events = async_capture_events(hass, EVENT_VEHICLE_CHARGE_LIMIT_RESET)
    await m.on_status_changed(STATE_CONNECTED)
    await m.on_status_changed(STATE_DISCONNECTED)
    assert m._adapters[ROLE_VEHICLE_CHARGE_LIMIT].writes == [80.0]
    assert m._last_written_limit == 80.0  # recorded for the echo guard
    assert len(events) == 1
    assert events[0].data == {ATTR_ENTRY_ID: "abc", ATTR_LIMIT: 80.0}


async def test_disconnect_from_charging_resets_vehicle_to_default(hass):
    """design §5.3: the edge's origin is "connected/charging", not just "connected"."""
    m = _manager(hass, vehicle=65.0, soc_override=80.0)
    await m.on_status_changed(STATE_CHARGING)
    await m.on_status_changed(STATE_DISCONNECTED)
    assert m._adapters[ROLE_VEHICLE_CHARGE_LIMIT].writes == [80.0]


async def test_disconnected_non_edge_is_a_noop(hass):
    """No prior connected status -> no reset (design §5.3 edge detection)."""
    m = _manager(hass, vehicle=65.0)
    await m.on_status_changed(STATE_DISCONNECTED)
    await m.on_status_changed(STATE_DISCONNECTED)
    assert m._adapters[ROLE_VEHICLE_CHARGE_LIMIT].writes == []


async def test_unknown_status_reading_does_not_mask_the_edge(hass):
    """A transient unavailable/unknown status read (None) between two real readings must not
    erase the edge -- connected -> None -> disconnected still resets (design §5.3)."""
    m = _manager(hass, vehicle=65.0, soc_override=80.0)
    await m.on_status_changed(STATE_CONNECTED)
    await m.on_status_changed(None)
    await m.on_status_changed(STATE_DISCONNECTED)
    assert m._adapters[ROLE_VEHICLE_CHARGE_LIMIT].writes == [80.0]


async def test_reset_write_failure_is_swallowed(hass):
    """A just-unplugged vehicle may be unreachable -- best-effort write (design §5.3)."""
    m = _manager(hass)
    await m.on_status_changed(STATE_CONNECTED)

    async def _boom(_value):
        raise RuntimeError("vehicle offline")

    m._adapters[ROLE_VEHICLE_CHARGE_LIMIT].write = _boom
    await m.on_status_changed(STATE_DISCONNECTED)  # must not raise
    assert m._last_written_limit is None


async def test_reset_is_a_noop_when_no_default_soc_limit_is_available(hass):
    """The Store returns None when soc_limit_override is unregistered/unavailable (ADR-0018) --
    the reset must skip, not crash on float(None)."""
    m = _manager(hass, vehicle=65.0, soc_override=None)
    await m.on_status_changed(STATE_CONNECTED)
    await m.on_status_changed(STATE_DISCONNECTED)
    assert m._adapters[ROLE_VEHICLE_CHARGE_LIMIT].writes == []


async def test_reset_is_a_noop_when_vehicle_adapter_is_unmapped(hass):
    """design success-criterion 6: no vehicle_charge_limit role configured -> M2 stays inert."""
    m = _manager_without_vehicle_adapter(hass)
    await m.on_status_changed(STATE_CONNECTED)
    await m.on_status_changed(STATE_DISCONNECTED)
    assert m._last_written_limit is None
