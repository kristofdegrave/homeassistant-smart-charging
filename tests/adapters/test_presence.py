"""HA-harness tests for the presence (car_home) read adapter (RA2 role, ADR-0003)."""

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

from custom_components.smart_charging.adapters.presence import PresenceReadAdapter


async def test_home_states_read_true(hass):
    hass.states.async_set("device_tracker.car", "home")
    assert await PresenceReadAdapter(hass, "device_tracker.car").read() is True
    hass.states.async_set("binary_sensor.car_home", "on")
    assert await PresenceReadAdapter(hass, "binary_sensor.car_home").read() is True


async def test_away_states_read_false(hass):
    hass.states.async_set("device_tracker.car", "not_home")
    assert await PresenceReadAdapter(hass, "device_tracker.car").read() is False
    hass.states.async_set("binary_sensor.car_home", "off")
    assert await PresenceReadAdapter(hass, "binary_sensor.car_home").read() is False


async def test_missing_or_unavailable_reads_none(hass):
    assert await PresenceReadAdapter(hass, "device_tracker.absent").read() is None
    hass.states.async_set("device_tracker.car", STATE_UNAVAILABLE)
    assert await PresenceReadAdapter(hass, "device_tracker.car").read() is None


async def test_unknown_reads_none(hass):
    hass.states.async_set("device_tracker.car", STATE_UNKNOWN)
    assert await PresenceReadAdapter(hass, "device_tracker.car").read() is None


async def test_unrecognized_zone_state_reads_false(hass):
    # A person entity in a named zone (not "home") is still "not at home" for the C2
    # gate this role backs -- deliberately not the ADR-0007 None/fault path (design §9.1).
    hass.states.async_set("person.driver", "work")
    assert await PresenceReadAdapter(hass, "person.driver").read() is False


async def test_write_is_not_supported(hass):
    with pytest.raises(NotImplementedError):
        await PresenceReadAdapter(hass, "device_tracker.car").write(True)
