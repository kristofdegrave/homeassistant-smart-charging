"""HA-harness config-flow tests (ADR-0005)."""

import pytest
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_charging.const import (
    CONF_CAPTAR_AVAILABLE,
    CONF_CAPTAR_COOLDOWN_MIN,
    CONF_CAR_HOME_ENTITY,
    CONF_CHARGER_CURRENT_ENTITY,
    CONF_CHARGING_STATES,
    CONF_CONNECTED_STATES,
    CONF_CONTROL_INTERVAL_S,
    CONF_DEFAULT_SOC_LIMIT,
    CONF_DEPARTURE_EXTERNAL_ENTITY,
    CONF_EV_BATTERY_CAPACITY_ENTITY,
    CONF_EV_BATTERY_CAPACITY_KWH,
    CONF_EV_SOC_ENTITY,
    CONF_EVENING_PROMPT_ENABLED,
    CONF_EVENING_PROMPT_TIME,
    CONF_GRID_CEILING_A,
    CONF_GRID_SAFETY_OFFSET_A,
    CONF_GRID_VOLTAGE_ENTITY,
    CONF_HOME_DAY_EXTERNAL_ENTITY,
    CONF_LOW_TARIFF_ENTITY,
    CONF_MAX_PEAK_KW,
    CONF_MAX_SOLAR_SOC,
    CONF_NOTIFICATION_TARGET_ENTITY,
    CONF_PEAK_GRACE_MIN,
    CONF_POWER_RESPECT_PEAK,
    CONF_SAFETY_MARGIN_W,
    CONF_SOLAR_FORECAST_ENTITY,
    CONF_SOLAR_FORECAST_THRESHOLD_KWH,
    CONF_SOLAR_INSTALLED,
    CONF_SOLAR_ONLY_STRATEGY,
    CONF_SOLAR_RESERVE_SOC,
    CONF_SOLAR_START_THRESHOLD_W,
    CONF_SOLAR_STEP_PP,
    CONF_SOLAR_STEP_THRESHOLD_PP,
    CONF_STATUS_TRANSLATION,
    CONF_VEHICLE_CHARGE_LIMIT_ENTITY,
    DEFAULT_CAPTAR_COOLDOWN_MIN,
    DEFAULT_CONTROL_INTERVAL_S,
    DEFAULT_EV_BATTERY_CAPACITY_KWH,
    DEFAULT_EVENING_PROMPT_ENABLED,
    DEFAULT_EVENING_PROMPT_TIME,
    DEFAULT_MAX_PEAK_KW,
    DEFAULT_MAX_SOLAR_SOC,
    DEFAULT_PEAK_GRACE_MIN,
    DEFAULT_POWER_RESPECT_PEAK,
    DEFAULT_SAFETY_MARGIN_W,
    DEFAULT_SOC_LIMIT,
    DEFAULT_SOLAR_FORECAST_THRESHOLD_KWH,
    DEFAULT_SOLAR_ONLY_STRATEGY,
    DEFAULT_SOLAR_RESERVE_SOC,
    DEFAULT_SOLAR_STEP_PP,
    DEFAULT_SOLAR_STEP_THRESHOLD_PP,
    DOMAIN,
    ROLE_CAR_HOME,
    ROLE_CHARGER_CURRENT,
    ROLE_VEHICLE_CHARGE_LIMIT,
    STATE_CHARGING,
    STATE_CONNECTED,
)
from tests.helpers import entry_data_base, entry_options_base, seed_charger_states

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


