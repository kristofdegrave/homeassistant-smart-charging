"""Runtime dashboard generation and registration (C5, #601, ADR-0022 Option C).

Builds a locked, YAML-mode Lovelace dashboard from the config entry's mapped entities plus
`entity-catalog.md`'s runtime-classified owned entities (via the `sc_runtime` label, `entity.py`),
regenerated and re-registered on every `async_setup_entry` per ADR-0022.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from homeassistant.components import frontend, lovelace
from homeassistant.components.lovelace.const import (
    CONF_REQUIRE_ADMIN,
    CONF_SHOW_IN_SIDEBAR,
    CONF_TITLE,
    MODE_YAML,
)
from homeassistant.components.lovelace.dashboard import CONF_FILENAME, LovelaceYAML
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ICON, CONF_MODE
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
    OWNED_SUFFIX_ACTIVE_SOC_LIMIT,
    OWNED_SUFFIX_MODE,
    OWNED_SUFFIX_PEAK_HEADROOM_A,
    OWNED_SUFFIX_PROFILE,
    OWNED_SUFFIX_SOLAR_SURPLUS_W,
    OWNED_SUFFIX_TIME_TO_FULL,
    PROFILE_MANUAL,
)

_TITLE = "Smart Charging"

# "active_mode"/"effective_peak_limit" have no OWNED_SUFFIX_* constant (sensor.py itself pins
# them as bare literals) -- consistent with that existing precedent, not a new deviation.
_ACTIVE_SOC_LIMIT_ENTITY = f"sensor.smart_charging_{OWNED_SUFFIX_ACTIVE_SOC_LIMIT}"
_ACTIVE_MODE_ENTITY = "sensor.smart_charging_active_mode"
_EFFECTIVE_PEAK_LIMIT_ENTITY = "sensor.smart_charging_effective_peak_limit"
_MODE_ENTITY = f"select.smart_charging_{OWNED_SUFFIX_MODE}"
_PEAK_HEADROOM_ENTITY = f"sensor.smart_charging_{OWNED_SUFFIX_PEAK_HEADROOM_A}"
_PROFILE_ENTITY = f"select.smart_charging_{OWNED_SUFFIX_PROFILE}"
_SOLAR_SURPLUS_ENTITY = f"sensor.smart_charging_{OWNED_SUFFIX_SOLAR_SURPLUS_W}"
_TIME_TO_FULL_ENTITY = f"sensor.smart_charging_{OWNED_SUFFIX_TIME_TO_FULL}"


def _tile(entity_id: str) -> dict:
    return {"type": "tile", "entity": entity_id}


def _charging_status_cards(entry: ConfigEntry) -> list[dict]:
    cards = [_tile(entry.data[CONF_CHARGER_STATUS_ENTITY])]
    ev_soc_entity = entry.data.get(CONF_EV_SOC_ENTITY)
    if ev_soc_entity:
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
    if solar_forecast_entity:
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
    # T8 (2026-08-13 addendum): select.smart_charging_mode only has an effect under the
    # Manual profile (system-overview.md's glossary already scopes it that way; Auto's own E2
    # drives dispatch instead) -- gated on its own conditional card rather than left editable
    # unconditionally in the label-driven list below.
    mode_gate_card = {
        "type": "conditional",
        "conditions": [
            {"condition": "state", "entity_id": _PROFILE_ENTITY, "state": PROFILE_MANUAL}
        ],
        "card": {"type": "entities", "entities": [_MODE_ENTITY]},
    }
    return [
        mode_gate_card,
        {
            "type": "custom:auto-entities",
            "card": {"type": "entities", "title": "Runtime settings"},
            # Deliberately no `exclude: label: sc_install` clause here (present in the
            # 2026-07-08-runtime-dashboard-design.md sketch) -- per that doc's own Decision 1
            # reasoning, no entity is ever labelled sc_install, so that clause can never match
            # anything. This exclude is a different, legitimate one: mode is rendered by the
            # conditional card above instead, so the auto-entities list must not duplicate it.
            "filter": {
                "include": [{"label": LABEL_SC_RUNTIME}],
                "exclude": [{"entity_id": _MODE_ENTITY}],
            },
            "sort": {"method": "friendly_name"},
        },
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
    config = build_dashboard_config(entry)
    yaml_path = _package_dir() / DASHBOARD_FILENAME

    def _write() -> None:
        # Atomic: write to a same-directory temp file, then rename -- os.replace is atomic on
        # both POSIX and Windows, so the frontend never observes a partially-written file.
        tmp_path = yaml_path.with_suffix(f"{yaml_path.suffix}.tmp")
        tmp_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        os.replace(tmp_path, yaml_path)

    await hass.async_add_executor_job(_write)

    # Guards `update=` on the panel registration below (frontend.DATA_PANELS is what that
    # actually protects) -- `lovelace_data.dashboards` can diverge from it (e.g. a partially
    # failed prior setup).
    already_registered = DASHBOARD_URL_PATH in hass.data.get(frontend.DATA_PANELS, {})
    lovelace_data = hass.data[lovelace.LOVELACE_DATA]
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
