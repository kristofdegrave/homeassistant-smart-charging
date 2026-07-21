"""End-to-end setup test (M1 + C1 + C2 + adapters)."""

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_charging.const import (
    CONF_CHARGER_CURRENT_ENTITY,
    CONF_CHARGER_POWER_ENTITY,
    CONF_CHARGER_STATUS_ENTITY,
    CONF_DEFAULT_SOC_LIMIT,
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
        CONF_DEFAULT_SOC_LIMIT: 80.0,
    }


def _capture_charger_current_writes(hass):
    """Capture number.set_value calls targeting the charger-current entity.

    The real `number` platform (loaded via PLATFORMS) registers its own set_value
    service handler on setup, so a fake `hass.services.async_register` stand-in gets
    clobbered; listen for the call_service event instead — it fires for every call
    regardless of which handler is installed.
    """
    calls = []

    def _record(event):
        if event.data["domain"] == "number" and event.data["service"] == "set_value":
            calls.append(event.data["service_data"])

    hass.bus.async_listen("call_service", _record)
    return calls


def _seed_states(hass, *, status: str) -> None:
    hass.states.async_set("number.charger_current", "0.0")
    hass.states.async_set("sensor.evse", status)
    hass.states.async_set("sensor.net_power", "0.0")
    hass.states.async_set("sensor.charger_power", "0.0")
    hass.states.async_set("sensor.grid_voltage", "230.0")


async def test_end_to_end_commands_target_current(hass):
    calls = _capture_charger_current_writes(hass)
    _seed_states(hass, status="Charging")

    entry = MockConfigEntry(domain=DOMAIN, data=_entry_data(), options=_entry_options())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # The number entity exists, its object_id suffixed per strings.json translations...
    assert hass.states.get("number.smart_charging_target_current") is not None
    # ...and the first cycle wrote the target current to the charger.
    assert calls and calls[-1]["entity_id"] == "number.charger_current"
    assert calls[-1]["value"] == 10.0
    # ...and the status sensor is OK.
    assert hass.states.get("sensor.smart_charging_status").state == "OK"


async def test_setup_falls_back_to_default_soc_limit_for_pre_solar_entries(hass):
    """A config entry created before this option existed must still set up (no migration)."""
    _seed_states(hass, status="Charging")
    options = _entry_options()
    del options[CONF_DEFAULT_SOC_LIMIT]

    entry = MockConfigEntry(domain=DOMAIN, data=_entry_data(), options=options)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("number.smart_charging_default_charge_limit")
    assert state is not None
    assert float(state.state) == 80.0


async def test_end_to_end_disconnect_forces_zero_and_fault(hass):
    calls = _capture_charger_current_writes(hass)
    _seed_states(hass, status="Unplugged")  # unmapped raw state -> None (ADR-0003/0007)

    entry = MockConfigEntry(domain=DOMAIN, data=_entry_data(), options=_entry_options())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert calls and calls[-1]["entity_id"] == "number.charger_current"
    assert calls[-1]["value"] == 0.0
    assert hass.states.get("sensor.smart_charging_status").state == "Fault"