async def test_second_config_entry_aborts_single_instance_allowed(hass):
    """ADR-0013: two config entries would both drive the same charger and register duplicate
    owned entities with `_2` object_id suffixes, breaking ADR-0013's documented stable
    entity_ids (#500). `manifest.json`'s `single_config_entry` makes HA core itself abort a
    second install attempt once one entry already exists."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1  # no `_2` entry ever created


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
    (ADR-0005) — it must replace data, leave options untouched, and reload the entry
    (ADR-0008: a mapping change tears down and recreates the coordinator). The entry is
    fully set up first so the reload is observable as a real side effect -- a brand-new
    coordinator instance replacing the old one -- rather than asserted only via the flow's
    own ABORT/reconfigure_successful result, which says nothing about whether a reload
    actually happened."""
    seed_charger_states(hass, status="Charging")
    hass.states.async_set("sensor.new_evse", "Charging")
    hass.states.async_set("number.new_charger_current", "0.0")

    data = entry_data_base()
    # CONF_CAPTAR_AVAILABLE defaults to True (DEFAULT_CAPTAR_AVAILABLE) and neither this
    # entry nor the reconfigure submission below maps ev_soc -- turn it off so the
    # required_when_captar_available guard doesn't reject the reconfigure submission.
    data[CONF_CAPTAR_AVAILABLE] = False
    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    original_options = dict(entry.options)
    original_coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

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
    await hass.async_block_till_done()

    assert entry.data[CONF_CHARGER_CURRENT_ENTITY] == "number.new_charger_current"
    assert entry.data[CONF_STATUS_TRANSLATION] == {
        "Connected": STATE_CONNECTED,
        "Charging": STATE_CHARGING,
    }
    assert dict(entry.options) == original_options
    # ADR-0008's central consequence: the reconfigure must trigger a full config-entry
    # reload, which recreates the coordinator from scratch. This entry's reload is actually
    # driven by two redundant paths -- async_update_reload_and_abort's own schedule_reload
    # (config_flow.py) and the generic update-listener __init__.py registers for any entry
    # update (_async_reload_entry) -- so this assertion only fails if reload-on-change were
    # removed from *both*; either path alone still satisfies ADR-0008 and keeps this green.
    new_coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    assert new_coordinator is not original_coordinator
    # ...and prove the reload actually picked up the new mapping, not just that *some*
    # reload happened against stale data.
    assert (
        new_coordinator._adapters[ROLE_CHARGER_CURRENT]._entity_id == "number.new_charger_current"
    )


def _suggested_values(result):
    """Map schema key -> its prefilled suggested_value (absent keys omitted)."""
    return {
        key.schema: key.description["suggested_value"]
        for key in result["data_schema"].schema
        if key.description and "suggested_value" in key.description
    }


_RECONFIGURE_ENTRY_DATA = {
    CONF_CHARGER_CURRENT_ENTITY: "number.charger_current",
    "charger_status_entity": "sensor.evse",
    "net_power_entity": "sensor.net_power",
    "charger_power_entity": "sensor.charger_power",
    CONF_GRID_VOLTAGE_ENTITY: "sensor.grid_voltage",
    CONF_LOW_TARIFF_ENTITY: "binary_sensor.low_tariff",
    CONF_NOTIFICATION_TARGET_ENTITY: "notify.mobile_app",
    CONF_CAR_HOME_ENTITY: "person.driver",
    CONF_CAPTAR_AVAILABLE: False,
    CONF_STATUS_TRANSLATION: {"Connected": STATE_CONNECTED, "Charging": STATE_CHARGING},
}


async def test_reconfigure_form_prefills_existing_mappings(hass):
    # Issue #499: the blank reconfigure form must be prefilled from entry.data, otherwise
    # any optional mapping the user doesn't retype is silently dropped on save.
    entry = MockConfigEntry(domain=DOMAIN, data=dict(_RECONFIGURE_ENTRY_DATA), options={})
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    suggested = _suggested_values(result)
    assert suggested[CONF_CHARGER_CURRENT_ENTITY] == "number.charger_current"
    assert suggested[CONF_GRID_VOLTAGE_ENTITY] == "sensor.grid_voltage"
    assert suggested[CONF_LOW_TARIFF_ENTITY] == "binary_sensor.low_tariff"
    assert suggested[CONF_NOTIFICATION_TARGET_ENTITY] == "notify.mobile_app"
    assert suggested[CONF_CAR_HOME_ENTITY] == "person.driver"
    # A bool field with a schema-level default (captar_available) must also prefill from
    # entry.data, not fall back to the schema default -- otherwise reconfiguring would
    # silently flip it back to True and re-trigger the ev_soc-required guard.
    assert suggested[CONF_CAPTAR_AVAILABLE] is False


