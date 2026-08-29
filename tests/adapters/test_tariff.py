"""HA-harness tests for the low-tariff adapter (ADR-0003, RA2 extension)."""

import pytest
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN

from custom_components.smart_charging.adapters.tariff import LowTariffReadAdapter

LOW_STATES = "low, off-peak"  # raw comma-separated string, matching config-entry storage
# (design doc §2)


async def test_native_on_returns_true(hass):
    hass.states.async_set("binary_sensor.tariff", STATE_ON)
    adapter = LowTariffReadAdapter(hass, "binary_sensor.tariff", "")
    assert await adapter.read() is True


async def test_native_off_returns_false(hass):
    hass.states.async_set("binary_sensor.tariff", STATE_OFF)
    adapter = LowTariffReadAdapter(hass, "binary_sensor.tariff", "")
    assert await adapter.read() is False


async def test_listed_raw_state_returns_true(hass):
    hass.states.async_set("sensor.tariff", "low")
    adapter = LowTariffReadAdapter(hass, "sensor.tariff", LOW_STATES)
    assert await adapter.read() is True


async def test_listed_raw_state_after_second_comma_element_is_stripped(hass):
    # Pins both the multi-element split and the whitespace strip: "off-peak" is the
    # second element of LOW_STATES ("low, off-peak"), with a leading space in the
    # raw string that must not survive into the parsed set.
    hass.states.async_set("sensor.tariff", "off-peak")
    adapter = LowTariffReadAdapter(hass, "sensor.tariff", LOW_STATES)
    assert await adapter.read() is True


async def test_unlisted_raw_state_returns_false(hass):
    # Not a fault (unlike StatusReadAdapter's unmapped-state case) -- a deliberate
    # restrictive default for a present-but-unmatched state (entity-catalog.md;
    # design doc §1), distinct from the glossary's permissive "always active"
    # default for a genuinely unmapped/unavailable signal (design doc §7).
    hass.states.async_set("sensor.tariff", "high")
    adapter = LowTariffReadAdapter(hass, "sensor.tariff", LOW_STATES)
    assert await adapter.read() is False


async def test_empty_states_string_returns_false_for_non_boolean_state(hass):
    hass.states.async_set("sensor.tariff", "high")
    adapter = LowTariffReadAdapter(hass, "sensor.tariff", "")
    assert await adapter.read() is False


async def test_unavailable_returns_none(hass):
    hass.states.async_set("sensor.tariff", STATE_UNAVAILABLE)
    adapter = LowTariffReadAdapter(hass, "sensor.tariff", LOW_STATES)
    assert await adapter.read() is None


async def test_unknown_returns_none(hass):
    hass.states.async_set("sensor.tariff", STATE_UNKNOWN)
    adapter = LowTariffReadAdapter(hass, "sensor.tariff", LOW_STATES)
    assert await adapter.read() is None


async def test_absent_returns_none(hass):
    adapter = LowTariffReadAdapter(hass, "sensor.tariff", LOW_STATES)
    assert await adapter.read() is None


async def test_native_on_off_takes_precedence_over_low_states(hass):
    # A native on/off entity is never expected to also carry a states list, but the
    # precedence is pinned regardless: on/off wins even if "off" were (oddly) listed.
    hass.states.async_set("binary_sensor.tariff", STATE_OFF)
    adapter = LowTariffReadAdapter(hass, "binary_sensor.tariff", "off")
    assert await adapter.read() is False


async def test_write_raises_not_implemented(hass):
    adapter = LowTariffReadAdapter(hass, "sensor.tariff", LOW_STATES)
    with pytest.raises(NotImplementedError):
        await adapter.write(True)
