"""HA-harness config-flow tests (ADR-0005)."""

import itertools

import pytest
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_charging import config_flow as config_flow_module
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
    DEFAULT_CAPTAR_COOLDOWN_MIN,
    DEFAULT_CONTROL_INTERVAL_S,
    DEFAULT_EV_BATTERY_CAPACITY_KWH,
    DEFAULT_EVENING_PROMPT_ENABLED,
    DEFAULT_EVENING_PROMPT_TIME,
    DEFAULT_MAX_PEAK_KW,
    DEFAULT_MAX_SOLAR_SOC,
    DEFAULT_PEAK_GRACE_MIN,
    DEFAULT_POWER_RESPECT_PEAK,
    DEFAULT_REMINDER_LEAD_H,
    DEFAULT_SAFETY_MARGIN_W,
    DEFAULT_SOC_LIMIT,
    DEFAULT_SOLAR_FORECAST_THRESHOLD_KWH,
    DEFAULT_SOLAR_ONLY_STRATEGY,
    DEFAULT_SOLAR_RESERVE_SOC,
    DEFAULT_SOLAR_STEP_PP,
    DEFAULT_SOLAR_STEP_THRESHOLD_PP,
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

# Per-step base fixtures for the guided install flow (UC12 steps 1/3/4/5/6/7/8). All four
# capability decisions default False here, including solar -- even though solar's rendered
# form default is True (T3) -- because CORE_INPUT is a fixture of explicit values, not a proof
# of the schema default (see test_solar_available_defaults_true for that), and leaving it
# False keeps every test that doesn't care about a capability off that capability's step
# entirely.
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

# UC12 step 3: only the two mappings need explicit values (both vol.Optional, no schema
# default); every threshold field is vol.Required(default=...) and needs no entry here.
SOLAR_INPUT = {
    CONF_EV_SOC_ENTITY: "sensor.ev_soc",
    CONF_SOLAR_FORECAST_ENTITY: "sensor.solar_forecast",
}

# UC12 step 4: ev_soc only needs a value here when solar didn't already collect it (R20 AC4's
# once-only rule) -- CORE_INPUT's own solar_available is False, so a bare captar-only run
# always needs it. _run_install_flow's None-removes-the-key mechanism drops it back out for
# the both-declared truth-table cases that must NOT ask for it again here.
CAPTAR_INPUT = {
    CONF_EV_SOC_ENTITY: "sensor.ev_soc",
}

# UC12 step 5: both fields are optional/defaulted (R18 AC7 -- neither is required), so an
# empty submission is a valid base fixture.
DEADLINE_INPUT = {}

# UC12 step 6: the two are always asked together -- vehicle_charge_limit_entity is
# vol.Required, car_home_entity is guarded (design D-3), so both need a value here.
VEHICLE_LIMIT_INPUT = {
    CONF_VEHICLE_CHARGE_LIMIT_ENTITY: "number.vehicle_charge_limit",
    CONF_CAR_HOME_ENTITY: "person.driver",
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
    STEP_SOLAR: SOLAR_INPUT,
    STEP_CAPTAR: CAPTAR_INPUT,
    STEP_DEADLINE: DEADLINE_INPUT,
    STEP_VEHICLE_LIMIT: VEHICLE_LIMIT_INPUT,
    STEP_MAPPINGS: MAPPINGS_INPUT,
    STEP_THRESHOLDS: THRESHOLDS_INPUT,
}


async def _run_install_flow(hass, *, per_step=None):
    """Drive the install flow across whichever steps the table shows this run -- which steps
    appear (e.g. `solar`) varies with the capability flags answered on the core step, so this
    follows the flow's own `step_id` rather than a fixed sequence. Submits each step's base
    fixture merged with `per_step[<step id>]`'s overrides (a value of None removes that key).
    Returns the final flow result: CREATE_ENTRY on success, or the re-shown FORM the moment a
    step-local guard rejects a submission -- detected as the same step_id appearing twice in a
    row, which stops the loop instead of resubmitting the same, still-failing fixture forever."""
    overrides = per_step or {}
    consumed_overrides: set[str] = set()
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    last_step_id = None
    while result["type"] == FlowResultType.FORM:
        step_id = result["step_id"]
        if step_id == last_step_id:
            break
        last_step_id = step_id
        consumed_overrides.add(step_id)
        submission = {**_INSTALL_STEP_BASES[step_id], **overrides.get(step_id, {})}
        submission = {k: v for k, v in submission.items() if v is not None}
        result = await hass.config_entries.flow.async_configure(result["flow_id"], submission)
    unconsumed = overrides.keys() - consumed_overrides
    assert not unconsumed, (
        f"per_step override(s) for {unconsumed} were never applied -- that step never "
        "rendered this run (a capability answer this test relies on may be missing/typo'd)"
    )
    return result


async def _create_entry(hass, *, per_step=None):
    result = await _run_install_flow(hass, per_step=per_step)
    return result["result"]


async def _run_reconfigure_flow(hass, entry, *, per_step=None):
    """The reconfigure analogue of `_run_install_flow` (T9, ADR-0025 point 4): entered via
    SOURCE_RECONFIGURE, otherwise identical -- same shared step methods and per-step base
    fixtures, same repeated-step-id guard against re-submitting a rejected fixture forever.
    The `thresholds` row is gated off entirely in this mode (UC12 1a), so the walk always
    ends at ABORT/reconfigure_successful, never CREATE_ENTRY."""
    overrides = per_step or {}
    consumed_overrides: set[str] = set()
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    last_step_id = None
    while result["type"] == FlowResultType.FORM:
        step_id = result["step_id"]
        if step_id == last_step_id:
            break
        last_step_id = step_id
        consumed_overrides.add(step_id)
        submission = {**_INSTALL_STEP_BASES.get(step_id, {}), **overrides.get(step_id, {})}
        submission = {k: v for k, v in submission.items() if v is not None}
        result = await hass.config_entries.flow.async_configure(result["flow_id"], submission)
    unconsumed = overrides.keys() - consumed_overrides
    assert not unconsumed, (
        f"per_step override(s) for {unconsumed} were never applied -- that step never "
        "rendered this run (a capability answer this test relies on may be missing/typo'd)"
    )
    return result


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
    # ev_soc mapping coverage (solar/captar steps) is exercised elsewhere: the solar step's
    # own tests (T4) and the captar step's (T5) -- CORE_INPUT declares both capabilities
    # absent here, so this test's own install has no field to answer it on.


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


