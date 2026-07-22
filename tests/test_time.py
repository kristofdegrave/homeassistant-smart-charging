"""HA-harness tests for the departure-time entities (C2, R14)."""

from datetime import time

import pytest
from pytest_homeassistant_custom_component.common import MockEntityPlatform

from custom_components.smart_charging.time import (
    DAY_OF_WEEK_DEFAULTS,
    OVERRIDE_DEFAULTS,
    WEEKDAY_DEFAULT,
    SmartChargingDepartureTime,
)

_WEEKDAY_SUFFIXES = ("mon", "tue", "wed", "thu", "fri")
_WEEKEND_SUFFIXES = ("sat", "sun")


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
        "mon",
        "tue",
        "wed",
        "thu",
        "fri",
        "sat",
        "sun",
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
    assert OVERRIDE_DEFAULTS == [("holiday", None), ("home_day", None)]
    for suffix, default in OVERRIDE_DEFAULTS:
        entity = SmartChargingDepartureTime(entry_id="abc", id_suffix=suffix, default=default)
        assert entity.native_value is None


def test_unique_id_is_scoped_to_entry_and_suffix():
    entity = SmartChargingDepartureTime(entry_id="abc", id_suffix="mon", default=WEEKDAY_DEFAULT)
    assert entity.unique_id == "abc_departure_mon"


async def test_user_can_set_a_departure_time(hass):
    entity = SmartChargingDepartureTime(entry_id="abc", id_suffix="mon", default=WEEKDAY_DEFAULT)
    platform = MockEntityPlatform(hass, domain="time")
    await platform.async_add_entities([entity])
    await entity.async_set_value(time(7, 30))
    assert entity.native_value == time(7, 30)


async def test_setting_one_entity_does_not_affect_a_sibling(hass):
    mon = SmartChargingDepartureTime(entry_id="abc", id_suffix="mon", default=WEEKDAY_DEFAULT)
    holiday = SmartChargingDepartureTime(entry_id="abc", id_suffix="holiday", default=None)
    platform = MockEntityPlatform(hass, domain="time")
    await platform.async_add_entities([mon, holiday])
    await mon.async_set_value(time(7, 30))
    assert mon.native_value == time(7, 30)
    assert holiday.native_value is None
