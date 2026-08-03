"""HA-harness test for the target-current number entity (C2, ADR-0004)."""

from homeassistant.components.number import NumberExtraStoredData
from homeassistant.core import State
from pytest_homeassistant_custom_component.common import (
    MockEntityPlatform,
    mock_restore_cache_with_extra_data,
)

from custom_components.smart_charging.const import SOC_LIMIT_OVERRIDE_MIN
from custom_components.smart_charging.number import (
    SocLimitOverrideNumber,
    TargetCurrentNumber,
)


async def test_set_value_writes_only_its_own_state(hass):
    """ADR-0018: TargetCurrentNumber no longer references the coordinator at all."""
    entity = TargetCurrentNumber(entry_id="abc", min_a=6.0, max_a=16.0, default=10.0)
    platform = MockEntityPlatform(hass, domain="number")
    await platform.async_add_entities([entity])
    await entity.async_set_native_value(12.0)
    assert entity.native_value == 12.0


def test_init_seeds_bounds_and_default():
    entity = TargetCurrentNumber(entry_id="abc", min_a=6.0, max_a=16.0, default=10.0)
    assert entity.native_min_value == 6.0
    assert entity.native_max_value == 16.0
    assert entity.native_value == 10.0
    assert entity.unique_id == "abc_target_current"


def test_init_clamps_out_of_range_default_target_current():
    """config_flow validates default_target_current with vol.Coerce(float) only, no
    [min_a, max_a] range -- an out-of-range configured default must clamp here too
    (ADR-0014 criterion 6, entity-side clamp, distinct from the coordinator's own)."""
    entity = TargetCurrentNumber(entry_id="abc", min_a=6.0, max_a=16.0, default=99.0)
    assert entity.native_value == 16.0


def test_init_clamps_out_of_range_default_target_current_below_minimum():
    """Same clamp as above, exercised on the below-minimum side too -- the plan's own test
    body only covers the above-maximum case, so this closes the min(default, min_a) half."""
    entity = TargetCurrentNumber(entry_id="abc", min_a=6.0, max_a=16.0, default=1.0)
    assert entity.native_value == 6.0


async def test_added_to_hass_seeds_default_when_no_restored_state(hass):
    entity = TargetCurrentNumber(entry_id="abc", min_a=6.0, max_a=16.0, default=10.0)
    platform = MockEntityPlatform(hass, domain="number")
    await platform.async_add_entities([entity])
    assert entity.native_value == 10.0


async def test_added_to_hass_restores_previous_value(hass):
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
    entity = TargetCurrentNumber(entry_id="abc", min_a=6.0, max_a=16.0, default=10.0)
    entity.entity_id = entity_id
    platform = MockEntityPlatform(hass, domain="number")
    await platform.async_add_entities([entity])
    assert entity.native_value == 13.0


async def test_soc_limit_override_set_value_writes_only_its_own_state(hass):
    """ADR-0018: SocLimitOverrideNumber no longer references the coordinator at all."""
    entity = SocLimitOverrideNumber(entry_id="abc", default=80.0)
    platform = MockEntityPlatform(hass, domain="number")
    await platform.async_add_entities([entity])
    await entity.async_set_native_value(90.0)
    assert entity.native_value == 90.0


def test_soc_limit_override_init_seeds_bounds_and_default():
    entity = SocLimitOverrideNumber(entry_id="abc", default=80.0)
    assert entity.native_min_value == 50.0
    assert entity.native_max_value == 100.0
    assert entity.native_value == 80.0
    assert entity.unique_id == "abc_soc_limit_override"


async def test_soc_limit_override_added_to_hass_seeds_default_when_no_restored_state(
    hass,
):
    entity = SocLimitOverrideNumber(entry_id="abc", default=80.0)
    platform = MockEntityPlatform(hass, domain="number")
    await platform.async_add_entities([entity])
    assert entity.native_value == 80.0


async def test_soc_limit_override_added_to_hass_restores_previous_value(
    hass,
):
    entity_id = "number.soc_limit_override"
    mock_restore_cache_with_extra_data(
        hass,
        (
            (
                State(entity_id, "95.0"),
                NumberExtraStoredData(
                    native_max_value=100.0,
                    native_min_value=50.0,
                    native_step=1.0,
                    native_unit_of_measurement="%",
                    native_value=95.0,
                ).as_dict(),
            ),
        ),
    )
    entity = SocLimitOverrideNumber(entry_id="abc", default=80.0)
    entity.entity_id = entity_id
    platform = MockEntityPlatform(hass, domain="number")
    await platform.async_add_entities([entity])
    assert entity.native_value == 95.0


async def test_soc_limit_override_added_to_hass_clamps_restored_value_above_max(hass):
    entity_id = "number.soc_limit_override_over"
    mock_restore_cache_with_extra_data(
        hass,
        (
            (
                State(entity_id, "150.0"),
                NumberExtraStoredData(
                    native_max_value=100.0,
                    native_min_value=50.0,
                    native_step=1.0,
                    native_unit_of_measurement="%",
                    native_value=150.0,
                ).as_dict(),
            ),
        ),
    )
    entity = SocLimitOverrideNumber(entry_id="abc", default=80.0)
    entity.entity_id = entity_id
    platform = MockEntityPlatform(hass, domain="number")
    await platform.async_add_entities([entity])
    assert entity.native_value == 100.0


async def test_soc_limit_override_added_to_hass_clamps_restored_value_below_min(hass):
    entity_id = "number.soc_limit_override_under"
    mock_restore_cache_with_extra_data(
        hass,
        (
            (
                State(entity_id, "10.0"),
                NumberExtraStoredData(
                    native_max_value=100.0,
                    native_min_value=50.0,
                    native_step=1.0,
                    native_unit_of_measurement="%",
                    native_value=10.0,
                ).as_dict(),
            ),
        ),
    )
    entity = SocLimitOverrideNumber(entry_id="abc", default=80.0)
    entity.entity_id = entity_id
    platform = MockEntityPlatform(hass, domain="number")
    await platform.async_add_entities([entity])
    assert entity.native_value == 50.0


def test_init_clamps_out_of_range_default_soc_limit():
    """config_flow validates default_soc_limit with vol.Coerce(float) only, no 50-100 range --
    an out-of-range configured default must clamp here too."""
    entity = SocLimitOverrideNumber(entry_id="abc", default=30.0)
    assert entity.native_value == SOC_LIMIT_OVERRIDE_MIN
