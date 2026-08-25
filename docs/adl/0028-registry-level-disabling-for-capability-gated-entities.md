# ADR-0028: Registry-level disabling for capability-gated entities

Date: 2026-08-21
Status: Proposed

## Context

Three config-time capability flags already exist (`const.py`): `CONF_SOLAR_AVAILABLE`,
`CONF_CAPTAR_AVAILABLE`, `CONF_DEADLINE_AVAILABLE`. Each says whether a piece of hardware or a
user-facing feature is actually present for this installation, resolved once per
`async_setup_entry` from `entry.data` (`SmartChargingConfig`, `config.py`), and re-resolved on
every reload — including every options-flow save (ADR-0008).

Today these flags gate different things, inconsistently:

- `ModeSelect`'s option list (`select.py`, built inline from `BASE_/SOLAR_/CAPTAR_CAPABLE_MODES`;
  `engines/capability_gate.py` answers the equivalent runtime question for `coordinator_cycle.py`)
  — restricts which modes are *selectable*, not whether the select entity itself exists.
- `SmartChargingDepartureTime`'s dashboard visibility (`time.py`) — when `deadline_available` is
  `False`, the entity's `_owned_labels` drops `LABEL_SC_RUNTIME` (synced via
  `SmartChargingEntity.async_added_to_hass`, `entity.py`), so the runtime dashboard's
  `auto-entities` card (label-driven per the 2026-07-08 runtime-dashboard design doc's Decision 1,
  R19 AC4) stops listing it. The entity itself stays fully created, enabled, and visible
  everywhere else HA surfaces a normal diagnostic/control entity — Settings → Entities, areas,
  the energy dashboard picker, service calls.
- Nothing at all, for `solar_available`: `SolarSurplusSensor` (`sensor.py`) is always created and
  always enabled regardless of whether a solar meter is configured. A no-solar install still gets
  a permanently-meaningless sensor, filed under the device's Diagnostic section but otherwise
  fully visible and pickable like any other entity.

`captar_available` is deliberately **not** in scope for entity-level gating, and that is worth
stating explicitly rather than leaving as an omission: `entity-catalog.md`'s CapTar-dependent-rows
note says `sensor.smart_charging_effective_peak_limit` and `sensor.smart_charging_peak_headroom_a`
"still resolve and are still surfaced for observability" when the capability is absent — only the
R3 clamp step that *consults* them is skipped, not the computation that produces them. Disabling
either sensor at the registry level would contradict that already-settled decision.
`sensor.smart_charging_monthly_peak_kw` is not captar-gated at all in the catalog — it tracks net
import unconditionally, independent of `captar_available` — so it was never a candidate for this
ADR's scope either.

This ADR is about extending capability gating to the entity registry's own `disabled_by`
mechanism (HA's documented way to mark an integration-owned entity as not applicable this
install — https://developers.home-assistant.io/docs/entity_registry_index#disabled_by) for the
entities above, so a capability-absent entity is actually hidden from Settings → Entities and
everywhere else that reads registry state, not just from the custom runtime dashboard.

A mechanical constraint shapes the whole decision: **HA does not add a registry-disabled entity
to hass** — `async_added_to_hass` is not called for it on any subsequent load (the check happens
in `EntityPlatform`, before the add-to-hass step that would otherwise call it). A sync mechanism
that lives inside that hook (like the current label sync) can therefore disable an entity, but
can never be the thing that re-enables it later — once disabled, the entity's own instance never
runs again to notice the capability came back. Any mechanism that touches `disabled_by` has to
run against the registry directly, from platform setup code, independent of whether the entity
ends up added to hass this reload.

That constraint has a second-order effect on `entity.py`'s *existing* label mechanism: once any
entity can become registry-disabled, the same hook-based sync that currently manages
`_owned_labels` is exposed to the identical problem — a label change made while the capability is
off can never be applied, because the entity that would apply it is never added to hass. This ADR
therefore also has to decide what happens to that existing mechanism, not just how the new
`disabled_by` behavior is added alongside it.

A related question worth settling explicitly: `SmartChargingDepartureTime` is a `RestoreEntity`
whose restored value is only *read* inside `async_added_to_hass`, which never runs while the
entity is registry-disabled — so it might appear that a user's set departure time would revert to
its constructor default (R14) across a `deadline_available` off→on cycle. It doesn't:
`RestoreEntity.async_internal_will_remove_from_hass` writes the entity's last state into HA's
`RestoreStateData` cache (keyed by `entity_id`) on *every* removal, disable-triggered or not, and
that write is exactly what `async_added_to_hass` reads back on re-enable — the cache isn't cleared
just because the entity was disabled for a while. So the restored value survives a same-runtime
off→on cycle correctly, with no engineering required beyond what `RestoreEntity` already does
(a restart-spanning disabled window isn't covered by this claim or by the test that demonstrates
it — see Consequences).

`notification_available` is a fourth capability of the same conceptual kind (functionally: a
notify target being configured), but no owned entity depends on it today — out of scope for the
decision below; see Consequences. This ADR also does not introduce a new requirement: it
generalizes R18's existing capability-gating intent (already applied to mode selectability and,
via R19 AC4, to dashboard visibility) to entity-registry visibility, rather than implementing an
acceptance criterion that names registry disabling specifically.

