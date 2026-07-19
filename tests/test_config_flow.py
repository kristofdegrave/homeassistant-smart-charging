"""HA-harness config-flow tests (ADR-0005)."""

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.smart_charging.const import (
    CONF_CHARGING_STATES,
    CONF_CONNECTED_STATES,
    CONF_CONTROL_INTERVAL_S,
    CONF_GRID_CEILING_A,
    CONF_GRID_SAFETY_OFFSET_A,
    CONF_GRID_VOLTAGE_ENTITY,
    CONF_STATUS_TRANSLATION,
    DEFAULT_CONTROL_INTERVAL_S,
    DOMAIN,
)

USER_INPUT = {
    "charger_current_entity": "number.charger_current",
    "charger_status_entity": "sensor.evse",
    CONF_CONNECTED_STATES: "Connected, Cable",
    CONF_CHARGING_STATES: "Charging, SuspendedEV",
    "net_power_entity": "sensor.net_power",
    "charger_power_entity": "sensor.charger_power",
    "grid_voltage_entity": "sensor.grid_voltage",
    "nominal_voltage": 230.0,
    "min_current": 6.0,
    "max_current": 16.0,
    CONF_GRID_CEILING_A: 25.0,
    CONF_GRID_SAFETY_OFFSET_A: 2.0,
    "default_target_current": 10.0,
}


async def test_adr0005_user_flow_builds_translation_and_splits_buckets(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] == FlowResultType.CREATE_ENTRY

    # Mappings + derived translation land in DATA (ADR-0005).
    translation = result["data"][CONF_STATUS_TRANSLATION]
    assert translation == {
        "Connected": "connected",
        "Cable": "connected",
        "Charging": "charging",
        "SuspendedEV": "charging",
    }
    # Thresholds/defaults (incl. the safety margin) + interval land in OPTIONS, not data.
    assert CONF_GRID_CEILING_A not in result["data"]
    assert result["options"][CONF_GRID_CEILING_A] == 25.0
    assert result["options"][CONF_GRID_SAFETY_OFFSET_A] == 2.0
    assert result["options"][CONF_CONTROL_INTERVAL_S] == DEFAULT_CONTROL_INTERVAL_S


async def test_overlapping_state_charging_wins(hass):
    """A raw state listed in both buckets resolves to charging (ADR-0005 install-step rule)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    user_input = dict(USER_INPUT)
    user_input[CONF_CONNECTED_STATES] = "Connected, Charging"
    user_input[CONF_CHARGING_STATES] = "Charging"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_STATUS_TRANSLATION]["Charging"] == "charging"


async def test_no_grid_voltage_still_creates_entry(hass):
    """grid_voltage_entity is optional (NF4) — omitting it still creates the entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    user_input = {k: v for k, v in USER_INPUT.items() if k != CONF_GRID_VOLTAGE_ENTITY}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert CONF_GRID_VOLTAGE_ENTITY not in result["data"]


async def test_options_flow_round_trip_updates_options_not_data(hass):
    """Changing a threshold via the options flow updates entry.options, leaving entry.data alone."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    entry = result["result"]

    original_data = dict(entry.data)

    options_result = await hass.config_entries.options.async_init(entry.entry_id)
    assert options_result["type"] == FlowResultType.FORM

    new_options = {
        "nominal_voltage": 230.0,
        "min_current": 6.0,
        "max_current": 16.0,
        CONF_GRID_CEILING_A: 25.0,
        CONF_GRID_SAFETY_OFFSET_A: 3.5,
        "default_target_current": 10.0,
        CONF_CONTROL_INTERVAL_S: 15,
    }
    options_result = await hass.config_entries.options.async_configure(
        options_result["flow_id"], new_options
    )
    assert options_result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_GRID_SAFETY_OFFSET_A] == 3.5
    assert entry.options[CONF_CONTROL_INTERVAL_S] == 15
    assert dict(entry.data) == original_data
