"""HA-harness tests for numeric adapters (ADR-0003/0009)."""

import pytest
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, STATE_UNAVAILABLE, STATE_UNKNOWN

from custom_components.smart_charging.adapters.numeric import (
    NumericReadAdapter,
    NumericReadWriteAdapter,
    PowerKilowattReadAdapter,
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


async def test_read_unknown_returns_none(hass):
    hass.states.async_set("sensor.net_power", STATE_UNKNOWN)
    adapter = NumericReadAdapter(hass, "sensor.net_power")
    assert await adapter.read() is None


async def test_read_only_write_raises_not_implemented(hass):
    adapter = NumericReadAdapter(hass, "sensor.net_power")
    with pytest.raises(NotImplementedError):
        await adapter.write(10.0)


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


@pytest.mark.parametrize(
    ("state", "unit"),
    [("4090", "W"), ("4.09", "kW")],
)
async def test_power_kilowatt_adapter_normalises_to_kw(hass, state, unit):
    hass.states.async_set("sensor.dso_peak", state, {ATTR_UNIT_OF_MEASUREMENT: unit})
    adapter = PowerKilowattReadAdapter(hass, "sensor.dso_peak")
    assert await adapter.read() == 4.09


async def test_power_kilowatt_adapter_absent_entity_returns_none(hass):
    adapter = PowerKilowattReadAdapter(hass, "sensor.missing")
    assert await adapter.read() is None


async def test_power_kilowatt_adapter_unavailable_returns_none(hass):
    hass.states.async_set("sensor.dso_peak", STATE_UNAVAILABLE, {ATTR_UNIT_OF_MEASUREMENT: "W"})
    adapter = PowerKilowattReadAdapter(hass, "sensor.dso_peak")
    assert await adapter.read() is None


async def test_power_kilowatt_adapter_unknown_returns_none(hass):
    hass.states.async_set("sensor.dso_peak", STATE_UNKNOWN, {ATTR_UNIT_OF_MEASUREMENT: "W"})
    adapter = PowerKilowattReadAdapter(hass, "sensor.dso_peak")
    assert await adapter.read() is None


async def test_power_kilowatt_adapter_non_numeric_returns_none(hass):
    hass.states.async_set("sensor.dso_peak", "not a number", {ATTR_UNIT_OF_MEASUREMENT: "W"})
    adapter = PowerKilowattReadAdapter(hass, "sensor.dso_peak")
    assert await adapter.read() is None


async def test_power_kilowatt_adapter_missing_unit_returns_none(hass):
    hass.states.async_set("sensor.dso_peak", "4090")
    adapter = PowerKilowattReadAdapter(hass, "sensor.dso_peak")
    assert await adapter.read() is None


async def test_power_kilowatt_adapter_non_power_unit_returns_none(hass):
    hass.states.async_set("sensor.dso_peak", "20", {ATTR_UNIT_OF_MEASUREMENT: "°C"})
    adapter = PowerKilowattReadAdapter(hass, "sensor.dso_peak")
    assert await adapter.read() is None
