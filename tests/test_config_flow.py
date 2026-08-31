"""HA-harness config-flow tests (ADR-0005).

T4 (topic-step config-flow plan, ADR-0027) cut the install/reconfigure flow over from the
seven-step model ADR-0025 (superseded by ADR-0027) specified to the nine topic steps. T7
completes the re-cut: the options flow now walks its own nine-topic-step OPTIONS_TABLE too
(ADR-0027 point 4) -- threshold halves only, gated on the *stored* capability flags, and the
sole presenter of the control interval.
"""

import itertools

import pytest
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_charging import config_flow as config_flow_module
from custom_components.smart_charging import const
from custom_components.smart_charging.adapters.factory import build_adapters
from custom_components.smart_charging.adapters.tariff import LowTariffReadAdapter
from custom_components.smart_charging.config_flow import (
    CONFIG_TABLE,
    CORE_MAPPING_SCHEMA,
    DEADLINE_MAPPING_SCHEMA,
    EV_CHARGER_MAPPING_SCHEMA,
    GRID_MAPPING_SCHEMA,
    NOTIFICATIONS_MAPPING_SCHEMA,
    OPTION_KEYS,
    OPTIONS_TABLE,
    SOLAR_MAPPING_SCHEMA,
    UC12_FIXED_STEP_ORDER,
    VEHICLE_MAPPING_SCHEMA,
    FlowMode,
    FlowStep,
    SmartChargingConfigFlow,
    SmartChargingOptionsFlow,
    _captar_threshold_schema,
    _core_threshold_schema,
    _deadline_threshold_schema,
    _ev_charger_threshold_schema,
    _grid_threshold_schema,
    _notifications_threshold_schema,
    _power_threshold_schema,
    _solar_threshold_schema,
    _TableWalkMixin,
    _vehicle_threshold_schema,
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
    CONF_DEADLINE_NOTICE_ENABLED,
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
    CONF_LOW_TARIFF_STATES,
    CONF_MAX_CURRENT,
    CONF_MAX_PEAK_KW,
    CONF_MAX_SOLAR_SOC,
    CONF_MIN_CURRENT,
    CONF_NET_POWER_ENTITY,
    CONF_NOMINAL_VOLTAGE,
    CONF_NOTIFICATION_TARGET_ENTITY,
    CONF_NOTIFICATIONS_AVAILABLE,
    CONF_PEAK_FLOOR_KW,
    CONF_PEAK_GRACE_MIN,
    CONF_PLUG_IN_REMINDER_ENABLED,
    CONF_POWER_COOLDOWN_MIN,
    CONF_POWER_RESPECT_PEAK,
    CONF_REMINDER_LEAD_H,
    CONF_SAFETY_MARGIN_W,
    CONF_SMOOTHING_WINDOW,
    CONF_SOLAR_AVAILABLE,
    CONF_SOLAR_COOLDOWN_MIN,
    CONF_SOLAR_FORECAST_ENTITY,
    CONF_SOLAR_FORECAST_THRESHOLD_KWH,
    CONF_SOLAR_HOLD_MIN,
    CONF_SOLAR_ONLY_HOLD_MIN,
    CONF_SOLAR_ONLY_MIDPOINT,
    CONF_SOLAR_ONLY_START_THRESHOLD_W,
    CONF_SOLAR_ONLY_STRATEGY,
    CONF_SOLAR_POWER_ENTITY,
    CONF_SOLAR_RESERVE_SOC,
    CONF_SOLAR_RESTART_DEBOUNCE_MIN,
    CONF_SOLAR_START_THRESHOLD_W,
    CONF_SOLAR_STEP_PP,
    CONF_SOLAR_STEP_THRESHOLD_PP,
    CONF_STATUS_TRANSLATION,
    CONF_VEHICLE_CHARGE_LIMIT_ENTITY,
    DEFAULT_CAPTAR_COOLDOWN_MIN,
    DEFAULT_CONTROL_INTERVAL_S,
    DEFAULT_DEADLINE_NOTICE_ENABLED,
    DEFAULT_DEFAULT_TARGET_CURRENT,
    DEFAULT_EV_BATTERY_CAPACITY_KWH,
    DEFAULT_EVENING_PROMPT_ENABLED,
    DEFAULT_GRID_CEILING_A,
    DEFAULT_GRID_SAFETY_OFFSET_A,
    DEFAULT_MAX_CURRENT,
    DEFAULT_MIN_CURRENT,
    DEFAULT_NOMINAL_VOLTAGE,
    DEFAULT_NOTIFICATIONS_AVAILABLE,
    DEFAULT_PLUG_IN_REMINDER_ENABLED,
    DEFAULT_POWER_COOLDOWN_MIN,
    DEFAULT_SMOOTHING_WINDOW,
    DEFAULT_SOC_LIMIT,
    DEFAULT_SOLAR_ONLY_STRATEGY,
    DOMAIN,
    ERROR_REQUIRED_WHEN_DEADLINE_AVAILABLE,
    ERROR_REQUIRED_WHEN_VEHICLE_LIMIT_MAPPED,
    ROLE_CAR_HOME,
    ROLE_CHARGER_CURRENT,
    ROLE_VEHICLE_CHARGE_LIMIT,
    STATE_CHARGING,
    STATE_CONNECTED,
    STEP_CAPTAR,
    STEP_CORE,
    STEP_DEADLINE,
    STEP_EV_CHARGER,
    STEP_GRID,
    STEP_NOTIFICATIONS,
    STEP_POWER,
    STEP_SOLAR,
    STEP_VEHICLE,
)
from tests.helpers import entry_data_base, entry_options_base, seed_charger_states

# Per-step base fixtures for the guided install flow (UC12's nine topic steps). All four
# capability decisions default False here, including solar -- even though solar's rendered
# form default is True -- because CORE_INPUT is a fixture of explicit values, not a proof of
# the schema default (see test_uc12_core_solar_available_defaults_true for that), and leaving
# it False keeps every test that doesn't care about a capability off that capability's step
# entirely.
CORE_INPUT = {
    CONF_SOLAR_AVAILABLE: False,
    CONF_CAPTAR_AVAILABLE: False,
    CONF_DEADLINE_AVAILABLE: False,
    CONF_NOTIFICATIONS_AVAILABLE: False,
}

GRID_INPUT = {
    CONF_NET_POWER_ENTITY: "sensor.net_power",
}

EV_CHARGER_INPUT = {
    CONF_CHARGER_CURRENT_ENTITY: "number.charger_current",
    CONF_CHARGER_STATUS_ENTITY: "sensor.evse",
    CONF_CONNECTED_STATES: "Connected, Cable",
    CONF_CHARGING_STATES: "Charging, SuspendedEV",
    CONF_CHARGER_POWER_ENTITY: "sensor.charger_power",
}

# ev_soc_entity is vol.Required (R20 AC4) -- always needs a value here, whatever the
# capability declarations.
VEHICLE_INPUT = {
    CONF_EV_SOC_ENTITY: "sensor.ev_soc",
}

POWER_INPUT = {}

CAPTAR_INPUT = {}

SOLAR_INPUT = {
    CONF_SOLAR_FORECAST_ENTITY: "sensor.solar_forecast",
}

DEADLINE_INPUT = {}

NOTIFICATIONS_INPUT = {}

_INSTALL_STEP_BASES = {
    STEP_CORE: CORE_INPUT,
    STEP_GRID: GRID_INPUT,
    STEP_EV_CHARGER: EV_CHARGER_INPUT,
    STEP_VEHICLE: VEHICLE_INPUT,
    STEP_POWER: POWER_INPUT,
    STEP_CAPTAR: CAPTAR_INPUT,
    STEP_SOLAR: SOLAR_INPUT,
    STEP_DEADLINE: DEADLINE_INPUT,
    STEP_NOTIFICATIONS: NOTIFICATIONS_INPUT,
}

_ALL_CAPABILITIES_TRUE = {
    CONF_SOLAR_AVAILABLE: True,
    CONF_CAPTAR_AVAILABLE: True,
    CONF_DEADLINE_AVAILABLE: True,
    CONF_NOTIFICATIONS_AVAILABLE: True,
}

# Every one of the 2**4 (solar, captar, deadline, notifications) capability combinations
# (R20 AC2 / AC3; ADR-0027 Consequences) -- shared by the install (T5) and reconfigure (T6)
# traversal-matrix tests.
ALL_SIXTEEN = list(itertools.product([False, True], repeat=4))


async def _walk_flow(hass, init_result, *, per_step=None):
    """Shared driver behind `_run_install_flow`/`_run_reconfigure_flow`: from an
    already-initiated flow's first result, follow whichever steps the table shows this run --
    which steps appear (e.g. `solar`) varies with the capability flags answered on the core
    step, so this follows the flow's own `step_id` rather than a fixed sequence. Submits each
    step's base fixture (strict lookup -- a step with no fixture is a bug in the fixture
    table, not something to paper over with an empty submission) merged with
    `per_step[<step id>]`'s overrides (a value of None removes that key). Returns the final
    flow result: success on completion, or the re-shown FORM the moment a step-local guard
    rejects a submission -- detected as the same step_id appearing twice in a row, which stops
    the loop instead of resubmitting the same, still-failing fixture forever."""
    overrides = per_step or {}
    consumed_overrides: set[str] = set()
    result = init_result
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


async def _run_install_flow(hass, *, capabilities=None, per_step_input=None):
    """Drive the install flow. `capabilities` overrides the four core-step flags (defaults
    all False, mirroring CORE_INPUT); `per_step_input` overrides any other step's fixture."""
    init_result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    overrides = dict(per_step_input or {})
    if capabilities:
        overrides[STEP_CORE] = {**overrides.get(STEP_CORE, {}), **capabilities}
    return await _walk_flow(hass, init_result, per_step=overrides)


async def _create_entry(hass, *, capabilities=None, per_step_input=None):
    result = await _run_install_flow(hass, capabilities=capabilities, per_step_input=per_step_input)
    return result["result"]


async def _run_reconfigure_flow(hass, entry, *, capabilities=None, per_step_input=None):
    """The reconfigure analogue of `_run_install_flow` (ADR-0027 point 5): entered via
    SOURCE_RECONFIGURE, otherwise identical -- same shared `_walk_flow` driver. `power`/
    `captar` are gated off entirely in this mode (UC12 1a), so the walk always ends at
    ABORT/reconfigure_successful, never CREATE_ENTRY."""
    init_result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    overrides = dict(per_step_input or {})
    if capabilities:
        overrides[STEP_CORE] = {**overrides.get(STEP_CORE, {}), **capabilities}
    return await _walk_flow(hass, init_result, per_step=overrides)


async def _run_options_flow(hass, entry, *, per_step=None):
    """Drive the options flow across whichever steps `OPTIONS_TABLE` shows for this entry's
    STORED capability flags (ADR-0027 point 4). Unlike the install/reconfigure drivers, the
    base submission for every step is empty: every threshold field is `vol.Required(default=
    ...)`, built fresh at render time from `self.config_entry.options`, so an empty submission
    is exactly an unedited resubmission of the current stored value -- `per_step[<step id>]`'s
    overrides are the only values that actually change anything."""
    overrides = per_step or {}
    consumed_overrides: set[str] = set()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    last_step_id = None
    while result["type"] == FlowResultType.FORM:
        step_id = result["step_id"]
        if step_id == last_step_id:
            break
        last_step_id = step_id
        consumed_overrides.add(step_id)
        submission = overrides.get(step_id, {})
        result = await hass.config_entries.options.async_configure(result["flow_id"], submission)
    unconsumed = overrides.keys() - consumed_overrides
    assert not unconsumed, (
        f"per_step override(s) for {unconsumed} were never applied -- that step never "
        "rendered this run (a capability answer this test relies on may be missing/typo'd)"
    )
    return result


def _keys(schema) -> set[str]:
    return {str(k) for k in schema.schema}


def _suggested_values(result):
    """Map schema key -> its prefilled suggested_value (absent keys omitted)."""
    return {
        key.schema: key.description["suggested_value"]
        for key in result["data_schema"].schema
        if key.description and "suggested_value" in key.description
    }


# --- Structural/framework tests: single-instance-allowed, overlapping states. ---


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
        per_step_input={
            STEP_EV_CHARGER: {
                CONF_CONNECTED_STATES: "Connected, Charging",
                CONF_CHARGING_STATES: "Charging",
            }
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_STATUS_TRANSLATION]["Charging"] == STATE_CHARGING