## Considered options

### Option A — `entity_registry_enabled_default` only, no reload resync

Compute `_attr_entity_registry_enabled_default` per-instance from the relevant capability flag.
HA reads this attribute only at an entity's first-ever registration.

- Pro: Zero new registry-write code for the first-install case — a single class attribute per
  gated entity, using a mechanism HA already provides for exactly this "not relevant for this
  install" case.
- Con: Only correct for a brand-new installation. Once an entity is registered, this attribute is
  never consulted again — a capability that changes later (a solar meter added, a departure
  deadline no longer tracked) via an options-flow reconfigure leaves the entity's `disabled_by`
  state permanently stale in whichever direction it started, which is the exact gap motivating
  this ADR in the first place.

### Option B — Keep the existing label mechanism untouched; add a separate, disabled_by-only sync for just the newly gated entities

Leave `entity.py`'s `async_added_to_hass`-based `_owned_labels` sync exactly as it is today, and
add a second, independent mechanism — a setup-time registry write — that handles only
`disabled_by` for `SolarSurplusSensor` and `SmartChargingDepartureTime`.

- Pro: Smallest possible diff — touches only the newly gated entities and adds new code, without
  reworking anything that already works for the five entities that only ever carry a constant
  label (`HomeDaySwitch`, `TargetCurrentNumber`, `SocLimitOverrideNumber`, `ModeSelect`,
  `ProfileSelect`).
- Con: Leaves two different registry-sync mechanisms permanently coexisting — a hook-based one
  for labels, a setup-time one for `disabled_by` — for `SmartChargingDepartureTime`, which needs
  both, with no shared code path between them despite solving the same underlying problem. Worse,
  it doesn't actually fix the label side of the problem this ADR's Context raises: that entity can
  now become registry-disabled, so the exact same "hook never runs while disabled" failure that
  motivates moving `disabled_by` out of `async_added_to_hass` also applies to its label sync —
  Option B relocates that bug onto a smaller surface (label staleness only while also
  capability-disabled) rather than removing it.

### Option C — Unified setup-time registry sync, replacing the hook-based mechanism entirely

