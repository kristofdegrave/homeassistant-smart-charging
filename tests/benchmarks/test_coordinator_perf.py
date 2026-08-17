"""CPU/RSS tripwire for the M1 control cycle (issue #708, ADR-0026).

Separate from the functional suite in tests/test_coordinator.py -- these tests report and
bound the cost of repeatedly running the hot path (SmartChargingCoordinator._async_update_data),
not its behavior. Ceilings are deliberately generous placeholders (a CI-runner tripwire for
gross regressions, not a performance SLA) until a real baseline exists (design doc S3.1).
"""

import json
import os
import statistics
import tracemalloc

import psutil

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
from tests.benchmarks.compare_baseline import BASELINE_KEY, METRICS
from tests.config_factory import make_test_config

_ITERATIONS = 200
_BATCHES = 11
_WARMUP_BATCHES = 1
_MAX_MEDIAN_CPU_MS = 20.0
_MAX_MAX_CPU_MS = 30.0
_MAX_MEDIAN_RSS_DELTA_KB = 2_000.0
_MAX_MEDIAN_PEAK_MEMORY_KB = 5_000.0

_process = psutil.Process()


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


async def _measure_one_batch(coord):
    """One batch's CPU-ms-per-cycle, net RSS delta (KB), and peak traced memory (KB).
    Sampled before/after this batch specifically (not once for the whole test) so the
    RSS delta is isolated from whatever earlier batches already allocated -- ADR-0026's
    own rationale for choosing psutil over resource.getrusage."""
    cpu_before = _process.cpu_times()
    rss_before_kb = _process.memory_info().rss / 1024
    tracemalloc.start()
    for _ in range(_ITERATIONS):
        await coord._async_update_data()
    _current_bytes, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    cpu_after = _process.cpu_times()
    rss_after_kb = _process.memory_info().rss / 1024

    cpu_s_total = (cpu_after.user + cpu_after.system) - (cpu_before.user + cpu_before.system)
    return (cpu_s_total * 1000) / _ITERATIONS, rss_after_kb - rss_before_kb, peak_bytes / 1024


async def test_power_mode_cycle_perf(hass):
    """CPU/RSS tripwire for the M1 control cycle (issue #708, ADR-0026). Runs _BATCHES
    batches of _ITERATIONS cycles each, discards the first as warm-up, and reports
    median (primary comparator) plus max_cpu_ms -- a small-n proxy for a 95th
    percentile, not a true one: with only _BATCHES - _WARMUP_BATCHES measured batches, a
    statistically rigorous p95 isn't meaningful (design doc S3)."""
    coord = SmartChargingCoordinator(
        hass, adapters=_adapters(), config=_config(), interval_s=30, store=_FakeStore()
    )
    coord.active_mode = MODE_POWER
    coord.target_current = 10.0

    batches = [await _measure_one_batch(coord) for _ in range(_BATCHES)]
    measured = batches[_WARMUP_BATCHES:]
    cpu_values = [b[0] for b in measured]
    rss_values = [b[1] for b in measured]
    peak_values = [b[2] for b in measured]

    median_cpu_ms = statistics.median(cpu_values)
    max_cpu_ms = max(cpu_values)  # small-n p95 proxy (design doc S3) -- not a true percentile
    median_rss_delta_kb = statistics.median(rss_values)
    median_peak_kb = statistics.median(peak_values)

    cpu_metric, rss_metric, peak_metric = METRICS
    _write_report(
        BASELINE_KEY,
        {
            "batches": _BATCHES,
            "warmup_batches": _WARMUP_BATCHES,
            "iterations_per_batch": _ITERATIONS,
            cpu_metric: median_cpu_ms,
            "max_cpu_ms": max_cpu_ms,
            rss_metric: median_rss_delta_kb,
            peak_metric: median_peak_kb,
        },
    )

    assert median_cpu_ms < _MAX_MEDIAN_CPU_MS, (
        f"Power-mode cycle's median CPU time was {median_cpu_ms:.2f} ms over "
        f"{len(measured)} measured batches of {_ITERATIONS} runs each "
        f"(ceiling {_MAX_MEDIAN_CPU_MS} ms) -- see issue #708"
    )
    assert max_cpu_ms < _MAX_MAX_CPU_MS, (
        f"Power-mode cycle's worst-batch CPU time per cycle was {max_cpu_ms:.2f} ms "
        f"(ceiling {_MAX_MAX_CPU_MS} ms) -- see issue #708"
    )
    assert median_rss_delta_kb < _MAX_MEDIAN_RSS_DELTA_KB, (
        f"Power-mode cycle's median RSS growth was {median_rss_delta_kb:.0f} KB per batch "
        f"(ceiling {_MAX_MEDIAN_RSS_DELTA_KB} KB) -- see issue #708"
    )
    assert median_peak_kb < _MAX_MEDIAN_PEAK_MEMORY_KB, (
        f"Power-mode cycle's median peak traced memory was {median_peak_kb:.0f} KB "
        f"(ceiling {_MAX_MEDIAN_PEAK_MEMORY_KB} KB) -- see issue #708"
    )