async def test_reconfigure_preserves_unretyped_optional_mappings(hass):
    # Issue #499: submitting exactly what a prefilled form round-trips back (the
    # rendered suggested values, unchanged) must not null out any optional mapping --
    # only the field the user actually edits (charger_current_entity here) should change.
    # Built from the rendered schema's own suggested values, so this fails for the right
    # reason if the prefill regresses: reverting the fix blanks every suggested value below.
    entry = MockConfigEntry(domain=DOMAIN, data=dict(_RECONFIGURE_ENTRY_DATA), options={})
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )

    new_mapping = dict(_suggested_values(result))
    # connected_states/charging_states have no stored raw value to prefill (known gap,
    # tracked separately) -- the user must always retype these two required fields.
    new_mapping[CONF_CONNECTED_STATES] = "Connected"
    new_mapping[CONF_CHARGING_STATES] = "Charging"
    new_mapping[CONF_CHARGER_CURRENT_ENTITY] = "number.new_charger_current"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], new_mapping)
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"

    assert entry.data[CONF_CHARGER_CURRENT_ENTITY] == "number.new_charger_current"
    assert entry.data[CONF_GRID_VOLTAGE_ENTITY] == "sensor.grid_voltage"
    assert entry.data[CONF_LOW_TARIFF_ENTITY] == "binary_sensor.low_tariff"
    assert entry.data[CONF_NOTIFICATION_TARGET_ENTITY] == "notify.mobile_app"
    assert entry.data[CONF_CAR_HOME_ENTITY] == "person.driver"


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
        overrides={
            CONF_SOLAR_INSTALLED: True,
            CONF_EV_SOC_ENTITY: "sensor.ev_soc",
            CONF_SOLAR_FORECAST_ENTITY: "sensor.solar_forecast",
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_SOLAR_INSTALLED] is True
    assert result["data"][CONF_EV_SOC_ENTITY] == "sensor.ev_soc"


async def test_pre_toggle_entry_defaults_solar_installed_false(hass):
    # An entry created before this task predates CONF_SOLAR_INSTALLED entirely -- setup
    # must default it to False, not KeyError (design doc §8). Exercised through the real
    # async_setup_entry wiring (__init__.py's `entry.data.get(CONF_SOLAR_INSTALLED, False)`
    # threaded into the coordinator's config), not a bare dict.get replicated in the test
    # itself -- that would pass even if the integration's own default fell back to True.
    # Kept alongside this file's other CONF_SOLAR_INSTALLED config-flow tests (ADR-0009's
    # "mirrors the module under test" is a default, not a hard split) rather than moved to
    # test_init.py's own "setup threads options into coordinator config" family, since this
    # one is specifically about a config-flow-era field, not an options-flow threading case.
    seed_charger_states(hass, status="Charging")
    data = entry_data_base()
    assert CONF_SOLAR_INSTALLED not in data  # sanity: this entry genuinely predates the toggle

    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    assert coordinator._config[CONF_SOLAR_INSTALLED] is False


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


async def test_reconfigure_rejects_solar_installed_true_without_solar_forecast(hass):
    # Design doc §3: the solar_forecast guard must also hold on reconfigure, mirroring
    # the ev_soc guard's own reconfigure test above -- otherwise a user could bypass it
    # by flipping CONF_SOLAR_INSTALLED on through Reconfigure instead of the install form.
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
        CONF_EV_SOC_ENTITY: "sensor.ev_soc",
    }

    result = await hass.config_entries.flow.async_configure(result["flow_id"], new_mapping)
    assert result["type"] == FlowResultType.FORM
    assert result["errors"][CONF_SOLAR_FORECAST_ENTITY] == "required_when_solar_installed"


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
    # An entry created before this task predates CONF_CAPTAR_AVAILABLE entirely -- setup
    # must default it to True (design doc §3), not KeyError. Exercised through the real
    # async_setup_entry wiring (__init__.py's
    # `entry.data.get(CONF_CAPTAR_AVAILABLE, DEFAULT_CAPTAR_AVAILABLE)` threaded into the
    # coordinator's config), not a bare dict.get replicated in the test itself -- that would
    # pass even if the integration's own default flipped to False. Kept alongside this
    # file's other CONF_CAPTAR_AVAILABLE config-flow tests rather than moved to
    # test_init.py, same rationale as test_pre_toggle_entry_defaults_solar_installed_false.
    seed_charger_states(hass, status="Charging")
    data = entry_data_base()
    assert CONF_CAPTAR_AVAILABLE not in data  # sanity: this entry genuinely predates the toggle

    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    assert coordinator._config[CONF_CAPTAR_AVAILABLE] is True


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


