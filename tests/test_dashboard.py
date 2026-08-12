"""Tests for the runtime dashboard's generated Lovelace config and registration (C5, #601).

`_package_dir` is redirected to `tmp_path` for every HA-harness test via the autouse fixture
in `tests/conftest.py` -- no per-test monkeypatch needed here.
"""

import yaml
from homeassistant.components import frontend, lovelace
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_charging.const import (
    CONF_EV_SOC_ENTITY,
    CONF_SOLAR_FORECAST_ENTITY,
    DASHBOARD_FILENAME,
    DASHBOARD_URL_PATH,
    DOMAIN,
    LABEL_SC_RUNTIME,
)
from custom_components.smart_charging.dashboard import (
    async_register_dashboard,
    async_unregister_dashboard,
    build_dashboard_config,
)
from tests.helpers import entry_data_base


def _entry(**data_overrides):
    return MockConfigEntry(domain=DOMAIN, data=entry_data_base(**data_overrides))


def _view(config, path):
    for view in config["views"]:
        if view["path"] == path:
            return view
    raise AssertionError(f"no view at path {path!r}")


def _cards(config, section_title, view_path="overview"):
    for section in _view(config, view_path)["sections"]:
        if section["title"] == section_title:
            return section["cards"]
    raise AssertionError(f"no section titled {section_title!r} in view {view_path!r}")


def test_dashboard_has_two_views_overview_and_deadline():
    """T9 (2026-08-13 addendum): HA renders >1 views in a YAML dashboard as tabs natively --
    no new registration mechanism needed beyond ADR-0022's Option C."""
    config = build_dashboard_config(_entry())

    assert [v["path"] for v in config["views"]] == ["overview", "deadline"]
    assert all(v["type"] == "sections" for v in config["views"])


def test_the_overview_view_is_titled_smart_charging():
    view = _view(build_dashboard_config(_entry()), "overview")

    assert view["title"] == "Smart Charging"


def test_the_overview_view_has_exactly_three_sections_in_order():
    """Regression guard: T9 rebuilt build_dashboard_config wholesale -- nothing else asserts
    the overview's section count/order survived that rebuild."""
    view = _view(build_dashboard_config(_entry()), "overview")

    assert [s["title"] for s in view["sections"]] == [
        "Charging status",
        "Power flow",
        "Runtime settings",
    ]


def test_the_deadline_view_is_titled_deadline_with_one_departure_times_section():
    view = _view(build_dashboard_config(_entry()), "deadline")

    assert view["title"] == "Deadline"
    assert [s["title"] for s in view["sections"]] == ["Departure times"]


def test_the_mode_entity_is_rendered_by_exactly_the_gated_card_not_the_auto_entities_list():
    """The invariant T8's exclude clause exists to guarantee, expressed directly: the mode
    entity is only ever *rendered* by the gated card, and the label-driven auto-entities card
    (which would otherwise render it unconditionally) excludes it rather than listing it."""
    cards = _cards(build_dashboard_config(_entry()), "Runtime settings")
    mode_gate_card, auto_entities_card = cards

    assert mode_gate_card["entities"] == ["select.smart_charging_mode"]
    assert {"entity_id": "select.smart_charging_mode"} in auto_entities_card["filter"]["exclude"]


def test_charging_status_section_has_the_seven_documented_tiles():
    entry = _entry(**{CONF_EV_SOC_ENTITY: "sensor.ev_soc"})
    cards = _cards(build_dashboard_config(entry), "Charging status")

    assert [c["entity"] for c in cards] == [
        "sensor.evse",  # CONF_CHARGER_STATUS_ENTITY, entry_data_base's mapped value
        "sensor.ev_soc",
        "select.smart_charging_profile",
        "sensor.smart_charging_active_mode",
        "sensor.smart_charging_active_soc_limit",
        "sensor.smart_charging_time_to_full",
        "sensor.smart_charging_peak_headroom_a",
    ]
    assert all(c["type"] == "tile" for c in cards)


def test_charging_status_section_omits_the_battery_tile_when_ev_soc_is_unset():
    entry = _entry()
    assert CONF_EV_SOC_ENTITY not in entry.data
    cards = _cards(build_dashboard_config(entry), "Charging status")

    assert len(cards) == 6
    assert all(c["entity"] is not None for c in cards)


def test_charging_status_section_omits_the_battery_tile_when_ev_soc_is_the_empty_string():
    """A reconfigure flow can persist an unmapped optional role as `""` rather than omitting
    the key entirely -- must be treated the same as unset, not templated into a broken tile."""
    entry = _entry(**{CONF_EV_SOC_ENTITY: ""})
    cards = _cards(build_dashboard_config(entry), "Charging status")

    assert len(cards) == 6


def test_power_flow_section_has_the_four_tiles_plus_a_conditional_markdown_card():
    entry = _entry(**{CONF_SOLAR_FORECAST_ENTITY: "sensor.solar_forecast_tomorrow"})
    cards = _cards(build_dashboard_config(entry), "Power flow")

    assert [c["entity"] for c in cards[:4]] == [
        "number.charger_current",  # CONF_CHARGER_CURRENT_ENTITY
        "sensor.net_power",  # CONF_NET_POWER_ENTITY
        "sensor.smart_charging_solar_surplus_w",
        "sensor.smart_charging_effective_peak_limit",
    ]
    assert len(cards) == 5
    markdown_card = cards[4]
    assert markdown_card["type"] == "markdown"
    assert "states('sensor.solar_forecast_tomorrow')" in markdown_card["content"]


