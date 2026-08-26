"""Regression test (issue #508): every config-flow error code the flow can emit must have
a matching `config.error` translation entry in both `strings.json` and
`translations/en.json`, so a typo'd or missing key fails a test instead of silently
rendering the raw error code as user-facing text.

Error codes are discovered dynamically from `const.py`'s `ERROR_*` constants (the module's
own single source of truth for the code strings, per issue #508's DATA_COORDINATOR/STATUS_*
sibling fixes) rather than hardcoded here, so a future `ERROR_*` constant added to const.py
without a matching translation key is caught automatically. This guarantee only covers error
codes exposed as an `ERROR_*` constant -- a code introduced as a bare literal directly in
config_flow.py (exactly the anti-pattern this file exists to close off) would not be seen.

This file also enforces the same anti-hardcoding discipline for **step and field** parity
(ADR-0027 Consequences: one `config.step.<id>` / `options.step.<id>` block per step id,
install and reconfigure sharing `config.step.*`). The step ids and each step's field set are
discovered from `config_flow.py`'s own tables and schema fragments -- the single source of
truth the dispatcher itself uses -- rather than hardcoded here, so a step added to a table
without a matching strings.json block (or a field moved to a different step without its
label following) is caught automatically.

Only `strings.json`/`translations/en.json` are checked, not `translations/nl.json` -- HA
falls back to `en` for missing keys, and requiring every locale to stay fully translated
would block adding a new locale incrementally.
"""

import json
from pathlib import Path

import pytest

from custom_components.smart_charging import config_flow as cf
from custom_components.smart_charging import const

COMPONENT_DIR = Path(__file__).parent.parent / "custom_components" / "smart_charging"

EMITTED_ERROR_CODES = {getattr(const, name) for name in dir(const) if name.startswith("ERROR_")}

_CHECKED_FILES = ("strings.json", "translations/en.json")


def _load(relative_path: str) -> dict:
    with open(COMPONENT_DIR / relative_path, encoding="utf-8") as f:
        return json.load(f)


def _config_error_keys(relative_path: str) -> set[str]:
    return set(_load(relative_path)["config"]["error"].keys())


def test_emitted_error_codes_is_non_empty():
    # Guards against the discovery mechanism silently finding nothing (a vacuously
    # passing test would defeat the point of this file).
    assert EMITTED_ERROR_CODES


def test_strings_json_has_every_emitted_error_code():
    missing = EMITTED_ERROR_CODES - _config_error_keys("strings.json")
    assert not missing, f"strings.json's config.error section is missing: {sorted(missing)}"


def test_translations_en_json_has_every_emitted_error_code():
    missing = EMITTED_ERROR_CODES - _config_error_keys("translations/en.json")
    assert not missing, f"translations/en.json's config.error section is missing: {sorted(missing)}"


# --- T12: step and field parity (guided config flow, ADR-0027 Consequences). ---


def _keys(schema) -> set[str]:
    return {str(k) for k in schema.schema}


# Step ids the config/options flows can show, discovered from the tables themselves --
# `core` is the shared entry point both install and reconfigure delegate into (ADR-0027
# point 5) and is deliberately not a CONFIG_TABLE row of its own (design, "Step ids"). Unlike
# CONFIG_TABLE, `core` IS an OPTIONS_TABLE row (the options flow's own entry point,
# async_step_init, renders no form of its own), so OPTIONS_STEP_IDS needs no such union.
CONFIG_STEP_IDS = {row.step_id for row in cf.CONFIG_TABLE} | {cf.STEP_CORE}
OPTIONS_STEP_IDS = {row.step_id for row in cf.OPTIONS_TABLE}

# Each step's field set, unioned across every schema variant it can render (mapping half +
# threshold half for the config flow) -- a field a step presents in ANY variant needs a label.
CONFIG_STEP_FIELDS = {
    cf.STEP_CORE: _keys(cf.CORE_MAPPING_SCHEMA) | _keys(cf._core_threshold_schema()),
    cf.STEP_GRID: _keys(cf.GRID_MAPPING_SCHEMA) | _keys(cf._grid_threshold_schema()),
    cf.STEP_EV_CHARGER: (
        _keys(cf.EV_CHARGER_MAPPING_SCHEMA) | _keys(cf._ev_charger_threshold_schema())
    ),
    cf.STEP_VEHICLE: _keys(cf.VEHICLE_MAPPING_SCHEMA) | _keys(cf._vehicle_threshold_schema()),
    cf.STEP_POWER: _keys(cf._power_threshold_schema()),
    cf.STEP_CAPTAR: _keys(cf._captar_threshold_schema()),
    cf.STEP_SOLAR: _keys(cf.SOLAR_MAPPING_SCHEMA) | _keys(cf._solar_threshold_schema()),
    cf.STEP_DEADLINE: _keys(cf.DEADLINE_MAPPING_SCHEMA) | _keys(cf._deadline_threshold_schema()),
    cf.STEP_NOTIFICATIONS: (
        _keys(cf.NOTIFICATIONS_MAPPING_SCHEMA) | _keys(cf._notifications_threshold_schema())
    ),
}

