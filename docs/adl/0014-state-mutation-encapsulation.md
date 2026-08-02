# ADR-0014: Setter-method encapsulation for the coordinator's externally-writable fields

Date: 2026-08-01
Status: Superseded by ADR-0016

## Context

A class's own fields should not be reassigned from outside it by whatever caller happens
to hold a reference — mutation should go through a method the class itself defines, so
that whatever invariant the field carries is enforced in one place regardless of who is
calling (Fowler's Anemic Domain Model concern).

Inside the coordinator, this is already how state transitions work: `_mode_state` and
`_last_active_mode` are reassigned together only from
`_reset_mode_state_if_changed()` (`coordinator.py:587-595`), the sole method that owns
that pair, called from `_run_cycle` rather than written from outside. The same shape
holds for `PeakDemandState.update()` (`coordinator_cycle.py`, ADR-0012): its three
tracking fields are reassigned only inside that method, never by a caller reaching in
directly. Pure engine/mode results (`PeakBreachTracker`, `SolarState`/`CaptarState`/
`SolarOnlyState`, `RequiredCurrentResult`, `SolarStepUpState`) are `@dataclass(frozen=True)`
and the module-level pure function operating on one returns a new instance rather than
mutating in place. None of the coordinator's *internal* state transitions are anemic
today.

The gap is at the coordinator's *public* boundary. `SmartChargingCoordinator` exposes
four plain writable attributes that entity platforms assign directly from outside the
class, with no method in between:

- `active_mode`, written by `ModeSelect.async_select_option`/`async_added_to_hass`
  (`select.py:62,66`)
- `active_profile`, written by `ProfileSelect.async_select_option`/`async_added_to_hass`
  (`select.py:89,93`)
- `target_current`, written by `TargetCurrentNumber.async_set_native_value`/
  `async_added_to_hass` (`number.py:47,51`)
- `soc_limit_override`, written by `SocLimitOverrideNumber.async_set_native_value`/
  `async_added_to_hass` (`number.py:80,84`)

For the two numeric fields, the only range validation is `min(max(value, min_value),
max_value)` inside `TargetCurrentNumber`/`SocLimitOverrideNumber` themselves
(`number.py:41-44,74-77`, applied only on restore, not on `async_set_native_value`) —
the coordinator's own `target_current`/`soc_limit_override` attributes accept whatever
value is assigned, with no clamp of their own. Any other caller that reaches
`coordinator.target_current = value` directly (a different entity, a future service
call, a test) bypasses that clamp entirely; the value is only made safe again if some
later engine step happens to floor/cap it downstream, which is an accidental side effect
of that engine's own logic, not a guarantee this field makes about itself.
`active_mode`/`active_profile` have no numeric range to violate — `SelectEntity`'s own
`options` list already stops `async_select_option` from ever being called with a value
outside the enum — but they are written through the same unencapsulated `field =
value` path as the two numeric ones.

`CycleContext` (`coordinator_cycle.py`, ADR-0012) is a related but separate case: it is a
per-cycle data carrier introduced by ADR-0012's decomposition, not yet wired into
`coordinator.py`'s `_run_cycle`. This ADR does not decide anything about it — whether its
planned field-by-field resolution needs setter methods is a question for the
implementation spec that wires it in, not this decision.

## Considered options

### Option A — Status quo: entity platforms keep assigning coordinator fields directly

- Pro: Zero migration cost; matches the common Home Assistant idiom of an entity writing
  a coordinator attribute and calling `async_request_refresh()`.
- Con: `target_current`/`soc_limit_override`'s range validation lives only in the
  entity's own `min`/`max` attrs and is silently skipped for any other caller that
  assigns the coordinator field directly — the coordinator's own attribute makes no
  promise about its own validity.

### Option B — Coordinator holds one immutable state snapshot; every external write goes through a method that returns a new snapshot, coordinator swaps its reference

- Pro: Matches Fowler's other suggested pattern (immutable state, methods return new
  instances) and the frozen-dataclass style already used throughout `engines/`/`modes/`.
- Con: Entities hold `self._coordinator = coordinator` for the object's whole lifetime,
  and HA's own `DataUpdateCoordinator` listener wiring (ADR-0006) is built around that
  same live reference; swapping the coordinator's identity on every write would break
  every entity's stored reference and re-open how ADR-0006 wires the coordinator into HA,
  for a scope far larger than the four fields actually in question.

### Option C — Add one setter method per externally-writable field; entity platforms call the method instead of assigning the attribute

Add `set_active_mode(mode)`, `set_active_profile(profile)`, `set_target_current(value)`,
`set_soc_limit_override(value)` to `SmartChargingCoordinator`, each the single place that
field's own validation (the range clamp, for the two numeric fields) runs; update the
four call sites in `select.py`/`number.py` to call the method instead of assigning.

- Pro: Closes Option A's gap — the range clamp moves from "each entity's own attrs,
  skipped by any other caller" to "the coordinator's own method, run for every caller" —
  without touching the coordinator's live identity or its `DataUpdateCoordinator` wiring.
- Con: Four small setter methods to add and keep in sync with each field's own rule, and
  four call sites to update across two platform files — a real, if small, diff.

### Option D — Setter methods only for the two numeric fields (`target_current`,
`soc_limit_override`); leave `active_mode`/`active_profile` as direct assignment

- Pro: Smaller diff than Option C — targets only the two fields with a real range
  invariant a bad caller could violate; `active_mode`/`active_profile` can't receive an
  invalid value today because `SelectEntity`'s own `options` list already rejects
  anything outside the enum before `async_select_option` is ever called.
- Con: Leaves two of the four externally-written fields unencapsulated "because they
  happen to be safe today", with no rule covering what happens if either later gains a
  second constraint beyond options-list membership (e.g. a mode becoming runtime-
  unavailable, not just configuration-time-absent) — a boundary drawn per field's current
  behavior rather than per field's role (externally-writable coordinator state).

## Decision

Option C. It closes the actual gap named in Context — validation for
`target_current`/`soc_limit_override` living only in the entity, silently bypassable by
any other caller — using the same "mutate only through an owning method" shape the
coordinator's internal transitions (`_reset_mode_state_if_changed`,
`PeakDemandState.update()`) already use, so the coordinator's external boundary follows
the same rule as its internal one instead of a different, weaker one. It avoids Option
B's cost of re-deriving ADR-0006's coordinator/HA wiring for a problem that is scoped to
four fields, not the coordinator's whole identity. Option D's smaller diff is rejected
because it draws the encapsulation boundary around each field's current behavior
("safe today") rather than its role (externally-writable coordinator state), which gives
no rule for the next field added to this surface.

## Consequences

- Follow-up issue: add `set_active_mode`, `set_active_profile`, `set_target_current`,
  and `set_soc_limit_override` to `SmartChargingCoordinator`; move the range clamp for
  the two numeric setters from `TargetCurrentNumber`/`SocLimitOverrideNumber` into the
  coordinator method (or have the entity clamp for its own displayed value and the
  coordinator clamp independently for its own — an implementation-spec-level choice, not
  part of this decision); update the four call sites in `select.py`/`number.py` to call
  the new methods instead of assigning.
- Any future field added to the coordinator's externally-writable surface follows this
  same rule (a setter method, not a bare attribute) rather than needing its own ADR.
- Does not change `_reset_mode_state_if_changed()`, `PeakDemandState`, or any
  frozen engine/mode value object — all already follow the pattern this ADR generalizes
  to the coordinator's public boundary.
- Does not decide anything about `CycleContext`, which is not yet wired into
  `coordinator.py`; that is scoped to the implementation spec that wires it in.