async def test_solar_forecast_required_when_solar_installed(hass):
    # Design doc §3: solar_forecast is required only when CONF_SOLAR_INSTALLED is True
    # (R9's precondition is inert without the solar capability) -- same
    # required_when_solar_installed-style guard ev_soc already uses.
    result = await _run_user_flow(
        hass, overrides={CONF_SOLAR_INSTALLED: True}, omit=[CONF_SOLAR_FORECAST_ENTITY]
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"][CONF_SOLAR_FORECAST_ENTITY] == "required_when_solar_installed"


async def test_solar_forecast_not_required_when_solar_not_installed(hass):
    result = await _run_user_flow(
        hass, overrides={CONF_SOLAR_INSTALLED: False}, omit=[CONF_SOLAR_FORECAST_ENTITY]
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY


async def test_ev_battery_capacity_entity_can_be_mapped(hass):
    result = await _run_user_flow(
        hass, overrides={CONF_EV_BATTERY_CAPACITY_ENTITY: "sensor.ev_battery_capacity"}
    )
    assert result["data"][CONF_EV_BATTERY_CAPACITY_ENTITY] == "sensor.ev_battery_capacity"


async def test_ev_battery_capacity_entity_is_optional(hass):
    result = await _run_user_flow(hass, omit=[CONF_EV_BATTERY_CAPACITY_ENTITY])
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert CONF_EV_BATTERY_CAPACITY_ENTITY not in result["data"]


async def test_departure_external_and_home_day_external_entities_can_be_mapped(hass):
    result = await _run_user_flow(
        hass,
        overrides={
            CONF_DEPARTURE_EXTERNAL_ENTITY: "sensor.departure_time",
            CONF_HOME_DAY_EXTERNAL_ENTITY: "binary_sensor.home_day",
        },
    )
    assert result["data"][CONF_DEPARTURE_EXTERNAL_ENTITY] == "sensor.departure_time"
    assert result["data"][CONF_HOME_DAY_EXTERNAL_ENTITY] == "binary_sensor.home_day"


async def test_low_tariff_entity_can_be_mapped(hass):
    result = await _run_user_flow(
        hass, overrides={CONF_LOW_TARIFF_ENTITY: "binary_sensor.low_tariff"}
    )
    assert result["data"][CONF_LOW_TARIFF_ENTITY] == "binary_sensor.low_tariff"


async def test_low_tariff_entity_is_optional(hass):
    result = await _run_user_flow(hass, omit=[CONF_LOW_TARIFF_ENTITY])
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert CONF_LOW_TARIFF_ENTITY not in result["data"]


async def test_new_thresholds_seeded_with_defaults(hass):
    result = await _run_user_flow(hass)
    assert result["options"][CONF_EV_BATTERY_CAPACITY_KWH] == DEFAULT_EV_BATTERY_CAPACITY_KWH
    assert result["options"][CONF_MAX_SOLAR_SOC] == DEFAULT_MAX_SOLAR_SOC
    assert result["options"][CONF_SOLAR_STEP_PP] == DEFAULT_SOLAR_STEP_PP
    assert result["options"][CONF_SOLAR_STEP_THRESHOLD_PP] == DEFAULT_SOLAR_STEP_THRESHOLD_PP
    assert result["options"][CONF_SOLAR_RESERVE_SOC] == DEFAULT_SOLAR_RESERVE_SOC
    assert (
        result["options"][CONF_SOLAR_FORECAST_THRESHOLD_KWH] == DEFAULT_SOLAR_FORECAST_THRESHOLD_KWH
    )


async def test_options_flow_edits_the_new_thresholds(hass):
    entry = await _create_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**_current_options(entry), CONF_SOLAR_RESERVE_SOC: 55.0}
    )
    assert entry.options[CONF_SOLAR_RESERVE_SOC] == 55.0