async def test_no_grid_voltage_still_creates_entry(hass):
    """grid_voltage_entity is optional (NF4) -- omitting it still creates the entry."""
    result = await _run_install_flow(hass)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert CONF_GRID_VOLTAGE_ENTITY not in result["data"]


# --- low_tariff state-translation (issue #746, T3). ---


@pytest.mark.parametrize("domain", ["sensor", "select", "input_select"])
async def test_grid_step_accepts_widened_low_tariff_domains(hass, domain):
    # Widened selector: a sensor/select/input_select tariff signal with a textual
    # state must be selectable, not just binary_sensor/input_boolean.
    entity_id = f"{domain}.tariff"
    result = await _run_install_flow(
        hass,
        per_step_input={
            STEP_GRID: {
                **GRID_INPUT,
                CONF_LOW_TARIFF_ENTITY: entity_id,
                CONF_LOW_TARIFF_STATES: "low, off-peak",
            }
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_LOW_TARIFF_ENTITY] == entity_id
    assert result["data"][CONF_LOW_TARIFF_STATES] == "low, off-peak"


async def test_grid_step_low_tariff_states_optional(hass):
    # Submitting the grid step with CONF_LOW_TARIFF_ENTITY mapped but
    # CONF_LOW_TARIFF_STATES left blank must still succeed.
    result = await _run_install_flow(
        hass,
        per_step_input={
            STEP_GRID: {**GRID_INPUT, CONF_LOW_TARIFF_ENTITY: "binary_sensor.low_tariff"}
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_LOW_TARIFF_ENTITY] == "binary_sensor.low_tariff"
    assert CONF_LOW_TARIFF_STATES not in result["data"]


async def test_reconfigure_grid_step_prefills_low_tariff_states(hass):
    # Issue #499 class: an entry already carrying CONF_LOW_TARIFF_STATES must render
    # it as the grid step's suggested value on reconfigure, and resubmitting the
    # prefilled form unchanged must not null it out. Unlike CONF_CONNECTED_STATES/
    # CONF_CHARGING_STATES, this field has no "known gap" carve-out; it must
    # actually prefill (design doc §2).
    data = dict(_RECONFIGURE_ENTRY_DATA)
    data[CONF_LOW_TARIFF_ENTITY] = "sensor.tariff"
    data[CONF_LOW_TARIFF_STATES] = "low, off-peak"
    entry = MockConfigEntry(domain=DOMAIN, data=data, options={})
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _suggested_values(result)
    )
    assert result["step_id"] == STEP_GRID
    suggested = _suggested_values(result)
    assert suggested[CONF_LOW_TARIFF_ENTITY] == "sensor.tariff"
    assert suggested[CONF_LOW_TARIFF_STATES] == "low, off-peak"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], suggested)
    assert result["step_id"] == STEP_EV_CHARGER
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            **EV_CHARGER_INPUT,
            CONF_CONNECTED_STATES: "Connected",
            CONF_CHARGING_STATES: "Charging",
        },
    )
    assert result["step_id"] == STEP_VEHICLE
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _suggested_values(result)
    )
    assert result["step_id"] == STEP_NOTIFICATIONS
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _suggested_values(result)
    )
    assert result["type"] == FlowResultType.ABORT
    await hass.async_block_till_done()
    assert entry.data[CONF_LOW_TARIFF_STATES] == "low, off-peak"


async def test_factory_builds_adapter_matching_flow_submitted_states(hass):
    # Integration checkpoint (design doc §4 criterion 7): drive the config flow to
    # produce a real entry with a sensor-domain low_tariff mapping and a states
    # table, then feed entry.data into build_adapters and assert the resulting
    # LowTariffReadAdapter's _low_states matches -- proving the flow's output and
    # the factory's input actually agree, not just each half against hand-built
    # fixtures.
    result = await _run_install_flow(
        hass,
        per_step_input={
            STEP_GRID: {
                **GRID_INPUT,
                CONF_LOW_TARIFF_ENTITY: "sensor.tariff",
                CONF_LOW_TARIFF_STATES: "low, off-peak",
            }
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    adapters = build_adapters(hass, result["data"])
    adapter = adapters[const.ROLE_LOW_TARIFF]
    assert isinstance(adapter, LowTariffReadAdapter)
    assert adapter._low_states == {"low", "off-peak"}


# --- Step 1 (plan T4) named tests. ---


def test_r20_ac1_core_mapping_is_exactly_the_four_capability_declarations():
    """R20 AC1 / design success criterion 1: CORE_MAPPING_SCHEMA is the four capability
    declarations and nothing more -- no mapping field survives on `core` from the seven-step
    model, where it carried the four core mappings too."""
    assert _keys(CORE_MAPPING_SCHEMA) == {
        CONF_SOLAR_AVAILABLE,
        CONF_CAPTAR_AVAILABLE,
        CONF_DEADLINE_AVAILABLE,
        CONF_NOTIFICATIONS_AVAILABLE,
    }


async def test_uc12_install_all_capabilities_walks_all_nine_steps_in_order(hass):
    """UC12 step 2 / R20 AC2: every capability declared present -> every one of the nine
    steps shows, in UC12's fixed order (captar before solar)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    visited = [result["step_id"]]
    # deadline_available True makes car_home_entity required on the vehicle step (design D-3).
    step_inputs = {
        **_INSTALL_STEP_BASES,
        STEP_CORE: {**CORE_INPUT, **_ALL_CAPABILITIES_TRUE},
        STEP_VEHICLE: {**VEHICLE_INPUT, CONF_CAR_HOME_ENTITY: "person.driver"},
    }
    while result["type"] == FlowResultType.FORM:
        step_id = result["step_id"]
        if visited.count(step_id) > 1:
            pytest.fail(f"step {step_id!r} re-shown twice; visited so far: {visited}")
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], step_inputs[step_id]
        )
        if result["type"] == FlowResultType.FORM:
            visited.append(result["step_id"])

    assert visited == [STEP_CORE, *UC12_FIXED_STEP_ORDER]
    assert result["type"] == FlowResultType.CREATE_ENTRY


async def test_uc12_install_default_capabilities_skips_notifications(hass):
    """R18 AC9 / UC12 5a: a household accepting the defaults is offered steps 6-8 (captar,
    solar, deadline) but NOT step 9 -- the one capability that is opted into rather than out
    of (its form default is False, unlike the other three)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    visited = [result["step_id"]]
    # Submit the core step with every OTHER field defaulted (i.e. omit them entirely) so the
    # schema's own defaults (solar/captar/deadline present, notifications absent) apply.
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    visited.append(result["step_id"])
    # DEFAULT_DEADLINE_AVAILABLE is True, so deadline is present by default too -- car_home is
    # therefore required on the vehicle step (design D-3).
    step_inputs = {
        **_INSTALL_STEP_BASES,
        STEP_VEHICLE: {**VEHICLE_INPUT, CONF_CAR_HOME_ENTITY: "person.driver"},
    }
    while result["type"] == FlowResultType.FORM:
        step_id = result["step_id"]
        if visited.count(step_id) > 1:
            pytest.fail(f"step {step_id!r} re-shown twice; visited so far: {visited}")
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], step_inputs[step_id]
        )
        if result["type"] == FlowResultType.FORM:
            visited.append(result["step_id"])

    assert STEP_NOTIFICATIONS not in visited
    assert visited == [
        STEP_CORE,
        STEP_GRID,
        STEP_EV_CHARGER,
        STEP_VEHICLE,
        STEP_POWER,
        STEP_CAPTAR,
        STEP_SOLAR,
        STEP_DEADLINE,
    ]
    assert result["type"] == FlowResultType.CREATE_ENTRY


@pytest.mark.parametrize("solar,captar,deadline,notifications", ALL_SIXTEEN)
async def test_r20_ac2_install_traverses_exactly_uc12s_steps_in_order(
    hass, solar, captar, deadline, notifications
):
    """R20 AC2 / AC3, UC12 5a (ADR-0027 Consequences): the five ungated steps (core, grid,
    ev_charger, vehicle, power) always show, plus exactly one step per declared capability, in
    UC12's fixed order (captar BEFORE solar). Expected sequence is computed here from the four
    flags, not read back from CONFIG_TABLE -- this is the test that exercises the gate logic
    itself, not a restatement of it."""
    expected = [STEP_CORE, STEP_GRID, STEP_EV_CHARGER, STEP_VEHICLE, STEP_POWER]
    if captar:
        expected.append(STEP_CAPTAR)
    if solar:
        expected.append(STEP_SOLAR)
    if deadline:
        expected.append(STEP_DEADLINE)
    if notifications:
        expected.append(STEP_NOTIFICATIONS)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    visited = [result["step_id"]]
    step_inputs = {
        **_INSTALL_STEP_BASES,
        STEP_CORE: {
            **CORE_INPUT,
            CONF_SOLAR_AVAILABLE: solar,
            CONF_CAPTAR_AVAILABLE: captar,
            CONF_DEADLINE_AVAILABLE: deadline,
            CONF_NOTIFICATIONS_AVAILABLE: notifications,
        },
    }
    # UC12 4a / design D-3: a present deadline capability requires car_home_entity on the
    # always-shown `vehicle` step -- fixture-only concession, not the behavior under test here.
    if deadline:
        step_inputs[STEP_VEHICLE] = {**VEHICLE_INPUT, CONF_CAR_HOME_ENTITY: "person.driver"}

    while result["type"] == FlowResultType.FORM:
        step_id = result["step_id"]
        if visited.count(step_id) > 1:
            pytest.fail(f"step {step_id!r} re-shown twice; visited so far: {visited}")
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], step_inputs[step_id]
        )
        if result["type"] == FlowResultType.FORM:
            visited.append(result["step_id"])

    assert visited == expected
    assert result["type"] == FlowResultType.CREATE_ENTRY