def _suggested_values(result):
    """Map schema key -> its prefilled suggested_value (absent keys omitted)."""
    return {
        key.schema: key.description["suggested_value"]
        for key in result["data_schema"].schema
        if key.description and "suggested_value" in key.description
    }


# --- T9: the reconfigure flow. ---


async def test_uc12_1a_reconfigure_shows_mapping_fields_only(hass):
    """UC12 1a: the per-capability steps are 'restricted to their mapping fields only ...
    never a threshold', and step 8 is skipped entirely."""
    data = entry_data_base(
        **{
            CONF_SOLAR_AVAILABLE: True,
            CONF_EV_SOC_ENTITY: "sensor.ev_soc",
            CONF_SOLAR_FORECAST_ENTITY: "sensor.solar_forecast",
        }
    )
    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    assert result["step_id"] == STEP_CORE
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**CORE_INPUT, CONF_SOLAR_AVAILABLE: True}
    )
    assert result["step_id"] == STEP_SOLAR
    assert _keys(result["data_schema"]) == _keys(_solar_mapping_schema(include_ev_soc=True))

    visited_steps = []
    while result["type"] == FlowResultType.FORM:
        visited_steps.append(result["step_id"])
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _INSTALL_STEP_BASES.get(result["step_id"], {})
        )

    assert STEP_THRESHOLDS not in visited_steps
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"


_RECONFIGURE_ENTRY_DATA = {
    CONF_CHARGER_CURRENT_ENTITY: "number.charger_current",
    "charger_status_entity": "sensor.evse",
    "net_power_entity": "sensor.net_power",
    "charger_power_entity": "sensor.charger_power",
    CONF_GRID_VOLTAGE_ENTITY: "sensor.grid_voltage",
    CONF_LOW_TARIFF_ENTITY: "binary_sensor.low_tariff",
    CONF_NOTIFICATION_TARGET_ENTITY: "notify.mobile_app",
    CONF_SOLAR_AVAILABLE: False,
    CONF_CAPTAR_AVAILABLE: False,
    CONF_DEADLINE_AVAILABLE: False,
    CONF_STATUS_TRANSLATION: {"Connected": STATE_CONNECTED, "Charging": STATE_CHARGING},
}


async def test_uc12_1a_reconfigure_prefills_step_one_from_the_existing_entry(hass):
    """ADR-0025 point 2: prefill is rendering-only, via add_suggested_values_to_schema."""
    entry = MockConfigEntry(domain=DOMAIN, data=dict(_RECONFIGURE_ENTRY_DATA), options={})
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_CORE

    suggested = _suggested_values(result)
    assert suggested[CONF_CHARGER_CURRENT_ENTITY] == "number.charger_current"
    # A bool field with a schema-level default (captar_available) must also prefill from
    # entry.data, not fall back to the schema default -- otherwise reconfiguring would
    # silently flip it back to True and re-trigger the ev_soc-required guard.
    assert suggested[CONF_CAPTAR_AVAILABLE] is False


async def test_reconfigure_form_prefills_existing_mappings(hass):
    # Issue #499: the blank reconfigure form must be prefilled from entry.data, otherwise
    # any optional mapping the user doesn't retype is silently dropped on save. Checked on
    # both the core step and the ungated mappings step, since T9 spreads what was once one
    # flat form across the guided flow's own steps.
    entry = MockConfigEntry(domain=DOMAIN, data=dict(_RECONFIGURE_ENTRY_DATA), options={})
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    # connected_states/charging_states have no stored raw value to prefill (known gap,
    # tracked separately) -- the user must always retype these two required fields.
    core_submission = {
        **_suggested_values(result),
        CONF_CONNECTED_STATES: "Connected",
        CONF_CHARGING_STATES: "Charging",
    }
    result = await hass.config_entries.flow.async_configure(result["flow_id"], core_submission)
    assert result["step_id"] == STEP_MAPPINGS

    suggested = _suggested_values(result)
    assert suggested[CONF_GRID_VOLTAGE_ENTITY] == "sensor.grid_voltage"
    assert suggested[CONF_LOW_TARIFF_ENTITY] == "binary_sensor.low_tariff"
    assert suggested[CONF_NOTIFICATION_TARGET_ENTITY] == "notify.mobile_app"


async def test_reconfigure_preserves_unretyped_optional_mappings(hass):
    # Issue #499: submitting exactly what a prefilled form round-trips back (the
    # rendered suggested values, unchanged) must not null out any optional mapping --
    # only the field the user actually edits (charger_current_entity, on the core step)
    # should change. Built from each rendered step's own suggested values, so this fails for
    # the right reason if the prefill regresses: reverting the fix blanks every suggested
    # value below.
    entry = MockConfigEntry(domain=DOMAIN, data=dict(_RECONFIGURE_ENTRY_DATA), options={})
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    core_submission = dict(_suggested_values(result))
    # connected_states/charging_states have no stored raw value to prefill (known gap,
    # tracked separately) -- the user must always retype these two required fields.
    core_submission[CONF_CONNECTED_STATES] = "Connected"
    core_submission[CONF_CHARGING_STATES] = "Charging"
    core_submission[CONF_CHARGER_CURRENT_ENTITY] = "number.new_charger_current"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], core_submission)
    assert result["step_id"] == STEP_MAPPINGS
    mappings_submission = dict(_suggested_values(result))

    result = await hass.config_entries.flow.async_configure(result["flow_id"], mappings_submission)
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"

    assert entry.data[CONF_CHARGER_CURRENT_ENTITY] == "number.new_charger_current"
    assert entry.data[CONF_GRID_VOLTAGE_ENTITY] == "sensor.grid_voltage"
    assert entry.data[CONF_LOW_TARIFF_ENTITY] == "binary_sensor.low_tariff"
    assert entry.data[CONF_NOTIFICATION_TARGET_ENTITY] == "notify.mobile_app"


