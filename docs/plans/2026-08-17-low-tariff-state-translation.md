# Low-tariff adapter role state-translation — TDD plan

**Design:** [2026-08-17-low-tariff-state-translation-design.md](2026-08-17-low-tariff-state-translation-design.md)
**Issue:** #746 (analysis: #743, PR #745)

Each task: failing test → minimal implementation → green → commit. No task starts before the
previous one is green.

---

## T1 — `LowTariffReadAdapter` (new, standalone)

**Test boundary (ADR-0009):** HA harness — reads live entity state via `_ReadOnlyAdapter`, same
boundary as `StatusReadAdapter`/`BooleanReadAdapter`.

**File:** `tests/adapters/test_tariff.py` (new, mirrors `tests/adapters/test_status.py`'s shape).

Write these failing tests first, against `custom_components.smart_charging.adapters.tariff.LowTariffReadAdapter`
(does not exist yet):

```python
"""HA-harness tests for the low-tariff adapter (ADR-0003, RA2 extension)."""

import pytest
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN

from custom_components.smart_charging.adapters.tariff import LowTariffReadAdapter

LOW_STATES = ["low", "off-peak"]


async def test_native_on_returns_true(hass):
    hass.states.async_set("binary_sensor.tariff", STATE_ON)
    adapter = LowTariffReadAdapter(hass, "binary_sensor.tariff", [])
    assert await adapter.read() is True


async def test_native_off_returns_false(hass):
    hass.states.async_set("binary_sensor.tariff", STATE_OFF)
    adapter = LowTariffReadAdapter(hass, "binary_sensor.tariff", [])
    assert await adapter.read() is False


async def test_listed_raw_state_returns_true(hass):
    hass.states.async_set("sensor.tariff", "low")
    adapter = LowTariffReadAdapter(hass, "sensor.tariff", LOW_STATES)
    assert await adapter.read() is True


async def test_unlisted_raw_state_returns_false(hass):
    # Not a fault (unlike StatusReadAdapter's unmapped-state case) -- the low-tariff
    # flag's own permissive default (entity-catalog.md).
    hass.states.async_set("sensor.tariff", "high")
    adapter = LowTariffReadAdapter(hass, "sensor.tariff", LOW_STATES)
    assert await adapter.read() is False


async def test_empty_states_list_returns_false_for_non_boolean_state(hass):
    hass.states.async_set("sensor.tariff", "high")
    adapter = LowTariffReadAdapter(hass, "sensor.tariff", [])
    assert await adapter.read() is False


async def test_unavailable_returns_none(hass):
    hass.states.async_set("sensor.tariff", STATE_UNAVAILABLE)
    adapter = LowTariffReadAdapter(hass, "sensor.tariff", LOW_STATES)
    assert await adapter.read() is None


async def test_unknown_returns_none(hass):
    hass.states.async_set("sensor.tariff", STATE_UNKNOWN)
    adapter = LowTariffReadAdapter(hass, "sensor.tariff", LOW_STATES)
    assert await adapter.read() is None


async def test_absent_returns_none(hass):
    adapter = LowTariffReadAdapter(hass, "sensor.tariff", LOW_STATES)
    assert await adapter.read() is None


async def test_write_raises_not_implemented(hass):
    adapter = LowTariffReadAdapter(hass, "sensor.tariff", LOW_STATES)
    with pytest.raises(NotImplementedError):
        await adapter.write(True)
```

**Implementation:** `custom_components/smart_charging/adapters/tariff.py` (new file) — the class
in design doc §3, verbatim.

**Commit:** `feat: LowTariffReadAdapter for the widened low_tariff role (T1, issue #746)`

---

## T2 — Wire into the adapter factory

**Test boundary:** HA harness (existing file).

**File:** `tests/adapters/test_factory.py`.

1. Update the existing `test_factory_builds_low_tariff_role_when_configured` — it currently
   asserts `isinstance(adapters[ROLE_LOW_TARIFF], BooleanReadAdapter)`; change the assertion to
   `LowTariffReadAdapter` (this makes the test fail against today's `factory.py`, since the
   production branch still builds `BooleanReadAdapter`).
2. Add a new failing test: `test_factory_passes_configured_low_tariff_states`:
   ```python
   async def test_factory_passes_configured_low_tariff_states(hass):
       data = _data()
       data[CONF_LOW_TARIFF_ENTITY] = "sensor.tariff"
       data[CONF_LOW_TARIFF_STATES] = ["low", "off-peak"]
       adapters = build_adapters(hass, data)
       assert adapters[ROLE_LOW_TARIFF]._low_states == {"low", "off-peak"}
   ```
3. Add `test_factory_low_tariff_states_defaults_to_empty_when_not_configured`:
   ```python
   async def test_factory_low_tariff_states_defaults_to_empty_when_not_configured(hass):
       data = _data()
       data[CONF_LOW_TARIFF_ENTITY] = "binary_sensor.low_tariff"
       adapters = build_adapters(hass, data)
       assert adapters[ROLE_LOW_TARIFF]._low_states == set()
   ```

**Implementation:** `custom_components/smart_charging/adapters/factory.py` — import
`LowTariffReadAdapter` from `.tariff` instead of relying on `BooleanReadAdapter` for this role;
change the `CONF_LOW_TARIFF_ENTITY` branch to:

```python
if data.get(CONF_LOW_TARIFF_ENTITY):
    adapters[ROLE_LOW_TARIFF] = LowTariffReadAdapter(
        hass, data[CONF_LOW_TARIFF_ENTITY], data.get(CONF_LOW_TARIFF_STATES, [])
    )
```

Also import `CONF_LOW_TARIFF_STATES` from `.const`. `BooleanReadAdapter`'s import and its
`home_day_external` branch are untouched.

**Commit:** `feat: factory builds low_tariff via LowTariffReadAdapter (T2, issue #746)`

---

## T3 — Config-flow selector + state-translation field

**Test boundary:** HA harness (config flow is HA-coupled, ADR-0009).

**File:** `tests/test_config_flow.py`.

Add to the existing ungated `mappings`-step test group:

```python
async def test_mappings_step_accepts_sensor_domain_low_tariff_entity(hass):
    # Widened selector: a sensor-domain tariff signal with a textual state must be
    # selectable, not just binary_sensor/input_boolean.
    ...  # drive the flow to the mappings step, submit CONF_LOW_TARIFF_ENTITY="sensor.tariff"
    # plus CONF_LOW_TARIFF_STATES="low, off-peak"; assert the step advances (no
    # vol.Invalid) and the resulting entry's data contains
    # {CONF_LOW_TARIFF_ENTITY: "sensor.tariff", CONF_LOW_TARIFF_STATES: ["low", "off-peak"]}.


async def test_mappings_step_low_tariff_states_parsed_like_charger_status_states(hass):
    # "low, off-peak" (with surrounding whitespace) parses to ["low", "off-peak"],
    # reusing _parse_states -- same shape as CONF_CONNECTED_STATES/CONF_CHARGING_STATES.
    ...


async def test_mappings_step_low_tariff_states_optional(hass):
    # Submitting the mappings step with CONF_LOW_TARIFF_ENTITY mapped but
    # CONF_LOW_TARIFF_STATES left blank must still succeed; the entry's data holds no
    # CONF_LOW_TARIFF_STATES key (or an empty list -- match whatever _split_data's
    # existing blank-field convention already does for comparable optional string
    # fields, don't invent a new one).
    ...
```

(Follow this file's existing helper pattern for driving the flow to the `mappings` step and
inspecting `result["data"]` — do not restate the whole flow-driving boilerplate here; match the
style of the adjacent `CONF_HOME_DAY_EXTERNAL_ENTITY`/`CONF_NOTIFICATION_TARGET_ENTITY` tests
already in this file.)

**Implementation:** `custom_components/smart_charging/config_flow.py`:

1. Add `CONF_LOW_TARIFF_STATES` to the `from .const import (...)` block.
2. `UNGATED_MAPPING_SCHEMA`: widen the entity selector and add the new field —
   ```python
   vol.Optional(CONF_LOW_TARIFF_ENTITY): _entity(
       ["binary_sensor", "input_boolean", "sensor", "input_select"]
   ),
   vol.Optional(CONF_LOW_TARIFF_STATES): str,
   ```
3. `_split_data`: after building `data`, parse the raw string in place —
   ```python
   if CONF_LOW_TARIFF_STATES in data:
       data[CONF_LOW_TARIFF_STATES] = _parse_states(data[CONF_LOW_TARIFF_STATES])
   ```

**Commit:** `feat: config flow accepts a low-tariff state-translation table (T3, issue #746)`

---

## T4 — Full regression + untouched-code check

1. Run the full suite (`pytest`) — every existing test, in particular every other
   `low_tariff`/`home_day_external` adapter-factory test and every other `mappings`-step
   config-flow test, must pass unchanged.
2. Read `adapters/boolean.py` and confirm it is byte-for-byte unchanged — `BooleanReadAdapter`
   still serves `home_day_external` exactly as before this slice (design doc §1's explicit
   out-of-scope row).
3. Confirm `docs/analysis/entity-catalog.md`'s `low_tariff` row and
   `docs/analysis/system-overview.md`'s `low-tariff flag` term (merged in PR #745) now match the
   shipped behaviour exactly: "does not already report on/off" ↔ T1's native-on/off tests; "every
   other raw state resolving to not-low-tariff" ↔ T1's unlisted-state and empty-list tests.

**Commit:** `test: full regression pass for low-tariff state translation (T4, issue #746)` (only
if this task's own check surfaces something to fix; otherwise fold the confirmation into the PR
description and skip an empty commit).

---

## Traceability

| Task | `system-design.md` service | `project-plan.md` task | Analysis anchor |
| --- | --- | --- | --- |
| T1 | Resource Access, V1 (adapter roles) | RA2 (continuation) | entity-catalog.md `low_tariff` row; PR #745 |
| T2 | Resource Access, V1 | RA2 (continuation) | same |
| T3 | Client, V14 (config flow) | C4 | UC12 steps 7, 9; PR #745 |
| T4 | — (regression) | — | — |
