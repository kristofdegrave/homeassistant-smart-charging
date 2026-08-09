# ADR-0021: Adapter-role readings surfaced via a single diagnostic sensor's attributes

Date: 2026-08-09
Status: Proposed

## Context

ADR-0003 chose config-flow entity mapping + Python adapters (its Option B) over synthetic
`sc_`-prefixed proxy entities (its Option A): each adapter role — defined as a `ROLE_*`
constant in `const.py` (e.g. `grid_voltage`, `net_power`, `charger_power`,
`charger_status`, `charger_current`, `ev_soc`) and instantiated conditionally in
`adapters/factory.py` when its entity is mapped — is config-entry mapping data and a
Python-side adapter read/write, not an HA entity. `entity-catalog.md` already documents
these rows as `adapter role`, explicitly not catalog entities.

This is sufficient for the coordinator's own control logic (it reads adapters directly),
but it leaves no fixed, shippable entity a Lovelace dashboard can bind to for showing live
hardware I/O — e.g. current charger power, EV SOC, solar production, charger status. Only
the `config` rows and ADR-0004's owned control/diagnostic entities are dashboard-safe
today; adapter-role values are invisible outside the integration's own process. ADR-0003's
Consequences already flagged this gap as expected follow-up work; R19 (Runtime dashboard)
and UC11 (monitor-and-manage-charging-configuration) are the requirement and use-case that
own this gap — R19's acceptance criteria require the dashboard to show charger status,
active SOC limit, current charger current, solar surplus, and net import, all of which are
adapter-role values today, and UC11's exception flow requires that an unavailable
adapter-role reading render as "unavailable" rather than stale or fabricated, without
affecting any other section of the dashboard.

Whatever this decision adds must not reopen NF3's "no new HA entities for hardware inputs"
promise more than necessary — NF3 and `entity-catalog.md` were already reworded once
(ADR-0003) specifically to make adapter roles code-level, not entities, and a large new
batch of hardware-mirroring entities would partially reverse that framing.

This ADR concerns whichever adapter roles `adapters/factory.py` actually wires at a given
time — today, every role in `const.py`'s `ROLE_*` set except `solar_power`, which
`entity-catalog.md` lists but no adapter yet implements. Both `ROLE_NOTIFICATION_TARGET`
and `ROLE_SUN` are also wired roles without an `entity-catalog.md` row of their own (`sun`
has no entity mapping at all — it wraps HA's core `sun.sun` entity). The set of wired roles
grows as later ADRs or implementation work add adapters (e.g. for `solar_power`); this
ADR's mechanism (Option C) does not need to be revisited when that happens, since the
chosen sensor's attributes are derived from whichever roles are wired, not a fixed list.

## Considered options

### Option A — One new diagnostic sensor entity per adapter role

Add a read-only `sensor.smart_charging_diag_<role>` (ADR-0004 owned-entity population, one
per adapter role) mirroring that role's current value, updated by the coordinator each
control cycle. The coordinator continues reading the adapter directly for control logic;
these sensors exist purely for observability.

- Pro: Each value is a first-class HA entity — full recorder history, standalone graph
  cards, and the standard `entity_category: diagnostic` pattern users already expect from
  other integrations.
- Con: Adds one new entity per wired adapter role — already well into double digits today,
  per `const.py`'s `ROLE_*` set — and grows further as more roles get adapters later; each
  one needs its own `strings.json`/translation entries (repeating the per-entity cost
  `write-requirement`/T5.2-style work just paid), its own object_id pinned per ADR-0013,
  and its own test coverage — a maintenance burden disproportionate to a value that is
  purely observational, and a larger reversal of NF3's "no new entities for hardware
  inputs" framing than the dashboard gap actually requires.

### Option B — Do nothing; dashboards fall back to raw entities

Leave adapter-role values as process-internal only. A dashboard wanting to show live
hardware I/O binds directly to the installation's raw upstream entity (e.g. the user's own
charger power sensor) instead of anything this integration exposes.

- Pro: Zero implementation cost, no new entities, no change to NF3 or `entity-catalog.md`.
- Con: Defeats hardware-agnosticism for the one surface (dashboards) where it is most
  visible to the user — a dashboard built against a specific installation's raw entities
  cannot be reused across installations with different hardware, which is exactly what the
  adapter-role abstraction exists to avoid everywhere else.

### Option C — Single new owned diagnostic sensor whose attributes carry all adapter-role values

