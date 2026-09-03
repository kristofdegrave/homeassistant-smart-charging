# TDD plan: dedicated `charger_status` diagnostic sensor (#917)

Derived from `docs/plans/2026-09-03-charger-status-sensor-design.md`. Branch: `development/<issue>`
per task, filed once this plan lands. Both tasks are HA harness (ADR-0009) — `sensor.py` and
`dashboard.py` are entity/config-entry-coupled, matching the low_tariff and config-mirror specs'
own precedent for a slice this size.

## T1 — `ChargerStatusSensor` (`sensor.py`, `const.py`, translations)

- Failing test (`tests/test_sensor.py`, alongside the existing `AdapterReadingsSensor` tests at
  `tests/test_sensor.py:391-420`, same four-test shape minus the attributes case):
  - `native_value` reflects `coordinator.data.adapter_readings[ROLE_CHARGER_STATUS]` for each of
    `STATE_DISCONNECTED`/`STATE_CONNECTED`/`STATE_CHARGING` (`const.py:47-49` — not re-typed as
    magic strings) and for `None` (unmapped/unavailable raw state) — parametrize over the four
    cases against a `SimpleNamespace(data=SimpleNamespace(adapter_readings=...))` stub, matching
    `AdapterReadingsSensor`'s own stubbing style.
  - `native_value is None` when `coordinator.data is None` (no cycle yet).
  - `unique_id == "abc_charger_status"`.
  - `entity_category == EntityCategory.DIAGNOSTIC`.
  - `device_class == SensorDeviceClass.ENUM` and
    `options == [STATE_DISCONNECTED, STATE_CONNECTED, STATE_CHARGING]`.
- Add `OWNED_SUFFIX_CHARGER_STATUS = "charger_status"` to `const.py`, alongside the other
  `OWNED_SUFFIX_*` constants (`const.py:91-105`).
- Add `ChargerStatusSensor(_CoordinatorFieldSensor)` to `sensor.py` per the design doc's Sensor
  shape section: `_attr_translation_key = "charger_status"`,
  `_object_id_suffix = OWNED_SUFFIX_CHARGER_STATUS`,
  `_attr_entity_category = EntityCategory.DIAGNOSTIC`,
  `_attr_device_class = SensorDeviceClass.ENUM`,
  `_attr_options = [STATE_DISCONNECTED, STATE_CONNECTED, STATE_CHARGING]`, `_coordinator_value`
  returns `data.adapter_readings.get(ROLE_CHARGER_STATUS)`. Import `ROLE_CHARGER_STATUS` from
  `const.py` (already used elsewhere in the package; new import into `sensor.py` only) —
  `SensorDeviceClass` and `STATE_DISCONNECTED`/`STATE_CONNECTED`/`STATE_CHARGING` are already
  imported into `sensor.py`/`const.py` respectively.
- Register it in `async_setup_entry`'s `async_add_entities` list, directly after
  `ChargingStatusSensor(entry.entry_id, coordinator)` (`sensor.py:502`) — the design doc's
  deliberate side-by-side grouping.
- Add one `entity.sensor.charger_status` block to `strings.json` and to
  `translations/en.json`/`translations/nl.json`, alongside the existing `status` block
  (`strings.json:358-360`) — a `name` ("Charger status", distinct name/key from `status`) plus a
  `state` block translating all three of `disconnected`/`connected`/`charging` (English names in
  strings.json/en.json; Dutch in nl.json, reusing this project's existing "verbonden"/"aan het
  laden" wording from the config-flow field descriptions, plus "niet verbonden" for
  disconnected).
- Failing test (`tests/test_sensor.py:429-440`): add `ChargerStatusSensor` to
  `test_all_sensor_object_id_suffixes_are_unique`'s hardcoded `sensor_classes` list — this is
  the ADR-0013 collision guard the design doc's Testing approach cites, and it is a hardcoded
  list, not an introspective one, so the new class must be added explicitly or the guard silently
  excludes it.
