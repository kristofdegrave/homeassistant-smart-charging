"""HA-harness tests for the home-day flag switch (R9, R13)."""

from datetime import timedelta

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockEntityPlatform,
    async_fire_time_changed,
)

from custom_components.smart_charging.const import DOMAIN
from custom_components.smart_charging.switch import HomeDaySwitch, async_setup_entry


class _StubCoordinator:
    def __init__(self):
        self.home_day_flag = False
        self.refreshed = False

    def set_home_day_flag(self, value):
        self.home_day_flag = value

    async def async_request_refresh(self):
        self.refreshed = True


async def test_defaults_off(hass):
    entity = HomeDaySwitch(entry_id="abc", coordinator=_StubCoordinator())
    platform = MockEntityPlatform(hass, domain="switch")
    await platform.async_add_entities([entity])
    assert entity.is_on is False
    await entity.async_remove()


async def test_user_can_turn_on_and_off(hass):
    entity = HomeDaySwitch(entry_id="abc", coordinator=_StubCoordinator())
    platform = MockEntityPlatform(hass, domain="switch")
    await platform.async_add_entities([entity])

    await entity.async_turn_on()
    assert entity.is_on is True

    await entity.async_turn_off()
    assert entity.is_on is False
    await entity.async_remove()


async def test_resets_to_off_at_local_midnight(hass):
    entity = HomeDaySwitch(entry_id="abc", coordinator=_StubCoordinator())
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
    entity = HomeDaySwitch(entry_id="abc", coordinator=_StubCoordinator())
    assert entity.unique_id == "abc_home_day"


# --- issue #402: pushing into the coordinator (R9's solar-reserve trigger was inert without
#     this, mirroring ModeSelect/ProfileSelect's push pattern). ---


async def test_added_to_hass_seeds_coordinator_with_default_off(hass):
    # Stub pre-poisoned to True so the assertion can only pass if async_added_to_hass
    # actually pushed the entity's own (False) constructor default.
    coord = _StubCoordinator()
    coord.home_day_flag = True
    entity = HomeDaySwitch(entry_id="abc", coordinator=coord)
    platform = MockEntityPlatform(hass, domain="switch")
    await platform.async_add_entities([entity])
    assert coord.home_day_flag is False
    await entity.async_remove()


async def test_turn_on_pushes_true_into_coordinator_and_refreshes(hass):
    coord = _StubCoordinator()
    entity = HomeDaySwitch(entry_id="abc", coordinator=coord)
    platform = MockEntityPlatform(hass, domain="switch")
    await platform.async_add_entities([entity])

    await entity.async_turn_on()
    assert coord.home_day_flag is True
    assert coord.refreshed is True
    await entity.async_remove()


async def test_turn_off_pushes_false_into_coordinator_and_refreshes(hass):
    coord = _StubCoordinator()
    entity = HomeDaySwitch(entry_id="abc", coordinator=coord)
    platform = MockEntityPlatform(hass, domain="switch")
    await platform.async_add_entities([entity])

    await entity.async_turn_on()
    coord.refreshed = False
    await entity.async_turn_off()
    assert coord.home_day_flag is False
    assert coord.refreshed is True
    await entity.async_remove()


async def test_midnight_reset_pushes_false_into_coordinator_and_refreshes(hass):
    coord = _StubCoordinator()
    entity = HomeDaySwitch(entry_id="abc", coordinator=coord)
    platform = MockEntityPlatform(hass, domain="switch")
    await platform.async_add_entities([entity])

    await entity.async_turn_on()
    assert coord.home_day_flag is True
    coord.refreshed = False

    midnight = dt_util.start_of_local_day() + timedelta(days=1)
    async_fire_time_changed(hass, midnight)
    await hass.async_block_till_done()

    assert coord.home_day_flag is False
    assert coord.refreshed is True
    await entity.async_remove()


async def test_setup_entry_wires_the_switch_to_the_coordinator_from_hass_data(hass):
    entry = MockConfigEntry(domain="smart_charging", entry_id="xyz")
    entry.add_to_hass(hass)
    coord = _StubCoordinator()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"coordinator": coord}
    added: list[HomeDaySwitch] = []

    def _capture(entities):
        added.extend(entities)

    await async_setup_entry(hass, entry, _capture)
    assert len(added) == 1
    platform = MockEntityPlatform(hass, domain="switch")
    await platform.async_add_entities(added)

    await added[0].async_turn_on()
    assert coord.home_day_flag is True
    assert coord.refreshed is True
    await added[0].async_remove()
