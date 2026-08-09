# ADR-0021: Adapter-role readings surfaced via a single diagnostic sensor's attributes

Date: 2026-08-09
Status: Proposed

## Context

ADR-0003 chose config-flow entity mapping + Python adapters (its Option B) over synthetic
`sc_`-prefixed proxy entities (its Option A): each adapter role (`grid_voltage`,
`net_power`, `charger_power`, `charger_status`, `charger_current`, `ev_soc`,
`ev_battery_capacity`, `car_home`, `vehicle_charge_limit`, `solar_power`, `solar_forecast`,
`departure_external`, `home_day_external`) is config-entry mapping data and a Python-side
adapter read/write, not an HA entity. `entity-catalog.md` already documents these rows as
`adapter role`, explicitly not catalog entities.

This is sufficient for the coordinator's own control logic (it reads adapters directly),
but it leaves no fixed, shippable entity a Lovelace dashboard can bind to for showing live
hardware I/O — e.g. current charger power, EV SOC, solar production, charger status. Only
the `config` rows and ADR-0004's owned control/diagnostic entities are dashboard-safe
today; adapter-role values are invisible outside the integration's own process. ADR-0003's
Consequences already flagged this gap as expected follow-up work. Issue #51 tracks it,
specifically scoped to the dashboard-observability use case (not the config-flow "review
mapping" step ADR-0003 also mentions, which is out of scope here).

Whatever this decision adds must not reopen NF3's "no new HA entities for hardware inputs"
promise more than necessary — NF3 and `entity-catalog.md` were already reworded once
(ADR-0003) specifically to make adapter roles code-level, not entities, and a large new
batch of hardware-mirroring entities would partially reverse that framing.

This ADR only concerns adapter roles that already have a wired adapter (ADR-0003's UC01-
UC04 scope plus the four already-wired control-cycle inputs); roles ADR-0003 itself
deferred (e.g. `solar_forecast`, `car_home`, `vehicle_charge_limit`, `ev_battery_capacity`,
`departure_external`, `home_day_external`) are surfaced by this mechanism automatically
once a later ADR wires their adapters — this ADR does not need to be revisited when that
happens.

## Considered options

### Option A — One new diagnostic sensor entity per adapter role

Add a read-only `sensor.smart_charging_diag_<role>` (ADR-0004 owned-entity population, one
per adapter role) mirroring that role's current value, updated by the coordinator each
control cycle. The coordinator continues reading the adapter directly for control logic;
these sensors exist purely for observability.

- Pro: Each value is a first-class HA entity — full recorder history, standalone graph
  cards, and the standard `entity_category: diagnostic` pattern users already expect from
  other integrations.
- Con: Roughly doubles the integration's entity count today (13 roles) and grows further as
  deferred roles get adapters later; each one needs its own `strings.json`/translation
  entries (repeating the per-entity cost `write-requirement`/T5.2-style work just paid),
  its own object_id pinned per ADR-0013, and its own test coverage — a maintenance burden
  disproportionate to a value that is purely observational, and a larger reversal of NF3's
  "no new entities for hardware inputs" framing than the dashboard gap actually requires.

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
object_id pinned per ADR-0013), whose state is the timestamp of the last successful
control-cycle read and whose `extra_state_attributes` hold one key per currently-wired
adapter role, set to that role's most recently read value. The coordinator writes these
attributes in step 10 of ADR-0006's cycle (alongside the other owned-entity updates),
sourced from the same reads it already performs for control logic — no extra adapter
reads. A dashboard binds to this one entity and templates the attribute it wants.

- Pro: Solves the same dashboard-visibility gap as Option A with one new entity instead of
  up to thirteen — a single `strings.json` entry, a single object_id to pin, and a
  footprint that does not grow as later ADRs wire more adapter roles (new roles just add
  attribute keys, no new entity, no new ADR).
- Con: Attribute values are not individually queryable by HA's recorder/history the way a
  first-class sensor's state is, so a dashboard wanting a standalone graph or long-term
  statistics on one specific role (e.g. a historical chart of solar power) cannot get it
  from this entity alone and would still need a dedicated sensor for that one role.

## Decision

Option C. Option A's Con — a maintenance and entity-count cost that scales with every
adapter role, present and future — is disproportionate to a purely observational need, and
partially reverses the same NF3 framing ADR-0003 deliberately established; Option B's Con
is a real, already-identified regression against hardware-agnosticism that this project
does not accept as permanent. Option C's Con (no per-role recorder history) is accepted
because nothing in scope today asks for long-term history or graphing of an individual
adapter-role value — if a future dashboard need requires that for one specific role,
promoting that one role to a first-class sensor (Option A, narrowed to a single role) is
the appropriate follow-up then, not a blanket decision now.

`sensor.smart_charging_adapter_readings` is scoped to whichever adapter roles are actually
wired at a given time (currently the roles ADR-0003 covers); it is not itself an adapter
and never mediates a coordinator read or write — it is populated from the same values the
coordinator already read for control logic, per ADR-0006 step 10.

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
  entity's attributes alongside the other owned-entity updates already happening there;
  implementation is tracked via the normal `write-impl-spec`/task-plan flow, not by this
  ADR.
- `object_id` for this entity (`adapter_readings`) must be pinned per ADR-0013 from the
  start, not left to translation-key-derived naming.
- If a later ADR wires an adapter role ADR-0003 deferred (e.g. `solar_forecast`), that
  role's value is added to this entity's attributes as part of that later work, with no new
  ADR required for the addition itself.
- Issue #51 is satisfied by this decision; the config-flow "review mapping" step ADR-0003's
  Consequences also mention remains untouched and tracked separately if wanted.
