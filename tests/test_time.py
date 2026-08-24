"""HA-harness tests for the departure-time entities (C2, R14)."""

import logging
from datetime import time

import pytest
from homeassistant.components.time import SERVICE_SET_VALUE
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, Platform
from homeassistant.core import State
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockEntityPlatform,
    mock_restore_cache,
)

from custom_components.smart_charging.const import (
    CONF_DEADLINE_AVAILABLE,
    DAY_FRI,
    DAY_MON,
    DAY_SAT,
    DAY_SUN,
    DAY_THU,
    DAY_TUE,
    DAY_WED,
    DEPARTURE_OVERRIDE_HOLIDAY,
    DEPARTURE_OVERRIDE_HOME_DAY,
    DOMAIN,
    LABEL_SC_RUNTIME,
)
from custom_components.smart_charging.time import (
    DAY_OF_WEEK_DEFAULTS,
    OVERRIDE_DEFAULTS,
    WEEKDAY_DEFAULT,
    SmartChargingDepartureTime,
    async_setup_entry,
)
from tests.helpers import entry_data_base, entry_options_base, seed_charger_states

_WEEKDAY_SUFFIXES = (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI)
_WEEKEND_SUFFIXES = (DAY_SAT, DAY_SUN)
# Derived from the same tables async_setup_entry itself builds from, so this can't drift from
# the real 9-entity population the way a hand-copied tuple could.
_ALL_DEPARTURE_SUFFIXES = tuple(suffix for suffix, _ in (*DAY_OF_WEEK_DEFAULTS, *OVERRIDE_DEFAULTS))


@pytest.mark.parametrize("suffix", _WEEKDAY_SUFFIXES)
def test_weekday_default_is_six_am(suffix):
    entity = SmartChargingDepartureTime(entry_id="abc", id_suffix=suffix, default=WEEKDAY_DEFAULT)
    assert entity.native_value == time(6, 0)


@pytest.mark.parametrize("suffix", _WEEKEND_SUFFIXES)
def test_weekend_default_is_none(suffix):
    entity = SmartChargingDepartureTime(entry_id="abc", id_suffix=suffix, default=None)
    assert entity.native_value is None


def test_day_of_week_defaults_table_has_seven_entries_with_weekday_weekend_split():
    assert [suffix for suffix, _ in DAY_OF_WEEK_DEFAULTS] == [
        DAY_MON,
        DAY_TUE,
        DAY_WED,
        DAY_THU,
        DAY_FRI,
        DAY_SAT,
        DAY_SUN,
    ]
    assert [default for _, default in DAY_OF_WEEK_DEFAULTS] == [
        WEEKDAY_DEFAULT,
        WEEKDAY_DEFAULT,
        WEEKDAY_DEFAULT,
        WEEKDAY_DEFAULT,
        WEEKDAY_DEFAULT,
        None,
        None,
    ]


def test_holiday_and_home_day_overrides_default_to_none():
    assert OVERRIDE_DEFAULTS == [
        (DEPARTURE_OVERRIDE_HOLIDAY, None),
        (DEPARTURE_OVERRIDE_HOME_DAY, None),
    ]
    for suffix, default in OVERRIDE_DEFAULTS:
        entity = SmartChargingDepartureTime(entry_id="abc", id_suffix=suffix, default=default)
        assert entity.native_value is None


def test_unique_id_is_scoped_to_entry_and_suffix():
    entity = SmartChargingDepartureTime(entry_id="abc", id_suffix=DAY_MON, default=WEEKDAY_DEFAULT)
    assert entity.unique_id == "abc_departure_mon"


async def test_user_can_set_a_departure_time(hass):
    entity = SmartChargingDepartureTime(entry_id="abc", id_suffix=DAY_MON, default=WEEKDAY_DEFAULT)
    platform = MockEntityPlatform(hass, domain="time")
    await platform.async_add_entities([entity])
    await entity.async_set_value(time(7, 30))
    assert entity.native_value == time(7, 30)


async def test_setting_one_entity_does_not_affect_a_sibling(hass):
    mon = SmartChargingDepartureTime(entry_id="abc", id_suffix=DAY_MON, default=WEEKDAY_DEFAULT)
    holiday = SmartChargingDepartureTime(
        entry_id="abc", id_suffix=DEPARTURE_OVERRIDE_HOLIDAY, default=None
    )
    platform = MockEntityPlatform(hass, domain="time")
    await platform.async_add_entities([mon, holiday])
    await mon.async_set_value(time(7, 30))
    assert mon.native_value == time(7, 30)
    assert holiday.native_value is None


