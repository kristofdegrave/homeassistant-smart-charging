"""Shared pytest fixtures for the Smart Charging test suite.

Per ADR-0009 (Option A), the pure mode/engine/profile logic under ``tests/modes/``,
``tests/engines/``, and ``tests/profiles/`` runs as plain pytest with no HA dependency.
Every other test (adapters, plus the root-level config-flow / coordinator / entity /
init tests) is an HA-harness test that needs the custom integration loaded. The
autouse fixture below applies ``enable_custom_integrations`` to the HA-harness tests
only, keeping the pure dirs HA-free so they collect without phcc.
"""

from pathlib import Path

import pytest

# Directories whose tests are pure logic with no HA dependency (ADR-0009).
_PURE_DIRS = frozenset({"modes", "engines", "profiles"})


def _is_pure_logic_test(node: pytest.Item) -> bool:
    """True when the test lives under a pure-logic dir (tests/modes, tests/engines)."""
    return any(part in _PURE_DIRS for part in Path(str(node.path)).parts)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(request):
    """Enable the custom integration for HA-harness tests (not pure-logic dirs)."""
    if not _is_pure_logic_test(request.node):
        request.getfixturevalue("enable_custom_integrations")
    yield