@pytest.mark.parametrize("solar,captar,deadline,notifications", ALL_SIXTEEN)
async def test_r20_ac5_grid_and_charger_bounds_are_asked_on_every_install_path(
    hass, solar, captar, deadline, notifications
):
    """Design, Safety caveat: grid_ceiling_a / grid_safety_offset_a / nominal_voltage (grid) and
    min_current / max_current (ev_charger) sit on ungated steps and can never be skipped by a
    capability gate, whatever the sixteen combinations declare."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            **CORE_INPUT,
            CONF_SOLAR_AVAILABLE: solar,
            CONF_CAPTAR_AVAILABLE: captar,
            CONF_DEADLINE_AVAILABLE: deadline,
            CONF_NOTIFICATIONS_AVAILABLE: notifications,
        },
    )
    assert result["step_id"] == STEP_GRID
    grid_keys = _keys(result["data_schema"])
    assert {CONF_GRID_CEILING_A, CONF_GRID_SAFETY_OFFSET_A, CONF_NOMINAL_VOLTAGE} <= grid_keys

    result = await hass.config_entries.flow.async_configure(result["flow_id"], GRID_INPUT)
    assert result["step_id"] == STEP_EV_CHARGER
    ev_charger_keys = _keys(result["data_schema"])
    assert {CONF_MIN_CURRENT, CONF_MAX_CURRENT} <= ev_charger_keys


async def test_r20_ac4_ev_soc_is_asked_on_vehicle_with_no_capabilities_declared(hass):
    """R20 AC4 / UC12 postconditions: presented exactly once, on the always-shown `vehicle`
    step, even when neither solar nor CapTar is declared -- the case the seven-step model
    could not present at all."""
    result = await _run_install_flow(hass)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_EV_SOC_ENTITY] == "sensor.ev_soc"


async def test_adr0005_install_splits_buckets_over_the_nine_step_answers(hass):
    """ADR-0005 / UC12 step 10: mappings + the four capability flags + the derived status
    translation in data; thresholds, defaults and seed values in options;
    control_interval_s defaulted, never asked (UC12 1b)."""
    result = await _run_install_flow(hass)
    assert result["type"] == FlowResultType.CREATE_ENTRY

    assert result["data"][CONF_SOLAR_AVAILABLE] is False
    assert result["data"][CONF_CAPTAR_AVAILABLE] is False
    assert result["data"][CONF_DEADLINE_AVAILABLE] is False
    assert result["data"][CONF_NOTIFICATIONS_AVAILABLE] is False
    assert result["data"][CONF_STATUS_TRANSLATION] == {
        "Connected": STATE_CONNECTED,
        "Cable": STATE_CONNECTED,
        "Charging": STATE_CHARGING,
        "SuspendedEV": STATE_CHARGING,
    }
    assert CONF_GRID_CEILING_A not in result["data"]

    # Positive proof the ungated steps' threshold halves are actually asked and stored, not
    # just that the gated ones are absent -- __init__.py reads several of these (min_current,
    # max_current, nominal_voltage, grid_ceiling_a, default_target_current) by DIRECT
    # indexing, so a dropped `.extend(...)` on core/grid/ev_charger/power would KeyError at
    # setup with no config-flow test catching it otherwise.
    assert result["options"][CONF_SMOOTHING_WINDOW] == DEFAULT_SMOOTHING_WINDOW
    assert result["options"][CONF_NOMINAL_VOLTAGE] == DEFAULT_NOMINAL_VOLTAGE
    assert result["options"][CONF_GRID_CEILING_A] == DEFAULT_GRID_CEILING_A
    assert result["options"][CONF_GRID_SAFETY_OFFSET_A] == DEFAULT_GRID_SAFETY_OFFSET_A
    assert result["options"][CONF_MIN_CURRENT] == DEFAULT_MIN_CURRENT
    assert result["options"][CONF_MAX_CURRENT] == DEFAULT_MAX_CURRENT
    assert result["options"][CONF_DEFAULT_TARGET_CURRENT] == DEFAULT_DEFAULT_TARGET_CURRENT
    assert result["options"][CONF_POWER_COOLDOWN_MIN] == DEFAULT_POWER_COOLDOWN_MIN
    assert result["options"][CONF_EV_BATTERY_CAPACITY_KWH] == DEFAULT_EV_BATTERY_CAPACITY_KWH
    assert result["options"][CONF_DEFAULT_SOC_LIMIT] == DEFAULT_SOC_LIMIT
    assert result["options"][CONF_CONTROL_INTERVAL_S] == DEFAULT_CONTROL_INTERVAL_S
    # Every OPTION_KEYS member gated off this run (solar/captar/deadline/notifications all
    # absent) is genuinely absent from options -- an intersection, not a default stand-in.
    assert CONF_SOLAR_START_THRESHOLD_W not in result["options"]
    assert CONF_CAPTAR_COOLDOWN_MIN not in result["options"]
    assert CONF_REMINDER_LEAD_H not in result["options"]
    assert CONF_DEADLINE_NOTICE_ENABLED not in result["options"]


async def test_r20_ac3_captar_absent_install_stores_no_peak_protection_keys(hass):
    """UC12 5b / R18 AC5: all five peak-protection values are now behind the CapTar gate."""
    result = await _run_install_flow(hass)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    for key in _keys(_captar_threshold_schema()):
        assert key not in result["options"]


async def test_r20_ac3_notifications_absent_install_stores_no_notification_keys(hass):
    """R18 AC10: no target mapping, no enable toggle, no evening-prompt time."""
    result = await _run_install_flow(hass)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert CONF_NOTIFICATION_TARGET_ENTITY not in result["data"]
    for key in _keys(_notifications_threshold_schema()):
        assert key not in result["options"]


async def test_uc12_5c_home_day_external_is_absent_when_deadlines_are_unmanaged(hass):
    """UC12 5c / R20 AC5: home_day_external_entity sits on the deadline-gated step -- with
    deadline declared absent, the deadline step never shows and the field is absent."""
    result = await _run_install_flow(hass)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert CONF_HOME_DAY_EXTERNAL_ENTITY not in result["data"]


async def test_r18_ac11_notification_toggles_default_on_and_land_in_options(hass):
    """R18 AC11: the three per-notification enable toggles each default on and land in the
    options bucket."""
    result = await _run_install_flow(hass, capabilities={CONF_NOTIFICATIONS_AVAILABLE: True})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_DEADLINE_NOTICE_ENABLED] == DEFAULT_DEADLINE_NOTICE_ENABLED
    assert result["options"][CONF_DEADLINE_NOTICE_ENABLED] is True
    assert result["options"][CONF_PLUG_IN_REMINDER_ENABLED] == DEFAULT_PLUG_IN_REMINDER_ENABLED
    assert result["options"][CONF_PLUG_IN_REMINDER_ENABLED] is True
    assert result["options"][CONF_EVENING_PROMPT_ENABLED] == DEFAULT_EVENING_PROMPT_ENABLED


# --- The `core` step. ---


async def test_uc12_core_solar_available_defaults_true(hass):
    """R20 AC1's 'defaulting to present': the core step's rendered default for solar is True,
    deliberately diverging from DEFAULT_SOLAR_AVAILABLE (design D-5). Proven by omitting the
    field from the submission and confirming the solar step still shows next."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    core_input = {k: v for k, v in CORE_INPUT.items() if k != CONF_SOLAR_AVAILABLE}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], core_input)
    for step_id in (STEP_GRID, STEP_EV_CHARGER, STEP_VEHICLE, STEP_POWER):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _INSTALL_STEP_BASES[step_id]
        )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_SOLAR


async def test_uc12_core_notifications_available_defaults_false(hass):
    """The converse (design D-5): notifications' form default and DEFAULT_NOTIFICATIONS_
    AVAILABLE agree, both False -- omitting the field must NOT show the notifications step."""
    result = await _run_install_flow(
        hass,
        capabilities={CONF_DEADLINE_AVAILABLE: True},
        per_step_input={STEP_VEHICLE: {**VEHICLE_INPUT, CONF_CAR_HOME_ENTITY: "person.driver"}},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_NOTIFICATIONS_AVAILABLE] is False


# --- The `grid`/`ev_charger` steps: always shown. ---


async def test_uc12_grid_step_presents_mapping_and_threshold_halves(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CORE_INPUT)
    assert result["step_id"] == STEP_GRID
    assert _keys(result["data_schema"]) == (
        _keys(GRID_MAPPING_SCHEMA) | _keys(_grid_threshold_schema())
    )


async def test_uc12_ev_charger_step_schema_shape(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CORE_INPUT)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], GRID_INPUT)
    assert result["step_id"] == STEP_EV_CHARGER
    assert _keys(result["data_schema"]) == (
        _keys(EV_CHARGER_MAPPING_SCHEMA) | _keys(_ev_charger_threshold_schema())
    )


# --- The `vehicle` step: ev_soc required, car_home guard. ---


async def test_r20_ac6_blank_required_ev_soc_is_reported_on_the_vehicle_step(hass):
    """R20 AC6 / ADR-0027 point 1: ev_soc_entity is a plain vol.Required on
    VEHICLE_MAPPING_SCHEMA now (the once-only cross-step guard is gone) -- a blank submission
    surfaces as InvalidData from the flow manager (a subclass of vol.Invalid), not a
    step-local error dict, and no entry is created."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    for step_id in (STEP_CORE, STEP_GRID, STEP_EV_CHARGER):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _INSTALL_STEP_BASES[step_id]
        )
    assert result["step_id"] == STEP_VEHICLE
    with pytest.raises(vol.Invalid):
        await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert not hass.config_entries.async_entries(DOMAIN)


async def test_r20_ac6_missing_car_home_is_reported_on_the_vehicle_step_charge_limit_trigger(
    hass,
):
    """UC12 4a / design D-3: a filled-in vehicle charge limit without car_home is rejected on
    the vehicle step, field-local, with ERROR_REQUIRED_WHEN_VEHICLE_LIMIT_MAPPED."""
    result = await _run_install_flow(
        hass,
        per_step_input={
            STEP_VEHICLE: {
                **VEHICLE_INPUT,
                CONF_VEHICLE_CHARGE_LIMIT_ENTITY: "number.vehicle_charge_limit",
            }
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_VEHICLE
    assert result["errors"] == {CONF_CAR_HOME_ENTITY: ERROR_REQUIRED_WHEN_VEHICLE_LIMIT_MAPPED}


async def test_r20_ac6_missing_car_home_is_reported_on_the_vehicle_step_deadline_trigger(hass):
    """UC12 4a's SECOND independent trigger (design D-3): a present deadline capability
    (declared earlier, on `core`) without car_home is rejected here too, with the OTHER error
    code -- ERROR_REQUIRED_WHEN_DEADLINE_AVAILABLE, not the charge-limit one."""
    result = await _run_install_flow(hass, capabilities={CONF_DEADLINE_AVAILABLE: True})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_VEHICLE
    assert result["errors"] == {CONF_CAR_HOME_ENTITY: ERROR_REQUIRED_WHEN_DEADLINE_AVAILABLE}


async def test_car_home_guard_charge_limit_trigger_takes_precedence_when_both_fire(hass):
    """Design D-3: the charge-limit trigger is checked first, so a submission that trips both
    triggers at once reports the message tied to the field just filled in on this same step."""
    result = await _run_install_flow(
        hass,
        capabilities={CONF_DEADLINE_AVAILABLE: True},
        per_step_input={
            STEP_VEHICLE: {
                **VEHICLE_INPUT,
                CONF_VEHICLE_CHARGE_LIMIT_ENTITY: "number.vehicle_charge_limit",
            }
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_VEHICLE
    assert result["errors"] == {CONF_CAR_HOME_ENTITY: ERROR_REQUIRED_WHEN_VEHICLE_LIMIT_MAPPED}


async def test_car_home_guard_satisfied_when_mapped(hass):
    result = await _run_install_flow(
        hass,
        capabilities={CONF_DEADLINE_AVAILABLE: True},
        per_step_input={
            STEP_VEHICLE: {
                **VEHICLE_INPUT,
                CONF_VEHICLE_CHARGE_LIMIT_ENTITY: "number.vehicle_charge_limit",
                CONF_CAR_HOME_ENTITY: "person.driver",
            }
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CAR_HOME_ENTITY] == "person.driver"


async def test_neither_vehicle_limit_nor_car_home_is_accepted(hass):
    """UC09 precondition: unmapped vehicle limit and absent deadline -> no requirement."""
    result = await _run_install_flow(hass)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert CONF_VEHICLE_CHARGE_LIMIT_ENTITY not in result["data"]
    assert CONF_CAR_HOME_ENTITY not in result["data"]


async def test_pre_field_entry_reads_vehicle_limit_and_car_home_as_absent(hass):
    """An entry created before these fields must not KeyError -- no migration needed."""
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


# --- The `power`/`captar` steps: threshold-only, gated off in reconfigure. ---


async def test_uc12_power_step_is_threshold_only(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    for step_id in (STEP_CORE, STEP_GRID, STEP_EV_CHARGER, STEP_VEHICLE):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _INSTALL_STEP_BASES[step_id]
        )
    assert result["step_id"] == STEP_POWER
    assert _keys(result["data_schema"]) == _keys(_power_threshold_schema())


async def test_uc12_captar_step_is_threshold_only_no_ev_soc(hass):
    """CapTar has no mapping half at all in the topic-step model -- unlike the seven-step
    model, no ev_soc field ever appears on this step (it moved wholly to `vehicle`)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    for step_id in (STEP_CORE, STEP_GRID, STEP_EV_CHARGER, STEP_VEHICLE, STEP_POWER):
        submission = (
            {**CORE_INPUT, CONF_CAPTAR_AVAILABLE: True}
            if step_id == STEP_CORE
            else _INSTALL_STEP_BASES[step_id]
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], submission)
    assert result["step_id"] == STEP_CAPTAR
    assert _keys(result["data_schema"]) == _keys(_captar_threshold_schema())
    assert CONF_EV_SOC_ENTITY not in _keys(result["data_schema"])

    result = await hass.config_entries.flow.async_configure(result["flow_id"], CAPTAR_INPUT)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_CAPTAR_COOLDOWN_MIN] == DEFAULT_CAPTAR_COOLDOWN_MIN


