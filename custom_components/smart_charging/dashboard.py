"""Runtime dashboard generation and registration (C5, #601, ADR-0022 Option C).

Builds a locked, YAML-mode Lovelace dashboard from the config entry's mapped entities plus
`entity-catalog.md`'s runtime-classified owned entities (via the `sc_runtime` label, `entity.py`),
regenerated and re-registered on every `async_setup_entry` per ADR-0022.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
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
    CONF_EV_SOC_ENTITY,
    CONF_NET_POWER_ENTITY,
    CONF_SOLAR_AVAILABLE,
    CONF_SOLAR_FORECAST_ENTITY,
    DASHBOARD_FILENAME,
    DASHBOARD_ICON,
    DASHBOARD_URL_PATH,
    DEFAULT_SOLAR_AVAILABLE,
    KEY_DASHBOARD_SECTION_CHARGING_STATUS,
    KEY_DASHBOARD_SECTION_DEPARTURE_TIMES,
    KEY_DASHBOARD_SECTION_POWER_FLOW,
    KEY_DASHBOARD_SECTION_RUNTIME_SETTINGS,
    KEY_DASHBOARD_VIEW_DEADLINE,
    LABEL_SC_RUNTIME,
    OWNED_SUFFIX_ACTIVE_SOC_LIMIT,
    OWNED_SUFFIX_CHARGER_STATUS,
    OWNED_SUFFIX_MODE,
    OWNED_SUFFIX_PEAK_HEADROOM_A,
    OWNED_SUFFIX_PROFILE,
    OWNED_SUFFIX_SOLAR_SURPLUS_W,
    OWNED_SUFFIX_TIME_TO_FULL,
    PRODUCT_NAME,
    PROFILE_MANUAL,
)
from .system_text import async_get_system_text

# The product name -- deliberately never translated (NF8 AC1): it is a brand name, not
# system-composed text, the same carve-out notification_manager.py's own `_PROMPT_TITLE`
# takes. `const.PRODUCT_NAME` is the one literal both modules read, not two independent ones.
_TITLE = PRODUCT_NAME

# NF8's English fallback for the headings below -- also `build_dashboard_config`'s default
# when no `headings` is given, matching NF8 AC2's "English otherwise" for a caller that has
# no `hass` to fetch a system language from (every existing unit test here). Kept as its own
# dict rather than duplicating strings.json's English copy inline at each use below, so this
# fallback and the translated path share one source of the 5 keys.
EN_HEADINGS: Mapping[str, str] = {
    KEY_DASHBOARD_SECTION_CHARGING_STATUS: "Charging status",
    KEY_DASHBOARD_SECTION_POWER_FLOW: "Power flow",
    KEY_DASHBOARD_SECTION_RUNTIME_SETTINGS: "Runtime settings",
    KEY_DASHBOARD_VIEW_DEADLINE: "Deadline",
    KEY_DASHBOARD_SECTION_DEPARTURE_TIMES: "Departure times",
}

# Issue #1009. Owned entities use `has_entity_name` against a device called "Smart Charging"
# (entity.py), so every friendly name is "Smart Charging " + the entity name -- 15 characters of
# constant prefix before anything distinguishing. A tile defaults to half a section's width,
# which across a three-section view left about 14 characters and rendered "Smart Charging L...".
#
# Width rather than a per-tile `name:` override: these names are translated (translations/nl.json
# carries Dutch for every owned entity), and hardcoding short English strings in this file would
# regress a translated install to English tile labels. Width costs vertical space and costs no
# correctness.
#
# `_FULL_SECTION_COLUMNS` is the full 12-column span of one section. `_MAX_VIEW_COLUMNS` widens
# the sections themselves, which is what reaches the auto-entities cards -- those render entity
# *rows* and already span their section, so tile width does nothing for them.
#
# A view-level `max_columns` rather than `column_span` on each section: a sections view defaults
# to 4 columns, so spanning each section across 2 of them lays out as 2 + 1 on the overview,
# leaving half the second row empty -- and on a viewport that fits exactly 3 columns it degrades
# to one section per row. Capping the view at 2 columns states "sections should be wide" once,
# and lays out the same way at every viewport.
_FULL_SECTION_COLUMNS = 12
_MAX_VIEW_COLUMNS = 2


def _full_width() -> dict:
    """A new `grid_options` dict per card.

    Deliberately a function, not a shared module-level dict: `register_dashboard` serialises this
    config with `yaml.safe_dump`, which emits an anchor/alias pair (`&id001` / `*id001`) for any
    object that appears more than once by identity. HA's loader resolves those correctly, but the
    file is the user-facing artifact of a YAML-mode dashboard -- one a user may read, copy a card
    out of, or hand to someone for support -- and a card whose width is `*id001` is not something
    anyone can act on. A shared dict would also make any future per-card width tweak silently
    mutate every other card.
    """
    return {"columns": _FULL_SECTION_COLUMNS}


# Bare string, not `homeassistant.const.Platform.TIME` -- that's a StrEnum member, and
# yaml.safe_dump (below) raises RepresenterError on it; a plain domain string is what
# auto-entities' filter schema expects anyway.
_TIME_DOMAIN = "time"

# "active_mode"/"effective_peak_limit"/"status" have no OWNED_SUFFIX_* constant (sensor.py
# itself pins them as bare literals) -- consistent with that existing precedent, not a new
# deviation.
_ACTIVE_SOC_LIMIT_ENTITY = f"sensor.smart_charging_{OWNED_SUFFIX_ACTIVE_SOC_LIMIT}"
_ACTIVE_MODE_ENTITY = "sensor.smart_charging_active_mode"
_CHARGER_STATUS_ENTITY = f"sensor.smart_charging_{OWNED_SUFFIX_CHARGER_STATUS}"
_EFFECTIVE_PEAK_LIMIT_ENTITY = "sensor.smart_charging_effective_peak_limit"
_MODE_ENTITY = f"select.smart_charging_{OWNED_SUFFIX_MODE}"
_PEAK_HEADROOM_ENTITY = f"sensor.smart_charging_{OWNED_SUFFIX_PEAK_HEADROOM_A}"
_PROFILE_ENTITY = f"select.smart_charging_{OWNED_SUFFIX_PROFILE}"
_SOLAR_SURPLUS_ENTITY = f"sensor.smart_charging_{OWNED_SUFFIX_SOLAR_SURPLUS_W}"
_STATUS_ENTITY = "sensor.smart_charging_status"
_TIME_TO_FULL_ENTITY = f"sensor.smart_charging_{OWNED_SUFFIX_TIME_TO_FULL}"


def _tile(entity_id: str) -> dict:
    return {"type": "tile", "entity": entity_id, "grid_options": _full_width()}


def _charging_status_cards(entry: ConfigEntry) -> list[dict]:
    # sensor.smart_charging_status (ADR-0007's Fault/OK health readout, R19 AC1/UC11,
    # #1349) leads the section, on every installation whatever the capabilities: a fault
    # gates the charger to 0 A and can make a required reading unavailable, and this tile
    # is what tells the household *why*, rather than leaving them only the 0 A current and
    # the unavailable reading to interpret.
    cards = [_tile(_STATUS_ENTITY), _tile(_CHARGER_STATUS_ENTITY)]
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
    ]
    # ADR-0028/R19 AC4: SolarSurplusSensor is registry-disabled when solar_available is off,
    # so its static tile must be omitted here too, or a no-solar install's dashboard shows a
    # permanently-unavailable tile (#814).
    if entry.data.get(CONF_SOLAR_AVAILABLE, DEFAULT_SOLAR_AVAILABLE):
        cards.append(_tile(_SOLAR_SURPLUS_ENTITY))
    cards.append(_tile(_EFFECTIVE_PEAK_LIMIT_ENTITY))
    solar_forecast_entity = entry.data.get(CONF_SOLAR_FORECAST_ENTITY)
    if solar_forecast_entity:
        cards.append(
            {
                "type": "markdown",
                "grid_options": _full_width(),
                "content": (
                    "\U0001f52e **{{ states('" + solar_forecast_entity + "') }} kWh** "
                    "forecast for tomorrow."
                ),
            }
        )
    return cards


def _runtime_settings_cards(headings: Mapping[str, str]) -> list[dict]:
    # select.smart_charging_mode only has an effect under the
    # Manual profile (system-overview.md's glossary already scopes it that way; Auto's own E2
    # drives dispatch instead) -- gated via the entities card's own `visibility` key rather than
    # a wrapping `type: conditional` card, HA's more native idiom for a single gated card in a
    # `sections` view. The Lovelace condition schema (both `visibility` and `conditional`) keys
    # the entity as `entity`, NOT `entity_id` (that key belongs to the automation/script
    # condition schema instead) -- get this wrong and the card silently never renders, since a
    # missing `entity` key resolves the checked state as `unavailable`.
    mode_gate_card = {
        "type": "entities",
        "entities": [_MODE_ENTITY],
        "grid_options": _full_width(),
        "visibility": [{"condition": "state", "entity": _PROFILE_ENTITY, "state": PROFILE_MANUAL}],
    }
    return [
        mode_gate_card,
        {
            "type": "custom:auto-entities",
            "card": {
                "type": "entities",
                "title": headings[KEY_DASHBOARD_SECTION_RUNTIME_SETTINGS],
            },
            "grid_options": _full_width(),
            # Deliberately no `exclude: label: sc_install` clause here: LABEL_SC_RUNTIME is
            # the only label this integration applies to an owned entity, so no entity is ever
            # labelled sc_install and such a clause could never match anything. The two
            # excludes below are different, legitimate ones: mode is rendered by the gated card
            # above instead, and the nine departure-time entities move to the deadline tab
            # instead -- neither should duplicate here.
            "filter": {
                "include": [{"label": LABEL_SC_RUNTIME}],
                "exclude": [{"entity_id": _MODE_ENTITY}, {"domain": _TIME_DOMAIN}],
            },
            "sort": {"method": "friendly_name"},
        },
    ]


def _deadline_cards() -> list[dict]:
    # Still label-driven, not a hardcoded list, so a newly added runtime entity appears
    # here without editing this file -- narrowed to the time domain via the same include filter
    # object (auto-entities ANDs the keys within one include entry). `show_empty: False` keeps
    # the tab from rendering a visibly-empty card now that the departure-time entities'
    # `sc_runtime` label is conditionally absent when the deadline capability is off (#674).
    return [
        {
            "type": "custom:auto-entities",
            "card": {"type": "entities"},
            "grid_options": _full_width(),
            "filter": {"include": [{"label": LABEL_SC_RUNTIME, "domain": _TIME_DOMAIN}]},
            "sort": {"method": "friendly_name"},
            "show_empty": False,
        }
    ]


def build_dashboard_config(entry: ConfigEntry, headings: Mapping[str, str] | None = None) -> dict:
    """Return the full Lovelace `views` config for the runtime dashboard (ADR-0022).

    Two views -- HA renders `views` of length >1 as tabs natively, so no new registration
    mechanism is needed beyond ADR-0022's Option C.

    `headings` (NF8): the view/card/section titles, keyed by the `KEY_DASHBOARD_*` constants
    -- `async_register_dashboard` passes HA's system-language translations; a caller with no
    `hass` to fetch them from (every test in this module) gets `EN_HEADINGS`, NF8 AC2's
    "English otherwise" default. The product name (`_TITLE`) is never in this dict -- it is
    never translated (NF8 AC1).
    """
    headings = headings if headings is not None else EN_HEADINGS
    return {
        "title": _TITLE,
        "views": [
            {
                "title": _TITLE,
                "path": "overview",
                "type": "sections",
                "max_columns": _MAX_VIEW_COLUMNS,
                "sections": [
                    {
                        "type": "grid",
                        "title": headings[KEY_DASHBOARD_SECTION_CHARGING_STATUS],
                        "cards": _charging_status_cards(entry),
                    },
                    {
                        "type": "grid",
                        "title": headings[KEY_DASHBOARD_SECTION_POWER_FLOW],
                        "cards": _power_flow_cards(entry),
                    },
                    {
                        "type": "grid",
                        "title": headings[KEY_DASHBOARD_SECTION_RUNTIME_SETTINGS],
                        "cards": _runtime_settings_cards(headings),
                    },
                ],
            },
            {
                "title": headings[KEY_DASHBOARD_VIEW_DEADLINE],
                "path": "deadline",
                "type": "sections",
                "max_columns": _MAX_VIEW_COLUMNS,
                "sections": [
                    {
                        "type": "grid",
                        "title": headings[KEY_DASHBOARD_SECTION_DEPARTURE_TIMES],
                        "cards": _deadline_cards(),
                    },
                ],
            },
        ],
    }


def _package_dir() -> Path:
    return Path(__file__).parent


async def async_register_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Write the generated YAML and register/update the locked dashboard panel (ADR-0022)."""
    headings = await async_get_system_text(hass)
    config = build_dashboard_config(entry, headings)
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
