"""CPU/memory tripwire for the M1 control cycle (issue #266).

Separate from the functional suite in tests/test_coordinator.py -- these tests report and
bound the cost of repeatedly running the hot path (SmartChargingCoordinator._async_update_data),
not its behavior. Ceilings are deliberately generous (a CI-runner tripwire for gross
regressions, not a performance SLA) until a real baseline exists.
"""

import json
import os
import time
import tracemalloc

from custom_components.smart_charging.config import SmartChargingConfig
from custom_components.smart_charging.const import (
    MODE_POWER,
    ROLE_CHARGER_CURRENT,
    ROLE_CHARGER_POWER,
    ROLE_CHARGER_STATUS,
    ROLE_GRID_VOLTAGE,
    ROLE_NET_POWER,
)
from custom_components.smart_charging.coordinator import SmartChargingCoordinator
from tests.config_factory import make_test_config

_ITERATIONS = 200
_MAX_AVG_CYCLE_MS = 20.0
_MAX_PEAK_MEMORY_KB = 5_000


class _FakeNumeric:
    def __init__(self, value):
        self._value = value

    async def read(self):
        return self._value

    async def write(self, value):
        pass


class _FakeStatus:
    def __init__(self, canonical):
        self._canonical = canonical

    async def read(self):
        return self._canonical


class _FakeStore:
    """Every read() returns None -- _read_owned_entities() becomes a no-op (ADR-0018)."""

    async def read(self, entity_domain, unique_id_suffix, value_type):
        return None


def _adapters():
    return {
        ROLE_CHARGER_CURRENT: _FakeNumeric(0.0),
        ROLE_CHARGER_STATUS: _FakeStatus("charging"),
        ROLE_NET_POWER: _FakeNumeric(2000.0),
        ROLE_CHARGER_POWER: _FakeNumeric(3000.0),
        ROLE_GRID_VOLTAGE: _FakeNumeric(230.0),
    }


def _config() -> SmartChargingConfig:
    """This suite's own SmartChargingConfig baseline, layered on tests/config_factory.py's
    shared production-DEFAULT_*-seeded factory (issue #570 follow-up: three near-identical
    per-suite factories collapsed to one). `smoothing_window`/`peak_window_size` are this
    file's own long-standing baseline values (distinct from the production defaults
    `make_test_config` otherwise uses)."""
    return make_test_config(smoothing_window=5, peak_window_size=5)


def _write_report(name, payload):
    # Only written when CI sets PERF_RESULTS_DIR (see .github/workflows/ci.yml perf job) --
    # local runs stay report-free.
    out_dir = os.environ.get("PERF_RESULTS_DIR")
    if not out_dir:
        return
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, f"{name}.json"), "w") as f:
        json.dump(payload, f, indent=2)


async def test_power_mode_cycle_perf(hass):
    coord = SmartChargingCoordinator(
        hass, adapters=_adapters(), config=_config(), interval_s=30, store=_FakeStore()
    )
    coord.active_mode = MODE_POWER
    coord.target_current = 10.0

    tracemalloc.start()
    start = time.perf_counter()
    for _ in range(_ITERATIONS):
        await coord._async_update_data()
    elapsed_s = time.perf_counter() - start
    _current_bytes, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    avg_cycle_ms = (elapsed_s / _ITERATIONS) * 1000
    peak_kb = peak_bytes / 1024

    _write_report(
        "coordinator_cycle",
        {
            "iterations": _ITERATIONS,
            "avg_cycle_ms": avg_cycle_ms,
            "peak_traced_memory_kb": peak_kb,
        },
    )

    assert avg_cycle_ms < _MAX_AVG_CYCLE_MS, (
        f"Power-mode cycle averaged {avg_cycle_ms:.2f} ms over {_ITERATIONS} runs "
        f"(ceiling {_MAX_AVG_CYCLE_MS} ms) -- see issue #266"
    )
    assert peak_kb < _MAX_PEAK_MEMORY_KB, (
        f"Power-mode cycle peaked at {peak_kb:.0f} KB traced memory over {_ITERATIONS} runs "
        f"(ceiling {_MAX_PEAK_MEMORY_KB} KB) -- see issue #266"
    )