# The options flow's own steps are threshold-only (ADR-0027 point 4, no mapping fields); `core`
# alone also asks the control interval (UC12 1b's own carve-out -- install/reconfigure never
# ask it).
OPTIONS_STEP_FIELDS = {
    cf.STEP_CORE: _keys(cf._core_threshold_schema(include_interval=True)),
    cf.STEP_GRID: _keys(cf._grid_threshold_schema()),
    cf.STEP_EV_CHARGER: _keys(cf._ev_charger_threshold_schema()),
    cf.STEP_VEHICLE: _keys(cf._vehicle_threshold_schema()),
    cf.STEP_POWER: _keys(cf._power_threshold_schema()),
    cf.STEP_CAPTAR: _keys(cf._captar_threshold_schema()),
    cf.STEP_SOLAR: _keys(cf._solar_threshold_schema()),
    cf.STEP_DEADLINE: _keys(cf._deadline_threshold_schema()),
    cf.STEP_NOTIFICATIONS: _keys(cf._notifications_threshold_schema()),
}

# Anti-vacuity guards (matching test_emitted_error_codes_is_non_empty's own rationale above):
# a step added to a table without a matching CONFIG_STEP_FIELDS/OPTIONS_STEP_FIELDS entry
# would otherwise silently escape field parity checking in both directions.
assert set(CONFIG_STEP_FIELDS) == CONFIG_STEP_IDS
assert set(OPTIONS_STEP_FIELDS) == OPTIONS_STEP_IDS


def _assert_title_and_description(relative_path, section, step_id, block):
    """Every step block must actually be user-facing -- a block with only a `data` object
    (no title/description) would pass every field-parity check below and still render blank."""
    assert block.get("title"), f"{relative_path}'s {section}.step.{step_id} has no title"
    assert block.get("description"), (
        f"{relative_path}'s {section}.step.{step_id} has no description"
    )


@pytest.mark.parametrize("relative_path", _CHECKED_FILES)
def test_every_config_step_has_a_strings_block(relative_path):
    """ADR-0027 Consequences: one config.step.<id> block per step id the config flow can
    show, including the shared `core` block both install and reconfigure render."""
    blocks = _load(relative_path)["config"]["step"]
    missing = CONFIG_STEP_IDS - set(blocks)
    assert not missing, f"{relative_path}'s config.step is missing blocks for {missing}"
    for step_id in CONFIG_STEP_IDS:
        _assert_title_and_description(relative_path, "config", step_id, blocks[step_id])


@pytest.mark.parametrize("relative_path", _CHECKED_FILES)
def test_every_options_step_has_a_strings_block(relative_path):
    blocks = _load(relative_path)["options"]["step"]
    missing = OPTIONS_STEP_IDS - set(blocks)
    assert not missing, f"{relative_path}'s options.step is missing blocks for {missing}"
    for step_id in OPTIONS_STEP_IDS:
        _assert_title_and_description(relative_path, "options", step_id, blocks[step_id])


@pytest.mark.parametrize("relative_path", _CHECKED_FILES)
def test_every_field_a_step_presents_has_a_label_in_that_steps_block(relative_path):
    """A field moved between steps without moving its label renders as a raw key."""
    data = _load(relative_path)
    for step_id, fields in CONFIG_STEP_FIELDS.items():
        block_data = set(data["config"]["step"][step_id].get("data", {}))
        missing = fields - block_data
        assert not missing, (
            f"{relative_path}'s config.step.{step_id} is missing labels for {missing}"
        )
    for step_id, fields in OPTIONS_STEP_FIELDS.items():
        block_data = set(data["options"]["step"][step_id].get("data", {}))
        missing = fields - block_data
        assert not missing, (
            f"{relative_path}'s options.step.{step_id} is missing labels for {missing}"
        )


@pytest.mark.parametrize("relative_path", _CHECKED_FILES)
def test_no_orphaned_step_block_or_field_label(relative_path):
    """The converse -- catches the flat flow's leftovers."""
    data = _load(relative_path)

    orphaned_config_steps = set(data["config"]["step"]) - CONFIG_STEP_IDS
    assert not orphaned_config_steps, (
        f"{relative_path} has orphaned config.step blocks: {orphaned_config_steps}"
    )
    orphaned_options_steps = set(data["options"]["step"]) - OPTIONS_STEP_IDS
    assert not orphaned_options_steps, (
        f"{relative_path} has orphaned options.step blocks: {orphaned_options_steps}"
    )

    for step_id, fields in CONFIG_STEP_FIELDS.items():
        block_data = set(data["config"]["step"][step_id].get("data", {}))
        orphaned = block_data - fields
        assert not orphaned, (
            f"{relative_path}'s config.step.{step_id} has orphaned field labels: {orphaned}"
        )
    for step_id, fields in OPTIONS_STEP_FIELDS.items():
        block_data = set(data["options"]["step"][step_id].get("data", {}))
        orphaned = block_data - fields
        assert not orphaned, (
            f"{relative_path}'s options.step.{step_id} has orphaned field labels: {orphaned}"
        )


@pytest.mark.parametrize("relative_path", _CHECKED_FILES)
def test_no_field_label_carries_a_conditional_qualifier(relative_path):
    """ADR-0027 Consequences: '(required if Solar installed)'-style qualifiers are redundant
    once a field only appears when it is required, and must not contradict the new
    structure."""
    data = _load(relative_path)
    banned_phrases = ("required if", "required when")
    for section in ("config", "options"):
        for step_id, block in data[section]["step"].items():
            for field, label in block.get("data", {}).items():
                lowered = label.lower()
                assert not any(phrase in lowered for phrase in banned_phrases), (
                    f"{relative_path}'s {section}.step.{step_id}.data.{field} still carries "
                    f"a conditional qualifier: {label!r}"
                )
