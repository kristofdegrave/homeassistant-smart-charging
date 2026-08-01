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
one `_object_id_suffix` value. No new service, entity, config key, adapter role, or structural
boundary (design §2).

**Tech Stack:** Same as the shipped slices — Python ≥3.12, Home Assistant,
`pytest-homeassistant-custom-component` (HA harness, ADR-0009), `ruff`. The base-class property
override (Task 1) is pure logic with no entity-registry/platform interaction → plain pytest;
every other task here is HA-coupled (entity registration) → HA harness.

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

## Phase 1 — The mechanism, proven in isolation (plain pytest)

### Task 1: Base-class `suggested_object_id` override, proven by a standalone unit test

Honors **ADR-0013** (explicit, locale-independent object_id pinned alongside `translation_key`).
This task lands the mechanism **fully green on its own** — it does not touch any owned entity
class or `tests/test_init.py`, so it cannot leave a known-red assertion in the repo. The
per-file pins in Phase 2 are what turn `tests/test_init.py`'s assertions green, each in its own
commit.

**Files:**
- Modify: `custom_components/smart_charging/entity.py`
- Add: `tests/test_entity.py`

**Step 1: Failing test (plain pytest — a property override with no entity-registry or
platform interaction is pure logic per ADR-0009, not HA-coupled).**

```python
"""Tests for SmartChargingEntity's object_id pin (ADR-0013)."""

from custom_components.smart_charging.entity import SmartChargingEntity


def test_suggested_object_id_falls_back_when_unset():
    """Undecorated entities keep HA's default (translated-name-derived) behavior."""
    entity = SmartChargingEntity(entry_id="test_entry")
    assert entity.suggested_object_id is None


def test_suggested_object_id_returns_pinned_suffix_when_set():
    """ADR-0013: a subclass pinning `_object_id_suffix` overrides the translated-name
    default, decoupling the registered object_id from the display name."""
    entity = SmartChargingEntity(entry_id="test_entry")
    entity._object_id_suffix = "soc_limit_override"
    assert entity.suggested_object_id == "soc_limit_override"
```

