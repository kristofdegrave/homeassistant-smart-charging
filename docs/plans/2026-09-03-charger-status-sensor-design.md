# Design: dedicated `charger_status` diagnostic sensor (#917)

## Scope

Implement ADR-0034's decision: one new owned diagnostic sensor,
`sensor.smart_charging_charger_status`, carrying the canonical translated charger state
(`disconnected`/`connected`/`charging`) that `adapters/status.py` already produces each control
cycle. Rebind the runtime dashboard's charging-status tile to it, replacing the raw
`entry.data[CONF_CHARGER_STATUS_ENTITY]` binding. Update `entity-catalog.md`'s `Read by` columns
to reflect the resulting hand-over, per the Notes bullet already written in that catalog (#915).

Source of truth: [ADR-0034](../adl/0034-dedicated-charger-status-diagnostic-sensor.md) (the
decision) and [`entity-catalog.md`](../analysis/entity-catalog.md)'s
`sensor.smart_charging_charger_status` row (#915, merged) — this design derives concrete
files/tests from both, it does not re-decide anything either one already settled.

## Success criteria

- `sensor.smart_charging_charger_status` exists, is diagnostic, disabled-by-default is **not**
  applied (it is always relevant, unlike the ADR-0031 config mirrors — ADR-0034 does not ask for
  registry-gating), and its `object_id` is pinned to `charger_status` per ADR-0013.
- Its state equals the same per-cycle value `adapter_readings`'s `charger_status` attribute
  already carries, with no new adapter read.
- A `None` reading (unmapped/unavailable raw state) presents as HA's `unknown` state; the entity
  itself stays available (never HA-`unavailable`), matching UC11's requirement that the rest of
  the dashboard keeps rendering through a fault.
- The runtime dashboard's "Charging status" section's first tile binds to the new sensor instead
  of the raw mapped entity.
- Nothing here changes `adapter_readings`'s own `charger_status` attribute — the duplication
  ADR-0034 accepts stays intact.

## Naming — avoiding the three-way collision ADR-0034 flagged

Three names must stay visually distinct in code and UI, per ADR-0034's Consequences:

| Thing | Symbol | Meaning |
| --- | --- | --- |
| `charger_status` **adapter role** | `ROLE_CHARGER_STATUS` (`const.py`) | the raw-to-canonical mapping input — not an entity |
| `sensor.smart_charging_status` | `ChargingStatusSensor`, `_object_id_suffix = "status"` (`sensor.py:96,100`) | ADR-0007's integration health (`OK`/`Fault`) — unrelated |
| `sensor.smart_charging_charger_status` (new) | `ChargerStatusSensor`, `_object_id_suffix = OWNED_SUFFIX_CHARGER_STATUS = "charger_status"` | this design's sensor |

`dashboard.py`'s existing `_charging_status_cards` function name (the dashboard *section*) is
left untouched — it already means the section, not this value, and ADR-0034 only asks that the
new class/translation avoid reusing it, not that it be renamed.

## Control flow

No new read and no new cache entry. `coordinator.py`'s `_read_cycle_inputs` already assigns
`self._role_readings[ROLE_CHARGER_STATUS]` on every cycle that reaches the required-role read
block (`coordinator.py:276-281`), including a `None` assignment when the raw state is unmapped or
the raw entity is unavailable (ADR-0007 semantics) — and holds the prior cycle's value, same as
`adapter_readings`, on the narrow window where an earlier required read in that same block raises
outright (ADR-0034's Consequences already work this out; this design does not revisit it).
`CycleResult.adapter_readings` (a `dict[str, Any]`, `coordinator.py:99`) is the single place this
value reaches `sensor.py` — there is no separate `CycleResult.charger_status` field, and this
design does not add one: adding a field would create a second writer for the same cached value,
exactly the divergence risk ADR-0034's Consequences reject. The new sensor's `native_value` reads
`data.adapter_readings.get(ROLE_CHARGER_STATUS)` — a plain dict lookup, `None` both when the key
is genuinely absent (no cycle yet) and when the role's own reading is `None`, which is exactly the
"unknown" outcome this design wants for both cases.

`CoordinatorEntity.available` already returns `self.coordinator.last_update_success`, and
`_async_update_data` (`coordinator.py:224-236`) catches every exception and returns a faulted
`CycleResult` rather than raising `UpdateFailed` — so `last_update_success` is always `True` once
the first cycle completes, and the new sensor's `available` needs no override to satisfy "must not
become unavailable."

## Sensor shape (`sensor.py`)

Follows `_CoordinatorFieldSensor` (`sensor.py:73-93`), the base every other single-field
diagnostic readout (`ActiveModeSensor`, `EffectivePeakLimitSensor`, …) already uses — not
`AdapterReadingsSensor`'s own base, since this sensor has no `extra_state_attributes`:

```python
class ChargerStatusSensor(_CoordinatorFieldSensor):
    """Diagnostic: the canonical translated charger state from the same per-cycle reading
    adapter_readings' charger_status attribute carries (ADR-0034)."""

    _attr_translation_key = "charger_status"
    _object_id_suffix = OWNED_SUFFIX_CHARGER_STATUS
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def _coordinator_value(self, data: Any) -> Any:
        return data.adapter_readings.get(ROLE_CHARGER_STATUS)
```

`_field_default` is left at `_CoordinatorFieldSensor`'s own default (`None`), matching "no cycle
yet -> unknown."

**`device_class` — decided: none.** `SensorDeviceClass.ENUM` requires a fixed `options` list and
constrains `native_value` to exactly those options or `None`; ADR-0034 flags it as "the natural
fit" but explicitly leaves the call to this spec. This design does **not** adopt it: the sibling
`ChargingStatusSensor` (also a small fixed-vocabulary string state, `Fault`/`OK`) carries no
device class either, and `AdapterReadingsSensor`'s own `charger_status` attribute — the value this
sensor must never disagree with — is a bare string with no `ENUM` typing of its own. Adding
`ENUM` only to this one surface would let the two surfaces diverge in *type* (one constrained,
one not) while ADR-0034 requires them to never diverge in *value*; omitting it keeps both
surfaces the same plain string (or `None`), consistent with every other same-shape owned sensor
in this file. This does mean the tile shows the raw lowercase tokens
(`disconnected`/`connected`/`charging`) untranslated in both locales, same as `ChargingStatusSensor`'s
own `Fault`/`OK` states today — `_attr_translation_key` (per this file's existing pattern) only
translates the entity's *name*, not its state values, and this design adds no
`entity.sensor.charger_status.state.*` translation block, so no new state-translation
capability is claimed here. That gap (no owned sensor in this file translates its state values
today) is accepted as a pre-existing cost this design does not take on fixing, not a benefit
`ENUM` would have specifically added.

`const.py` gains one constant alongside the other `OWNED_SUFFIX_*` names
(`const.py:91-105`):

```python
OWNED_SUFFIX_CHARGER_STATUS = "charger_status"
```

`async_setup_entry` (`sensor.py:500-513`) adds one line to the `async_add_entities` list, next to
`ChargingStatusSensor`'s own (grouping the two intentionally, so a future reader sees them
side by side and notices the naming distinction rather than one being easy to miss):

```python
ChargingStatusSensor(entry.entry_id, coordinator),
ChargerStatusSensor(entry.entry_id, coordinator),
```

`strings.json` / `translations/en.json` / `translations/nl.json` each gain one
`entity.sensor.charger_status.name` entry ("Charger status" / Dutch equivalent), distinct from
the existing `status` entry ("Status").

## Dashboard rebind (`dashboard.py`)

`_charging_status_cards` (`dashboard.py:69-81`) currently does:

```python
cards = [_tile(entry.data[CONF_CHARGER_STATUS_ENTITY])]
```

Changes to a module-level constant + reference, matching the existing
`_ACTIVE_MODE_ENTITY`/`_PROFILE_ENTITY`/etc. pattern (`dashboard.py:53-62`) rather than a bare
literal:

```python
_CHARGER_STATUS_ENTITY = f"sensor.smart_charging_{OWNED_SUFFIX_CHARGER_STATUS}"
...
cards = [_tile(_CHARGER_STATUS_ENTITY)]
```

`CONF_CHARGER_STATUS_ENTITY` drops out of `dashboard.py`'s imports once this is the only use in
that module (checked: it is). The raw entity remains the adapter role's mapping target either
way — only the tile's binding changes, exactly as ADR-0034's Consequences describe.

## `entity-catalog.md` follow-up

Per the Notes bullet #915 already added, once this rebind lands, four spots in
`entity-catalog.md` move from "expected" to "settled" — this is not only the table's two cells:

- The `charger_status` **adapter role** row (`entity-catalog.md:143`)'s `Read by` column drops
  its current `UC11` reference (the dashboard no longer reads that role's raw entity directly).
- `sensor.smart_charging_charger_status`'s own row's `Read by` column changes from the `(UC11)`
  placeholder to a current `UC11` reference (the dashboard now reads this sensor directly).
- The `adapter_readings` Notes bullet's own prose (`entity-catalog.md:391-392`), which currently
  lists "a current `UC11` reference on `charger_power`/`charger_status`/`charger_current`/
  `net_power`" — `charger_status` must be removed from that list; it is no longer read directly
  by the dashboard.
- The `sensor.smart_charging_charger_status` Notes bullet's own hand-over paragraph
  (`entity-catalog.md:410-415`), which describes the swap as a future expectation ("only
  because the shipped dashboard tile still binds..."); once this task lands, that paragraph
  describes the past, not the future, and must be rewritten to settled tense (or removed if it
  no longer adds information beyond the two table cells above).

Folded into T2 below rather than a separate task, since it is mechanically tied to the same
code change — but it is a four-spot edit, not a two-cell one.

## Mapping to `system-design.md` services

Sits under `project-plan.md`'s **C3 — Diagnostic output entities** slice (same as every existing
`_CoordinatorFieldSensor`): "owned entities the Coordinator writes... listed under Phase 4 for
build-order reasons only" (`project-plan.md:371-375`), no new `ADR gate` beyond ADR-0034 itself.
The dashboard rebind is **C5 — Runtime dashboard (UC11)**, which already "depends on... C3
(diagnostics)" (`project-plan.md:396-400`) — this is exactly that dependency being exercised, not
a new one. Neither slice's service definition changes; this is new content inside each, matching
the ADR-0021/ADR-0031 precedent the config-mirror-sensors design doc already established for this
kind of small ADR-driven addition to C3/C5.

## Testing approach (ADR-0009)

HA harness throughout (`sensor.py`/`dashboard.py` are entity/adapter-coupled, per ADR-0009's
split) — no plain-pytest task, matching the low_tariff and config-mirror specs' precedent for a
slice this size:

- `tests/test_sensor.py`: new sensor's `native_value` reflects `data.adapter_readings`, defaults
  to `None` with no coordinator data yet, unique id is `<entry_id>_charger_status`, entity
  category is diagnostic — same four-test shape `AdapterReadingsSensor`'s own tests already use
  (`tests/test_sensor.py:391-420`), minus the attributes assertion this sensor doesn't have.
- `test_all_sensor_object_id_suffixes_are_unique` (`tests/test_sensor.py:423-440`) — existing
  ADR-0013 collision guard, but its `sensor_classes` list is **hardcoded**, not introspective:
  `ChargerStatusSensor` must be added to it explicitly, or the guard silently excludes the new
  class.
- `test_every_owned_entity_id_matches_entity_catalog` (`tests/test_init.py`) — the real
  full-registration guard for this change: its `expected` dict is an exhaustive owned-entity
  set enforced by a final `assert registered == expected_by_domain`, so the new sensor's
  `entity_id` must be added there too, or a full `async_setup_entry` fails that assertion.
- `tests/test_dashboard.py`: `test_charging_status_section_has_the_seven_documented_tiles`
  (`tests/test_dashboard.py:92-105`) — the entity in position 0 changes from the raw mapped
  entity (`"sensor.evse"`) to `"sensor.smart_charging_charger_status"`.
- `tests/test_translations.py` — the en/nl parity tests cover the new key automatically, but
  `test_every_entity_translation_key_has_a_name`'s `sensor_keys` tuple
  (`tests/test_translations.py:73-118`) is hardcoded too: `"charger_status"` must be added to it.

**Integration checkpoint:** a full `async_setup_entry` run producing both the new sensor entity
and a dashboard config whose "Charging status" section's first tile is that sensor's entity id —
`test_every_owned_entity_id_matches_entity_catalog`'s addition above already exercises the full
setup half; `test_dashboard.py`'s case above exercises the tile-binding half. No new
cross-cutting test needed for a change this narrow.

## Packaging

`strings.json`, `translations/en.json`, `translations/nl.json` — one new
`entity.sensor.charger_status` block each, per the Sensor shape section above.

## Deferrals

- The `enum` device class — considered and explicitly declined above, not deferred; a future
  spec could revisit if translated per-state display via `device_class` becomes worth the
  divergence-in-type risk.
- Any change to `adapter_readings`'s own attribute — ADR-0034 keeps the duplication; out of
  scope here as it is for the ADR.
- Registry-gating this sensor by capability (ADR-0028's pattern) — not asked for by ADR-0034;
  `charger_status` is a required role (always mapped), unlike `solar_available`-gated
  `SolarSurplusSensor`, so there is no capability to gate on.
