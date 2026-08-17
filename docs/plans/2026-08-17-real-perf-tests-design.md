# Real performance tests for the coordinator — design

**Date:** 2026-08-17
**Status:** draft (issue #708, epic #706, ADR-0026)
**Type:** implementation design (test-infrastructure slice — not a `docs/design/project-plan.md`
build slice; this spec derives from the epic #706's work breakdown and
[ADR-0026](../adl/0026-psutil-for-perf-test-cpu-rss-measurement.md), the same way a feature slice's
design derives from `project-plan.md`)

This document is the follow-up implementation spec issue #708 calls for: turning
`tests/benchmarks/test_coordinator_perf.py` (issue #266's original CPU/memory tripwire) into a
real performance test — real CPU-time accounting, real process memory (RSS), multi-run statistical
treatment, and trend tracking across CI runs — per ADR-0026's decision to measure with `psutil`.

**This is test-infrastructure only: no `custom_components/` behavior change.** The coordinator's
control-cycle logic, entities, config, and events are untouched; only the test file and CI wiring
change.

---

## 1. Why this slice

Epic #706 lists three gaps in the current suite: wall-clock time instead of CPU time,
`tracemalloc`'s traced-Python-heap peak instead of real process memory (RSS), and a single sample
with no statistical treatment or trend tracking. ADR-0026 already decided the measurement
primitive (`psutil`, chosen over stdlib `resource.getrusage` because `memory_info().rss` reports a
*current* value that can be sampled before/after a block to compute an isolated delta, whereas
`getrusage`'s `ru_maxrss` is a monotonic whole-process high-water mark that contaminates across
test functions sharing one pytest process). This spec derives the concrete measurement code, the
statistical treatment, and the trend-tracking mechanism; it invents no new measurement primitive
and revisits no ADR-0026 trade-off.

| Epic #706 gap | This slice |
| --- | --- |
| Wall-clock time, not CPU time | **In scope** — replace `time.perf_counter()` with `psutil.Process().cpu_times()` before/after delta (§2) |
| `tracemalloc` peak, not RSS | **In scope** — add `psutil.Process().memory_info().rss` before/after delta *alongside* `tracemalloc` (§2); ADR-0026's Consequences left this an open choice — this spec keeps `tracemalloc` for its genuine per-block Python-allocation attribution (a property neither `psutil` metric has) while adding RSS as the real-memory signal `tracemalloc` cannot provide |
| Single sample, no statistical treatment | **In scope** — multiple batches, first batch discarded as warm-up, median (and a small-n p95 proxy) across the rest (§3) |
| No trend/evolution tracking across CI runs | **In scope** — a committed rolling baseline JSON + a comparison step, not `github-action-benchmark` (§4 explains the choice) |
| Whether `perf` stays `continue-on-error: true` | **Decided: stays advisory for now** — deferred to a follow-up issue once real trend history exists to calibrate a hard gate (§5); requires also fixing a pre-existing gap where the merge-blocking `test` job unintentionally collects `tests/benchmarks/` too (§5) |

---

## 2. Measurement primitives (per ADR-0026)

Both new primitives are sampled **before and after each batch** (not once per whole test run) —
this is what makes a delta meaningful in a single, long-lived pytest process, per ADR-0026's own
rationale.

Illustrative shape only (the coordinator's own cycle is `async`, so the paired plan's real
implementation is an `async def`, not the sync sketch below):

```python
import psutil

_process = psutil.Process()

def _cpu_ms_and_rss_delta_kb(run_batch):
    cpu_before = _process.cpu_times()
    rss_before_kb = _process.memory_info().rss / 1024
    tracemalloc.start()
    run_batch()
    _current_bytes, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    cpu_after = _process.cpu_times()
    rss_after_kb = _process.memory_info().rss / 1024
    cpu_ms = ((cpu_after.user + cpu_after.system) - (cpu_before.user + cpu_before.system)) * 1000
    return cpu_ms, rss_after_kb - rss_before_kb, peak_bytes / 1024
```

`cpu_times()` sums `user` + `system` seconds (both CPU cost, unlike wall-clock, which also counts
time the process was scheduled out) — this is the direct replacement for `time.perf_counter()`.
`rss_after_kb - rss_before_kb` is the batch's own net RSS growth, isolated from whatever earlier
batches or earlier tests in the same process already allocated. `tracemalloc` keeps its existing
per-batch `start()`/`stop()` scoping (already isolated per batch today) and keeps reporting peak
*traced Python* memory — a different, still-useful signal (per-allocation attribution) that RSS
cannot give.

---

## 3. Statistical treatment (multi-run, warm-up discard, median/p95)

A single sample is noisy on a shared CI runner (epic #706's stated gap). This slice runs
**11 batches** of the existing `_ITERATIONS = 200` cycles each, discards the **first batch as
warm-up** (JIT-free CPython has no warm-up in the traditional sense, but the first batch still
absorbs one-time costs — import caching, adapter object creation, the first `asyncio` event-loop
scheduling round — that later batches don't pay), and reports **median** and a **p95 proxy** across
the remaining 10 measured batches.

```python
_BATCHES = 11
_WARMUP_BATCHES = 1

async def _run_batches(coord):
    results = []
    for _ in range(_BATCHES):
        cpu_ms, rss_delta_kb, peak_kb = await _measure_one_batch(coord)
        results.append((cpu_ms / _ITERATIONS, rss_delta_kb, peak_kb))
    return results[_WARMUP_BATCHES:]
```

With only 10 measured batches, a statistically rigorous 95th percentile isn't meaningful — this
spec is explicit that **`p95` here means `max()` of the 10 measured batches**, documented in the
report payload and the test's own docstring as a small-n tail proxy, not a true percentile. Median
(`statistics.median`) is the primary ceiling comparator; the max/"p95" is reported for visibility
and compared against its own, more generous ceiling.

### 3.1 Ceiling selection

No trustworthy measurement exists yet to derive numeric ceilings from — that is exactly the gap
this slice closes (§4). The paired plan therefore keeps the same posture the current suite already
states in its own docstring ("deliberately generous... until a real baseline exists"): initial
ceilings are chosen generously (same order of magnitude as today's `_MAX_AVG_CYCLE_MS`/
`_MAX_PEAK_MEMORY_KB`, extended with a comparably generous RSS-delta ceiling), explicitly as
placeholders, not derived from data. Once Phase 3 (§9) seeds the first real `baseline.json`, a
human can tighten these ceilings in a small follow-up commit if the real medians run far below
them — this spec does not do that tightening itself, since it would be guessing at numbers a real
run hasn't produced yet.

---

## 4. Trend tracking: committed baseline JSON, not `github-action-benchmark`

Epic #706 named two options: wire up `github-action-benchmark`, or commit-and-diff a rolling
baseline JSON. This spec chooses the **committed baseline JSON**.

`github-action-benchmark` needs a `gh-pages` branch (or an external storage backend) to persist
history, `contents: write` permission (the workflow currently declares only `contents: read` in
its top-level `permissions:` block), and typically a bot commit back to the repo on every `main`
push —
infrastructure this project doesn't otherwise have and that sits awkwardly with the project's
"no auto-merge, no bot self-approval" posture (CLAUDE.md merge policy) applied one level down to
CI writing to branches unattended. A single committed `baseline.json`, updated **only by a human
deliberately running a script and committing the result**, keeps the same manual-approval
discipline the project already applies to every other change, at a fraction of the setup cost.

**`tests/benchmarks/baseline.json`** (new, committed to the repo):

```json
{
  "coordinator_cycle": {
    "median_cpu_ms": 12.4,
    "median_rss_delta_kb": 180.0,
    "median_peak_traced_memory_kb": 2100.0,
    "recorded_at": "2026-08-17"
  }
}
```

The first commit of this file uses the first real CI run's own output as its seed value (Task
listed in the paired plan) — there is no pre-existing trustworthy baseline today (the current
suite's ceilings are, per its own docstring, "deliberately generous... until a real baseline
exists").

**`tests/benchmarks/compare_baseline.py`** (new, invoked as a CI step, not part of the pytest run
itself — keeps the comparison logic testable and runnable standalone):

```python
def compare(results_path, baseline_path) -> list[str]:
    """Returns a list of markdown table rows (one per metric) comparing results_path's
    payload against baseline_path's stored medians, at a 25% tolerance (a deliberately
    loose first-cut threshold -- there is no real variance data yet to calibrate a
    tighter one; revisiting this number is part of the same follow-up §5 already
    schedules). Never raises/exits non-zero on a regression -- advisory only (see design
    doc S5); returns the rows for the caller to write to GITHUB_STEP_SUMMARY and to
    decide whether to fail the job in a later, separate decision. If results_path does
    not exist (the pytest step errored before writing it), returns a single row saying
    so rather than raising."""
```

Runnable as a script with two positional arguments (`results_path`, `baseline_path`) — not via an
environment variable — so the CI step and a human running it locally use the identical invocation
(paired plan Task 0.1/4.1).

**`tests/benchmarks/update_baseline.py`** (new, run locally/manually, never by CI):

```python
def update(results_path, baseline_path) -> None:
    """Overwrites baseline_path's stored medians with results_path's fresh medians. A human
    runs this deliberately after judging a new normal acceptable (e.g. after a legitimate
    coordinator change that intentionally shifts the cost), then commits baseline.json in
    its own small PR -- the same manual-approval discipline as every other change."""
```

**CI wiring** (`.github/workflows/ci.yml`'s `perf` job): one new step after the existing
`pytest tests/benchmarks -q` step, only running the comparison (no baseline mutation):

```yaml
    env:
      PERF_RESULTS_DIR: ${{ runner.temp }}/perf-results
    steps:
      ...
      - run: pytest tests/benchmarks -q
      - run: python tests/benchmarks/compare_baseline.py "$PERF_RESULTS_DIR/coordinator_cycle.json" tests/benchmarks/baseline.json >> "$GITHUB_STEP_SUMMARY"
        if: always()
```

(`PERF_RESULTS_DIR` moves to the job's own `env:` block so both steps share one definition instead
of two copies drifting apart.) No `contents: write` permission is added — the comparison step only
reads `baseline.json` (already checked out) and the fresh results directory; it writes only to the
step summary, not to the repo.

**A second, pre-existing CI fix this slice must make (§5):** `pyproject.toml`'s
`testpaths = ["tests"]` means the merge-blocking `test` job's bare `pytest -q` already collects
`tests/benchmarks/test_coordinator_perf.py` too — today's single wall-clock/tracemalloc assertion
already runs there with no `continue-on-error`, which the `perf` job's own advisory framing doesn't
protect against. This slice increases that test's cost (11 batches instead of one sample) and adds
a new, less-predictable RSS-delta assertion, so leaving this pre-existing gap unfixed would make
the "advisory only" claim false in practice. The `test` job's step becomes
`pytest -q --ignore=tests/benchmarks || [ $? -eq 5 ]` — `tests/benchmarks` keeps running only in
the dedicated, `continue-on-error: true` `perf` job (paired plan Task 4.1).

---

## 5. Decision: `perf` stays `continue-on-error: true`

Epic #706's last open question is whether `perf` should start gating merges. This spec decides
**no, not yet** — `continue-on-error: true` stays, and the `test` job's accidental collection of
`tests/benchmarks` (§4) is fixed so that job genuinely stops being a second, unintended gate on
this suite. Real CI history doesn't exist yet
(this slice produces the *first* trustworthy baseline, per §4); gating merges on a metric with no
track record risks blocking legitimate PRs on shared-runner noise the multi-run treatment (§3)
reduces but cannot eliminate. This is a deliberate deferral, not a silent one: **a follow-up issue
should be opened once `baseline.json` has accumulated a few weeks of real update history**, to
revisit whether `perf` should gate merges for a confirmed (not single-run) regression.

---

## 6. Testing (ADR-0009 harness split)

- `tests/benchmarks/test_coordinator_perf.py` keeps its existing HA-harness test boundary
  (`hass` fixture, `SmartChargingCoordinator._async_update_data`) — this doesn't change; only the
  measurement/statistics inside the one existing test function change.
- `tests/benchmarks/compare_baseline.py` and `update_baseline.py` are HA-free pure functions
  (read/write JSON, do arithmetic) → get their own **plain-pytest** tests,
  `tests/benchmarks/test_compare_baseline.py`, covering: a metric within tolerance produces no
  regression row; a metric beyond tolerance produces a row flagged as regressed; `update_baseline`
  overwrites the three median fields and `recorded_at`, and nothing else.
- `tests/conftest.py`'s autouse HA-harness fixture treats anything outside `_PURE_DIRS`/
  `_PURE_FILES` as needing `hass` (it is not itself scoped by directory beyond that check, so a
  new file under `tests/benchmarks/` — a directory that must stay HA-harness-capable for its
  sibling `test_coordinator_perf.py` — would otherwise be silently routed through the harness,
  the exact ADR-0009 mis-split this spec must not introduce). `test_compare_baseline.py` is added
  to `conftest.py`'s `_PURE_FILES` set so it collects as plain pytest despite living in that
  directory.
- No new HA-harness tests are added — the coordinator's own behavior is unchanged by this slice.

---

## 7. Packaging

```text
tests/benchmarks/
  test_coordinator_perf.py     # rewritten measurement body (S2/S3); same HA-harness test boundary
  baseline.json                 # new -- committed rolling baseline, human-updated only
  compare_baseline.py            # new -- plain function, CI-invoked, advisory (S4)
  update_baseline.py             # new -- plain function, human-invoked only, never by CI
  test_compare_baseline.py       # new -- plain pytest for the two scripts above

tests/conftest.py
  _PURE_FILES                    # + "test_compare_baseline.py" (S6)

.github/workflows/ci.yml
  test job                       # pytest -q -> pytest -q --ignore=tests/benchmarks (S4/S5 fix)
  perf job                       # env: block gains PERF_RESULTS_DIR (shared with the new step);
                                  # + one step running compare_baseline.py into GITHUB_STEP_SUMMARY
                                  #   (S4); continue-on-error: true unchanged (S5)

requirements-test.txt
  + psutil==7.2.2                 # pinned per ADR-0026; test-only, never shipped in the HACS
                                  #   package (custom_components/smart_charging/manifest.json)
```

---

## 8. Deliberately deferred

- `github-action-benchmark` or any externally-hosted trend dashboard — rejected in §4; not
  revisited here.
- Gating merges on a `perf` regression — deferred in §5 to a follow-up issue once real baseline
  history exists.
- A true statistical p95 (needs a much larger sample size than 10 batches to be meaningful) — the
  small-n max proxy (§3) is what this slice ships; a larger-N redesign is a future decision if the
  proxy proves misleading in practice.
- Any change to the coordinator's own control-cycle behavior, entities, config, or events — this
  slice is test-infrastructure only.

---

## 9. Next step

This design feeds the `writing-plans` skill to produce the ordered, test-driven implementation
plan (`2026-08-17-real-perf-tests.md`). Build order: `compare_baseline.py`/`update_baseline.py`
(test-first, plain pytest) → rewrite `test_coordinator_perf.py`'s measurement body → seed the first
real `baseline.json` from that rewritten test's own CI output → wire the CI comparison step. No
`custom_components/` code is touched at any point in this slice.
