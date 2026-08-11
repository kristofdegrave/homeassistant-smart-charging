"""Runtime dashboard generation and registration (C5, #601, ADR-0022 Option C).

Builds a locked, YAML-mode Lovelace dashboard from the config entry's mapped entities plus
`entity-catalog.md`'s runtime-classified owned entities (via the `sc_runtime` label, `entity.py`),
regenerated and re-registered on every `async_setup_entry` per ADR-0022.
"""

from __future__ import annotations

from pathlib import Path

from homeassistant.components import frontend, lovelace
from homeassistant.components.lovelace.const import (
    CONF_ICON,
    CONF_MODE,
    CONF_REQUIRE_ADMIN,
    CONF_SHOW_IN_SIDEBAR,
    CONF_TITLE,
    MODE_YAML,
)
from homeassistant.components.lovelace.dashboard import CONF_FILENAME, LovelaceYAML
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_CHARGER_CURRENT_ENTITY,
    CONF_CHARGER_STATUS_ENTITY,
    CONF_EV_SOC_ENTITY,
    CONF_NET_POWER_ENTITY,
    CONF_SOLAR_FORECAST_ENTITY,
    DASHBOARD_FILENAME,
    DASHBOARD_ICON,
    DASHBOARD_URL_PATH,
    LABEL_SC_RUNTIME,
)

_TITLE = "Smart Charging"

_ACTIVE_SOC_LIMIT_ENTITY = "sensor.smart_charging_active_soc_limit"
_ACTIVE_MODE_ENTITY = "sensor.smart_charging_active_mode"
_EFFECTIVE_PEAK_LIMIT_ENTITY = "sensor.smart_charging_effective_peak_limit"
_PEAK_HEADROOM_ENTITY = "sensor.smart_charging_peak_headroom_a"
_PROFILE_ENTITY = "select.smart_charging_profile"
_SOLAR_SURPLUS_ENTITY = "sensor.smart_charging_solar_surplus_w"
_TIME_TO_FULL_ENTITY = "sensor.smart_charging_time_to_full"


def _tile(entity_id: str) -> dict:
    return {"type": "tile", "entity": entity_id}


def _charging_status_cards(entry: ConfigEntry) -> list[dict]:
    cards = [_tile(entry.data[CONF_CHARGER_STATUS_ENTITY])]
    ev_soc_entity = entry.data.get(CONF_EV_SOC_ENTITY)
    if ev_soc_entity is not None:
        cards.append(_tile(ev_soc_entity))
    cards += [
        _tile(_PROFILE_ENTITY),
        _tile(_ACTIVE_MODE_ENTITY),
        _tile(_ACTIVE_SOC_LIMIT_ENTITY),
        _tile(_TIME_TO_FULL_ENTITY),
        _tile(_PEAK_HEADROOM_ENTITY),
    ]
    return cards


def _power_flow_cards(entry: ConfigEntry) -> list[dict]:
    cards = [
        _tile(entry.data[CONF_CHARGER_CURRENT_ENTITY]),
        _tile(entry.data[CONF_NET_POWER_ENTITY]),
        _tile(_SOLAR_SURPLUS_ENTITY),
        _tile(_EFFECTIVE_PEAK_LIMIT_ENTITY),
    ]
    solar_forecast_entity = entry.data.get(CONF_SOLAR_FORECAST_ENTITY)
    if solar_forecast_entity is not None:
        cards.append(
            {
                "type": "markdown",
                "content": (
                    "\U0001f52e **{{ states('" + solar_forecast_entity + "') }} kWh** "
                    "forecast for tomorrow."
                ),
            }
        )
    return cards


def _runtime_settings_cards() -> list[dict]:
    # Deliberately no `exclude: label: sc_install` clause here (present in the
    # 2026-07-08-runtime-dashboard-design.md sketch) -- per that doc's own Decision 1
    # reasoning, no entity is ever labelled sc_install, so the clause can never match anything.
    return [
        {
            "type": "custom:auto-entities",
            "card": {"type": "entities", "title": "Runtime settings"},
            "filter": {"include": [{"label": LABEL_SC_RUNTIME}]},
            "sort": {"method": "friendly_name"},
        }
    ]


def build_dashboard_config(entry: ConfigEntry) -> dict:
    """Return the full Lovelace `views` config for the runtime dashboard (ADR-0022)."""
    return {
        "title": _TITLE,
        "views": [
            {
                "title": _TITLE,
                "path": DASHBOARD_URL_PATH,
                "type": "sections",
                "sections": [
                    {
                        "type": "grid",
                        "title": "Charging status",
                        "cards": _charging_status_cards(entry),
                    },
                    {
                        "type": "grid",
                        "title": "Power flow",
                        "cards": _power_flow_cards(entry),
                    },
                    {
                        "type": "grid",
                        "title": "Runtime settings",
                        "cards": _runtime_settings_cards(),
                    },
                ],
            }
        ],
    }


def _package_dir() -> Path:
    return Path(__file__).parent


async def async_register_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Write the generated YAML and register/update the locked dashboard panel (ADR-0022)."""
    import yaml as yaml_lib

    config = build_dashboard_config(entry)
    yaml_path = _package_dir() / DASHBOARD_FILENAME

    def _write() -> None:
        yaml_path.write_text(yaml_lib.safe_dump(config, sort_keys=False), encoding="utf-8")

    await hass.async_add_executor_job(_write)

    lovelace_data = hass.data[lovelace.LOVELACE_DATA]
    already_registered = DASHBOARD_URL_PATH in lovelace_data.dashboards
    lovelace_data.dashboards[DASHBOARD_URL_PATH] = LovelaceYAML(
        hass,
        DASHBOARD_URL_PATH,
        {
            CONF_MODE: MODE_YAML,
            CONF_FILENAME: str(yaml_path),  # absolute -- hass.config.path() leaves it untouched
            CONF_TITLE: _TITLE,
            CONF_ICON: DASHBOARD_ICON,
            CONF_REQUIRE_ADMIN: False,
            CONF_SHOW_IN_SIDEBAR: True,
        },
    )
    frontend.async_register_built_in_panel(
        hass,
        lovelace.DOMAIN,
        frontend_url_path=DASHBOARD_URL_PATH,
        sidebar_title=_TITLE,
        sidebar_icon=DASHBOARD_ICON,
        show_in_sidebar=True,
        require_admin=False,
        config={CONF_MODE: MODE_YAML},
        update=already_registered,
    )


async def async_unregister_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Tear down the dashboard panel registered by `async_register_dashboard`."""
    frontend.async_remove_panel(hass, DASHBOARD_URL_PATH, warn_if_unknown=False)
    lovelace_data = hass.data.get(lovelace.LOVELACE_DATA)
    if lovelace_data is not None:
        lovelace_data.dashboards.pop(DASHBOARD_URL_PATH, None)
