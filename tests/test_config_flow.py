"""HA-harness config-flow tests (ADR-0005)."""

import pytest
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_charging.config_flow import (
    CONFIG_TABLE,
    CORE_MAPPING_SCHEMA,
    DEADLINE_MAPPING_SCHEMA,
    OPTION_KEYS,
    OPTIONS_TABLE,
    UNGATED_MAPPING_SCHEMA,
    VEHICLE_LIMIT_MAPPING_SCHEMA,
    FlowStep,
    SmartChargingConfigFlow,
    SmartChargingOptionsFlow,
    _captar_mapping_schema,
    _captar_threshold_schema,
    _deadline_threshold_schema,
    _solar_mapping_schema,
    _solar_threshold_schema,
    _TableWalkMixin,
    _ungated_threshold_schema,
)
from custom_components.smart_charging.const import (
    CONF_CAPTAR_AVAILABLE,
    CONF_CAPTAR_COOLDOWN_MIN,
    CONF_CAR_HOME_ENTITY,
    CONF_CHARGER_CURRENT_ENTITY,
    CONF_CHARGER_POWER_ENTITY,
    CONF_CHARGER_STATUS_ENTITY,
    CONF_CHARGING_STATES,
    CONF_CONNECTED_STATES,
    CONF_CONTROL_INTERVAL_S,
    CONF_DEADLINE_AVAILABLE,
    CONF_DEFAULT_SOC_LIMIT,
    CONF_DEFAULT_TARGET_CURRENT,
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
    CONF_MAX_CURRENT,
    CONF_MAX_PEAK_KW,
    CONF_MAX_SOLAR_SOC,
    CONF_MIN_CURRENT,
    CONF_NET_POWER_ENTITY,
    CONF_NOMINAL_VOLTAGE,
    CONF_NOTIFICATION_TARGET_ENTITY,
    CONF_PEAK_GRACE_MIN,
    CONF_POWER_RESPECT_PEAK,
    CONF_PROMPT_TIMEOUT_H,
    CONF_REMINDER_LEAD_H,
    CONF_SAFETY_MARGIN_W,
    CONF_SMOOTHING_WINDOW,
    CONF_SOLAR_AVAILABLE,
    CONF_SOLAR_COOLDOWN_MIN,
    CONF_SOLAR_FORECAST_ENTITY,
    CONF_SOLAR_FORECAST_THRESHOLD_KWH,
    CONF_SOLAR_HOLD_MIN,
    CONF_SOLAR_ONLY_MIDPOINT,
    CONF_SOLAR_ONLY_START_THRESHOLD_W,
    CONF_SOLAR_ONLY_STRATEGY,
    CONF_SOLAR_RESERVE_SOC,
    CONF_SOLAR_START_THRESHOLD_W,
    CONF_SOLAR_STEP_PP,
    CONF_SOLAR_STEP_THRESHOLD_PP,
    CONF_STATUS_TRANSLATION,
    CONF_VEHICLE_CHARGE_LIMIT_ENTITY,
    CONF_VEHICLE_LIMIT_MAPPED,
    DEFAULT_CONTROL_INTERVAL_S,
    DEFAULT_EV_BATTERY_CAPACITY_KWH,
    DEFAULT_EVENING_PROMPT_ENABLED,
    DEFAULT_EVENING_PROMPT_TIME,
    DEFAULT_MAX_PEAK_KW,
    DEFAULT_PEAK_GRACE_MIN,
    DEFAULT_POWER_RESPECT_PEAK,
    DEFAULT_SAFETY_MARGIN_W,
    DEFAULT_SOC_LIMIT,
    DOMAIN,
    ERROR_REQUIRED_WHEN_CAPTAR_AVAILABLE,
    ERROR_REQUIRED_WHEN_SOLAR_AVAILABLE,
    ERROR_REQUIRED_WHEN_VEHICLE_LIMIT_MAPPED,
    ROLE_CAR_HOME,
    ROLE_CHARGER_CURRENT,
    ROLE_VEHICLE_CHARGE_LIMIT,
    STATE_CHARGING,
    STATE_CONNECTED,
    STEP_CAPTAR,
    STEP_CORE,
    STEP_DEADLINE,
    STEP_MAPPINGS,
    STEP_SOLAR,
    STEP_THRESHOLDS,
    STEP_VEHICLE_LIMIT,
)
from tests.helpers import entry_data_base, entry_options_base, seed_charger_states

# USER_INPUT is the flat MAPPING_SCHEMA/_threshold_schema()-shaped fixture -- still used
# directly (never through the flow) by tests that build a MockConfigEntry's data by hand or
# exercise async_step_reconfigure, both of which still speak the flat schema (T9/T13).
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

# Per-step base fixtures for the guided install flow (UC12 steps 1/7/8 -- T3's own scope).
# All three capability decisions default off: T3 adds no solar/captar/deadline step, so
# ev_soc_entity/solar_forecast_entity/departure_external_entity have no field to answer them
# on -- turning a capability on here can only ever exercise the thresholds-step guard
# rejecting the still-missing mapping (T4-T6 add the real success path once their step exists).
CORE_INPUT = {
    CONF_CHARGER_CURRENT_ENTITY: "number.charger_current",
    CONF_CHARGER_STATUS_ENTITY: "sensor.evse",
    CONF_CONNECTED_STATES: "Connected, Cable",
    CONF_CHARGING_STATES: "Charging, SuspendedEV",
    CONF_NET_POWER_ENTITY: "sensor.net_power",
    CONF_CHARGER_POWER_ENTITY: "sensor.charger_power",
    CONF_SOLAR_AVAILABLE: False,
    CONF_CAPTAR_AVAILABLE: False,
    CONF_DEADLINE_AVAILABLE: False,
    CONF_VEHICLE_LIMIT_MAPPED: False,
}

