# Real Performance Tests Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace `tests/benchmarks/test_coordinator_perf.py`'s wall-clock+tracemalloc-only
tripwire with real CPU-time (`psutil`) and RSS measurement, multi-batch statistical treatment, and
a committed rolling baseline for trend tracking, per
[ADR-0026](../adl/0026-psutil-for-perf-test-cpu-rss-measurement.md) and issue #708.
**Test-infrastructure only — no `custom_components/` behavior change.**

**Architecture:** Two new plain-Python modules (`tests/benchmarks/compare_baseline.py`,
`tests/benchmarks/update_baseline.py`, registered in `tests/conftest.py`'s `_PURE_FILES`) plus a
committed `tests/benchmarks/baseline.json`; the existing `test_coordinator_perf.py`'s single test
function gets a rewritten measurement body (11 batches, `psutil` CPU/RSS deltas, `tracemalloc`
kept alongside). One new CI step in the `perf` job; `perf` scoped to `push` on `main` only
(issue #729); and a fix to the `test` job so it stops accidentally also collecting
`tests/benchmarks`. Full design:
[`2026-08-17-real-perf-tests-design.md`](2026-08-17-real-perf-tests-design.md).

**Tech Stack:** Python ≥3.13 (per `pyproject.toml`), `pytest` (plain, ADR-0009 — the two new baseline scripts),
`pytest-homeassistant-custom-component` (HA harness — the existing coordinator perf test, test
boundary unchanged), `psutil==7.2.2` (new test-only dependency, ADR-0026), `ruff`.

**Model:** Per CLAUDE.md, this is development work — execute on **Sonnet**.

> **Amended following issue #739 / ADR-0029.** This plan's code sketches for the CPU metric, the
> `tracemalloc` window, and the zero-baseline case were written against ADR-0026 alone and **no
> longer match the shipped implementation**: CPU is now sampled with stdlib `time.process_time()`
> ([ADR-0029](../adl/0029-process-time-for-perf-test-cpu-measurement.md), which supersedes
> ADR-0026's CPU half only — RSS via `psutil` is untouched), CPU/RSS and `tracemalloc` are measured
> in two separate sub-batch windows, and `compare_baseline.py` has a per-metric absolute-tolerance
> fallback for a `0.0` baseline. See the amendment note in
> [`2026-08-17-real-perf-tests-design.md`](2026-08-17-real-perf-tests-design.md) for the rationale;
> `tests/benchmarks/test_coordinator_perf.py` and `tests/benchmarks/compare_baseline.py` are the
> source of truth for current behavior. The task-by-task narrative below is left as the historical
> record of how the suite was originally built.

---

## Conventions used throughout

- **Named constants, no magic strings** (CLAUDE.md).
- **`git commit --author="Claude <noreply@anthropic.com>"`** with the trailer
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- Re-check `git branch --show-current` before every commit (shared checkout).
- Both `ruff check .` and `ruff format --check .` before each commit that touches Python.
- `compare_baseline.py`/`update_baseline.py` tests are plain pytest, no `hass` fixture (ADR-0009 —
  both modules only read/write JSON and do arithmetic, no HA coupling).
- Once Phase 0 lands, `pytest tests/benchmarks -q` (the `perf` CI job's own invocation) also
  collects `test_compare_baseline.py` alongside the coordinator perf test — harmless (it's fast,
  plain-pytest, and always green by the time `perf` runs it), just worth knowing before reading a
  `perf` job log that has more than one test name in it.

---

## Phase 0 — `tests/benchmarks/compare_baseline.py`

### Task 0.1: `compare(results_path, baseline_path)` — within-tolerance case

**ADR honored:** ADR-0026 (measurement primitives this compares are `psutil`-based, decided
there). **Test boundary:** plain pytest, `tests/benchmarks/test_compare_baseline.py` (new file —
pure, no HA; see Step 0 below for why this needs an explicit `conftest.py` registration despite
living in `tests/benchmarks/`).

**Files:**
- Create: `tests/benchmarks/compare_baseline.py`
- Create: `tests/benchmarks/test_compare_baseline.py`
- Edit: `tests/conftest.py`

**Step 0: Register the new test file as pure-logic**

`tests/conftest.py`'s autouse fixture routes anything outside `_PURE_DIRS`/`_PURE_FILES` through
the HA harness (design doc §6). `tests/benchmarks/` is not, and cannot become, a `_PURE_DIRS`
entry — its sibling `test_coordinator_perf.py` genuinely needs `hass`. Add the new file by name to
`_PURE_FILES` instead (matches by `path.name`, so the directory doesn't matter):

```python
_PURE_FILES = frozenset(
    {
        "test_coordinator_cycle.py",
        "test_entity.py",
        "test_notification_state.py",
        "test_config_flow_translations.py",
        "test_compare_baseline.py",
    }
)
```

**Step 1: Write the failing test** — this first test only needs the "ok" case; the "REGRESSED"
row and its tolerance constant are driven into existence by Task 0.2, not here.

```python
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
```

**Step 2: Run to verify failure** —
`pytest tests/benchmarks/test_compare_baseline.py -v` →
`ModuleNotFoundError: No module named 'tests.benchmarks.compare_baseline'`.

**Step 3: Implement** — minimal version: every metric reports "ok" (no tolerance check yet; Task
0.2 adds that). Also handle a missing results file (the pytest step erroring before
`_write_report` runs) by returning a single explanatory row rather than raising — CI's
`if: always()` (Task 4.1) means this step still runs in that case.

```python
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

**Step 2: Run to verify failure** — Task 0.1's `compare()` always reports `ok`; this new test
expects a `REGRESSED` row, so it fails on the first assertion.

**Step 3: Implement** — add the tolerance check Task 0.1 deliberately left out:

```python
_TOLERANCE_PCT = 25.0  # deliberately loose first-cut threshold (design doc S4) --
                        # no real variance data exists yet to calibrate a tighter one
```

and change the per-metric row to:

```python
        status = "REGRESSED" if delta_pct > _TOLERANCE_PCT else "ok"
        rows.append(
            f"| {metric} | {base_value:.1f} | {current_value:.1f} | {delta_pct:+.1f}% | {status} |"
        )
```

**Step 4: Run to verify pass**, then re-run Task 0.1's test to confirm it still passes (10.5 vs.
10.0 is a 5% delta, well within the new 25% tolerance).

> **Amendment (issue #739):** the percentage-only tolerance shown here is superseded — a `0.0`
> baseline (which `median_rss_delta_kb` legitimately has at this iteration count) makes a
> percentage delta undefined, so the shipped `compare_baseline.py` adds a per-metric
> absolute-tolerance fallback for that case. See `tests/benchmarks/compare_baseline.py`.

**Step 5: Commit** — `feat: flag regressions beyond tolerance in compare_baseline (issue #708)`.

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
from datetime import date

from tests.benchmarks.update_baseline import update


def test_update_overwrites_the_medians_and_recorded_at_and_nothing_else(tmp_path):
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
    assert updated == {
        "median_cpu_ms": 11.0,
        "median_rss_delta_kb": 110.0,
        "median_peak_traced_memory_kb": 1100.0,
        "recorded_at": date.today().isoformat(),
    }
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

> **Amendment (issue #739):** the sketch below is **superseded** — see the amendment at the top of
> this document. The shipped test uses `time.process_time()` rather than `_process.cpu_times()`
> (ADR-0029), and splits `_measure_one_batch` into `_measure_cpu_and_rss` (tracemalloc explicitly
> not running) and `_measure_peak_memory` (its own tracemalloc window), because tracing inside the
> CPU/RSS window polluted both readings. Read
> `tests/benchmarks/test_coordinator_perf.py` for the current code; the sketch is kept here only as
> the historical record.

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

> **Amendment (issue #739):** `psutil.cpu_times()` is **no longer** the CPU primitive — stdlib
> `time.process_time()` replaces `time.perf_counter()` instead (ADR-0029); `psutil` remains only
> for RSS (ADR-0026). The `time` import therefore stays. See
> `tests/benchmarks/test_coordinator_perf.py`.

The four new ceilings (`_MAX_MEDIAN_CPU_MS`, `_MAX_MAX_CPU_MS`, `_MAX_MEDIAN_RSS_DELTA_KB`,
`_MAX_MEDIAN_PEAK_MEMORY_KB`) are **placeholders, not derived from real data** — design doc §3.1
explains why (no trustworthy measurement exists yet to derive them from; Phase 3 seeds the first
one). Also update the module docstring (currently: "Ceilings are deliberately generous... until a
real baseline exists" — issue #266's original wording) to reference issue #708/ADR-0026 instead of
#266, keeping the same "deliberately generous placeholder" framing since it's still accurate.

**Step 3: Run to verify pass** — `pytest tests/benchmarks -q` locally (or under WSL on Windows,
per this project's existing HA-harness convention).

**Step 4: Commit** — `refactor: measure coordinator perf with psutil CPU/RSS + multi-batch stats (ADR-0026, issue #708)`.

---

## Phase 3 — Seed the first real baseline

### Task 3.1: Record the first `baseline.json` from real CI output

**ADR honored:** ADR-0026. **Test boundary:** none — this task records data, it doesn't add code.

**Files:**
- Create: `tests/benchmarks/baseline.json`

**Step 1:** Push Task 2.1's commit on its PR branch and let the `perf` CI job run once (or run
`PERF_RESULTS_DIR=/tmp/perf-results pytest tests/benchmarks -q` locally/under WSL and use that
output — either is a legitimate seed per the design doc, since there is no prior trustworthy
baseline to preserve). **This dual path is only available before Task 4.1 lands** (issue #729
scopes `perf` to `push` on `main` only, so a PR-branch push stops triggering it) — once Task 4.1
is done, any future re-seed can only come from a local/WSL run or a real push-to-`main` run's
output, not from a PR's own CI.

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

### Task 4.1: Add the `compare_baseline.py` step, scope `perf` to `push` only, and stop the `test` job from also collecting `tests/benchmarks`

**ADR honored:** ADR-0026. **Test boundary:** none — CI YAML only, verified by the next CI run.

**Files:**
- Edit: `.github/workflows/ci.yml`

**Step 1: Implement the comparison step** — in the `perf` job (`.github/workflows/ci.yml:80-103`),
move `PERF_RESULTS_DIR` to the job's own `env:` block (currently only the `pytest`
step sets it inline) and add one new step immediately after `pytest tests/benchmarks -q`, before
`actions/upload-artifact`:

```yaml
  perf:
    ...
    env:
      PERF_RESULTS_DIR: ${{ runner.temp }}/perf-results
    steps:
      ...
      - run: pytest tests/benchmarks -q
      - run: python tests/benchmarks/compare_baseline.py "$PERF_RESULTS_DIR/coordinator_cycle.json" tests/benchmarks/baseline.json >> "$GITHUB_STEP_SUMMARY"
        if: always()
      - uses: actions/upload-artifact@v7
        ...
```

`compare_baseline.py` is already runnable as a script (its `if __name__ == "__main__":` block was
added in Task 0.1). No `permissions:` change in `ci.yml` — the step only reads `baseline.json`
(already checked out) and the results directory, and writes to `$GITHUB_STEP_SUMMARY`, not to the
repo.

**Step 2: Scope `perf` to `push` only** (design doc §4 amendment, issue #729) — `perf` currently
inherits the workflow's shared `pull_request` + `push` trigger, running on every PR attempt too.
Add a `github.event_name == 'push'` clause to the job's existing `if:`:

```yaml
    if: always() && github.event_name == 'push' && (needs.changes.result != 'success' || needs.changes.outputs.code == 'true')
```

Per `ci.yml`'s own header comment, `perf` isn't a required status check (only `lint`/`test`/
`hassfest`/`hacs` are), so it's safe for it to simply report **skipped** on a `pull_request` event
rather than needing the "always report skipped" fail-safe that comment describes for the required
jobs — confirm this against the repo's actual branch-protection settings (Settings → Branches)
before merging this task, since the comment is a paraphrase, not the authoritative source. Update
that same header comment (lines 9-14) to note `perf` as a deliberate exception to the "every job
reports skipped via the shared `if:`" pattern it describes — otherwise the comment goes stale the
moment this step lands.

**Step 3: Fix the pre-existing `test`-job gap** (design doc §4/§5) — the merge-blocking `test` job
(`.github/workflows/ci.yml`, the `test:` job) runs bare `pytest -q`, which `pyproject.toml`'s
`testpaths = ["tests"]` already expands to include `tests/benchmarks/test_coordinator_perf.py`
*without* the `perf` job's `continue-on-error: true` protecting it. Change that job's step:

```yaml
      - run: pytest -q --ignore=tests/benchmarks || [ $? -eq 5 ]
```

This is what makes the "`perf` stays advisory" decision (§5) actually true instead of only true
for one of the two jobs that run it.

**Step 4:** No new automated test — this is CI YAML, verified by observing the next real workflow
run: a PR run's job list shows `perf` skipped (Step 2), a push-to-`main` run's `perf` job summary
shows the comparison table (Step 1), and the `test` job's log no longer mentions
`test_coordinator_perf.py` (Step 3). Note this verification step explicitly in the PR description
so the human reviewer checks the Actions tab, not just the diff.

**Step 5: Commit** — `ci: compare perf results against the committed baseline, run perf on push to main only, and stop the required test job from also gating on it (issue #708, #729)`.

---

## Phase 5 — Final verification

### Task 5.1: Full regression pass

**ADR honored:** ADR-0009, ADR-0026. **Test boundary:** full suite.

**Files:** none changed — verification only.

**Step 1:** `pytest tests/` (entire suite) — must pass in full, including the two new
`compare_baseline`/`update_baseline` tests and the rewritten perf test.

**Step 2:** `ruff check .` and `ruff format --check .` on the whole repo.

**Step 3:** Confirm `git diff` touches only `tests/benchmarks/`, `tests/conftest.py`,
`requirements-test.txt`, and `.github/workflows/ci.yml` — no `custom_components/` file changed
(this slice's own success criterion, design doc §1).

**Step 4: Report** — plan complete; issue #708 implemented, no coordinator behavior change, full
suite green, first real baseline committed.
