"""HA-harness tests for the home-day flag switch (R9, R13)."""

from datetime import timedelta

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockEntityPlatform,
    async_fire_time_changed,
)

from custom_components.smart_charging.switch import HomeDaySwitch


async def test_defaults_off(hass):
    entity = HomeDaySwitch(entry_id="abc")
    platform = MockEntityPlatform(hass, domain="switch")
    await platform.async_add_entities([entity])
    assert entity.is_on is False
    await entity.async_remove()


async def test_user_can_turn_on_and_off(hass):
    entity = HomeDaySwitch(entry_id="abc")
    platform = MockEntityPlatform(hass, domain="switch")
    await platform.async_add_entities([entity])

    await entity.async_turn_on()
    assert entity.is_on is True

    await entity.async_turn_off()
    assert entity.is_on is False
    await entity.async_remove()


async def test_resets_to_off_at_local_midnight(hass):
    entity = HomeDaySwitch(entry_id="abc")
    platform = MockEntityPlatform(hass, domain="switch")
    await platform.async_add_entities([entity])

    await entity.async_turn_on()
    assert entity.is_on is True

    midnight = dt_util.start_of_local_day() + timedelta(days=1)
    async_fire_time_changed(hass, midnight)
    await hass.async_block_till_done()

    assert entity.is_on is False
    await entity.async_remove()


def test_init_seeds_unique_id():
    entity = HomeDaySwitch(entry_id="abc")
    assert entity.unique_id == "abc_home_day"
