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

from custom_components.smart_charging.const import (
    CONF_MAX_PEAK_KW,
    CONF_PEAK_GRACE_MIN,
    CONF_PEAK_WINDOW_SIZE,
    CONF_POWER_RESPECT_PEAK,
    CONF_SAFETY_MARGIN_W,
    CONF_SMOOTHING_WINDOW,
    MODE_POWER,
)
from custom_components.smart_charging.coordinator import SmartChargingCoordinator

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


def _adapters():
    return {
        "charger_current": _FakeNumeric(0.0),
        "charger_status": _FakeStatus("charging"),
        "net_power": _FakeNumeric(2000.0),
        "charger_power": _FakeNumeric(3000.0),
        "grid_voltage": _FakeNumeric(230.0),
    }


def _config():
    return {
        "min_current": 6.0,
        "max_current": 16.0,
        "grid_ceiling_a": 25.0,
        "grid_safety_offset_a": 2.0,
        "nominal_voltage": 230.0,
        CONF_SMOOTHING_WINDOW: 5,
        CONF_MAX_PEAK_KW: 100.0,
        CONF_SAFETY_MARGIN_W: 250.0,
        CONF_PEAK_GRACE_MIN: 2.0,
        CONF_POWER_RESPECT_PEAK: True,
        CONF_PEAK_WINDOW_SIZE: 5,
    }


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
    coord = SmartChargingCoordinator(hass, adapters=_adapters(), config=_config(), interval_s=30)
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
