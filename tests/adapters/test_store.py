"""HA-harness tests for the RA3 Store (ADR-0018/0019)."""

from datetime import time as time_of_day
from unittest.mock import patch

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, Platform
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_charging.adapters.store import Store
from custom_components.smart_charging.const import (
    DOMAIN,
    OWNED_SUFFIX_HOME_DAY,
    OWNED_SUFFIX_SOC_LIMIT_OVERRIDE,
)
from tests.helpers import entry_data_base, entry_options_base

SOC_LIMIT_ENTITY_ID = "number.smart_charging_soc_limit_override"
HOME_DAY_ENTITY_ID = "switch.smart_charging_home_day"


def _register(hass, entity_domain: str, object_id: str, unique_id: str, state: str) -> None:
    """Register an entity_domain.object_id entity under DOMAIN with the given unique_id, then
    set its state -- mirrors how a real owned entity's platform setup + async_write_ha_state
    behave."""
    er.async_get(hass).async_get_or_create(
        entity_domain, DOMAIN, unique_id, suggested_object_id=object_id
    )
    hass.states.async_set(f"{entity_domain}.{object_id}", state)


async def test_read_str_returns_registered_entity_state(hass):
    _register(hass, Platform.SELECT, "smart_charging_mode", "entry1_mode", "solar")
    store = Store(hass, "entry1")
    assert await store.read(Platform.SELECT, "mode", str) == "solar"


async def test_read_float_coerces_native_value(hass):
    _register(
        hass, Platform.NUMBER, "smart_charging_target_current", "entry1_target_current", "10.0"
    )
    store = Store(hass, "entry1")
    assert await store.read(Platform.NUMBER, "target_current", float) == 10.0


async def test_read_unregistered_entity_returns_none(hass):
    store = Store(hass, "entry1")
    assert await store.read(Platform.SELECT, "mode", str) is None


async def test_read_unavailable_returns_none(hass):
    _register(
        hass,
        Platform.NUMBER,
        "smart_charging_target_current",
        "entry1_target_current",
        STATE_UNAVAILABLE,
    )
    store = Store(hass, "entry1")
    assert await store.read(Platform.NUMBER, "target_current", float) is None


async def test_read_unknown_returns_none(hass):
    _register(
        hass,
        Platform.NUMBER,
        "smart_charging_target_current",
        "entry1_target_current",
        STATE_UNKNOWN,
    )
    store = Store(hass, "entry1")
    assert await store.read(Platform.NUMBER, "target_current", float) is None


async def test_read_float_non_numeric_returns_none(hass):
    _register(
        hass,
        Platform.NUMBER,
        "smart_charging_target_current",
        "entry1_target_current",
        "not-a-number",
    )
    store = Store(hass, "entry1")
    assert await store.read(Platform.NUMBER, "target_current", float) is None


async def test_read_bool_on_returns_true(hass):
    _register(hass, Platform.SWITCH, "smart_charging_home_day", "entry1_home_day", "on")
    store = Store(hass, "entry1")
    assert await store.read(Platform.SWITCH, "home_day", bool) is True


async def test_read_bool_off_returns_false(hass):
    _register(hass, Platform.SWITCH, "smart_charging_home_day", "entry1_home_day", "off")
    store = Store(hass, "entry1")
    assert await store.read(Platform.SWITCH, "home_day", bool) is False


async def test_read_time_parses_isoformat(hass):
    _register(
        hass, Platform.TIME, "smart_charging_departure_mon", "entry1_departure_mon", "06:00:00"
    )
    store = Store(hass, "entry1")
    assert await store.read(Platform.TIME, "departure_mon", time_of_day) == time_of_day(6, 0)


async def test_read_time_invalid_isoformat_returns_none(hass):
    _register(
        hass,
        Platform.TIME,
        "smart_charging_departure_mon",
        "entry1_departure_mon",
        "not-a-time",
    )
    store = Store(hass, "entry1")
    assert await store.read(Platform.TIME, "departure_mon", time_of_day) is None


