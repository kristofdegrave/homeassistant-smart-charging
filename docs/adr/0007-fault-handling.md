# ADR-0007: Fault handling for adapter reads, translation failures, and uncaught exceptions

Date: 2026-07-04
Status: Accepted

## Context

The coordinator's control cycle (ADR-0006) reads mapped entities through adapters (ADR-0003)
and feeds them into mode logic to produce a charger current. Several things can go wrong on
any given cycle: a mapped entity can be missing or unavailable, a charger can report a raw
status string the translation table has no entry for, or an exception can be raised anywhere
in the cycle (an adapter, mode logic, or the write-back to the charger). C1 requires the
charger current to always be either 0 A or within the valid range — never something guessed
or stale by default — and R11 requires that any stop still runs its cooldown to completion
rather than being bypassed. NF4 already defines one specific missing-reading case (grid
voltage) with its own normal fallback (the nominal voltage), which is not itself a fault.

Home Assistant's `DataUpdateCoordinator` has built-in backoff/retry for failed refreshes, but
that scheduling is about *when the library retries fetching data*, not about *whether the
charger current gets re-evaluated on the library's own schedule* — a safety-critical clamp
like C1 cannot rely on it alone to guarantee the current is revisited promptly after a
failure.

This ADR covers only the fault path: what counts as a fault, and how the coordinator responds
to one. Reload behavior on reconfigure/options changes is a separate decision (ADR-0008). R6
(vehicle charge-limit write-back) and its C2 "never while away from home" guard are out of
scope.

## Considered options

### Option A — Force 0 A and set Fault, through the normal stop machinery

- Pro: One failure-handling path for every kind of failure (missing mapping, unavailable
  entity, untranslatable charger status, uncaught exception) — the coordinator never has to
  decide case-by-case whether a given failure is "safe enough" to ignore. Because the fault
  path re-enters the same C1/R11 invariants as any other stop, a fault can never leave the
  charger current between 0 A and the minimum, and a fault-triggered stop still respects
  the cooldown before the charger can restart — no separate, less-tested code path exists
  that could bypass R11's rapid-cycling protection.
- Con: A transient, single-cycle blip (e.g. one dropped poll of a mapped sensor) forces a
  full stop-and-cooldown cycle rather than tolerating it, so a flaky-but-recovering entity
  causes more charging interruptions than a design that tolerated brief gaps would.

### Option B — Hold the last known current

- Pro: Tolerates a brief, single-cycle outage without interrupting charging, which is kinder
  to charge sessions when the underlying cause is a transient polling hiccup rather than a
  real fault.
- Con: `DataUpdateCoordinator`'s default backoff/retry does not guarantee the charger current
  gets re-evaluated on the library's own schedule, so a stale current held past the point
  where it's still safe (e.g. solar production has since dropped, or the car has reached its
  SOC limit) can persist for longer than a control cycle — exactly the kind of unbounded,
  ungoverned state C1 exists to prevent.

## Decision

Option A. An adapter returning `None` for a required role — a mapped entity that is missing
or unavailable, or, for charger status specifically, a raw state with no translation-table
entry — is treated as a fault: the coordinator sets `sensor.smart_charging_status` to `Fault`
and forces 0 A through the same C1/R11 invariants as any other stop. No substitute value is
ever guessed. Grid voltage is the one documented exception, per NF4: a missing/unavailable
reading there resolves to the nominal voltage, which is NF4's normal fallback path, not a
fault. An uncaught exception anywhere in a coordinator cycle is treated identically (force
0 A, set `Fault`) rather than leaving the charger at its last set current, for the reason
Option B's Con names — `DataUpdateCoordinator`'s backoff/retry does not, on its own,
guarantee prompt re-evaluation of the current. Each outage logs once at warning level (not
once per cycle, to avoid log spam); a recovery logs at info level.

## Consequences

- The coordinator needs exactly one fault-handling code path (force 0 A through the C1/R11
  stop machinery, set `Fault`) that every kind of adapter/exception failure funnels into —
  ADR-0006's step order must route every failure mode into it rather than adding
  special-cased short-circuits.
- Grid-voltage fallback (NF4) must be implemented as a distinct branch from the fault path,
  not as a special case within it, since a missing voltage reading is explicitly not a
  fault.
- Warning/info-level once-per-outage logging (not per-cycle) needs its own de-duplication
  state (e.g. "was the previous cycle also faulted") — a follow-up implementation detail for
  whichever issue implements the coordinator, tracked once that work starts.
- R6 (vehicle charge-limit write-back) and C2 will need their own error-handling treatment
  when that requirement is designed — not decided by this ADR.
- Depends on ADR-0003 (what an adapter returning `None` means) and ADR-0006 (the coordinator
  step order/invariants the fault path re-enters); if either of those changes in a way that
  removes or renames the C1/R11 stop machinery this ADR relies on, this ADR should be
  revisited.
