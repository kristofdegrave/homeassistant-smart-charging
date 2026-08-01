# Owned-entity object_ids — design

**Date:** 2026-07-27
**Status:** draft (issue #417)
**Type:** implementation design (a corrective slice realizing an accepted decision — not a new decision)

This document defines the **owned-entity object_id** build slice: pin an explicit,
locale-independent `object_id` on every owned entity across
`custom_components/smart_charging/{select,number,sensor,switch,time}.py`, so each entity
registers under the `entity_id` that [`entity-catalog.md`](../analysis/entity-catalog.md)
already documents, in every Home Assistant locale.

It carries out the implementation follow-up
[ADR-0013](../adl/0013-stable-owned-entity-object-ids.md) (Accepted) calls for in its Consequences.
Nothing here decides anything new: ADR-0013 already chose *Option A — pin an explicit,
locale-independent object_id for every owned entity* over correcting the docs; this slice
is the code and tests, exactly the scope [issue #417](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/417)
carves out. It introduces **no** new service, entity, adapter role, config key, or
structural boundary — it is a naming correction inside the existing owned-entity base
class and the five platform files ADR-0004 already owns.

---

## 1. Why this slice exists (the bug ADR-0013 named)

`entity.py`'s `SmartChargingEntity` base sets `_attr_has_entity_name = True` and provides a
`DeviceInfo(name="Smart Charging")`. Under `has_entity_name = True`, Home Assistant derives
a newly-registered owned entity's `object_id` (the part of the `entity_id` after the domain)
from the **device name + the entity's translated display name**, *not* from its
`_attr_translation_key`. The display name is the localized `entity.<platform>.<key>.name`
string in `strings.json`. So the generated `entity_id`:

- diverges from the catalog whenever the display-name slug differs from the catalog suffix, and
- is **not stable across locales** — a Dutch install and an English install register the
  same entity under different `entity_id`s, because the name string is translated but the
  catalog suffix is not.

Concretely, with the current `strings.json` names (English), the owned entities whose
generated `entity_id` **already diverges from the catalog today** are:

| Class | `strings.json` name | Generated id today | Catalog id (target) |
| --- | --- | --- | --- |
| `SocLimitOverrideNumber` | "Default charge limit" | `number.smart_charging_default_charge_limit` | `number.smart_charging_soc_limit_override` |
| `MonthlyPeakSensor` | "Monthly peak" | `sensor.smart_charging_monthly_peak` | `sensor.smart_charging_monthly_peak_kw` |
| `ActiveSocLimitSensor` | "Active charge limit" | `sensor.smart_charging_active_charge_limit` | `sensor.smart_charging_active_soc_limit` |
| `SmartChargingDepartureTime` ×9 | "Monday departure time" … "Home-day departure time" | `time.smart_charging_monday_departure_time` … `time.smart_charging_home_day_departure_time` | `time.smart_charging_departure_mon` … `time.smart_charging_departure_home_day` |

`tests/test_init.py:149` (`test_setup_falls_back_to_default_soc_limit_for_pre_solar_entries`) already asserts the wrong
`number.smart_charging_default_charge_limit`, documenting that the locale-derived id is what
ships today — this is a real bug against the catalog's contract, not a test artifact.

The remaining owned entities' display-name slugs *happen to coincide* with their catalog
suffix today (`mode`, `profile`, `status`, `active_mode`, `effective_peak_limit`,
`home_day`, and — with no catalog row — `target_current`). ADR-0013 is explicit that these
**still get an explicit pin**, so a future `strings.json` wording change (e.g. renaming
"Status" to "Charging status") cannot silently drift their `entity_id` the way it already has
for the four rows above.

---

## 2. Scope and non-goals

**In scope** — pin an explicit, locale-independent object_id on every owned entity in the
five platform files, via one shared mechanism in `entity.py` (§4), and update the tests that
assert an owned `entity_id` (§6). The owned population is ADR-0004's second population; mapped
hardware entities are referenced by the user's own `entity_id` and are untouched.

**Non-goals**, each stated out loud because a reader might expect them:

- **No further `entity-catalog.md`/`README.md` rewrite.** ADR-0013's Decision concluded none
  is needed — the existing documented ids become *correct* once this code lands. This slice
  does not touch either document.
- **No `strings.json` rename.** Pinning the object_id deliberately decouples it from the
  display name — e.g. `soc_limit_override` keeps its "Default charge limit" display name while
  its id becomes `number.smart_charging_soc_limit_override` (same for "Monthly peak" /
  `monthly_peak_kw` and "Active charge limit" / `active_soc_limit`). That divergence is the
  intended effect of ADR-0013, not something this slice needs to reconcile.
- **`number.smart_charging_target_current` has no catalog row to verify against.**
  `TargetCurrentNumber` (`_attr_translation_key = "target_current"`) has **no** owned-entity
  row in `entity-catalog.md` today — the catalog documents only `input_number.sc_power_target_current_a`
  (the legacy helper id, "Power" mode section). That is a **pre-existing catalog/code drift,
  unrelated to ADR-0013's object_id mechanism**, and issue #417 explicitly lists it as out of
  scope. This slice **still pins its object_id to `target_current`** for consistency with its
  sibling in the same file and to satisfy ADR-0013's "every owned entity" mandate — but its
  resulting `number.smart_charging_target_current` has **no catalog row to check it against**.
  That reconciliation (add a catalog row, or redomain the legacy helper) is a **separate,
  out-of-scope concern** tracked apart from this slice.
- **No entity-registry migration for already-registered entities** (§7).
- **No config-entry schema/version change** (§7).
- **`sensor.smart_charging_desired_current`** (entity-catalog "Diagnostic outputs") and
  **`binary_sensor.smart_charging_plug_in_reminder`** (entity-catalog "Notification
  configuration → Reminders & prompts", deferred per the notifications design) are both
  catalogued but have **no entity class today** — they are catalog-ahead-of-code and not this
  slice's concern; we pin only entities that exist. Both must pin their object_id suffix the
  same way (ADR-0013's last consequence) when they land in a future slice.

---

## 3. What the correct HA mechanism actually is (researched, not assumed)

This was verified directly against the Home Assistant core installed in this repo's venv
(`homeassistant/helpers/entity.py` and `entity_platform.py`, `entity_registry.py`), because
the mechanism in this HA version differs from older guidance.

### The two id-generation inputs HA uses

When an entity with a `unique_id` is first added, `entity_platform._async_add_entity` calls
`_async_derive_object_ids(entity, platform)` (`entity_platform.py`), which produces **two**
distinct registry inputs:

- **`suggested_object_id`** — set only when the integration assigned `entity.entity_id`
  *before* the entity was added (HA captures `split_entity_id(entity.entity_id)[1]` into the
  internal `internal_integration_suggested_object_id`, `entity.py`). This value is
  **never prefixed with the device name** (`entity_registry._async_generate_entity_id`
  docstring: *"`name` and `suggested_object_id` will never be prefixed with the device name"*).
- **`object_id_base`** — otherwise, the value of the `Entity.suggested_object_id`
  **property**. That property (`entity.py:709`) returns the entity's translated **name** (via
  `_name_internal`) — which is exactly the source of the current locale-derived bug.
  `object_id_base` **is** prefixed with the device name when `has_entity_name` is True
  (same docstring: *"`object_id_base` will be [prefixed] if `has_entity_name` is True"*), via
  `_async_get_full_entity_name(...)`.

Priority: `name` (user override) > `suggested_object_id` > `object_id_base`.

### Why `_attr_suggested_object_id` is a no-op here

In this HA version `Entity.suggested_object_id` is a plain computed `@property` that derives
its value from the entity **name**; it does **not** read any `_attr_suggested_object_id`.
Setting that attribute therefore does nothing — it is silently ignored. (This corrects the
common older-HA assumption; it is worth stating so no reviewer expects the attr to work.)

### Chosen mechanism — override the `suggested_object_id` property in the shared base class

Override `SmartChargingEntity.suggested_object_id` to return a **fixed per-entity suffix**
(e.g. `"soc_limit_override"`) instead of the translated name. Because we do **not** set
`entity.entity_id`, this flows through as `object_id_base`, which — with
`has_entity_name = True` and the device named "Smart Charging" (slug `smart_charging`) — HA
prefixes to `smart_charging_<suffix>`. Result: `number.smart_charging_soc_limit_override`,
locale-independent (the returned suffix is a constant, not the translated name). The display
name in the UI still comes from `_attr_translation_key`/`strings.json` and stays fully
localized — only the wire `entity_id` is pinned.

**Why this over setting `self.entity_id` directly** (the `suggested_object_id`-registry-input
path): that path works too, but its value is **not** device-prefixed, so every class would
have to hardcode the full `smart_charging_` prefix in an `entity_id` string, repeating the
prefix and coupling each class to the device slug; HA also marks the backing
`internal_integration_suggested_object_id` *"only handled internally, never to be used by
integrations"* (`entity.py`). The property override keeps each entity declaring only its
short, catalog-matching suffix — mirroring how `_attr_translation_key` is already a short key —
with the device prefix applied once, by HA, in the base class. One implementation point, no
repeated prefix.

**Residual coupling this does not remove.** Because the pinned suffix still flows through
`object_id_base`, HA prefixes it with `device.name_by_user or device.name`
(`entity_registry.py`), not a hardcoded `"smart_charging"` literal. So the pin is
locale-independent but not *device-name*-independent: an owned entity first registered
**after** a user renames the "Smart Charging" device would pick up that custom name's slug
instead of `smart_charging_`. This is a narrower, pre-existing exposure (device rename is rare
and user-initiated, unlike locale which varies per install by default) and is not this ADR's
concern to close — noted here, and again in §7, as a known limitation rather than a silent gap.

**Consistency with the ADRs.** ADR-0013 (Option A) mandates *"an explicit, locale-independent
object_id pinned alongside its `_attr_translation_key`"* — the property override is precisely
that, kept as a **distinct** identifier (ADR-0013's "two related-but-distinct identifiers"),
not derived from the translation key. ADR-0004 keeps owned entities as native platform
entities under one "Smart Charging" device; pinning their object_ids does not change the
owned-vs-mapped boundary. Neither ADR is contradicted.

### Implementation shape (base class)

`SmartChargingEntity` gains one property plus a per-entity attribute it reads:

```python
class SmartChargingEntity(Entity):
    _attr_has_entity_name = True
    _object_id_suffix: str | None = None  # locale-independent object_id suffix (ADR-0013)

    @property
    def suggested_object_id(self) -> str | None:
        # ADR-0013: pin the object_id to a fixed, locale-independent suffix so the
        # registered entity_id matches entity-catalog.md in every HA locale, decoupled
        # from the translated display name (which still comes from translation_key).
        return self._object_id_suffix or super().suggested_object_id
```

Each owned class sets `_object_id_suffix` to its catalog suffix — as a class attribute for the
fixed entities, or in `__init__` for the parameterized departure entity
(`self._object_id_suffix = f"departure_{id_suffix}"`, right beside the existing
`self._attr_translation_key = f"departure_{id_suffix}"`).

---

## 4. Full per-entity mapping

Every owned entity, its current `_attr_translation_key`, the object_id suffix to pin
(identical in value to the translation key — verified per entity against the catalog, not
assumed), the resulting `entity_id`, the catalog row it must match, and whether its generated
id diverges from the catalog **today**.

| File | Class | `_attr_translation_key` | object_id suffix to pin | Resulting `entity_id` | Catalog row | Diverges today? |
| --- | --- | --- | --- | --- | --- | --- |
| `select.py` | `ModeSelect` | `mode` | `mode` | `select.smart_charging_mode` | Core & coordinator | no (coincides) |
| `select.py` | `ProfileSelect` | `profile` | `profile` | `select.smart_charging_profile` | Core & coordinator | no |
| `number.py` | `TargetCurrentNumber` | `target_current` | `target_current` | `number.smart_charging_target_current` | **none — out of scope (§2)** | no |
| `number.py` | `SocLimitOverrideNumber` | `soc_limit_override` | `soc_limit_override` | `number.smart_charging_soc_limit_override` | EV · SOC & battery | **yes** → `default_charge_limit` |
| `sensor.py` | `ChargingStatusSensor` | `status` | `status` | `sensor.smart_charging_status` | Diagnostic outputs | no |
| `sensor.py` | `ActiveModeSensor` | `active_mode` | `active_mode` | `sensor.smart_charging_active_mode` | Diagnostic outputs | no |
| `sensor.py` | `MonthlyPeakSensor` | `monthly_peak_kw` | `monthly_peak_kw` | `sensor.smart_charging_monthly_peak_kw` | Peak protection | **yes** → `monthly_peak` |
| `sensor.py` | `EffectivePeakLimitSensor` | `effective_peak_limit` | `effective_peak_limit` | `sensor.smart_charging_effective_peak_limit` | Diagnostic outputs | no |
| `sensor.py` | `ActiveSocLimitSensor` | `active_soc_limit` | `active_soc_limit` | `sensor.smart_charging_active_soc_limit` | Diagnostic outputs | **yes** → `active_charge_limit` |
| `switch.py` | `HomeDaySwitch` | `home_day` | `home_day` | `switch.smart_charging_home_day` | Home day | no |
| `time.py` | `SmartChargingDepartureTime` | `departure_mon` | `departure_mon` | `time.smart_charging_departure_mon` | Departure times (`<dow>`) | **yes** → `monday_departure_time` |
| `time.py` | `SmartChargingDepartureTime` | `departure_tue` | `departure_tue` | `time.smart_charging_departure_tue` | Departure times (`<dow>`) | **yes** |
| `time.py` | `SmartChargingDepartureTime` | `departure_wed` | `departure_wed` | `time.smart_charging_departure_wed` | Departure times (`<dow>`) | **yes** |
| `time.py` | `SmartChargingDepartureTime` | `departure_thu` | `departure_thu` | `time.smart_charging_departure_thu` | Departure times (`<dow>`) | **yes** |
| `time.py` | `SmartChargingDepartureTime` | `departure_fri` | `departure_fri` | `time.smart_charging_departure_fri` | Departure times (`<dow>`) | **yes** |
| `time.py` | `SmartChargingDepartureTime` | `departure_sat` | `departure_sat` | `time.smart_charging_departure_sat` | Departure times (`<dow>`) | **yes** |
| `time.py` | `SmartChargingDepartureTime` | `departure_sun` | `departure_sun` | `time.smart_charging_departure_sun` | Departure times (`<dow>`) | **yes** |
| `time.py` | `SmartChargingDepartureTime` | `departure_holiday` | `departure_holiday` | `time.smart_charging_departure_holiday` | Departure times (holiday) | **yes** → `public_holiday_departure_time` |
| `time.py` | `SmartChargingDepartureTime` | `departure_home_day` | `departure_home_day` | `time.smart_charging_departure_home_day` | Departure times (home_day) | **yes** → `home_day_departure_time` |

19 owned entities total. 12 diverge from the catalog today (1 number, 2 sensor, 9 time); the
other 7 coincide but are pinned anyway per ADR-0013. The 9 `time` suffixes come from the
`DAY_MON`…`DAY_SUN` / `DEPARTURE_OVERRIDE_HOLIDAY` / `DEPARTURE_OVERRIDE_HOME_DAY` constants
already used in `time.py`, so the pin reuses those constants (no new literals).

---

## 5. Where the change lives

```text
custom_components/smart_charging/
  entity.py     # + `_object_id_suffix` attr + `suggested_object_id` property override (§3) — the mechanism
  select.py     # set _object_id_suffix on ModeSelect, ProfileSelect
  number.py     # set _object_id_suffix on TargetCurrentNumber, SocLimitOverrideNumber
  sensor.py     # set _object_id_suffix on the 5 sensor classes
  switch.py     # set _object_id_suffix on HomeDaySwitch
  time.py       # set self._object_id_suffix = f"departure_{id_suffix}" in __init__
```

No `strings.json`, `const.py`, `config_flow.py`, `__init__.py`, or adapter change. The
`time.py` pin reuses the existing day/override constants; every other pin is a single-line
class attribute whose value equals the class's existing `_attr_translation_key`.

---

## 6. Testing approach (ADR-0009 split)

Entity platform files are HA-coupled (they register through `entity_platform` and the entity
registry), so per **ADR-0009** their `entity_id`-generation behavior is tested on the **HA
harness**, not plain pytest. The one exception is the `suggested_object_id` property override
itself (§3): it reads a plain instance attribute and calls no HA registry/platform API, so it
is pure logic and gets a small standalone plain-pytest test (`tests/test_entity.py`) proving the
override in isolation, ahead of and independent from any owned entity pinning its suffix.

**Why most existing entity tests do not exercise this fix.** Some tests in `tests/test_select.py`,
`tests/test_sensor.py`, and `tests/test_time.py` set `entity.entity_id = "..."` *manually*
before adding the entity to a `MockEntityPlatform`; those bypass the registry-derived object_id
entirely (they take the `suggested_object_id`-registry-input path, not `object_id_base`), so
they neither verify nor are broken by this change. Others — several tests across
`tests/test_select.py`, `tests/test_number.py`, `tests/test_switch.py`, and `tests/test_time.py`
— add the entity to `MockEntityPlatform` **without** setting `entity_id`, which *does* take the
`object_id_base`/`suggested_object_id`-property path this slice changes; because no device is
created under `MockEntityPlatform`, these would register unprefixed ids (e.g. `switch.home_day`)
after the pin instead of the currently name-derived ones. None of them assert an `entity_id`
today, so all keep passing either way, but they provide **no** coverage of the pin either. The
end-to-end tests that do assert a real, HA-generated `entity_id` (device prefix included) —
`tests/test_init.py` and the full-setup suites in `tests/test_captar_end_to_end.py`,
`tests/test_solar_end_to_end.py`, and `tests/test_deadline_soc_management_end_to_end.py` — all
assert only *coincident* ids (ones unaffected by this pin), so none of them guard the 12
diverging ids either. `tests/test_init.py` is where this slice's coverage belongs because it
already carries the one assertion that currently encodes the bug (line 149) and is where new
full-setup tests for this integration are conventionally added.

Changes required:

1. **`tests/test_init.py:149` (`test_setup_falls_back_to_default_soc_limit_for_pre_solar_entries`)** — flip the asserted id from
   `number.smart_charging_default_charge_limit` to
   `number.smart_charging_soc_limit_override`. This is the one existing assertion that
   currently encodes the bug; it turns red the moment the pin lands and green once the
   assertion is corrected. Existing full-setup assertions that already reference a
   *coincident* id (`sensor.smart_charging_status`, `sensor.smart_charging_active_mode`,
   `number.smart_charging_target_current`) resolve to the **same** id after the pin and need
   no change.

2. **New comprehensive regression test in `tests/test_init.py`** — enumerate **all 19 owned
   entity_ids** against their catalog values after a full setup, looking each up by its
   `unique_id` in the entity registry (`er.async_get(hass).async_get_entity_id(...)`) and
   asserting the returned `entity_id` equals the catalog value, plus a reverse assertion that no
   registered owned entity is missing from that expectation table (closing ADR-0013's "any
   future owned entity must pin its object_id the same way" consequence — without it, a 20th
   owned entity added later without a pin would pass silently). `tests/test_init.py` has no
   single owned-id-enumeration check today (only scattered per-id `hass.states.get(...)`
   assertions); this one guards the whole owned population against future drift in one place,
   which is the corrective intent of ADR-0013. It lands with the last per-entity pin (§ plan
   Task 2.3), added once every owned entity already pins its suffix so it lands green rather
   than driving the work; plan Task 3 re-runs it as part of the full-suite check, but does not
   introduce it. Looking entities up by `unique_id` (not by the literal id) keeps the test
   locale-robust: it asserts the *generated* id equals the catalog id, which is the property
   under test.

No **new test file** is warranted for this enumeration test — it is a corrective change to
existing entities, not new behavior, so the coverage belongs alongside the existing full-setup
tests in `tests/test_init.py`. (`tests/test_entity.py`, added in Task 1, is a separate, small
new file for the base-class mechanism itself — see above.)

---

## 7. Packaging & rollout

- **First-registration only; no entity-registry migration.** Both `object_id_base` and
  `suggested_object_id` influence an `entity_id` **only at creation** (when the registry has
  no entry for that `unique_id` yet). An entity already in a user's registry keeps its
  persisted — currently wrong — `entity_id`; the code change will **not** rename it. Renaming
  an existing install would require either an `async_migrate_entry`/`async_regenerate_entity_id`
  registry migration or the user manually renaming (or deleting and re-adding) the affected
  entities.
- **Device-rename exposure (see §3).** The pin removes locale-dependence but not
  device-name-dependence: an owned entity first registered after a user renames the "Smart
  Charging" device inherits that custom name's slug instead of `smart_charging_`. Out of scope
  here, same as the migration limitation above.
- **Why "new installs only, no migration" is the correct scope here.** The integration is
  pre-release — `manifest.json` version `0.2.1`, an actively-developed HACS custom
  integration with no stable installed base whose entity_ids we must preserve. ADR-0013 did
  not ask for a migration, and adding a registry-rename migration would risk clobbering an
  `entity_id` a user deliberately customized. So the accepted, out-loud scope is: **fixed for
  every new install; no migration for the few pre-release installs**, which can delete and
  re-add the integration (or rename in the UI) if they care. This is stated as an explicit
  limitation, not silently dropped.
- **No config-entry version bump.** `config_flow.py`'s `VERSION = 1` (with no
  `async_migrate_entry`) governs the config-entry **data/options schema** — a different
  subsystem from the entity registry. This slice changes neither the entry schema nor any
  `CONF_*`/`DEFAULT_*` key, so no bump and no entry migration is required or appropriate.

---

## 8. Next step

This design feeds the paired TDD plan
([`2026-07-27-owned-entity-object-ids.md`](2026-07-27-owned-entity-object-ids.md)). Build
order: the base-class mechanism first, proven green in isolation by a standalone unit test
(no owned entity or `tests/test_init.py` assertion touched yet); then the per-file pins, each
turning its own slice of `tests/test_init.py` coverage green in the same commit — the corrected
`test_init.py:149` assertion lands with the `select`/`number` pins, and the comprehensive
enumeration test (with its reverse assertion) lands already-green with the final `time.py` pins;
then the full-suite integration checkpoint. No task commits a known-red test, and no
`custom_components/` code is written ahead of the plan.