Add two small helpers to `entity.py`: one that syncs `disabled_by` (called from each platform's
`async_setup_entry`, keyed on `unique_id` — the only identifier available before an entity has
been added, since `entity_id` doesn't exist yet for a not-yet-registered one) and one that syncs
labels (called after `async_add_entities`, once `entity_id` is guaranteed). Apply both uniformly
to every `_owned_labels`-carrying class — not just the newly capability-gated ones — and delete
the existing `async_added_to_hass` registry override from `SmartChargingEntity` entirely.

The pre/post split is not a stylistic choice, but the reason is narrower than it might first
appear: HA removes a live entity immediately when its registry row is marked disabled (the
registry-update listener calls `async_remove()` on the spot), so a *post*-add `disabled_by` write
would still take effect the same reload, not one reload later. The real reason to write it
*before* `async_add_entities` is to avoid the transient churn of adding an entity live (firing
`async_added_to_hass`, subscribing callbacks, writing an initial state) only to remove it again
moments later in the same setup pass. Labels have no equivalent pre-add option regardless: HA's
`Entity` base has no attribute for declaring initial labels, and
`registry.async_update_entity(..., labels=...)` requires a registry row that doesn't exist for a
brand-new entity until `async_add_entities` creates it.

- Pro: One mechanism, one place (`entity.py`) to read to understand how any owned entity's
  registry state gets kept current, for every capability-gated and non-gated `_owned_labels`
  entity alike. Fixes the label-staleness failure mode for real (labels are now written from
  registry-side code that doesn't depend on the entity being added to hass) rather than avoiding
  it only for entities that happen not to need `disabled_by` yet.
- Con: Touches five entity classes (`HomeDaySwitch`, `TargetCurrentNumber`,
  `SocLimitOverrideNumber`, `ModeSelect`, `ProfileSelect`) that have no bug today and no
  capability dependency — their call site moves from an entity-instance hook to their platform's
  `async_setup_entry`, for consistency rather than to fix anything currently broken for them.

## Decision

Option C, combined with Option A rather than instead of it: Option A's `_attr_entity_registry_enabled_default`
is still necessary as the first-registration half of the mechanism (there is no existing registry
row for a `sync_disabled_by` call to act on before an entity's first `async_add_entities`), but it
is not sufficient on its own — the reconfigure case is Option A's Con and the reason this ADR
exists. The real choice is B vs. C, and it turns on whether the hook-based label mechanism can
keep working once *any* entity in the same base class can become registry-disabled: it can't, per
Context — a hook that only runs on an added-to-hass entity is structurally the wrong place for
state that must survive the entity being disabled. Since `SmartChargingDepartureTime` needs both
`disabled_by` and label syncing, Option B's narrower diff still has to build the setup-time shape
for that one class anyway; Option C simply recognizes that the same shape is strictly better for
the other five classes too — one mechanism to maintain instead of two, at the cost of a mechanical
(not behavioral) call-site change for entities that aren't capability-gated. That cost is small
and one-time; Option B's ongoing cost (two coexisting mechanisms, and a label bug merely relocated
rather than fixed) is not.

The `sync_disabled_by` helper must leave any non-`None`, non-`RegistryEntryDisabler.INTEGRATION`
`disabled_by` value (notably `USER`) untouched in either direction — a capability change must
never silently override a user's own choice to enable or disable an entity themselves.

`SmartChargingDepartureTime` keeps its existing per-instance `_owned_labels` gating on
`deadline_available` *in addition to* the new `disabled_by` gating, even though a
registry-disabled entity cannot appear on the label-driven dashboard regardless of its labels:
the two are independent because a user can force an entity back on (`disabled_by=USER`) while the
capability is still absent, and in that case the label must still reflect `deadline_available`
correctly so the dashboard stays consistent even for a capability-absent entity the user chose to
re-enable.

## Consequences

- `entity.py`: remove `SmartChargingEntity.async_added_to_hass`'s registry-write body; add
  `sync_disabled_by(registry, platform, unique_id, *, capability_met: bool)` (pre-add, looks up
  the entity via `registry.async_get_entity_id`, no-ops if not yet registered) and
  `sync_labels(registry, entity_id, *, owned_labels, manageable_labels)` (post-add) as the two
  setup-time helpers.
- `sensor.py`: `SolarSurplusSensor` gains `_attr_entity_registry_enabled_default` from
  `solar_available` and a `sync_disabled_by` call keyed on the same flag. `MonthlyPeakSensor`,
  `EffectivePeakLimitSensor`, `PeakHeadroomSensor` are unaffected by this ADR — see Context.
- `time.py`: `SmartChargingDepartureTime` gains `_attr_entity_registry_enabled_default` and a
  `sync_disabled_by` call keyed on `deadline_available`, alongside its existing (now
  setup-time-relocated) label gating. No restore-state cost across a same-runtime
  `deadline_available` off→on cycle — see Context for the mechanism.
- `switch.py`, `number.py`, `select.py`: `HomeDaySwitch`, `TargetCurrentNumber`,
  `SocLimitOverrideNumber`, `ModeSelect`, `ProfileSelect` move their label-sync call from the
  removed `async_added_to_hass` hook to the same `sync_labels` call, after `async_add_entities`,
  in each file's `async_setup_entry` — no behavior change for these five; only the mechanism
  producing it changes.
- Follow-up: the implementation spec + TDD plan (`write-impl-spec`) this ADR called for has since
  been filed and implemented (docs/plans/2026-08-21-capability-gated-entity-registry-disabling*.md,
  epic #779); it covers the pre-add/post-add ordering, the USER-`disabled_by` non-override rule,
  and the departure-time restore-state behavior above as an explicit test case.
- Follow-up: if a future owned entity is ever gated by a notification-availability capability, it
  should use these same two helpers rather than inventing a third mechanism — this ADR's Decision
  is not scoped to today's flags, only its concrete task list is.
- No change to `docs/design/system-design.md` or any existing `Accepted` ADR's Decision text is
  required — this ADR extends ADR-0004's owned-entity lifecycle (registry-level enable/disable is
  part of "created, named, and retired entirely by" the integration) and does not contradict
  ADR-0013 (object_id stability) or ADR-0022 (dashboard delivery mechanism, which governs the
  label-driven dashboard section this ADR leaves untouched). It also does not require an
  `entity-catalog.md` edit — the catalog's existing CapTar-observability note is respected, not
  overridden.
