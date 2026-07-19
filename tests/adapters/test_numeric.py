"""HA-harness tests for numeric adapters (ADR-0003/0009)."""

from homeassistant.const import STATE_UNAVAILABLE

from custom_components.smart_charging.adapters.numeric import (
    NumericReadAdapter,
    NumericReadWriteAdapter,
)


async def test_reads_native_float(hass):
    hass.states.async_set("sensor.net_power", "2300.0")
    adapter = NumericReadAdapter(hass, "sensor.net_power")
    assert await adapter.read() == 2300.0


async def test_read_absent_entity_returns_none(hass):
    adapter = NumericReadAdapter(hass, "sensor.missing")
    assert await adapter.read() is None


async def test_read_unavailable_returns_none(hass):
    hass.states.async_set("sensor.net_power", STATE_UNAVAILABLE)
    adapter = NumericReadAdapter(hass, "sensor.net_power")
    assert await adapter.read() is None


async def test_read_non_numeric_returns_none(hass):
    hass.states.async_set("sensor.net_power", "not-a-number")
    adapter = NumericReadAdapter(hass, "sensor.net_power")
    assert await adapter.read() is None


async def test_write_calls_number_set_value(hass):
    calls = []

    async def _record(call):
        calls.append(call.data)

    hass.services.async_register("number", "set_value", _record)
    hass.states.async_set("number.charger_current", "6.0")
    adapter = NumericReadWriteAdapter(hass, "number.charger_current")
    await adapter.write(10.0)
    await hass.async_block_till_done()
    assert calls and calls[0]["value"] == 10.0
    assert calls[0]["entity_id"] == "number.charger_current"
