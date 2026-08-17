# Real Performance Tests Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace `tests/benchmarks/test_coordinator_perf.py`'s wall-clock+tracemalloc-only
tripwire with real CPU-time (`psutil`) and RSS measurement, multi-batch statistical treatment, and
a committed rolling baseline for trend tracking, per
[ADR-0026](../adl/0026-psutil-for-perf-test-cpu-rss-measurement.md) and issue #708.
**Test-infrastructure only — no `custom_components/` behavior change.**

**Architecture:** Two new plain-Python modules (`tests/benchmarks/compare_baseline.py`,
`tests/benchmarks/update_baseline.py`) plus a committed `tests/benchmarks/baseline.json`; the
existing `test_coordinator_perf.py`'s single test function gets a rewritten measurement body
(11 batches, `psutil` CPU/RSS deltas, `tracemalloc` kept alongside). One new CI step in the `perf`
job. Full design: [`2026-08-17-real-perf-tests-design.md`](2026-08-17-real-perf-tests-design.md).

**Tech Stack:** Python ≥3.12, `pytest` (plain, ADR-0009 — the two new baseline scripts),
`pytest-homeassistant-custom-component` (HA harness — the existing coordinator perf test, test
boundary unchanged), `psutil==7.2.2` (new test-only dependency, ADR-0026), `ruff`.

**Model:** Per CLAUDE.md, this is development work — execute on **Sonnet**.

---

## Conventions used throughout

- **Named constants, no magic strings** (CLAUDE.md).
- **`git commit --author="Claude <noreply@anthropic.com>"`** with the trailer
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- Re-check `git branch --show-current` before every commit (shared checkout).
- Both `ruff check .` and `ruff format --check .` before each commit that touches Python.
- `compare_baseline.py`/`update_baseline.py` tests are plain pytest, no `hass` fixture (ADR-0009 —
  both modules only read/write JSON and do arithmetic, no HA coupling).

---

## Phase 0 — `tests/benchmarks/compare_baseline.py`

### Task 0.1: `compare(results_path, baseline_path)` — within-tolerance case

**ADR honored:** ADR-0026 (measurement primitives this compares are `psutil`-based, decided
there). **Test boundary:** plain pytest, `tests/benchmarks/test_compare_baseline.py` (new file —
pure, no HA).

**Files:**
- Create: `tests/benchmarks/compare_baseline.py`
- Create: `tests/benchmarks/test_compare_baseline.py`

**Step 1: Write the failing test**

```python
import json

from tests.benchmarks.compare_baseline import compare

_TOLERANCE_PCT = 25.0


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
```

**Step 2: Run to verify failure** —
`pytest tests/benchmarks/test_compare_baseline.py -v` →
`ModuleNotFoundError: No module named 'tests.benchmarks.compare_baseline'`.

**Step 3: Implement**

```python
"""Advisory baseline comparison for the coordinator perf suite (issue #708, ADR-0026).

Never raises or signals failure on a regression -- this is deliberately advisory-only
(design doc S5: `perf` stays continue-on-error: true until real trend history exists).
Callers write the returned rows to GITHUB_STEP_SUMMARY or print them; deciding whether a
regression should ever fail the job is a separate, future decision.
"""

import json

_TOLERANCE_PCT = 25.0

_METRICS = ("median_cpu_ms", "median_rss_delta_kb", "median_peak_traced_memory_kb")


def compare(results_path: str, baseline_path: str) -> list[str]:
    with open(results_path) as f:
        results = json.load(f)
    with open(baseline_path) as f:
        baseline = json.load(f)["coordinator_cycle"]

    rows = ["| metric | baseline | current | delta % | status |", "| --- | --- | --- | --- | --- |"]
    for metric in _METRICS:
        base_value = baseline[metric]
        current_value = results[metric]
        delta_pct = ((current_value - base_value) / base_value) * 100 if base_value else 0.0
        status = "REGRESSED" if delta_pct > _TOLERANCE_PCT else "ok"
        rows.append(
            f"| {metric} | {base_value:.1f} | {current_value:.1f} | {delta_pct:+.1f}% | {status} |"
        )
    return rows
```

**Step 4: Run to verify pass.**

**Step 5: Commit** — `test: add compare_baseline within-tolerance case (issue #708)`.

### Task 0.2: `compare` — regression case

**Test boundary:** plain pytest, same file.

**Files:**
- Edit: `tests/benchmarks/test_compare_baseline.py`

**Step 1: Write the failing test**

```python
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
```

**Step 2: Run to verify it already passes** (Task 0.1's implementation already handles this case —
this step documents/locks the regression-flagging behavior with its own test, no new code
expected). If it fails, fix `compare()` until it passes.

**Step 3: Commit** — `test: add compare_baseline regression case (issue #708)`.

---

## Phase 1 — `tests/benchmarks/update_baseline.py`