async def test_uc12_2a_captar_absent_skips_the_captar_step(hass):
    """Solar declared present (so a step exists right after `power` to land on), captar left
    absent (CORE_INPUT's default) -- the captar step must not be the one shown."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    step_inputs = {**_INSTALL_STEP_BASES, STEP_CORE: {**CORE_INPUT, CONF_SOLAR_AVAILABLE: True}}
    for step_id in (STEP_CORE, STEP_GRID, STEP_EV_CHARGER, STEP_VEHICLE, STEP_POWER):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], step_inputs[step_id]
        )
    assert result["step_id"] == STEP_SOLAR


# --- The `solar` step. ---


async def test_uc12_solar_step_presents_mapping_and_threshold_halves(hass):
    result = await _run_install_flow(hass, capabilities={CONF_SOLAR_AVAILABLE: True})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_SOLAR_FORECAST_ENTITY] == "sensor.solar_forecast"
    assert result["options"][CONF_SOLAR_ONLY_STRATEGY] == DEFAULT_SOLAR_ONLY_STRATEGY


async def test_r20_ac6_blank_required_solar_forecast_is_reported_on_the_solar_step(hass):
    """R20 AC6 / ADR-0027 point 1: solar_forecast_entity is a plain vol.Required on
    SOLAR_MAPPING_SCHEMA now -- a blank submission surfaces as InvalidData from the flow
    manager, not as an end-of-flow error, and no entry is created."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    for step_id in (STEP_CORE, STEP_GRID, STEP_EV_CHARGER, STEP_VEHICLE, STEP_POWER):
        submission = (
            {**CORE_INPUT, CONF_SOLAR_AVAILABLE: True}
            if step_id == STEP_CORE
            else _INSTALL_STEP_BASES[step_id]
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], submission)
    assert result["step_id"] == STEP_SOLAR
    with pytest.raises(vol.Invalid):
        await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert not hass.config_entries.async_entries(DOMAIN)


async def test_solar_power_entity_is_optional(hass):
    result = await _run_install_flow(hass, capabilities={CONF_SOLAR_AVAILABLE: True})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert CONF_SOLAR_POWER_ENTITY not in result["data"]


async def test_solar_power_entity_can_be_mapped(hass):
    result = await _run_install_flow(
        hass,
        capabilities={CONF_SOLAR_AVAILABLE: True},
        per_step_input={STEP_SOLAR: {**SOLAR_INPUT, CONF_SOLAR_POWER_ENTITY: "sensor.solar_power"}},
    )
    assert result["data"][CONF_SOLAR_POWER_ENTITY] == "sensor.solar_power"


async def test_uc12_2a_solar_absent_skips_the_solar_step(hass):
    """Every capability declared absent (CORE_INPUT's default): with captar/deadline/
    notifications also off, the flow has nothing left to show after `power` and completes --
    the direct proof that solar (and everything after it) was skipped, not just deferred."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    for step_id in (STEP_CORE, STEP_GRID, STEP_EV_CHARGER, STEP_VEHICLE, STEP_POWER):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _INSTALL_STEP_BASES[step_id]
        )
    assert result["type"] == FlowResultType.CREATE_ENTRY


# --- The `deadline` step. ---


async def test_uc12_deadline_step_presents_mapping_and_threshold_halves(hass):
    result = await _run_install_flow(
        hass,
        capabilities={CONF_DEADLINE_AVAILABLE: True},
        per_step_input={
            STEP_DEADLINE: {
                CONF_DEPARTURE_EXTERNAL_ENTITY: "sensor.departure_time",
                CONF_HOME_DAY_EXTERNAL_ENTITY: "binary_sensor.home_day",
                CONF_REMINDER_LEAD_H: 3.0,
            },
            STEP_VEHICLE: {**VEHICLE_INPUT, CONF_CAR_HOME_ENTITY: "person.driver"},
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_DEPARTURE_EXTERNAL_ENTITY] == "sensor.departure_time"
    assert result["data"][CONF_HOME_DAY_EXTERNAL_ENTITY] == "binary_sensor.home_day"
    assert result["options"][CONF_REMINDER_LEAD_H] == 3.0


async def test_uc12_2a_deadline_absent_skips_the_deadline_step(hass):
    result = await _run_install_flow(hass)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert CONF_DEPARTURE_EXTERNAL_ENTITY not in result["data"]
    assert CONF_REMINDER_LEAD_H not in result["options"]


# --- The `notifications` step. ---


async def test_uc12_notifications_step_presents_mapping_and_threshold_halves(hass):
    result = await _run_install_flow(
        hass,
        capabilities={CONF_NOTIFICATIONS_AVAILABLE: True},
        per_step_input={
            STEP_NOTIFICATIONS: {
                CONF_NOTIFICATION_TARGET_ENTITY: "notify.mobile_app_phone",
            }
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_NOTIFICATION_TARGET_ENTITY] == "notify.mobile_app_phone"


async def test_notification_target_entity_rejects_non_notify_domain(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**CORE_INPUT, CONF_NOTIFICATIONS_AVAILABLE: True}
    )
    for step_id in (STEP_GRID, STEP_EV_CHARGER, STEP_VEHICLE, STEP_POWER):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _INSTALL_STEP_BASES[step_id]
        )
    assert result["step_id"] == STEP_NOTIFICATIONS

    bad_input = {CONF_NOTIFICATION_TARGET_ENTITY: "sensor.not_a_notify_entity"}
    with pytest.raises(vol.Invalid):
        await hass.config_entries.flow.async_configure(result["flow_id"], bad_input)
    assert not hass.config_entries.async_entries(DOMAIN)


# --- Reconfigure (UC12 1a). ---


_RECONFIGURE_ENTRY_DATA = {
    CONF_CHARGER_CURRENT_ENTITY: "number.charger_current",
    CONF_CHARGER_STATUS_ENTITY: "sensor.evse",
    CONF_NET_POWER_ENTITY: "sensor.net_power",
    CONF_CHARGER_POWER_ENTITY: "sensor.charger_power",
    CONF_GRID_VOLTAGE_ENTITY: "sensor.grid_voltage",
    CONF_LOW_TARIFF_ENTITY: "binary_sensor.low_tariff",
    CONF_NOTIFICATION_TARGET_ENTITY: "notify.mobile_app",
    CONF_EV_SOC_ENTITY: "sensor.ev_soc",
    CONF_SOLAR_AVAILABLE: False,
    CONF_CAPTAR_AVAILABLE: False,
    CONF_DEADLINE_AVAILABLE: False,
    CONF_NOTIFICATIONS_AVAILABLE: True,
    CONF_STATUS_TRANSLATION: {"Connected": STATE_CONNECTED, "Charging": STATE_CHARGING},
}


async def test_uc12_1a_reconfigure_never_shows_power_or_captar(hass):
    """ADR-0027 point 3: neither step has a mapping half, so both are absent from the
    reconfigure walk -- asserted with the CapTar capability PRESENT, so the only reason
    `captar` is skipped is the conjoined flow-mode half of its gate."""
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data_base(), options=entry_options_base())
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    visited = []
    overrides = {STEP_CORE: {**CORE_INPUT, CONF_CAPTAR_AVAILABLE: True}}
    while result["type"] == FlowResultType.FORM:
        step_id = result["step_id"]
        visited.append(step_id)
        submission = {**_INSTALL_STEP_BASES[step_id], **overrides.get(step_id, {})}
        result = await hass.config_entries.flow.async_configure(result["flow_id"], submission)
    assert result["type"] == FlowResultType.ABORT
    await hass.async_block_till_done()
    assert STEP_POWER not in visited
    assert STEP_CAPTAR not in visited


async def test_uc12_1a_reconfigure_shows_mapping_halves_only(hass):
    """UC12 1a: the per-capability steps that DO show in reconfigure are restricted to
    mapping fields only -- never a threshold field mixed in."""
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data_base(), options=entry_options_base())
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    assert result["step_id"] == STEP_CORE
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**CORE_INPUT, **_ALL_CAPABILITIES_TRUE}
    )
    assert result["step_id"] == STEP_GRID
    assert _keys(result["data_schema"]) == _keys(GRID_MAPPING_SCHEMA)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], GRID_INPUT)
    assert result["step_id"] == STEP_EV_CHARGER
    assert _keys(result["data_schema"]) == _keys(EV_CHARGER_MAPPING_SCHEMA)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], EV_CHARGER_INPUT)
    assert result["step_id"] == STEP_VEHICLE
    assert _keys(result["data_schema"]) == _keys(VEHICLE_MAPPING_SCHEMA)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**VEHICLE_INPUT, CONF_CAR_HOME_ENTITY: "person.driver"}
    )
    # power/captar have no mapping half -- both skipped entirely in reconfigure (proven by
    # test_uc12_1a_reconfigure_never_shows_power_or_captar), so the walk jumps straight here.
    assert result["step_id"] == STEP_SOLAR
    assert _keys(result["data_schema"]) == _keys(SOLAR_MAPPING_SCHEMA)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], SOLAR_INPUT)
    assert result["step_id"] == STEP_DEADLINE
    assert _keys(result["data_schema"]) == _keys(DEADLINE_MAPPING_SCHEMA)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], DEADLINE_INPUT)
    assert result["step_id"] == STEP_NOTIFICATIONS
    assert _keys(result["data_schema"]) == _keys(NOTIFICATIONS_MAPPING_SCHEMA)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], NOTIFICATIONS_INPUT)
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()


async def test_uc12_1a_reconfigure_shows_core_grid_ev_charger_vehicle_unconditionally(hass):
    """UC12 1a: the `vehicle` mapping half appears even with every capability absent."""
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data_base(), options=entry_options_base())
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    assert result["step_id"] == STEP_CORE
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CORE_INPUT)
    assert result["step_id"] == STEP_GRID
    assert _keys(result["data_schema"]) == _keys(GRID_MAPPING_SCHEMA)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], GRID_INPUT)
    assert result["step_id"] == STEP_EV_CHARGER
    assert _keys(result["data_schema"]) == _keys(EV_CHARGER_MAPPING_SCHEMA)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], EV_CHARGER_INPUT)
    assert result["step_id"] == STEP_VEHICLE
    assert _keys(result["data_schema"]) == _keys(VEHICLE_MAPPING_SCHEMA)

    # Every capability absent (CORE_INPUT's default): the vehicle step still shows, and
    # submitting it finishes the walk directly -- the direct proof that it is unconditional,
    # not merely reachable when some other capability happens to be on.
    result = await hass.config_entries.flow.async_configure(result["flow_id"], VEHICLE_INPUT)
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()


async def test_uc12_1a_reconfigure_prefills_step_one_from_the_existing_entry(hass):
    """ADR-0027 point 2: prefill is rendering-only, via add_suggested_values_to_schema."""
    entry = MockConfigEntry(domain=DOMAIN, data=dict(_RECONFIGURE_ENTRY_DATA), options={})
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_CORE

    suggested = _suggested_values(result)
    # A bool field with a schema-level default (captar_available) must also prefill from
    # entry.data, not fall back to the schema default.
    assert suggested[CONF_CAPTAR_AVAILABLE] is False
    assert suggested[CONF_NOTIFICATIONS_AVAILABLE] is True


async def test_reconfigure_form_prefills_existing_mappings(hass):
    # Issue #499: the blank reconfigure form must be prefilled from entry.data, otherwise
    # any optional mapping the user doesn't retype is silently dropped on save.
    entry = MockConfigEntry(domain=DOMAIN, data=dict(_RECONFIGURE_ENTRY_DATA), options={})
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _suggested_values(result)
    )
    assert result["step_id"] == STEP_GRID
    suggested = _suggested_values(result)
    assert suggested[CONF_GRID_VOLTAGE_ENTITY] == "sensor.grid_voltage"
    assert suggested[CONF_LOW_TARIFF_ENTITY] == "binary_sensor.low_tariff"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], suggested)
    assert result["step_id"] == STEP_EV_CHARGER

    # connected_states/charging_states are reconstructed from the stored translation dict
    # (`_unbuild_translation`), since only CONF_STATUS_TRANSLATION is persisted -- the raw
    # comma-separated fields the user typed have no stored key of their own.
    suggested = _suggested_values(result)
    assert suggested[CONF_CONNECTED_STATES] == "Connected"
    assert suggested[CONF_CHARGING_STATES] == "Charging"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], suggested)
    assert result["step_id"] == STEP_VEHICLE
    suggested = _suggested_values(result)
    assert suggested[CONF_EV_SOC_ENTITY] == "sensor.ev_soc"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], suggested)
    assert result["step_id"] == STEP_NOTIFICATIONS
    suggested = _suggested_values(result)
    assert suggested[CONF_NOTIFICATION_TARGET_ENTITY] == "notify.mobile_app"


async def test_r20_ac7_withdrawing_a_capability_drops_its_mapping_fields_only(hass):
    """UC12 1a / 5b: the withdrawn capability's mapping fields leave the data bucket (the
    accumulator was never seeded from the entry, ADR-0027 point 2), while its thresholds stay
    in options untouched -- solar answered 'no' where it was 'yes' -> the solar step is never
    shown, so solar_forecast_entity never enters the accumulator and is absent from the saved
    data bucket, but the stored solar thresholds in options are untouched (proven separately by
    test_r20_ac7_reconfigure_leaves_the_options_bucket_untouched)."""
    data = entry_data_base(
        **{
            CONF_SOLAR_AVAILABLE: True,
            CONF_EV_SOC_ENTITY: "sensor.ev_soc",
            CONF_SOLAR_FORECAST_ENTITY: "sensor.solar_forecast",
        }
    )
    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)

    result = await _run_reconfigure_flow(hass, entry, capabilities={CONF_SOLAR_AVAILABLE: False})
    assert result["type"] == FlowResultType.ABORT
    await hass.async_block_till_done()  # drain the background reload this ABORT schedules
    assert entry.data[CONF_SOLAR_AVAILABLE] is False
    assert CONF_SOLAR_FORECAST_ENTITY not in entry.data


async def test_r20_ac7_reconfigure_leaves_the_options_bucket_untouched(hass):
    """UC12 1a: any thresholds already stored in the options bucket are left untouched --
    byte-for-byte equal before and after, including the withdrawn capability's thresholds."""
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

    result = await _run_reconfigure_flow(hass, entry, capabilities={CONF_SOLAR_AVAILABLE: False})
    assert result["type"] == FlowResultType.ABORT
    await hass.async_block_till_done()  # drain the background reload this ABORT schedules
    assert dict(entry.options) == original_options


