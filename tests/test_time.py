"""HA-harness tests for the departure-time entities (C2, R14)."""

from datetime import time

import pytest
from homeassistant.core import State
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockEntityPlatform,
    mock_restore_cache,
)

from custom_components.smart_charging.const import (
    DAY_FRI,
    DAY_MON,
    DAY_SAT,
    DAY_SUN,
    DAY_THU,
    DAY_TUE,
    DAY_WED,
    DEPARTURE_OVERRIDE_HOLIDAY,
    DEPARTURE_OVERRIDE_HOME_DAY,
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
