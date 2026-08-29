# ADR-0029: stdlib `time.process_time()` for perf-test CPU measurement, `psutil` retained for RSS

Date: 2026-08-29
Status: Accepted

## Context

ADR-0026 adopted `psutil` for both halves of the coordinator perf suite's real-cost
measurement: `psutil.Process().cpu_times()` for CPU time and
`psutil.Process().memory_info().rss` for resident memory, each sampled before/after a
measured batch to compute an isolated delta.

Issue #739 (a follow-up surfaced by fresh-agent review during T2.1/#725 and T3.1/#726)
found that the CPU half doesn't hold up in practice. `psutil.Process().cpu_times()`
reads `/proc/<pid>/stat` on Linux, whose `utime`/`stime` fields are counted in clock
ticks (`USER_HZ`, almost always 100 Hz, i.e. 10ms resolution) — the kernel's own
accounting granularity, not something `psutil` can read more finely. `median_cpu_ms` is
a *per-iteration* value (`(cpu_after - cpu_before) * 1000 / _ITERATIONS`); at this
suite's `_ITERATIONS = 200` cycles per batch, one tick's 10ms quantization is
`10 / 200 = 0.05` ms/iteration — already a 50% swing on the committed baseline's
`median_cpu_ms: 0.1`, well over `tests/benchmarks/compare_baseline.py`'s 25% regression
tolerance. Run-to-run noise in the reported metric is therefore dominated by which side
of a 10ms-per-batch boundary the batch happened to land on, not by any real change in
the coordinator cycle's cost.

ADR-0026 compared `psutil` against stdlib `resource.getrusage(RUSAGE_SELF)` and rejected
it — but that rejection was about `ru_maxrss` (RSS), a monotonic whole-process
high-water mark that contaminates across test functions sharing one pytest process. It
never separately evaluated a stdlib primitive for CPU time alone. Python's stdlib
already has one purpose-built for exactly this: `time.process_time()`, which returns the
sum of system and user CPU time for the calling process as a float in seconds, backed
by `clock_gettime(CLOCK_PROCESS_CPUTIME_ID)` on Linux — sub-microsecond resolution, not
a 10ms clock tick. Like `cpu_times()`, it is a monotonically increasing counter since an
unspecified starting point (an implementation detail, not guaranteed to be process
start), so a before/after delta isolates one batch's cost the same way the current code
already does regardless of what that starting point is; it carries none of
`ru_maxrss`'s high-water-mark problem, because that problem is specific to a *peak*
memory reading, not a cumulative-time counter.

RSS is unaffected by this gap: `memory_info().rss` remains a *current* value (not a
high-water mark), and `psutil` remains the only primitive in ADR-0026's comparison set
with that property. This decision revisits only the CPU-time half; ADR-0026 remains the
authoritative record for the RSS/`psutil` rationale even after its Status changes below.

## Considered options

### Option A — stdlib `time.process_time()` for CPU, keep `psutil` for RSS

- Pro: backed by `clock_gettime(CLOCK_PROCESS_CPUTIME_ID)` on Linux — a nanosecond-
  resolution kernel clock, unlike `psutil.cpu_times()`, which reads `/proc/<pid>/stat`'s
  `USER_HZ`-quantized `utime`/`stime` fields. Same kernel-level CPU-time accounting
  concept, a different (finer-grained) interface onto it — closing the quantization gap
  `cpu_times()` cannot close no matter how it's called.
- Pro: stdlib, no new dependency for the metric this ADR changes — `psutil` is already
  a dependency (kept for RSS), so this doesn't reduce the project's dependency surface,
  but it also doesn't add to it.
- Con: introduces a second measurement library/primitive alongside `psutil` in the same
  test file (one for CPU, one for RSS) rather than a single primitive for both — a minor
  cognitive-load cost the `_measure_one_batch` docstring (which already names ADR-0026
  by number) must call out explicitly so a future reader doesn't assume both metrics
  share one clock source.

### Option B — keep `psutil.Process().cpu_times()`, raise `_ITERATIONS` substantially

Increase iterations per batch (e.g. 200 → 2,000+) so that one clock tick's quantization
becomes a small fraction of the measured total, without changing the primitive.

- Pro: no new primitive to reason about — CPU and RSS keep sharing one measurement
  library (`psutil`), preserving ADR-0026's single-primitive shape.
- Con: doesn't close the gap so much as dilute it — the *absolute* quantization error
  per batch is unchanged (still up to one tick, ~10ms), so the fix is really "make the
  denominator big enough that 10ms/N stays under tolerance," which trades CI job runtime
  (each perf run already takes non-trivial wall-clock time across 11 batches) for a
  workaround rather than a resolution improvement, and the tolerance-vs-iteration-count
  relationship would need re-deriving any time `_TOLERANCE_PCT` or the ceiling constants
  change.