def test_translation_key_matches_suffix():
    entity = SmartChargingDepartureTime(
        entry_id="abc", id_suffix=DEPARTURE_OVERRIDE_HOLIDAY, default=None
    )
    assert entity.translation_key == "departure_holiday"


async def test_restores_a_previously_set_value_across_restart(hass):
    entity_id = "time.smart_charging_departure_mon"
    mock_restore_cache(hass, (State(entity_id, "07:30:00"),))
    entity = SmartChargingDepartureTime(entry_id="abc", id_suffix=DAY_MON, default=WEEKDAY_DEFAULT)
    entity.entity_id = entity_id
    platform = MockEntityPlatform(hass, domain="time")
    await platform.async_add_entities([entity])
    assert entity.native_value == time(7, 30)


async def test_malformed_restored_state_keeps_the_constructor_default(hass, caplog):
    """A malformed restored state (e.g. a corrupted registry entry) must not raise out of
    entity setup -- the constructor default is kept, mirroring adapters/store.py,
    adapters/time_read.py, and sensor.py's guarded restore paths (#571)."""
    entity_id = "time.smart_charging_departure_mon"
    mock_restore_cache(hass, (State(entity_id, "not-a-time"),))
    entity = SmartChargingDepartureTime(entry_id="abc", id_suffix=DAY_MON, default=WEEKDAY_DEFAULT)
    entity.entity_id = entity_id
    platform = MockEntityPlatform(hass, domain="time")
    with caplog.at_level(logging.ERROR):
        await platform.async_add_entities([entity])
    assert not any(record.levelno >= logging.ERROR for record in caplog.records)
    # Harness-independent signal: on the unguarded code, HA's entity_platform catches the
    # ValueError, logs it, and calls add_to_platform_abort() -- the entity never finishes
    # setup and its state is never written.
    assert hass.states.get(entity_id) is not None
    assert entity.native_value == WEEKDAY_DEFAULT


@pytest.mark.parametrize("sentinel_state", [STATE_UNKNOWN, STATE_UNAVAILABLE])
async def test_sentinel_restored_state_keeps_the_constructor_default(hass, sentinel_state):
    entity_id = "time.smart_charging_departure_mon"
    mock_restore_cache(hass, (State(entity_id, sentinel_state),))
    entity = SmartChargingDepartureTime(entry_id="abc", id_suffix=DAY_MON, default=WEEKDAY_DEFAULT)
    entity.entity_id = entity_id
    platform = MockEntityPlatform(hass, domain="time")
    await platform.async_add_entities([entity])
    assert entity.native_value == WEEKDAY_DEFAULT


async def test_no_restored_state_keeps_the_constructor_default(hass):
    entity = SmartChargingDepartureTime(entry_id="abc", id_suffix=DAY_MON, default=WEEKDAY_DEFAULT)
    platform = MockEntityPlatform(hass, domain="time")
    await platform.async_add_entities([entity])
    assert entity.native_value == WEEKDAY_DEFAULT


async def test_async_setup_entry_creates_nine_entities_with_expected_ids_and_defaults(hass):
    entry = MockConfigEntry(domain="smart_charging", entry_id="xyz")
    entry.add_to_hass(hass)
    added: list[SmartChargingDepartureTime] = []

    def _capture(entities):
        added.extend(entities)

    await async_setup_entry(hass, entry, _capture)

    assert len(added) == 9
    by_unique_id = {e.unique_id: e for e in added}
    expected_suffixes = [
        DAY_MON,
        DAY_TUE,
        DAY_WED,
        DAY_THU,
        DAY_FRI,
        DAY_SAT,
        DAY_SUN,
        DEPARTURE_OVERRIDE_HOLIDAY,
        DEPARTURE_OVERRIDE_HOME_DAY,
    ]
    assert set(by_unique_id) == {f"xyz_departure_{suffix}" for suffix in expected_suffixes}
    for suffix in (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI):
        assert by_unique_id[f"xyz_departure_{suffix}"].native_value == WEEKDAY_DEFAULT
    for suffix in (DAY_SAT, DAY_SUN, DEPARTURE_OVERRIDE_HOLIDAY, DEPARTURE_OVERRIDE_HOME_DAY):
        assert by_unique_id[f"xyz_departure_{suffix}"].native_value is None


