"""Advisory baseline comparison for the coordinator perf suite (issue #708, ADR-0026).

Never raises or signals failure on a regression -- this is deliberately advisory-only
(design doc S5: `perf` stays continue-on-error: true until real trend history exists).
Callers write the returned rows to GITHUB_STEP_SUMMARY or print them; deciding whether a
regression should ever fail the job is a separate, future decision.
"""

import json
import os

_METRICS = ("median_cpu_ms", "median_rss_delta_kb", "median_peak_traced_memory_kb")


def compare(results_path: str, baseline_path: str) -> list[str]:
    if not os.path.exists(results_path):
        return [f"No perf results found at {results_path} -- the pytest step likely errored."]

    with open(results_path) as f:
        results = json.load(f)
    with open(baseline_path) as f:
        baseline = json.load(f)["coordinator_cycle"]

    rows = ["| metric | baseline | current | delta % | status |", "| --- | --- | --- | --- | --- |"]
    for metric in _METRICS:
        base_value = baseline[metric]
        current_value = results[metric]
        delta_pct = ((current_value - base_value) / base_value) * 100 if base_value else 0.0
        rows.append(
            f"| {metric} | {base_value:.1f} | {current_value:.1f} | {delta_pct:+.1f}% | ok |"
        )
    return rows


if __name__ == "__main__":
    import sys

    print("\n".join(compare(sys.argv[1], sys.argv[2])))
