"""HA-harness tests for the RA3 Store (ADR-0018/0019)."""

from datetime import time as time_of_day

from homeassistant.const import Platform
from homeassistant.helpers import entity_registry as er

from custom_components.smart_charging.adapters.store import Store
from custom_components.smart_charging.const import DOMAIN


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
        "unavailable",
    )
    store = Store(hass, "entry1")
    assert await store.read(Platform.NUMBER, "target_current", float) is None


async def test_read_unknown_returns_none(hass):
    _register(
        hass, Platform.NUMBER, "smart_charging_target_current", "entry1_target_current", "unknown"
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
