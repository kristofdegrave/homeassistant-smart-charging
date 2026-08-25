# Capability-gated entity registry disabling — design

**Date:** 2026-08-21
**Status:** draft (issue #786, ADR-0028)
**Type:** implementation design (a slice of an already-drafted architectural decision — not a new
decision; ADR-0028's own Status flips to Accepted independently of this document, per the
project's usual post-merge follow-up)

This document is the `docs/plans` implementation spec [ADR-0028](../adl/0028-registry-level-disabling-for-capability-gated-entities.md)
itself calls for. It derives the concrete files, helper signatures, and TDD build order for:
registry-level `disabled_by` gating on `SolarSurplusSensor` (`solar_available`) and the 9
`SmartChargingDepartureTime` entities (`deadline_available`), and the accompanying replacement of
`entity.py`'s `async_added_to_hass`-based label sync with a unified setup-time mechanism, applied
uniformly to every `_owned_labels`-carrying class. It invents no new service, call direction, or
behavior beyond what ADR-0028's Decision/Consequences already state.

**Not in scope, per ADR-0028's own Context:** `captar_available` gates no entity at the registry
level — `MonthlyPeakSensor`/`EffectivePeakLimitSensor`/`PeakHeadroomSensor` are untouched by this
slice.

This slice sits inside `system-design.md`'s/`project-plan.md`'s existing task boundaries — it
does not reclassify either task. `SmartChargingDepartureTime` (and the five non-gated classes) is
part of **C2** ("Owned control entities", a Client, V14). `SolarSurplusSensor` is part of **C3**
("Diagnostic output entities" — `project-plan.md:372-375` classifies these as *owned entities
written through the Store, not Clients*, V13/V14, listed under Phase 4 for build-order reasons
only). No `project-plan.md` edit is scheduled by this slice; ADR-0028 doesn't ask for one.

---

## 1. Why this slice

| ADR-0028 Decision/Consequences item | This slice |
| --- | --- |
| Remove `SmartChargingEntity.async_added_to_hass`'s registry-write body | **In scope** — `entity.py` (§2), deferred to the last task (§2.3) so the suite stays green throughout (§7) |
| `sync_disabled_by` helper, pre-add, keyed on `unique_id` | **In scope** — `entity.py` (§2.1) |
| `sync_labels` helper, post-add, keyed on `unique_id` | **In scope** — `entity.py` (§2.2) |
| `SolarSurplusSensor` gains `_attr_entity_registry_enabled_default` + `sync_disabled_by` on `solar_available` | **In scope** — `sensor.py` (§3.1) |
| `SmartChargingDepartureTime` gains `_attr_entity_registry_enabled_default` + `sync_disabled_by` on `deadline_available`, alongside its existing (unchanged) `_owned_labels` conditional | **In scope** — `time.py` (§3.2) |
| `HomeDaySwitch`/`TargetCurrentNumber`/`SocLimitOverrideNumber`/`ModeSelect`/`ProfileSelect` move their label-sync call site only | **In scope** — `switch.py`/`number.py`/`select.py` (§3.3) |
| `MonthlyPeakSensor`/`EffectivePeakLimitSensor`/`PeakHeadroomSensor` | **Out of scope** — ADR-0028 Context explicitly excludes `captar_available` from entity-level gating |
| Any change to `ModeSelect`'s option-list gating (`select.py`'s inline `BASE_/SOLAR_/CAPTAR_CAPABLE_MODES` construction) or `engines/capability_gate.py` | **Out of scope** — a separate, pre-existing mechanism (which modes are *selectable*), untouched by ADR-0028 |
| The runtime dashboard's static "Power flow" tile for `sensor.smart_charging_solar_surplus_w` | **Out of scope, deferral recorded** — see §4; not label-driven, so ADR-0022's label mechanism doesn't cover it, and ADR-0028 doesn't ask for a dashboard change |

---

## 2. `entity.py`

### 2.1 `sync_disabled_by` (pre-add)

```python
def sync_disabled_by(
    registry: er.EntityRegistry, domain: str, unique_id: str, *, capability_met: bool
) -> None:
    """Pre-add registry sync (ADR-0028): flips disabled_by between None and
    RegistryEntryDisabler.INTEGRATION as capability_met changes, for an entity that already has
    a registry row. No-ops if the entity isn't registered yet (a brand-new entity's initial
    disabled state is set by _attr_entity_registry_enabled_default at add time instead -- there
    is no row for this call to act on before that) or if the row is somehow missing despite a
    matching entity_id (same defensive guard entity.py's removed hook kept). Never touches any
    other existing disabled_by value (notably USER) in either direction."""
    entity_id = registry.async_get_entity_id(domain, DOMAIN, unique_id)
    if entity_id is None:
        return
    existing = registry.async_get(entity_id)
    if existing is None:
        return
    if not capability_met and existing.disabled_by is None:
        registry.async_update_entity(entity_id, disabled_by=RegistryEntryDisabler.INTEGRATION)
    elif capability_met and existing.disabled_by is RegistryEntryDisabler.INTEGRATION:
        registry.async_update_entity(entity_id, disabled_by=None)
```

`domain` is the entity's platform domain (`"sensor"`, `"time"`, ...) — the same first positional
argument `registry.async_get_entity_id(domain, platform, unique_id)` itself takes, where
`platform` there means the *integration* domain (`DOMAIN`, i.e. `"smart_charging"`). Named
`domain` here, not `platform`, to avoid exactly that ambiguity.

Called from a platform's `async_setup_entry`, once per capability-gated entity, **before**
`async_add_entities` (ADR-0028's ordering rationale: avoid the transient churn of adding an
entity live only to remove it again in the same setup pass).

### 2.2 `sync_labels` (post-add)

```python
def sync_labels(
    registry: er.EntityRegistry,
    domain: str,
    unique_id: str,
    *,
    owned_labels: frozenset[str],
    manageable_labels: frozenset[str] = frozenset(),
) -> None:
    """Post-add registry sync (ADR-0028): replaces the removed async_added_to_hass-based label
    sync with the identical merge semantics. Keyed on unique_id (via the same
    registry.async_get_entity_id lookup as sync_disabled_by), NOT the entity instance's own
    entity_id attribute -- a registry-disabled entity never gets added to hass, so its instance
    may have no reliable entity_id to read; the registry lookup works regardless of whether the
    entity was added live this reload (ADR-0028's Decision requires the label to stay correct
    even for a capability-absent entity a user forced back on with disabled_by=USER)."""
    manageable = manageable_labels or owned_labels
    if not manageable:
        return
    entity_id = registry.async_get_entity_id(domain, DOMAIN, unique_id)
    if entity_id is None:
        return
    existing = registry.async_get(entity_id)
    if existing is None:
        return
    registry.async_update_entity(entity_id, labels=(existing.labels - manageable) | owned_labels)
```

Called from every platform's `async_setup_entry`, once per `_owned_labels`-carrying entity,
**after** `async_add_entities` — entity_id resolution no longer depends on the add having
succeeded, so the call is safe to make unconditionally, whether or not the entity ended up added
to hass this reload.

`SolarSurplusSensor` carries no `_owned_labels`, so it gets **no** `sync_labels` call at all —
not a call that happens to no-op. ADR-0028's Consequences say to apply the mechanism "uniformly
to every `_owned_labels`-carrying class"; `SolarSurplusSensor` isn't one, so it's simply excluded,
not exercised as a no-op case.

### 2.3 Retire `SmartChargingEntity.async_added_to_hass`

Once every `_owned_labels`-carrying class's `async_setup_entry` calls `sync_labels` (i.e. after
§3.2 and §3.3 both land), delete `entity.py:49-74`'s `async_added_to_hass` method **entirely** —
not a pass-through stub. Once its registry-write body is gone, all that would remain is
`await super().async_added_to_hass()`, which is exactly what *not* overriding the method already
does; a subclass calling `super().async_added_to_hass()` (e.g. `RestoreEntity`-mixing classes)
resolves correctly to the next class in the MRO with no override present at all. Deleting the
whole method, not just its body, is deliberate: keeping a pointless pass-through would suggest a
future reader look there for behavior that no longer exists.

