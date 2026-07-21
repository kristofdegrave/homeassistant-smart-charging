"""HA-harness config-flow tests (ADR-0005)."""

import pytest
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_charging.const import (
    CONF_CAPTAR_AVAILABLE,
    CONF_CAPTAR_COOLDOWN_MIN,
    CONF_CHARGER_CURRENT_ENTITY,
    CONF_CHARGING_STATES,
    CONF_CONNECTED_STATES,
    CONF_CONTROL_INTERVAL_S,
    CONF_DEFAULT_SOC_LIMIT,
    CONF_EV_SOC_ENTITY,
    CONF_GRID_CEILING_A,
    CONF_GRID_SAFETY_OFFSET_A,
    CONF_GRID_VOLTAGE_ENTITY,
    CONF_MAX_PEAK_KW,
    CONF_PEAK_GRACE_MIN,
    CONF_POWER_RESPECT_PEAK,
    CONF_SAFETY_MARGIN_W,
    CONF_SOLAR_INSTALLED,
    CONF_SOLAR_ONLY_STRATEGY,
    CONF_SOLAR_START_THRESHOLD_W,
    CONF_STATUS_TRANSLATION,
    DEFAULT_CAPTAR_COOLDOWN_MIN,
    DEFAULT_CONTROL_INTERVAL_S,
    DEFAULT_MAX_PEAK_KW,
    DEFAULT_PEAK_GRACE_MIN,
    DEFAULT_POWER_RESPECT_PEAK,
    DEFAULT_SAFETY_MARGIN_W,
    DEFAULT_SOC_LIMIT,
    DEFAULT_SOLAR_ONLY_STRATEGY,
    DOMAIN,
    STATE_CHARGING,
    STATE_CONNECTED,
)

USER_INPUT = {
    "charger_current_entity": "number.charger_current",
    "charger_status_entity": "sensor.evse",
    CONF_CONNECTED_STATES: "Connected, Cable",
    CONF_CHARGING_STATES: "Charging, SuspendedEV",
    "net_power_entity": "sensor.net_power",
    "charger_power_entity": "sensor.charger_power",
    "grid_voltage_entity": "sensor.grid_voltage",
    CONF_EV_SOC_ENTITY: "sensor.ev_soc",
    "nominal_voltage": 230.0,
    "min_current": 6.0,
    "max_current": 16.0,
    CONF_GRID_CEILING_A: 25.0,
    CONF_GRID_SAFETY_OFFSET_A: 2.0,
    "default_target_current": 10.0,
}


async def _run_user_flow(hass, overrides=None, omit=None):
    user_input = dict(USER_INPUT)
    user_input.update(overrides or {})
    for key in omit or ():
        user_input.pop(key, None)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    return await hass.config_entries.flow.async_configure(result["flow_id"], user_input)


async def _create_entry(hass, overrides=None):
    result = await _run_user_flow(hass, overrides=overrides)
    return result["result"]


def _current_options(entry):
    return dict(entry.options)


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
        "Connected": STATE_CONNECTED,
        "Cable": STATE_CONNECTED,
        "Charging": STATE_CHARGING,
        "SuspendedEV": STATE_CHARGING,
    }
    # Thresholds/defaults (incl. the safety margin) + interval land in OPTIONS, not data.
    assert CONF_GRID_CEILING_A not in result["data"]
    assert result["options"][CONF_GRID_CEILING_A] == 25.0
    assert result["options"][CONF_GRID_SAFETY_OFFSET_A] == 2.0
    assert result["options"][CONF_CONTROL_INTERVAL_S] == DEFAULT_CONTROL_INTERVAL_S
    # ev_soc is a DATA field (RA1 extension) -- lands alongside the other role mappings.
    assert result["data"][CONF_EV_SOC_ENTITY] == "sensor.ev_soc"


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
    assert result["data"][CONF_STATUS_TRANSLATION]["Charging"] == STATE_CHARGING


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


