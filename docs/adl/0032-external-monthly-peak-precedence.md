# ADR-0032: External monthly-peak sensor — precedence semantics

Date: 2026-08-31
Status: Proposed

## Context

ADR-0030 adds an optional adapter role, `ROLE_MONTHLY_PEAK_EXTERNAL`, mapping an external
DSO/smart-meter monthly-peak sensor. Once that role is mapped, the coordinator has two
independently-sourced readings of the same underlying quantity each cycle: the external
role's reading, and the internally-tracked monthly peak demand from
`update_monthly_peak_demand` (`engines/peak_demand_tracker.py`). `resolve_effective_peak_limit`
(`engines/billing_protection.py`) takes a single monthly-peak operand for its row-2 clamp —
this ADR decides which of the two (or what combination) feeds it when both are present.

R3's row 2 exists to keep charging from raising the household's real monthly peak demand
above the effective peak limit; within it, the peak floor sub-part exists so a low or
not-yet-established monthly peak demand doesn't resolve the effective peak limit down near
0 kW and needlessly block charging. The scenario motivating ADR-0030/this ADR is an instance
of the floor problem — the tracked monthly peak demand under-representing the real one — so
a merge rule that fixes it has to be judged against both halves of row 2's purpose: does it
still let a too-low internal reading be raised (the goal), and does it risk letting a too-high
reading raise the limit further than R3's own purpose intends (the failure mode to avoid)?

When the external role is unmapped or its reading is unavailable, all options below fall
back to the internally-tracked value alone (the same optional-role default ADR-0030
establishes for the role itself) — that fallback case is not itself a point of disagreement
between the options and is not re-litigated per option below.

## Considered options

### Option A — `max(external, internal)`

`resolve_effective_peak_limit` receives `max(external_reading, monthly_peak_kw)` in place of
today's bare `monthly_peak_kw`; the function's own existing `min(..., max_peak_kw)` step
already bounds the result, unchanged.

- Pro: Can raise the effective floor to match either source's own observation, but never
  lower it below what either has independently recorded — directly matches the under-report
  scenario that motivated ADR-0030 (external already at 4.09 kW, internal tracker low or
  not-yet-established for a month it never fully observed, and floored to 2.5 kW downstream
  by `resolve_effective_peak_limit` itself: `max` immediately reflects the external 4.09 kW),
  and the internal tracker can still push the peak higher between external sensor refreshes
  (a spike this integration observes live that the external sensor hasn't reported yet is
  not discarded).
- Con: `max()` only ever *relaxes* row 2, so it is exactly as exposed to a too-**high**
  external reading as it is protected against a too-low internal one: a unit mismatch (W
  mapped where kW is expected), the wrong entity mapped, or a DSO sensor that hasn't yet
  rolled over to the new month while the internal tracker correctly has, would all raise the
  effective peak limit — bounded by `maximum peak` (the function's existing ceiling, not a
  new one this option adds), but for as long as the bad reading persists, charging would
  itself be allowed to draw up to that higher limit, which is the real monthly peak demand
  this project bills against — the exact outcome R3 exists to prevent, not merely a display
  artifact. Of the three causes, only a persistent unit mismatch stays wrong indefinitely; a
  DSO rollover or a corrected mapping self-corrects on its next read, since the merge is
  computed fresh each cycle at the call site and never overwrites the internally-tracked
  value.

### Option B — External always wins when mapped

`resolve_effective_peak_limit` uses the external reading exclusively whenever the role is
mapped and its reading is available, ignoring the internally-tracked monthly peak demand
entirely.

- Pro: Single source of truth once configured — whatever the DSO/smart-meter reports is
  authoritative, simplest mental model, and a stale/wrong external reading is not compounded
  by also taking the internal tracker's max — the external sensor's own correction on its
  next refresh is the only thing that changes the effective peak limit.
- Con: A spike the internal tracker observes between external sensor refreshes (DSO sensors
  commonly update on a slower cadence — daily or on billing-cycle boundaries, not every
  coordinator cycle) is silently discarded even though the household's own live power draw
  already exceeded it — reintroduces a narrower version of the exact under-report risk
  ADR-0030 exists to close, just shifted from "integration wasn't running" to "the
  integration's own tracker is more current than the external sensor right now."

