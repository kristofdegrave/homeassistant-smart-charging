# Owned-entity object_ids Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Pin an explicit, locale-independent `object_id` on every owned entity across
`custom_components/smart_charging/{select,number,sensor,switch,time}.py` so each registers
under the `entity_id` [`entity-catalog.md`](../analysis/entity-catalog.md) documents, in
every HA locale — per [`2026-07-27-owned-entity-object-ids-design.md`](2026-07-27-owned-entity-object-ids-design.md)
and [ADR-0013](../adl/0013-stable-owned-entity-object-ids.md).

**Architecture:** One shared mechanism in `entity.py` — override the
`SmartChargingEntity.suggested_object_id` property to return a fixed per-entity suffix
(design §3), which HA prefixes with the `smart_charging` device slug to yield the catalog id
(locale-independent, decoupled from the translated display name). Each owned class then sets
one `_object_id` value. No new service, entity, config key, adapter role, or structural
boundary (design §2).

**Tech Stack:** Same as the shipped slices — Python ≥3.12, Home Assistant,
`pytest-homeassistant-custom-component` (HA harness, ADR-0009), `ruff`. Every task here is
HA-coupled (entity registration) → HA harness; there is no plain-pytest piece.

**Model:** Per CLAUDE.md, this is development work — execute on **Sonnet**.

---

## Conventions used throughout

Same as `2026-07-21-notifications.md`'s conventions (package root, tests-mirror-1:1,
commit-after-green, re-check `git branch --show-current` before every commit,
`--author="Claude <noreply@anthropic.com>"` + `Co-Authored-By: Claude Sonnet 5`
trailer). Additionally: the object_id suffix pinned on each entity **equals in value** its
existing `_attr_translation_key` (design §4) but is a **distinct** identifier (ADR-0013 — two
related-but-distinct identifiers), so it is set explicitly, never derived from the
translation key. Do not touch `strings.json`, `README.md`, or `entity-catalog.md` (design §2
non-goals).

---

## Phase 1 — The mechanism + the failing assertions (HA harness)

### Task 1: Base-class `suggested_object_id` override, with the corrected + new tests as the failing tests

Honors **ADR-0013** (explicit, locale-independent object_id pinned alongside `translation_key`)
and **ADR-0009** (HA harness — entity registration is HA-coupled). The failing tests here are
what drive the whole slice red→green; the per-file pins in Phase 2 turn each entity's row of
the enumeration test green.

**Files:**
- Modify: `custom_components/smart_charging/entity.py`
- Modify: `tests/test_init.py`

**Step 1: Failing tests (HA harness).**

1. **Correct the existing assertion.** In `tests/test_init.py`, change the id asserted at
   line ~149 from `number.smart_charging_default_charge_limit` (the locale-derived bug) to
   the catalog id `number.smart_charging_soc_limit_override`:

   ```python
   state = hass.states.get("number.smart_charging_soc_limit_override")
   assert state is not None
   assert float(state.state) == 80.0
   ```

