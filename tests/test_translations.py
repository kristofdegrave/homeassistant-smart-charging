"""strings.json/translations completeness guard (T6.3).

Plain pytest, no HA harness needed (ADR-0009) -- these are pure data-file checks, plus
introspection of the entities' own `_attr_translation_key` literals. Catches two regression
classes that `python -m script.hassfest` (a strings.json *schema* check, run only as a GitHub
Action) does not: (1) strings.json/en.json/nl.json drifting apart (missing keys or a
non-identical English copy), and (2) an entity `_attr_translation_key` with no matching
`entity.<platform>.<key>.name`.

Config-flow step/field label parity (the config-flow-specific regression class this module
used to also cover) now lives in tests/test_config_flow_translations.py instead (plan T12) --
its dynamic per-step-id parity checks, discovered from config_flow.py's own tables and schema
fragments, superseded this module's single hardcoded test against the three flat blocks
(config.step.user/reconfigure, options.step.init) the guided config flow's tables replaced.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from custom_components.smart_charging import number, select, sensor, switch
from custom_components.smart_charging import time as time_platform

COMPONENT_DIR = Path(__file__).parent.parent / "custom_components" / "smart_charging"


def _load(name: str) -> dict:
    return json.loads((COMPONENT_DIR / name).read_text(encoding="utf-8"))


def _flatten(d: dict, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    for k, v in d.items():
        p = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            keys |= _flatten(v, p)
        else:
            keys.add(p)
    return keys


def test_strings_json_and_en_json_are_identical():
    """translations/en.json is the English strings.json's own translations copy -- the
    two must never drift (this project keeps them byte-for-byte identical)."""
    assert _load("strings.json") == _load("translations/en.json")


def test_nl_json_has_the_same_keys_as_en_json():
    """No partial translation coverage: every key en.json has, nl.json has too (and
    vice versa)."""
    en_keys = _flatten(_load("translations/en.json"))
    nl_keys = _flatten(_load("translations/nl.json"))
    assert en_keys == nl_keys


# test_every_config_flow_field_has_a_label is removed here, not updated in place -- see the
# module docstring above for why (superseded by test_config_flow_translations.py, plan T12).


def test_every_entity_translation_key_has_a_name():
    """Every `_attr_translation_key` literal set by an entity class has a matching
    entity.<platform>.<key>.name in strings.json (and, by the two tests above, in
    en.json/nl.json too)."""
    strings = _load("strings.json")
    entity = strings["entity"]

    # select.py
    assert "profile" in entity["select"]
    assert "mode" in entity["select"]

    # sensor.py
    sensor_keys = (
        "status",
        "charger_status",
        "active_mode",
        "monthly_peak_kw",
        "effective_peak_limit",
        "active_soc_limit",
        # ADR-0031 config-mirror sensors (T1-T4, #888) -- the full 35-row mapping table's
        # object_id_suffix values, matching sensor.py's mirror_specs list exactly.
        "solar_available",
        "captar_available",
        "deadline_available",
        "notifications_available",
        "smoothing_window",
        "grid_supply_ceiling_a",
        "grid_safety_offset_a",
        "nominal_voltage_v",
        "min_current_a",
        "max_current_a",
        "safety_margin_w",
        "max_peak_kw",
        "peak_floor_kw",
        "peak_grace_min",
        "captar_cooldown_min",
        "power_respect_peak",
        "power_cooldown_min",
        "reminder_lead_h",
        "deadline_notice_enabled",
        "plug_in_reminder_enabled",
        "evening_prompt_enabled",
        "evening_prompt_time",
        "ev_battery_capacity_kwh",
        "solar_start_threshold_w",
        "solar_hold_min",
        "solar_cooldown_min",
        "solar_restart_debounce_min",
        "solar_only_start_threshold_w",
        "solar_only_hold_min",
        "solar_only_rounding_strategy",
        "solar_only_rounding_midpoint_pct",
        "max_solar_soc",
        "solar_step_pp",
        "solar_step_threshold_pp",
        "solar_forecast_threshold_kwh",
    )
    for key in sensor_keys:
        assert key in entity["sensor"]

    # sensor.py: charger_status is an ENUM device_class -- its translated state values must
    # match its `options` exactly, or a dropped/renamed state key silently falls back to the
    # raw untranslated value in the UI (ADR-0034's entire reason for choosing ENUM).
    charger_status_sensor = sensor.ChargerStatusSensor(
        entry_id="abc", coordinator=SimpleNamespace(data=None)
    )
    assert set(entity["sensor"]["charger_status"]["state"]) == set(charger_status_sensor.options)

    # switch.py
    assert "home_day" in entity["switch"]

    # number.py
    assert "target_current" in entity["number"]
    assert "soc_limit_override" in entity["number"]

    # time.py: nine departure entities, one per DAY_OF_WEEK_DEFAULTS/OVERRIDE_DEFAULTS suffix
    for suffix, _default in (*time_platform.DAY_OF_WEEK_DEFAULTS, *time_platform.OVERRIDE_DEFAULTS):
        assert f"departure_{suffix}" in entity["time"]

    # Guard against the reverse gap too: every platform module actually referenced above
    # is imported (an unused-import lint failure would mean this test silently checked
    # nothing for that module).
    assert number and select and sensor and switch and time_platform