- Failing test (`tests/test_init.py`): add `"charger_status": "sensor.smart_charging_charger_status"`
  to `test_every_owned_entity_id_matches_entity_catalog`'s `expected` dict (the owned-entity
  completeness set that test's final `assert registered == expected_by_domain` enforces
  exhaustively) and bump its "all 58 owned entities" comment to 59. This is the real, designated
  ADR-0013 full-registration guard for this change — not the dashboard checkpoint.
- Green: `tests/test_translations.py` (existing sweep covering `strings.json`/en.json/nl.json
  parity) passes with no changes of its own; `test_every_entity_translation_key_has_a_name`
  (`tests/test_translations.py:73-118`) does **not** auto-cover the new key (its `sensor_keys`
  tuple is hardcoded) — add `"charger_status"` to that tuple too, in the same commit.
- Commit: `feat: add sensor.smart_charging_charger_status diagnostic sensor (ADR-0034, #917)`.

## T2 — Rebind the dashboard tile + `entity-catalog.md` hand-over

- Failing test (`tests/test_dashboard.py`): amend
  `test_charging_status_section_has_the_seven_documented_tiles`
  (`tests/test_dashboard.py:92-105`) — position 0's expected entity changes from `"sensor.evse"`
  (the raw mapped entity, `CONF_CHARGER_STATUS_ENTITY`) to
  `"sensor.smart_charging_charger_status"`. `test_charging_status_section_omits_the_battery_tile_when_ev_soc_is_unset`
  (`tests/test_dashboard.py:108-114`) needs no change — it only asserts count and non-`None`
  entities, not which entity is first.
- In `dashboard.py`: add `_CHARGER_STATUS_ENTITY = f"sensor.smart_charging_{OWNED_SUFFIX_CHARGER_STATUS}"`
  alongside the other `_<NAME>_ENTITY` module constants (`dashboard.py:53-62`); import
  `OWNED_SUFFIX_CHARGER_STATUS` from `const.py`. Change `_charging_status_cards`
  (`dashboard.py:69-70`) from `_tile(entry.data[CONF_CHARGER_STATUS_ENTITY])` to
  `_tile(_CHARGER_STATUS_ENTITY)`. Drop the now-unused `CONF_CHARGER_STATUS_ENTITY` import from
  `dashboard.py` (confirm no other use in that module before removing).
- In `docs/analysis/entity-catalog.md`, four spots (not just the two table cells — see the
  design doc's `entity-catalog.md` follow-up section for why):
  1. `charger_status` **adapter role** row (`entity-catalog.md:143`): drop the row's current
     `UC11` reference from its `Read by` column (the dashboard no longer reads that role's raw
     entity directly — the mapping still exists, only nothing displays it directly any more).
  2. `sensor.smart_charging_charger_status` row (`entity-catalog.md:188`): change `Read by` from
     the `(UC11)` placeholder to a current `UC11` reference (the dashboard now reads this sensor
     directly).
  3. The `adapter_readings` Notes bullet (`entity-catalog.md:391-392`): remove `charger_status`
     from the list of roles carrying "a current `UC11` reference."
  4. The `sensor.smart_charging_charger_status` Notes bullet's hand-over paragraph
     (`entity-catalog.md:410-415`): rewrite from future/expected tense ("once this rebind lands,
     the role's reference should drop...") to settled tense describing what this task just did,
     or remove the paragraph if the two table cells above already say everything it added.
- Green, commit: `feat: rebind the dashboard's charger-status tile to the dedicated sensor (ADR-0034, #917)`.

## Integration checkpoint

Both tasks together close ADR-0034/R19 AC1: a fresh `async_setup_entry` registers
`sensor.smart_charging_charger_status` (T1), and `build_dashboard_config`'s "Charging status"
section's first tile is that same entity id (T2). T1's addition to
`test_every_owned_entity_id_matches_entity_catalog` (`tests/test_init.py`) is this slice's real
full-registration checkpoint — a full `async_setup_entry` asserting the new entity's exact
`entity_id`, as part of the exhaustive owned-entity set that test already enforces — so no
separate cross-cutting task is needed beyond T1's and T2's own tests.
