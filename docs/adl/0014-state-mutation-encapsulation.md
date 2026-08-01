# ADR-0014: State-mutation encapsulation for coordinator-owned state

Date: 2026-08-01
Status: Proposed

## Context

Issue #420 raises Fowler's Anemic Domain Model concern: a class's own fields should not
be reassigned from outside it by whatever caller happens to hold a reference; mutation
should go through a method the class itself defines (or, alternatively, the class should
be immutable and a method should return a new instance rather than mutate in place).

The codebase today has three different patterns already in place, none of them
contradicting each other on their own terms, but with no written rule for which pattern a
new piece of state should follow:

- **Pure engine/mode value objects** — `PeakBreachTracker` (`engines/billing_protection.py`),
  `SolarState`/`CaptarState`/`SolarOnlyState` (`modes/*.py`), `RequiredCurrentResult`
  (`engines/deadline.py`) — are `@dataclass(frozen=True)`, and the module-level pure
  function that operates on one returns a new instance (e.g. `apply_peak_clamp` returns
  `(clamped_current, new_tracker, force_stop)`). No field is ever reassigned in place.
- **`PeakDemandState`** (`coordinator_cycle.py`, ADR-0012) is the opposite: a plain
  (non-frozen) dataclass whose three tracking fields (`window`, `tracked_kw`,
  `tracked_month`) are reassigned only from inside its own `update()` method — no caller
  ever writes `peak_demand.window = ...` directly.
- **`SmartChargingCoordinator` itself** does neither. `_run_cycle` reassigns the
  coordinator's own instance fields directly and repeatedly: `self.active_mode`,
  `self._mode_state`, `self._was_faulted`, `self._last_active_mode`,
  `self._last_active_soc_limit`, `self._step_up_state`, `self._net_window`, and
  `self._required_current` are all set by bare `self.x = ...` from more than a dozen call
  sites spread across the method (`coordinator.py:279-665`). At least one of these
  encodes a real cross-field invariant with no single place enforcing it: `_mode_state`
  must be reset to fresh whenever `active_mode` changes, and today that reset is
  duplicated by hand at two independent call sites (`coordinator.py:487` and `:594`) —
  exactly the failure mode an anemic model produces, where an invariant between two
  fields depends on every caller remembering to keep both in sync, rather than on one
  method that owns both.
- **`CycleContext`** (`coordinator_cycle.py`, ADR-0012) is deliberately mutable by design,
  with its own comment saying so: each of `_run_cycle`'s ten steps sets the one or two
  fields it resolves (`ctx.surplus_w = ...`, `ctx.urgent = ...`, ...) as that step runs.
  No field depends on another for validity — each is independently resolved and later
  read once — so there is no cross-field invariant for a method to protect.