Add one new owned entity, `sensor.smart_charging_adapter_readings` (ADR-0004 population,
`entity_category: diagnostic` per Option A's Pro; object_id pinned per ADR-0013), whose
state is the timestamp of the last successful control-cycle read and whose
`extra_state_attributes` hold one key per currently-wired *read* adapter role (excluding
write-only roles with no value to show, e.g. `notification_target`), set to that role's
most recently read value, or `None` when that role's own reading is unavailable — matching
ADR-0007's fault semantics — without the entity itself becoming unavailable, so every other
attribute keeps rendering exactly as UC11's exception flow requires. The coordinator writes
these attributes through RA3's Store (ADR-0018), the same write path already used for the
other owned diagnostic entities in step 10 of ADR-0006's cycle, sourced from the same reads
it already performs for control logic — no extra adapter reads. A dashboard binds to this
one entity and templates the attribute it wants.

- Pro: Solves the same dashboard-visibility gap as Option A with one new entity instead of
  one per role — a single `strings.json` entry, a single object_id to pin, and a footprint
  that does not grow as later ADRs wire more adapter roles (new roles just add attribute
  keys, no new entity, no new ADR).
- Con: Attribute values are not individually queryable by HA's recorder/history the way a
  first-class sensor's state is, so a dashboard wanting a standalone graph or long-term
  statistics on one specific role (e.g. a historical chart of solar power) cannot get it
  from this entity alone and would still need a dedicated sensor for that one role. The
  reverse cost also applies: because the entity's state (the read timestamp) changes every
  control cycle, its entire attribute blob is written to HA's recorder database at the
  control interval indefinitely — a larger sustained database footprint than the same data
  spread across individually-recorded scalar sensors would produce.

### Option D — Attach the attributes to the existing `sensor.smart_charging_status` entity instead of a new one

Rather than creating any new entity, add the same `extra_state_attributes` to the
already-owned `sensor.smart_charging_status` (ADR-0004's Fault/OK diagnostic sensor).

- Pro: Zero new entities — no new `strings.json` entry, no new object_id to pin, no new
  catalog row at all.
- Con: Overloads an entity whose state and availability lifecycle is defined by ADR-0007's
  fault handling (Fault/OK) with an unrelated concern (hardware-I/O observability); an
  automation or dashboard card that only wants "is the integration healthy" now also carries
  sixteen-plus adapter-role attributes it didn't ask for, and a future change to fault
  semantics risks colliding with this decision's attribute contract on the same entity.

## Decision

Option C. Option A's Con — a maintenance and entity-count cost that scales with every
adapter role, present and future — is disproportionate to a purely observational need, and
partially reverses the same NF3 framing ADR-0003 deliberately established; Option B's Con
is a real, already-identified regression against hardware-agnosticism that this project
does not accept as permanent. Option D's Con (overloading the fault-status entity's
semantics) is rejected in favor of Option C's own, smaller Con: Option C's absence of
per-role recorder history is accepted because nothing in scope today asks for long-term
history or graphing of an individual adapter-role value — if a future dashboard need
requires that for one specific role, applying Option A's mechanism to just that one role
(a dedicated first-class sensor for it) is the appropriate follow-up then, not a blanket
decision now.

`sensor.smart_charging_adapter_readings` is scoped to whichever *read* adapter roles are
actually wired at a given time; it is not itself an adapter and never mediates a
coordinator read or write — it is populated from the same values the coordinator already
read for control logic, written through RA3's Store (ADR-0018) alongside the other owned
diagnostic entities in ADR-0006 step 10.

## Consequences

- `entity-catalog.md` needs a new row under the owned control/diagnostic entities section
  for `sensor.smart_charging_adapter_readings`, describing it as an attribute-bearing
  diagnostic sensor rather than a `state`/`config` row — tracked as follow-up via the
  standard `write-requirement` flow, not done in this ADR.
- ADR-0004's owned-entity list gains this one entity; ADR-0004 itself is not edited (it is
  `Accepted` and immutable) — its Consequences already note the owned-entity inventory
  grows without needing a new ADR unless the two-population boundary changes, and this
  addition does not change that boundary.
- The coordinator (`coordinator.py`, ADR-0006 step 10) must be updated to write this
  entity's attributes through RA3's Store (ADR-0018), alongside the other owned-entity
  updates already happening there; implementation is tracked via the normal
  `write-impl-spec`/task-plan flow, not by this ADR.
- `object_id` for this entity (`adapter_readings`) must be pinned per ADR-0013 from the
  start, not left to translation-key-derived naming.
- A role whose reading is unavailable must resolve to `None` in this entity's attributes,
  per ADR-0007's fault semantics, without the entity itself becoming unavailable — the
  implementation must not conflate "one role's upstream entity is unavailable" with "this
  diagnostic sensor is unavailable," since UC11's exception flow requires the rest of the
  dashboard to keep rendering.
- If a later ADR or implementation task wires an adapter role not yet wired today (e.g.
  `solar_power`), that role's value is added to this entity's attributes as part of that
  later work, with no new ADR required for the addition itself.
- This decision does not cover the config-flow "review mapping" step ADR-0003's
  Consequences also mention — that remains untouched and tracked separately if wanted.