async def test_adr0008_reconfigure_reloads_the_entry(hass):
    """async_step_reconfigure is the only sanctioned path to remap entity roles
    (ADR-0005) -- it must replace data, leave options untouched, and reload the entry
    (ADR-0008: a mapping change tears down and recreates the coordinator)."""
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
        result["flow_id"], {**CORE_INPUT, CONF_SOLAR_AVAILABLE: True, CONF_DEADLINE_AVAILABLE: True}
    )
    assert result["step_id"] == STEP_GRID
    result = await hass.config_entries.flow.async_configure(result["flow_id"], GRID_INPUT)
    assert result["step_id"] == STEP_EV_CHARGER
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_CHARGER_CURRENT_ENTITY: "number.new_charger_current",
            CONF_CHARGER_STATUS_ENTITY: "sensor.new_evse",
            CONF_CONNECTED_STATES: "Connected",
            CONF_CHARGING_STATES: "Charging",
            CONF_CHARGER_POWER_ENTITY: "sensor.charger_power",
        },
    )
    assert result["step_id"] == STEP_VEHICLE
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**VEHICLE_INPUT, CONF_CAR_HOME_ENTITY: "person.driver"}
    )
    assert result["step_id"] == STEP_SOLAR
    result = await hass.config_entries.flow.async_configure(result["flow_id"], SOLAR_INPUT)
    assert result["step_id"] == STEP_DEADLINE
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
    new_coordinator = entry.runtime_data.coordinator
    assert new_coordinator is not original_coordinator
    assert (
        new_coordinator._adapters[ROLE_CHARGER_CURRENT]._entity_id == "number.new_charger_current"
    )


async def test_reconfigure_still_runs_the_solar_steps_step_local_guard(hass):
    """ADR-0027 point 5 shares the exact step methods between install and reconfigure, so
    every step-local guard already applies to reconfigure by construction. This is the smoke
    test confirming reconfigure genuinely walks the shared table: a solar_forecast_entity
    missing on the solar step is rejected by schema validation even in reconfigure mode."""
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data_base(), options=entry_options_base())
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**CORE_INPUT, CONF_SOLAR_AVAILABLE: True}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], GRID_INPUT)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], EV_CHARGER_INPUT)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], VEHICLE_INPUT)
    assert result["step_id"] == STEP_SOLAR

    with pytest.raises(vol.Invalid):
        await hass.config_entries.flow.async_configure(result["flow_id"], {})


@pytest.mark.parametrize("solar,captar,deadline,notifications", ALL_SIXTEEN)
async def test_r20_ac2_reconfigure_traverses_exactly_uc12s_mapping_halves(
    hass, solar, captar, deadline, notifications
):
    """ADR-0027 Consequences: every capability combination must be shown to traverse exactly
    the steps UC12 prescribes, in order, for EACH of the three flows -- this is the
    reconfigure third (T5 covers install, T7 options). Expected sequence: core, grid,
    ev_charger, vehicle, then solar/deadline/notifications per the capability answers given
    on THIS run's own `core` step (reconfigure gates on `self._answers`, not `entry.data` --
    that's the options flow's rule); never power, never captar."""
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data_base(), options=entry_options_base())
    entry.add_to_hass(hass)

    overrides = {
        STEP_CORE: {
            **CORE_INPUT,
            CONF_SOLAR_AVAILABLE: solar,
            CONF_CAPTAR_AVAILABLE: captar,
            CONF_DEADLINE_AVAILABLE: deadline,
            CONF_NOTIFICATIONS_AVAILABLE: notifications,
        },
        # car_home_entity is required whenever deadline is declared present (UC12 4a) --
        # supplied unconditionally since it's harmless on every other combination.
        STEP_VEHICLE: {**VEHICLE_INPUT, CONF_CAR_HOME_ENTITY: "person.driver"},
    }

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    visited = []
    while result["type"] == FlowResultType.FORM:
        step_id = result["step_id"]
        if step_id in visited:
            pytest.fail(f"step {step_id!r} re-shown; visited so far: {visited}")
        visited.append(step_id)
        submission = {**_INSTALL_STEP_BASES[step_id], **overrides.get(step_id, {})}
        result = await hass.config_entries.flow.async_configure(result["flow_id"], submission)
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()

    expected = [STEP_CORE, STEP_GRID, STEP_EV_CHARGER, STEP_VEHICLE]
    if solar:
        expected.append(STEP_SOLAR)
    if deadline:
        expected.append(STEP_DEADLINE)
    if notifications:
        expected.append(STEP_NOTIFICATIONS)
    assert visited == expected


async def test_d7_reconfigure_prefills_notifications_available_from_a_stored_target(hass):
    """Design D-7: an entry that predates notifications_available but stores a
    notification_target_entity renders the declaration ON, reaches step 9, and keeps the
    stored mapping -- the accumulator-never-seeded rule would otherwise drop it silently."""
    data = entry_data_base(**{CONF_NOTIFICATION_TARGET_ENTITY: "notify.mobile_app"})
    assert CONF_NOTIFICATIONS_AVAILABLE not in data
    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    assert result["step_id"] == STEP_CORE
    core_suggested = _suggested_values(result)
    assert core_suggested[CONF_NOTIFICATIONS_AVAILABLE] is True

    # Submit exactly the rendered suggestion for notifications_available (not a value typed
    # fresh in the test) -- proving the prefill itself, not just that the flag can be turned
    # on some other way. The other three capabilities are explicitly declined (irrelevant to
    # D-7) to keep the walk on the direct core -> grid -> ev_charger -> vehicle -> notifications
    # path -- entry.data has no stored answer for them, so nothing else is prefilled here.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            **CORE_INPUT,
            **core_suggested,
        },
    )
    assert result["step_id"] == STEP_GRID
    result = await hass.config_entries.flow.async_configure(result["flow_id"], GRID_INPUT)
    assert result["step_id"] == STEP_EV_CHARGER
    result = await hass.config_entries.flow.async_configure(result["flow_id"], EV_CHARGER_INPUT)
    assert result["step_id"] == STEP_VEHICLE
    result = await hass.config_entries.flow.async_configure(result["flow_id"], VEHICLE_INPUT)
    assert result["step_id"] == STEP_NOTIFICATIONS

    notifications_suggested = _suggested_values(result)
    assert notifications_suggested[CONF_NOTIFICATION_TARGET_ENTITY] == "notify.mobile_app"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], notifications_suggested
    )
    assert result["type"] == FlowResultType.ABORT
    await hass.async_block_till_done()
    assert entry.data[CONF_NOTIFICATIONS_AVAILABLE] is True
    assert entry.data[CONF_NOTIFICATION_TARGET_ENTITY] == "notify.mobile_app"


async def test_d7_reconfigure_stored_flag_false_wins_over_a_stored_target(hass):
    """Design D-7: `data.get(CONF_NOTIFICATIONS_AVAILABLE, bool(data.get(TARGET)))` -- the
    STORED flag wins whenever the key is present, and is only derived from the target when
    the key predates this slice. An entry that already answered "no" on notifications, but
    still carries a stale notification_target_entity from before it was withdrawn, must keep
    rendering the declaration OFF -- a naive `bool(FLAG) or bool(TARGET)` fallback would flip
    this back ON and make it impossible to ever leave notifications withdrawn on such an
    entry."""
    data = entry_data_base(
        **{
            CONF_NOTIFICATIONS_AVAILABLE: False,
            CONF_NOTIFICATION_TARGET_ENTITY: "notify.mobile_app",
        }
    )
    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    assert result["step_id"] == STEP_CORE
    suggested = _suggested_values(result)
    assert suggested[CONF_NOTIFICATIONS_AVAILABLE] is False


async def test_d7_reconfigure_declares_notifications_off_when_neither_key_is_stored(hass):
    """Design D-7 negative case: an entry with neither notifications_available nor a stored
    notification_target_entity renders the declaration OFF -- the derive-from-target fallback
    has nothing to derive from."""
    data = entry_data_base()
    assert CONF_NOTIFICATIONS_AVAILABLE not in data
    assert CONF_NOTIFICATION_TARGET_ENTITY not in data
    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    suggested = _suggested_values(result)
    assert suggested[CONF_NOTIFICATIONS_AVAILABLE] is False


# --- Exception flow 1: domain mismatch (T9, UC12, R20 AC6). ---


async def test_r20_ac6_wrong_domain_entity_is_rejected_on_the_step_that_presents_it(hass):
    """UC12 exception flow 1 / R20 AC6: e.g. a `sensor` entity where charger_current_entity
    requires a `number` domain -- rejected by the EntitySelector's own domain filter (`vol.
    Invalid`, naming the offending field), the flow does not advance, and no entry is created.
    Proven that the same step is still the one presented (not skipped, not corrupted) by
    resubmitting a valid mapping afterwards and landing on the very next step, not one further
    along."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CORE_INPUT)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], GRID_INPUT)
    assert result["step_id"] == STEP_EV_CHARGER

    bad_input = {**EV_CHARGER_INPUT, CONF_CHARGER_CURRENT_ENTITY: "sensor.wrong_domain"}
    with pytest.raises(vol.Invalid) as excinfo:
        await hass.config_entries.flow.async_configure(result["flow_id"], bad_input)
    assert excinfo.value.path == [CONF_CHARGER_CURRENT_ENTITY]
    assert not hass.config_entries.async_entries(DOMAIN)

    # Still parked on ev_charger, not advanced and not thrown back to an earlier step.
    result = await hass.config_entries.flow.async_configure(result["flow_id"], EV_CHARGER_INPUT)
    assert result["step_id"] == STEP_VEHICLE


# --- Abandonment (UC12 exception flow 3 / R20 AC8). ---


async def test_r20_ac8_abandoning_install_creates_no_entry(hass):
    """UC12 exception flow 3 / R20 AC8: closing the flow mid-walk creates no entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CORE_INPUT)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_GRID

    hass.config_entries.flow.async_abort(result["flow_id"])
    assert not hass.config_entries.async_entries(DOMAIN)
    assert not hass.config_entries.flow.async_progress()


async def test_r20_ac8_abandoning_reconfigure_leaves_the_entry_exactly_as_it_was(hass):
    """R20 AC8: closing a reconfigure flow mid-walk leaves both buckets byte-for-byte as they
    were before the flow started."""
    entry = await _create_entry(hass)
    original_data = dict(entry.data)
    original_options = dict(entry.options)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CORE_INPUT)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_GRID

    hass.config_entries.flow.async_abort(result["flow_id"])
    assert dict(entry.data) == original_data
    assert dict(entry.options) == original_options


