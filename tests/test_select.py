"""HA-harness test for the mode selector (C2)."""

import pytest
from homeassistant.core import State
from pytest_homeassistant_custom_component.common import (
    MockEntityPlatform,
    mock_restore_cache,
)

from custom_components.smart_charging.select import ModeSelect, ProfileSelect


async def test_select_option_writes_only_its_own_state(hass):
    """ADR-0018: ModeSelect no longer references the coordinator at all -- its
    constructor doesn't accept one, and it only manages its own displayed state."""
    entity = ModeSelect(entry_id="abc", solar_installed=True)
    platform = MockEntityPlatform(hass, domain="select")
    await platform.async_add_entities([entity])
    await entity.async_select_option("Solar")
    assert entity.current_option == "Solar"


async def test_restores_last_selection(hass):
    entity_id = "select.smart_charging_mode"
    mock_restore_cache(hass, (State(entity_id, "SolarOnly"),))
    entity = ModeSelect(entry_id="abc", solar_installed=True)
    entity.entity_id = entity_id
    platform = MockEntityPlatform(hass, domain="select")
    await platform.async_add_entities([entity])
    assert entity.current_option == "SolarOnly"


async def test_restore_rejects_solar_option_when_solar_not_installed(hass):
    entity_id = "select.smart_charging_mode"
    mock_restore_cache(hass, (State(entity_id, "SolarOnly"),))
    entity = ModeSelect(entry_id="abc", solar_installed=False)
    entity.entity_id = entity_id
    platform = MockEntityPlatform(hass, domain="select")
    await platform.async_add_entities([entity])
    assert entity.current_option == "Off"


async def test_restore_rejects_captar_option_when_captar_not_available(hass):
    entity_id = "select.smart_charging_mode"
    mock_restore_cache(hass, (State(entity_id, "Captar"),))
    entity = ModeSelect(entry_id="abc", captar_available=False)
    entity.entity_id = entity_id
    platform = MockEntityPlatform(hass, domain="select")
    await platform.async_add_entities([entity])
    assert entity.current_option == "Off"


async def test_added_to_hass_seeds_default_when_no_restored_state(hass):
    entity = ModeSelect(entry_id="abc", solar_installed=True)
    platform = MockEntityPlatform(hass, domain="select")
    await platform.async_add_entities([entity])
    assert entity.current_option == "Off"


def test_init_seeds_unique_id():
    entity = ModeSelect(entry_id="abc", solar_installed=True)
    assert entity.unique_id == "abc_mode"


def test_options_are_off_power_only_when_solar_not_installed():
    entity = ModeSelect(entry_id="abc", solar_installed=False)
    assert entity.options == ["Off", "Power"]


def test_options_include_solar_modes_when_solar_installed():
    entity = ModeSelect(entry_id="abc", solar_installed=True)
    assert entity.options == ["Off", "Power", "Solar", "SolarOnly"]


@pytest.mark.parametrize(
    ("solar_installed", "captar_available", "expected"),
    [
        (False, False, ["Off", "Power"]),
        (True, False, ["Off", "Power", "Solar", "SolarOnly"]),
        (False, True, ["Off", "Power", "Captar"]),
        (True, True, ["Off", "Power", "Solar", "SolarOnly", "Captar"]),
    ],
)
def test_mode_options_compose_independently(solar_installed, captar_available, expected):
    entity = ModeSelect(
        entry_id="abc",
        solar_installed=solar_installed,
        captar_available=captar_available,
    )
    assert entity.options == expected


def test_default_profile_is_manual():
    entity = ProfileSelect(entry_id="abc")
    assert entity.current_option == "Manual"
    assert entity.options == ["Manual", "Auto"]


async def test_select_auto_writes_only_its_own_state(hass):
    """ADR-0018: ProfileSelect no longer references the coordinator at all."""
    entity = ProfileSelect(entry_id="abc")
    platform = MockEntityPlatform(hass, domain="select")
    await platform.async_add_entities([entity])
    await entity.async_select_option("Auto")
    assert entity.current_option == "Auto"


async def test_restores_prior_selection_across_restart(hass):
    """Mirrors ModeSelect's RestoreEntity test: a restored 'Auto' state is adopted on
    async_added_to_hass instead of resetting to the 'Manual' default."""
    entity_id = "select.smart_charging_profile"
    mock_restore_cache(hass, (State(entity_id, "Auto"),))
    entity = ProfileSelect(entry_id="abc")
    entity.entity_id = entity_id
    platform = MockEntityPlatform(hass, domain="select")
    await platform.async_add_entities([entity])
    assert entity.current_option == "Auto"


async def test_restore_rejects_unknown_option_falls_back_to_manual(hass):
    """Mirrors ModeSelect's test_restore_rejects_*_option tests: a restored state that is no
    longer a valid option (e.g. a renamed/removed profile) falls back to the Manual default
    rather than adopting the invalid value."""
    entity_id = "select.smart_charging_profile"
    mock_restore_cache(hass, (State(entity_id, "Bogus"),))
    entity = ProfileSelect(entry_id="abc")
    entity.entity_id = entity_id
    platform = MockEntityPlatform(hass, domain="select")
    await platform.async_add_entities([entity])
    assert entity.current_option == "Manual"


async def test_profile_added_to_hass_seeds_default_when_no_restored_state(hass):
    entity = ProfileSelect(entry_id="abc")
    platform = MockEntityPlatform(hass, domain="select")
    await platform.async_add_entities([entity])
    assert entity.current_option == "Manual"


def test_profile_init_seeds_unique_id():
    entity = ProfileSelect(entry_id="abc")
    assert entity.unique_id == "abc_profile"