def test_owned_labels_include_sc_runtime_when_deadline_available():
    entity = SmartChargingDepartureTime(
        entry_id="abc", id_suffix=DAY_MON, default=WEEKDAY_DEFAULT, deadline_available=True
    )
    assert entity._owned_labels == frozenset({LABEL_SC_RUNTIME})


def test_owned_labels_are_empty_when_deadline_not_available():
    entity = SmartChargingDepartureTime(
        entry_id="abc", id_suffix=DAY_MON, default=WEEKDAY_DEFAULT, deadline_available=False
    )
    assert entity._owned_labels == frozenset()


async def test_async_setup_entry_threads_deadline_capability_from_entry_data(hass):
    """Covers all three sources `async_setup_entry` reads `deadline_available` from: stored
    True, stored False, and the key absent entirely (a pre-existing entry from before this
    capability existed, #674) -- absent must default to present (R18 AC1)."""
    cases = [
        ({CONF_DEADLINE_AVAILABLE: True}, frozenset({LABEL_SC_RUNTIME})),
        ({CONF_DEADLINE_AVAILABLE: False}, frozenset()),
        ({}, frozenset({LABEL_SC_RUNTIME})),
    ]
    for entry_id, (data, expected) in enumerate(cases):
        entry = MockConfigEntry(domain="smart_charging", entry_id=str(entry_id), data=data)
        entry.add_to_hass(hass)
        added: list[SmartChargingDepartureTime] = []

        def _capture(entities, added=added):
            added.extend(entities)

        await async_setup_entry(hass, entry, _capture)

        assert len(added) == 9
        assert all(entity._owned_labels == expected for entity in added)


async def test_departure_time_disabled_by_default_when_deadline_unavailable(hass):
    """ADR-0028: a fresh install with deadline_available=False registers all 9 departure-time
    entities disabled."""
    seed_charger_states(hass, status="Charging")
    data = entry_data_base()
    data[CONF_DEADLINE_AVAILABLE] = False
    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    for suffix in _ALL_DEPARTURE_SUFFIXES:
        entity_id = registry.async_get_entity_id(
            Platform.TIME, DOMAIN, f"{entry.entry_id}_departure_{suffix}"
        )
        assert entity_id is not None, suffix
        assert registry.async_get(entity_id).disabled_by is er.RegistryEntryDisabler.INTEGRATION, (
            suffix
        )


async def test_departure_time_enabled_when_deadline_available(hass):
    """ADR-0028: deadline_available=True registers all 9 departure-time entities enabled."""
    seed_charger_states(hass, status="Charging")
    data = entry_data_base()
    data[CONF_DEADLINE_AVAILABLE] = True
    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    for suffix in _ALL_DEPARTURE_SUFFIXES:
        entity_id = registry.async_get_entity_id(
            Platform.TIME, DOMAIN, f"{entry.entry_id}_departure_{suffix}"
        )
        assert entity_id is not None, suffix
        assert registry.async_get(entity_id).disabled_by is None, suffix


async def test_departure_time_label_and_disabled_by_both_reflect_capability(hass):
    """ADR-0028 design doc §5: the one entity exercising both mechanisms together. Starts
    deadline_available=True (label present, entity live), then reloads with it False -- the
    entity is registry-disabled and never added to hass this reload, yet BOTH disabled_by
    becomes INTEGRATION AND the sc_runtime label is removed. Starting from a fresh install
    with the capability already off would prove nothing (no label to remove, no hook to
    replace) -- the label REMOVAL is what proves sync_labels's unique_id-keyed lookup (not
    entity_id-keyed) works independent of whether the entity was added to hass this reload."""
    seed_charger_states(hass, status="Charging")
    data = entry_data_base()
    data[CONF_DEADLINE_AVAILABLE] = True
    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        Platform.TIME, DOMAIN, f"{entry.entry_id}_departure_{DAY_MON}"
    )
    assert entity_id is not None
    entry_reg = registry.async_get(entity_id)
    assert entry_reg.disabled_by is None
    assert entry_reg.labels == {LABEL_SC_RUNTIME}

    off_data = entry_data_base()
    off_data[CONF_DEADLINE_AVAILABLE] = False
    hass.config_entries.async_update_entry(entry, data=off_data)
    await hass.async_block_till_done()

    entry_reg = registry.async_get(entity_id)
    assert entry_reg.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert entry_reg.labels == set()


