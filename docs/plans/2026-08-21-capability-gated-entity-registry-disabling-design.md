# Capability-gated entity registry disabling — design

**Date:** 2026-08-21
**Status:** draft (issue #786, ADR-0028)
**Type:** implementation design (a slice of an already-Accepted architectural decision — not a
new decision)

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

This is a Client-layer (V14) change, inside `system-design.md`'s existing C2 ("Owned control
entities") and C3 ("Diagnostic output entities") task boundaries — it does not reclassify either
task or introduce a new one. ADR-0028 is the new ADR gate for both, superseding their prior "none"
gate in `project-plan.md`.

---

## 1. Why this slice

| ADR-0028 Decision/Consequences item | This slice |
| --- | --- |
| Remove `SmartChargingEntity.async_added_to_hass`'s registry-write body | **In scope** — `entity.py` (§2) |
| `sync_disabled_by` helper, pre-add, keyed on `unique_id` | **In scope** — `entity.py` (§2.1) |
| `sync_labels` helper, post-add, keyed on `entity_id` | **In scope** — `entity.py` (§2.2) |
| `SolarSurplusSensor` gains `_attr_entity_registry_enabled_default` + `sync_disabled_by` on `solar_available` | **In scope** — `sensor.py` (§3.1) |
| `SmartChargingDepartureTime` gains `_attr_entity_registry_enabled_default` + `sync_disabled_by` on `deadline_available`, alongside its existing (unchanged) `_owned_labels` conditional | **In scope** — `time.py` (§3.2) |
| `HomeDaySwitch`/`TargetCurrentNumber`/`SocLimitOverrideNumber`/`ModeSelect`/`ProfileSelect` move their label-sync call site only | **In scope** — `switch.py`/`number.py`/`select.py` (§3.3) |
| `MonthlyPeakSensor`/`EffectivePeakLimitSensor`/`PeakHeadroomSensor` | **Out of scope** — ADR-0028 Context explicitly excludes `captar_available` from entity-level gating |
| Any change to `ModeSelect`'s option-list gating (`select.py`'s inline `BASE_/SOLAR_/CAPTAR_CAPABLE_MODES` construction) or `engines/capability_gate.py` | **Out of scope** — a separate, pre-existing mechanism (which modes are *selectable*), untouched by ADR-0028 |
| A reseed/migration mechanism for `SmartChargingDepartureTime`'s restore-state gap | **Out of scope, by design** — ADR-0028 accepts this as a documented cost, not something to engineer around (§4) |

---

## 2. `entity.py`

### 2.1 `sync_disabled_by` (pre-add)

```python
def sync_disabled_by(
    registry: er.EntityRegistry, platform: str, unique_id: str, *, capability_met: bool
) -> None:
    """Pre-add registry sync (ADR-0028): flips disabled_by between None and
    RegistryEntryDisabler.INTEGRATION as capability_met changes, for an entity that already has
    a registry row. No-ops if the entity isn't registered yet (a brand-new entity's initial
    disabled state is set by _attr_entity_registry_enabled_default at add time instead -- there
    is no row for this call to act on before that). Never touches any other existing disabled_by
    value (notably USER) in either direction."""
    entity_id = registry.async_get_entity_id(platform, DOMAIN, unique_id)
    if entity_id is None:
        return
    existing = registry.async_get(entity_id)
    if not capability_met and existing.disabled_by is None:
        registry.async_update_entity(entity_id, disabled_by=RegistryEntryDisabler.INTEGRATION)
    elif capability_met and existing.disabled_by is RegistryEntryDisabler.INTEGRATION:
        registry.async_update_entity(entity_id, disabled_by=None)
```

Called from a platform's `async_setup_entry`, once per capability-gated entity, **before**
`async_add_entities` (ADR-0028's ordering rationale: avoid the transient churn of adding an
entity live only to remove it again in the same setup pass).

### 2.2 `sync_labels` (post-add)

```python
def sync_labels(
    registry: er.EntityRegistry,
    entity_id: str,
    *,
    owned_labels: frozenset[str],
    manageable_labels: frozenset[str],
) -> None:
    """Post-add registry sync (ADR-0028): replaces the removed async_added_to_hass-based label
    sync with the identical merge semantics, called once entity_id is guaranteed to exist (a
    label write needs a registry row, which a brand-new entity doesn't have until
    async_add_entities creates it)."""
    manageable = manageable_labels or owned_labels
    if not manageable:
        return
    existing = registry.async_get(entity_id)
    registry.async_update_entity(entity_id, labels=(existing.labels - manageable) | owned_labels)
```