This ADR decides which of these patterns new coordinator-owned state should follow,
without reopening ADR-0012 (which already accepted `PeakDemandState`'s and
`CycleContext`'s specific designs) or ADR-0006/0009/0010's separate rule that pure
engine/mode logic stays HA-free and side-effect-free.

## Considered options

### Option A — Status quo: no rule; leave `SmartChargingCoordinator`'s own fields as raw assignment

- Pro: Zero migration cost; nothing in `_run_cycle` changes.
- Con: The `active_mode`/`_mode_state` reset invariant stays enforced only by convention
  at two separate call sites, with no structural guard stopping a third mode-change path
  from being added later without the matching reset — the exact anemic-model failure
  issue #420 names, and the one already reproducing in this codebase today.

### Option B — Full functional immutability everywhere: no in-place mutation anywhere, including `CycleContext` and the coordinator's own fields

Every step and every owned object returns a new instance instead of mutating; the
coordinator threads a new state snapshot through `_run_cycle` each cycle rather than
holding mutable instance fields at all.

- Pro: One uniform rule with no categories to learn — matches Fowler's second suggested
  alternative (immutable state, methods return new instances) applied without exception.
- Con: `CycleContext`'s in-place field resolution was a deliberate, already-reviewed
  choice in ADR-0012 for a ten-step, five-second-interval hot loop with ten independently
  resolved fields and no cross-field invariant to protect; forcing it (and the
  coordinator's own long-lived fields) through copy-on-write would reopen an Accepted
  ADR with no new fact that invalidates its reasoning, for a much larger diff than the
  one real problem (the coordinator's own scattered raw assignment) requires.

### Option C — Encapsulate only state with a cross-field invariant behind an owning method; leave per-cycle `CycleContext` and pure engine/mode value objects as they already are

Extend the pattern `PeakDemandState.update()` already established: any state whose fields
must change together to stay valid gets pulled into its own small object, mutated only by
a method that changes all of them together. Fields with no such invariant, or state
scoped to a single cycle (`CycleContext`), stay as they are.

- Pro: Targets exactly the demonstrated problem — the `active_mode`/`_mode_state` reset
  invariant duplicated at two call sites — using a pattern the codebase has already
  adopted and had reviewed (`PeakDemandState`); does not touch `CycleContext` or the
  frozen engine/mode value objects, both already correct on their own terms.
- Con: Three coexisting mutation conventions (mutator-method state owners, frozen
  value-objects-plus-pure-functions, and freely-mutable per-cycle scratch objects) means a
  future contributor must learn which category a given class falls into rather than apply
  one rule everywhere.

### Option D — Same as Option C, but also wrap `CycleContext`'s per-step field resolution behind setter methods

- Pro: No object anywhere is ever mutated via a bare `obj.field = value` from outside its
  own methods — closer to full encapsulation than Option C.
- Con: `CycleContext`'s ten fields are each resolved independently by a different step
  with nothing to protect between them (no field's validity depends on another's value);
  wrapping each in a one-line setter is ceremony with no invariant behind it, and reopens
  ADR-0012's already-accepted `CycleContext` design without a new reason to.

## Decision

Option C. The rule: **a field may be reassigned directly only if no other field's
validity depends on it; state where two or more fields must change together to stay
consistent must be owned by its own object, mutated only through a method that changes
all of them together** — the same shape `PeakDemandState.update()` already established.
This makes the choice between "mutator method" and "immutable value returned by a
function" (issue #420's two suggested alternatives) a consequence of one question — does
this object outlive a single control cycle and carry a cross-field invariant? — rather
than a global either/or:

- Pure engine/mode results (`PeakBreachTracker`, `SolarState`, `RequiredCurrentResult`,
  ...) stay frozen dataclasses returned fresh by pure functions — they carry no identity
  across cycles for a mutator method to attach to; ADR-0006/0009/0010's HA-free,
  side-effect-free rule for this layer is unaffected.
- `PeakDemandState` is unchanged and is the model going forward: cross-cycle,
  invariant-bearing state gets a mutator method.
- `CycleContext` is unchanged: single-cycle scoped, no cross-field invariant, so direct
  field assignment during its one cycle of life is not the problem this ADR addresses.
- `SmartChargingCoordinator`'s own `active_mode`/`_mode_state` pair is the one violation
  this ADR requires fixing, since it is the one demonstrated case of an invariant
  enforced only by convention at multiple call sites.

## Consequences

- Follow-up issue: extract `active_mode`, `_mode_state`, and `_last_active_mode` into one
  small owned object (e.g. a `ModeTransitionState` mutated only by a
  `transition_to(new_mode)` method that resets `_mode_state` exactly once), replacing the
  two independent reset call sites at `coordinator.py:487` and `:594`. This is
  implementation-spec-level detail, not part of this decision.
- `_was_faulted`, `_last_active_soc_limit`, `_step_up_state`, `_net_window`, and
  `_required_current` are single fields with no sibling field's validity depending on
  them today; this ADR does not require extracting them, but any future addition that
  gives one of them a cross-field invariant (as `_mode_state` already has with
  `active_mode`) must follow this same rule rather than adding another hand-kept
  convention.
- This ADR does not reopen ADR-0012's `CycleContext` or `PeakDemandState` designs, and
  does not change ADR-0006/0009/0010's rule that engine/mode logic stays pure and
  HA-free.
- A future object that needs cross-field invariant protection follows this same rule by
  construction — no new ADR needed per object, only when the *category* boundary itself
  is challenged (e.g., a proposal to make `CycleContext` invariant-bearing, or to drop
  frozen dataclasses for engine results).
