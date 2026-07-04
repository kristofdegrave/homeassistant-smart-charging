# ADR-0006: Coordinator and data flow

Date: 2026-07-04
Status: Accepted

## Context

`control-cycle.md` specifies the control cycle's *behavior*: read sensors, smooth net and
solar power (R10), resolve supply voltage (NF4), dispatch to the active mode, apply the R3
peak clamp, apply the C4 grid-supply-ceiling clamp, enforce C1/R11, write the result. It does
not say how that behavior is implemented as Home Assistant Python — how many coordinator
objects there are, which reads go through adapters, which values are raw vs. smoothed at each
clamp, or how mode modules are shaped so NF2's self-containment is structural rather than a
convention. This is backfilled from Decision 5 of
`docs/plans/2026-07-04-integration-architecture-design.md` (PR #30, still open — see
ADR-0001's plan to give each of that doc's decisions its own ADR before #30 merges).

This decision builds on ADR-0003 (adapters supply the readings in step 1) and ADR-0004/0005
(owned diagnostic entities and config entries feed steps 4-6); it does not restate or change
those. It leaves error handling (what happens when an adapter read fails) and testing strategy
(how mode modules get unit-tested) to ADR-0007 and ADR-0008, which depend on the shape fixed
here.

Two forces sharpen the implementation choice beyond what `control-cycle.md` already settled:

- **Which of the two clamps (R3 peak-protection, C4 grid-supply-ceiling) can be skipped, and
  under what condition.** `control-cycle.md` step 5 says peak protection is "active in every
  mode except when `Power` mode has its peak-protection option disabled (R17)"; step 6 says
  the grid-supply-ceiling clamp is "the one clamp `Power` mode cannot switch off" and applies
  "even when the step 5 peak clamp was skipped." An implementation has to decide whether that
  is one clamp routine with a conditional inside it, or two separate steps — the difference
  matters because a single routine's opt-out is easy to wire so it accidentally silences both
  clamps, which `control-cycle.md` explicitly forbids.
- **Which reading (raw or smoothed) each downstream step consumes.** R10 smooths net and solar
  power for the mode's set-point decision; `control-cycle.md` step 5 clamps on the raw reading
  "to avoid lag." An implementation has to keep both the raw and the smoothed value in scope
  through the whole cycle, not just the smoothed one, or the clamps silently start operating on
  smoothed (lagged) data.

## Considered options

### Option A — One `DataUpdateCoordinator`, single combined peak-protection routine

A single coordinator subclass runs steps 1-10 below, but step 5 and step 6
(`control-cycle.md`'s R3 and C4 clamps) are merged into one routine: it checks the R17
opt-out first, and only evaluates the effective peak limit and the grid supply ceiling
together if the opt-out is off.

- Pro: Fewer call sites; a single "apply protective clamps" method is easier to find than two.
- Con: Makes the R17 opt-out (Power mode's peak-protection toggle) the single gate over *both*
  limits. `control-cycle.md` step 6 and its "Grid supply ceiling reached" edge case are explicit
  that C4 applies "even when the step 5 peak clamp was skipped" — merging the two steps means a
  future change to the opt-out's condition (or a bug in the merged conditional) can silently
  disable fuse protection too, which is exactly the failure `control-cycle.md` calls out by
  name.

### Option B — One `DataUpdateCoordinator`, two distinct clamp steps

A single coordinator subclass runs the ten steps below, with the R3 peak-protection clamp
(step 7) and the C4 grid-supply-ceiling clamp (step 8) implemented as two separate methods
called in sequence. Only step 7 checks the R17 opt-out; step 8 has no opt-out path at all.

- Pro: The R17 opt-out can only ever skip step 7. Step 8 has no conditional that could
  accidentally absorb it, so C4 stays "always active" by construction, matching
  `control-cycle.md`'s framing of it as the one clamp Power mode cannot switch off.
- Con: Two call sites (and two units of raw-reading plumbing) to keep in sync instead of one;
  a future maintainer touching "the clamp logic" has to know to check both methods.

### Option C — Two coordinators (one for the control cycle, one for diagnostics/notifications)

Split the ten steps into a fast coordinator (steps 1-9: read through write) and a slower,
independently-scheduled coordinator for diagnostic entities and notification triggers
(step 10).

- Pro: Decouples the notification/diagnostic cadence from the control interval, which could
  matter if R12/R13 notification checks turn out to be expensive or need a different schedule.
- Con: Two coordinators mean two update cycles to reason about, and diagnostics/notifications
  in this design need the *same* cycle's resolved values (SOC limit, applied current, which
  clamp fired) that steps 1-9 just computed — splitting them means either duplicating that
  state or passing it across coordinators, adding coupling for a cadence difference that
  R12/R13 (not yet built) haven't shown a need for yet.

## Decision

Option B. A single `DataUpdateCoordinator` subclass drives the full cycle:

1. Read raw values through adapters (ADR-0003): net power, charger power, EV SOC, charger
   status, monthly peak demand, and — when solar is present — solar power. Grid voltage is
   read when mapped, otherwise treated as absent; this is expected, not a fault (see step 3).
2. Smooth net power and solar power per R10 (rolling mean over N cycles). Charger power is
   used raw — `entity-catalog.md`'s note on `sc_charger_power_w` is explicit that it is not an
   operand of solar surplus via the smoothed channel. The raw net-power reading is kept
   alongside the smoothed one: steps 7-8's clamps use the raw reading so a breach can't hide
   behind the smoothing window.
3. Resolve the supply voltage (NF4): the measured grid-voltage reading when healthy, otherwise
   the configured nominal voltage. Missing grid voltage is the one input where "absent" is
   normal, expected behavior, not a fault — NF4 requires this fallback.
4. Resolve the active SOC limit (`resolution_rules.active_soc_limit`, scoped in this
   implementation to the default row only).
5. Resolve the active profile -> active mode (`profiles/manual.py` reads the user's
   `select.smart_charging_mode`; `profiles/auto.py`, once it exists, runs the flow-selection
   logic).
6. Dispatch smoothed readings + resolved SOC limit + config to the active mode module
   (`modes/*.py`) -> desired current.
7. Apply the R3 peak-protection clamp on raw readings — its own method, skippable only in
   `Power` mode with its peak-protection option (R17) disabled.
8. Apply the C4 grid-supply-ceiling clamp on raw readings — a distinct method from step 7,
   with no opt-out of its own, so it always runs, including when step 7 was skipped.
9. Apply rapid-cycling prevention (R11) and the C1 floor/cap invariant.
10. Write the result through the charger-current adapter (skip the write if unchanged), update
    the owned diagnostic entities, and evaluate notification triggers (R12/R13, once those
    use-cases exist).

Mode modules (`solar.py`, `solar_only.py`, `captar.py`, `power.py`, `off.py`) are pure
functions/classes: smoothed readings + config in, desired current out — no direct HA or
adapter access. This is a rule this decision adds on top of NF2 (which requires only that each
mode be self-contained, not that it avoid HA access); it is what makes the mode modules
unit-testable without a running Home Assistant instance, a property ADR-0008 relies on to
define its testing strategy. NF2 itself states nothing about testability — the self-containment
it requires is realized structurally by ADR-0002's `adapters/`/`modes/`/`profiles/` package
layout, and this decision's "no direct HA or adapter access" rule is what makes that
self-containment strong enough to also buy the testability ADR-0008 depends on.

Step 7/8's split is Option B specifically because Option A's single routine would let the R17
opt-out — a `Power`-mode-only, user-facing toggle — reach into C4 by construction, which
`control-cycle.md` forbids outright ("the one clamp `Power` mode cannot switch off"). Option C
is deferred rather than rejected outright: nothing in the current requirement set (R12/R13 not
yet built) demands a different cadence for diagnostics/notifications than the control interval,
so the added coordination cost of two coordinators has no offsetting benefit yet.

## Consequences

- `coordinator.py` is the one place the ten-step order lives in code; a change to step order
  or to which reading (raw/smoothed) a step consumes is a change to this ADR (a new ADR
  superseding this one), not a silent refactor.
- ADR-0007 (error handling) defines what happens when an adapter read in step 1 fails or when
  the mode module in step 6 raises — this ADR only fixes the happy-path shape it must handle.
- ADR-0008 (testing strategy) relies on mode modules being pure and adapter-free (this
  decision's added rule) to unit-test `modes/*.py` without a running Home Assistant instance.
- If R12/R13 (notifications) later need a different schedule than the control interval, Option
  C becomes worth revisiting — this decision does not foreclose it, it just isn't justified by
  anything in scope today.
- Step 7 and step 8 must remain separate methods/call sites in `coordinator.py`; a future
  change that merges them back into one conditional would reintroduce the Option A failure mode
  this decision rejects.