Called from every platform's `async_setup_entry`, once per `_owned_labels`-carrying entity,
**after** `async_add_entities`.

### 2.3 `SmartChargingEntity.async_added_to_hass`

Delete the registry-write body (current `entity.py:49-74`) entirely. The method still exists for
subclasses that call `super().async_added_to_hass()` as part of the `RestoreEntity`/
`CoordinatorEntity` MRO chain (ADR-0002's base-class-first delegation) — it becomes a pure
pass-through to `super()`, with no registry side effect of its own.

---

## 3. Platform files

### 3.1 `sensor.py` — `SolarSurplusSensor`

- Constructor gains `solar_available: bool` (mirrors `ModeSelect`'s existing
  `solar_available`/`captar_available` params in `select.py`), setting
  `self._attr_entity_registry_enabled_default = solar_available`.
- `async_setup_entry` reads `entry.runtime_data.coordinator._config.solar_available` (the same
  resolved `SmartChargingConfig` field every other capability-aware `async_setup_entry` already
  reads — see `select.py:95`), calls `sync_disabled_by(registry, Platform.SENSOR, unique_id,
  capability_met=solar_available)` **before** `async_add_entities`, then `sync_labels(...)`
  **after** for every sensor in the platform (`SolarSurplusSensor` has no `_owned_labels`, so its
  own `sync_labels` call is a documented no-op — T3.1's test asserts this explicitly).
- `MonthlyPeakSensor`, `EffectivePeakLimitSensor`, `PeakHeadroomSensor`: no change.

### 3.2 `time.py` — `SmartChargingDepartureTime`

- Constructor already takes `deadline_available` (existing `_owned_labels` conditional,
  `time.py:85-91`) — add `self._attr_entity_registry_enabled_default = deadline_available`
  alongside the existing `self._owned_labels = ...` line.
- `async_setup_entry` (already resolves `deadline_available` at `time.py:110`) calls
  `sync_disabled_by(registry, Platform.TIME, unique_id, capability_met=deadline_available)` per
  entity before `async_add_entities`, then `sync_labels(...)` per entity after — the latter using
  each instance's own (per-instance, capability-conditional) `_owned_labels`/`_manageable_labels`,
  unchanged from today's values.

### 3.3 `switch.py`, `number.py`, `select.py` — call-site move only

`HomeDaySwitch` (`switch.py`), `TargetCurrentNumber`/`SocLimitOverrideNumber` (`number.py`),
`ModeSelect`/`ProfileSelect` (`select.py`): each file's `async_setup_entry` calls `sync_labels`
for each of its entities, after `async_add_entities` — replacing what the removed
`async_added_to_hass` hook did for them. No `_attr_entity_registry_enabled_default` is added to
any of these five; they are not capability-gated, only their sync mechanism moves.

---

## 4. Deliberate deferrals

- **`SmartChargingDepartureTime`'s restore-state gap** (ADR-0028 Context): a user's set departure
  time can revert to its R14 constructor default across a `deadline_available` off→on cycle,
  since the `RestoreEntity` read only runs while the entity is added to hass. This is an accepted
  cost per the ADR, not engineered around here — T4.4 asserts the documented behavior (revert to
  default) so it stays a decided outcome, not a silent, unasserted regression.
- **`captar_available`-gated sensors**: excluded entirely, per ADR-0028's Context — not a
  narrower version of the mechanism, a deliberate non-application of it.
- **A future `notification_available`-gated entity**: none exists yet; when one is added, it
  should reuse `sync_disabled_by`/`sync_labels` rather than a new mechanism (ADR-0028
  Consequences) — no code changes here in anticipation of that.

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
| `sync_labels` no-ops cleanly (no `_owned_labels`) | `SolarSurplusSensor` |
| Regression: label still applied after the call-site move | `HomeDaySwitch`, `TargetCurrentNumber`, `SocLimitOverrideNumber`, `ModeSelect`, `ProfileSelect` |
| Accepted-risk case: restored value does **not** survive an off/on cycle | `SmartChargingDepartureTime` |

---

## 6. Packaging / integration checkpoint

No new file. No config-entry schema change (`solar_available`/`deadline_available` already
exist). ⎔ integration checkpoint: a full `async_setup_entry` → `async_unload_entry` →
`async_setup_entry` cycle (an options-flow reload, ADR-0008) leaves the registry in the correct
`disabled_by`/label state for every affected entity, matching the table above.