MAPPINGS_INPUT = {
    CONF_GRID_VOLTAGE_ENTITY: "sensor.grid_voltage",
}

THRESHOLDS_INPUT = {
    CONF_NOMINAL_VOLTAGE: 230.0,
    CONF_MIN_CURRENT: 6.0,
    CONF_MAX_CURRENT: 16.0,
    CONF_GRID_CEILING_A: 25.0,
    CONF_GRID_SAFETY_OFFSET_A: 2.0,
    CONF_DEFAULT_TARGET_CURRENT: 10.0,
}

_INSTALL_STEP_BASES = {
    STEP_CORE: CORE_INPUT,
    STEP_MAPPINGS: MAPPINGS_INPUT,
    STEP_THRESHOLDS: THRESHOLDS_INPUT,
}


async def _run_install_flow(hass, *, per_step=None):
    """Drive the install flow (core -> mappings -> thresholds, UC12 steps 1/7/8) step by
    step, submitting each step's base fixture merged with `per_step[<step id>]`'s overrides
    (a value of None removes that key, replacing the old `_run_user_flow`'s `omit`). Returns
    the final flow result -- a FORM if a step-local guard rejected the last submission,
    otherwise CREATE_ENTRY. Asserts each form encountered along the way is the expected step."""
    overrides = per_step or {}
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    for step_id in (STEP_CORE, STEP_MAPPINGS, STEP_THRESHOLDS):
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == step_id
        submission = {**_INSTALL_STEP_BASES[step_id], **overrides.get(step_id, {})}
        submission = {k: v for k, v in submission.items() if v is not None}
        result = await hass.config_entries.flow.async_configure(result["flow_id"], submission)
    return result


async def _create_entry(hass, *, per_step=None):
    result = await _run_install_flow(hass, per_step=per_step)
    return result["result"]


def _current_options(entry):
    """Options as the flat options-flow schema would resubmit them. Excludes
    prompt_timeout_h: stored via the guided install flow since T3, but not yet asked by this
    still-flat `_threshold_schema()` (T10 gives the options flow its own table) -- spreading
    it back in would submit a key the flat schema rejects as unknown."""
    return {k: v for k, v in entry.options.items() if k != CONF_PROMPT_TIMEOUT_H}


async def test_adr0005_user_flow_builds_translation_and_splits_buckets(hass):
    result = await _run_install_flow(hass)
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
    # ev_soc mapping coverage moves to T4/T5 (solar/captar steps) -- T3's guided flow has no
    # step that can answer it yet (see CORE_INPUT's module comment).


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
    result = await _run_install_flow(
        hass,
        per_step={
            STEP_CORE: {
                CONF_CONNECTED_STATES: "Connected, Charging",
                CONF_CHARGING_STATES: "Charging",
            }
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_STATUS_TRANSLATION]["Charging"] == STATE_CHARGING


async def test_no_grid_voltage_still_creates_entry(hass):
    """grid_voltage_entity is optional (NF4) — omitting it still creates the entry."""
    result = await _run_install_flow(
        hass, per_step={STEP_MAPPINGS: {CONF_GRID_VOLTAGE_ENTITY: None}}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert CONF_GRID_VOLTAGE_ENTITY not in result["data"]


async def test_options_flow_round_trip_updates_options_not_data(hass):
    """Changing a threshold via the options flow updates entry.options, leaving entry.data alone."""
    entry = await _create_entry(hass)

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
    await hass.async_block_till_done()
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
    original_coordinator = entry.runtime_data.coordinator

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
    new_coordinator = entry.runtime_data.coordinator
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
    # Design doc §3/§8: with solar_available and captar_available both declared absent
    # (CORE_INPUT's default), ev_soc is optional -- an install without it still produces a
    # valid entry.
    result = await _run_install_flow(hass)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert CONF_EV_SOC_ENTITY not in result["data"]
    assert result["data"][CONF_SOLAR_AVAILABLE] is False


async def test_solar_available_true_requires_ev_soc(hass):
    # Design doc §3: flipping Solar installed to True without mapping ev_soc must be
    # rejected by the flow itself (config-time guard), not deferred to a runtime fault. T3
    # has no solar step yet -- ev_soc has no field to answer it on at all -- so the guard,
    # moved to the thresholds step's temporary safety net (plan T3), still fires here.
    result = await _run_install_flow(hass, per_step={STEP_CORE: {CONF_SOLAR_AVAILABLE: True}})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_THRESHOLDS
    assert result["errors"][CONF_EV_SOC_ENTITY] == ERROR_REQUIRED_WHEN_SOLAR_AVAILABLE


# test_solar_available_true_with_ev_soc_succeeds is deferred to T4: ev_soc_entity has no
# field to answer it on until the solar step's mapping fragment exists.


async def test_pre_toggle_entry_defaults_solar_available_false(hass):
    # An entry created before this task predates CONF_SOLAR_AVAILABLE entirely -- setup
    # must default it to False, not KeyError (design doc §8). Exercised through the real
    # async_setup_entry wiring (__init__.py's `entry.data.get(CONF_SOLAR_AVAILABLE, False)`
    # threaded into the coordinator's config), not a bare dict.get replicated in the test
    # itself -- that would pass even if the integration's own default fell back to True.
    # Kept alongside this file's other CONF_SOLAR_AVAILABLE config-flow tests (ADR-0009's
    # "mirrors the module under test" is a default, not a hard split) rather than moved to
    # test_init.py's own "setup threads options into coordinator config" family, since this
    # one is specifically about a config-flow-era field, not an options-flow threading case.
    seed_charger_states(hass, status="Charging")
    data = entry_data_base()
    assert CONF_SOLAR_AVAILABLE not in data  # sanity: this entry genuinely predates the toggle

    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = entry.runtime_data.coordinator
    assert coordinator._config.solar_available is False


async def test_solar_thresholds_seeded_into_options_with_defaults(hass):
    # solar_only_strategy lives on the solar step (T4), which doesn't exist yet -- only the
    # ungated default_soc_limit is checked here until then.
    result = await _run_install_flow(hass)
    assert result["options"][CONF_DEFAULT_SOC_LIMIT] == DEFAULT_SOC_LIMIT


async def test_options_flow_edits_solar_thresholds(hass):
    entry = await _create_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**_current_options(entry), CONF_SOLAR_START_THRESHOLD_W: 200.0}
    )
    await hass.async_block_till_done()
    assert entry.options[CONF_SOLAR_START_THRESHOLD_W] == 200.0


