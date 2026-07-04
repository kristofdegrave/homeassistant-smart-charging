# ADR-0004: Owned control/diagnostic entities vs. mapped hardware entities

Date: 2026-07-04
Status: Accepted

## Context

This is backfilled from Decision 3 of
`docs/plans/2026-07-04-integration-architecture-design.md` (PR #30, still open — see
ADR-0001's plan to give each of that doc's decisions its own ADR before #30 merges).

The `smart_charging` integration needs to represent two very different kinds of Home
Assistant entities:

- The user's **existing** charger, EV, solar, and grid entities — created and owned by
  other integrations, referenced only by `entity_id`, and read (or in the charger's case,
  written) by the adapter layer.
- **New** entities this integration itself needs to create to expose control and
  diagnostic surface to the user — e.g. which profile/mode is active, a SoC override, WFH
  status, departure time, and diagnostic readouts of what the coordinator computed.

Both kinds live in the same HA entity registry, and both are visible in the same
dashboard/automation surface once the integration is installed. Without a clear rule for
which entities the integration is allowed to create, rename, or remove, and which it must
only ever read or write by reference, later contributors (or an automated refactor) have
no structural signal for "is this entity safe to touch?" — that ambiguity is exactly the
kind of decision this project's ADR process exists to make explicit and durable (see
ADR-0001).

This decision also has to say where entity *state* lives. The integration has no backend
of its own (no database, no cloud service) — anything it doesn't get from HA's own
mechanisms would require inventing custom storage, which is a cost this decision should
avoid if HA already provides an adequate mechanism.

This decision depends on ADR-0002 (domain/package layout), which reserves `entity.py` at
the package root specifically for "base classes for owned entities" — i.e. ADR-0002
already assumes the two-population split this ADR now makes explicit and justifies. It
also relates to ADR-0003 (adapter layer for reading/writing mapped entities), which is
expected to define how mapped entities are accessed; if ADR-0003 has not yet been accepted
by the time this ADR lands, the relationship still holds in prose: the adapter layer is
the only code path this integration uses to touch mapped entities; owned entities never go
through it, since the integration has direct authority over its own.

**Known conflict, tracked in [issue #29](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/29).**
`requirements.md` (NF3) and `entity-catalog.md` currently read literally — every mapped
hardware value is read from a concrete `sc_`-prefixed **wrapper entity**, and raw upstream
entities are "never catalog rows." This ADR's mapped-entity side (Option B, referenced
directly by `entity_id`, no wrapper entity) conflicts with that literal wording, for the
same reason Decision 2 of the design doc does. Issue #29 already proposes the resolution
this ADR assumes: reword NF3/`entity-catalog.md` to describe the wrapper as a code-level
adapter abstraction for *mapped* entities, while keeping this ADR's owned control/
diagnostic entities as real HA entities — which is exactly what issue #29 asks to
preserve. Until #29's reword lands via the standard write-requirement flow, NF3 and
`entity-catalog.md` remain the authoritative source of truth per this project's
methodology, and this ADR's mapped-entity side should not be treated as implementable
ahead of that reword landing. This ADR's owned-entity side (Option B's second population)
is not blocked by #29 either way, since issue #29 explicitly proposes keeping owned
entities as real HA entities.

**Separate, additional conflict with `entity-catalog.md` (not covered by issue #29).**
Several of this ADR's owned entities already have catalog rows under different HA
domains: `input_select.sc_active_profile`, `input_select.sc_active_mode`,
`input_number.sc_active_soc`, and `input_datetime.sc_departure_<dow>`/`_holiday`/
`_home_day` are catalogued today as **`input_*` helper entities**, whereas this ADR makes
them **native platform entities** (`select.smart_charging_profile`,
`select.smart_charging_mode`, `number.smart_charging_soc_limit_override`,
`time.smart_charging_departure_*`) owned and created by the integration itself. That is a
bigger change than the `sc_` → `smart_charging_` prefix noted in Consequences — it swaps
the entity domain and creation mechanism (user-configured helper vs. integration-owned
platform entity). The WFH switch and plug-in-reminder binary_sensor, by contrast, are
genuinely new — `entity-catalog.md` has no row for either today. Both kinds of change need
`entity-catalog.md` updated to match (renaming/redomaining the existing rows, and adding
the two new ones); tracked as follow-up in Consequences.

## Considered options

### Option A — Single unified entity registry/namespace (integration treats mapped and
owned entities the same way, e.g. wrapping every hardware entity in an integration-owned
proxy entity alongside the control entities)

- Pro: One entity-handling code path — every entity the integration deals with is created,
  named, and reasoned about the same way, with no special-casing for "entities we don't
  own."