async def test_r20_ac7_withdrawing_a_capability_drops_its_mapping_fields(hass):
    """R20 AC7 / ADR-0025 point 2: solar answered 'no' where it was 'yes' -> the solar step is
    never shown, so solar_forecast_entity never enters the accumulator and is absent from the
    saved data bucket (and so is ev_soc_entity, solar's only source for it here)."""
    data = entry_data_base(
        **{
            CONF_SOLAR_AVAILABLE: True,
            CONF_EV_SOC_ENTITY: "sensor.ev_soc",
            CONF_SOLAR_FORECAST_ENTITY: "sensor.solar_forecast",
        }
    )
    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)

    result = await _run_reconfigure_flow(
        hass, entry, per_step={STEP_CORE: {CONF_SOLAR_AVAILABLE: False}}
    )
    assert result["type"] == FlowResultType.ABORT
    assert entry.data[CONF_SOLAR_AVAILABLE] is False
    assert CONF_SOLAR_FORECAST_ENTITY not in entry.data
    assert CONF_EV_SOC_ENTITY not in entry.data


async def test_r20_ac7_reconfigure_leaves_the_options_bucket_untouched(hass):
    """UC12 1a: 'any of its thresholds already stored in the options bucket are left untouched'
    -- byte-for-byte equal before and after, including the withdrawn capability's thresholds."""
    data = entry_data_base(
        **{
            CONF_SOLAR_AVAILABLE: True,
            CONF_EV_SOC_ENTITY: "sensor.ev_soc",
            CONF_SOLAR_FORECAST_ENTITY: "sensor.solar_forecast",
        }
    )
    options = entry_options_base(**{CONF_SOLAR_START_THRESHOLD_W: 999.0})
    entry = MockConfigEntry(domain=DOMAIN, data=data, options=options)
    entry.add_to_hass(hass)
    original_options = dict(entry.options)

    result = await _run_reconfigure_flow(
        hass, entry, per_step={STEP_CORE: {CONF_SOLAR_AVAILABLE: False}}
    )
    assert result["type"] == FlowResultType.ABORT
    assert dict(entry.options) == original_options


async def test_adr0008_reconfigure_reloads_the_entry(hass):
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

    data = entry_data_base(**{CONF_CAPTAR_AVAILABLE: False})
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
    assert result["step_id"] == STEP_CORE

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_CHARGER_CURRENT_ENTITY: "number.new_charger_current",
            "charger_status_entity": "sensor.new_evse",
            CONF_CONNECTED_STATES: "Connected",
            CONF_CHARGING_STATES: "Charging",
            "net_power_entity": "sensor.net_power",
            "charger_power_entity": "sensor.charger_power",
            CONF_SOLAR_AVAILABLE: False,
            CONF_CAPTAR_AVAILABLE: False,
            CONF_DEADLINE_AVAILABLE: False,
            CONF_VEHICLE_LIMIT_MAPPED: False,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_MAPPINGS

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
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


async def test_uc12_1a_reconfigure_prefills_the_vehicle_limit_election_from_the_stored_mapping(
    hass,
):
    """Design D-2: no stored election key exists, so the answer is derived from whether
    vehicle_charge_limit_entity is mapped."""
    data = entry_data_base(
        **{
            CONF_VEHICLE_CHARGE_LIMIT_ENTITY: "number.vehicle_charge_limit",
            CONF_CAR_HOME_ENTITY: "person.driver",
        }
    )
    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    assert _suggested_values(result)[CONF_VEHICLE_LIMIT_MAPPED] is True


async def test_reconfigure_vehicle_limit_election_defaults_false_when_unmapped(hass):
    """The converse of the test above: no vehicle_charge_limit_entity stored -> the derived
    election is False, same as a fresh install that never elects it."""
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data_base(), options=entry_options_base())
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    assert _suggested_values(result)[CONF_VEHICLE_LIMIT_MAPPED] is False


async def test_reconfigure_still_runs_the_solar_steps_step_local_guard(hass):
    """T9 shares the exact step methods between install and reconfigure (ADR-0025 point 4),
    so every step-local guard already applies to reconfigure by construction -- each guard
    call runs unconditionally, with no `if self._mode is INSTALL` branch to accidentally skip
    it. There is therefore no separate reconfigure-specific guard implementation left to
    duplicate-test per guard (superseding the three now-removed reconfigure guard tests that
    predated this task's rewrite). This is the one smoke test confirming reconfigure genuinely
    walks the shared table rather than some other, guard-less path."""
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data_base(), options=entry_options_base())
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**CORE_INPUT, CONF_SOLAR_AVAILABLE: True}
    )
    assert result["step_id"] == STEP_SOLAR

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SOLAR_FORECAST_ENTITY: "sensor.solar_forecast"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_SOLAR
    assert result["errors"] == {CONF_EV_SOC_ENTITY: ERROR_REQUIRED_WHEN_SOLAR_AVAILABLE}


async def test_ev_soc_is_optional_when_solar_not_installed(hass):
    # Design doc §3/§8: with solar_available and captar_available both declared absent
    # (CORE_INPUT's default), ev_soc is optional -- an install without it still produces a
    # valid entry.
    result = await _run_install_flow(hass)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert CONF_EV_SOC_ENTITY not in result["data"]
    assert result["data"][CONF_SOLAR_AVAILABLE] is False