def test_power_flow_section_omits_the_markdown_card_when_solar_forecast_is_unset():
    entry = _entry()
    assert CONF_SOLAR_FORECAST_ENTITY not in entry.data
    cards = _cards(build_dashboard_config(entry), "Power flow")

    assert len(cards) == 4


def test_power_flow_section_omits_the_markdown_card_when_solar_forecast_is_the_empty_string():
    entry = _entry(**{CONF_SOLAR_FORECAST_ENTITY: ""})
    cards = _cards(build_dashboard_config(entry), "Power flow")

    assert len(cards) == 4


def test_runtime_settings_section_has_the_mode_gate_and_the_auto_entities_card():
    cards = _cards(build_dashboard_config(_entry()), "Runtime settings")

    assert len(cards) == 2
    mode_gate_card, auto_entities_card = cards

    # T8 (2026-08-13 addendum): the mode selector only makes sense under the Manual profile
    # (system-overview.md's glossary already scopes it that way) -- gated via the entities
    # card's own `visibility` key, HA's native idiom in a `sections` view. The condition schema
    # keys the entity as `entity`, NOT `entity_id` (that's the automation/script condition
    # schema instead) -- a missing `entity` key resolves the checked state as `unavailable` and
    # the card silently never renders, so this is asserted explicitly rather than left to a
    # dict-equality mirror of the implementation.
    assert mode_gate_card["type"] == "entities"
    assert mode_gate_card["entities"] == ["select.smart_charging_mode"]
    assert mode_gate_card["visibility"] == [
        {"condition": "state", "entity": "select.smart_charging_profile", "state": "Manual"}
    ]
    assert "entity_id" not in mode_gate_card["visibility"][0]

    assert auto_entities_card["type"] == "custom:auto-entities"
    assert auto_entities_card["filter"]["include"] == [{"label": LABEL_SC_RUNTIME}]
    # Regression guard for the deliberate deviation from the 2026-07-08 design doc's sketch
    # (Decision 1's own reasoning: no entity is ever labelled sc_install, so that clause can
    # never match anything). The two excludes here are different, legitimate ones: mode is
    # rendered by the conditional card above instead (T8), and the nine departure-time
    # entities move to the deadline tab instead (T9) -- neither should duplicate here.
    assert auto_entities_card["filter"]["exclude"] == [
        {"entity_id": "select.smart_charging_mode"},
        {"domain": "time"},
    ]


def test_deadline_view_has_one_section_with_a_time_domain_auto_entities_card():
    view = _view(build_dashboard_config(_entry()), "deadline")

    assert len(view["sections"]) == 1
    section = view["sections"][0]
    cards = section["cards"]
    assert len(cards) == 1
    card = cards[0]
    assert card["type"] == "custom:auto-entities"
    assert card["filter"]["include"] == [{"label": LABEL_SC_RUNTIME, "domain": "time"}]
    assert "exclude" not in card["filter"]
    assert card["show_empty"] is False


async def test_register_dashboard_writes_the_yaml_file_and_the_panel(hass, tmp_path):
    assert await async_setup_component(hass, "lovelace", {})
    entry = _entry()

    await async_register_dashboard(hass, entry)

    lovelace_data = hass.data[lovelace.LOVELACE_DATA]
    dashboard = lovelace_data.dashboards[DASHBOARD_URL_PATH]
    assert dashboard.path == str(tmp_path / DASHBOARD_FILENAME)

    on_disk = yaml.safe_load((tmp_path / DASHBOARD_FILENAME).read_text(encoding="utf-8"))
    assert on_disk == build_dashboard_config(entry)

    panel = hass.data[frontend.DATA_PANELS][DASHBOARD_URL_PATH]
    assert panel.config["mode"] == "yaml"
    assert panel.sidebar_title == "Smart Charging"


async def test_register_dashboard_twice_does_not_raise_or_duplicate(hass):
    assert await async_setup_component(hass, "lovelace", {})
    entry = _entry()

    await async_register_dashboard(hass, entry)
    panel_count_after_first = len(hass.data[frontend.DATA_PANELS])

    await async_register_dashboard(hass, entry)  # simulates an ADR-0008 reload

    assert len(hass.data[frontend.DATA_PANELS]) == panel_count_after_first
    assert DASHBOARD_URL_PATH in hass.data[frontend.DATA_PANELS]


async def test_unregister_dashboard_removes_the_panel(hass):
    assert await async_setup_component(hass, "lovelace", {})
    entry = _entry()
    await async_register_dashboard(hass, entry)

    await async_unregister_dashboard(hass, entry)

    assert DASHBOARD_URL_PATH not in hass.data[frontend.DATA_PANELS]
    assert DASHBOARD_URL_PATH not in hass.data[lovelace.LOVELACE_DATA].dashboards


async def test_unregister_dashboard_when_nothing_was_registered_does_not_raise(hass):
    assert await async_setup_component(hass, "lovelace", {})
    entry = _entry()

    await async_unregister_dashboard(hass, entry)  # must not raise