# The original test_solar_available_error_preserves_previously_entered_values asserted
# suggested values for charger_current_entity/solar_available on the re-shown form -- neither
# is a thresholds-step field now, so that specific assertion is deferred to T4/T5 along with
# the guard itself. The thresholds step's OWN fields are testable today, via the same
# add_suggested_values_to_schema call (config_flow.py's async_step_thresholds):
async def test_thresholds_error_preserves_previously_entered_values(hass):
    result = await _run_install_flow(
        hass,
        per_step={
            STEP_CORE: {CONF_SOLAR_AVAILABLE: True},
            STEP_THRESHOLDS: {CONF_NOMINAL_VOLTAGE: 231.5},
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_THRESHOLDS

    suggested = {key.schema: key.description for key in result["data_schema"].schema}
    assert suggested[CONF_NOMINAL_VOLTAGE]["suggested_value"] == 231.5


async def test_reconfigure_rejects_solar_available_true_without_ev_soc(hass):
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
        CONF_SOLAR_AVAILABLE: True,
    }

    result = await hass.config_entries.flow.async_configure(result["flow_id"], new_mapping)
    assert result["type"] == FlowResultType.FORM
    assert result["errors"][CONF_EV_SOC_ENTITY] == ERROR_REQUIRED_WHEN_SOLAR_AVAILABLE


async def test_reconfigure_rejects_solar_available_true_without_solar_forecast(hass):
    # Design doc §3: the solar_forecast guard must also hold on reconfigure, mirroring
    # the ev_soc guard's own reconfigure test above -- otherwise a user could bypass it
    # by flipping CONF_SOLAR_AVAILABLE on through Reconfigure instead of the install form.
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
        CONF_SOLAR_AVAILABLE: True,
        CONF_EV_SOC_ENTITY: "sensor.ev_soc",
    }

    result = await hass.config_entries.flow.async_configure(result["flow_id"], new_mapping)
    assert result["type"] == FlowResultType.FORM
    assert result["errors"][CONF_SOLAR_FORECAST_ENTITY] == ERROR_REQUIRED_WHEN_SOLAR_AVAILABLE


async def test_captar_available_defaults_true(hass):
    # Design doc §3: R18 ("defaulting to present") / entity-catalog.md's sc_captar_available.
    # Omitting the field from the core submission (rather than a successful, ev_soc-mapped
    # install, which has no step to answer ev_soc on until T5) lets CORE_MAPPING_SCHEMA's own
    # default apply -- proven end-to-end by the guard firing exactly as it does when the
    # field is explicitly set True (test_captar_available_true_requires_ev_soc above).
    result = await _run_install_flow(hass, per_step={STEP_CORE: {CONF_CAPTAR_AVAILABLE: None}})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_THRESHOLDS
    assert result["errors"][CONF_EV_SOC_ENTITY] == ERROR_REQUIRED_WHEN_CAPTAR_AVAILABLE


async def test_solar_available_defaults_true(hass):
    # Design doc, "Decisions on two forks" §2: the core step's rendered default is True (R20
    # AC1's "defaulting to present"), deliberately diverging from DEFAULT_SOLAR_AVAILABLE
    # (False, the absent-key read fallback). Proven the same way as the captar default above:
    # omitting the field lets the schema default apply, and the guard fires accordingly.
    result = await _run_install_flow(hass, per_step={STEP_CORE: {CONF_SOLAR_AVAILABLE: None}})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_THRESHOLDS
    assert result["errors"][CONF_EV_SOC_ENTITY] == ERROR_REQUIRED_WHEN_SOLAR_AVAILABLE


