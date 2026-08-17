"""Human-run baseline update for the coordinator perf suite (issue #708, ADR-0026).

Never invoked by CI -- a human runs this deliberately after judging a fresh perf-test
result an acceptable new normal, then commits the updated baseline.json in its own PR
(design doc S4), the same manual-approval discipline as every other change in this
project.
"""

import json
from datetime import date

from tests.benchmarks.compare_baseline import BASELINE_KEY, METRICS


def update(results_path: str, baseline_path: str) -> None:
    with open(results_path) as f:
        results = json.load(f)
    with open(baseline_path) as f:
        baseline = json.load(f)

    baseline.setdefault(BASELINE_KEY, {})
    for metric in METRICS:
        baseline[BASELINE_KEY][metric] = results[metric]
    baseline[BASELINE_KEY]["recorded_at"] = date.today().isoformat()

    with open(baseline_path, "w") as f:
        json.dump(baseline, f, indent=2)
        f.write("\n")


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        sys.exit("usage: update_baseline.py <results_path> <baseline_path>")
    update(sys.argv[1], sys.argv[2])
