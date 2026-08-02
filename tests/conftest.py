"""Shared pytest fixtures and end-to-end test helpers for the Smart Charging test suite.

Per ADR-0009 (Option A), the pure mode/engine/profile logic under ``tests/modes/``,
``tests/engines/``, and ``tests/profiles/`` runs as plain pytest with no HA dependency.
Every other test (adapters, plus the root-level config-flow / coordinator / init tests,
and any other root-level file listed in ``_PURE_FILES`` below) is an HA-harness test that
needs the custom integration loaded. The autouse fixture below applies
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

The module-level helpers below (``entry_data_base``, ``entry_options_base``,
``capture_charger_current_writes``, ``seed_ample_peak_headroom``, ``seed_today_deadline``)
are the shared shape promoted from ``tests/test_init.py``, ``tests/test_coordinator.py``,
``tests/test_captar_end_to_end.py``, ``tests/test_deadline_soc_management_end_to_end.py``,
and ``tests/test_solar_end_to_end.py`` (issue #411, follow-up from PR #407's code-reviewer
findings): those files had each grown near-verbatim copies of the same config-entry/
coordinator seeding helpers. Each importing suite still owns its own scenario-specific
overrides -- these only give the identical common shape one source of truth.
"""

from datetime import timedelta
from pathlib import Path

import pytest
from homeassistant.util import dt as dt_util

from custom_components.smart_charging.const import (
    CONF_CHARGER_CURRENT_ENTITY,
    CONF_CHARGER_POWER_ENTITY,
    CONF_CHARGER_STATUS_ENTITY,
    CONF_DEFAULT_SOC_LIMIT,
    CONF_DEFAULT_TARGET_CURRENT,
    CONF_GRID_CEILING_A,
    CONF_GRID_SAFETY_OFFSET_A,
    CONF_GRID_VOLTAGE_ENTITY,
    CONF_MAX_CURRENT,
    CONF_MIN_CURRENT,
    CONF_NET_POWER_ENTITY,
    CONF_NOMINAL_VOLTAGE,
    CONF_STATUS_TRANSLATION,
    STATE_CHARGING,
    STATE_CONNECTED,
)

# Directories whose tests are pure logic with no HA dependency (ADR-0009).
_PURE_DIRS = frozenset({"modes", "engines", "profiles"})

# Root-level test files that are pure logic despite living outside _PURE_DIRS (ADR-0012/0013).
_PURE_FILES = frozenset({"test_coordinator_cycle.py", "test_entity.py"})


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


def entry_data_base(**overrides):
    """DATA bucket -- entity-role mappings + translation only (ADR-0005).

    Callers layer their own scenario-specific keys (or override a base one, e.g. a
    narrower ``CONF_STATUS_TRANSLATION``) via ``overrides`` -- this only fixes the common
    shape every end-to-end suite's config entry starts from.
    """
    data = {
        CONF_CHARGER_CURRENT_ENTITY: "number.charger_current",
        CONF_CHARGER_STATUS_ENTITY: "sensor.evse",
        CONF_STATUS_TRANSLATION: {"Charging": STATE_CHARGING, "Connected": STATE_CONNECTED},
        CONF_NET_POWER_ENTITY: "sensor.net_power",
        CONF_CHARGER_POWER_ENTITY: "sensor.charger_power",
        CONF_GRID_VOLTAGE_ENTITY: "sensor.grid_voltage",
    }
    data.update(overrides)
    return data


def entry_options_base(**overrides):
    """OPTIONS bucket -- thresholds/defaults + interval (ADR-0005).

    Callers layer their own scenario-specific keys on top via ``overrides``.
    """
    options = {
        CONF_NOMINAL_VOLTAGE: 230.0,
        CONF_MIN_CURRENT: 6.0,
        CONF_MAX_CURRENT: 16.0,
        CONF_GRID_CEILING_A: 25.0,
        CONF_GRID_SAFETY_OFFSET_A: 2.0,
        CONF_DEFAULT_TARGET_CURRENT: 10.0,
        CONF_DEFAULT_SOC_LIMIT: 80.0,
    }
    options.update(overrides)
    return options


def seed_charger_states(hass, *, status, net_w=0.0, charger_w=0.0, ev_soc=50.0, grid_voltage=230.0):
    """Seed the raw entity states a config-entry-driven coordinator cycle reads from.

    Every end-to-end suite seeds the same five/six entities; a suite that doesn't map a
    given role (e.g. no `ev_soc` entity configured) just leaves the corresponding state
    unused rather than omitting it here.
    """
    hass.states.async_set("number.charger_current", "0.0")
    hass.states.async_set("sensor.evse", status)
    hass.states.async_set("sensor.net_power", str(net_w))
    hass.states.async_set("sensor.charger_power", str(charger_w))
    hass.states.async_set("sensor.grid_voltage", str(grid_voltage))
    hass.states.async_set("sensor.ev_soc", str(ev_soc))


def capture_charger_current_writes(hass):
    """Capture number.set_value calls targeting the charger-current entity.

    The real `number` platform (loaded via PLATFORMS) registers its own set_value
    service handler on setup, so a fake `hass.services.async_register` stand-in gets
    clobbered; listen for the call_service event instead -- it fires for every call
    regardless of which handler is installed.
    """
    calls = []

    def _record(event):
        if event.data["domain"] == "number" and event.data["service"] == "set_value":
            calls.append(event.data["service_data"])

    hass.bus.async_listen("call_service", _record)
    return calls


def seed_ample_peak_headroom(coordinator, kw=100.0):
    """Pre-seed the Peak-Demand Tracker as though a large historical peak already exists
    (the same shape a MonthlyPeakSensor restore would seed, Task 4.2) -- keeps R3's clamp
    out of the way of tests that exercise unrelated behavior, not R3 itself."""
    now_dt = dt_util.now()
    coordinator._peak_demand.tracked_month = (now_dt.year, now_dt.month)
    coordinator._peak_demand.tracked_kw = kw


def seed_today_deadline(coordinator, *, hours_from_now):
    """Seed today's departure-deadline default so it resolves `hours_from_now` ahead of
    real wall-clock now (the deadline/required-current resolution reads dt_util.now(),
    not the mode state machines' injected monotonic clock)."""
    now_dt = dt_util.now()
    coordinator.departure_dow_defaults[now_dt.weekday()] = (
        now_dt + timedelta(hours=hours_from_now)
    ).time()