This is sequenced last (§7) specifically so no window exists where the suite is red between "the
old mechanism is gone" and "the new call sites all exist."

---

## 3. Platform files

### 3.1 `sensor.py` — `SolarSurplusSensor`

- Constructor gains `solar_available: bool = False` (mirrors `ModeSelect`'s existing
  `solar_available: bool = False`/`captar_available: bool = False` params, `select.py:61-62`),
  setting `self._attr_entity_registry_enabled_default = solar_available`.
- `async_setup_entry` resolves the flag the same way `select.py:95`/`time.py:110` already do —
  `entry.data.get(CONF_SOLAR_AVAILABLE, DEFAULT_SOLAR_AVAILABLE)` — **not** by reaching into
  `entry.runtime_data.coordinator`'s private `_config` attribute; no platform file reads that
  today, and it would be a new, private Client→Manager access path this slice has no license to
  introduce.
- Calls `sync_disabled_by(registry, Platform.SENSOR, unique_id, capability_met=solar_available)`
  **before** `async_add_entities`. No `sync_labels` call for this sensor (§2.2).
- Existing `SolarSurplusSensor(...)` construction call sites in `tests/test_sensor.py` (direct,
  parametrized-loop, and full-setup constructions) must each pass an explicit
  `solar_available=True` unless the specific test is deliberately exercising the disabled case —
  the `= False` default matches `ModeSelect`'s convention but would otherwise silently flip every
  untouched existing test's sensor to disabled. This is a required edit in Task 1.1, not an
  incidental one.
- `MonthlyPeakSensor`, `EffectivePeakLimitSensor`, `PeakHeadroomSensor`: no change.

