"""End-to-end setup test (M1 + C1 + C2 + adapters)."""

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_charging.const import (
    CONF_CHARGER_CURRENT_ENTITY,
    CONF_CHARGER_POWER_ENTITY,
    CONF_CHARGER_STATUS_ENTITY,
    CONF_DEFAULT_TARGET_CURRENT,
    CONF_GRID_CEILING_A,
    CONF_GRID_SAFETY_OFFSET_A,
    CONF_GRID_VOLTAGE_ENTITY,
    CONF_MAX_CURRENT,
    CONF_MIN_CURRENT,
    CONF_NET_POWER_ENTITY,
    CONF_NOMINAL_VOLTAGE,
    CONF_STATUS_TRANSLATION,
    DOMAIN,
)


def _entry_data():
    """DATA bucket — entity-role mappings + translation only (ADR-0005)."""
    return {
        CONF_CHARGER_CURRENT_ENTITY: "number.charger_current",
        CONF_CHARGER_STATUS_ENTITY: "sensor.evse",
        CONF_STATUS_TRANSLATION: {"Charging": "charging", "Connected": "connected"},
        CONF_NET_POWER_ENTITY: "sensor.net_power",
        CONF_CHARGER_POWER_ENTITY: "sensor.charger_power",
        CONF_GRID_VOLTAGE_ENTITY: "sensor.grid_voltage",
    }


def _entry_options():
    """OPTIONS bucket — thresholds/defaults + interval (ADR-0005)."""
    return {
        CONF_NOMINAL_VOLTAGE: 230.0,
        CONF_MIN_CURRENT: 6.0,
        CONF_MAX_CURRENT: 16.0,
        CONF_GRID_CEILING_A: 25.0,
        CONF_GRID_SAFETY_OFFSET_A: 2.0,
        CONF_DEFAULT_TARGET_CURRENT: 10.0,
    }


async def test_end_to_end_commands_target_current(hass):
    # The real `number` platform (loaded via PLATFORMS) registers its own set_value
    # service handler on setup, so a fake `async_register` gets clobbered; listen for
    # the call_service event instead — it fires for every call regardless of handler.
    calls = []
    hass.bus.async_listen(
        "call_service",
        lambda event: (
            calls.append(event.data["service_data"])
            if event.data["service"] == "set_value"
            else None
        ),
    )

    hass.states.async_set("number.charger_current", "0.0")
    hass.states.async_set("sensor.evse", "Charging")
    hass.states.async_set("sensor.net_power", "0.0")
    hass.states.async_set("sensor.charger_power", "0.0")
    hass.states.async_set("sensor.grid_voltage", "230.0")

    entry = MockConfigEntry(domain=DOMAIN, data=_entry_data(), options=_entry_options())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # The number entity exists (object_id is just the device name until Task 6.3 adds
    # strings.json translations for _attr_translation_key)...
    assert hass.states.get("number.smart_charging") is not None
    # ...and the first cycle wrote the target current to the charger.
    assert calls and calls[-1]["value"] == 10.0
    # ...and the status sensor is OK.
    assert hass.states.get("sensor.smart_charging").state == "OK"


async def test_end_to_end_disconnect_forces_zero_and_fault(hass):
    calls = []
    hass.bus.async_listen(
        "call_service",
        lambda event: (
            calls.append(event.data["service_data"])
            if event.data["service"] == "set_value"
            else None
        ),
    )

    hass.states.async_set("number.charger_current", "0.0")
    hass.states.async_set("sensor.evse", "Unplugged")  # unmapped raw state -> None (ADR-0003/0007)
    hass.states.async_set("sensor.net_power", "0.0")
    hass.states.async_set("sensor.charger_power", "0.0")
    hass.states.async_set("sensor.grid_voltage", "230.0")

    entry = MockConfigEntry(domain=DOMAIN, data=_entry_data(), options=_entry_options())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert calls and calls[-1]["value"] == 0.0
    assert hass.states.get("sensor.smart_charging").state == "Fault"
