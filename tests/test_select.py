"""HA-harness test for the mode selector (C2).

Deliberately pins the raw option strings ("Off"/"Power"/"Solar"/.../"Manual"/"Auto") rather
than importing MODE_*/PROFILE_* from const.py (issue #508 scope note): these are the
entity's user-facing external contract (select.mode/select.profile's actual state values),
so a test asserting against the same constants the entity is built from wouldn't catch a
constant-value regression -- pinning the literal is the point here, not an oversight.
"""

import pytest
from homeassistant.const import Platform
from homeassistant.core import State
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockEntityPlatform,
    mock_restore_cache,
)

from custom_components.smart_charging.const import (
    DOMAIN,
    LABEL_SC_RUNTIME,
    OWNED_SUFFIX_MODE,
    OWNED_SUFFIX_PROFILE,
)
from custom_components.smart_charging.select import ModeSelect, ProfileSelect
from tests.helpers import entry_data_base, entry_options_base, seed_charger_states


async def test_select_option_writes_only_its_own_state(hass):
    """ADR-0018: ModeSelect no longer references the coordinator at all -- its
    constructor doesn't accept one, and it only manages its own displayed state."""
    entity = ModeSelect(entry_id="abc", solar_available=True)
    platform = MockEntityPlatform(hass, domain="select")
    await platform.async_add_entities([entity])
    await entity.async_select_option("Solar")
    assert entity.current_option == "Solar"


async def test_restores_last_selection(hass):
    entity_id = "select.smart_charging_mode"
    mock_restore_cache(hass, (State(entity_id, "SolarOnly"),))
    entity = ModeSelect(entry_id="abc", solar_available=True)
    entity.entity_id = entity_id
    platform = MockEntityPlatform(hass, domain="select")
    await platform.async_add_entities([entity])
    assert entity.current_option == "SolarOnly"


async def test_restore_rejects_solar_option_when_solar_not_installed(hass):
    entity_id = "select.smart_charging_mode"
    mock_restore_cache(hass, (State(entity_id, "SolarOnly"),))
    entity = ModeSelect(entry_id="abc", solar_available=False)
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
    entity = ModeSelect(entry_id="abc", solar_available=True)
    platform = MockEntityPlatform(hass, domain="select")
    await platform.async_add_entities([entity])
    assert entity.current_option == "Off"


def test_init_seeds_unique_id():
    entity = ModeSelect(entry_id="abc", solar_available=True)
    assert entity.unique_id == "abc_mode"


def test_options_are_off_power_only_when_solar_not_installed():
    entity = ModeSelect(entry_id="abc", solar_available=False)
    assert entity.options == ["Off", "Power"]


def test_options_include_solar_modes_when_solar_available():
    entity = ModeSelect(entry_id="abc", solar_available=True)
    assert entity.options == ["Off", "Power", "Solar", "SolarOnly"]


@pytest.mark.parametrize(
    ("solar_available", "captar_available", "expected"),
    [
        (False, False, ["Off", "Power"]),
        (True, False, ["Off", "Power", "Solar", "SolarOnly"]),
        (False, True, ["Off", "Power", "Captar"]),
        (True, True, ["Off", "Power", "Solar", "SolarOnly", "Captar"]),
    ],
)
def test_mode_options_compose_independently(solar_available, captar_available, expected):
    entity = ModeSelect(
        entry_id="abc",
        solar_available=solar_available,
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


@pytest.mark.parametrize("suffix", [OWNED_SUFFIX_MODE, OWNED_SUFFIX_PROFILE])
async def test_select_entity_carries_runtime_label_after_setup(hass, suffix):
    """ADR-0028 (T3.3): ModeSelect's and ProfileSelect's label sync moves to a setup-time
    sync_labels call in async_setup_entry, replacing the async_added_to_hass hook -- a pure
    mechanism move. Neither entity's registry disabled_by state is capability-gated:
    ModeSelect's solar_available/captar_available constructor params only gate its *option
    list* (a separate, pre-existing, untouched mechanism), not this label/disabled_by
    machinery. Mirrors T3.1/T3.2's tests: currently passes via the still-active hook alone
    (T3.3 doesn't delete it -- that's T3.4's job), so it's a regression guard for T3.4, not a
    red/green TDD case in the usual sense. Directly confirmed (not just inferred) that the
    setup-time sync_labels call itself is what writes the label: a temporary diagnostic print
    inside async_setup_entry showed registry.async_get_entity_id already resolving for both
    entities at the exact point sync_labels runs, immediately after the non-awaited
    async_add_entities(entities) call -- so this isn't relying on the hook racing to finish
    later (the same class of concern T3.2's review raised and settled the same way)."""
    seed_charger_states(hass, status="Charging")
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data_base(), options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(Platform.SELECT, DOMAIN, f"{entry.entry_id}_{suffix}")
    assert entity_id is not None
    entry_reg = registry.async_get(entity_id)
    assert entry_reg.labels == {LABEL_SC_RUNTIME}
    assert entry_reg.disabled_by is None
