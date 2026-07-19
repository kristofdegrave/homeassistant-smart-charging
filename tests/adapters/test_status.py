"""HA-harness tests for the charger-status adapter (ADR-0003)."""

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

from custom_components.smart_charging.adapters.status import StatusAdapter
from custom_components.smart_charging.const import STATE_CHARGING, STATE_CONNECTED

# Many raw values collapse onto one canonical state.
TRANSLATION = {
    "Charging": STATE_CHARGING,
    "SuspendedEV": STATE_CHARGING,
    "Connected": STATE_CONNECTED,
    "Cable": STATE_CONNECTED,
}


async def test_translates_raw_to_canonical(hass):
    hass.states.async_set("sensor.evse", "Charging")
    adapter = StatusAdapter(hass, "sensor.evse", TRANSLATION)
    assert await adapter.read() == STATE_CHARGING


async def test_many_to_one_mapping(hass):
    hass.states.async_set("sensor.evse", "SuspendedEV")
    adapter = StatusAdapter(hass, "sensor.evse", TRANSLATION)
    assert await adapter.read() == STATE_CHARGING


async def test_unmapped_raw_state_returns_none(hass):
    # An unmapped firmware state is treated as missing data (ADR-0003 -> ADR-0007 fault).
    hass.states.async_set("sensor.evse", "FirmwareGremlin")
    adapter = StatusAdapter(hass, "sensor.evse", TRANSLATION)
    assert await adapter.read() is None


async def test_unavailable_returns_none(hass):
    hass.states.async_set("sensor.evse", STATE_UNAVAILABLE)
    adapter = StatusAdapter(hass, "sensor.evse", TRANSLATION)
    assert await adapter.read() is None


async def test_unknown_returns_none(hass):
    hass.states.async_set("sensor.evse", STATE_UNKNOWN)
    adapter = StatusAdapter(hass, "sensor.evse", TRANSLATION)
    assert await adapter.read() is None


async def test_absent_returns_none(hass):
    adapter = StatusAdapter(hass, "sensor.evse", TRANSLATION)
    assert await adapter.read() is None


async def test_write_raises_not_implemented(hass):
    adapter = StatusAdapter(hass, "sensor.evse", TRANSLATION)
    with pytest.raises(NotImplementedError):
        await adapter.write(STATE_CHARGING)
