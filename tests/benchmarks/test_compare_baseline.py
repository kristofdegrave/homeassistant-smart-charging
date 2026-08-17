"""Plain-pytest tests for tests/benchmarks/compare_baseline.py (issue #708, ADR-0026).

Pure JSON/arithmetic -- no HA dependency (registered in tests/conftest.py's _PURE_FILES).
"""

import json

from tests.benchmarks.compare_baseline import compare


def test_compare_reports_no_regression_within_tolerance(tmp_path):
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "coordinator_cycle": {
                    "median_cpu_ms": 10.0,
                    "median_rss_delta_kb": 100.0,
                    "median_peak_traced_memory_kb": 1000.0,
                    "recorded_at": "2026-08-17",
                }
            }
        )
    )
    results_path = tmp_path / "coordinator_cycle.json"
    results_path.write_text(
        json.dumps(
            {
                "median_cpu_ms": 10.5,
                "median_rss_delta_kb": 105.0,
                "median_peak_traced_memory_kb": 1020.0,
            }
        )
    )

    rows = compare(str(results_path), str(baseline_path))

    assert not any("REGRESSED" in row for row in rows)
    assert any("median_cpu_ms" in row for row in rows)