### Option D — stdlib `resource.getrusage(RUSAGE_SELF)`'s `ru_utime`/`ru_stime` for CPU

`ru_utime`/`ru_stime` are `timeval`s (microsecond-resolution, not `USER_HZ`-quantized),
cumulative since process start — the CPU-time fields of the same `getrusage` call whose
`ru_maxrss` field ADR-0026 rejected for RSS.

- Pro: stdlib, same family as Option B's "no new primitive" framing — a single stdlib
  call already sampled elsewhere in the codebase's ADR history (ADR-0026's Option B)
  rather than introducing `time.process_time()` as a third measurement API.
- Con: `getrusage` returns a `struct rusage` whose *other* field (`ru_maxrss`) is the
  exact high-water-mark/unit-ambiguity trap ADR-0026 rejected — reintroducing any part
  of that struct risks a future edit reaching for `ru_maxrss` by proximity.
  `time.process_time()` is the narrower, purpose-built primitive for exactly one thing
  (process CPU time as a plain float), with no adjacent attractive-nuisance field.

### Option C — do nothing (accept quantization-dominated CPU trend signal)

- Pro: zero implementation cost; the suite still functions as a coarse tripwire (its
  `_MAX_MEDIAN_CPU_MS = 20.0`/`_MAX_MAX_CPU_MS = 30.0` absolute ceilings, unaffected by
  this issue, sit ~200x/300x above the `0.1` ms baseline, so they still catch a
  two-orders-of-magnitude regression even though the trend signal below that is noise).
- Con: leaves the *trend-tracking* half of epic #706's stated goal — the reason
  `compare_baseline.py` and a committed rolling baseline exist at all — unable to detect
  any real regression smaller than one clock tick's swing, which is the majority of
  plausible regressions in a sub-millisecond hot path.

## Decision

Adopt **Option A**: switch the CPU metric to stdlib `time.process_time()`, sampled
before/after each batch exactly as `cpu_times()` is today, and keep
`psutil.Process().memory_info().rss` unchanged for the RSS metric. Option B was
rejected because it doesn't fix the underlying resolution problem, only shrinks its
relative size at the cost of CI runtime and a tolerance/iteration-count coupling that
would need re-deriving later. Option C was rejected because it leaves epic #706's
trend-tracking goal unmet for the CPU metric specifically, with only a coarse ~200x
tripwire remaining. Option D was rejected because, while it would also close the
resolution gap, it reaches for one field of a struct whose sibling field (`ru_maxrss`)
is a known trap this project already rejected once — `time.process_time()` gives the
same resolution improvement with no adjacent misuse risk. Option A's cognitive-load con
(two measurement primitives in one file) is judged acceptable because the two metrics
already measure conceptually different things (CPU time vs. resident memory) and the
`_measure_one_batch` docstring is sufficient to keep the distinction clear.

This decision does not reopen ADR-0026's RSS rationale: `memory_info().rss`'s
current-value property (vs. `resource.getrusage`'s `ru_maxrss` high-water mark) is
untouched by this change, since `time.process_time()` is a cumulative counter like
`cpu_times()` was, not a peak reading.

## Consequences

- `tests/benchmarks/test_coordinator_perf.py`'s `_measure_one_batch` replaces
  `_process.cpu_times()` before/after sampling with `time.process_time()` before/after
  sampling for the CPU delta; the RSS sampling via `_process.memory_info().rss` is
  unchanged. `docs/plans/2026-08-17-real-perf-tests-design.md` needs a matching update
  to its §2 measurement-primitive sketch and its ADR-0026 cross-reference.
- The committed `tests/benchmarks/baseline.json` `median_cpu_ms` value was seeded under
  the old `cpu_times()` primitive; it must be re-seeded (via
  `tests/benchmarks/update_baseline.py`, the existing human-run process — ADR-0026's
  Consequences already established this is never CI-automated) once the new primitive
  ships, since the two primitives are not directly comparable and the old baseline's
  quantized value is not a meaningful starting point for the new one's finer-grained
  readings.
- Issue #739's other two items (`tracemalloc`'s measurement window overlapping the
  CPU/RSS window; the seeded `median_rss_delta_kb` baseline being exactly `0.0`, which
  disables that metric's regression check) are implementation/test-design fixes, not
  primitive/architecture choices, and are addressed alongside this ADR's implementation
  work rather than in a separate ADR.
- `docs/adl/0026-psutil-for-perf-test-cpu-rss-measurement.md`'s Status becomes
  `Superseded by ADR-0029`; its Context/Decision/Consequences are left untouched per this
  project's ADR-immutability rule. `psutil` remains a pinned `requirements-test.txt`
  dependency for the RSS metric — this ADR does not remove it.