2. **Add a comprehensive owned-id enumeration regression test** (design §6). After a full
   config-entry setup that forwards all five platforms, look each owned entity up by its
   `unique_id` and assert the registry's generated `entity_id` equals the catalog value:

   ```python
   async def test_every_owned_entity_id_matches_entity_catalog(hass):
       """ADR-0013: every owned entity registers under its documented entity-catalog id,
       independent of the translated display name. Looked up by unique_id so the test
       asserts the GENERATED id equals the catalog id (the property under test)."""
       _seed_states(hass, status="Charging")
       data = _entry_data()
       data[CONF_SOLAR_INSTALLED] = True
       data[CONF_EV_SOC_ENTITY] = "sensor.ev_soc"
       hass.states.async_set("sensor.ev_soc", "50.0")
       entry = MockConfigEntry(domain=DOMAIN, data=data, options=_entry_options())
       entry.add_to_hass(hass)
       assert await hass.config_entries.async_setup(entry.entry_id)
       await hass.async_block_till_done()

       registry = er.async_get(hass)
       # (unique_id suffix, expected catalog entity_id) for all 19 owned entities.
       expected = {
           "mode": "select.smart_charging_mode",
           "profile": "select.smart_charging_profile",
           "target_current": "number.smart_charging_target_current",
           "soc_limit_override": "number.smart_charging_soc_limit_override",
           "status": "sensor.smart_charging_status",
           "active_mode": "sensor.smart_charging_active_mode",
           "monthly_peak_kw": "sensor.smart_charging_monthly_peak_kw",
           "effective_peak_limit": "sensor.smart_charging_effective_peak_limit",
           "active_soc_limit": "sensor.smart_charging_active_soc_limit",
           "home_day": "switch.smart_charging_home_day",
           "departure_mon": "time.smart_charging_departure_mon",
           "departure_tue": "time.smart_charging_departure_tue",
           "departure_wed": "time.smart_charging_departure_wed",
           "departure_thu": "time.smart_charging_departure_thu",
           "departure_fri": "time.smart_charging_departure_fri",
           "departure_sat": "time.smart_charging_departure_sat",
           "departure_sun": "time.smart_charging_departure_sun",
           "departure_holiday": "time.smart_charging_departure_holiday",
           "departure_home_day": "time.smart_charging_departure_home_day",
       }
       for uid_suffix, want_id in expected.items():
           domain = want_id.split(".", 1)[0]
           got = registry.async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{uid_suffix}")
           assert got == want_id, f"{uid_suffix}: {got!r} != {want_id!r}"
   ```

   Add the `homeassistant.helpers.entity_registry as er` import if not already present, plus
   any `CONF_*` already used elsewhere in the file. `target_current` is asserted at its
   sibling-consistent id even though it has **no catalog row** (design §2 out-of-scope note) —
   its expected id here is code-consistency, not catalog-verified.

**Step 2: Run** → both fail: the corrected assertion (id is `default_charge_limit` today) and
the enumeration test (12 of 19 ids diverge — the `soc_limit_override`, `monthly_peak_kw`,
`active_soc_limit`, and 9 `departure_*` rows).

**Step 3: Implement** the mechanism in `entity.py` (design §3):

```python
class SmartChargingEntity(Entity):
    _attr_has_entity_name = True
    _object_id: str | None = None  # locale-independent object_id suffix (ADR-0013)

    @property
    def suggested_object_id(self) -> str | None:
        # ADR-0013: pin the object_id to a fixed, locale-independent suffix so the
        # registered entity_id matches entity-catalog.md in every HA locale, decoupled
        # from the translated display name (which still comes from translation_key). The
        # returned suffix is device-name-prefixed by HA because has_entity_name is True,
        # yielding e.g. number.smart_charging_soc_limit_override.
        return self._object_id or super().suggested_object_id
```

At this point no subclass sets `_object_id` yet, so the enumeration test still fails — the
per-file pins in Phase 2 make it pass class by class. (If preferred, Task 1 and the Phase 2
pins may be developed together and committed once the whole enumeration test is green; keep
them as separate commits per file if committing incrementally, re-running the suite after
each.)

**Step 4: Run** → mechanism present; enumeration test still red pending Phase 2. **Step 5:
Commit** the mechanism + tests.

```bash
git add custom_components/smart_charging/entity.py tests/test_init.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add locale-independent object_id mechanism to owned-entity base (ADR-0013)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

> **⎔ Phase 1 checkpoint:** `SmartChargingEntity.suggested_object_id` returns `_object_id`
> when set; the corrected `test_init.py:149` and the new enumeration test exist and drive the
> remaining work.

---

## Phase 2 — Pin the suffix on every owned entity (HA harness)

Each task sets `_object_id` (value == the class's existing `_attr_translation_key`, design §4)
and turns its rows of the Phase 1 enumeration test green. All honor **ADR-0013** / **ADR-0004**
(owned native entities) / **ADR-0009**.

### Task 2.1: `select.py` + `number.py`

**Files:** Modify `custom_components/smart_charging/select.py`,
`custom_components/smart_charging/number.py`.

**Change:** add a `_object_id` class attribute to each of `ModeSelect` (`"mode"`),
`ProfileSelect` (`"profile"`), `TargetCurrentNumber` (`"target_current"`),
`SocLimitOverrideNumber` (`"soc_limit_override"`). Before/after ids: `select.smart_charging_mode`
and `select.smart_charging_profile` and `number.smart_charging_target_current` already coincide
(pinned to prevent future drift); `number.smart_charging_default_charge_limit` →
`number.smart_charging_soc_limit_override`.

**Run** → the enumeration test's `soc_limit_override` row and the corrected `test_init.py:149`
now pass; select/number rows green. **Commit.**

```bash
git add custom_components/smart_charging/select.py custom_components/smart_charging/number.py
git commit --author="Claude <noreply@anthropic.com>" -m "fix: pin select/number owned-entity object_ids to catalog ids (ADR-0013)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

