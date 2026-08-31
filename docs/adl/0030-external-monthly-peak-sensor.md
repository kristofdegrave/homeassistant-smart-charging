# ADR-0030: External monthly-peak sensor -- adapter role + precedence semantics

Date: 2026-08-31
Status: Proposed

## Context

`monthly_peak_kw`, the operand `resolve_effective_peak_limit`
(`engines/billing_protection.py`) reads for R3's row-2 clamp, is computed entirely from the
integration's own smoothed `net_power` sampling inside `update_monthly_peak_demand`
(`engines/peak_demand_tracker.py`). That tracker only ever sees power while HA and this
integration are running. Whenever they weren't -- HA down, the integration newly added
mid-month, a restart that missed a brief spike -- the tracked peak under-reports the real
billing-month peak. #872 observed exactly this: the integration's own tracker read
`peak_floor_kw` (~2.5 kW) for a month where an external source (the household's smart
meter / DSO capacity-tariff sensor) already reported 4.09 kW for the same month.

Many DSO/smart-meter integrations already expose the utility's own billing-month peak as an
HA sensor entity, refreshed independently of this integration's own sampling. Folding that
reading in gives `resolve_effective_peak_limit` a second, independently-sourced operand that
does not depend on this integration having been running continuously. Two structural
questions have to be settled before any requirement/UC or code work (#873):

1. How does the external reading enter the system -- what shape does the optional
   integration point take, following the existing optional-adapter-role pattern (NF3:
   `ROLE_LOW_TARIFF`, `ROLE_SOLAR_FORECAST`, `ROLE_DEPARTURE_EXTERNAL`,
   `ROLE_HOME_DAY_EXTERNAL`) that already lets a role be absent at the factory level and
   fall back to a documented default?
2. When both an external reading and the internally-tracked `monthly_peak_kw` are present,
   which one (or what combination) feeds `resolve_effective_peak_limit`? R3's row-2 clamp
   exists specifically to avoid under-clamping the charger below what the household can
   safely draw, so the merge rule has direct billing-protection-safety consequences, not
   just a display/cosmetic one.

## Considered options

### Question 1 -- integration point for the external reading

#### Option A -- New optional adapter role, `ROLE_MONTHLY_PEAK_EXTERNAL`

Add a role key in `const.py` alongside the other NF3 optional roles, mapped via the config
flow to an HA entity (the DSO/smart-meter peak sensor) exactly like `ROLE_LOW_TARIFF` or
`ROLE_SOLAR_FORECAST`. Unmapped -> the role's adapter is simply absent from the factory's
built roles, same as today's optional roles; mapped -> the coordinator reads it once per
cycle like any other role and passes the value into the Billing-Protection engine call, same
data path `monthly_peak_kw` already takes in from the Peak-Demand Tracker.

- Pro: Reuses a pattern this codebase already has four instances of (NF3) with no new kind
  of config-flow step, adapter class, or coordinator wiring to invent -- the factory, ADR-0021's
  adapter-readings diagnostic sensor, and the config flow's existing optional-role branch
  already know how to add a role. The reading updates live every cycle from whatever the
  external sensor currently reports, so a DSO correction later in the month is picked up
  automatically.
- Con: Ties this feature to the household actually having (and correctly mapping) a
  DSO/smart-meter integration in HA that exposes a monthly-peak entity -- some setups will
  never have one, and this role is then permanently absent, unlike a config-flow-entered
  static value the user could type in without any such integration existing.

#### Option B -- Config-flow numeric field (static value, no entity mapping)

Add a plain number field to the config/options flow (e.g. "known monthly peak so far, kW")
that the user types in and updates manually, stored in the config entry like a regular
option rather than resolved through an adapter role.

- Pro: Works even for a household with no DSO/smart-meter HA integration at all -- the user
  can read the number off a utility app or bill and type it in once.
- Con: Never updates itself; the moment the DSO's own reading changes mid-month (a new
  peak, a billing-period rollover) the stored value goes stale until the user notices and
  re-enters it by hand -- directly undermines the goal of never under-clamping against the
  *current* real peak, and gives this feature no live-update story the rest of NF3's roles
  already have for free.

## Considered options (continued) -- Question 2, merge/precedence semantics

Applies only once Question 1's Option A is adopted, i.e. the external reading, when mapped,
is a per-cycle value alongside the internally-tracked `monthly_peak_kw`.

#### Option C -- `max(external, internal)`