async def test_vehicle_limit_mapped_without_car_home_is_rejected(hass):
    # UC09 C2 / design §9.1: a vehicle-limit output with no presence source is unsafe --
    # the config-time guard must reject the save outright, not defer to a runtime fault.
    result = await _run_user_flow(
        hass, overrides={CONF_VEHICLE_CHARGE_LIMIT_ENTITY: "number.car_limit"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"][CONF_CAR_HOME_ENTITY] == "required_when_vehicle_limit_mapped"


async def test_vehicle_limit_mapped_with_car_home_is_accepted(hass):
    result = await _run_user_flow(
        hass,
        overrides={
            CONF_VEHICLE_CHARGE_LIMIT_ENTITY: "number.car_limit",
            CONF_CAR_HOME_ENTITY: "device_tracker.car",
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_VEHICLE_CHARGE_LIMIT_ENTITY] == "number.car_limit"
    assert result["data"][CONF_CAR_HOME_ENTITY] == "device_tracker.car"
    # ADR-0005: both are hardware mappings, folded into DATA -- neither belongs in options.
    assert CONF_VEHICLE_CHARGE_LIMIT_ENTITY not in result["options"]
    assert CONF_CAR_HOME_ENTITY not in result["options"]


async def test_car_home_mapped_alone_is_accepted(hass):
    # car_home has no guard of its own -- only vehicle_charge_limit requires it.
    result = await _run_user_flow(hass, overrides={CONF_CAR_HOME_ENTITY: "device_tracker.car"})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CAR_HOME_ENTITY] == "device_tracker.car"
    assert CONF_VEHICLE_CHARGE_LIMIT_ENTITY not in result["data"]


async def test_neither_vehicle_limit_nor_car_home_is_accepted(hass):
    # UC09 precondition: unmapped vehicle limit -> M2 inert, no requirement on car_home.
    result = await _run_user_flow(hass)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert CONF_VEHICLE_CHARGE_LIMIT_ENTITY not in result["data"]
    assert CONF_CAR_HOME_ENTITY not in result["data"]


async def test_pre_field_entry_reads_vehicle_limit_and_car_home_as_absent(hass):
    # An entry created before these fields must not KeyError -- no migration needed
    # (design doc §8), mirroring the ev_soc/captar_available pre-toggle-entry tests above.
    # Exercised through the real async_setup_entry -> build_adapters wiring
    # (adapters/factory.py's `data.get(CONF_VEHICLE_CHARGE_LIMIT_ENTITY)` /
    # `data.get(CONF_CAR_HOME_ENTITY)` guards), not a bare dict.get replicated in the test
    # itself -- that would pass even if the factory's own guards were deleted outright.
    # tests/adapters/test_factory.py's test_car_home_role_absent_when_not_configured /
    # test_vehicle_charge_limit_role_absent_when_not_configured already cover the factory
    # guard itself in isolation; the role-absence assertions below are this test's covering
    # detail -- what's unique here is that a full config-entry setup (async_setup_entry,
    # the `assert await hass.config_entries.async_setup(...)` line) succeeds end-to-end for
    # a pre-field entry without KeyError.
    seed_charger_states(hass, status="Charging")
    data = entry_data_base()
    assert CONF_VEHICLE_CHARGE_LIMIT_ENTITY not in data
    assert CONF_CAR_HOME_ENTITY not in data

    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    assert ROLE_VEHICLE_CHARGE_LIMIT not in coordinator._adapters
    assert ROLE_CAR_HOME not in coordinator._adapters


async def test_reconfigure_rejects_vehicle_limit_mapped_without_car_home(hass):
    # Design doc §9.1: the guard must hold on reconfigure too, mirroring the ev_soc/
    # solar_forecast reconfigure guard tests above -- otherwise a user could bypass it by
    # mapping vehicle_charge_limit through Reconfigure instead of the install form.
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
        CONF_CAPTAR_AVAILABLE: False,  # isolate the car_home guard from the ev_soc guard
        CONF_VEHICLE_CHARGE_LIMIT_ENTITY: "number.car_limit",
    }

    result = await hass.config_entries.flow.async_configure(result["flow_id"], new_mapping)
    assert result["type"] == FlowResultType.FORM
    assert result["errors"][CONF_CAR_HOME_ENTITY] == "required_when_vehicle_limit_mapped"


async def test_options_flow_edits_solar_forecast_threshold(hass):
    # Notifications design doc §3: the options flow round-trips edits to the forecast
    # threshold, same as every other threshold field (this field predates this task -- it
    # is reused, not newly added -- but the round-trip itself was previously untested here).
    entry = await _create_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**_current_options(entry), CONF_SOLAR_FORECAST_THRESHOLD_KWH: 15.0}
    )
    assert entry.options[CONF_SOLAR_FORECAST_THRESHOLD_KWH] == 15.0


