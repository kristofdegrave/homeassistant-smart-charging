# ADR-0030: External monthly-peak sensor — optional adapter role

Date: 2026-08-31
Status: Proposed

## Context

Monthly peak demand — the operand that `resolve_effective_peak_limit`
(`custom_components/smart_charging/engines/billing_protection.py`) reads for R3's row-2
clamp — is computed entirely from the integration's own smoothed `net_power` sampling
inside `update_monthly_peak_demand` (`engines/peak_demand_tracker.py`). That tracker's state
already survives a restart: `MonthlyPeakSensor` (`sensor.py`) is a `RestoreSensor` whose
`async_added_to_hass` seeds the coordinator's tracked `(kw, month)` back from the entity's
last stored state, so a plain HA/integration restart does not lose a peak the tracker had
already recorded. What the tracker still cannot know about is any peak that occurred
**while it was not observing at all**: a genuinely new install partway through a month, a
period where HA itself was down, or a lost/malformed restore payload. A reported install hit
exactly that: the integration's own tracker read the peak floor (~2.5 kW) for a month where
an external source (the household's smart meter / DSO capacity-tariff sensor) already showed
4.09 kW for the same month.

Many DSO/smart-meter integrations already expose the utility's own tracked monthly peak
demand as an HA sensor entity, refreshed independently of this integration's own sampling.
This ADR settles only how such a reading, if the household has one, enters the system. How
it is combined with the internally-tracked monthly peak demand once both are present is a
separate decision, ADR-0032 — that decision only matters if this one admits an external
reading at all, but the reverse is not true (a config-flow static-value input, for example,
would need the same merge decision), so the two are recorded independently.

## Considered options

### Option A — Do nothing (internal tracking only)

Keep `monthly_peak_kw` sourced exclusively from `update_monthly_peak_demand`, relying only
on its existing restore-on-restart behavior; no external input of any kind.

- Pro: No new adapter role, config-flow surface, or merge logic — zero implementation cost.
- Con: Leaves the observing-gap failure mode open exactly as reported — a spike during HA
  downtime, a fresh mid-month install with nothing to restore, or a lost restore payload all
  have no way to recover the real peak already reached that month.

### Option B — New optional adapter role, `ROLE_MONTHLY_PEAK_EXTERNAL`

Add a role key in `const.py` alongside the other optional roles that are absent at the
factory level when unmapped (`ROLE_LOW_TARIFF`, `ROLE_SOLAR_FORECAST`,
`ROLE_DEPARTURE_EXTERNAL`, `ROLE_HOME_DAY_EXTERNAL` — ADR-0003's config-flow entity-mapping
mechanism, ADR-0006's per-cycle reads), mapped via the config flow to an HA entity (the
DSO/smart-meter peak sensor). Unmapped → the role's adapter is simply absent from the
factory's built roles, same as today's optional roles; mapped → the coordinator reads it
once per cycle like any other role and passes the value on to whatever ADR-0032 decides to
do with it.

- Pro: Reuses a pattern this codebase already has four instances of, with no new kind of
  adapter class or coordinator-wiring mechanism to invent. The reading updates live every
  cycle from whatever the external sensor currently reports, so a DSO correction later in
  the month is picked up automatically.
- Con: Ties this feature to the household actually having (and correctly mapping) a
  DSO/smart-meter integration in HA that exposes a monthly-peak entity — some setups will
  never have one, and this role is then permanently absent, unlike a config-flow-entered
  static value the user could type in without any such integration existing. It also needs
  a config-flow home: ADR-0027's accepted nine-step topic-grouped flow has no catch-all
  mapping step to drop this into (the natural fit, `STEP_CAPTAR`, is itself gated on
  `CONF_CAPTAR_AVAILABLE`, so a non-CapTar install would need either its own ungated step or
  a different home) — as of this ADR, `config_flow.py` on `main` has not yet migrated to that
  nine-step model and still exposes the older `STEP_MAPPINGS` catch-all, so the concrete
  placement also depends on which flow shape has landed by the time this role is built.

### Option C — Config-flow numeric field (static value, no entity mapping)

Add a plain number field to the config/options flow (e.g. "known monthly peak so far, kW")
that the user types in and updates manually, stored in the config entry like a regular
option rather than resolved through an adapter role.

- Pro: Works even for a household with no DSO/smart-meter HA integration at all — the user
  can read the number off a utility app or bill and type it in once.
- Con: Never updates itself; the moment the DSO's own reading changes mid-month (a new
  peak, a month rollover) the stored value goes stale until the user notices and re-enters
  it by hand — directly undermines the goal of never under-clamping against the *current*
  real peak, and gives this feature no live-update story the other optional roles already
  have for free.