# test_solar_available_true_requires_ev_soc is superseded by
# test_r20_ac6_missing_ev_soc_is_reported_on_the_solar_step (T4 section below): the rejection
# now surfaces on the solar step itself, not the thresholds-step safety net.


async def test_solar_available_true_with_ev_soc_succeeds(hass):
    """The mirror of the guard test above: mapping ev_soc on the solar step (T4) lets a
    solar-declared install proceed all the way to CREATE_ENTRY."""
    result = await _run_install_flow(hass, per_step={STEP_CORE: {CONF_SOLAR_AVAILABLE: True}})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_EV_SOC_ENTITY] == "sensor.ev_soc"
    assert result["data"][CONF_SOLAR_FORECAST_ENTITY] == "sensor.solar_forecast"


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
    result = await _run_install_flow(hass)
    assert result["options"][CONF_DEFAULT_SOC_LIMIT] == DEFAULT_SOC_LIMIT


async def test_solar_declared_thresholds_seeded_into_options_with_defaults(hass):
    result = await _run_install_flow(hass, per_step={STEP_CORE: {CONF_SOLAR_AVAILABLE: True}})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_SOLAR_ONLY_STRATEGY] == DEFAULT_SOLAR_ONLY_STRATEGY
    assert result["options"][CONF_SOLAR_RESERVE_SOC] == DEFAULT_SOLAR_RESERVE_SOC


async def test_options_flow_edits_solar_thresholds(hass):
    entry = await _create_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**_current_options(entry), CONF_SOLAR_START_THRESHOLD_W: 200.0}
    )
    await hass.async_block_till_done()
    assert entry.options[CONF_SOLAR_START_THRESHOLD_W] == 200.0


# test_thresholds_error_preserves_previously_entered_values (T3/T4, deferred through T5/T6) is
# retired, not restored: T7 deletes the thresholds step's `_mapping_errors` safety net outright
# now that all three guards it combined are step-local (the last one, _car_home_missing_error,
# moves to the new vehicle_limit step below). The thresholds step never shows an error again,
# so there is no longer a suggested-value-preservation behaviour of its own left to pin --
# `test_ungated_thresholds_step_reports_no_mapping_error_of_its_own` (T7 section below) is this
# removal's regression guard instead.


async def test_solar_error_preserves_previously_entered_values(hass):
    """The solar step's own new guard (T4) re-shows the SAME step with suggested values from
    the rejected submission preserved -- the solar-step analogue of the thresholds-step test
    above, now that the guard runs here."""
    result = await _run_install_flow(
        hass,
        per_step={
            STEP_CORE: {CONF_SOLAR_AVAILABLE: True},
            STEP_SOLAR: {CONF_EV_SOC_ENTITY: None, CONF_SOLAR_START_THRESHOLD_W: 175.0},
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_SOLAR

    suggested = {key.schema: key.description for key in result["data_schema"].schema}
    assert suggested[CONF_SOLAR_START_THRESHOLD_W]["suggested_value"] == 175.0


# test_reconfigure_rejects_solar_available_true_without_ev_soc,
# test_reconfigure_rejects_solar_available_true_without_solar_forecast and
# test_reconfigure_rejects_both_ev_soc_and_solar_forecast_missing_together (pre-T9) each pinned
# a guard against T7's now-deleted flat three-guard combine inlined directly into
# async_step_reconfigure. T9 replaces that flat form with a delegate into the shared `core`
# step (ADR-0025 point 4), so every step-local guard already covers reconfigure by
# construction -- see test_reconfigure_still_runs_the_solar_steps_step_local_guard (T9 section
# below) for the one smoke test that still needs to exist.


async def test_captar_available_defaults_true(hass):
    # Design doc §3: R18 ("defaulting to present") / entity-catalog.md's sc_captar_available.
    # Now that the captar step exists (T5), the direct and observable proof mirrors
    # test_solar_available_defaults_true below: omitting the field lets CORE_MAPPING_SCHEMA's
    # own default apply, and the captar table row's own gate reads it -- the step SHOWS.
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    core_input = {k: v for k, v in CORE_INPUT.items() if k != CONF_CAPTAR_AVAILABLE}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], core_input)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_CAPTAR


async def test_solar_available_defaults_true(hass):
    # Design doc, "Decisions on two forks" §2: the core step's rendered default is True (R20
    # AC1's "defaulting to present"), deliberately diverging from DEFAULT_SOLAR_AVAILABLE
    # (False, the absent-key read fallback). Now that the solar step exists (T4), the direct
    # and observable proof is that the step SHOWS at all when the field is omitted -- the
    # solar table row's own gate reads this schema-level default.
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    core_input = {k: v for k, v in CORE_INPUT.items() if k != CONF_SOLAR_AVAILABLE}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], core_input)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_SOLAR


# test_captar_available_true_requires_ev_soc is superseded by
# test_r20_ac6_missing_ev_soc_is_reported_on_the_captar_step (T5 section below): the rejection
# now surfaces on the captar step itself, not the thresholds-step safety net.


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
    result = await _run_install_flow(hass)
    assert result["options"][CONF_MAX_PEAK_KW] == DEFAULT_MAX_PEAK_KW
    assert result["options"][CONF_POWER_RESPECT_PEAK] == DEFAULT_POWER_RESPECT_PEAK
    assert result["options"][CONF_SAFETY_MARGIN_W] == DEFAULT_SAFETY_MARGIN_W
    assert result["options"][CONF_PEAK_GRACE_MIN] == DEFAULT_PEAK_GRACE_MIN