- Con: Wrapping or otherwise unifying the user's existing charger/EV/solar/grid entities
  under this integration's device/namespace blurs who owns them for restore-state,
  renaming, and removal purposes — a config change or integration reload could plausibly
  rename, orphan, or delete the user's pre-existing entity (or a proxy tightly coupled to
  its lifecycle), which is destructive to a device the user configured outside this
  integration and does not expect this integration to manage. It also leaves no clean
  signal for a future contributor asking "can I safely change how this entity's unique_id
  is generated?" — the answer differs by entity, but a unified namespace hides that
  difference instead of encoding it structurally.

### Option B — Two clearly separated populations: mapped entities (referenced by
`entity_id`, never modified/renamed) and owned entities (created and fully managed by
`smart_charging`, grouped under one HA device)

- Pro: The boundary is structural, not just documented convention — mapped entities are
  read-only references the adapter layer holds onto, owned entities are the only ones this
  integration creates, names, and is responsible for through HA's entity-registry
  lifecycle (restore-state, unique_id stability, removal on unload). Anyone asking "is it
  safe to rename/remove this entity from smart_charging code?" gets a structural answer:
  yes for owned, never for mapped.
- Con: The integration must maintain two different mental models and code paths — one for
  entities it merely observes/drives via reference, one for entities it fully owns — which
  is more upfront conceptual overhead than a single unified treatment, and every new
  feature has to decide up front which population a given entity belongs to.

## Decision

Option B. Two distinct entity populations:

1. **Mapped hardware entities** — the user's existing charger/EV/solar/grid entities,
   referenced by `entity_id`, never modified or renamed by this integration. (Read/write
   access to these goes through the adapter layer — ADR-0003, once accepted; see the
   Context note above if it is not yet accepted.)
2. **Owned control/diagnostic entities** — new entities created by `smart_charging`,
   grouped under one HA device (e.g. "Smart Charging"):
   - `select.smart_charging_profile` (Manual / Auto)
   - `select.smart_charging_mode` (Manual profile's mode override: Solar / SolarOnly /
     Captar / Power / Off)
   - `number.smart_charging_soc_limit_override`
   - `time.smart_charging_departure_*`
   - `switch.smart_charging_wfh`
   - `sensor.smart_charging_desired_current`, `sensor.smart_charging_effective_peak_limit`,
     `sensor.smart_charging_active_mode`, `sensor.smart_charging_status` (Fault/OK)
   - `binary_sensor.smart_charging_plug_in_reminder`

Option B is chosen over Option A because the two populations already have fundamentally
different ownership semantics — the user's hardware entities must never be renamed or
removed by this integration, while the owned entities are created, named, and retired
entirely by it. Encoding that as two populations (Option B's structural boundary) rather
than one unified namespace (Option A) avoids the ambiguity Option A's Con describes:
there is never a question of whether it's safe to touch a given entity, because which
population it belongs to answers that directly.

State for owned entities persists via HA's normal entity-registry restore-state; no
custom storage is needed for them.

## Consequences

- `entity.py` (reserved by ADR-0002) is where the owned-entity base classes live; any new
  owned entity is added there and grouped under the "Smart Charging" device, never mixed
  into the adapter layer's mapped-entity handling.
- Mapped entities are never given `unique_id`s or names by this integration and are never
  targets of `async_remove`/rename logic — only the adapter layer (ADR-0003, once
  accepted) reads or writes them, always by the `entity_id` the user configured.
- Restore-state correctness for owned entities is HA's responsibility (standard
  entity-registry behavior), so this integration does not need its own persistence layer
  for profile/mode/SoC-override/departure-time state — a deliberate scope reduction this
  decision buys.
- Follow-up: once ADR-0003 is accepted, revisit this ADR's Context note about the adapter
  layer being "expected to define" mapped-entity access, and update the cross-reference
  if ADR-0003's final shape differs from what's assumed here.
- Follow-up: the concrete list of owned entities above will grow as later use-cases
  (R5–R13, per ADR-0002's Context) are implemented; this ADR records the split, not the
  final entity inventory — new owned entities don't need a new ADR unless they change the
  two-population boundary itself.
- Follow-up: issue #29 (reword NF3 and `entity-catalog.md` to describe mapped-entity
  access as a code-level adapter abstraction, not a literal wrapper entity, while keeping
  owned control/diagnostic entities as real HA entities) must land, via the standard
  write-requirement flow, before the mapped-entity side of this ADR is implemented against
  real hardware — it is not blocked on ADR-0003 specifically, but on that requirements
  reword.
- Follow-up: `entity-catalog.md` needs a second, separate update (via the standard
  write-requirement flow, tracked either as part of issue #29 or a new issue) to reconcile
  its existing owned-entity rows with this ADR — `input_select.sc_active_profile`,
  `input_select.sc_active_mode`, `input_number.sc_active_soc`, and
  `input_datetime.sc_departure_*` move from user-configured `input_*` helpers to native
  platform entities (`select`/`number`/`time`) owned and created by the integration under
  the `smart_charging_` prefix; the WFH switch and plug-in-reminder binary_sensor are
  added as entirely new rows, since the catalog has none today.
