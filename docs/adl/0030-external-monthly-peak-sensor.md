# ADR-0030: External monthly-peak sensor — adapter role + precedence semantics

Date: 2026-08-31
Status: Proposed

## Context

Monthly peak demand — the operand that `resolve_effective_peak_limit`
(`custom_components/smart_charging/engines/billing_protection.py`) reads for R3's row-2
clamp — is computed entirely from the integration's own smoothed `net_power` sampling
inside `update_monthly_peak_demand` (`engines/peak_demand_tracker.py`). That tracker only
ever sees power while HA and this integration are running. Whenever they weren't — HA down,
the integration newly added mid-month, a restart that missed a brief spike — the tracked
peak under-reports the household's real monthly peak demand for the calendar month. A
reported install hit exactly this: the integration's own tracker read the peak floor
(~2.5 kW) for a month where an external source (the household's smart meter / DSO
capacity-tariff sensor) already showed 4.09 kW for the same month.

Many DSO/smart-meter integrations already expose the utility's own tracked monthly peak
demand as an HA sensor entity, refreshed independently of this integration's own sampling.
Folding that reading in gives `resolve_effective_peak_limit` a second, independently-sourced
operand that does not depend on this integration having run continuously all month. Two
structural questions have to be settled before any requirement/UC or code work:

1. How does the external reading enter the system — what shape does the optional
   integration point take?
2. When both an external reading and the internally-tracked monthly peak demand are
   present, which one (or what combination) feeds `resolve_effective_peak_limit`? R3's
   row-2 clamp exists specifically to avoid under-clamping the charger below what the
   household can safely draw, so the merge rule has direct billing-protection-safety
   consequences, not just a display/cosmetic one.

These are two separable structural choices — Question 2's merge rule would apply just as
much if Question 1 were answered by a static config-flow value instead of a live adapter
role — but they are recorded in one ADR because the whole point of admitting an external
reading (Question 1) is what happens when it disagrees with the internal tracker
(Question 2); a decision on one without the other leaves the feature only half specified.
The **Considered options** section below is split into two clearly-labeled groups for
exactly that reason, using distinct option letters throughout so cross-references stay
unambiguous.

## Considered options

### Question 1 — integration point for the external reading

#### Option A — Do nothing (internal tracking only)

Keep `monthly_peak_kw` sourced exclusively from `update_monthly_peak_demand`; no external
input of any kind.

- Pro: No new adapter role, config-flow surface, or merge logic — zero implementation cost.
- Con: Leaves the under-report failure mode open exactly as observed — a restart or
  newly-added integration mid-month has no way to recover the real peak already reached
  that month.

#### Option B — New optional adapter role, `ROLE_MONTHLY_PEAK_EXTERNAL`

Add a role key in `const.py` alongside the other NF3 optional roles (`ROLE_LOW_TARIFF`,
`ROLE_SOLAR_FORECAST`, `ROLE_DEPARTURE_EXTERNAL`, `ROLE_HOME_DAY_EXTERNAL`), mapped via the
config flow to an HA entity (the DSO/smart-meter peak sensor). Unmapped → the role's adapter
is simply absent from the factory's built roles, same as today's optional roles (ADR-0003's
adapter-mapping mechanism, ADR-0006's per-cycle reads); mapped → the coordinator reads it
once per cycle like any other role and passes the value into the Billing-Protection engine
call, the same data path `monthly_peak_kw` already takes in from the Peak-Demand Tracker.

- Pro: Reuses a pattern this codebase already has four instances of, with no new kind of
  adapter class or coordinator-wiring mechanism to invent. The reading updates live every
  cycle from whatever the external sensor currently reports, so a DSO correction later in
  the month is picked up automatically.
- Con: Ties this feature to the household actually having (and correctly mapping) a
  DSO/smart-meter integration in HA that exposes a monthly-peak entity — some setups will
  never have one, and this role is then permanently absent, unlike a config-flow-entered
  static value the user could type in without any such integration existing. It also needs
  a config-flow home: the nine-step topic-grouped flow (ADR-0027) has no existing catch-all
  mapping step to drop this into — the natural home, `STEP_CAPTAR`, is itself gated on
  `CONF_CAPTAR_AVAILABLE`, so on a non-CapTar install this role would need either its own
  ungated step or to live somewhere the household without CapTar can still reach it.

#### Option C — Config-flow numeric field (static value, no entity mapping)

Add a plain number field to the config/options flow (e.g. "known monthly peak so far, kW")
that the user types in and updates manually, stored in the config entry like a regular
option rather than resolved through an adapter role.

- Pro: Works even for a household with no DSO/smart-meter HA integration at all — the user
  can read the number off a utility app or bill and type it in once.
- Con: Never updates itself; the moment the DSO's own reading changes mid-month (a new
  peak, a month rollover) the stored value goes stale until the user notices and re-enters
  it by hand — directly undermines the goal of never under-clamping against the *current*
  real peak, and gives this feature no live-update story the rest of NF3's optional roles
  already have for free.

#### Option D — Backfill from HA's recorder / long-term statistics

Instead of a new external source, derive the missing history from HA's own recorder:
at startup (or on a month change), query long-term statistics for the mapped `net_power`
entity across the current calendar month and seed `monthly_peak_kw` from its recorded
maximum, covering the "HA/integration wasn't running" gap without any DSO integration.

- Pro: Needs no external sensor at all — works purely from data this integration is already
  configured to read, so every install benefits, not just ones with a DSO peak sensor.
