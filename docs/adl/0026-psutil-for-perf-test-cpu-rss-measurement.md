# ADR-0026: psutil for CPU-time/RSS measurement in perf tests

Date: 2026-08-17
Status: Accepted

## Context

The M1 control-cycle performance suite currently measures the hot path with
`time.perf_counter()` (wall-clock elapsed time) and `tracemalloc` (traced
Python allocations, peak bytes). A real performance-test design needs a
concrete measurement primitive for CPU cost and process memory before it can
spec replacement assertions, reporting shape, and trend tracking.

Wall-clock time is noisy on shared CI runners -- it captures scheduler
contention and neighbour load, not the cycle's own CPU cost. `tracemalloc`
only sees allocations the CPython allocator instruments; it misses
C-extension/native memory and doesn't report the process's actual resident
set (RSS), which is what an operator's host actually pays for.

The suite needs to measure:

1. **CPU time consumed by the process**, not wall-clock time elapsed.
2. **Real process memory (RSS)**, not just traced Python allocations.

The perf test exercises the coordinator's HA-harness (`pytest-homeassistant-
custom-component`) fixture, which imports the Unix-only `fcntl` module, so
this suite already cannot run natively on Windows -- Windows contributors run
it under WSL (Linux), same as CI (`ubuntu-latest`). Cross-platform reach is
therefore *not* the deciding factor between the candidate primitives below;
both a POSIX-only and a cross-platform primitive would run everywhere this
suite already runs. The deciding factor is measurement semantics within a
single, long-lived pytest process: `pytest` runs every test function in one
process, so a primitive whose value is a monotonic, whole-process high-water
mark (never resets) will have one test's allocations bleed into the next
test's measurement, whereas a primitive that reports a *current* value can be
sampled before and after the measured block to compute an isolated delta.

## Considered options

### Option A -- `psutil` (new third-party dependency)

`psutil.Process().cpu_times()` for user+system CPU seconds attributable to the
process, and `psutil.Process().memory_info().rss` for current resident
memory, sampled before/after the measured block to compute a delta.

- Pro: `memory_info().rss` reports the *current* resident set, not a
  process-lifetime high-water mark -- sampling before/after each measured
  block isolates that block's contribution and avoids contamination from
  whatever earlier tests in the same pytest process allocated.
- Con: Still whole-process CPU/RSS, so a before/after delta includes
  scheduling noise from the harness and any background work pytest itself
  does around the measured block, not a pure per-call attribution the way
  `tracemalloc`'s start/stop pair attributes allocations to code run between
  those calls. Also adds a new third-party dependency to maintain (version
  pin, supply-chain surface, CI install time) for a test-only concern.

### Option B -- stdlib `resource.getrusage(RUSAGE_SELF)`

`resource.getrusage(resource.RUSAGE_SELF)` exposes `ru_utime`/`ru_stime`
(user/system CPU seconds, cumulative since process start) and `ru_maxrss`
(peak RSS -- KB on Linux, **bytes on macOS**, a portability trap if a
contributor ever runs this on macOS).

- Pro: No new dependency -- stdlib only, zero install/pin/supply-chain cost.
- Con: `ru_maxrss` is a monotonic, whole-process high-water mark that never
  resets between test functions -- in a shared pytest process, a memory-heavy
  test that runs earlier permanently inflates every later test's `ru_maxrss`
  reading, with no way to isolate one test's own peak. `ru_utime`/`ru_stime`
  have the same cumulative-since-start property for CPU time, requiring a
  before/after delta (`getrusage` supports that; `ru_maxrss` does not).

### Option C -- status quo (wall-clock + tracemalloc), statistical treatment only

Keep the current primitives; only add multiple runs, warm-up discard, and
median/p95 reporting on top of them.

- Pro: `tracemalloc`'s `start()`/`stop()` pair genuinely attributes traced
  allocations to the code run between those calls, scoped to one measured
  block -- a real per-block attribution `psutil`/`resource` don't have. Also
  lowest cost: no new dependency, no primitive change, ships fastest.
- Con: Doesn't close the gap this ADR exists to close -- wall-clock time
  still isn't CPU time (shared-runner noise stays baked into the ceiling),
  and `tracemalloc` still isn't RSS (native/C-extension memory and real
  OS-level resident memory stay invisible).

## Decision

Adopt **Option A, `psutil`**. The decisive property is `memory_info().rss`
reporting a *current* value: sampled before and after the measured block, it
yields a delta isolated to that block, avoiding the cross-test contamination
that Option B's monotonic `ru_maxrss` high-water mark cannot avoid in a
shared pytest process. Option B's stdlib-only cost saving doesn't offset that
measurement-semantics gap, and its `ru_maxrss` unit ambiguity (KB on Linux,
bytes on macOS) is an additional portability trap. Option C was rejected
because it doesn't address the CPU-time/RSS gap this decision exists to
close, though its `tracemalloc` per-block attribution is a real property
worth keeping alongside `psutil` rather than discarding -- the two primitives
answer different questions (CPU/RSS cost vs. Python-allocation attribution)
and can complement each other in the resulting test design.

`psutil` is added to `requirements-test.txt` only (test-only concern, never
shipped in the HACS package `custom_components/smart_charging/manifest.json`),
pinned to an exact version the same way `homeassistant`, `pytest-
homeassistant-custom-component`, and `ruff` are pinned in that file.

## Consequences

- `requirements-test.txt` gains a pinned `psutil==<version>` entry; the perf
  CI job's `pip install -r requirements-test.txt` step picks it up with no
  workflow changes needed.
- The performance-test design that follows this decision names
  `psutil.Process().cpu_times()` and before/after
  `psutil.Process().memory_info().rss` deltas as the concrete primitives for
  the replacement assertions, multi-run/median/p95 reporting, and
  trend-tracking payload -- and decides whether `tracemalloc` stays alongside
  `psutil` for per-block allocation attribution or is dropped now that RSS is
  measured directly.
- No platform-conditional skip logic is needed in the perf suite: it already
  only runs where the HA-harness fixture runs (CI's `ubuntu-latest`, or WSL
  for local Windows contributors), and `psutil` works unchanged there.