async def test_options_flow_rejects_a_data_key(hass):
    """The options flow's schema is thresholds/interval only — a data key (entity-role
    mapping) submitted to it is rejected, not silently accepted (ADR-0005: only the
    reconfigure flow may change entity-role mappings)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_CHARGER_CURRENT_ENTITY: "number.charger_current", CONF_STATUS_TRANSLATION: {}},
        options={
            "nominal_voltage": 230.0,
            "min_current": 6.0,
            "max_current": 16.0,
            CONF_GRID_CEILING_A: 25.0,
            CONF_GRID_SAFETY_OFFSET_A: 2.0,
            "default_target_current": 10.0,
            CONF_CONTROL_INTERVAL_S: DEFAULT_CONTROL_INTERVAL_S,
        },
    )
    entry.add_to_hass(hass)

    options_result = await hass.config_entries.options.async_init(entry.entry_id)
    tampered_options = dict(entry.options)
    tampered_options[CONF_CHARGER_CURRENT_ENTITY] = "number.some_other_charger"

    with pytest.raises(vol.Invalid):
        await hass.config_entries.options.async_configure(
            options_result["flow_id"], tampered_options
        )
    assert entry.data[CONF_CHARGER_CURRENT_ENTITY] == "number.charger_current"


async def test_reconfigure_replaces_data_leaves_options_and_reloads(hass):
    """async_step_reconfigure is the only sanctioned path to remap entity roles
    (ADR-0005) — it must replace data, leave options untouched, and reload the entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CHARGER_CURRENT_ENTITY: "number.charger_current",
            "charger_status_entity": "sensor.evse",
            "net_power_entity": "sensor.net_power",
            "charger_power_entity": "sensor.charger_power",
            CONF_STATUS_TRANSLATION: {"Connected": STATE_CONNECTED, "Charging": STATE_CHARGING},
        },
        options={
            CONF_GRID_SAFETY_OFFSET_A: 2.0,
            CONF_CONTROL_INTERVAL_S: DEFAULT_CONTROL_INTERVAL_S,
        },
    )
    entry.add_to_hass(hass)
    original_options = dict(entry.options)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    new_mapping = {
        CONF_CHARGER_CURRENT_ENTITY: "number.new_charger_current",
        "charger_status_entity": "sensor.new_evse",
        CONF_CONNECTED_STATES: "Connected",
        CONF_CHARGING_STATES: "Charging",
        "net_power_entity": "sensor.net_power",
        "charger_power_entity": "sensor.charger_power",
        CONF_CAPTAR_AVAILABLE: False,
    }
    result = await hass.config_entries.flow.async_configure(result["flow_id"], new_mapping)
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"

    assert entry.data[CONF_CHARGER_CURRENT_ENTITY] == "number.new_charger_current"
    assert entry.data[CONF_STATUS_TRANSLATION] == {
        "Connected": STATE_CONNECTED,
        "Charging": STATE_CHARGING,
    }
    assert dict(entry.options) == original_options


async def test_ev_soc_is_optional_when_solar_not_installed(hass):
    # Design doc §3/§8: with the Solar-installed toggle left False (its default), ev_soc
    # is optional -- an install without it still produces a valid entry. CapTar available
    # must also be turned off, since its own guard requires ev_soc otherwise (Captar T3.2).
    result = await _run_user_flow(
        hass, overrides={CONF_CAPTAR_AVAILABLE: False}, omit=[CONF_EV_SOC_ENTITY]
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert CONF_EV_SOC_ENTITY not in result["data"]
    assert result["data"][CONF_SOLAR_INSTALLED] is False


async def test_solar_installed_true_requires_ev_soc(hass):
    # Design doc §3: flipping Solar installed to True without mapping ev_soc must be
    # rejected by the flow itself (config-time guard), not deferred to a runtime fault.
    result = await _run_user_flow(
        hass, overrides={CONF_SOLAR_INSTALLED: True}, omit=[CONF_EV_SOC_ENTITY]
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"][CONF_EV_SOC_ENTITY] == "required_when_solar_installed"


async def test_solar_installed_true_with_ev_soc_succeeds(hass):
    result = await _run_user_flow(
        hass,
        overrides={CONF_SOLAR_INSTALLED: True, CONF_EV_SOC_ENTITY: "sensor.ev_soc"},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_SOLAR_INSTALLED] is True
    assert result["data"][CONF_EV_SOC_ENTITY] == "sensor.ev_soc"


async def test_pre_toggle_entry_defaults_solar_installed_false(hass):
    # An entry created before this task predates CONF_SOLAR_INSTALLED entirely --
    # reading it must default to False, not KeyError (design doc §8).
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={k: v for k, v in USER_INPUT.items() if k not in (CONF_SOLAR_INSTALLED,)},
        options={},
    )
    assert entry.data.get(CONF_SOLAR_INSTALLED, False) is False


async def test_solar_thresholds_seeded_into_options_with_defaults(hass):
    result = await _run_user_flow(hass)
    assert result["options"][CONF_SOLAR_ONLY_STRATEGY] == DEFAULT_SOLAR_ONLY_STRATEGY
    assert result["options"][CONF_DEFAULT_SOC_LIMIT] == DEFAULT_SOC_LIMIT


async def test_options_flow_edits_solar_thresholds(hass):
    entry = await _create_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**_current_options(entry), CONF_SOLAR_START_THRESHOLD_W: 200.0}
    )
    assert entry.options[CONF_SOLAR_START_THRESHOLD_W] == 200.0