- Con: Recorder access is a Home Assistant storage-layer read, not adapter I/O — pulling it
  into an engine would violate the engine-purity boundary (system-design §4 rule 4, ADR-0010:
  no engine performs HA I/O), so it would have to live in the coordinator/a manager instead,
  adding a new HA-coupled responsibility there. Long-term statistics are also downsampled
  (hourly, sometimes 5-minute short-term) rather than the tracker's own ~15-minute smoothing
  window, so the backfilled figure would not have the same provenance as a live reading, and
  it does nothing for a genuinely new install with no prior recorder history for that month.

### Question 2 — precedence/merge semantics

Applies once Question 1's Option B is adopted: the external reading, when mapped, is a
per-cycle value alongside the internally-tracked monthly peak demand.

#### Option E — `max(external, internal)`

`resolve_effective_peak_limit` receives `max(external_reading, monthly_peak_kw)` in place of
today's bare `monthly_peak_kw` whenever the external role is mapped and its reading is not
`None`/unavailable; falls back to `monthly_peak_kw` alone when unmapped or unavailable
(NF3's existing optional-role default behavior).

- Pro: Can raise the effective floor to match either source's own observation, but never
  lower it below what either has independently recorded — directly matches the observed
  under-report scenario (external already at 4.09 kW, internal tracker restarted at 2.5 kW:
  `max` immediately reflects 4.09 kW), and the internal tracker can still push the peak
  higher between external sensor refreshes (a spike this integration observes live that the
  external sensor hasn't reported yet is not discarded).
- Con: `max()` only ever *relaxes* R3's clamp, so it is exactly as exposed to a too-**high**
  external reading as it is protected against a too-low internal one: a unit mismatch (W
  mapped where kW is expected), the wrong entity mapped, or a DSO sensor that hasn't yet
  rolled over to the new month while the internal tracker correctly has, would all raise the
  effective peak and stay stuck there for the rest of the month with no way back down —
  there is no external-reading ceiling below `maximum peak` in this option as stated.
  Two independently-sourced peaks also now feed one number with no single reading a user can
  point to as "the" peak, including on the existing `monthly_peak_kw` owned entity, which
  would then read *lower* than the value actually driving the clamp.

#### Option F — External always wins when mapped

When the external role is mapped and its reading is available, `resolve_effective_peak_limit`
uses the external reading exclusively, ignoring the internally-tracked monthly peak demand
entirely; falls back to internal-only when unmapped or unavailable.

- Pro: Single source of truth once configured — whatever the DSO/smart-meter reports is
  authoritative, simplest mental model, no need to explain a blended value anywhere, and a
  stale/wrong external reading cannot be compounded by also taking the internal tracker's
  max — the external sensor's own correction on its next refresh is the only thing that
  changes the effective peak.
- Con: A spike the internal tracker observes between external sensor refreshes (DSO sensors
  commonly update on a slower cadence — daily or on billing-cycle boundaries, not every
  coordinator cycle) is silently discarded even though the household's own live power draw
  already exceeded it — reintroduces a narrower version of the exact under-clamping risk
  this ADR exists to close, just shifted from "integration wasn't running" to "the
  integration's own tracker is more current than the external sensor right now."

## Decision

**Question 1: Option B**, a new optional adapter role `ROLE_MONTHLY_PEAK_EXTERNAL`. Option A
leaves the reported failure mode open with no mitigation at all. Option D would fix the same
gap without depending on a DSO integration, but at the cost of putting HA recorder access
somewhere in the pure-engine call path this project has kept deliberately HA-free (ADR-0010)
— a heavier structural cost than Option B's, whose only downside is not helping households
without a DSO peak sensor, which is a coverage gap rather than an architectural violation.
Option C's static-value convenience for DSO-less households does not offset losing the
live-update mechanism the other three options provide — a feature meant to close an
under-reporting gap must not introduce a new, manual one. Option B's config-flow-placement
Con (no existing ungated step) is real but is a config-flow design detail for #876 to
resolve, not a reason to reject the role shape itself.

**Question 2: Option E**, `max(external, internal)`, **with the external operand capped at
`maximum peak`** before the `max()` is taken — closing Option E's stated Con about an
unbounded too-high external reading by reusing the ceiling `resolve_effective_peak_limit`
already enforces via its own `min(..., max_peak_kw)` step, rather than introducing a new
one. With that cap in place, Option E remains the only one of the two that can never make
the effective peak *lower* than either independently-tracked source, in both directions
Option F leaves exposed: the original integration-was-off scenario and the narrower
stale-external-sensor-cadence scenario. Option F's simpler single-source-of-truth story is
real, but it is a legibility win purchased at the cost of the exact safety property row 2
exists for, and does not fully close the risk Option E's own Con raises (a wrong-unit or
stale external reading is just as authoritative under Option F, with no internal-tracker
value to catch it). The remaining legibility concern — a blended number with no single
reading a user can point to as "the" peak — is addressed structurally below, not by
changing the merge rule.

## Consequences

- `const.py` gains `ROLE_MONTHLY_PEAK_EXTERNAL` next to the other NF3 optional roles. The
  config-flow home for its mapping — a new ungated step, or a place reachable regardless of
  `CONF_CAPTAR_AVAILABLE` — is left to the guided-config-flow use case to resolve, not
  decided here.
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
  include the new role's own raw external reading, but not `monthly_peak_kw` or the merged
  result (neither is an adapter-role reading). Surfacing all three there — external raw
  value, internal tracker value, and the merged result — is adopted as part of this
  decision, to give users the breakdown Option E's legibility Con calls for; the
  implementation spec must add that attribute explicitly rather than relying on the
  existing default.
- The requirement and the guided-config-flow use case for this strand can now proceed
  against a settled role name, a settled merge rule (including the `maximum peak` cap), and
  a known open config-flow-placement question to resolve.
- A glossary entry is needed for the new merged quantity once the implementation spec names
  it, alongside the existing `monthly peak demand` term.