async def test_adr0027_accumulator_starts_empty_on_a_second_run(hass):
    """ADR-0027 point 2: per-run state. An abandoned run's answers must not leak into the
    next flow started on the same handler class."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    # deadline also declared present, so submitting solar advances to another FORM (deadline)
    # rather than completing the flow outright -- leaving something to abort mid-flow.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**CORE_INPUT, CONF_SOLAR_AVAILABLE: True, CONF_DEADLINE_AVAILABLE: True}
    )
    step_inputs = {
        **_INSTALL_STEP_BASES,
        STEP_VEHICLE: {**VEHICLE_INPUT, CONF_CAR_HOME_ENTITY: "person.driver"},
    }
    for step_id in (STEP_GRID, STEP_EV_CHARGER, STEP_VEHICLE, STEP_POWER):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], step_inputs[step_id]
        )
    assert result["step_id"] == STEP_SOLAR
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**SOLAR_INPUT, CONF_SOLAR_START_THRESHOLD_W: 999.0}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_DEADLINE
    hass.config_entries.flow.async_abort(result["flow_id"])

    entry = await _create_entry(hass)
    assert CONF_SOLAR_FORECAST_ENTITY not in entry.data
    assert CONF_SOLAR_START_THRESHOLD_W not in entry.options


# --- The options flow: T7's own nine-topic-step OPTIONS_TABLE (UC12 1b, ADR-0027 point 4). ---


async def test_uc12_1b_options_walks_all_five_ungated_steps_plus_declared_gated_ones(hass):
    """UC12 1b / R20 AC2: every capability declared present -> the options flow walks all
    nine steps, in UC12's fixed order (captar before solar) -- the same order CONFIG_TABLE
    uses, prefixed by the shared `core` entry point."""
    entry = await _create_entry(
        hass,
        capabilities=_ALL_CAPABILITIES_TRUE,
        per_step_input={STEP_VEHICLE: {**VEHICLE_INPUT, CONF_CAR_HOME_ENTITY: "person.driver"}},
    )
    result = await hass.config_entries.options.async_init(entry.entry_id)
    visited = [result["step_id"]]
    while result["type"] == FlowResultType.FORM:
        step_id = result["step_id"]
        if visited.count(step_id) > 1:
            pytest.fail(f"step {step_id!r} re-shown twice; visited so far: {visited}")
        result = await hass.config_entries.options.async_configure(result["flow_id"], {})
        if result["type"] == FlowResultType.FORM:
            visited.append(result["step_id"])

    assert visited == [STEP_CORE, *UC12_FIXED_STEP_ORDER]
    assert result["type"] == FlowResultType.CREATE_ENTRY


async def test_uc12_1b_control_interval_is_presented_on_the_options_core_step_only(hass):
    """UC12 1b: install defaults it, reconfigure touches no options -- the options flow is
    the only path that presents it. Assert its absence on both other flows too. The install
    check must run BEFORE any entry exists (single-instance-allowed aborts a second one)."""
    install_result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert install_result["step_id"] == STEP_CORE
    assert CONF_CONTROL_INTERVAL_S not in _keys(install_result["data_schema"])
    hass.config_entries.flow.async_abort(install_result["flow_id"])

    entry = await _create_entry(hass)

    options_result = await hass.config_entries.options.async_init(entry.entry_id)
    assert options_result["step_id"] == STEP_CORE
    assert CONF_CONTROL_INTERVAL_S in _keys(options_result["data_schema"])

    reconfigure_result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    assert reconfigure_result["step_id"] == STEP_CORE
    assert CONF_CONTROL_INTERVAL_S not in _keys(reconfigure_result["data_schema"])
    hass.config_entries.flow.async_abort(reconfigure_result["flow_id"])


async def test_uc12_1b_options_never_presents_a_mapping_or_a_capability_declaration(hass):
    """R20 AC7 / ADR-0027 point 4: the options flow's own table is threshold halves only --
    no step it can show ever renders a mapping field or a capability declaration."""
    mapping_fields = {k for frag in _ALL_MAPPING_FRAGMENTS for k in _keys(frag)}
    capability_fields = {
        CONF_SOLAR_AVAILABLE,
        CONF_CAPTAR_AVAILABLE,
        CONF_DEADLINE_AVAILABLE,
        CONF_NOTIFICATIONS_AVAILABLE,
    }

    entry = await _create_entry(
        hass,
        capabilities=_ALL_CAPABILITIES_TRUE,
        per_step_input={STEP_VEHICLE: {**VEHICLE_INPUT, CONF_CAR_HOME_ENTITY: "person.driver"}},
    )
    result = await hass.config_entries.options.async_init(entry.entry_id)
    while result["type"] == FlowResultType.FORM:
        rendered = _keys(result["data_schema"])
        assert not (rendered & mapping_fields), f"{result['step_id']} renders a mapping field"
        assert not (rendered & capability_fields), (
            f"{result['step_id']} renders a capability declaration"
        )
        result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    assert result["type"] == FlowResultType.CREATE_ENTRY


_ALL_SIXTEEN = list(itertools.product([False, True], repeat=4))


@pytest.mark.parametrize("solar,captar,deadline,notifications", _ALL_SIXTEEN)
async def test_r20_ac2_options_traverses_exactly_the_stored_capabilities_steps(
    hass, solar, captar, deadline, notifications
):
    """R20 AC2: the options flow walks the five ungated steps plus exactly the gated steps
    whose capability is STORED present, in UC12's fixed order (captar before solar) --
    all sixteen combinations of the four capability flags."""
    per_step_input = {}
    if deadline:
        # D-3's vehicle-step guard: a present deadline capability requires car_home_entity
        # on install, independent of this test's own concern.
        per_step_input[STEP_VEHICLE] = {**VEHICLE_INPUT, CONF_CAR_HOME_ENTITY: "person.driver"}
    entry = await _create_entry(
        hass,
        capabilities={
            CONF_SOLAR_AVAILABLE: solar,
            CONF_CAPTAR_AVAILABLE: captar,
            CONF_DEADLINE_AVAILABLE: deadline,
            CONF_NOTIFICATIONS_AVAILABLE: notifications,
        },
        per_step_input=per_step_input or None,
    )
    expected = [STEP_CORE, STEP_GRID, STEP_EV_CHARGER, STEP_VEHICLE, STEP_POWER]
    if captar:
        expected.append(STEP_CAPTAR)
    if solar:
        expected.append(STEP_SOLAR)
    if deadline:
        expected.append(STEP_DEADLINE)
    if notifications:
        expected.append(STEP_NOTIFICATIONS)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    visited = [result["step_id"]]
    while result["type"] == FlowResultType.FORM:
        result = await hass.config_entries.options.async_configure(result["flow_id"], {})
        if result["type"] == FlowResultType.FORM:
            visited.append(result["step_id"])

    assert visited == expected
    assert result["type"] == FlowResultType.CREATE_ENTRY


async def test_uc12_1b_options_gate_on_an_entry_predating_notifications_available(hass):
    """Design 'Step ids': a MockConfigEntry whose data has no notifications_available key
    (nor solar/captar/deadline_available -- every options gate's own absent-key fallback,
    D-1) opens Configure without KeyError and skips step 9."""
    data = entry_data_base()
    assert CONF_SOLAR_AVAILABLE not in data
    assert CONF_CAPTAR_AVAILABLE not in data
    assert CONF_DEADLINE_AVAILABLE not in data
    assert CONF_NOTIFICATIONS_AVAILABLE not in data
    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    for step_id in (STEP_CORE, STEP_GRID, STEP_EV_CHARGER, STEP_VEHICLE, STEP_POWER):
        assert result["step_id"] == step_id
        result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    # captar_available absent -> DEFAULT_CAPTAR_AVAILABLE True -> shown.
    assert result["step_id"] == STEP_CAPTAR
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    # solar_available absent -> DEFAULT_SOLAR_AVAILABLE False -> skipped;
    # deadline_available absent -> DEFAULT_DEADLINE_AVAILABLE True -> shown.
    assert result["step_id"] == STEP_DEADLINE
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    # notifications_available absent -> DEFAULT_NOTIFICATIONS_AVAILABLE False -> skipped,
    # so this finishes without KeyError.
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()


async def test_options_flow_round_trip_updates_options_not_data(hass):
    """Changing a threshold via the options flow updates entry.options, leaving entry.data alone."""
    entry = await _create_entry(hass)
    original_data = dict(entry.data)

    result = await _run_options_flow(
        hass,
        entry,
        per_step={
            STEP_CORE: {CONF_CONTROL_INTERVAL_S: 15},
            STEP_GRID: {CONF_GRID_SAFETY_OFFSET_A: 3.5},
        },
    )
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_GRID_SAFETY_OFFSET_A] == 3.5
    assert entry.options[CONF_CONTROL_INTERVAL_S] == 15
    assert dict(entry.data) == original_data


async def test_options_flow_rejects_a_data_key(hass):
    """The options flow's schema is thresholds/interval only -- a data key (entity-role
    mapping) submitted to it is rejected, not silently accepted (ADR-0005: only the
    reconfigure flow may change entity-role mappings)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_CHARGER_CURRENT_ENTITY: "number.charger_current", CONF_STATUS_TRANSLATION: {}},
        options={
            CONF_SMOOTHING_WINDOW: DEFAULT_SMOOTHING_WINDOW,
            CONF_CONTROL_INTERVAL_S: DEFAULT_CONTROL_INTERVAL_S,
        },
    )
    entry.add_to_hass(hass)

    options_result = await hass.config_entries.options.async_init(entry.entry_id)
    assert options_result["step_id"] == STEP_CORE
    tampered_options = dict(entry.options)
    tampered_options[CONF_CHARGER_CURRENT_ENTITY] = "number.some_other_charger"

    with pytest.raises(vol.Invalid):
        await hass.config_entries.options.async_configure(
            options_result["flow_id"], tampered_options
        )
    assert entry.data[CONF_CHARGER_CURRENT_ENTITY] == "number.charger_current"


async def test_options_flow_edits_solar_thresholds(hass):
    entry = await _create_entry(hass, capabilities={CONF_SOLAR_AVAILABLE: True})
    result = await _run_options_flow(
        hass, entry, per_step={STEP_SOLAR: {CONF_SOLAR_START_THRESHOLD_W: 200.0}}
    )
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_SOLAR_START_THRESHOLD_W] == 200.0


async def test_options_flow_edits_peak_protection_thresholds(hass):
    entry = await _create_entry(hass, capabilities={CONF_CAPTAR_AVAILABLE: True})
    result = await _run_options_flow(hass, entry, per_step={STEP_CAPTAR: {CONF_MAX_PEAK_KW: 5.0}})
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_MAX_PEAK_KW] == 5.0


async def test_r20_ac3_captar_absent_options_save_does_not_reintroduce_peak_protection_keys(hass):
    """Issue #830's second note: while the options flow still walked the pre-T7 always-shown
    `thresholds` step, a CapTar-absent install's peak-protection keys got re-introduced at
    module defaults the first time Configure was opened and saved. Now that `captar` is a
    gated OPTIONS_TABLE row, a CapTar-absent Configure+Save must not write any of them."""
    entry = await _create_entry(hass)  # captar_available False (CORE_INPUT default)
    for key in (
        CONF_CAPTAR_COOLDOWN_MIN,
        CONF_POWER_RESPECT_PEAK,
        CONF_SAFETY_MARGIN_W,
        CONF_MAX_PEAK_KW,
        CONF_PEAK_FLOOR_KW,
        CONF_PEAK_GRACE_MIN,
    ):
        assert key not in entry.options

    result = await _run_options_flow(hass, entry)
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY

    for key in (
        CONF_CAPTAR_COOLDOWN_MIN,
        CONF_POWER_RESPECT_PEAK,
        CONF_SAFETY_MARGIN_W,
        CONF_MAX_PEAK_KW,
        CONF_PEAK_FLOOR_KW,
        CONF_PEAK_GRACE_MIN,
    ):
        assert key not in entry.options