async def _setup_entry(hass):
    """Set up the real integration so the genuine SocLimitOverrideNumber entity exists --
    a registry row + a seeded state string (this file's `_register`) is enough for read(),
    but a service call needs a real entity object to dispatch to. Unlike tests/test_init.py's
    setup, this does not call seed_charger_states() first -- the hardware adapters are left
    unmapped, so the coordinator's first cycle logs missing-entity warnings for them (absorbed
    by its own ADR-0007 fault path) and does nothing else; harmless noise for these tests,
    which only exercise the owned number entity."""
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data_base(), options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_write_sets_the_real_number_entity(hass):
    """ADR-0018 write half: the value reaches the real entity (native_value + HA state), not
    just the state machine -- so RestoreNumber persists it (ADR-0004)."""
    entry = await _setup_entry(hass)
    store = Store(hass, entry.entry_id)

    assert await store.write(Platform.NUMBER, OWNED_SUFFIX_SOC_LIMIT_OVERRIDE, 70.0) is True
    await hass.async_block_till_done()

    assert float(hass.states.get(SOC_LIMIT_ENTITY_ID).state) == 70.0


async def test_write_goes_through_the_entity_not_around_it(hass):
    """The value survives the entity writing its own state again -- a direct
    hass.states.async_set would be reverted here, since _attr_native_value would be stale."""
    entry = await _setup_entry(hass)
    store = Store(hass, entry.entry_id)
    await store.write(Platform.NUMBER, OWNED_SUFFIX_SOC_LIMIT_OVERRIDE, 70.0)
    await hass.async_block_till_done()

    entity = hass.data["entity_components"][Platform.NUMBER].get_entity(SOC_LIMIT_ENTITY_ID)
    entity.async_write_ha_state()
    await hass.async_block_till_done()

    assert float(hass.states.get(SOC_LIMIT_ENTITY_ID).state) == 70.0


async def test_write_unregistered_entity_returns_false(hass):
    """Startup race: nothing registered for this suffix -- a benign no-op, same as read()."""
    store = Store(hass, "entry1")
    assert await store.write(Platform.NUMBER, OWNED_SUFFIX_SOC_LIMIT_OVERRIDE, 70.0) is False


async def test_write_unsupported_domain_returns_false(hass):
    """Scope guard (design doc): only `number` is supported today -- a wrong domain must not
    issue a number.set_value against an entity that cannot take it. Targets
    home_day_flag (a real switch.py entity, OWNED_SUFFIX_HOME_DAY), not soc_limit_override
    -- the latter lives in the number domain and would return False via the unregistered
    branch even without the domain guard, making the test vacuous."""
    entry = await _setup_entry(hass)
    store = Store(hass, entry.entry_id)
    before = hass.states.get(HOME_DAY_ENTITY_ID).state

    assert await store.write(Platform.SWITCH, OWNED_SUFFIX_HOME_DAY, 70.0) is False

    assert hass.states.get(HOME_DAY_ENTITY_ID).state == before


async def test_write_out_of_range_value_returns_false_and_leaves_entity_unchanged(hass):
    """The clamp is the caller's job (design: Managers hold R6's 50-100 policy) -- the
    entity's own bounds are the backstop, and a violation is a logged no-op, never an
    exception escaping into a Manager's reaction path."""
    entry = await _setup_entry(hass)
    store = Store(hass, entry.entry_id)
    before = hass.states.get(SOC_LIMIT_ENTITY_ID).state

    assert await store.write(Platform.NUMBER, OWNED_SUFFIX_SOC_LIMIT_OVERRIDE, 120.0) is False
    await hass.async_block_till_done()

    assert hass.states.get(SOC_LIMIT_ENTITY_ID).state == before


async def test_write_service_failure_returns_false(hass):
    """A raising service call is best-effort, not fatal -- deliberately a plain RuntimeError,
    not a HomeAssistantError, so this pins the broad `except Exception` contract rather than
    only the narrower `except HomeAssistantError` the out-of-range test above would also
    satisfy (ServiceValidationError is itself a HomeAssistantError subclass). ServiceRegistry
    declares __slots__, so patch.object on the instance would raise AttributeError before the
    test body runs -- patch the class."""
    entry = await _setup_entry(hass)
    store = Store(hass, entry.entry_id)

    async def _boom(*args, **kwargs):
        raise RuntimeError("service unavailable")

    with patch.object(type(hass.services), "async_call", _boom):
        assert await store.write(Platform.NUMBER, OWNED_SUFFIX_SOC_LIMIT_OVERRIDE, 70.0) is False
