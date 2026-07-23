"""HA-harness tests for the time-of-day adapter (ADR-0003 extension, Task 2.1/RA2)."""

from datetime import time

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

from custom_components.smart_charging.adapters.time_read import TimeReadAdapter


async def test_reads_native_time(hass):
    hass.states.async_set("sensor.departure_time", "07:30:00")
    adapter = TimeReadAdapter(hass, "sensor.departure_time")
    assert await adapter.read() == time(7, 30, 0)


async def test_read_absent_entity_returns_none(hass):
    adapter = TimeReadAdapter(hass, "sensor.missing")
    assert await adapter.read() is None


async def test_read_unavailable_returns_none(hass):
    hass.states.async_set("sensor.departure_time", STATE_UNAVAILABLE)
    adapter = TimeReadAdapter(hass, "sensor.departure_time")
    assert await adapter.read() is None


async def test_read_unknown_returns_none(hass):
    hass.states.async_set("sensor.departure_time", STATE_UNKNOWN)
    adapter = TimeReadAdapter(hass, "sensor.departure_time")
    assert await adapter.read() is None


async def test_read_unparseable_state_returns_none(hass):
    # R14: the external sensor "currently reports no deadline" -- represented as a
    # non-time-parseable native state, same ADR-0007 fault/None signal as every other role.
    hass.states.async_set("sensor.departure_time", "no deadline")
    adapter = TimeReadAdapter(hass, "sensor.departure_time")
    assert await adapter.read() is None


async def test_read_only_write_raises_not_implemented(hass):
    adapter = TimeReadAdapter(hass, "sensor.departure_time")
    with pytest.raises(NotImplementedError):
        await adapter.write(time(7, 30))