async def test_r20_ac7_options_merges_into_stored_options_never_replaces_them(hass):
    """A capability withdrawn through reconfigure leaves its thresholds in options; the next
    Configure+Save must not delete them."""
    entry = await _create_entry(hass, capabilities={CONF_SOLAR_AVAILABLE: True})
    await _run_options_flow(
        hass, entry, per_step={STEP_SOLAR: {CONF_SOLAR_START_THRESHOLD_W: 321.0}}
    )
    await hass.async_block_till_done()
    assert entry.options[CONF_SOLAR_START_THRESHOLD_W] == 321.0

    result = await _run_reconfigure_flow(hass, entry, capabilities={CONF_SOLAR_AVAILABLE: False})
    assert result["type"] == FlowResultType.ABORT
    await hass.async_block_till_done()
    assert entry.data[CONF_SOLAR_AVAILABLE] is False
    assert entry.options[CONF_SOLAR_START_THRESHOLD_W] == 321.0  # UC12 1a: data bucket only

    result = await _run_options_flow(hass, entry)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options[CONF_SOLAR_START_THRESHOLD_W] == 321.0


async def test_r18_ac11_options_can_toggle_one_notification_off_without_touching_the_others(hass):
    entry = await _create_entry(hass, capabilities={CONF_NOTIFICATIONS_AVAILABLE: True})
    assert entry.options[CONF_DEADLINE_NOTICE_ENABLED] is True
    assert entry.options[CONF_PLUG_IN_REMINDER_ENABLED] is True
    assert entry.options[CONF_EVENING_PROMPT_ENABLED] is True

    result = await _run_options_flow(
        hass, entry, per_step={STEP_NOTIFICATIONS: {CONF_DEADLINE_NOTICE_ENABLED: False}}
    )
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_DEADLINE_NOTICE_ENABLED] is False
    assert entry.options[CONF_PLUG_IN_REMINDER_ENABLED] is True
    assert entry.options[CONF_EVENING_PROMPT_ENABLED] is True


async def test_adr0008_options_change_reloads_the_entry(hass):
    seed_charger_states(hass, status="Charging")
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data_base(), options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    original_coordinator = entry.runtime_data.coordinator

    # captar_available absent -> DEFAULT_CAPTAR_AVAILABLE True -> STEP_CAPTAR is reachable.
    result = await _run_options_flow(hass, entry, per_step={STEP_CAPTAR: {CONF_MAX_PEAK_KW: 7.0}})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert entry.options[CONF_MAX_PEAK_KW] == 7.0
    new_coordinator = entry.runtime_data.coordinator
    assert new_coordinator is not original_coordinator


async def test_r20_ac8_abandoning_options_leaves_the_options_bucket_exactly_as_it_was(hass):
    """R20 AC8: closing the options flow mid-walk leaves the options bucket byte-for-byte as
    it was before the flow started. Exercises the nine-topic-step OPTIONS_TABLE T7 cut over
    to; the walk now runs core/grid/ev_charger/vehicle/power/solar/deadline in that order."""
    entry = await _create_entry(
        hass,
        capabilities={CONF_SOLAR_AVAILABLE: True, CONF_DEADLINE_AVAILABLE: True},
        # D-3's vehicle-step guard: a present deadline capability requires car_home_entity.
        per_step_input={STEP_VEHICLE: {**VEHICLE_INPUT, CONF_CAR_HOME_ENTITY: "person.driver"}},
    )
    original_options = dict(entry.options)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    for step_id in (STEP_CORE, STEP_GRID, STEP_EV_CHARGER, STEP_VEHICLE, STEP_POWER):
        assert result["step_id"] == step_id
        result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    assert result["step_id"] == STEP_SOLAR
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SOLAR_START_THRESHOLD_W: 999.0}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_DEADLINE

    hass.config_entries.options.async_abort(result["flow_id"])
    assert dict(entry.options) == original_options


# --- Pre-toggle-entry defaults (setup path, not the flow itself). ---


async def test_pre_toggle_entry_defaults_solar_available_false(hass):
    seed_charger_states(hass, status="Charging")
    data = entry_data_base()
    assert CONF_SOLAR_AVAILABLE not in data

    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = entry.runtime_data.coordinator
    assert coordinator._config.solar_available is False


async def test_pre_toggle_entry_defaults_captar_available_true(hass):
    seed_charger_states(hass, status="Charging")
    data = entry_data_base()
    assert CONF_CAPTAR_AVAILABLE not in data

    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = entry.runtime_data.coordinator
    assert coordinator._config.captar_available is True


# --- Fragment/table structural tests (unit-level, no hass fixture needed). ---


def test_flat_flow_schema_surface_is_deleted():
    assert not hasattr(config_flow_module, "MAPPING_SCHEMA")
    assert not hasattr(config_flow_module, "_threshold_schema")
    assert not hasattr(config_flow_module, "USER_SCHEMA")
    assert not hasattr(config_flow_module, "UNGATED_MAPPING_SCHEMA")
    assert not hasattr(config_flow_module, "VEHICLE_LIMIT_MAPPING_SCHEMA")
    assert not hasattr(config_flow_module, "_solar_mapping_schema")
    assert not hasattr(config_flow_module, "_captar_mapping_schema")
    assert not hasattr(config_flow_module, "_ev_soc_missing_error")
    assert not hasattr(config_flow_module, "_solar_forecast_missing_error")
    assert not hasattr(config_flow_module, "async_step_vehicle_limit")
    # T7's own deletions: the always-shown catch-all threshold fragment, the interim-named
    # table it was cut over from, and the step id only it (and the retired options step
    # `async_step_thresholds`) ever used.
    assert not hasattr(config_flow_module, "_ungated_threshold_schema")
    assert not hasattr(config_flow_module, "NINE_STEP_OPTIONS_TABLE")
    assert not hasattr(const, "STEP_THRESHOLDS")


def test_config_flow_class_has_no_retired_step_methods():
    for name in ("async_step_mappings", "async_step_vehicle_limit"):
        assert not hasattr(SmartChargingConfigFlow, name)


def test_uc12_step2_ev_charger_and_vehicle_fragments_have_exactly_uc12s_fields():
    assert _keys(EV_CHARGER_MAPPING_SCHEMA) == {
        CONF_CHARGER_CURRENT_ENTITY,
        CONF_CHARGER_STATUS_ENTITY,
        CONF_CONNECTED_STATES,
        CONF_CHARGING_STATES,
        CONF_CHARGER_POWER_ENTITY,
    }
    assert _keys(_ev_charger_threshold_schema()) == {CONF_MIN_CURRENT, CONF_MAX_CURRENT}
    assert _keys(VEHICLE_MAPPING_SCHEMA) == {
        CONF_EV_SOC_ENTITY,
        CONF_EV_BATTERY_CAPACITY_ENTITY,
        CONF_VEHICLE_CHARGE_LIMIT_ENTITY,
        CONF_CAR_HOME_ENTITY,
    }
    assert _keys(_vehicle_threshold_schema()) == {
        CONF_EV_BATTERY_CAPACITY_KWH,
        CONF_DEFAULT_SOC_LIMIT,
    }


def test_uc12_step5_power_threshold_fragment_has_exactly_uc12s_fields():
    assert _keys(_power_threshold_schema()) == {
        CONF_DEFAULT_TARGET_CURRENT,
        CONF_POWER_COOLDOWN_MIN,
    }


def test_uc12_5b_captar_threshold_fragment_carries_the_peak_protection_fields():
    assert _keys(_captar_threshold_schema()) == {
        CONF_CAPTAR_COOLDOWN_MIN,
        CONF_POWER_RESPECT_PEAK,
        CONF_SAFETY_MARGIN_W,
        CONF_MAX_PEAK_KW,
        CONF_PEAK_FLOOR_KW,
        CONF_PEAK_GRACE_MIN,
    }


def test_uc12_step7_solar_fragments_have_exactly_uc12s_fields():
    assert _keys(SOLAR_MAPPING_SCHEMA) == {CONF_SOLAR_POWER_ENTITY, CONF_SOLAR_FORECAST_ENTITY}
    assert _keys(_solar_threshold_schema()) == {
        CONF_SOLAR_START_THRESHOLD_W,
        CONF_SOLAR_ONLY_START_THRESHOLD_W,
        CONF_SOLAR_ONLY_STRATEGY,
        CONF_SOLAR_ONLY_MIDPOINT,
        CONF_SOLAR_HOLD_MIN,
        CONF_SOLAR_ONLY_HOLD_MIN,
        CONF_SOLAR_RESTART_DEBOUNCE_MIN,
        CONF_SOLAR_COOLDOWN_MIN,
        CONF_SOLAR_STEP_PP,
        CONF_SOLAR_STEP_THRESHOLD_PP,
        CONF_MAX_SOLAR_SOC,
        CONF_SOLAR_RESERVE_SOC,
        CONF_SOLAR_FORECAST_THRESHOLD_KWH,
    }


def test_uc12_5c_deadline_mapping_carries_the_home_day_external_carve_out():
    assert _keys(DEADLINE_MAPPING_SCHEMA) == {
        CONF_DEPARTURE_EXTERNAL_ENTITY,
        CONF_HOME_DAY_EXTERNAL_ENTITY,
    }


def test_uc12_step9_notifications_fragments_have_exactly_uc12s_fields():
    assert _keys(NOTIFICATIONS_MAPPING_SCHEMA) == {CONF_NOTIFICATION_TARGET_ENTITY}
    assert _keys(_notifications_threshold_schema()) == {
        CONF_DEADLINE_NOTICE_ENABLED,
        CONF_PLUG_IN_REMINDER_ENABLED,
        CONF_EVENING_PROMPT_ENABLED,
        CONF_EVENING_PROMPT_TIME,
    }


_ALL_MAPPING_FRAGMENTS = (
    CORE_MAPPING_SCHEMA,
    GRID_MAPPING_SCHEMA,
    EV_CHARGER_MAPPING_SCHEMA,
    VEHICLE_MAPPING_SCHEMA,
    SOLAR_MAPPING_SCHEMA,
    DEADLINE_MAPPING_SCHEMA,
    NOTIFICATIONS_MAPPING_SCHEMA,
)
_ALL_THRESHOLD_FRAGMENTS = (
    _core_threshold_schema(),
    _grid_threshold_schema(),
    _ev_charger_threshold_schema(),
    _vehicle_threshold_schema(),
    _power_threshold_schema(),
    _captar_threshold_schema(),
    _solar_threshold_schema(),
    _deadline_threshold_schema(),
    _notifications_threshold_schema(),
)


def test_r20_ac4_no_field_belongs_to_two_fragments():
    """R20 AC4: ev_soc_entity moved to the ungated `vehicle` step, so fragments are now
    strictly disjoint, with no exemption list."""
    seen: set[str] = set()
    for fragment in (*_ALL_MAPPING_FRAGMENTS, *_ALL_THRESHOLD_FRAGMENTS):
        overlap = _keys(fragment) & seen
        assert not overlap, f"field(s) {overlap} appear in more than one fragment"
        seen |= _keys(fragment)


def test_option_keys_has_no_duplicate_member():
    assert len(OPTION_KEYS) == len(set(OPTION_KEYS))


def test_adr0005_every_option_key_appears_in_exactly_one_threshold_fragment():
    all_keys: list[str] = []
    for fragment in _ALL_THRESHOLD_FRAGMENTS:
        all_keys.extend(_keys(fragment))
    assert sorted(all_keys) == sorted(set(OPTION_KEYS))


def test_adr0005_no_option_key_appears_in_a_mapping_fragment():
    mapping_keys: set[str] = set()
    for fragment in _ALL_MAPPING_FRAGMENTS:
        mapping_keys |= _keys(fragment)
    assert not (mapping_keys & set(OPTION_KEYS))


def test_uc12_1b_control_interval_is_only_in_the_core_threshold_fragment_when_requested():
    assert CONF_CONTROL_INTERVAL_S not in _keys(_core_threshold_schema())
    assert CONF_CONTROL_INTERVAL_S in _keys(_core_threshold_schema(include_interval=True))
    for fragment in (*_ALL_MAPPING_FRAGMENTS, *_ALL_THRESHOLD_FRAGMENTS):
        assert CONF_CONTROL_INTERVAL_S not in _keys(fragment)


def test_d1_new_config_keys_match_the_entity_catalog():
    assert CONF_NOTIFICATIONS_AVAILABLE == "notifications_available"
    assert DEFAULT_NOTIFICATIONS_AVAILABLE is False
    assert CONF_POWER_COOLDOWN_MIN == "power_cooldown_min"
    assert DEFAULT_POWER_COOLDOWN_MIN == 10.0
    assert CONF_DEADLINE_NOTICE_ENABLED == "deadline_notice_enabled"
    assert DEFAULT_DEADLINE_NOTICE_ENABLED is True
    assert CONF_PLUG_IN_REMINDER_ENABLED == "plug_in_reminder_enabled"
    assert DEFAULT_PLUG_IN_REMINDER_ENABLED is True
    assert CONF_SOLAR_POWER_ENTITY == "solar_power_entity"
    assert ERROR_REQUIRED_WHEN_DEADLINE_AVAILABLE == "required_when_deadline_available"