### Task 1.1: `update(results_path, baseline_path)`

**ADR honored:** ADR-0026. **Test boundary:** plain pytest,
`tests/benchmarks/test_compare_baseline.py` (shared file — both scripts are small enough not to
need separate test files; see Packaging note in the design doc if this grows).

**Files:**
- Create: `tests/benchmarks/update_baseline.py`
- Edit: `tests/benchmarks/test_compare_baseline.py`

**Step 1: Write the failing test**

```python
from tests.benchmarks.update_baseline import update


def test_update_overwrites_only_the_three_median_fields(tmp_path):
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
                "median_cpu_ms": 11.0,
                "median_rss_delta_kb": 110.0,
                "median_peak_traced_memory_kb": 1100.0,
            }
        )
    )

    update(str(results_path), str(baseline_path))

    updated = json.loads(baseline_path.read_text())["coordinator_cycle"]
    assert updated["median_cpu_ms"] == 11.0
    assert updated["median_rss_delta_kb"] == 110.0
    assert updated["median_peak_traced_memory_kb"] == 1100.0
```

**Step 2: Run to verify failure.**

**Step 3: Implement**

```python
"""Human-run baseline update for the coordinator perf suite (issue #708, ADR-0026).

Never invoked by CI -- a human runs this deliberately after judging a fresh perf-test
result an acceptable new normal, then commits the updated baseline.json in its own PR
(design doc S4), the same manual-approval discipline as every other change in this project.
"""

import json
from datetime import date

_METRICS = ("median_cpu_ms", "median_rss_delta_kb", "median_peak_traced_memory_kb")


def update(results_path: str, baseline_path: str) -> None:
    with open(results_path) as f:
        results = json.load(f)
    with open(baseline_path) as f:
        baseline = json.load(f)

    for metric in _METRICS:
        baseline["coordinator_cycle"][metric] = results[metric]
    baseline["coordinator_cycle"]["recorded_at"] = date.today().isoformat()

    with open(baseline_path, "w") as f:
        json.dump(baseline, f, indent=2)
        f.write("\n")
```

**Step 4: Run to verify pass.**

**Step 5: Commit** — `feat: add update_baseline script (issue #708)`.

---

## Phase 2 — Rewrite `test_coordinator_perf.py`'s measurement body

### Task 2.1: Add `psutil` and rewrite the measurement/assertions

**ADR honored:** ADR-0026. **Test boundary:** HA harness, `tests/benchmarks/test_coordinator_perf.py`
(existing file, existing `hass`-fixture test — the harness boundary itself doesn't change, only
the measurement body).

**Files:**
- Edit: `requirements-test.txt`
- Edit: `tests/benchmarks/test_coordinator_perf.py`

**Step 1: Pin the new dependency**

Add to `requirements-test.txt` (alongside the other pinned test-only dependencies):

```text
psutil==7.2.2
```

Run `pip install -r requirements-test.txt` to confirm it resolves.

