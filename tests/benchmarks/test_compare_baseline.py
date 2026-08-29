"""Plain-pytest tests for tests/benchmarks/compare_baseline.py and update_baseline.py
(issue #708, ADR-0026).

Pure JSON/arithmetic -- no HA dependency (registered in tests/conftest.py's _PURE_FILES).
"""

import json
from datetime import date
from pathlib import Path

from tests.benchmarks.compare_baseline import BASELINE_KEY, METRICS, compare
from tests.benchmarks.update_baseline import update

_REAL_BASELINE_PATH = Path(__file__).parent / "baseline.json"


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

    assert len(rows) == 2 + 3  # header + separator + one row per metric
    assert any("| median_cpu_ms | 10.0 | 10.5 | +5.0% | ok |" == row for row in rows)
    assert not any("REGRESSED" in row for row in rows)


def test_compare_flags_regression_beyond_tolerance(tmp_path):
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
                "median_cpu_ms": 15.0,  # +50%, beyond the 25% tolerance
                "median_rss_delta_kb": 100.0,
                "median_peak_traced_memory_kb": 1000.0,
            }
        )
    )

    rows = compare(str(results_path), str(baseline_path))

    assert any("median_cpu_ms" in row and "REGRESSED" in row for row in rows)
    assert not any("median_rss_delta_kb" in row and "REGRESSED" in row for row in rows)


def test_compare_flags_regression_for_a_negative_baseline(tmp_path):
    """Guards the abs(base_value) sign fix -- signed division would compute
    (-50 - -100) / -100 * 100 = -50% (a false "improvement"), never REGRESSED."""
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "coordinator_cycle": {
                    "median_cpu_ms": 10.0,
                    "median_rss_delta_kb": -100.0,
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
                "median_cpu_ms": 10.0,
                "median_rss_delta_kb": -50.0,
                "median_peak_traced_memory_kb": 1000.0,
            }
        )
    )

    rows = compare(str(results_path), str(baseline_path))

    assert any("median_rss_delta_kb" in row and "REGRESSED" in row for row in rows)


def test_compare_tolerance_boundary(tmp_path):
    """Pins _TOLERANCE_PCT=25.0 and its `>` (not `>=`) boundary -- exactly +25% stays ok,
    a hair over regresses."""
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "coordinator_cycle": {
                    "median_cpu_ms": 100.0,
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
                "median_cpu_ms": 125.0,  # exactly +25% -- at tolerance, not beyond it
                "median_rss_delta_kb": 125.1,  # a hair over +25%
                "median_peak_traced_memory_kb": 1000.0,
            }
        )
    )

    rows = compare(str(results_path), str(baseline_path))

    assert not any("median_cpu_ms" in row and "REGRESSED" in row for row in rows)
    assert any("median_rss_delta_kb" in row and "REGRESSED" in row for row in rows)


def test_compare_zero_baseline_ok_within_absolute_tolerance(tmp_path):
    """A seeded zero baseline (e.g. median_rss_delta_kb: 0.0, issue #739) can't use a percentage
    delta -- guards the absolute-KB fallback instead of the old "+0.0% ok" always-passes bug."""
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "coordinator_cycle": {
                    "median_cpu_ms": 10.0,
                    "median_rss_delta_kb": 0.0,
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
                "median_cpu_ms": 10.0,
                "median_rss_delta_kb": 50.0,  # within the absolute tolerance floor
                "median_peak_traced_memory_kb": 1000.0,
            }
        )
    )

    rows = compare(str(results_path), str(baseline_path))

    assert not any("median_rss_delta_kb" in row and "REGRESSED" in row for row in rows)
    assert any("median_rss_delta_kb" in row and "(vs zero baseline)" in row for row in rows)


def test_compare_zero_baseline_never_flags_a_negative_current_value(tmp_path):
    """Guards the no-abs()-on-the-zero-baseline-branch fix -- current_value=-150.0 is RSS
    *shrinking*, a real improvement, not a regression; abs(-150.0) > floor would wrongly flag it."""
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "coordinator_cycle": {
                    "median_cpu_ms": 10.0,
                    "median_rss_delta_kb": 0.0,
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
                "median_cpu_ms": 10.0,
                "median_rss_delta_kb": -150.0,  # RSS shrank -- not a regression at any magnitude
                "median_peak_traced_memory_kb": 1000.0,
            }
        )
    )

    rows = compare(str(results_path), str(baseline_path))

    assert not any("median_rss_delta_kb" in row and "REGRESSED" in row for row in rows)


def test_compare_zero_baseline_flags_regression_beyond_absolute_tolerance(tmp_path):
    """150.0 KB exceeds median_rss_delta_kb's 100.0 KB floor (issue #739)."""
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "coordinator_cycle": {
                    "median_cpu_ms": 10.0,
                    "median_rss_delta_kb": 0.0,
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
                "median_cpu_ms": 10.0,
                "median_rss_delta_kb": 150.0,  # beyond the absolute tolerance floor
                "median_peak_traced_memory_kb": 1000.0,
            }
        )
    )

    rows = compare(str(results_path), str(baseline_path))

    assert any("median_rss_delta_kb" in row and "REGRESSED" in row for row in rows)


def test_compare_reports_missing_results_file_without_raising(tmp_path):
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps({"coordinator_cycle": {"median_cpu_ms": 10.0, "recorded_at": "2026-08-17"}})
    )
    missing_results_path = tmp_path / "does-not-exist.json"

    rows = compare(str(missing_results_path), str(baseline_path))

    assert len(rows) == 1
    assert str(missing_results_path) in rows[0]


def test_update_overwrites_the_medians_and_recorded_at_and_nothing_else(tmp_path):
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "unrelated_top_level_key": "untouched",
                "coordinator_cycle": {
                    "median_cpu_ms": 10.0,
                    "median_rss_delta_kb": 100.0,
                    "median_peak_traced_memory_kb": 1000.0,
                    "recorded_at": "2020-01-01",  # unambiguously stale, unlike today's date
                    "batches": 11,  # unrelated sibling key -- must also survive the update
                },
            }
        )
    )
    results_path = tmp_path / "coordinator_cycle.json"
    results_path.write_text(
        json.dumps(
            {
                "median_cpu_ms": 11.0,
                "median_rss_delta_kb": 110.0,
                "median_peak_traced_memory_kb": 1100.0,
            }
        )
    )

    update(str(results_path), str(baseline_path))

    updated = json.loads(baseline_path.read_text())
    assert updated["unrelated_top_level_key"] == "untouched"
    assert updated["coordinator_cycle"] == {
        "median_cpu_ms": 11.0,
        "median_rss_delta_kb": 110.0,
        "median_peak_traced_memory_kb": 1100.0,
        "recorded_at": date.today().isoformat(),
        "batches": 11,
    }


def test_committed_baseline_is_loadable_and_schema_complete():
    """Guards the real, committed tests/benchmarks/baseline.json (issue #708 Task 3.1) --
    a typo in that hand-authored file would otherwise surface only as a KeyError inside
    the CI perf job's `if: always()` comparison step (ci.yml), which never fails the job."""
    baseline = json.loads(_REAL_BASELINE_PATH.read_text())[BASELINE_KEY]
    for metric in METRICS:
        assert isinstance(baseline[metric], (int, float))
    assert "recorded_at" in baseline