### Option C — External reading seeds the internal tracker, one published quantity

Instead of merging two values at the call site, feed the external reading into
`update_monthly_peak_demand`'s own state each cycle — e.g. `max(tracked_kw, external_reading)`
computed as part of updating `tracked_kw` itself — so `monthly_peak_kw` remains the single
quantity `resolve_effective_peak_limit` and every consumer (including the
`monthly_peak_kw` owned entity) reads, now permanently informed by the external source
whenever it disagrees upward.

- Pro: No second operand at the call site and no second published number to reconcile —
  `monthly_peak_kw` stays "the" monthly peak demand everywhere it's read, including the
  existing owned entity, and Option A's two-numbers legibility concern does not arise.
- Con: A bad external reading (wrong unit, wrong entity, stale pre-rollover value) is no
  longer a per-cycle operand that self-corrects on its next read (as Option A's is) — it
  gets folded permanently into the tracker's own running state for the month, the same state
  the `MonthlyPeakSensor`'s restore-on-restart behavior (ADR-0030's Context) persists across
  restarts. Recovering from a bad seed would need an explicit correction, not just fixing
  the mapping. It also changes `update_monthly_peak_demand`'s contract (currently a pure
  function of the smoothed reading and the month) to take a second input, a broader change
  than either Option A or B needs.

## Decision

**Option A**, `max(external, internal)`. Option C keeps a single published quantity, which
is a real simplicity win, but at the cost of making a bad external reading permanent for the
tracked month instead of self-correcting per cycle (Option A's own Con, resolved for two of
its three causes; Option C's Con notes it is not resolved for any of them) — a heavier
structural cost for the readability it buys, and it changes a currently pure function's
contract to do so. Option B's simpler single-source-of-truth story is real, but it does not
fully close the risk Option A's own Con raises either (a wrong-unit or stale external
reading is just as authoritative under Option B, with no internal-tracker value to catch
it), while giving up Option A's Pro of the internal tracker still catching a live spike
between external refreshes. Option A's residual risk — a bad external reading raising the
effective peak limit as high as `maximum peak` for as long as it persists — is accepted
because `maximum peak` is itself the ceiling the system is otherwise willing to charge to
under deadline urgency (row 1); this decision does not introduce a way to exceed that
ceiling, it only makes row 2 reach it under a wrong reading the same way row 1 already can
under urgency.

## Consequences

- `resolve_effective_peak_limit` (or its caller, the coordinator) gains a merge step
  computing `max(external_reading, monthly_peak_kw)` as the value passed into today's
  `min(max(monthly, floor), max)` clamp — exact call-site placement and signature change
  belong to the implementation spec, not this ADR.
- `docs/analysis/resolution-rules.md`'s row-2 formula and `docs/analysis/entity-catalog.md`'s
  description of `sensor.smart_charging_effective_peak_limit` both currently state the
  operand as bare monthly peak demand; both need updating to reflect the merged operand once
  the implementation spec lands.
- `monthly_peak_kw`'s existing meaning ("the integration's own tracked peak") is unchanged;
  the merged value used by `resolve_effective_peak_limit` becomes a distinct, larger-scoped
  quantity. `sensor.smart_charging_effective_peak_limit` already exposes the resolved value
  that actually drives the clamp, so the merge is not invisible to a user — the
  `monthly_peak_kw` owned entity, however, would then show a number lower than the one
  driving the clamp whenever the external reading is higher; whether that needs a rename,
  a second entity, or no change beyond documentation is deferred to the implementation spec.
- Whether the external role's raw reading, alongside `monthly_peak_kw`, is also worth
  surfacing on the ADR-0021 adapter-readings diagnostic sensor (today scoped to wired
  read-adapter-role values, which already includes the external role's raw reading by the
  existing default, but not `monthly_peak_kw` or the merged result) is left open as
  optional follow-up, not decided here — extending that sensor's attribute contract to
  non-adapter-role values is a separate structural choice ADR-0021 does not itself make.
- The requirement and the guided-config-flow use case for this strand can now proceed
  against a settled merge rule.
