# ADR-0008: Config-entry reload on reconfigure and options changes

Date: 2026-07-04
Status: Accepted

## Context

This is backfilled from Decision 6 of
`docs/plans/2026-07-04-integration-architecture-design.md`, per ADR-0001's plan to give
each of that doc's decisions its own ADR.

Entity mappings (ADR-0003) can change through the reconfigure flow, and thresholds can
change through the options flow, while the integration is running. Either change can happen
mid-cooldown or mid-hold — the coordinator (ADR-0006) may have an in-progress rapid-cycling
cooldown timer (R11) or a solar-surplus hold running at the moment the user submits a
mapping or threshold change. This ADR covers only that reload behavior; the coordinator's
fault path (missing/unavailable entities, untranslatable charger status, uncaught
exceptions) is a separate decision (ADR-0007) and is out of scope here.

## Considered options

### Option A — Full config-entry reload on mapping or threshold change

- Pro: Simple and uniform — Home Assistant's own reload mechanism recreates the coordinator
  and mode instances from scratch, so there is no separate code path that has to reconcile
  an in-progress hold/cooldown timer against a changed mapping or threshold; the new
  configuration always starts from a clean, known state.
- Con: Resets any in-progress hold/cooldown timer, including a `Captar` cooldown that may
  have minutes left to run — a user who intentionally reconfigures mid-cooldown loses that
  protection for one cycle, however rare that timing is in practice.

### Option B — State-preserving reconfigure (carry timers across the reload)

- Pro: A mapping or threshold change would no longer cost an in-progress hold/cooldown timer,
  closing Option A's Con.
- Con: Requires persisting and re-attaching timer state across a teardown/setup that Home
  Assistant's reload mechanism does not naturally support, and requires validating that the
  carried-over timer is still meaningful against the *new* mapping/thresholds (e.g. a
  cooldown duration that itself just changed) — meaningful added complexity in the
  reconfigure/options flow for a case (thresholds changing while mid-cooldown) that happens
  rarely.

## Decision

Option A. Changing entity mappings via the reconfigure flow, or a threshold via the options
flow, triggers a full config-entry reload, recreating the coordinator and its mode instances
and resetting any in-progress hold/cooldown timer. Option A's Con (losing in-progress
cooldown state) is accepted as a trade-off rather than an oversight: thresholds and mappings
change rarely, and R11's "a cooldown, once started, always runs to completion" concern is
about normal operation continuing undisturbed, not about a user actively reconfiguring the
integration — Option B's added complexity is not justified by how rarely the two coincide.

## Consequences

- The reconfigure and options flows do not need any special-case logic to preserve
  hold/cooldown state across a reload; relying on Home Assistant's standard reload behavior
  is sufficient and intentional.
- A user who reconfigures mid-cooldown loses that cooldown's remaining protection for one
  cycle after reload — worth a line in user-facing documentation for the reconfigure/options
  flow once that UI is implemented, but not a behavior change to make there.
- Depends on ADR-0003 (what a mapping change means) and ADR-0006 (the coordinator/timer state
  a reload resets); if either changes how hold/cooldown state is held, this ADR should be
  revisited.