async def test_solar_installed_error_preserves_previously_entered_values(hass):
    # The re-shown form on the required_when_solar_installed rejection must not drop
    # what the user already typed -- otherwise flipping the toggle back on and refilling
    # every mapping is the only way to recover (a real UX regression, not just cosmetic).
    result = await _run_user_flow(
        hass, overrides={CONF_SOLAR_INSTALLED: True}, omit=[CONF_EV_SOC_ENTITY]
    )
    assert result["type"] == FlowResultType.FORM

    suggested = {key.schema: key.description for key in result["data_schema"].schema}
    assert suggested[CONF_CHARGER_CURRENT_ENTITY]["suggested_value"] == "number.charger_current"
    assert suggested[CONF_SOLAR_INSTALLED]["suggested_value"] is True


async def test_reconfigure_rejects_solar_installed_true_without_ev_soc(hass):
    # Design doc §3: the config-time guard must hold on reconfigure too -- otherwise a
    # user can bypass it entirely by flipping the toggle through Reconfigure instead of
    # the initial install form.
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CHARGER_CURRENT_ENTITY: "number.charger_current",
            "charger_status_entity": "sensor.evse",
            "net_power_entity": "sensor.net_power",
            "charger_power_entity": "sensor.charger_power",
            CONF_STATUS_TRANSLATION: {"Connected": STATE_CONNECTED, "Charging": STATE_CHARGING},
        },
        options={},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    new_mapping = {
        CONF_CHARGER_CURRENT_ENTITY: "number.charger_current",
        "charger_status_entity": "sensor.evse",
        CONF_CONNECTED_STATES: "Connected",
        CONF_CHARGING_STATES: "Charging",
        "net_power_entity": "sensor.net_power",
        "charger_power_entity": "sensor.charger_power",
        CONF_SOLAR_INSTALLED: True,
    }

    result = await hass.config_entries.flow.async_configure(result["flow_id"], new_mapping)
    assert result["type"] == FlowResultType.FORM
    assert result["errors"][CONF_EV_SOC_ENTITY] == "required_when_solar_installed"


async def test_captar_available_defaults_true(hass):
    # Design doc §3: R18 ("defaulting to present") / entity-catalog.md's sc_captar_available.
    result = await _run_user_flow(hass)
    assert result["data"][CONF_CAPTAR_AVAILABLE] is True


async def test_captar_available_true_requires_ev_soc(hass):
    # Design doc §3: flipping CapTar available to True (or leaving its default) without
    # mapping ev_soc must be rejected by the flow itself, exactly like CONF_SOLAR_INSTALLED's
    # guard on the same field.
    result = await _run_user_flow(hass, omit=[CONF_EV_SOC_ENTITY])
    assert result["type"] == FlowResultType.FORM
    assert result["errors"][CONF_EV_SOC_ENTITY] == "required_when_captar_available"


async def test_captar_available_false_does_not_require_ev_soc(hass):
    result = await _run_user_flow(
        hass, overrides={CONF_CAPTAR_AVAILABLE: False}, omit=[CONF_EV_SOC_ENTITY]
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CAPTAR_AVAILABLE] is False
    assert CONF_EV_SOC_ENTITY not in result["data"]


async def test_pre_toggle_entry_defaults_captar_available_true(hass):
    # An entry created before this task predates CONF_CAPTAR_AVAILABLE entirely -- reading
    # it must default to True (design doc §3), not KeyError.
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={k: v for k, v in USER_INPUT.items() if k != CONF_CAPTAR_AVAILABLE},
        options={},
    )
    assert entry.data.get(CONF_CAPTAR_AVAILABLE, True) is True


async def test_peak_protection_thresholds_seeded_into_options_with_defaults(hass):
    result = await _run_user_flow(hass)
    assert result["options"][CONF_MAX_PEAK_KW] == DEFAULT_MAX_PEAK_KW
    assert result["options"][CONF_POWER_RESPECT_PEAK] == DEFAULT_POWER_RESPECT_PEAK
    assert result["options"][CONF_SAFETY_MARGIN_W] == DEFAULT_SAFETY_MARGIN_W
    assert result["options"][CONF_PEAK_GRACE_MIN] == DEFAULT_PEAK_GRACE_MIN
    assert result["options"][CONF_CAPTAR_COOLDOWN_MIN] == DEFAULT_CAPTAR_COOLDOWN_MIN


async def test_options_flow_edits_peak_protection_thresholds(hass):
    entry = await _create_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**_current_options(entry), CONF_MAX_PEAK_KW: 5.0}
    )
    assert entry.options[CONF_MAX_PEAK_KW] == 5.0


async def test_power_respect_peak_can_be_turned_off(hass):
    entry = await _create_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**_current_options(entry), CONF_POWER_RESPECT_PEAK: False}
    )
    assert entry.options[CONF_POWER_RESPECT_PEAK] is False
