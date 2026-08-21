# ADR-0028: Registry-level disabling for capability-gated entities

Date: 2026-08-21
Status: Proposed

## Context

Three config-time capability flags already exist (`const.py`): `CONF_SOLAR_AVAILABLE`,
`CONF_CAPTAR_AVAILABLE`, `CONF_DEADLINE_AVAILABLE`. Each says whether a piece of hardware or a
user-facing feature is actually present for this installation, resolved once per
`async_setup_entry` from `entry.data` (`SmartChargingConfig`, `config.py`), and re-resolved on
every reload — including every options-flow save (ADR-0008).

Today these flags gate three different things, inconsistently:

- `ModeSelect`'s option list (`select.py`, via `engines/capability_gate.py`) — restricts which
  modes are *selectable*, not whether the select entity itself exists.
- `SmartChargingDepartureTime`'s dashboard visibility (`time.py`) — when `deadline_available` is
  `False`, the entity's `_owned_labels` drops `LABEL_SC_RUNTIME` (synced via
  `SmartChargingEntity.async_added_to_hass`, `entity.py`), so the runtime dashboard's
  `auto-entities` card (label-driven per the 2026-07-08 runtime-dashboard design doc's Decision 1)
  stops listing it. The entity itself stays fully created, enabled, and visible everywhere else
  HA surfaces entities — Settings → Entities, areas, the energy dashboard picker, service calls.
- Nothing at all, for `solar_available`/`captar_available`: `SolarSurplusSensor`,
  `MonthlyPeakSensor`, `EffectivePeakLimitSensor`, and `PeakHeadroomSensor` (`sensor.py`) are
  always created and always enabled, regardless of whether the matching hardware exists. A
  no-solar install still gets a permanently-meaningless `SolarSurplusSensor`, visible everywhere
  a normal entity is.

This ADR is about extending capability gating to the entity registry's own `disabled_by`
mechanism (HA's documented way to mark an integration-owned entity as not applicable this
install — https://developers.home-assistant.io/docs/entity_registry_index#disabled_by), so a
capability-absent entity is actually hidden from Settings → Entities and everywhere else that
reads registry state, not just from the custom runtime dashboard.

A mechanical constraint shapes the whole decision: **HA never instantiates a registry-disabled
entity** — `async_added_to_hass` is not called for it on any subsequent load. A sync mechanism
that lives inside that hook (like the current label sync) can therefore disable an entity, but
can never be the thing that re-enables it later — once disabled, the entity's own instance never
runs again to notice the capability came back. Any mechanism that touches `disabled_by` has to
run against the registry directly, from platform setup code, independent of whether the entity
ends up instantiated this reload.

That constraint has a second-order effect on `entity.py`'s *existing* label mechanism: once any
entity can become registry-disabled, the same hook-based sync that currently manages
`_owned_labels` is exposed to the identical problem — a label change made while the capability is
off can never be applied, because the entity that would apply it is never instantiated. This ADR
therefore also has to decide what happens to that existing mechanism, not just how the new
`disabled_by` behavior is added alongside it.

`notification_available` is a fourth capability of the same conceptual kind (functionally: a
notify target being configured), but no owned entity depends on it today — out of scope for the
decision below; see Consequences.

## Considered options

### Option A — `entity_registry_enabled_default` only, no reload resync

Compute `_attr_entity_registry_enabled_default` per-instance from the relevant capability flag.
HA reads this attribute only at an entity's first-ever registration.

- Pro: Zero new registry-write code — a single class attribute per gated entity, using a
  mechanism HA already provides for exactly this "not relevant for this install" case.
- Con: Only correct for a brand-new installation. Once an entity is registered, this attribute is
  never consulted again — a capability that changes later (a solar meter added, a CapTar
  subscription lapsing) via an options-flow reconfigure leaves the entity's `disabled_by` state
  permanently stale in whichever direction it started, which is the exact gap motivating this
  ADR in the first place.

### Option B — Keep the existing label mechanism untouched; add a separate, disabled_by-only sync for just the newly gated entities

Leave `entity.py`'s `async_added_to_hass`-based `_owned_labels` sync exactly as it is today, and
add a second, independent mechanism — a setup-time registry write — that handles only
`disabled_by` for `SolarSurplusSensor`, the three captar sensors, and
`SmartChargingDepartureTime`.

- Pro: Smallest possible diff — touches only the newly gated entities and adds new code, without
  reworking anything that already works for the five entities that only ever carry a constant
  label (`HomeDaySwitch`, `TargetCurrentNumber`, `SocLimitOverrideNumber`, `ModeSelect`,
  `ProfileSelect`).
- Con: Leaves two different registry-sync mechanisms permanently coexisting — a hook-based one
  for labels, a setup-time one for `disabled_by` — for entities (`SmartChargingDepartureTime`)
  that need both, with no shared code path between them despite solving the same underlying
  problem. Worse, it doesn't actually fix the label side of the problem this ADR's Context
  raises: `SmartChargingDepartureTime` can now become registry-disabled, so the exact same
  "hook never runs while disabled" failure that motivates moving `disabled_by` out of
  `async_added_to_hass` also applies to its label sync — Option B relocates that bug onto a
  smaller surface (label staleness only while also capability-disabled) rather than removing it.

### Option C — Unified setup-time registry sync, replacing the hook-based mechanism entirely

Add two small helpers to `entity.py`: one that syncs `disabled_by` (called from each platform's
`async_setup_entry`, before `async_add_entities`) and one that syncs labels (called after
`async_add_entities`). Apply both uniformly to every `_owned_labels`-carrying class — not just the
three newly capability-gated entities — and delete the existing `async_added_to_hass` registry
override from `SmartChargingEntity` entirely.

The pre/post split is not a stylistic choice: `disabled_by` must be written *before*
`async_add_entities` so a capability turning off takes effect the same reload, rather than one
reload later (once already-live, an entity stays live until the *next* setup pass notices);
labels can only be written *after* — HA's `Entity` base has no attribute for declaring initial
labels, and `registry.async_update_entity(..., labels=...)` requires a registry row that doesn't
exist for a brand-new entity until `async_add_entities` creates it.

- Pro: One mechanism, one place (`entity.py`) to read to understand how any owned entity's
  registry state gets kept current, for every capability-gated and non-gated `_owned_labels`
  entity alike. Fixes the label-staleness failure mode for real (labels are now written from
  registry-side code that doesn't depend on the entity being instantiated) rather than avoiding it
  only for entities that happen not to need `disabled_by` yet.
- Con: Touches five entity classes (`HomeDaySwitch`, `TargetCurrentNumber`,
  `SocLimitOverrideNumber`, `ModeSelect`, `ProfileSelect`) that have no bug today and no
  capability dependency — their call site moves from an entity-instance hook to their platform's
  `async_setup_entry`, for consistency rather than to fix anything currently broken for them.

## Decision

Option C. Option A is rejected outright — it doesn't solve the reconfigure case at all, which is
the problem this ADR exists to fix. The real choice is B vs. C, and it turns on whether the
hook-based label mechanism can keep working once *any* entity in the same base class can become
registry-disabled: it can't, per Context — a hook that only runs on a live, instantiated entity
is structurally the wrong place for state that must survive the entity being disabled. Since
`SmartChargingDepartureTime` needs both `disabled_by` and label syncing, Option B's narrower diff
still has to build the setup-time shape for that one class anyway; Option C simply recognizes that
the same shape is strictly better for the other five classes too — one mechanism to maintain
instead of two, at the cost of a mechanical (not behavioral) call-site change for entities that
aren't capability-gated. That cost is small and one-time; Option B's ongoing cost (two coexisting
mechanisms, and a label bug merely relocated rather than fixed) is not.

Both new helpers must leave any non-`None`, non-`RegistryEntryDisabler.INTEGRATION` `disabled_by`
value (notably `USER`) untouched in either direction — a capability change must never silently
override a user's own choice to enable or disable an entity themselves.

## Consequences

- `entity.py`: remove `SmartChargingEntity.async_added_to_hass`'s registry-write body; add
  `sync_disabled_by(registry, entity_id, *, capability_met: bool)` and
  `sync_labels(registry, entity_id, *, owned_labels, manageable_labels)` as the two setup-time
  helpers.
- `sensor.py`: `SolarSurplusSensor` gains `_attr_entity_registry_enabled_default` from
  `solar_available` and a `sync_disabled_by` call keyed on the same flag; `MonthlyPeakSensor`,
  `EffectivePeakLimitSensor`, `PeakHeadroomSensor` gain the same, keyed on `captar_available`.
- `time.py`: `SmartChargingDepartureTime` gains `_attr_entity_registry_enabled_default` and a
  `sync_disabled_by` call keyed on `deadline_available`, alongside its existing (now
  setup-time-relocated) label gating.
- `switch.py`, `number.py`, `select.py`: `HomeDaySwitch`, `TargetCurrentNumber`,
  `SocLimitOverrideNumber`, `ModeSelect`, `ProfileSelect` move their label-sync call from the
  removed `async_added_to_hass` hook to the same `sync_labels` call, after `async_add_entities`,
  in each file's `async_setup_entry` — no behavior change for these five; only the mechanism
  producing it changes.
- Follow-up: file the implementation spec + TDD plan (`write-impl-spec`) once this ADR is
  Accepted; it must cover the pre-add/post-add ordering and the USER-`disabled_by` non-override
  rule as explicit test cases, not just the happy-path enable/disable transitions.
- Follow-up: if a future owned entity is ever gated by a notification-availability capability,
  it should use these same two helpers rather than inventing a third mechanism — this ADR's
  Decision is not scoped to today's three flags, only its concrete task list is.
- No change to `docs/design/system-design.md` or any existing `Accepted` ADR's Decision text is
  required — this ADR extends ADR-0004's owned-entity lifecycle (registry-level enable/disable is
  part of "created, named, and retired entirely by" the integration) and does not contradict
  ADR-0013 (object_id stability) or ADR-0022 (dashboard delivery mechanism, which governs the
  label-driven dashboard section this ADR leaves untouched).