async def test_captar_available_true_requires_ev_soc(hass):
    # Design doc §3: flipping CapTar available to True (or leaving its default) without
    # mapping ev_soc must be rejected by the flow itself, exactly like CONF_SOLAR_AVAILABLE's
    # guard on the same field. T3 has no captar step yet, so ev_soc has no field to answer
    # it on -- the guard, moved to the thresholds step's temporary safety net, still fires.
    result = await _run_install_flow(hass, per_step={STEP_CORE: {CONF_CAPTAR_AVAILABLE: True}})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_THRESHOLDS
    assert result["errors"][CONF_EV_SOC_ENTITY] == ERROR_REQUIRED_WHEN_CAPTAR_AVAILABLE


async def test_captar_available_false_does_not_require_ev_soc(hass):
    result = await _run_install_flow(hass, per_step={STEP_CORE: {CONF_CAPTAR_AVAILABLE: False}})
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
    # test_init.py, same rationale as test_pre_toggle_entry_defaults_solar_available_false.
    seed_charger_states(hass, status="Charging")
    data = entry_data_base()
    assert CONF_CAPTAR_AVAILABLE not in data  # sanity: this entry genuinely predates the toggle

    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = entry.runtime_data.coordinator
    assert coordinator._config.captar_available is True


async def test_peak_protection_thresholds_seeded_into_options_with_defaults(hass):
    # captar_cooldown_min lives on the captar step (T5), which doesn't exist yet -- only the
    # ungated peak-protection thresholds are checked here until then.
    result = await _run_install_flow(hass)
    assert result["options"][CONF_MAX_PEAK_KW] == DEFAULT_MAX_PEAK_KW
    assert result["options"][CONF_POWER_RESPECT_PEAK] == DEFAULT_POWER_RESPECT_PEAK
    assert result["options"][CONF_SAFETY_MARGIN_W] == DEFAULT_SAFETY_MARGIN_W
    assert result["options"][CONF_PEAK_GRACE_MIN] == DEFAULT_PEAK_GRACE_MIN


async def test_options_flow_edits_peak_protection_thresholds(hass):
    entry = await _create_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**_current_options(entry), CONF_MAX_PEAK_KW: 5.0}
    )
    await hass.async_block_till_done()
    assert entry.options[CONF_MAX_PEAK_KW] == 5.0


async def test_power_respect_peak_can_be_turned_off(hass):
    entry = await _create_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**_current_options(entry), CONF_POWER_RESPECT_PEAK: False}
    )
    await hass.async_block_till_done()
    assert entry.options[CONF_POWER_RESPECT_PEAK] is False


async def test_solar_forecast_required_when_solar_available(hass):
    # Design doc §3: solar_forecast is required only when CONF_SOLAR_AVAILABLE is True
    # (R9's precondition is inert without the solar capability) -- same
    # required_when_solar_available-style guard ev_soc already uses. T3 has no solar step
    # yet, so solar_forecast has no field to answer it on -- the guard, moved to the
    # thresholds step's temporary safety net, still fires (alongside the ev_soc guard, since
    # neither is answerable -- both error keys are asserted present, not just this one).
    result = await _run_install_flow(hass, per_step={STEP_CORE: {CONF_SOLAR_AVAILABLE: True}})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_THRESHOLDS
    assert result["errors"][CONF_SOLAR_FORECAST_ENTITY] == ERROR_REQUIRED_WHEN_SOLAR_AVAILABLE


async def test_solar_forecast_not_required_when_solar_not_installed(hass):
    result = await _run_install_flow(hass, per_step={STEP_CORE: {CONF_SOLAR_AVAILABLE: False}})
    assert result["type"] == FlowResultType.CREATE_ENTRY


async def test_ev_battery_capacity_entity_can_be_mapped(hass):
    result = await _run_install_flow(
        hass,
        per_step={STEP_MAPPINGS: {CONF_EV_BATTERY_CAPACITY_ENTITY: "sensor.ev_battery_capacity"}},
    )
    assert result["data"][CONF_EV_BATTERY_CAPACITY_ENTITY] == "sensor.ev_battery_capacity"


async def test_ev_battery_capacity_entity_is_optional(hass):
    result = await _run_install_flow(hass)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert CONF_EV_BATTERY_CAPACITY_ENTITY not in result["data"]


async def test_home_day_external_entity_can_be_mapped(hass):
    # departure_external_entity lives on the deadline step (T6), which doesn't exist yet --
    # only home_day_external_entity (ungated mappings) is exercised here until then.
    result = await _run_install_flow(
        hass, per_step={STEP_MAPPINGS: {CONF_HOME_DAY_EXTERNAL_ENTITY: "binary_sensor.home_day"}}
    )
    assert result["data"][CONF_HOME_DAY_EXTERNAL_ENTITY] == "binary_sensor.home_day"


async def test_low_tariff_entity_can_be_mapped(hass):
    result = await _run_install_flow(
        hass, per_step={STEP_MAPPINGS: {CONF_LOW_TARIFF_ENTITY: "binary_sensor.low_tariff"}}
    )
    assert result["data"][CONF_LOW_TARIFF_ENTITY] == "binary_sensor.low_tariff"


async def test_low_tariff_entity_is_optional(hass):
    result = await _run_install_flow(hass)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert CONF_LOW_TARIFF_ENTITY not in result["data"]