async def test_departure_time_user_disable_survives_capability_toggle(hass):
    """ADR-0028: a user's own disabled_by=USER on one departure-time entity must survive a
    deadline_available toggle in either direction, while its label keeps tracking the
    capability correctly regardless -- the two mechanisms are independent (design doc's
    Decision), since the entity being force-enabled by the user doesn't mean the capability is
    present."""
    seed_charger_states(hass, status="Charging")
    data = entry_data_base()
    data[CONF_DEADLINE_AVAILABLE] = True
    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        Platform.TIME, DOMAIN, f"{entry.entry_id}_departure_{DAY_MON}"
    )
    assert entity_id is not None
    registry.async_update_entity(entity_id, disabled_by=er.RegistryEntryDisabler.USER)

    off_data = entry_data_base()
    off_data[CONF_DEADLINE_AVAILABLE] = False
    hass.config_entries.async_update_entry(entry, data=off_data)
    await hass.async_block_till_done()

    assert registry.async_get(entity_id).disabled_by is er.RegistryEntryDisabler.USER
    assert registry.async_get(entity_id).labels == set()

    on_data = entry_data_base()
    on_data[CONF_DEADLINE_AVAILABLE] = True
    hass.config_entries.async_update_entry(entry, data=on_data)
    await hass.async_block_till_done()

    assert registry.async_get(entity_id).disabled_by is er.RegistryEntryDisabler.USER
    assert registry.async_get(entity_id).labels == {LABEL_SC_RUNTIME}


async def test_departure_time_restored_value_survives_disable_cycle(hass):
    """Correction to ADR-0028's Context, which assumed a set departure time would revert to
    its R14 constructor default across a deadline_available off->on cycle, on the reasoning
    that the RestoreEntity read only runs while the entity is added to hass. Empirically, it
    doesn't need to run *during* the disabled window -- `RestoreEntity.async_will_remove_from_hass`
    writes the entity's last state into HA's `RestoreStateData` cache (keyed by entity_id) on
    every removal, disable-triggered or not, and that write is what `async_added_to_hass` reads
    back on re-enable; the cache isn't cleared just because the entity was disabled for a while.
    Documents the actual (safe) behavior as a passing assertion; the ADR's Consequences text
    needs a follow-up correction -- tracked in issue #804."""
    seed_charger_states(hass, status="Charging")
    data = entry_data_base()
    data[CONF_DEADLINE_AVAILABLE] = True
    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        Platform.TIME, DOMAIN, f"{entry.entry_id}_departure_{DAY_MON}"
    )
    assert entity_id is not None
    await hass.services.async_call(
        Platform.TIME,
        SERVICE_SET_VALUE,
        {"entity_id": entity_id, "time": "07:30:00"},
        blocking=True,
    )
    assert hass.states.get(entity_id).state == "07:30:00"

    off_data = entry_data_base()
    off_data[CONF_DEADLINE_AVAILABLE] = False
    hass.config_entries.async_update_entry(entry, data=off_data)
    await hass.async_block_till_done()

    # Confirm this is a genuine disable/re-enable cycle, not just a plain reload -- otherwise
    # the final assertion below would pass even if the gating were removed entirely.
    assert registry.async_get(entity_id).disabled_by is er.RegistryEntryDisabler.INTEGRATION
    # A previously-live entity leaves a restored/unavailable ghost state behind on removal
    # rather than disappearing from the state machine outright (same shape T1.1 found for
    # SolarSurplusSensor).
    disabled_state = hass.states.get(entity_id)
    assert disabled_state is None or disabled_state.state == STATE_UNAVAILABLE

    on_data = entry_data_base()
    on_data[CONF_DEADLINE_AVAILABLE] = True
    hass.config_entries.async_update_entry(entry, data=on_data)
    await hass.async_block_till_done()

    assert registry.async_get(entity_id).disabled_by is None
    assert hass.states.get(entity_id).state == "07:30:00"