`resolve_effective_peak_limit` receives `max(external_reading, monthly_peak_kw)` in place of
today's bare `monthly_peak_kw` whenever the external role is mapped and its reading is not
`None`/unavailable; falls back to `monthly_peak_kw` alone when unmapped or unavailable
(NF3's existing optional-role default behavior).

- Pro: Can only raise the effective floor never lower it below what either source has
  independently observed -- directly matches #872's under-report scenario (external already
  at 4.09 kW, internal tracker restarted at 2.5 kW: `max` immediately reflects 4.09 kW), and
  the internal tracker can still push the peak higher between external sensor refreshes (a
  spike this integration observes live that the external sensor hasn't reported yet is not
  discarded). Never under-clamps in either direction.
- Con: Two independently-sourced peaks now feed one number with no single reading a user can
  point to as "the" peak -- the value shown/used can exceed both the external sensor's
  current display (if internal is higher) and the integration's own historical tracker (if
  external is higher), which needs to be surfaced clearly wherever `monthly_peak_kw` is
  displayed to avoid an unexplained-looking number.

#### Option D -- External always wins when mapped

When the external role is mapped and its reading is available, `resolve_effective_peak_limit`
uses the external reading exclusively, ignoring the internally-tracked `monthly_peak_kw`
entirely; falls back to internal-only when unmapped or unavailable.

- Pro: Single source of truth once configured -- whatever the DSO/smart-meter reports is
  authoritative, simplest mental model, no need to explain a blended value anywhere.
- Con: A spike the internal tracker observes between external sensor refreshes (DSO sensors
  commonly update on a slower cadence -- daily or on billing-period boundaries, not
  every coordinator cycle) is silently discarded even though the household's own live power
  draw already exceeded it -- reintroduces a narrower version of the exact under-clamping
  risk this ADR exists to close, just shifted from "integration wasn't running" to
  "integration's own tracker is more current than the external sensor right now."

## Decision

**Question 1: Option A**, a new optional adapter role `ROLE_MONTHLY_PEAK_EXTERNAL`. It costs
nothing structurally new (Option A's Pro) and Option B's static-value convenience for
DSO-less households does not offset losing this integration's only live-update mechanism
(Option B's Con) -- a feature meant to close an under-reporting gap must not introduce a
new, manual one.

**Question 2: Option C**, `max(external, internal)`. R3's row-2 clamp exists to protect
against under-clamping (system-design/billing_protection.py's own docstring); Option C is
the only one of the two that can never make the effective peak *lower* than either
independently-tracked source, in both directions Option D leaves exposed: the original
integration-was-off scenario (#872) and the narrower stale-external-sensor-cadence
scenario. Option D's simpler single-source-of-truth story is real, but it is a legibility
win purchased at the cost of the exact safety property row 2 exists for. Option C's own
Con -- a blended number needing explanation -- is addressed by exposing both source values
(the external role's raw reading and the internally-tracked `monthly_peak_kw`) alongside the
merged result via the existing ADR-0021 adapter-readings diagnostic sensor, rather than by
changing the merge rule.

## Consequences

- `const.py` gains `ROLE_MONTHLY_PEAK_EXTERNAL` next to the other NF3 optional roles; the
  config flow's existing optional-role step gains one more mapping entry (#876 covers the
  guided-config-flow UC).
- `resolve_effective_peak_limit` (or its caller, the coordinator) gains a merge step
  computing `max(external, internal)` before today's `min(max(monthly, floor), max)`
  clamp -- exact call-site placement and signature change belong to the implementation spec
  (#873's checklist), not this ADR.
- `monthly_peak_kw`'s existing meaning ("the integration's own tracked peak") is unchanged;
  the merged value used by `resolve_effective_peak_limit` becomes a distinct, larger-scoped
  quantity -- naming that distinction (e.g. `effective_monthly_peak_kw` vs
  `monthly_peak_kw`) is deferred to the implementation spec.
- ROLES_ADAPTER_READINGS_EXCLUDED (ADR-0021) does not need to list the new role -- it is a
  read role like `ROLE_LOW_TARIFF`, so its raw reading surfaces in the adapter-readings
  diagnostic sensor by the existing default, giving users the external/internal/merged
  breakdown this Decision's Consequences promised.
- #875 (requirement) and #876 (UC) can now proceed against a settled role name and merge
  rule instead of leaving either open.
- `docs/adl/README.md` gets a new row for ADR-0030.