async def test_new_thresholds_seeded_with_defaults(hass):
    # max_solar_soc/solar_step_pp/solar_step_threshold_pp/solar_reserve_soc/
    # solar_forecast_threshold_kwh live on the solar step (T4), which doesn't exist yet --
    # only the ungated ev_battery_capacity_kwh is checked here until then.
    result = await _run_install_flow(hass)
    assert result["options"][CONF_EV_BATTERY_CAPACITY_KWH] == DEFAULT_EV_BATTERY_CAPACITY_KWH


async def test_options_flow_edits_the_new_thresholds(hass):
    entry = await _create_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**_current_options(entry), CONF_SOLAR_RESERVE_SOC: 55.0}
    )
    await hass.async_block_till_done()
    assert entry.options[CONF_SOLAR_RESERVE_SOC] == 55.0


# test_vehicle_limit_mapped_without_car_home_is_rejected,
# test_vehicle_limit_mapped_with_car_home_is_accepted and test_car_home_mapped_alone_is_accepted
# are deferred to T7: vehicle_charge_limit_entity/car_home_entity live on the vehicle_limit
# step, which doesn't exist yet -- CONF_VEHICLE_LIMIT_MAPPED (core) only elects whether that
# step would be shown; it carries no entity mapping of its own.


async def test_neither_vehicle_limit_nor_car_home_is_accepted(hass):
    # UC09 precondition: unmapped vehicle limit -> M2 inert, no requirement on car_home.
    result = await _run_install_flow(hass)
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

    coordinator = entry.runtime_data.coordinator
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
    assert result["errors"][CONF_CAR_HOME_ENTITY] == ERROR_REQUIRED_WHEN_VEHICLE_LIMIT_MAPPED


async def test_options_flow_edits_solar_forecast_threshold(hass):
    # Notifications design doc §3: the options flow round-trips edits to the forecast
    # threshold, same as every other threshold field (this field predates this task -- it
    # is reused, not newly added -- but the round-trip itself was previously untested here).
    entry = await _create_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**_current_options(entry), CONF_SOLAR_FORECAST_THRESHOLD_KWH: 15.0}
    )
    await hass.async_block_till_done()
    assert entry.options[CONF_SOLAR_FORECAST_THRESHOLD_KWH] == 15.0


async def test_notification_target_entity_can_be_mapped(hass):
    # RA4 notify-target data field (notifications design doc §3/§6).
    result = await _run_install_flow(
        hass,
        per_step={STEP_MAPPINGS: {CONF_NOTIFICATION_TARGET_ENTITY: "notify.mobile_app_phone"}},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_NOTIFICATION_TARGET_ENTITY] == "notify.mobile_app_phone"


async def test_notification_target_entity_is_optional(hass):
    result = await _run_install_flow(hass)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert CONF_NOTIFICATION_TARGET_ENTITY not in result["data"]


async def test_notification_target_entity_rejects_non_notify_domain(hass):
    # Design doc §3/§6: the mapped entity's expected platform must be `notify` -- mirrors the
    # existing platform-validation guard (EntitySelector's own domain filter raises vol.Invalid,
    # the same mechanism test_options_flow_rejects_a_data_key exercises for a tampered options
    # submission). notification_target_entity is on the mappings step (UC12 step 7).
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CORE_INPUT)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_MAPPINGS

    bad_mappings = {**MAPPINGS_INPUT, CONF_NOTIFICATION_TARGET_ENTITY: "sensor.not_a_notify_entity"}
    with pytest.raises(vol.Invalid):
        await hass.config_entries.flow.async_configure(result["flow_id"], bad_mappings)
    assert not hass.config_entries.async_entries(DOMAIN)


async def test_evening_prompt_options_seeded_into_options_with_defaults(hass):
    # Notifications design doc §3: evening-prompt options seed into OPTIONS with their
    # DEFAULT_* fallbacks -- no config-entry migration needed (an entry that predates these
    # keys reads each with its DEFAULT_* fallback, exercised separately below).
    result = await _run_install_flow(hass)
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
    await hass.async_block_till_done()
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


# --- T3: install happy path -- core -> mappings -> thresholds -> create entry. ---


