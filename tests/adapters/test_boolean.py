"""HA-harness tests for the boolean-flag adapter (ADR-0003 extension, Task 2.1/RA2)."""

import pytest
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN

from custom_components.smart_charging.adapters.boolean import BooleanReadAdapter


async def test_reads_on_as_true(hass):
    hass.states.async_set("binary_sensor.home_day", STATE_ON)
    adapter = BooleanReadAdapter(hass, "binary_sensor.home_day")
    assert await adapter.read() is True


async def test_reads_off_as_false(hass):
    hass.states.async_set("binary_sensor.home_day", STATE_OFF)
    adapter = BooleanReadAdapter(hass, "binary_sensor.home_day")
    assert await adapter.read() is False


async def test_read_absent_entity_returns_none(hass):
    adapter = BooleanReadAdapter(hass, "binary_sensor.missing")
    assert await adapter.read() is None


async def test_read_unavailable_returns_none(hass):
    hass.states.async_set("binary_sensor.home_day", STATE_UNAVAILABLE)
    adapter = BooleanReadAdapter(hass, "binary_sensor.home_day")
    assert await adapter.read() is None


async def test_read_unknown_returns_none(hass):
    hass.states.async_set("binary_sensor.home_day", STATE_UNKNOWN)
    adapter = BooleanReadAdapter(hass, "binary_sensor.home_day")
    assert await adapter.read() is None


async def test_read_unrecognized_state_returns_none(hass):
    hass.states.async_set("binary_sensor.home_day", "maybe")
    adapter = BooleanReadAdapter(hass, "binary_sensor.home_day")
    assert await adapter.read() is None


async def test_read_only_write_raises_not_implemented(hass):
    adapter = BooleanReadAdapter(hass, "binary_sensor.home_day")
    with pytest.raises(NotImplementedError):
        await adapter.write(True)
