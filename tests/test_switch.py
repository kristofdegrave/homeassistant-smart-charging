"""HA-harness tests for the home-day flag switch (R9, R13)."""

from datetime import timedelta

from homeassistant.const import Platform
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockEntityPlatform,
    async_fire_time_changed,
)

from custom_components.smart_charging.const import DOMAIN, LABEL_SC_RUNTIME, OWNED_SUFFIX_HOME_DAY
from custom_components.smart_charging.switch import HomeDaySwitch
from tests.helpers import entry_data_base, entry_options_base, seed_charger_states


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


async def test_home_day_switch_carries_runtime_label_after_setup(hass):
    """ADR-0028 (T3.1): HomeDaySwitch's label sync moves to a setup-time sync_labels call in
    async_setup_entry, replacing the async_added_to_hass hook -- a pure mechanism move, no
    capability gating (this entity is never conditional). This currently passes via the
    still-active hook alone (T3.1 doesn't delete it -- that's T3.4's job), so it isn't a
    red-then-green test in the usual TDD sense; it's the regression guard the plan's own
    build-order note calls for, proving the label still ends up correct once the setup-time
    call site exists, so T3.4 can safely delete the hook later without this test needing to
    change at all."""
    seed_charger_states(hass, status="Charging")
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data_base(), options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        Platform.SWITCH, DOMAIN, f"{entry.entry_id}_{OWNED_SUFFIX_HOME_DAY}"
    )
    assert entity_id is not None
    assert registry.async_get(entity_id).labels == {LABEL_SC_RUNTIME}
