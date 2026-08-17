# ADR-0026: psutil for CPU-time/RSS measurement in perf tests

Date: 2026-08-17
Status: Proposed

## Context

`tests/benchmarks/test_coordinator_perf.py` (issue #266) currently measures the
M1 control-cycle hot path with `time.perf_counter()` (wall-clock elapsed time)
and `tracemalloc` (traced Python allocations, peak bytes). Issue #706 tracks
turning this tripwire into a real performance-test design; issue #708 (the
paired test-design spec) is blocked on this ADR because it needs a concrete
measurement primitive before it can spec the replacement assertions, reporting
shape, and trend tracking.

Wall-clock time is noisy on shared CI runners (`ubuntu-latest`) -- it captures
scheduler contention and neighbour load, not the cycle's own CPU cost.
`tracemalloc` only sees allocations the CPython allocator instruments; it
misses C-extension/native memory and doesn't report the process's actual
resident set (RSS), which is what an operator's host actually pays for.

The suite needs to measure:

1. **CPU time consumed by the process**, not wall-clock time elapsed.
2. **Real process memory (RSS)**, not just traced Python allocations.

Two candidate primitives exist for this in Python, plus the option of not
adding a new primitive at all. The project's CI runs perf on `ubuntu-latest`
only (`.github/workflows/ci.yml`), but CLAUDE.md and the project's WSL/local
test setup mean contributors also run the suite locally on Windows -- a
POSIX-only primitive would make the perf suite CI-only, silently skipped or
erroring for Windows contributors who run `pytest tests/benchmarks` locally.

## Considered options

### Option A -- `psutil` (new third-party dependency)

`psutil.Process().cpu_times()` for user+system CPU seconds attributable to the
process, and `psutil.Process().memory_info().rss` for real resident memory.

- Pro: Cross-platform (Linux, Windows, macOS) -- the suite runs the same way
  in CI (`ubuntu-latest`) and on a contributor's Windows machine; no
  platform-conditional skip logic needed in the test file.
- Con: Adds a new third-party dependency to maintain (version pin, supply-chain
  surface, CI install time), for a test-only concern.

### Option B -- stdlib `resource.getrusage(RUSAGE_SELF)`

`resource.getrusage(resource.RUSAGE_SELF)` exposes `ru_utime`/`ru_stime` (user/
system CPU seconds) and `ru_maxrss` (peak RSS, in KB on Linux).

- Pro: No new dependency -- stdlib only, zero install/pin/supply-chain cost.
- Con: `resource` is POSIX-only; it does not exist on Windows at all
  (`import resource` raises `ModuleNotFoundError`). Since contributors run
  this suite locally on Windows (per CLAUDE.md's environment notes), this
  would force either a Windows-only skip (silently losing local coverage) or
  a parallel Windows code path -- reintroducing the platform-branching cost
  Option A avoids, but without the cross-platform library doing it for us.

### Option C -- status quo (wall-clock + tracemalloc), statistical treatment only

Keep the current primitives; only add multiple runs, warm-up discard, and
median/p95 reporting on top of them.

- Pro: Lowest cost -- no new dependency, no primitive change, ships fastest.
- Con: Doesn't close the gap this ADR exists to close: wall-clock time still
  isn't CPU time (shared-runner noise stays baked into the ceiling), and
  `tracemalloc` still isn't RSS (native/C-extension memory and real OS-level
  resident memory stay invisible). Issue #706/#708's stated goal --
  "real performance test design (CPU/RSS)" -- would not be met.

## Decision

Adopt **Option A, `psutil`**. Cross-platform support is decisive: this
project's contributors run the perf suite locally on Windows as well as in
CI on `ubuntu-latest`, so a POSIX-only primitive (Option B) would either
silently drop local Windows coverage or require a second, parallel
measurement path -- the platform-branching cost Option B was supposed to
avoid, without actually avoiding it. Option C was rejected because it doesn't
address the actual problem #706/#708 were opened to fix.

`psutil` is added to `requirements-test.txt` only (test-only concern, never
shipped in the HACS package `custom_components/smart_charging/manifest.json`),
pinned to an exact version the same way the file's other test dependencies are
pinned (see the file's existing "Pinned after first resolve" convention).

## Consequences

- `requirements-test.txt` gains a pinned `psutil==<version>` entry; the
  `perf` CI job's `pip install -r requirements-test.txt` step picks it up
  with no workflow changes needed.
- The #708 implementation spec can now name `psutil.Process().cpu_times()`
  and `psutil.Process().memory_info().rss` as the concrete primitives to wire
  into `tests/benchmarks/test_coordinator_perf.py`'s replacement assertions,
  multi-run/median/p95 reporting, and trend-tracking payload.
- No platform-conditional skip logic is needed in the perf suite -- it runs
  identically on CI (`ubuntu-latest`) and on a contributor's local Windows
  environment.
- Follow-up: file/update the #708 implementation-spec issue referencing this
  ADR once accepted, and open a task issue for adding the pinned `psutil`
  entry to `requirements-test.txt` as part of that implementation work (the
  spec, not this ADR, performs the actual pin).