async def test_captar_declared_cooldown_seeded_into_options_with_defaults(hass):
    result = await _run_install_flow(hass, per_step={STEP_CORE: {CONF_CAPTAR_AVAILABLE: True}})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_CAPTAR_COOLDOWN_MIN] == DEFAULT_CAPTAR_COOLDOWN_MIN


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


# test_solar_forecast_required_when_solar_available is superseded by
# test_r20_ac6_missing_solar_forecast_is_reported_on_the_solar_step (T4 section below): the
# rejection now surfaces on the solar step itself, not the thresholds-step safety net.


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
    # departure_external_entity lives on the deadline step (T6's own tests below) --
    # home_day_external_entity is a distinct, ungated mapping, exercised here.
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
    result = await _run_install_flow(hass)
    assert result["options"][CONF_EV_BATTERY_CAPACITY_KWH] == DEFAULT_EV_BATTERY_CAPACITY_KWH


async def test_solar_declared_new_thresholds_seeded_with_defaults(hass):
    result = await _run_install_flow(hass, per_step={STEP_CORE: {CONF_SOLAR_AVAILABLE: True}})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_MAX_SOLAR_SOC] == DEFAULT_MAX_SOLAR_SOC
    assert result["options"][CONF_SOLAR_STEP_PP] == DEFAULT_SOLAR_STEP_PP
    assert result["options"][CONF_SOLAR_STEP_THRESHOLD_PP] == DEFAULT_SOLAR_STEP_THRESHOLD_PP
    assert (
        result["options"][CONF_SOLAR_FORECAST_THRESHOLD_KWH] == DEFAULT_SOLAR_FORECAST_THRESHOLD_KWH
    )


async def test_options_flow_edits_the_new_thresholds(hass):
    entry = await _create_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**_current_options(entry), CONF_SOLAR_RESERVE_SOC: 55.0}
    )
    await hass.async_block_till_done()
    assert entry.options[CONF_SOLAR_RESERVE_SOC] == 55.0


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


# test_reconfigure_rejects_vehicle_limit_mapped_without_car_home (pre-T9) is superseded the
# same way as the solar/captar reconfigure guard tests above: see
# test_reconfigure_still_runs_the_solar_steps_step_local_guard's docstring (T9 section below).


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
    # OPTION_KEYS member that lives on a step this run didn't declare (solar/captar/deadline,
    # all three gated off by CORE_INPUT).
    assert sorted(result["options"]) == sorted(
        _keys(_ungated_threshold_schema(include_interval=True))
    )
    assert result["options"][CONF_CONTROL_INTERVAL_S] == DEFAULT_CONTROL_INTERVAL_S


async def test_adr0025_option_keys_consumption_is_intersection_based(hass):
    """ADR-0025 Consequences: a skipped step leaves its OPTION_KEYS members absent from the
    accumulator; the terminal step must intersect, not index. Declaring solar/captar/deadline
    absent (as CORE_INPUT does) is enough on its own to prove this -- their own steps'
    OPTION_KEYS members are absent purely because their gates failed, not because the steps
    don't exist."""
    result = await _run_install_flow(hass)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert CONF_SOLAR_START_THRESHOLD_W not in result["options"]
    assert CONF_CAPTAR_COOLDOWN_MIN not in result["options"]
    assert CONF_REMINDER_LEAD_H not in result["options"]


# --- T4: the solar step. ---


async def test_uc12_step3_solar_declared_shows_solar_step_with_its_own_thresholds(hass):
    """UC12 step 3: declaring solar on the core step shows the solar step next, carrying
    both the mapping and threshold halves for the install flow (design, "Schema fragments")."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**CORE_INPUT, CONF_SOLAR_AVAILABLE: True}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_SOLAR
    assert _keys(result["data_schema"]) == (
        _keys(_solar_mapping_schema(include_ev_soc=True)) | _keys(_solar_threshold_schema())
    )


async def test_uc12_2a_solar_absent_skips_the_solar_step(hass):
    """UC12 exception/alternate flow 2a: declaring solar absent skips straight to the
    ungated mappings step -- the solar step never shows."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CORE_INPUT)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_MAPPINGS


async def test_r20_ac3_solar_absent_install_stores_no_solar_threshold_keys(hass):
    """R20 AC3: with solar declared absent, none of the solar threshold fragment's OPTION_KEYS
    members are stored -- the flip side of
    test_adr0025_option_keys_consumption_is_intersection_based, stated as its own named R20
    acceptance criterion."""
    result = await _run_install_flow(hass)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    for key in _keys(_solar_threshold_schema()):
        assert key not in result["options"]