**Step 2: Run** → both fail (`suggested_object_id` doesn't exist yet on the base class).

**Step 3: Implement** the mechanism in `entity.py` (design §3):

```python
class SmartChargingEntity(Entity):
    _attr_has_entity_name = True
    _object_id_suffix: str | None = None  # locale-independent object_id suffix (ADR-0013)

    @property
    def suggested_object_id(self) -> str | None:
        # ADR-0013: pin the object_id to a fixed, locale-independent suffix so the
        # registered entity_id matches entity-catalog.md in every HA locale, decoupled
        # from the translated display name (which still comes from translation_key). The
        # returned suffix is device-name-prefixed by HA because has_entity_name is True,
        # yielding e.g. number.smart_charging_soc_limit_override.
        return self._object_id_suffix or super().suggested_object_id
```

**Step 4: Run** → both green. **Step 5: Commit.**

```bash
git add custom_components/smart_charging/entity.py tests/test_entity.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add locale-independent object_id mechanism to owned-entity base (ADR-0013)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

> **⎔ Phase 1 checkpoint:** `SmartChargingEntity.suggested_object_id` returns
> `_object_id_suffix` when set, else falls back to HA's default — proven in isolation, fully
> green. No owned entity pins its suffix yet; that is Phase 2.

---

## Phase 2 — Pin the suffix on every owned entity (HA harness)

Each task sets `_object_id_suffix` (value == the class's existing `_attr_translation_key`,
design §4) and lands its own `tests/test_init.py` coverage green in the same commit — no task
here ever leaves a known-red assertion. All honor **ADR-0013** / **ADR-0004** (owned native
entities) / **ADR-0009**.

### Task 2.1: `select.py` + `number.py`, plus the corrected `test_init.py` assertion

**Files:** Modify `custom_components/smart_charging/select.py`,
`custom_components/smart_charging/number.py`, `tests/test_init.py`.

**Step 1: Failing test.** Correct the existing assertion in `tests/test_init.py` (line ~149)
from the locale-derived bug to the catalog id:

```python
state = hass.states.get("number.smart_charging_soc_limit_override")
assert state is not None
assert float(state.state) == 80.0
```

**Step 2: Run** → fails (today's id is `number.smart_charging_default_charge_limit`).

**Step 3: Implement.** Add a `_object_id_suffix` class attribute to each of `ModeSelect`
(`"mode"`), `ProfileSelect` (`"profile"`), `TargetCurrentNumber` (`"target_current"`),
`SocLimitOverrideNumber` (`"soc_limit_override"`). Before/after ids: `select.smart_charging_mode`
and `select.smart_charging_profile` and `number.smart_charging_target_current` already coincide
(pinned to prevent future drift); `number.smart_charging_default_charge_limit` →
`number.smart_charging_soc_limit_override`.

**Step 4: Run** → the corrected assertion passes. **Step 5: Commit.**

```bash
git add custom_components/smart_charging/select.py custom_components/smart_charging/number.py tests/test_init.py
git commit --author="Claude <noreply@anthropic.com>" -m "fix: pin select/number owned-entity object_ids to catalog ids (ADR-0013)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

### Task 2.2: `sensor.py` + `switch.py`

**Files:** Modify `custom_components/smart_charging/sensor.py`,
`custom_components/smart_charging/switch.py`.

**Change:** add `_object_id_suffix` to `ChargingStatusSensor` (`"status"`), `ActiveModeSensor`
(`"active_mode"`), `MonthlyPeakSensor` (`"monthly_peak_kw"`), `EffectivePeakLimitSensor`
(`"effective_peak_limit"`), `ActiveSocLimitSensor` (`"active_soc_limit"`), and `HomeDaySwitch`
(`"home_day"`). Before/after: `sensor.smart_charging_monthly_peak` →
`sensor.smart_charging_monthly_peak_kw`; `sensor.smart_charging_active_charge_limit` →
`sensor.smart_charging_active_soc_limit`; the other three sensors and the switch already
coincide (pinned to prevent drift). This task doesn't touch `tests/test_init.py` — no existing
assertion there covers these ids yet (that lands with Task 2.3's enumeration test), so there is
nothing to turn red or green here beyond the full suite continuing to pass.

**Run** → full suite still green (no regression). **Commit.**

```bash
git add custom_components/smart_charging/sensor.py custom_components/smart_charging/switch.py
git commit --author="Claude <noreply@anthropic.com>" -m "fix: pin sensor/switch owned-entity object_ids to catalog ids (ADR-0013)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

### Task 2.3: `time.py` (the 9 departure entities) + the comprehensive enumeration test

**Files:** Modify `custom_components/smart_charging/time.py`, `tests/test_init.py`.

**Step 1: Pin the remaining entities.** In `SmartChargingDepartureTime.__init__`, set
`self._object_id_suffix = f"departure_{id_suffix}"` right beside the existing
`self._attr_translation_key = f"departure_{id_suffix}"` (reusing the `id_suffix` already
built from `DAY_MON`…`DAY_SUN` / `DEPARTURE_OVERRIDE_HOLIDAY` / `DEPARTURE_OVERRIDE_HOME_DAY`
— no new literals). Before/after for all 9:
`time.smart_charging_<weekday>_departure_time` (and `public_holiday_`/`home_day_` variants) →
`time.smart_charging_departure_<suffix>`.

**Step 2: Add the comprehensive owned-id enumeration regression test** (design §6). By this
point every owned entity pins its suffix, so this test is added already green — it is the
integration checkpoint for the whole slice, not a driver of it. After a full config-entry setup
that forwards all five platforms, look each owned entity up by its `unique_id` and assert the
registry's generated `entity_id` equals the catalog value, **and** that no owned entity is
missing from the expectation table (closing ADR-0013's "any future owned entity must pin its
object_id the same way" consequence):

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
        "target_current": "number.smart_charging_target_current",  # no catalog row (design §2)
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

    # No owned entity may be missing from `expected` above — a future owned entity added
    # without a pin here would otherwise pass this test silently (ADR-0013's last consequence).
    registered = {
        e.unique_id.removeprefix(f"{entry.entry_id}_")
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    assert registered == set(expected)
```

Add the `homeassistant.helpers.entity_registry as er` import if not already present, plus any
`CONF_*` already used elsewhere in the file.

**Step 3: Run** → the 9 `departure_*` rows and the new enumeration test (including its reverse
assertion) all pass. **Step 4: Commit.**

```bash
git add custom_components/smart_charging/time.py tests/test_init.py
git commit --author="Claude <noreply@anthropic.com>" -m "fix: pin departure-time owned-entity object_ids to catalog ids, add enumeration regression test (ADR-0013)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

> **⎔ Phase 2 checkpoint:** every owned entity sets `_object_id_suffix`; the corrected
> `test_init.py:149` assertion and the new enumeration test (with its reverse assertion) are
> both green.

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
  `entity_id`s equal their catalog value (design §4 table), and the reverse assertion confirms
  no owned entity is missing from the expectation table;
- the corrected `test_init.py` SOC-limit assertion passes;
- no other test regressed. Design §6 explains in detail which existing entity tests do and
  don't exercise this change and why (some bypass the registry-derived path entirely by setting
  `entity.entity_id` manually; others take the changed path but assert no `entity_id`, so they
  pass either way) — if any of them *did* start failing, treat it as a genuine signal to
  investigate against that explanation, not a false alarm to silence.

**Step 3:** If any pre-existing full-setup assertion still encodes a now-wrong id (none
expected beyond the corrected line 149), fix it to the catalog id and note it. **Commit** only
if a fix was needed.

> **⎔ Phase 3 / slice checkpoint:** `ruff check . && ruff format --check . && pytest -q` all
> green; every owned entity registers under its `entity-catalog.md` id, locale-independently
> (ADR-0013 satisfied). Out of scope and unchanged, per design §2: `entity-catalog.md`/README,
> the `target_current` catalog-row gap, and any entity-registry migration for already-registered
> pre-release installs.