async def test_r20_ac1_first_step_presents_only_core_mappings_and_decisions(hass):
    """R20 AC1 / UC12 step 1: the first form's schema is exactly CORE_MAPPING_SCHEMA --
    in particular it no longer carries a single threshold (the flat USER_SCHEMA did)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_CORE
    assert _keys(result["data_schema"]) == _keys(CORE_MAPPING_SCHEMA)


async def test_adr0005_all_capabilities_off_install_splits_buckets(hass):
    """UC12 step 9 / ADR-0005: solar/captar/deadline all declared absent and no vehicle limit
    elected -> core, mappings, thresholds only; DATA carries the mappings, the capability flags
    and the derived status_translation; OPTIONS carries only the ungated thresholds plus the
    defaulted control interval."""
    result = await _run_install_flow(hass)
    assert result["type"] == FlowResultType.CREATE_ENTRY

    assert result["data"][CONF_SOLAR_AVAILABLE] is False
    assert result["data"][CONF_CAPTAR_AVAILABLE] is False
    assert result["data"][CONF_DEADLINE_AVAILABLE] is False
    assert CONF_VEHICLE_LIMIT_MAPPED not in result["data"]  # design D-2: transient, not stored
    assert result["data"][CONF_STATUS_TRANSLATION] == {
        "Connected": STATE_CONNECTED,
        "Cable": STATE_CONNECTED,
        "Charging": STATE_CHARGING,
        "SuspendedEV": STATE_CHARGING,
    }

    # Only the ungated thresholds + control_interval_s -- the intersection excludes every
    # OPTION_KEYS member that lives on a not-yet-existing step (solar/captar/deadline, T4-T6).
    assert sorted(result["options"]) == sorted(
        _keys(_ungated_threshold_schema(include_interval=True))
    )
    assert result["options"][CONF_CONTROL_INTERVAL_S] == DEFAULT_CONTROL_INTERVAL_S


async def test_adr0025_option_keys_consumption_is_intersection_based(hass):
    """ADR-0025 Consequences: a skipped step leaves its OPTION_KEYS members absent from the
    accumulator; the terminal step must intersect, not index. T3's own thresholds fragment
    is one field short of the full OPTION_KEYS set (solar/captar/deadline thresholds live on
    steps that don't exist yet) -- direct indexing would KeyError here."""
    result = await _run_install_flow(hass)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert CONF_SOLAR_START_THRESHOLD_W not in result["options"]
    assert CONF_CAPTAR_COOLDOWN_MIN not in result["options"]
    assert CONF_REMINDER_LEAD_H not in result["options"]


# --- T1: per-step schema fragments (guided config flow, ADR-0025 Option C; UC12/R20). ---
# Pure schema-shape assertions -- no `hass` fixture needed (design, "Testing approach").


def _keys(schema) -> set[str]:
    return {str(marker) for marker in schema.schema}


def test_uc12_step1_core_fragment_has_exactly_the_core_mappings_and_decisions():
    """UC12 step 1 / R20 AC1: four core mappings + two state lists + four enablement
    decisions -- and nothing else (grid voltage moves to the ungated-mappings step,
    UC12 step 7)."""
    assert _keys(CORE_MAPPING_SCHEMA) == {
        CONF_CHARGER_CURRENT_ENTITY,
        CONF_CHARGER_STATUS_ENTITY,
        CONF_CONNECTED_STATES,
        CONF_CHARGING_STATES,
        CONF_NET_POWER_ENTITY,
        CONF_CHARGER_POWER_ENTITY,
        CONF_SOLAR_AVAILABLE,
        CONF_CAPTAR_AVAILABLE,
        CONF_DEADLINE_AVAILABLE,
        CONF_VEHICLE_LIMIT_MAPPED,
    }


def test_uc12_step3_solar_mapping_fragment_with_ev_soc():
    assert _keys(_solar_mapping_schema(include_ev_soc=True)) == {
        CONF_EV_SOC_ENTITY,
        CONF_SOLAR_FORECAST_ENTITY,
    }


def test_uc12_step3_solar_mapping_fragment_without_ev_soc():
    assert _keys(_solar_mapping_schema(include_ev_soc=False)) == {CONF_SOLAR_FORECAST_ENTITY}


def test_uc12_step3_solar_threshold_fragment():
    assert _keys(_solar_threshold_schema()) == {
        CONF_SOLAR_START_THRESHOLD_W,
        CONF_SOLAR_ONLY_START_THRESHOLD_W,
        CONF_SOLAR_ONLY_STRATEGY,
        CONF_SOLAR_ONLY_MIDPOINT,
        CONF_SOLAR_HOLD_MIN,
        CONF_SOLAR_COOLDOWN_MIN,
        CONF_SOLAR_STEP_PP,
        CONF_SOLAR_STEP_THRESHOLD_PP,
        CONF_MAX_SOLAR_SOC,
        CONF_SOLAR_RESERVE_SOC,
        CONF_SOLAR_FORECAST_THRESHOLD_KWH,
    }


def test_uc12_step4_captar_mapping_fragment_with_ev_soc():
    assert _keys(_captar_mapping_schema(include_ev_soc=True)) == {CONF_EV_SOC_ENTITY}


def test_uc12_step4_captar_mapping_fragment_without_ev_soc():
    assert _keys(_captar_mapping_schema(include_ev_soc=False)) == set()


def test_uc12_step4_captar_threshold_fragment():
    assert _keys(_captar_threshold_schema()) == {CONF_CAPTAR_COOLDOWN_MIN}


def test_uc12_step5_deadline_mapping_fragment():
    assert _keys(DEADLINE_MAPPING_SCHEMA) == {CONF_DEPARTURE_EXTERNAL_ENTITY}


def test_uc12_step5_deadline_threshold_fragment():
    assert _keys(_deadline_threshold_schema()) == {CONF_REMINDER_LEAD_H}


def test_uc12_step6_vehicle_limit_mapping_fragment():
    assert _keys(VEHICLE_LIMIT_MAPPING_SCHEMA) == {
        CONF_VEHICLE_CHARGE_LIMIT_ENTITY,
        CONF_CAR_HOME_ENTITY,
    }


def test_uc12_step7_ungated_mapping_fragment():
    assert _keys(UNGATED_MAPPING_SCHEMA) == {
        CONF_GRID_VOLTAGE_ENTITY,
        CONF_LOW_TARIFF_ENTITY,
        CONF_NOTIFICATION_TARGET_ENTITY,
        CONF_EV_BATTERY_CAPACITY_ENTITY,
        CONF_HOME_DAY_EXTERNAL_ENTITY,
    }


# Final key set (design, "Schema fragments") -- T3 added CONF_PROMPT_TIMEOUT_H per
# "Decisions on two forks" §1.
_UNGATED_THRESHOLD_KEYS = {
    CONF_NOMINAL_VOLTAGE,
    CONF_MIN_CURRENT,
    CONF_MAX_CURRENT,
    CONF_GRID_CEILING_A,
    CONF_GRID_SAFETY_OFFSET_A,
    CONF_SMOOTHING_WINDOW,
    CONF_DEFAULT_SOC_LIMIT,
    CONF_DEFAULT_TARGET_CURRENT,
    CONF_SAFETY_MARGIN_W,
    CONF_MAX_PEAK_KW,
    CONF_PEAK_GRACE_MIN,
    CONF_EV_BATTERY_CAPACITY_KWH,
    CONF_POWER_RESPECT_PEAK,
    CONF_EVENING_PROMPT_ENABLED,
    CONF_EVENING_PROMPT_TIME,
    CONF_PROMPT_TIMEOUT_H,
}


def test_uc12_step8_ungated_threshold_fragment_without_interval():
    """UC12 step 8, install/reconfigure: the control interval is never asked on this path
    (defaulted instead, R20 AC5's carve-out)."""
    assert _keys(_ungated_threshold_schema(include_interval=False)) == _UNGATED_THRESHOLD_KEYS


def test_uc12_step8_ungated_threshold_fragment_with_interval():
    """UC12 1b: the options flow alone asks the control interval."""
    assert _keys(_ungated_threshold_schema(include_interval=True)) == (
        _UNGATED_THRESHOLD_KEYS | {CONF_CONTROL_INTERVAL_S}
    )


def test_every_option_key_appears_in_exactly_one_threshold_fragment():
    """ADR-0005: every OPTION_KEYS member has exactly one step that presents it -- no key
    orphaned by the split, none asked twice."""
    threshold_fragments = [
        _solar_threshold_schema(),
        _captar_threshold_schema(),
        _deadline_threshold_schema(),
        _ungated_threshold_schema(include_interval=False),
    ]
    all_keys: list[str] = []
    for fragment in threshold_fragments:
        all_keys.extend(_keys(fragment))
    # control_interval_s is deliberately not an OPTION_KEYS member (it's appended separately
    # at the terminal step, design "The terminal step and the bucket split") and only the
    # options-flow variant of the ungated fragment carries it -- excluded here by using
    # include_interval=False above.
    assert sorted(all_keys) == sorted(set(OPTION_KEYS))


def test_no_field_appears_in_two_fragments_except_ev_soc():
    """Every field belongs to exactly one fragment -- with one deliberate carve-out.
    ev_soc_entity is a member of BOTH _solar_mapping_schema(include_ev_soc=True) and
    _captar_mapping_schema(include_ev_soc=True) by design: the once-only rule (R20 AC4,
    UC12 postcondition 3) is enforced at RENDER time by the include_ev_soc argument, not by
    fragment membership. Compare the fragments built with include_ev_soc=False so the
    carve-out is structural rather than a subtracted special case.

    Note this does NOT generalise UC12 postcondition 3 -- that postcondition is about what a
    presented step shows (T8's traversal assertion), not a statement about fragment
    membership."""
    all_fragments = [
        CORE_MAPPING_SCHEMA,
        _solar_mapping_schema(include_ev_soc=False),
        _solar_threshold_schema(),
        _captar_mapping_schema(include_ev_soc=False),
        _captar_threshold_schema(),
        DEADLINE_MAPPING_SCHEMA,
        _deadline_threshold_schema(),
        VEHICLE_LIMIT_MAPPING_SCHEMA,
        UNGATED_MAPPING_SCHEMA,
        _ungated_threshold_schema(include_interval=False),
    ]
    seen: set[str] = set()
    for fragment in all_fragments:
        overlap = _keys(fragment) & seen
        assert not overlap, f"field(s) {overlap} appear in more than one fragment"
        seen |= _keys(fragment)


# --- T2: the step table and the shared dispatcher (guided config flow, ADR-0025 Option C). ---
# CONFIG_TABLE/OPTIONS_TABLE are populated incrementally (T3 onward), so the reachability
# tests below are written to hold at every point along that build-out, not just today's
# empty tables -- they are the named discharge of ADR-0025's stated Con (a step method absent
# from its table is silently unreachable) and stay meaningful as later tasks add rows.

# Steps legitimately absent from CONFIG_TABLE: the two framework-mandated entry points
# (ADR-0025 point 4) plus `core` (UC12 step 1) -- the shared entry point both async_step_user
# and async_step_reconfigure delegate into (T3), which is deliberately not a table row of its
# own (design, "Step ids"). Omitting `core` here would make the converse test below fail the
# moment T3 adds async_step_core, for a step that is correct by design, not a wiring bug.
_CONFIG_FLOW_FRAMEWORK_STEPS = {"async_step_user", "async_step_reconfigure", "async_step_core"}
_OPTIONS_FLOW_FRAMEWORK_STEPS = {"async_step_init"}


def _non_framework_step_methods(cls, framework: set[str]) -> set[str]:
    """Step methods `cls` itself defines -- not `dir(cls)`, which would also pick up
    discovery-flow hooks (e.g. `async_step_usb`) inherited from HA's own ConfigFlow base."""
    return {name for name in vars(cls) if name.startswith("async_step_") and name not in framework}


def test_adr0025_every_config_table_step_has_a_step_method():
    """ADR-0025 test obligation: a table row with no async_step_<id> strands the flow."""
    for row in CONFIG_TABLE:
        # cls's own method, not an inherited HA discovery-flow hook (e.g. async_step_usb).
        assert f"async_step_{row.step_id}" in vars(SmartChargingConfigFlow)


def test_adr0025_every_config_step_method_is_in_the_table():
    """The converse: a step method absent from the table is unreachable and nothing raises."""
    table_step_ids = {row.step_id for row in CONFIG_TABLE}
    for name in _non_framework_step_methods(SmartChargingConfigFlow, _CONFIG_FLOW_FRAMEWORK_STEPS):
        assert name.removeprefix("async_step_") in table_step_ids


def test_adr0025_every_options_table_step_has_a_step_method():
    """Same obligation, for the options flow's own table (ADR-0025 point 3)."""
    for row in OPTIONS_TABLE:
        assert f"async_step_{row.step_id}" in vars(SmartChargingOptionsFlow)


def test_adr0025_every_options_step_method_is_in_the_table():
    table_step_ids = {row.step_id for row in OPTIONS_TABLE}
    for name in _non_framework_step_methods(
        SmartChargingOptionsFlow, _OPTIONS_FLOW_FRAMEWORK_STEPS
    ):
        assert name.removeprefix("async_step_") in table_step_ids


def _assert_is_subsequence_of(actual_order: list[str], fixed_order: list[str]) -> None:
    """Each id in `actual_order` must appear in `fixed_order`, in the same relative order,
    with no reordering permitted -- a subsequence check, not full-population equality (see
    the TODO(T7, T10) note on UC12_FIXED_STEP_ORDER for why equality isn't checked yet)."""
    remaining = fixed_order[:]
    for step_id in actual_order:
        assert step_id in remaining, f"{step_id} is out of UC12's fixed order"
        remaining = remaining[remaining.index(step_id) + 1 :]


def test_uc12_step2_config_table_is_in_uc12s_fixed_order():
    """UC12 step 2 / R20 AC2: solar -> captar -> deadline -> vehicle limit -> ungated mappings
    -> ungated thresholds. Whatever subset of CONFIG_TABLE's rows exist at any point in the
    build-out, their relative order must be a subsequence of this fixed order -- the order is
    the table's, and it is asserted literally. The expected order is spelled out here from
    UC12 itself (via const.py's STEP_* ids), not imported from config_flow.py's own
    UC12_FIXED_STEP_ORDER -- otherwise a reordering that "fixes" both the table and that
    constant together would still pass."""
    _assert_is_subsequence_of(
        [row.step_id for row in CONFIG_TABLE],
        [
            STEP_SOLAR,
            STEP_CAPTAR,
            STEP_DEADLINE,
            STEP_VEHICLE_LIMIT,
            STEP_MAPPINGS,
            STEP_THRESHOLDS,
        ],
    )


def test_uc12_1b_options_table_is_in_uc12s_fixed_order():
    """UC12 1b: the options flow's own table has no vehicle_limit row (ADR-0025 point 3) but
    is otherwise gated in the same fixed order as the config table."""
    _assert_is_subsequence_of(
        [row.step_id for row in OPTIONS_TABLE],
        [STEP_SOLAR, STEP_CAPTAR, STEP_DEADLINE, STEP_THRESHOLDS],
    )


async def test_adr0025_dispatcher_advances_past_a_failing_gate_and_finishes_when_exhausted():
    """Dispatcher unit test over a synthetic two-row table (ADR-0025, Option C): a failing
    gate is skipped, the next passing row is shown, and exhausting the table calls
    _async_finish exactly once. Each gate asserts it received the flow handler itself (not,
    say, `self._answers`), pinning FlowStep.gate's `Callable[[Any], bool]` contract -- one
    signature serving both the config table (reads self._answers/self._mode) and the options
    table (reads self.config_entry.data)."""
    calls = []

    class _FakeFlow(_TableWalkMixin):
        _table = (
            FlowStep(step_id="skip_me", gate=lambda f: f is flow and False),
            FlowStep(step_id="show_me", gate=lambda f: f is flow),
        )

        async def async_step_skip_me(self):
            calls.append("skip_me")
            return "unreachable"

        async def async_step_show_me(self):
            calls.append("show_me")
            return "shown"

        async def _async_finish(self):
            calls.append("finish")
            return "finished"

    flow = _FakeFlow()
    result = await flow._async_advance(after=None)
    assert result == "shown"
    assert calls == ["show_me"]

    # Advancing past the last row (nothing left to try) finishes.
    result = await flow._async_advance(after="show_me")
    assert result == "finished"
    assert calls == ["show_me", "finish"]

    # `after` not itself a table member (e.g. the shared `core`/`init` entry points, ADR-0025
    # point 4) restarts the walk from the first row -- the same path core/init rely on.
    calls.clear()
    result = await flow._async_advance(after="not_a_table_member")
    assert result == "shown"
    assert calls == ["show_me"]
