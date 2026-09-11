"""HA-harness tests for numeric adapters (ADR-0003/0009)."""

import logging

import pytest
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    PERCENTAGE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfPower,
)
from homeassistant.util.unit_conversion import PowerConverter

from custom_components.smart_charging.adapters.numeric import (
    _MAX_WARNED_UNITS,
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


async def test_power_kilowatt_adapter_non_power_unit_warns_too(hass, caplog):
    hass.states.async_set("sensor.dso_peak", "20", {ATTR_UNIT_OF_MEASUREMENT: PERCENTAGE})
    adapter = PowerKilowattReadAdapter(hass, "sensor.dso_peak")
    assert await adapter.read() is None
    assert "discarded" in caplog.text


async def test_a_recognised_unit_warns_about_nothing(hass, caplog):
    """The silent-success case, which nothing else pins: an implementation that warned on every
    read of a correctly-mapped W sensor would pass every other test in this file while
    producing a log line per control cycle -- exactly the spam ADR-0038's cadence rule exists
    to prevent."""
    hass.states.async_set("sensor.net_power", "2300", {ATTR_UNIT_OF_MEASUREMENT: "W"})
    adapter = PowerWattReadAdapter(hass, "sensor.net_power")
    for _ in range(5):
        assert await adapter.read() == 2300.0
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


async def test_rejection_warning_is_also_once_per_entity(hass, caplog):
    """The rejection branch needs the cadence guarantee more than the assumption branch does,
    not less: a rejected required role is a persistent fault, so it is read and rejected every
    cycle for as long as the mis-mapping stands."""
    hass.states.async_set("sensor.net_power", "55", {ATTR_UNIT_OF_MEASUREMENT: PERCENTAGE})
    adapter = PowerWattReadAdapter(hass, "sensor.net_power")
    for _ in range(5):
        assert await adapter.read() is None
    assert caplog.text.count("discarded") == 1


async def test_kilowatt_absent_unit_rejection_warning_is_once_per_entity(hass, caplog):
    """Same guarantee for the branch ADR-0038 added -- the carve-out's own rejection."""
    hass.states.async_set("sensor.dso_peak", "4090")
    adapter = PowerKilowattReadAdapter(hass, "sensor.dso_peak")
    for _ in range(5):
        assert await adapter.read() is None
    assert caplog.text.count("discarded") == 1


async def test_warning_state_is_per_adapter_not_shared_across_entities(hass, caplog):
    """Two entities, two warnings. Holding the warned-unit set on the class instead of the
    instance would silence the second entity entirely, and every other test in this file --
    all single-adapter -- would still pass."""
    hass.states.async_set("sensor.net_power", "2300")
    hass.states.async_set("sensor.charger_power", "1100")
    first = PowerWattReadAdapter(hass, "sensor.net_power")
    second = PowerWattReadAdapter(hass, "sensor.charger_power")
    assert await first.read() == 2300.0
    assert await second.read() == 1100.0
    assert "sensor.net_power" in caplog.text
    assert "sensor.charger_power" in caplog.text


async def test_a_flapping_unit_stops_warning_once_bounded(hass, caplog):
    """Keying warnings on the observed unit means a templated, flapping unit_of_measurement
    would otherwise warn forever and grow the set without limit. Past the cap the adapter goes
    quiet rather than becoming the spam the cadence rule exists to prevent."""
    adapter = PowerWattReadAdapter(hass, "sensor.net_power")
    for i in range(_MAX_WARNED_UNITS + 5):
        hass.states.async_set("sensor.net_power", "10", {ATTR_UNIT_OF_MEASUREMENT: f"bogus{i}"})
        assert await adapter.read() is None
    assert caplog.text.count("discarded") == _MAX_WARNED_UNITS


async def test_every_ha_power_unit_converts_not_just_w_and_kw(hass):
    """`PowerConverter.VALID_UNITS` is exactly `set(UnitOfPower)`, so the contract is "any power
    unit HA knows", not "W or kW". BTU/h is the member most likely to be assumed unsupported --
    pinned here so a future narrowing of the accepted set is a deliberate choice rather than a
    silent one."""
    hass.states.async_set("sensor.net_power", "12000", {ATTR_UNIT_OF_MEASUREMENT: "BTU/h"})
    adapter = PowerWattReadAdapter(hass, "sensor.net_power")
    assert await adapter.read() == pytest.approx(3516.85, abs=0.01)


async def test_a_near_miss_unit_spelling_is_rejected_with_an_actionable_message(hass, caplog):
    """The realistic mis-mapping is not a wrong quantity but a wrong string on an otherwise
    correct sensor. The message points at the unit rather than diagnosing the entity, because
    "is not a power unit" sends the user looking in the wrong place."""
    hass.states.async_set("sensor.net_power", "2300", {ATTR_UNIT_OF_MEASUREMENT: "Watt"})
    adapter = PowerWattReadAdapter(hass, "sensor.net_power")
    assert await adapter.read() is None
    assert "cannot be converted" in caplog.text
    assert "unit string itself" in caplog.text


async def test_the_cap_never_silences_the_absent_unit_warning(hass, caplog):
    """The cap exists to bound unbounded unit STRINGS, and must not take the absent-unit
    warning with it. An entity that flaps through the cap and then settles on reporting no unit
    at all would otherwise be assumed silently forever -- the exact silence ADR-0038 exists to
    end, reached by a pathological but reachable route."""
    adapter = PowerWattReadAdapter(hass, "sensor.net_power")
    for i in range(_MAX_WARNED_UNITS + 5):
        hass.states.async_set("sensor.net_power", "10", {ATTR_UNIT_OF_MEASUREMENT: f"bogus{i}"})
        assert await adapter.read() is None
    caplog.clear()

    hass.states.async_set("sensor.net_power", "2300")
    assert await adapter.read() == 2300.0
    assert "assuming W" in caplog.text


async def test_reaching_the_cap_says_so_rather_than_just_going_quiet(hass, caplog):
    """A log that stops mentioning an entity reads the same as a mapping that got fixed. One
    terminal line distinguishes "capped by policy" from "resolved", which matters most to the
    user debugging the flapping sensor that caused the cap."""
    adapter = PowerWattReadAdapter(hass, "sensor.net_power")
    for i in range(_MAX_WARNED_UNITS + 5):
        hass.states.async_set("sensor.net_power", "10", {ATTR_UNIT_OF_MEASUREMENT: f"bogus{i}"})
        assert await adapter.read() is None
    assert caplog.text.count("will not be warned about") == 1


def test_every_ha_power_unit_is_convertible():
    """Pins the identity the rejection-branch comment asserts. The code tests membership in
    VALID_UNITS itself, so it stays correct either way -- but if HA ever ships a power unit its
    own converter cannot handle, this fails loudly instead of leaving a stale comment."""
    assert PowerConverter.VALID_UNITS == set(UnitOfPower)
