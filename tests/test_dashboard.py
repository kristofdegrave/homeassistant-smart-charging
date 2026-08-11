"""Tests for the runtime dashboard's generated Lovelace config and registration (C5, #601)."""

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


def _cards(config, section_title):
    (view,) = config["views"]
    for section in view["sections"]:
        if section["title"] == section_title:
            return section["cards"]
    raise AssertionError(f"no section titled {section_title!r}")


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
    assert cards[4]["type"] == "markdown"


def test_power_flow_section_omits_the_markdown_card_when_solar_forecast_is_unset():
    entry = _entry()
    assert CONF_SOLAR_FORECAST_ENTITY not in entry.data
    cards = _cards(build_dashboard_config(entry), "Power flow")

    assert len(cards) == 4


def test_runtime_settings_section_is_a_single_label_filtered_auto_entities_card():
    cards = _cards(build_dashboard_config(_entry()), "Runtime settings")

    assert len(cards) == 1
    card = cards[0]
    assert card["type"] == "custom:auto-entities"
    assert card["filter"]["include"] == [{"label": LABEL_SC_RUNTIME}]
    # Regression guard for the deliberate deviation from the 2026-07-08 design doc's sketch
    # (Decision 1's own reasoning: no entity is ever labelled sc_install, so the clause the
    # doc's YAML sketch showed can never match anything).
    assert "exclude" not in card["filter"]


async def test_register_dashboard_writes_the_yaml_file_and_the_panel(hass, tmp_path, monkeypatch):
    monkeypatch.setattr("custom_components.smart_charging.dashboard._package_dir", lambda: tmp_path)
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


async def test_register_dashboard_twice_does_not_raise_or_duplicate(hass, tmp_path, monkeypatch):
    monkeypatch.setattr("custom_components.smart_charging.dashboard._package_dir", lambda: tmp_path)
    assert await async_setup_component(hass, "lovelace", {})
    entry = _entry()

    await async_register_dashboard(hass, entry)
    panel_count_after_first = len(hass.data[frontend.DATA_PANELS])

    await async_register_dashboard(hass, entry)  # simulates an ADR-0008 reload

    assert len(hass.data[frontend.DATA_PANELS]) == panel_count_after_first
    assert DASHBOARD_URL_PATH in hass.data[frontend.DATA_PANELS]


async def test_unregister_dashboard_removes_the_panel(hass, tmp_path, monkeypatch):
    monkeypatch.setattr("custom_components.smart_charging.dashboard._package_dir", lambda: tmp_path)
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