### 3.2 `time.py` — `SmartChargingDepartureTime`

- Constructor already takes `deadline_available` (existing `_owned_labels` conditional,
  `time.py:85-91`) — add `self._attr_entity_registry_enabled_default = deadline_available`
  alongside the existing `self._owned_labels = ...` line.
- `async_setup_entry` (already resolves `deadline_available` at `time.py:110`) calls
  `sync_disabled_by(registry, Platform.TIME, unique_id, capability_met=deadline_available)` per
  entity before `async_add_entities`, then `sync_labels(registry, Platform.TIME, unique_id,
  owned_labels=entity._owned_labels)` per entity after — using each instance's own (per-instance,
  capability-conditional) `_owned_labels`, unchanged from today's values. `_manageable_labels`
  stays the class-level constant, read the same way it is today.

### 3.3 `switch.py`, `number.py`, `select.py` — call-site move only

`HomeDaySwitch` (`switch.py`), `TargetCurrentNumber`/`SocLimitOverrideNumber` (`number.py`),
`ModeSelect`/`ProfileSelect` (`select.py`): each file's `async_setup_entry` calls `sync_labels`
for each of its entities, after `async_add_entities` — replacing what the (still-present, until
§2.3) `async_added_to_hass` hook does for them. Both the hook and the new call fire during this
phase — redundant but idempotent, not conflicting, since both write the identical, already-merged
label set. No `_attr_entity_registry_enabled_default` is added to any of these five; they are not
capability-gated, only their sync mechanism moves.

---

## 4. Deliberate deferrals

- **`captar_available`-gated sensors**: excluded entirely, per ADR-0028's Context — not a
  narrower version of the mechanism, a deliberate non-application of it.
- **A future notifications-capability-gated entity**: none exists yet; when one is added, it
  should reuse `sync_disabled_by`/`sync_labels` rather than a new mechanism (ADR-0028
  Consequences) — no code changes here in anticipation of that.
- **The generated runtime dashboard's static "Power flow" tile.** `dashboard.py` places a fixed
  tile for `sensor.smart_charging_solar_surplus_w` in the unconditional Power-flow grid — not the
  label-driven `auto-entities` section ADR-0022 governs. Once `SolarSurplusSensor` can be
  registry-disabled, a no-solar install's dashboard will show that tile as unavailable. ADR-0028
  doesn't ask this slice to fix the dashboard, and doing so is a separate, C5-scoped change — this
  is recorded here as a known, deferred consequence, not fixed by this slice. Worth a follow-up
  issue against `dashboard.py`/C5 rather than silent acceptance.

---

## 5. Testing approach (ADR-0009)

All HA harness — every unit here touches the entity registry, `async_setup_entry`, or restore
state, none of it HA-free pure logic. No plain-pytest tests are added by this slice.

| Case | Entities exercised |
| --- | --- |
| First install, capability off → `disabled_by == INTEGRATION` immediately | `SolarSurplusSensor`, `SmartChargingDepartureTime` |
| Reload, capability off→on → `disabled_by` clears to `None` | both |
| Reload, capability on→off → `disabled_by` becomes `INTEGRATION`, entity not live same reload | both |
| `disabled_by == USER` untouched in either direction | both |
| Idempotency across repeated reloads, capability unchanged | both |
| Label **and** `disabled_by` both correct while disabled | `SmartChargingDepartureTime` only (the one entity with both mechanisms) |
| Regression: label still applied after the call-site move | `HomeDaySwitch`, `TargetCurrentNumber`, `SocLimitOverrideNumber`, `ModeSelect`, `ProfileSelect` |
| Restored value **does** survive an off/on cycle (documents the actual, safe `RestoreEntity` behavior) | `SmartChargingDepartureTime` |

`sync_disabled_by`/`sync_labels` themselves get direct unit-level HA-harness tests
(`tests/test_entity_labels.py`) exercising the registry functions in isolation, independent of any
real platform's `async_setup_entry` — see the TDD plan's Phase 0.

---

## 6. Packaging / integration checkpoint

No new file. No config-entry schema change (`solar_available`/`deadline_available` already
exist). ⎔ integration checkpoint: a full `async_setup_entry` → `async_unload_entry` →
`async_setup_entry` cycle (an options-flow reload, ADR-0008), asserted in `tests/test_init.py`,
leaves the registry in the correct `disabled_by`/label state for every affected entity, matching
the table in §5.

---

## 7. Build-order note: keeping the suite green

`entity.py`'s hook-based label sync and the new setup-time mechanism can coexist safely for the
duration of this slice's build-out (§3.3's redundant-but-idempotent double-write). The TDD plan
exploits that: `sync_disabled_by`/`sync_labels` are added and unit-tested first (Phase 0), then
wired into each platform one at a time (Phases 1–3), and only once every `_owned_labels` class has
its new call site does the old hook get deleted (§2.3, the final task) — at no point does the
suite go red waiting for a call site that doesn't exist yet.
