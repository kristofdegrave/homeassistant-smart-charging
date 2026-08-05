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

Only `strings.json`/`translations/en.json` are checked, not `translations/nl.json` -- HA
falls back to `en` for missing keys, and requiring every locale to stay fully translated
would block adding a new locale incrementally.
"""

import json
from pathlib import Path

from custom_components.smart_charging import const

COMPONENT_DIR = Path(__file__).parent.parent / "custom_components" / "smart_charging"

EMITTED_ERROR_CODES = {getattr(const, name) for name in dir(const) if name.startswith("ERROR_")}


def _config_error_keys(relative_path: str) -> set[str]:
    with open(COMPONENT_DIR / relative_path, encoding="utf-8") as f:
        data = json.load(f)
    return set(data["config"]["error"].keys())


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
