"""Shared pytest fixtures for the Smart Charging test suite.

Per ADR-0009 (Option A), the pure mode/engine/profile logic under ``tests/modes/``,
``tests/engines/``, and ``tests/profiles/`` runs as plain pytest with no HA dependency.
Every other test (adapters, plus the root-level config-flow / coordinator / init tests,
and any other file listed in ``_PURE_FILES`` below, root-level or not) is an HA-harness
test that needs the custom integration loaded. The autouse fixture below applies
``enable_custom_integrations`` to the HA-harness tests only, keeping the pure dirs/files
HA-free so they collect without phcc.

``test_coordinator_cycle.py`` is a deliberate root-level exception (ADR-0012): it tests
``coordinator_cycle.py``, a root-sibling module to ``coordinator.py`` that is nonetheless
HA-free like ``engines/``/``modes/`` (see that module's own docstring), so its tests are
plain pytest too.

``test_entity.py`` is a deliberate root-level exception (ADR-0013): it tests
``SmartChargingEntity.suggested_object_id`` by direct instantiation, needing no ``hass``,
``EntityPlatform``, or registry (see that module's own docstring), so its tests are plain
pytest too.

``test_notification_state.py`` is a deliberate root-level exception (notifications design
doc Sec7, ADR-0009): it tests ``notification_state.py``'s pure UC08 prompt-lifecycle
state machine (prior state, observed inputs, and an injected clock -- no HA imports), so
its tests are plain pytest too.

``test_config_flow_translations.py`` is a deliberate root-level exception (issue #508): it
only reads ``const.py`` and the integration's own JSON translation files off disk, needing
no ``hass`` fixture at all, so its tests are plain pytest too.

``test_compare_baseline.py`` is a deliberate exception despite living under
``tests/benchmarks/`` (issue #708, ADR-0026): it tests ``compare_baseline.py``, a pure
JSON/arithmetic module with no HA dependency, distinct from its sibling
``test_coordinator_perf.py`` in the same directory, which genuinely needs ``hass`` and
stays an HA-harness test.

This file deliberately stays HA-free -- it is imported for every test under ``tests/``,
including the pure-logic dirs above. The shared end-to-end test helpers (config-entry
seeding, coordinator seeding, etc.) that the HA-harness suites need live in
``tests/helpers.py`` instead (issue #411).
"""

from pathlib import Path

import pytest

# Directories whose tests are pure logic with no HA dependency (ADR-0009).
_PURE_DIRS = frozenset({"modes", "engines", "profiles"})

# Individual test files that are pure logic despite living outside _PURE_DIRS -- most are
# root-level (ADR-0012/0013; test_notification_state.py per the notifications design doc
# Sec7), but test_compare_baseline.py per issue #708/ADR-0026 is not: it lives under
# tests/benchmarks/, which must stay HA-harness-capable for its sibling
# test_coordinator_perf.py.
_PURE_FILES = frozenset(
    {
        "test_coordinator_cycle.py",
        "test_entity.py",
        "test_notification_state.py",
        "test_config_flow_translations.py",
        "test_compare_baseline.py",
    }
)


def _is_pure_logic_test(node: pytest.Item) -> bool:
    """True when the test lives under a pure-logic dir, or is a named pure-logic file."""
    path = Path(str(node.path))
    return path.name in _PURE_FILES or any(part in _PURE_DIRS for part in path.parts)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(request):
    """Enable the custom integration for HA-harness tests (not pure-logic dirs)."""
    if not _is_pure_logic_test(request.node):
        request.getfixturevalue("enable_custom_integrations")
    yield


@pytest.fixture(autouse=True)
def _dashboard_package_dir_uses_tmp_path(request, monkeypatch, tmp_path):
    """C5 (#601): every HA-harness suite that sets up a full config entry now regenerates the
    runtime dashboard's YAML file -- redirect `dashboard._package_dir()` to `tmp_path` for all
    of them, not just `tests/test_dashboard.py`'s own tests, so the real package directory on
    disk is never written to as a side effect of running the suite."""
    if not _is_pure_logic_test(request.node):
        monkeypatch.setattr(
            "custom_components.smart_charging.dashboard._package_dir", lambda: tmp_path
        )
    yield
