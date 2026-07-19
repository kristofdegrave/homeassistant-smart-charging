"""HA-harness test for the target-current number entity (C2, ADR-0004)."""

from homeassistant.components.number import NumberExtraStoredData
from homeassistant.core import State
from pytest_homeassistant_custom_component.common import (
    MockEntityPlatform,
    mock_restore_cache_with_extra_data,
)

from custom_components.smart_charging.number import TargetCurrentNumber


class _StubCoordinator:
    def __init__(self):
        self.target_current = None
        self.refreshed = False

    async def async_request_refresh(self):
        self.refreshed = True


async def test_set_value_pushes_to_coordinator(hass):
    coord = _StubCoordinator()
    entity = TargetCurrentNumber(
        entry_id="abc", coordinator=coord, min_a=6.0, max_a=16.0, default=10.0
    )
    platform = MockEntityPlatform(hass, domain="number")
    await platform.async_add_entities([entity])
    await entity.async_set_native_value(12.0)
    assert coord.target_current == 12.0
    assert coord.refreshed is True
    assert entity.native_value == 12.0


def test_init_seeds_bounds_and_default():
    coord = _StubCoordinator()
    entity = TargetCurrentNumber(
        entry_id="abc", coordinator=coord, min_a=6.0, max_a=16.0, default=10.0
    )
    assert entity.native_min_value == 6.0
    assert entity.native_max_value == 16.0
    assert entity.native_value == 10.0
    assert entity.unique_id == "abc_target_current"


async def test_added_to_hass_seeds_coordinator_with_default_when_no_restored_state(hass):
    coord = _StubCoordinator()
    entity = TargetCurrentNumber(
        entry_id="abc", coordinator=coord, min_a=6.0, max_a=16.0, default=10.0
    )
    platform = MockEntityPlatform(hass, domain="number")
    await platform.async_add_entities([entity])
    assert coord.target_current == 10.0
    assert entity.native_value == 10.0


async def test_added_to_hass_restores_previous_value_and_seeds_coordinator(hass):
    entity_id = "number.target_current"
    mock_restore_cache_with_extra_data(
        hass,
        (
            (
                State(entity_id, "13.0"),
                NumberExtraStoredData(
                    native_max_value=16.0,
                    native_min_value=6.0,
                    native_step=1.0,
                    native_unit_of_measurement="A",
                    native_value=13.0,
                ).as_dict(),
            ),
        ),
    )
    coord = _StubCoordinator()
    entity = TargetCurrentNumber(
        entry_id="abc", coordinator=coord, min_a=6.0, max_a=16.0, default=10.0
    )
    entity.entity_id = entity_id
    platform = MockEntityPlatform(hass, domain="number")
    await platform.async_add_entities([entity])
    assert entity.native_value == 13.0
    assert coord.target_current == 13.0
