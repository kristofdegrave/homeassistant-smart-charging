"""hacs.json declared-minimum guard (NF6).

Plain pytest, no HA harness needed (ADR-0009) -- this is a pure data-file check, like
tests/test_translations.py's strings.json guard. NF6 requires the declared minimum to be true:
the integration behaves as `docs/analysis/requirements.md` states on that release and on the
stable release current when a version is published (#1031). This test does not re-derive the
floor from the code -- it pins `hacs.json` to the minimum #1031 established
(`dashboard.py`'s `grid_options`, added in Home Assistant 2024.11, is the binding feature).
Re-derive and update both together when the shipped code adopts a still-newer HA feature, the
same way #1031 found the previous, untrue value.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# The derived minimum (#1031): the latest Home Assistant release introducing any feature the
# shipped code uses. `dashboard.py`'s `grid_options` (every card) is the binding constraint --
# see #1031 for the full evidence table and its primary sources.
_DERIVED_HA_MINIMUM = "2024.11.0"


def _load_hacs_json() -> dict:
    return json.loads((REPO_ROOT / "hacs.json").read_text(encoding="utf-8"))


def test_should_declare_the_derived_ha_minimum_when_hacs_json_is_read():
    # Arrange
    hacs_manifest = _load_hacs_json()

    # Act
    declared_minimum = hacs_manifest["homeassistant"]

    # Assert
    assert declared_minimum == _DERIVED_HA_MINIMUM