async def test_notification_target_entity_can_be_mapped(hass):
    # RA4 notify-target data field (notifications design doc §3/§6).
    result = await _run_user_flow(
        hass, overrides={CONF_NOTIFICATION_TARGET_ENTITY: "notify.mobile_app_phone"}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_NOTIFICATION_TARGET_ENTITY] == "notify.mobile_app_phone"


async def test_notification_target_entity_is_optional(hass):
    result = await _run_user_flow(hass, omit=[CONF_NOTIFICATION_TARGET_ENTITY])
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert CONF_NOTIFICATION_TARGET_ENTITY not in result["data"]


async def test_notification_target_entity_rejects_non_notify_domain(hass):
    # Design doc §3/§6: the mapped entity's expected platform must be `notify` -- mirrors the
    # existing platform-validation guard (EntitySelector's own domain filter raises vol.Invalid,
    # the same mechanism test_options_flow_rejects_a_data_key exercises for a tampered options
    # submission).
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    user_input = dict(USER_INPUT)
    user_input[CONF_NOTIFICATION_TARGET_ENTITY] = "sensor.not_a_notify_entity"

    with pytest.raises(vol.Invalid):
        await hass.config_entries.flow.async_configure(result["flow_id"], user_input)
    assert not hass.config_entries.async_entries(DOMAIN)


async def test_evening_prompt_options_seeded_into_options_with_defaults(hass):
    # Notifications design doc §3: evening-prompt options seed into OPTIONS with their
    # DEFAULT_* fallbacks -- no config-entry migration needed (an entry that predates these
    # keys reads each with its DEFAULT_* fallback, exercised separately below).
    result = await _run_user_flow(hass)
    assert result["options"][CONF_EVENING_PROMPT_ENABLED] == DEFAULT_EVENING_PROMPT_ENABLED
    assert result["options"][CONF_EVENING_PROMPT_TIME] == DEFAULT_EVENING_PROMPT_TIME


async def test_options_flow_round_trips_evening_prompt_options(hass):
    entry = await _create_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            **_current_options(entry),
            CONF_EVENING_PROMPT_ENABLED: False,
            CONF_EVENING_PROMPT_TIME: "19:30:00",
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_EVENING_PROMPT_ENABLED] is False
    assert entry.options[CONF_EVENING_PROMPT_TIME] == "19:30:00"


async def test_pre_existing_entry_defaults_evening_prompt_options(hass):
    # An entry created before this task predates these keys entirely -- opening the options
    # flow on it must seed each field with its DEFAULT_* (no config-entry migration, design
    # doc §3), and submitting that pre-filled form must persist those defaults, not KeyError.
    entry = MockConfigEntry(domain=DOMAIN, data=dict(USER_INPUT), options={})
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    defaults = {key.schema: key.default() for key in result["data_schema"].schema}
    assert defaults[CONF_EVENING_PROMPT_ENABLED] == DEFAULT_EVENING_PROMPT_ENABLED
    assert defaults[CONF_EVENING_PROMPT_TIME] == DEFAULT_EVENING_PROMPT_TIME

    result = await hass.config_entries.options.async_configure(result["flow_id"], defaults)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_EVENING_PROMPT_ENABLED] == DEFAULT_EVENING_PROMPT_ENABLED
    assert entry.options[CONF_EVENING_PROMPT_TIME] == DEFAULT_EVENING_PROMPT_TIME
