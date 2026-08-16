"""HA-harness tests for the departure-time entities (C2, R14)."""

import logging
from datetime import time

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
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
    LABEL_SC_RUNTIME,
)
from custom_components.smart_charging.time import (
    DAY_OF_WEEK_DEFAULTS,
    OVERRIDE_DEFAULTS,
    WEEKDAY_DEFAULT,
    SmartChargingDepartureTime,
    async_setup_entry,
)

_WEEKDAY_SUFFIXES = (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI)
_WEEKEND_SUFFIXES = (DAY_SAT, DAY_SUN)
_USER_LABEL = "some_other_label"


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


async def test_sc_runtime_label_is_registered_when_deadline_capability_present(hass):
    entity = SmartChargingDepartureTime(
        entry_id="abc", id_suffix=DAY_MON, default=WEEKDAY_DEFAULT, deadline_available=True
    )
    platform = MockEntityPlatform(hass, domain="time")
    await platform.async_add_entities([entity])

    registry = er.async_get(hass)
    assert registry.async_get(entity.entity_id).labels == {LABEL_SC_RUNTIME}


async def test_sc_runtime_label_is_absent_when_deadline_capability_off_from_the_start(hass):
    entity = SmartChargingDepartureTime(
        entry_id="abc", id_suffix=DAY_MON, default=WEEKDAY_DEFAULT, deadline_available=False
    )
    platform = MockEntityPlatform(hass, domain="time")
    await platform.async_add_entities([entity])

    registry = er.async_get(hass)
    assert registry.async_get(entity.entity_id).labels == set()


async def test_sc_runtime_label_is_removed_on_reload_after_capability_turned_off(hass):
    """The #674 fix must not be add-only: an installation that had the deadline capability on
    (registering the label) and later declares it off (reconfigure) must have the label
    removed on the next reload, not just skipped on future adds."""
    entity_id = "time.smart_charging_departure_mon"
    registry = er.async_get(hass)

    was_on = SmartChargingDepartureTime(
        entry_id="abc", id_suffix=DAY_MON, default=WEEKDAY_DEFAULT, deadline_available=True
    )
    was_on.entity_id = entity_id
    platform = MockEntityPlatform(hass, domain="time")
    await platform.async_add_entities([was_on])
    assert registry.async_get(entity_id).labels == {LABEL_SC_RUNTIME}

    # Simulate the entry reload a capability change triggers: a fresh instance, same
    # entity_id, with the capability now off.
    now_off = SmartChargingDepartureTime(
        entry_id="abc", id_suffix=DAY_MON, default=WEEKDAY_DEFAULT, deadline_available=False
    )
    now_off.entity_id = entity_id
    now_off.hass = hass
    await now_off.async_added_to_hass()

    assert registry.async_get(entity_id).labels == set()


async def test_sc_runtime_label_removal_preserves_a_users_own_label(hass):
    entity_id = "time.smart_charging_departure_mon"
    registry = er.async_get(hass)

    was_on = SmartChargingDepartureTime(
        entry_id="abc", id_suffix=DAY_MON, default=WEEKDAY_DEFAULT, deadline_available=True
    )
    was_on.entity_id = entity_id
    platform = MockEntityPlatform(hass, domain="time")
    await platform.async_add_entities([was_on])
    registry.async_update_entity(entity_id, labels={LABEL_SC_RUNTIME, _USER_LABEL})

    now_off = SmartChargingDepartureTime(
        entry_id="abc", id_suffix=DAY_MON, default=WEEKDAY_DEFAULT, deadline_available=False
    )
    now_off.entity_id = entity_id
    now_off.hass = hass
    await now_off.async_added_to_hass()

    assert registry.async_get(entity_id).labels == {_USER_LABEL}