def test_adr0027_step_ids_are_uc12s_nine():
    assert STEP_GRID == "grid"
    assert STEP_EV_CHARGER == "ev_charger"
    assert STEP_VEHICLE == "vehicle"
    assert STEP_POWER == "power"
    assert STEP_NOTIFICATIONS == "notifications"


# --- CONFIG_TABLE / OPTIONS_TABLE reachability + order (ADR-0027 Option C). ---

_CONFIG_FLOW_FRAMEWORK_STEPS = {
    "async_step_user",
    "async_step_reconfigure",
    "async_step_core",
}
# Unlike CONFIG_TABLE, `core` IS an OPTIONS_TABLE row (design "Options table": the options
# flow's own entry point, async_step_init, renders no form of its own) -- so, unlike
# `_CONFIG_FLOW_FRAMEWORK_STEPS`, `async_step_core` does NOT need excluding here: it is a
# genuine table member and the converse test below passes it on that basis.
_OPTIONS_FLOW_FRAMEWORK_STEPS = {
    "async_step_init",
}


def _non_framework_step_methods(cls, framework: set[str]) -> set[str]:
    """Step methods `cls` itself defines -- not `dir(cls)`, which would also pick up
    discovery-flow hooks (e.g. `async_step_usb`) inherited from HA's own ConfigFlow base."""
    return {name for name in vars(cls) if name.startswith("async_step_") and name not in framework}


def test_adr0027_every_config_table_step_has_a_step_method():
    """Named discharge of Option C's stated Con: a row with no method is silently unreachable."""
    for row in CONFIG_TABLE:
        assert f"async_step_{row.step_id}" in vars(SmartChargingConfigFlow)


def test_every_config_step_method_is_in_the_table():
    """The converse: a step method absent from the table is unreachable and nothing raises."""
    table_step_ids = {row.step_id for row in CONFIG_TABLE}
    for name in _non_framework_step_methods(SmartChargingConfigFlow, _CONFIG_FLOW_FRAMEWORK_STEPS):
        assert name.removeprefix("async_step_") in table_step_ids


def test_adr0027_every_options_table_step_has_a_step_method():
    for row in OPTIONS_TABLE:
        assert f"async_step_{row.step_id}" in vars(SmartChargingOptionsFlow)


def test_every_options_step_method_is_in_the_table():
    """The converse: a step method absent from the table is unreachable and nothing raises."""
    table_step_ids = {row.step_id for row in OPTIONS_TABLE}
    for name in _non_framework_step_methods(
        SmartChargingOptionsFlow, _OPTIONS_FLOW_FRAMEWORK_STEPS
    ):
        assert name.removeprefix("async_step_") in table_step_ids


def test_uc12_config_table_is_uc12s_fixed_order_minus_the_core_entry_point():
    """UC12 step table / ADR-0027 point 5: the nine-step model's eight table rows, captar
    BEFORE solar; `core` is the shared entry point and deliberately not a row."""
    assert [row.step_id for row in CONFIG_TABLE] == [
        STEP_GRID,
        STEP_EV_CHARGER,
        STEP_VEHICLE,
        STEP_POWER,
        STEP_CAPTAR,
        STEP_SOLAR,
        STEP_DEADLINE,
        STEP_NOTIFICATIONS,
    ]
    assert list(UC12_FIXED_STEP_ORDER) == [row.step_id for row in CONFIG_TABLE]


def test_uc12_1b_options_table_is_uc12s_fixed_order_plus_the_core_row():
    """T7's own cut-over (design "Options table"): the options flow's own nine-topic-step
    table -- `core` prefixed onto UC12's fixed eight-row order, unlike CONFIG_TABLE where
    `core` is the shared entry point rather than a row of its own."""
    assert [row.step_id for row in OPTIONS_TABLE] == [STEP_CORE, *UC12_FIXED_STEP_ORDER]


async def test_dispatcher_advances_past_a_failing_gate_and_finishes_when_exhausted():
    """Dispatcher unit test over a synthetic two-row table (ADR-0027 Option C, unchanged in
    mechanism): a failing gate is skipped, the next passing row is shown, and exhausting the
    table calls _async_finish exactly once."""
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

    result = await flow._async_advance(after="show_me")
    assert result == "finished"
    assert calls == ["show_me", "finish"]

    calls.clear()
    result = await flow._async_advance(after="not_a_table_member")
    assert result == "shown"
    assert calls == ["show_me"]


async def test_r20_ac9_a_tenth_gated_row_appended_changes_no_existing_step(hass, monkeypatch):
    """R20 AC9 / ADR-0027 Decision ("a new capability is one table row plus one step method,
    appended after the existing gated rows, with no existing step touched" -- the decisive
    point over Option B): monkeypatch a synthetic tenth row (gated on a fake flag) onto the
    END of CONFIG_TABLE with its own step method. The capability set is closed this release
    (R18 AC13), so this criterion is only reachable by construction. Asserts (a) the new step
    is reached when its flag is set, (b) skipped when it is not, and (c) the nine existing
    steps' order and field sets are byte-identical either way."""
    STEP_SYNTHETIC = "synthetic_tenth"
    gate_flag = {"enabled": False}

    async def async_step_synthetic_tenth(self, user_input=None):
        if user_input is None:
            return self.async_show_form(step_id=STEP_SYNTHETIC, data_schema=vol.Schema({}))
        return await self._async_advance(after=STEP_SYNTHETIC)

    synthetic_row = FlowStep(step_id=STEP_SYNTHETIC, gate=lambda flow: gate_flag["enabled"])
    monkeypatch.setattr(SmartChargingConfigFlow, "_table", (*CONFIG_TABLE, synthetic_row))
    monkeypatch.setattr(
        SmartChargingConfigFlow,
        f"async_step_{STEP_SYNTHETIC}",
        async_step_synthetic_tenth,
        raising=False,
    )

    async def _walk():
        """Drive the install flow, recording every visited step's field set alongside the
        visited order."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        visited = [result["step_id"]]
        field_sets = {result["step_id"]: _keys(result["data_schema"])}
        step_inputs = {
            **_INSTALL_STEP_BASES,
            STEP_CORE: {**CORE_INPUT, **_ALL_CAPABILITIES_TRUE},
            STEP_VEHICLE: {**VEHICLE_INPUT, CONF_CAR_HOME_ENTITY: "person.driver"},
            STEP_SYNTHETIC: {},
        }
        while result["type"] == FlowResultType.FORM:
            step_id = result["step_id"]
            if visited.count(step_id) > 1:
                pytest.fail(f"step {step_id!r} re-shown twice; visited so far: {visited}")
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], step_inputs[step_id]
            )
            if result["type"] == FlowResultType.FORM:
                visited.append(result["step_id"])
                field_sets[result["step_id"]] = _keys(result["data_schema"])
        assert result["type"] == FlowResultType.CREATE_ENTRY
        # single-instance-allowed: remove this run's entry so the next _walk() can install
        # again rather than aborting.
        await hass.config_entries.async_remove(result["result"].entry_id)
        await hass.async_block_till_done()
        return visited, field_sets

    gate_flag["enabled"] = False
    gated_off_visited, gated_off_fields = await _walk()
    assert STEP_SYNTHETIC not in gated_off_visited
    assert gated_off_visited == [STEP_CORE, *UC12_FIXED_STEP_ORDER]

    gate_flag["enabled"] = True
    gated_on_visited, gated_on_fields = await _walk()
    assert gated_on_visited == [STEP_CORE, *UC12_FIXED_STEP_ORDER, STEP_SYNTHETIC]

    # (c): the nine existing steps' order and field sets are byte-identical either way.
    assert gated_off_visited == gated_on_visited[: len(gated_off_visited)]
    for step_id in [STEP_CORE, *UC12_FIXED_STEP_ORDER]:
        assert gated_off_fields[step_id] == gated_on_fields[step_id], step_id


class _StubConfigFlow:
    """A bare stand-in exposing exactly what CONFIG_TABLE's gates read (`_answers`, `_mode`)
    -- no `hass` fixture needed to exercise gate callables directly."""

    def __init__(self, *, answers: dict, mode: FlowMode) -> None:
        self._answers = answers
        self._mode = mode


def test_adr0027_point3_power_and_captar_rows_are_gated_off_in_reconfigure():
    """UC12 1a: neither has a mapping half, so both must be absent from the reconfigure walk
    -- expressed as each row's own conjoined gate, not as a stop condition."""
    power_gate = next(row for row in CONFIG_TABLE if row.step_id == STEP_POWER).gate
    captar_gate = next(row for row in CONFIG_TABLE if row.step_id == STEP_CAPTAR).gate

    reconfigure_flow = _StubConfigFlow(
        answers={CONF_CAPTAR_AVAILABLE: True}, mode=FlowMode.RECONFIGURE
    )
    assert power_gate(reconfigure_flow) is False
    assert captar_gate(reconfigure_flow) is False

    install_flow = _StubConfigFlow(answers={CONF_CAPTAR_AVAILABLE: True}, mode=FlowMode.INSTALL)
    assert power_gate(install_flow) is True
    assert captar_gate(install_flow) is True


def test_uc12_config_table_solar_deadline_notifications_gates_read_this_runs_own_answers():
    """Each of the three plain capability gates (`solar`, `deadline`, `notifications`) reads
    its OWN CONF_*_AVAILABLE answer, not any of the other two."""
    gates = {row.step_id: row.gate for row in CONFIG_TABLE}
    install = FlowMode.INSTALL

    only_solar = _StubConfigFlow(answers={CONF_SOLAR_AVAILABLE: True}, mode=install)
    assert gates[STEP_SOLAR](only_solar) is True
    assert gates[STEP_DEADLINE](only_solar) is False
    assert gates[STEP_NOTIFICATIONS](only_solar) is False

    only_deadline = _StubConfigFlow(answers={CONF_DEADLINE_AVAILABLE: True}, mode=install)
    assert gates[STEP_SOLAR](only_deadline) is False
    assert gates[STEP_DEADLINE](only_deadline) is True
    assert gates[STEP_NOTIFICATIONS](only_deadline) is False

    only_notifications = _StubConfigFlow(answers={CONF_NOTIFICATIONS_AVAILABLE: True}, mode=install)
    assert gates[STEP_SOLAR](only_notifications) is False
    assert gates[STEP_DEADLINE](only_notifications) is False
    assert gates[STEP_NOTIFICATIONS](only_notifications) is True


class _StubOptionsFlow:
    """Bare stand-in for the gate callables in OPTIONS_TABLE, which read
    `flow.config_entry.data` rather than `_answers`/`_mode`."""

    def __init__(self, *, entry_data: dict) -> None:
        self.config_entry = MockConfigEntry(domain=DOMAIN, data=entry_data, options={})


def test_uc12_1b_options_gates_read_stored_flags_defensively():
    """ADR-0027 point 4: every options gate is .get(key, DEFAULT_*), so an entry predating
    notifications_available -- the key this slice actually introduces (D-1); the other three
    capability keys already existed before this slice -- opens Configure without KeyError."""
    gates = {row.step_id: row.gate for row in OPTIONS_TABLE}

    stub = _StubOptionsFlow(entry_data={})  # predates every capability key
    # Defaults, absent-key read fallback: captar True, solar False, deadline True,
    # notifications False.
    assert gates[STEP_CAPTAR](stub) is True
    assert gates[STEP_SOLAR](stub) is False
    assert gates[STEP_DEADLINE](stub) is True
    assert gates[STEP_NOTIFICATIONS](stub) is False

    inverted = _StubOptionsFlow(
        entry_data={
            CONF_CAPTAR_AVAILABLE: False,
            CONF_SOLAR_AVAILABLE: True,
            CONF_DEADLINE_AVAILABLE: False,
            CONF_NOTIFICATIONS_AVAILABLE: True,
        }
    )
    assert gates[STEP_CAPTAR](inverted) is False
    assert gates[STEP_SOLAR](inverted) is True
    assert gates[STEP_DEADLINE](inverted) is False
    assert gates[STEP_NOTIFICATIONS](inverted) is True
