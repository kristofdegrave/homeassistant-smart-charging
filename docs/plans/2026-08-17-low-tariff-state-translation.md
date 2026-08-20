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

LOW_STATES = "low, off-peak"  # raw comma-separated string, matching config-entry storage (design SS2)


async def test_native_on_returns_true(hass):
    hass.states.async_set("binary_sensor.tariff", STATE_ON)
    adapter = LowTariffReadAdapter(hass, "binary_sensor.tariff", "")
    assert await adapter.read() is True


async def test_native_off_returns_false(hass):
    hass.states.async_set("binary_sensor.tariff", STATE_OFF)
    adapter = LowTariffReadAdapter(hass, "binary_sensor.tariff", "")
    assert await adapter.read() is False


async def test_listed_raw_state_returns_true(hass):
    hass.states.async_set("sensor.tariff", "low")
    adapter = LowTariffReadAdapter(hass, "sensor.tariff", LOW_STATES)
    assert await adapter.read() is True


async def test_unlisted_raw_state_returns_false(hass):
    # Not a fault (unlike StatusReadAdapter's unmapped-state case) -- a deliberate
    # restrictive default for a present-but-unmatched state (entity-catalog.md;
    # design doc SS1), distinct from the glossary's permissive "always active"
    # default for a genuinely unmapped/unavailable signal (design doc SS7).
    hass.states.async_set("sensor.tariff", "high")
    adapter = LowTariffReadAdapter(hass, "sensor.tariff", LOW_STATES)
    assert await adapter.read() is False


async def test_empty_states_string_returns_false_for_non_boolean_state(hass):
    hass.states.async_set("sensor.tariff", "high")
    adapter = LowTariffReadAdapter(hass, "sensor.tariff", "")
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


async def test_native_on_off_takes_precedence_over_low_states(hass):
    # A native on/off entity is never expected to also carry a states list, but the
    # precedence is pinned regardless: on/off wins even if "off" were (oddly) listed.
    hass.states.async_set("binary_sensor.tariff", STATE_OFF)
    adapter = LowTariffReadAdapter(hass, "binary_sensor.tariff", "off")
    assert await adapter.read() is False


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

**File:** `tests/adapters/test_factory.py`. Add `LowTariffReadAdapter` and `CONF_LOW_TARIFF_STATES`
to this file's own import block alongside its existing imports.

1. Update the existing `test_factory_builds_low_tariff_role_when_configured` — it currently
   asserts `isinstance(adapters[ROLE_LOW_TARIFF], BooleanReadAdapter)`; change the assertion to
   `LowTariffReadAdapter` (this makes the test fail against today's `factory.py`, since the
   production branch still builds `BooleanReadAdapter`).
2. Add a new failing test: `test_factory_passes_configured_low_tariff_states`:
   ```python
   async def test_factory_passes_configured_low_tariff_states(hass):
       data = _data()
       data[CONF_LOW_TARIFF_ENTITY] = "sensor.tariff"
       data[CONF_LOW_TARIFF_STATES] = "low, off-peak"
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
`LowTariffReadAdapter` from `.tariff` and `CONF_LOW_TARIFF_STATES` from `.const`, instead of
relying on `BooleanReadAdapter` for this role; change the `CONF_LOW_TARIFF_ENTITY` branch to:

```python
if data.get(CONF_LOW_TARIFF_ENTITY):
    adapters[ROLE_LOW_TARIFF] = LowTariffReadAdapter(
        hass, data[CONF_LOW_TARIFF_ENTITY], data.get(CONF_LOW_TARIFF_STATES, "")
    )
```

`BooleanReadAdapter`'s import and its `home_day_external` branch are untouched.

**Commit:** `feat: factory builds low_tariff via LowTariffReadAdapter (T2, issue #746)`

---

## T3 — Config-flow selector + state-translation field

**Test boundary:** HA harness (config flow is HA-coupled, ADR-0009).

**Files:** `tests/test_config_flow.py`, `tests/test_config_flow_translations.py`,
`tests/test_translations.py` (the latter two are existing suites this task must keep green, not
new files — see Implementation step 4).

Add to the existing ungated `mappings`-step test group in `tests/test_config_flow.py`:

```python
@pytest.mark.parametrize("domain", ["sensor", "select", "input_select"])
async def test_mappings_step_accepts_widened_low_tariff_domains(hass, domain):
    # Widened selector: a sensor/select/input_select tariff signal with a textual
    # state must be selectable, not just binary_sensor/input_boolean.
    ...  # drive the flow to the mappings step, submit
    # CONF_LOW_TARIFF_ENTITY=f"{domain}.tariff" plus CONF_LOW_TARIFF_STATES="low, off-peak";
    # assert the step advances (no vol.Invalid) and the resulting entry's data contains
    # {CONF_LOW_TARIFF_ENTITY: f"{domain}.tariff", CONF_LOW_TARIFF_STATES: "low, off-peak"}
    # -- stored as the raw string, unparsed (design SS2).


async def test_mappings_step_low_tariff_states_optional(hass):
    # Submitting the mappings step with CONF_LOW_TARIFF_ENTITY mapped but
    # CONF_LOW_TARIFF_STATES left blank must still succeed.
    ...


async def test_reconfigure_mappings_step_prefills_low_tariff_states(hass):
    # Issue #499 class: an entry already carrying CONF_LOW_TARIFF_STATES must render
    # it as the mappings step's suggested value on reconfigure, and resubmitting the
    # prefilled form unchanged must not null it out. Model this on
    # test_reconfigure_form_prefills_existing_mappings /
    # test_reconfigure_preserves_unretyped_optional_mappings (this file) -- unlike
    # CONF_CONNECTED_STATES/CONF_CHARGING_STATES, this field has no "known gap"
    # carve-out; it must actually prefill.
    ...


async def test_factory_builds_adapter_matching_flow_submitted_states(hass):
    # Integration checkpoint (design SS4 criterion 7): drive the config flow to
    # produce a real entry with CONF_LOW_TARIFF_ENTITY="sensor.tariff" and
    # CONF_LOW_TARIFF_STATES="low, off-peak", then feed entry.data into
    # build_adapters (adapters/factory.py) and assert the resulting
    # LowTariffReadAdapter's _low_states == {"low", "off-peak"} -- proving the
    # flow's output and the factory's input actually agree, not just each half
    # against hand-built fixtures (T2 already covers the factory in isolation).
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
       ["binary_sensor", "input_boolean", "sensor", "select", "input_select"]
   ),
   vol.Optional(CONF_LOW_TARIFF_STATES): str,
   ```
3. `_split_data` is **not** touched — `CONF_LOW_TARIFF_STATES` is not in `OPTION_KEYS` and not one
   of the two excluded status-translation fields, so it already lands in `data` as the raw
   submitted string by `_split_data`'s existing default behaviour (design SS2's whole point: no
   exclude/derive pair needed).
4. `strings.json`, `translations/en.json`, `translations/nl.json`: add a `low_tariff_states` label
   under `STEP_MAPPINGS`'s field block, alongside the existing `low_tariff_entity` entry
   (`strings.json:68`) — required for `tests/test_config_flow_translations.py` and
   `tests/test_translations.py` to stay green (both discover `UNGATED_MAPPING_SCHEMA`'s field set
   and assert every field has a label in all three files).

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