**Step 2: Write the failing test** — this task rewrites the *existing* test function rather than
adding a new one (the design doc's success criterion is the same test name, new body). Replace
`test_power_mode_cycle_perf` entirely:

```python
import statistics

import psutil

_BATCHES = 11
_WARMUP_BATCHES = 1
_MAX_MEDIAN_CPU_MS = 20.0
_MAX_MAX_CPU_MS = 30.0
_MAX_MEDIAN_RSS_DELTA_KB = 2_000.0
_MAX_MEDIAN_PEAK_MEMORY_KB = 5_000.0

_process = psutil.Process()


async def _measure_one_batch(coord):
    cpu_before = _process.cpu_times()
    rss_before_kb = _process.memory_info().rss / 1024
    tracemalloc.start()
    for _ in range(_ITERATIONS):
        await coord._async_update_data()
    _current_bytes, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    cpu_after = _process.cpu_times()
    rss_after_kb = _process.memory_info().rss / 1024

    cpu_ms_total = (cpu_after.user + cpu_after.system) - (cpu_before.user + cpu_before.system)
    return (cpu_ms_total * 1000) / _ITERATIONS, rss_after_kb - rss_before_kb, peak_bytes / 1024


async def test_power_mode_cycle_perf(hass):
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

    _write_report(
        "coordinator_cycle",
        {
            "batches": _BATCHES,
            "warmup_batches": _WARMUP_BATCHES,
            "iterations_per_batch": _ITERATIONS,
            "median_cpu_ms": median_cpu_ms,
            "max_cpu_ms": max_cpu_ms,
            "median_rss_delta_kb": median_rss_delta_kb,
            "median_peak_traced_memory_kb": median_peak_kb,
        },
    )

    assert median_cpu_ms < _MAX_MEDIAN_CPU_MS, (
        f"Power-mode cycle's median CPU time was {median_cpu_ms:.2f} ms over "
        f"{len(measured)} measured batches of {_ITERATIONS} runs each "
        f"(ceiling {_MAX_MEDIAN_CPU_MS} ms) -- see issue #708"
    )
    assert max_cpu_ms < _MAX_MAX_CPU_MS, (
        f"Power-mode cycle's max-batch CPU time was {max_cpu_ms:.2f} ms "
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
```

Remove the now-unused `_MAX_AVG_CYCLE_MS`/`_MAX_PEAK_MEMORY_KB` constants and the `time` import
(no longer used — `psutil.cpu_times()` replaces `time.perf_counter()` entirely, per the design
doc's "replace," not "augment," decision for wall-clock specifically). Keep the `tracemalloc`
import — still used for `median_peak_traced_memory_kb`.

**Step 3: Run to verify pass** — `pytest tests/benchmarks -q` locally (or under WSL on Windows,
per this project's existing HA-harness convention).

**Step 4: Commit** — `refactor: measure coordinator perf with psutil CPU/RSS + multi-batch stats (ADR-0026, issue #708)`.

---

## Phase 3 — Seed the first real baseline

### Task 3.1: Record the first `baseline.json` from real CI output

**ADR honored:** ADR-0026. **Test boundary:** none — this task records data, it doesn't add code.

**Files:**
- Create: `tests/benchmarks/baseline.json`

**Step 1:** Push Task 2.1's commit and let the `perf` CI job run once (or run
`PERF_RESULTS_DIR=/tmp/perf-results pytest tests/benchmarks -q` locally/under WSL and use that
output — either is a legitimate seed per the design doc, since there is no prior trustworthy
baseline to preserve).

**Step 2:** Take the resulting `coordinator_cycle.json`'s three median fields and write
`tests/benchmarks/baseline.json`:

```json
{
  "coordinator_cycle": {
    "median_cpu_ms": <value from the run>,
    "median_rss_delta_kb": <value from the run>,
    "median_peak_traced_memory_kb": <value from the run>,
    "recorded_at": "<today's date>"
  }
}
```

(Or run `python -c "from tests.benchmarks.update_baseline import update; update('/tmp/perf-results/coordinator_cycle.json', 'tests/benchmarks/baseline.json')"`
against an empty starter file with the `coordinator_cycle` key already present, then hand-edit
`recorded_at` if needed — either mechanism produces the same file.)

**Step 3: Commit** — `chore: seed the first real perf baseline (issue #708)`.

---

## Phase 4 — Wire the CI comparison step

### Task 4.1: Add the `compare_baseline.py` step to the `perf` job

**ADR honored:** ADR-0026. **Test boundary:** none — CI YAML only, verified by the next CI run.

**Files:**
- Edit: `.github/workflows/ci.yml`

**Step 1: Implement** — in the `perf` job (`.github/workflows/ci.yml:80-103`), add one step
immediately after the existing `pytest tests/benchmarks -q` step, before `actions/upload-artifact`:

```yaml
      - run: python tests/benchmarks/compare_baseline.py "$PERF_RESULTS_DIR/coordinator_cycle.json" tests/benchmarks/baseline.json >> "$GITHUB_STEP_SUMMARY"
        if: always()
        env:
          PERF_RESULTS_DIR: ${{ runner.temp }}/perf-results
```

This requires `compare_baseline.py` to be runnable as a script, not just importable — add a
`if __name__ == "__main__":` block:

```python
if __name__ == "__main__":
    import sys

    print("\n".join(compare(sys.argv[1], sys.argv[2])))
```

No `permissions:` change in `ci.yml` — the step only reads `baseline.json` (already checked out)
and the results directory, and writes to `$GITHUB_STEP_SUMMARY`, not to the repo.

**Step 2:** No new automated test — this is CI YAML, verified by observing the next real workflow
run's job summary shows the comparison table. Note this verification step explicitly in the PR
description so the human reviewer checks the Actions tab, not just the diff.

**Step 3: Commit** — `ci: compare perf results against the committed baseline (issue #708)`.

---

## Phase 5 — Final verification

### Task 5.1: Full regression pass

**ADR honored:** ADR-0009, ADR-0026. **Test boundary:** full suite.

**Files:** none changed — verification only.

**Step 1:** `pytest tests/` (entire suite) — must pass in full, including the two new
`compare_baseline`/`update_baseline` tests and the rewritten perf test.

**Step 2:** `ruff check .` and `ruff format --check .` on the whole repo.

**Step 3:** Confirm `git diff` touches only `tests/benchmarks/`, `requirements-test.txt`, and
`.github/workflows/ci.yml` — no `custom_components/` file changed (this slice's own success
criterion, design doc §1).

**Step 4: Report** — plan complete; issue #708 implemented, no coordinator behavior change, full
suite green, first real baseline committed.
