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

R3's row-2 clamp exists specifically to avoid under-clamping the charger below what the
household can safely draw, so this merge rule has direct billing-protection-safety
consequences, not just a display/cosmetic one. When the external role is unmapped or its
reading is unavailable, all options below fall back to the internally-tracked value alone
(the same optional-role default ADR-0030 establishes for the role itself) — that fallback
case is not itself a point of disagreement between the options and is not re-litigated per
option below.

## Considered options

### Option A — `max(external, internal)`

`resolve_effective_peak_limit` receives `max(external_reading, monthly_peak_kw)` in place of
today's bare `monthly_peak_kw`.

- Pro: Can raise the effective floor to match either source's own observation, but never
  lower it below what either has independently recorded — directly matches the under-report
  scenario that motivated ADR-0030 (external already at 4.09 kW, internal tracker at the
  peak floor of 2.5 kW for a month it never fully observed: `max` immediately reflects
  4.09 kW), and the internal tracker can still push the peak higher between external sensor
  refreshes (a spike this integration observes live that the external sensor hasn't reported
  yet is not discarded).
- Con: `max()` only ever *relaxes* R3's clamp, so it is exactly as exposed to a too-**high**
  external reading as it is protected against a too-low internal one: a unit mismatch (W
  mapped where kW is expected), the wrong entity mapped, or a DSO sensor that hasn't yet
  rolled over to the new month while the internal tracker correctly has, would all raise the
  effective peak and stay stuck there for the rest of the month with no way back down —
  there is no external-reading ceiling below `maximum peak` in this option as stated.
  Two independently-sourced peaks also now feed one number with no single reading a user can
  point to as "the" peak, including on the existing `monthly_peak_kw` owned entity, which
  would then read *lower* than the value actually driving the clamp.

### Option B — External always wins when mapped

`resolve_effective_peak_limit` uses the external reading exclusively whenever the role is
mapped and its reading is available, ignoring the internally-tracked monthly peak demand
entirely.

- Pro: Single source of truth once configured — whatever the DSO/smart-meter reports is
  authoritative, simplest mental model, no need to explain a blended value anywhere, and a
  stale/wrong external reading cannot be compounded by also taking the internal tracker's
  max — the external sensor's own correction on its next refresh is the only thing that
  changes the effective peak.
- Con: A spike the internal tracker observes between external sensor refreshes (DSO sensors
  commonly update on a slower cadence — daily or on billing-cycle boundaries, not every
  coordinator cycle) is silently discarded even though the household's own live power draw
  already exceeded it — reintroduces a narrower version of the exact under-clamping risk
  ADR-0030 exists to close, just shifted from "integration wasn't running" to "the
  integration's own tracker is more current than the external sensor right now."

## Decision

**Option A**, `max(external, internal)`, **with the external operand capped at
`maximum peak`** before the `max()` is taken — closing Option A's stated Con about an
unbounded too-high external reading by reusing the ceiling `resolve_effective_peak_limit`
already enforces via its own `min(..., max_peak_kw)` step, rather than introducing a new
one. With that cap in place, Option A remains the only one of the two that can never make
the effective peak *lower* than either independently-tracked source, in both directions
Option B leaves exposed: the original integration-was-off scenario and the narrower
stale-external-sensor-cadence scenario. Option B's simpler single-source-of-truth story is
real, but it is a legibility win purchased at the cost of the exact safety property row 2
exists for, and does not fully close the risk Option A's own Con raises (a wrong-unit or
stale external reading is just as authoritative under Option B, with no internal-tracker
value to catch it). The remaining legibility concern — a blended number with no single
reading a user can point to as "the" peak — is addressed structurally below, not by
changing the merge rule.

## Consequences

- `resolve_effective_peak_limit` (or its caller, the coordinator) gains a merge step
  computing `min(max(external_reading, monthly_peak_kw), max_peak_kw)` before today's
  `min(max(monthly, floor), max)` clamp — exact call-site placement and signature change
  belong to the implementation spec, not this ADR.
- `monthly_peak_kw`'s existing meaning ("the integration's own tracked peak") is unchanged;
  the merged value used by `resolve_effective_peak_limit` becomes a distinct, larger-scoped
  quantity — naming that distinction (e.g. `effective_monthly_peak_kw` vs `monthly_peak_kw`)
  and updating the `monthly_peak_kw` owned entity's display (or adding a second entity for
  the merged figure) so it doesn't read lower than the value actually driving the clamp, is
  deferred to the implementation spec.
- This ADR extends ADR-0021's adapter-readings diagnostic sensor contract: today that
  sensor's attributes cover only wired *read-adapter-role* values, which would already
  include the external role's own raw reading (per ADR-0030), but not `monthly_peak_kw` or
  the merged result (neither is an adapter-role reading). Surfacing all three there —
  external raw value, internal tracker value, and the merged result — is adopted as part of
  this decision, to give users the breakdown Option A's legibility Con calls for; the
  implementation spec must add that attribute explicitly rather than relying on the
  existing default.
- The requirement and the guided-config-flow use case for this strand can now proceed
  against a settled merge rule, including the `maximum peak` cap.
- A glossary entry is needed for the new merged quantity once the implementation spec names
  it, alongside the existing `monthly peak demand` term.
