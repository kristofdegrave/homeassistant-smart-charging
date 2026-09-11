"""HA-harness tests for numeric adapters (ADR-0003/0009)."""

import pytest
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    PERCENTAGE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)

from custom_components.smart_charging.adapters.numeric import (
    NumericReadAdapter,
    NumericReadWriteAdapter,
    PowerKilowattReadAdapter,
    PowerWattReadAdapter,
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
    assert await adapter.read() == pytest.approx(4.09)


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


# --- PowerWattReadAdapter: ADR-0038's contract for the three W-valued roles ----------------


@pytest.mark.parametrize(
    ("state", "unit"),
    [("3705.7", "W"), ("3.7057", "kW")],
)
async def test_power_watt_adapter_normalises_to_w(hass, state, unit):
    """ADR-0038: a recognised power unit is converted to the role's documented unit. The kW
    case is issue #1007's live defect -- a grid meter reporting kW was read as W, a 1000x
    error that reached the peak clamp and the solar-surplus reading alike."""
    hass.states.async_set("sensor.net_power", state, {ATTR_UNIT_OF_MEASUREMENT: unit})
    adapter = PowerWattReadAdapter(hass, "sensor.net_power")
    assert await adapter.read() == pytest.approx(3705.7)


async def test_power_watt_adapter_absent_unit_assumes_watts(hass, caplog):
    """ADR-0038 Option E: an absent unit keeps the documented unit, because a bare number is
    common and usually correct -- rejecting it would fault a required role on installs that
    work today. The assumption is warned, not silent."""
    hass.states.async_set("sensor.net_power", "2300")
    adapter = PowerWattReadAdapter(hass, "sensor.net_power")
    assert await adapter.read() == 2300.0
    assert "sensor.net_power" in caplog.text
    assert "assuming W" in caplog.text


async def test_power_watt_adapter_present_non_power_unit_is_rejected(hass, caplog):
    """A unit that is present but not a power unit is positive evidence of a mis-mapping,
    unlike an absent one -- so it reads as None, with a rejection warning saying so."""
    hass.states.async_set("sensor.net_power", "55", {ATTR_UNIT_OF_MEASUREMENT: PERCENTAGE})
    adapter = PowerWattReadAdapter(hass, "sensor.net_power")
    assert await adapter.read() is None
    assert "sensor.net_power" in caplog.text
    assert "discarded" in caplog.text


async def test_power_watt_adapter_absent_entity_returns_none(hass):
    adapter = PowerWattReadAdapter(hass, "sensor.missing")
    assert await adapter.read() is None


async def test_power_watt_adapter_unavailable_returns_none(hass):
    hass.states.async_set("sensor.net_power", STATE_UNAVAILABLE, {ATTR_UNIT_OF_MEASUREMENT: "W"})
    adapter = PowerWattReadAdapter(hass, "sensor.net_power")
    assert await adapter.read() is None


async def test_power_watt_adapter_unknown_returns_none(hass):
    hass.states.async_set("sensor.net_power", STATE_UNKNOWN, {ATTR_UNIT_OF_MEASUREMENT: "W"})
    adapter = PowerWattReadAdapter(hass, "sensor.net_power")
    assert await adapter.read() is None


async def test_power_watt_adapter_non_numeric_returns_none(hass):
    hass.states.async_set("sensor.net_power", "not a number", {ATTR_UNIT_OF_MEASUREMENT: "W"})
    adapter = PowerWattReadAdapter(hass, "sensor.net_power")
    assert await adapter.read() is None


async def test_power_watt_adapter_write_raises_not_implemented(hass):
    adapter = PowerWattReadAdapter(hass, "sensor.net_power")
    with pytest.raises(NotImplementedError):
        await adapter.write(10.0)


# --- Warning cadence (ADR-0038: once per entity per config-entry load) ---------------------


async def test_warning_is_emitted_once_per_entity_not_once_per_read(hass, caplog):
    """ADR-0038 fixes the cadence deliberately: the control cycle reads every role every
    cycle, so a per-read warning would be log spam that trains the user to ignore exactly the
    signal this contract exists to provide."""
    hass.states.async_set("sensor.net_power", "2300")
    adapter = PowerWattReadAdapter(hass, "sensor.net_power")
    for _ in range(5):
        assert await adapter.read() == 2300.0
    assert caplog.text.count("assuming W") == 1


async def test_a_changed_unit_warns_again(hass, caplog):
    """The once-per-entity cap is keyed on the observed unit, not the adapter's lifetime -- an
    entity that starts reporting a different (still wrong) unit is a new fact the user should
    see, not a repeat of one already reported."""
    hass.states.async_set("sensor.net_power", "2300")
    adapter = PowerWattReadAdapter(hass, "sensor.net_power")
    assert await adapter.read() == 2300.0
    caplog.clear()
    hass.states.async_set("sensor.net_power", "55", {ATTR_UNIT_OF_MEASUREMENT: PERCENTAGE})
    assert await adapter.read() is None
    assert "discarded" in caplog.text


# --- PowerKilowattReadAdapter: ADR-0038's carve-out ----------------------------------------


async def test_power_kilowatt_adapter_absent_unit_warns_rather_than_failing_silently(hass, caplog):
    """ADR-0038's carve-out keeps this role's absent-unit REJECTION -- a DSO peak sensor's
    likely true unit is W while its documented unit is kW, so assuming kW would pin the
    effective peak limit at max_peak_kw. But the rejection must say so: a silent None makes
    the role vanish indistinguishably from unmapped, which is the silence this contract
    exists to end."""
    hass.states.async_set("sensor.dso_peak", "4090")
    adapter = PowerKilowattReadAdapter(hass, "sensor.dso_peak")
    assert await adapter.read() is None
    assert "sensor.dso_peak" in caplog.text
    assert "discarded" in caplog.text
    assert "assuming" not in caplog.text


async def test_power_kilowatt_adapter_non_power_unit_warns_too(hass, caplog):
    hass.states.async_set("sensor.dso_peak", "20", {ATTR_UNIT_OF_MEASUREMENT: PERCENTAGE})
    adapter = PowerKilowattReadAdapter(hass, "sensor.dso_peak")
    assert await adapter.read() is None
    assert "discarded" in caplog.text