async def test_r20_ac6_missing_ev_soc_is_reported_on_the_solar_step(hass):
    """R20 AC6 / UC12 exception flow 2 / ADR-0025 point 1: the error is field-local
    (errors == {CONF_EV_SOC_ENTITY: ERROR_REQUIRED_WHEN_SOLAR_AVAILABLE}), the same step is
    re-shown, and the flow has NOT advanced -- replacing the end-of-form _mapping_errors case."""
    result = await _run_install_flow(
        hass,
        per_step={
            STEP_CORE: {CONF_SOLAR_AVAILABLE: True},
            STEP_SOLAR: {CONF_EV_SOC_ENTITY: None},
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_SOLAR
    assert result["errors"] == {CONF_EV_SOC_ENTITY: ERROR_REQUIRED_WHEN_SOLAR_AVAILABLE}


async def test_r20_ac6_missing_solar_forecast_is_reported_on_the_solar_step(hass):
    result = await _run_install_flow(
        hass,
        per_step={
            STEP_CORE: {CONF_SOLAR_AVAILABLE: True},
            STEP_SOLAR: {CONF_SOLAR_FORECAST_ENTITY: None},
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_SOLAR
    assert result["errors"] == {CONF_SOLAR_FORECAST_ENTITY: ERROR_REQUIRED_WHEN_SOLAR_AVAILABLE}


async def test_r20_ac6_wrong_domain_solar_forecast_entity_is_rejected(hass):
    """R20 AC6 / UC12 exception flow 1 ('a mapped entity is of the wrong domain for its
    role'): this is the OTHER half of AC6, which every other AC6 test above covers only for
    a blank required field. Submit the solar step with an entity id whose domain the field's
    EntitySelector does not allow -> the submission is rejected and the solar step is
    re-shown; the flow does not advance. The solar-forecast mapping is the first
    EntitySelector-backed required field a gated step introduces, so this is where the
    domain-mismatch half of AC6 gets its named test (design, success criterion 6)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**CORE_INPUT, CONF_SOLAR_AVAILABLE: True}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_SOLAR

    bad_input = {**SOLAR_INPUT, CONF_SOLAR_FORECAST_ENTITY: "switch.not_a_sensor"}
    with pytest.raises(vol.Invalid):
        await hass.config_entries.flow.async_configure(result["flow_id"], bad_input)
    assert not hass.config_entries.async_entries(DOMAIN)
    # The rejected submission never reached the flow handler (voluptuous raised first), so the
    # flow itself is still sitting on the solar step -- the direct non-advancement proof, not
    # just the (necessary but weaker) absence of a created entry.
    assert hass.config_entries.flow.async_get(result["flow_id"])["step_id"] == STEP_SOLAR


async def test_solar_step_error_can_be_corrected_and_the_flow_advances(hass):
    """The recovery path T4's fix depends on: a rejected solar submission is not a dead end --
    resubmitting with the missing mapping filled in advances the flow normally, and the earlier
    rejected attempt leaves no residue in self._answers."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**CORE_INPUT, CONF_SOLAR_AVAILABLE: True}
    )
    assert result["step_id"] == STEP_SOLAR

    rejected = {k: v for k, v in SOLAR_INPUT.items() if k != CONF_EV_SOC_ENTITY}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], rejected)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_SOLAR
    assert result["errors"] == {CONF_EV_SOC_ENTITY: ERROR_REQUIRED_WHEN_SOLAR_AVAILABLE}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], SOLAR_INPUT)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_MAPPINGS


# --- T5: the CapTar step, and the once-only EV state-of-charge mapping. ---