### Option D — Backfill from HA's recorder / long-term statistics

Instead of a new external source, derive the missing history from HA's own recorder:
at startup (or on a month change), query long-term statistics for the mapped `net_power`
entity across the current calendar month and seed `monthly_peak_kw` from its recorded
maximum, covering the observing-gap cases without any DSO integration.

- Pro: Needs no external sensor at all — works purely from data this integration is already
  configured to read, so every install benefits, not just ones with a DSO peak sensor. Not
  mutually exclusive with Option B — a future ADR could add this as a second, independent
  input alongside the external role rather than instead of it.
- Con: Long-term statistics are downsampled (hourly, sometimes 5-minute short-term) rather
  than the tracker's own ~15-minute smoothing window, so a backfilled figure would not have
  the same provenance as a live reading, and it does nothing for a genuinely new install
  with no prior recorder history for that month either — the two cases Option B's live
  external reading does cover.

## Decision

**Option B**, a new optional adapter role `ROLE_MONTHLY_PEAK_EXTERNAL`. Option A leaves the
reported failure mode open with no mitigation at all. Option D covers the same
HA-was-running-but-integration-wasn't gap without depending on a DSO integration, and reading
the recorder is ordinary coordinator-level HA I/O, not an engine-purity violation (ADR-0010
scopes that boundary to the pure engines, not the coordinator) — so it is not rejected on
structural grounds, but on its own stated Cons: it cannot help a genuinely new install with
no recorder history, and its downsampled resolution does not match the tracker's own
15-minute window. Since D and B are not mutually exclusive, D remains open as later,
complementary follow-up rather than a rejected alternative. Option C's static-value
convenience for DSO-less households does not offset losing the live-update mechanism the
other options provide — a feature meant to close an under-reporting gap must not introduce a
new, manual one. Option B's config-flow-placement Con (no existing ungated step, and the
target model itself not yet shipped) is real but is a config-flow design detail for the
guided-config-flow use case to resolve, not a reason to reject the role shape itself.

## Consequences

- `const.py` gains `ROLE_MONTHLY_PEAK_EXTERNAL`, absent at the factory level when unmapped
  like the other optional roles it sits alongside. The config-flow home for its mapping — a
  new ungated step, or a place reachable regardless of `CONF_CAPTAR_AVAILABLE`, and how that
  interacts with `config_flow.py`'s eventual migration to ADR-0027's nine-step model — is
  left to the guided-config-flow use case to resolve, not decided here.
- The role's adapter must define unavailable/unknown handling for the mapped entity under
  ADR-0007's existing fault semantics (falling back to "role absent" behavior, same as the
  other optional roles), and a unit contract for the reading — DSO/smart-meter peak sensors
  commonly report in W, so the adapter (or its config-flow mapping) must normalize to kW
  before the value reaches the coordinator; this is an implementation-spec obligation this
  ADR surfaces but does not itself resolve.
- This role's raw reading, once wired, surfaces on the ADR-0021 adapter-readings diagnostic
  sensor by the existing default (it is a wired read-adapter-role value). Whether it combines
  with `monthly_peak_kw` for `resolve_effective_peak_limit`, and whether that combined value
  also needs surfacing there, is ADR-0032's decision.
- `entity-catalog.md` needs a row for the new adapter role, matching how the other optional
  `ROLE_*` roles are already cataloged.
- The requirement and the guided-config-flow use case for this strand can now proceed
  against a settled role name, with the config-flow-placement question and the merge
  semantics (ADR-0032) still open.
