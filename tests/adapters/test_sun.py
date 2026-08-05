"""HA-harness tests for the sun-state adapter (ADR-0003 extension, issue #376)."""

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

from custom_components.smart_charging.adapters.sun import (
    SUN_ENTITY_ID,
    SUN_STATE_ABOVE_HORIZON,
    SUN_STATE_BELOW_HORIZON,
    SunReadAdapter,
)


async def test_reads_above_horizon(hass):
    hass.states.async_set(SUN_ENTITY_ID, SUN_STATE_ABOVE_HORIZON)
    adapter = SunReadAdapter(hass)
    assert await adapter.read() == SUN_STATE_ABOVE_HORIZON


async def test_reads_below_horizon(hass):
    hass.states.async_set(SUN_ENTITY_ID, SUN_STATE_BELOW_HORIZON)
    adapter = SunReadAdapter(hass)
    assert await adapter.read() == SUN_STATE_BELOW_HORIZON


async def test_read_absent_entity_returns_none(hass):
    adapter = SunReadAdapter(hass)
    assert await adapter.read() is None


async def test_read_unavailable_returns_none(hass):
    hass.states.async_set(SUN_ENTITY_ID, STATE_UNAVAILABLE)
    adapter = SunReadAdapter(hass)
    assert await adapter.read() is None


async def test_read_unknown_returns_none(hass):
    hass.states.async_set(SUN_ENTITY_ID, STATE_UNKNOWN)
    adapter = SunReadAdapter(hass)
    assert await adapter.read() is None


async def test_read_only_write_raises_not_implemented(hass):
    adapter = SunReadAdapter(hass)
    with pytest.raises(NotImplementedError):
        await adapter.write(SUN_STATE_ABOVE_HORIZON)