### Task 2.2: `sensor.py` + `switch.py`

**Files:** Modify `custom_components/smart_charging/sensor.py`,
`custom_components/smart_charging/switch.py`.

**Change:** add `_object_id` to `ChargingStatusSensor` (`"status"`), `ActiveModeSensor`
(`"active_mode"`), `MonthlyPeakSensor` (`"monthly_peak_kw"`), `EffectivePeakLimitSensor`
(`"effective_peak_limit"`), `ActiveSocLimitSensor` (`"active_soc_limit"`), and `HomeDaySwitch`
(`"home_day"`). Before/after: `sensor.smart_charging_monthly_peak` →
`sensor.smart_charging_monthly_peak_kw`; `sensor.smart_charging_active_charge_limit` →
`sensor.smart_charging_active_soc_limit`; the other three sensors and the switch already
coincide (pinned to prevent drift).

**Run** → enumeration test's sensor + switch rows green. **Commit.**

```bash
git add custom_components/smart_charging/sensor.py custom_components/smart_charging/switch.py
git commit --author="Claude <noreply@anthropic.com>" -m "fix: pin sensor/switch owned-entity object_ids to catalog ids (ADR-0013)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

### Task 2.3: `time.py` (the 9 departure entities)

**Files:** Modify `custom_components/smart_charging/time.py`.

**Change:** in `SmartChargingDepartureTime.__init__`, set
`self._object_id = f"departure_{id_suffix}"` right beside the existing
`self._attr_translation_key = f"departure_{id_suffix}"` (reusing the `id_suffix` already
built from `DAY_MON`…`DAY_SUN` / `DEPARTURE_OVERRIDE_HOLIDAY` / `DEPARTURE_OVERRIDE_HOME_DAY`
— no new literals). Before/after for all 9:
`time.smart_charging_<weekday>_departure_time` (and `public_holiday_`/`home_day_` variants) →
`time.smart_charging_departure_<suffix>`.

**Run** → enumeration test's 9 `departure_*` rows green; the whole enumeration test now
passes. **Commit.**

```bash
git add custom_components/smart_charging/time.py
git commit --author="Claude <noreply@anthropic.com>" -m "fix: pin departure-time owned-entity object_ids to catalog ids (ADR-0013)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

> **⎔ Phase 2 checkpoint:** every owned entity sets `_object_id`; the Phase 1 enumeration test
> is fully green.

---

## Phase 3 — Integration checkpoint (full HA-harness suite)

### Task 3: Full-suite regression + catalog conformance

**Files:** none (verification only; add fixes if the suite surfaces a stale assertion).

**Step 1:** Run the full quality gate:

```bash
ruff check . && ruff format --check . && pytest -q
```

**Step 2:** Confirm:
- the new `test_every_owned_entity_id_matches_entity_catalog` passes — all 19 owned
  `entity_id`s equal their catalog value (design §4 table);
- the corrected `test_init.py` SOC-limit assertion passes;
- no other test regressed. In particular, `tests/test_select.py`, `tests/test_sensor.py`,
  and `tests/test_time.py` set `entity.entity_id` manually and are unaffected (design §6) —
  if any *did* break, that is a signal the mechanism took the wrong id path and must be
  investigated, not silenced.

**Step 3:** If any pre-existing full-setup assertion still encodes a now-wrong id (none
expected beyond the corrected line 149), fix it to the catalog id and note it. **Commit** only
if a fix was needed.

> **⎔ Phase 3 / slice checkpoint:** `ruff check . && ruff format --check . && pytest -q` all
> green; every owned entity registers under its `entity-catalog.md` id, locale-independently
> (ADR-0013 satisfied). Out of scope and unchanged, per design §2: `entity-catalog.md`/README,
> the `target_current` catalog-row gap, and any entity-registry migration for already-registered
> pre-release installs.
