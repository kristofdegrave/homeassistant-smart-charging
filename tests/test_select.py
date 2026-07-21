"""HA-harness test for the mode selector (C2)."""

import pytest
from homeassistant.core import State
from pytest_homeassistant_custom_component.common import (
    MockEntityPlatform,
    mock_restore_cache,
)

from custom_components.smart_charging.select import ModeSelect


class _StubCoordinator:
    def __init__(self):
        self.active_mode = None
        self.refreshed = False

    async def async_request_refresh(self):
        self.refreshed = True


async def test_select_option_pushes_to_coordinator(hass):
    coord = _StubCoordinator()
    entity = ModeSelect(entry_id="abc", coordinator=coord, solar_installed=True)
    platform = MockEntityPlatform(hass, domain="select")
    await platform.async_add_entities([entity])
    await entity.async_select_option("Solar")
    assert coord.active_mode == "Solar"
    assert coord.refreshed is True
    assert entity.current_option == "Solar"


async def test_restores_last_selection(hass):
    entity_id = "select.smart_charging_mode"
    mock_restore_cache(hass, (State(entity_id, "SolarOnly"),))
    coord = _StubCoordinator()
    entity = ModeSelect(entry_id="abc", coordinator=coord, solar_installed=True)
    entity.entity_id = entity_id
    platform = MockEntityPlatform(hass, domain="select")
    await platform.async_add_entities([entity])
    assert entity.current_option == "SolarOnly"
    assert coord.active_mode == "SolarOnly"


async def test_restore_rejects_solar_option_when_solar_not_installed(hass):
    entity_id = "select.smart_charging_mode"
    mock_restore_cache(hass, (State(entity_id, "SolarOnly"),))
    coord = _StubCoordinator()
    entity = ModeSelect(entry_id="abc", coordinator=coord, solar_installed=False)
    entity.entity_id = entity_id
    platform = MockEntityPlatform(hass, domain="select")
    await platform.async_add_entities([entity])
    assert entity.current_option == "Off"
    assert coord.active_mode == "Off"


async def test_restore_rejects_captar_option_when_captar_not_available(hass):
    entity_id = "select.smart_charging_mode"
    mock_restore_cache(hass, (State(entity_id, "Captar"),))
    coord = _StubCoordinator()
    entity = ModeSelect(entry_id="abc", coordinator=coord, captar_available=False)
    entity.entity_id = entity_id
    platform = MockEntityPlatform(hass, domain="select")
    await platform.async_add_entities([entity])
    assert entity.current_option == "Off"
    assert coord.active_mode == "Off"


async def test_added_to_hass_seeds_coordinator_with_default_when_no_restored_state(hass):
    coord = _StubCoordinator()
    entity = ModeSelect(entry_id="abc", coordinator=coord, solar_installed=True)
    platform = MockEntityPlatform(hass, domain="select")
    await platform.async_add_entities([entity])
    assert entity.current_option == "Off"
    assert coord.active_mode == "Off"


def test_init_seeds_unique_id():
    entity = ModeSelect(entry_id="abc", coordinator=_StubCoordinator(), solar_installed=True)
    assert entity.unique_id == "abc_mode"


def test_options_are_off_power_only_when_solar_not_installed():
    entity = ModeSelect(entry_id="abc", coordinator=_StubCoordinator(), solar_installed=False)
    assert entity.options == ["Off", "Power"]


def test_options_include_solar_modes_when_solar_installed():
    entity = ModeSelect(entry_id="abc", coordinator=_StubCoordinator(), solar_installed=True)
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
        coordinator=_StubCoordinator(),
        solar_installed=solar_installed,
        captar_available=captar_available,
    )
    assert entity.options == expected