async def test_r20_ac4_ev_soc_asked_on_solar_step_only_when_both_capabilities_declared(hass):
    """R20 AC4 / UC12 postcondition 3: solar and CapTar both present -> the EV state-of-charge
    mapping appears on the solar step and NOT again on the CapTar step."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**CORE_INPUT, CONF_SOLAR_AVAILABLE: True, CONF_CAPTAR_AVAILABLE: True}
    )
    assert result["step_id"] == STEP_SOLAR
    assert CONF_EV_SOC_ENTITY in _keys(result["data_schema"])

    result = await hass.config_entries.flow.async_configure(result["flow_id"], SOLAR_INPUT)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_CAPTAR
    assert CONF_EV_SOC_ENTITY not in _keys(result["data_schema"])


async def test_r20_ac4_both_capabilities_declared_install_completes_with_ev_soc_once(hass):
    """The end-to-end companion to the schema-shape test above: with both capabilities
    declared, the captar step's own guard (config_flow.py's async_step_captar) must read
    ev_soc off self._answers, not off this step's own (deliberately ev_soc-less) submission --
    exactly the wiring ADR-0025's Consequences flags as needing particular care. Proven by
    completing the install without ever answering ev_soc on the captar step and confirming it
    reaches CREATE_ENTRY with ev_soc in DATA and both capabilities' OPTION_KEYS in OPTIONS."""
    result = await _run_install_flow(
        hass,
        per_step={
            STEP_CORE: {CONF_SOLAR_AVAILABLE: True, CONF_CAPTAR_AVAILABLE: True},
            # ev_soc is not on the captar step's schema this run (already collected on
            # solar) -- CAPTAR_INPUT's base value would be an unknown-key vol.Invalid here.
            STEP_CAPTAR: {CONF_EV_SOC_ENTITY: None},
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_EV_SOC_ENTITY] == "sensor.ev_soc"
    assert result["options"][CONF_SOLAR_ONLY_STRATEGY] == DEFAULT_SOLAR_ONLY_STRATEGY
    assert result["options"][CONF_CAPTAR_COOLDOWN_MIN] == DEFAULT_CAPTAR_COOLDOWN_MIN


async def test_r20_ac4_ev_soc_asked_on_captar_step_when_only_captar_declared(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**CORE_INPUT, CONF_CAPTAR_AVAILABLE: True}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_CAPTAR
    assert CONF_EV_SOC_ENTITY in _keys(result["data_schema"])


async def test_r20_ac4_ev_soc_never_asked_when_neither_capability_declared(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CORE_INPUT)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_MAPPINGS
    assert CONF_EV_SOC_ENTITY not in _keys(result["data_schema"])


async def test_r20_ac6_missing_ev_soc_is_reported_on_the_captar_step(hass):
    """... with ERROR_REQUIRED_WHEN_CAPTAR_AVAILABLE, not the solar code."""
    result = await _run_install_flow(
        hass,
        per_step={
            STEP_CORE: {CONF_CAPTAR_AVAILABLE: True},
            STEP_CAPTAR: {CONF_EV_SOC_ENTITY: None},
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_CAPTAR
    assert result["errors"] == {CONF_EV_SOC_ENTITY: ERROR_REQUIRED_WHEN_CAPTAR_AVAILABLE}


async def test_uc12_step4_captar_step_presents_the_captar_cooldown(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**CORE_INPUT, CONF_CAPTAR_AVAILABLE: True}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_CAPTAR
    assert _keys(result["data_schema"]) == (
        _keys(_captar_mapping_schema(include_ev_soc=True)) | _keys(_captar_threshold_schema())
    )


async def test_uc12_2a_captar_absent_skips_the_captar_step(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CORE_INPUT)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_MAPPINGS


async def test_r20_ac3_captar_absent_install_stores_no_captar_threshold_keys(hass):
    result = await _run_install_flow(hass)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    for key in _keys(_captar_threshold_schema()):
        assert key not in result["options"]


async def test_captar_step_error_can_be_corrected_and_the_flow_advances(hass):
    """The captar-step analogue of test_solar_step_error_can_be_corrected_and_the_flow_advances
    (T4): a rejected captar submission is fixable on the spot, not a dead end."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**CORE_INPUT, CONF_CAPTAR_AVAILABLE: True}
    )
    assert result["step_id"] == STEP_CAPTAR

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_CAPTAR
    assert result["errors"] == {CONF_EV_SOC_ENTITY: ERROR_REQUIRED_WHEN_CAPTAR_AVAILABLE}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], CAPTAR_INPUT)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_MAPPINGS


# --- T6: the deadline step. ---


async def test_uc12_step5_deadline_step_presents_departure_mapping_and_reminder_lead(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**CORE_INPUT, CONF_DEADLINE_AVAILABLE: True}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_DEADLINE
    assert _keys(result["data_schema"]) == (
        _keys(DEADLINE_MAPPING_SCHEMA) | _keys(_deadline_threshold_schema())
    )


async def test_uc12_2a_deadline_absent_skips_the_deadline_step(hass):
    """UC12 exception/alternate flow 2a: declaring deadline absent skips straight to the
    ungated mappings step -- the deadline step never shows. The direct proof that the field
    is never OFFERED (R18 AC7's other half from the stored-entry check below)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CORE_INPUT)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_MAPPINGS


async def test_r18_ac7_deadline_absent_offers_no_departure_or_reminder_field(hass):
    """R18 AC7 / R20 AC3: the deadline step is skipped entirely, and the stored entry carries
    neither departure_external_entity nor reminder_lead_h."""
    result = await _run_install_flow(hass)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert CONF_DEPARTURE_EXTERNAL_ENTITY not in result["data"]
    assert CONF_REMINDER_LEAD_H not in result["options"]


async def test_uc12_step5_departure_mapping_is_optional(hass):
    """UC12 step 5 calls it 'the optional external departure-time mapping' -- submitting the
    step without it advances."""
    result = await _run_install_flow(hass, per_step={STEP_CORE: {CONF_DEADLINE_AVAILABLE: True}})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert CONF_DEPARTURE_EXTERNAL_ENTITY not in result["data"]
    assert result["options"][CONF_REMINDER_LEAD_H] == DEFAULT_REMINDER_LEAD_H


async def test_uc12_step5_deadline_declared_departure_mapping_can_be_set(hass):
    result = await _run_install_flow(
        hass,
        per_step={
            STEP_CORE: {CONF_DEADLINE_AVAILABLE: True},
            STEP_DEADLINE: {CONF_DEPARTURE_EXTERNAL_ENTITY: "sensor.departure_time"},
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_DEPARTURE_EXTERNAL_ENTITY] == "sensor.departure_time"


async def test_uc12_step5_deadline_declared_reminder_lead_can_be_set(hass):
    result = await _run_install_flow(
        hass,
        per_step={
            STEP_CORE: {CONF_DEADLINE_AVAILABLE: True},
            STEP_DEADLINE: {CONF_REMINDER_LEAD_H: 3.0},
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_REMINDER_LEAD_H] == 3.0


# --- T7: the vehicle-charge-limit step, and removal of the validation safety net. ---


async def test_uc12_step6_elected_vehicle_limit_asks_the_limit_and_car_home_together(hass):
    """UC12 step 6: "the two are always asked together"."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**CORE_INPUT, CONF_VEHICLE_LIMIT_MAPPED: True}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_VEHICLE_LIMIT
    assert _keys(result["data_schema"]) == _keys(VEHICLE_LIMIT_MAPPING_SCHEMA)


async def test_uc12_2a_declined_vehicle_limit_asks_neither_field(hass):
    """UC12 exception/alternate flow 2a: declining the election skips straight to the ungated
    mappings step -- the vehicle_limit step, and both its fields, never show."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CORE_INPUT)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_MAPPINGS
    assert not {CONF_VEHICLE_CHARGE_LIMIT_ENTITY, CONF_CAR_HOME_ENTITY} & _keys(
        result["data_schema"]
    )


async def test_r20_ac6_missing_car_home_is_reported_on_the_vehicle_limit_step(hass):
    """errors == {CONF_CAR_HOME_ENTITY: ERROR_REQUIRED_WHEN_VEHICLE_LIMIT_MAPPED}, same step
    re-shown, flow not advanced."""
    result = await _run_install_flow(
        hass,
        per_step={
            STEP_CORE: {CONF_VEHICLE_LIMIT_MAPPED: True},
            STEP_VEHICLE_LIMIT: {CONF_CAR_HOME_ENTITY: None},
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_VEHICLE_LIMIT
    assert result["errors"] == {CONF_CAR_HOME_ENTITY: ERROR_REQUIRED_WHEN_VEHICLE_LIMIT_MAPPED}


async def test_d2_vehicle_limit_election_is_not_persisted(hass):
    """Design D-2: the election is a transient form key -- entity-catalog.md has no row for it,
    so CONF_VEHICLE_LIMIT_MAPPED must not appear in EITHER stored bucket. Checking both (not
    just data) pins that `_async_finish` pops it before both `_split_data` and the OPTION_KEYS
    intersection run, not just before one of the two."""
    result = await _run_install_flow(hass, per_step={STEP_CORE: {CONF_VEHICLE_LIMIT_MAPPED: True}})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert CONF_VEHICLE_LIMIT_MAPPED not in result["data"]
    assert CONF_VEHICLE_LIMIT_MAPPED not in result["options"]
    assert result["data"][CONF_VEHICLE_CHARGE_LIMIT_ENTITY] == "number.vehicle_charge_limit"
    assert result["data"][CONF_CAR_HOME_ENTITY] == "person.driver"


def test_mapping_errors_combiner_is_deleted():
    """Removal's actual regression guard (ADR-0025, Consequences: "the combiner has no
    guided-flow step left that needs all three"). An end-to-end flow test cannot discriminate
    this deletion: every condition `_mapping_errors` used to catch is now blocked one step
    earlier by its own step-local guard, so no reachable state ever reaches the thresholds
    step still violating one -- a fully-satisfied install would pass identically whether or
    not this helper (and the call to it this task also deleted) had ever been removed. Only a
    direct structural check pins the deletion itself."""
    assert not hasattr(config_flow_module, "_mapping_errors")


async def test_all_capabilities_and_vehicle_limit_declared_install_completes(hass):
    """Happy-path integration coverage (not a removal regression guard -- see
    test_mapping_errors_combiner_is_deleted for that): every capability/election declared and
    every step-local guard satisfied still reaches CREATE_ENTRY. Now the
    (True, True, True, True) row of T8's traversal matrix below duplicates this exact
    combination -- kept anyway since it predates that matrix and still documents the T7
    removal's own happy path in context, right next to the deletion it accompanies."""
    result = await _run_install_flow(
        hass,
        per_step={
            STEP_CORE: {
                CONF_SOLAR_AVAILABLE: True,
                CONF_CAPTAR_AVAILABLE: True,
                CONF_DEADLINE_AVAILABLE: True,
                CONF_VEHICLE_LIMIT_MAPPED: True,
            },
            STEP_CAPTAR: {CONF_EV_SOC_ENTITY: None},
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY


# --- T8: traversal matrix -- every enablement combination, in UC12's order. ---
# Test-only task (plan T8): no production code. If a combination below fails, the fix belongs
# to the step task that owns the offending step, not here.


@pytest.mark.parametrize(
    "solar,captar,deadline,vehicle", list(itertools.product([True, False], repeat=4))
)
async def test_uc12_step2_traversal_visits_exactly_the_prescribed_steps_in_order(
    hass, solar, captar, deadline, vehicle
):
    """UC12 step 2 + 2a / R20 AC2 + AC3: the visited step ids are exactly
    [core] + [solar if solar] + [captar if captar] + [deadline if deadline]
    + [vehicle_limit if vehicle] + [mappings, thresholds] -- order included. Asserted as
    equality, not "contains", so both a skipped and an extra step fail."""
    step_inputs = {
        STEP_CORE: {
            **CORE_INPUT,
            CONF_SOLAR_AVAILABLE: solar,
            CONF_CAPTAR_AVAILABLE: captar,
            CONF_DEADLINE_AVAILABLE: deadline,
            CONF_VEHICLE_LIMIT_MAPPED: vehicle,
        },
        STEP_SOLAR: SOLAR_INPUT,
        # R20 AC4's once-only rule: omit ev_soc here when solar already collected it, or the
        # captar step's schema (which then excludes the field) rejects it as an unknown key.
        # Derived from CAPTAR_INPUT rather than hard-coded to {}, so a future field added to
        # that fixture is still carried through instead of silently dropped.
        STEP_CAPTAR: (
            {k: v for k, v in CAPTAR_INPUT.items() if k != CONF_EV_SOC_ENTITY}
            if solar
            else CAPTAR_INPUT
        ),
        STEP_DEADLINE: DEADLINE_INPUT,
        STEP_VEHICLE_LIMIT: VEHICLE_LIMIT_INPUT,
        STEP_MAPPINGS: MAPPINGS_INPUT,
        STEP_THRESHOLDS: THRESHOLDS_INPUT,
    }
    expected_steps = (
        [STEP_CORE]
        + ([STEP_SOLAR] if solar else [])
        + ([STEP_CAPTAR] if captar else [])
        + ([STEP_DEADLINE] if deadline else [])
        + ([STEP_VEHICLE_LIMIT] if vehicle else [])
        + [STEP_MAPPINGS, STEP_THRESHOLDS]
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    visited = [result["step_id"]]
    while result["type"] == FlowResultType.FORM:
        last_step_id = result["step_id"]
        if last_step_id not in step_inputs:
            pytest.fail(f"unexpected step {last_step_id!r}; visited so far {visited}")
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], step_inputs[last_step_id]
        )
        if result["type"] == FlowResultType.FORM:
            if result["step_id"] == last_step_id:
                # a step-local guard rejected the fixture and re-showed itself -- stop here
                # (rather than resubmitting the same, still-failing input forever) so the
                # equality assertion below fails with a readable diff instead of hanging,
                # mirroring _run_install_flow's own re-show guard.
                visited.append(result["step_id"])
                break
            visited.append(result["step_id"])

    assert visited == expected_steps
    assert result["type"] == FlowResultType.CREATE_ENTRY

    # Design doc, "Safety caveat": the grid-safety threshold group is on an ungated step, so it
    # is present -- with the submitted value, not a silently-standing-in default -- in every
    # combination's options regardless of any capability answer.
    for key in (
        CONF_NOMINAL_VOLTAGE,
        CONF_MIN_CURRENT,
        CONF_MAX_CURRENT,
        CONF_GRID_CEILING_A,
        CONF_GRID_SAFETY_OFFSET_A,
    ):
        assert result["options"][key] == THRESHOLDS_INPUT[key]


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
    with no reordering permitted -- a subsequence check, not full-population equality. T8's
    traversal matrix is the exact-sequence assertion for CONFIG_TABLE; the TODO(T10) note on
    UC12_FIXED_STEP_ORDER covers the still-open OPTIONS_TABLE completeness check."""
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
