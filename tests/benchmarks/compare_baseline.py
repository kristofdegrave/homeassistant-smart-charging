"""Advisory baseline comparison for the coordinator perf suite (issue #708, ADR-0026;
zero-baseline handling per issue #739).

Never raises or signals failure on a regression -- this is deliberately advisory-only
(design doc S5: `perf` stays continue-on-error: true until real trend history exists).
Callers write the returned rows to GITHUB_STEP_SUMMARY or print them; deciding whether a
regression should ever fail the job is a separate, future decision.
"""

import json
import os

BASELINE_KEY = "coordinator_cycle"  # not module-private -- update_baseline.py reuses it
METRICS = ("median_cpu_ms", "median_rss_delta_kb", "median_peak_traced_memory_kb")
_STATUS_OK = "ok"
_STATUS_REGRESSED = "REGRESSED"
# Deliberately loose first-cut threshold (design doc S4) -- no real variance data exists
# yet to calibrate a tighter one.
_TOLERANCE_PCT = 25.0
# A percentage delta is undefined against a zero baseline (division by zero) -- median_rss_delta_kb
# in particular can legitimately be seeded at 0.0 (issue #739). Rather than silently reporting
# "+0.0% ok" forever in that case, fall back to this per-metric absolute floor (same unit as the
# metric itself). Deliberately generous, same first-cut-threshold spirit as _TOLERANCE_PCT --
# each floor sits well under that metric's own gross-regression ceiling in
# test_coordinator_perf.py's _MAX_* constants (a single shared floor would either be vacuous for
# KB-scale metrics or exceed the CPU metric's own ceiling).
_ZERO_BASELINE_ABS_TOLERANCE = {
    "median_cpu_ms": 5.0,
    "median_rss_delta_kb": 100.0,
    "median_peak_traced_memory_kb": 100.0,
}


def compare(results_path: str, baseline_path: str) -> list[str]:
    if not os.path.exists(results_path):
        return [f"No perf results found at {results_path} -- the pytest step likely errored."]

    with open(results_path) as f:
        results = json.load(f)
    with open(baseline_path) as f:
        baseline = json.load(f)[BASELINE_KEY]

    rows = ["| metric | baseline | current | delta | status |", "| --- | --- | --- | --- | --- |"]
    for metric in METRICS:
        base_value = baseline[metric]
        current_value = results[metric]
        if base_value:
            # A metric like median_rss_delta_kb can legitimately be <= 0 -- dividing by the
            # signed base_value would flip the sign of a real regression into a false
            # "improvement" for a negative baseline. abs() keeps delta_pct's sign meaning
            # "current is higher/lower than baseline" regardless of the baseline's own sign.
            delta_pct = ((current_value - base_value) / abs(base_value)) * 100
            status = _STATUS_REGRESSED if delta_pct > _TOLERANCE_PCT else _STATUS_OK
            delta_display = f"{delta_pct:+.1f}%"
        else:
            # No abs() here, unlike the branch above: current_value is compared directly against
            # the baseline of 0, so only a *growth* past the floor counts as a regression -- a
            # metric that legitimately went negative (e.g. RSS shrank) must never be flagged.
            status = (
                _STATUS_REGRESSED
                if current_value > _ZERO_BASELINE_ABS_TOLERANCE[metric]
                else _STATUS_OK
            )
            delta_display = f"{current_value:+.1f} (vs zero baseline)"
        rows.append(
            f"| {metric} | {base_value:.1f} | {current_value:.1f} | {delta_display} | {status} |"
        )
    return rows


if __name__ == "__main__":
    import sys

    print("\n".join(compare(sys.argv[1], sys.argv[2])))
