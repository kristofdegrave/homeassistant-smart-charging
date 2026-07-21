"""End-to-end setup test (M1 + C1 + C2 + adapters)."""

from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_charging.const import (
    CONF_CHARGER_CURRENT_ENTITY,
    CONF_CHARGER_POWER_ENTITY,
    CONF_CHARGER_STATUS_ENTITY,
    CONF_DEFAULT_SOC_LIMIT,
    CONF_DEFAULT_TARGET_CURRENT,
    CONF_EV_SOC_ENTITY,
    CONF_GRID_CEILING_A,
    CONF_GRID_SAFETY_OFFSET_A,
    CONF_GRID_VOLTAGE_ENTITY,
    CONF_MAX_CURRENT,
    CONF_MIN_CURRENT,
    CONF_NET_POWER_ENTITY,
    CONF_NOMINAL_VOLTAGE,
    CONF_SOLAR_INSTALLED,
    CONF_STATUS_TRANSLATION,
    DOMAIN,
    MODE_POWER,
    MODE_SOLAR,
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
    # ...the mode selector defaults to Off when never set (T6.1/design doc §2 criterion 1) --
    # select Power explicitly, same as a real install's first manual step.
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    coordinator.active_mode = MODE_POWER
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # ...and that cycle wrote the target current to the charger.
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


async def test_select_entity_is_registered_on_setup(hass):
    """T6.1: the select platform must be forwarded alongside number/sensor. Looked up by
    unique_id, not entity_id -- the "_mode"-suffixed entity_id depends on the select.mode
    translation entry that T6.3 (strings/translations) adds, not this task."""
    _seed_states(hass, status="Charging")
    data = _entry_data()
    data[CONF_SOLAR_INSTALLED] = True
    data[CONF_EV_SOC_ENTITY] = "sensor.ev_soc"
    hass.states.async_set("sensor.ev_soc", "50.0")

    entry = MockConfigEntry(domain=DOMAIN, data=data, options=_entry_options())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("select", DOMAIN, f"{entry.entry_id}_mode")
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes["options"] == ["Off", "Power", "Solar", "SolarOnly"]


async def test_end_to_end_solar_mode_uses_configured_thresholds(hass):
    """T6.1: the new Solar/SolarOnly options must be threaded into the coordinator's
    config dict -- without it, dispatching to Solar mode KeyErrors on
    CONF_SOLAR_START_THRESHOLD_W (coordinator.py reads it unconditionally, no default)."""
    calls = _capture_charger_current_writes(hass)
    _seed_states(hass, status="Charging")
    hass.states.async_set("sensor.charger_power", "2300.0")  # ample surplus
    data = _entry_data()
    data[CONF_EV_SOC_ENTITY] = "sensor.ev_soc"
    hass.states.async_set("sensor.ev_soc", "50.0")

    entry = MockConfigEntry(domain=DOMAIN, data=data, options=_entry_options())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    coordinator.active_mode = MODE_SOLAR
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get("sensor.smart_charging_status").state == "OK"
    assert calls[-1]["value"] > 0.0
