# Vehicle-Limit Manager Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the Vehicle-Limit Manager (M2, V12) and its `vehicle_charge_limit` (RA1-VL) +
`car_home` adapter roles — keeping the vehicle's own charge-limit setting synchronised with the active
SOC limit in both directions, with an echo guard, and resetting it to the default on disconnect (UC09,
R6).

**Architecture:** M2 is a Manager at the package root (`vehicle_limit.py`, sibling to
`coordinator.py`), driven by HA state-change listeners on three entities (the mapped `charger_status`
and `vehicle_charge_limit` entities, and `sensor.smart_charging_active_soc_limit`). It reads inputs
through adapters, writes the vehicle through the `vehicle_charge_limit` adapter, and adopts manual
changes by setting the existing `number.smart_charging_soc_limit_override` entity. It never calls or is
called by the Coordinator (system-design §4 rule 5; ADR-0011). Full design:
[`2026-07-21-vehicle-limit-manager-design.md`](2026-07-21-vehicle-limit-manager-design.md).

**Tech Stack:** Python ≥3.12, Home Assistant, `pytest`, `pytest-homeassistant-custom-component` (HA
harness, test-only per ADR-0009), `ruff`. **Every task in this slice is HA-coupled** (adapters, a
Manager, config flow, setup) → **all tests use the HA harness**; there is no pure-logic (`modes/`,
`engines/`) module here (design §10).

**Model:** Per CLAUDE.md, this is development work — execute on **Sonnet**.

---

## Read first: the E3/M1 dependency (design §0)

The **System→vehicle write branch (Task 4.x)** consumes the `ActiveSocLimitChanged` domain event via
the `sensor.smart_charging_active_soc_limit` entity, which **E3/M1 do not build yet** (epic #255, open).
This slice does **not** build that sensor or event. Task 4.x is written and tested **against a
simulated `sensor.smart_charging_active_soc_limit` state** in the HA harness, and is **dormant in
production** until E3/M1 land. The other two branches (manual adoption, disconnect reset) depend on
nothing from E3/M1 and are fully functional on ship. Do not attempt to make the coordinator publish the
event as part of this slice — that is out of scope (design §8).

---

## Conventions used throughout

Same as `2026-07-20-captar.md`'s conventions section (package root, tests-mirror-1:1, canonical charger
states from `const.py`, engine/adapter purity boundaries, ADR-0009 harness split, commit-after-green).
**Branch:** this plan document lives on `docs/276`; the implementation commits it describes land on a
`dev/276`-style implementation branch. Re-check `git branch --show-current` before every commit
(shared checkout — a concurrent session can switch HEAD). Additionally:

- **Named constants, no magic strings** (CLAUDE.md): every new role key, config key, HA event type, and
  entity id is a `const.py` constant, referenced by name in code and tests.
- **`git commit --author="Claude <noreply@anthropic.com>"`** with the trailer
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` (per CLAUDE.md's commit convention for the
  implementer model).
- Test docstrings name the **UC09 step / R6 acceptance criterion** they anchor to (traceability).

---

## Phase 0 — Constants (foundation for every later task)

### Task 0.1: Add the role keys, config keys, event types, and the subscribed entity id

**ADR honored:** ADR-0003 (role keys), ADR-0005 (data vs options — these are all *data*/identifiers, no
new options), ADR-0011 (the subscribed entity id + event names). **Test boundary:** none of its own
(constants only); exercised by every later task.

**Files:**
- Modify: `custom_components/smart_charging/const.py`

**Step 1: Append to `const.py`**

```python
# Adapter role keys (RA1-VL + the car_home RA2 role, built early — M2 is their first consumer).
ROLE_VEHICLE_CHARGE_LIMIT = "vehicle_charge_limit"
ROLE_CAR_HOME = "car_home"

# --- Config entry DATA additions (ADR-0005 — hardware-role mappings are reconfigure-only) ---
CONF_VEHICLE_CHARGE_LIMIT_ENTITY = "vehicle_charge_limit_entity"  # optional (UC09 precondition)
CONF_CAR_HOME_ENTITY = "car_home_entity"  # required when vehicle_charge_limit is mapped (design §9.1)

# Entity M2 subscribes to for the resolved-active-SOC-limit change (ADR-0011). NOT built by this
# slice — materialized by E3/M1 (epic #255); M2's write branch is dormant until it exists (design §0).
ACTIVE_SOC_LIMIT_ENTITY = "sensor.smart_charging_active_soc_limit"

# Domain events M2 fires on the HA event bus (UC09 "Domain events produced"; DDD→HA mapping). Not
# consumed by any other Manager (ADR-0011) — observability/automation only.
EVENT_VEHICLE_CHARGE_LIMIT_SYNCED = "smart_charging_vehicle_charge_limit_synced"
EVENT_MANUAL_CHARGE_LIMIT_ADOPTED = "smart_charging_manual_charge_limit_adopted"
EVENT_VEHICLE_CHARGE_LIMIT_RESET = "smart_charging_vehicle_charge_limit_reset"
```

**Step 2: Commit**

```bash
git add custom_components/smart_charging/const.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add vehicle-limit role/config/event constants (M2)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Phase 1 — Resource Access (RA1-VL + car_home)

### Task 1.1: `PresenceReadAdapter` — the `car_home` role

**ADR honored:** ADR-0003 (one adapter per role, `Adapter` protocol). **Test boundary:** HA harness
(adapters read HA state), `tests/adapters/`.

**Files:**
- Create: `custom_components/smart_charging/adapters/presence.py`
- Test: `tests/adapters/test_presence.py`

**Step 1: Write the failing tests**

```python
"""HA-harness tests for the presence (car_home) read adapter (RA2 role, ADR-0003)."""

from custom_components.smart_charging.adapters.presence import PresenceReadAdapter


async def test_home_states_read_true(hass):
    hass.states.async_set("device_tracker.car", "home")
    assert await PresenceReadAdapter(hass, "device_tracker.car").read() is True
    hass.states.async_set("binary_sensor.car_home", "on")
    assert await PresenceReadAdapter(hass, "binary_sensor.car_home").read() is True


async def test_away_states_read_false(hass):
    hass.states.async_set("device_tracker.car", "not_home")
    assert await PresenceReadAdapter(hass, "device_tracker.car").read() is False
    hass.states.async_set("binary_sensor.car_home", "off")
    assert await PresenceReadAdapter(hass, "binary_sensor.car_home").read() is False


async def test_missing_or_unavailable_reads_none(hass):
    assert await PresenceReadAdapter(hass, "device_tracker.absent").read() is None
    hass.states.async_set("device_tracker.car", "unavailable")
    assert await PresenceReadAdapter(hass, "device_tracker.car").read() is None


async def test_write_is_not_supported(hass):
    import pytest

    with pytest.raises(NotImplementedError):
        await PresenceReadAdapter(hass, "device_tracker.car").write(True)
```

**Step 2: Run to verify failure**

Run: `pytest tests/adapters/test_presence.py -v`
Expected: FAIL — `ModuleNotFoundError: ...adapters.presence`.

**Step 3: Write the minimal implementation**

```python
"""Presence (car_home) read adapter: maps a presence entity's state to a bool (ADR-0003)."""

from homeassistant.const import STATE_HOME, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

_HOME_STATES = (STATE_HOME, STATE_ON)


class PresenceReadAdapter:
    """Reads a presence/device_tracker/binary_sensor entity as car-at-home (True/False).

    None when the entity is missing/unavailable/unknown — for this role that is not the
    ADR-0007 fault path (M2 is outside the control cycle); the Manager treats None as
    "cannot confirm presence" and suppresses a System write (design §9.1 alternative).
    """

    def __init__(self, hass: HomeAssistant, entity_id: str) -> None:
        self._hass = hass
        self._entity_id = entity_id

    async def read(self) -> bool | None:
        state = self._hass.states.get(self._entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        return state.state in _HOME_STATES

    async def write(self, value: bool) -> None:
        raise NotImplementedError("car_home is read-only")
```

**Step 4: Run to verify pass**

Run: `pytest tests/adapters/test_presence.py -v` → Expected: PASS.

**Step 5: Commit**

```bash
git add custom_components/smart_charging/adapters/presence.py tests/adapters/test_presence.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add presence (car_home) read adapter (RA2 role)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

### Task 1.2: Factory builds `vehicle_charge_limit` (RA1-VL) and `car_home`, both optional

**ADR honored:** ADR-0003 (config-driven factory). **Test boundary:** HA harness,
`tests/adapters/test_factory.py`.

**Files:**
- Modify: `custom_components/smart_charging/adapters/factory.py`
- Test: `tests/adapters/test_factory.py`

**Step 1: Write the failing tests** (append to the existing suite; `_data()` is the module's existing
minimal-valid-data helper)

```python
from custom_components.smart_charging.const import (
    CONF_CAR_HOME_ENTITY,
    CONF_VEHICLE_CHARGE_LIMIT_ENTITY,
    ROLE_CAR_HOME,
    ROLE_VEHICLE_CHARGE_LIMIT,
)
from custom_components.smart_charging.adapters.numeric import NumericReadWriteAdapter
from custom_components.smart_charging.adapters.presence import PresenceReadAdapter


async def test_factory_builds_vehicle_charge_limit_and_car_home_when_mapped(hass):
    data = _data()
    data[CONF_VEHICLE_CHARGE_LIMIT_ENTITY] = "number.car_charge_limit"
    data[CONF_CAR_HOME_ENTITY] = "device_tracker.car"
    adapters = build_adapters(hass, data)
    assert isinstance(adapters[ROLE_VEHICLE_CHARGE_LIMIT], NumericReadWriteAdapter)
    assert isinstance(adapters[ROLE_CAR_HOME], PresenceReadAdapter)


async def test_vehicle_charge_limit_and_car_home_absent_when_not_mapped(hass):
    adapters = build_adapters(hass, _data())
    assert ROLE_VEHICLE_CHARGE_LIMIT not in adapters
    assert ROLE_CAR_HOME not in adapters
```

**Step 2: Run** → FAIL (`KeyError`/constants unused yet).

**Step 3: Implement** — add the two imports and, after the `ev_soc` block in `build_adapters`:

```python
if data.get(CONF_VEHICLE_CHARGE_LIMIT_ENTITY):
    adapters[ROLE_VEHICLE_CHARGE_LIMIT] = NumericReadWriteAdapter(
        hass, data[CONF_VEHICLE_CHARGE_LIMIT_ENTITY]
    )
if data.get(CONF_CAR_HOME_ENTITY):
    adapters[ROLE_CAR_HOME] = PresenceReadAdapter(hass, data[CONF_CAR_HOME_ENTITY])
```

(Import `PresenceReadAdapter` from `.presence` and the four constants from `..const`.)

**Step 4: Run** → PASS.

**Step 5: Commit**

```bash
git add custom_components/smart_charging/adapters/factory.py tests/adapters/test_factory.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: factory builds vehicle_charge_limit (RA1-VL) + car_home roles

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

> **⎔ Phase 1 checkpoint:** `pytest tests/adapters -v` green; the two roles are reachable through the
> factory only when mapped (design §4).

---

## Phase 2 — Config flow (the two data fields + the C2 guard)

### Task 2.1: Add the mapping fields and the `car_home`-required-when-`vehicle_charge_limit`-mapped guard

**ADR honored:** ADR-0005 (data bucket for hardware mappings), ADR-0003. **Test boundary:** HA harness,
`tests/test_config_flow.py`.

**Files:**
- Modify: `custom_components/smart_charging/config_flow.py`
- Test: `tests/test_config_flow.py`

**Step 1: Write the failing tests** (use the suite's existing user-flow helper; names below mirror the
CapTar suite's `_run_user_flow` shape — adapt to the actual helper in the file)

```python
from homeassistant.data_entry_flow import FlowResultType

from custom_components.smart_charging.const import (
    CONF_CAR_HOME_ENTITY,
    CONF_VEHICLE_CHARGE_LIMIT_ENTITY,
)


async def test_vehicle_limit_mapped_without_car_home_is_rejected(hass):
    """UC09 C2 / design §9.1: a vehicle-limit output with no presence source is unsafe."""
    result = await _run_user_flow(
        hass, overrides={CONF_VEHICLE_CHARGE_LIMIT_ENTITY: "number.car_limit"}
    )  # car_home omitted
    assert result["type"] == FlowResultType.FORM
    assert result["errors"][CONF_CAR_HOME_ENTITY] == "required_when_vehicle_limit_mapped"


async def test_vehicle_limit_mapped_with_car_home_is_accepted(hass):
    result = await _run_user_flow(
        hass,
        overrides={
            CONF_VEHICLE_CHARGE_LIMIT_ENTITY: "number.car_limit",
            CONF_CAR_HOME_ENTITY: "device_tracker.car",
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_VEHICLE_CHARGE_LIMIT_ENTITY] == "number.car_limit"
    assert result["data"][CONF_CAR_HOME_ENTITY] == "device_tracker.car"


async def test_neither_vehicle_limit_nor_car_home_is_accepted(hass):
    """UC09 precondition: unmapped vehicle limit → M2 inert, no requirement on car_home."""
    result = await _run_user_flow(hass)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert CONF_VEHICLE_CHARGE_LIMIT_ENTITY not in result["data"]
    assert CONF_CAR_HOME_ENTITY not in result["data"]


async def test_pre_field_entry_reads_keys_as_absent(hass):
    """An entry created before these fields must not KeyError — no migration needed (design §8)."""
    entry = MockConfigEntry(domain=DOMAIN, data=_data(), options=_options())
    assert entry.data.get(CONF_VEHICLE_CHARGE_LIMIT_ENTITY) is None
    assert entry.data.get(CONF_CAR_HOME_ENTITY) is None
```

**Step 2: Run** → FAIL (fields/guard don't exist).

**Step 3: Implement**

- In `MAPPING_SCHEMA`, add two optional entity fields:

```python
vol.Optional(CONF_VEHICLE_CHARGE_LIMIT_ENTITY): _entity("number"),
vol.Optional(CONF_CAR_HOME_ENTITY): _entity(["device_tracker", "person", "binary_sensor"]),
```

- Add a guard helper mirroring `_ev_soc_missing_error`, and call it alongside that one in **both**
  `async_step_user` and `async_step_reconfigure` (so mapping through either path is validated the same):

```python
def _car_home_missing_error(user_input: dict) -> dict[str, str] | None:
    """UC09 C2 / design §9.1: mapping vehicle_charge_limit requires car_home — the
    home-only write gate is not optional. Unmapped vehicle limit imposes no requirement."""
    if user_input.get(CONF_VEHICLE_CHARGE_LIMIT_ENTITY) and not user_input.get(
        CONF_CAR_HOME_ENTITY
    ):
        return {CONF_CAR_HOME_ENTITY: "required_when_vehicle_limit_mapped"}
    return None
```

  Combine with the existing error dict (e.g. `errors = _ev_soc_missing_error(user_input) or {}` then
  `errors.update(_car_home_missing_error(user_input) or {})`, showing the form if `errors` is non-empty).
  Import the two new constants. No `OPTION_KEYS` change (both fields are data, folded into the data
  bucket by the existing `_split_data`, which already keeps any non-option, non-state key).

**Step 4: Run** → PASS.

**Step 5: Commit**

```bash
git add custom_components/smart_charging/config_flow.py tests/test_config_flow.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: config flow maps vehicle_charge_limit + car_home with the C2 guard

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

> **⎔ Phase 2 checkpoint:** the flow rejects a vehicle-limit mapping without `car_home`, accepts both
> or neither, and an entry predating the fields reads them as absent (no migration).

---

## Phase 3 — The Vehicle-Limit Manager (M2), fully-functional branches first

M2 lives in a new root module `vehicle_limit.py` (design §9.4). Build its two E3/M1-independent
branches (adoption, disconnect reset) and the echo guard **first** — they ship working; the dormant
System→vehicle branch follows in Phase 4. Each task drives M2 through its **public reaction methods**
in the HA harness (not by faking HA listener plumbing — that is Phase 5's job); tests construct M2 with
a small adapter map and call the reaction directly.

### Task 3.1: M2 skeleton + the echo-guard state

**ADR honored:** system-design §4 rule 5 / ADR-0011 (Manager, no M1 coupling). **Test boundary:** HA
harness, `tests/test_vehicle_limit.py`.

**Files:**
- Create: `custom_components/smart_charging/vehicle_limit.py`
- Test: `tests/test_vehicle_limit.py`

**Step 1: Write the failing test**

```python
"""HA-harness tests for the Vehicle-Limit Manager (M2 — UC09/R6/ADR-0011)."""

from custom_components.smart_charging.const import (
    ROLE_CAR_HOME,
    ROLE_CHARGER_STATUS,
    ROLE_VEHICLE_CHARGE_LIMIT,
    STATE_CONNECTED,
    STATE_DISCONNECTED,
)
from custom_components.smart_charging.vehicle_limit import VehicleLimitManager


class _RWAdapter:
    def __init__(self, value=None):
        self.value = value
        self.writes = []

    async def read(self):
        return self.value

    async def write(self, value):
        self.writes.append(value)
        self.value = value


class _ReadAdapter:
    def __init__(self, value):
        self.value = value

    async def read(self):
        return self.value


def _manager(hass, *, vehicle=80.0, home=True, status=STATE_CONNECTED, soc_override=80.0):
    adapters = {
        ROLE_VEHICLE_CHARGE_LIMIT: _RWAdapter(vehicle),
        ROLE_CAR_HOME: _ReadAdapter(home),
        ROLE_CHARGER_STATUS: _ReadAdapter(status),
    }
    return VehicleLimitManager(
        hass, adapters=adapters, entry_id="abc", get_default_soc_limit=lambda: soc_override
    )


async def test_manager_starts_with_no_recorded_write(hass):
    m = _manager(hass)
    assert m._last_written_limit is None  # echo guard initialises empty (design §6)
```

**Step 2: Run** → FAIL (`ImportError`).

**Step 3: Implement** the skeleton:

```python
"""Vehicle-Limit Manager (M2, V12) — bidirectional vehicle charge-limit sync (UC09/R6).

A Manager (system-design §4 rule 5 / ADR-0011): triggered by HA state changes and the
ActiveSocLimitChanged event, it reads inputs through adapters and writes the vehicle
through the vehicle_charge_limit adapter / adopts manual changes into
number.smart_charging_soc_limit_override. It NEVER calls or is called by the Coordinator.
No control-cycle logic, no clamps, no set-point — see design 2026-07-21-vehicle-limit-manager.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from homeassistant.core import HomeAssistant

from .const import (
    CHARGEABLE_STATES,
    EVENT_MANUAL_CHARGE_LIMIT_ADOPTED,
    EVENT_VEHICLE_CHARGE_LIMIT_RESET,
    EVENT_VEHICLE_CHARGE_LIMIT_SYNCED,
    ROLE_CAR_HOME,
    ROLE_CHARGER_STATUS,
    ROLE_VEHICLE_CHARGE_LIMIT,
    STATE_DISCONNECTED,
)

_LOGGER = logging.getLogger(__name__)

# The number entity's own range (R6 AC 1) — adoption clamps into it.
_SOC_MIN, _SOC_MAX = 50.0, 100.0


class VehicleLimitManager:
    def __init__(
        self,
        hass: HomeAssistant,
        *,
        adapters: dict,
        entry_id: str,
        get_default_soc_limit: Callable[[], float],
        set_default_soc_limit: Callable[[float], None] | None = None,
    ) -> None:
        self._hass = hass
        self._adapters = adapters
        self._entry_id = entry_id
        self._get_default_soc_limit = get_default_soc_limit
        self._set_default_soc_limit = set_default_soc_limit
        self._last_written_limit: float | None = None
        self._last_status: str | None = None
```

**Step 4: Run** → PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/vehicle_limit.py tests/test_vehicle_limit.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add Vehicle-Limit Manager (M2) skeleton + echo-guard state

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

### Task 3.2: Disconnect reset (UC09 steps 7–8, R6 AC 3)

**ADR honored:** ADR-0011 (charger_status disconnect is adapter-observed, re-derived — no event).
**Test boundary:** HA harness.

**Step 1: Write the failing tests**

```python
async def test_disconnect_from_connected_resets_vehicle_to_default(hass):
    """UC09 step 8 / R6 AC 3: connected→disconnected writes the default (80%) to the vehicle."""
    m = _manager(hass, vehicle=65.0, soc_override=80.0)
    m._last_status = STATE_CONNECTED
    events = _capture(hass, "smart_charging_vehicle_charge_limit_reset")
    await m.on_status_changed(STATE_DISCONNECTED)
    assert m._adapters[ROLE_VEHICLE_CHARGE_LIMIT].writes == [80.0]
    assert m._last_written_limit == 80.0  # recorded for the echo guard
    assert len(events) == 1


async def test_disconnected_non_edge_is_a_noop(hass):
    """No prior connected status → no reset (design §5.3 edge detection)."""
    m = _manager(hass, vehicle=65.0)
    m._last_status = STATE_DISCONNECTED
    await m.on_status_changed(STATE_DISCONNECTED)
    assert m._adapters[ROLE_VEHICLE_CHARGE_LIMIT].writes == []


async def test_reset_write_failure_is_swallowed(hass):
    """A just-unplugged vehicle may be unreachable — best-effort write (design §5.3)."""
    m = _manager(hass)
    m._last_status = STATE_CONNECTED

    async def _boom(_value):
        raise RuntimeError("vehicle offline")

    m._adapters[ROLE_VEHICLE_CHARGE_LIMIT].write = _boom
    await m.on_status_changed(STATE_DISCONNECTED)  # must not raise
```

(`_capture` = a small helper subscribing to an HA event type and appending fired events; define once at
the top of the test module.)

**Step 2: Run** → FAIL (`AttributeError: on_status_changed`).

**Step 3: Implement**

```python
async def on_status_changed(self, status: str | None) -> None:
    """React to a canonical charger-status change (design §5.3). Disconnect edge → reset."""
    was_connected = self._last_status in CHARGEABLE_STATES
    self._last_status = status
    if status == STATE_DISCONNECTED and was_connected:
        await self._reset_to_default()

async def _reset_to_default(self) -> None:
    default = float(self._get_default_soc_limit())
    if await self._write_vehicle(default):
        self._fire(EVENT_VEHICLE_CHARGE_LIMIT_RESET, default)

async def _write_vehicle(self, value: float) -> bool:
    """Best-effort write to the vehicle; records the value for the echo guard. Returns success."""
    adapter = self._adapters.get(ROLE_VEHICLE_CHARGE_LIMIT)
    if adapter is None:
        return False
    try:
        await adapter.write(value)
    except Exception as err:  # noqa: BLE001 - a just-unplugged vehicle may be unreachable (§5.3)
        _LOGGER.debug("vehicle_charge_limit write failed: %s", err)
        return False
    self._last_written_limit = value
    return True

def _fire(self, event_type: str, limit: float) -> None:
    self._hass.bus.async_fire(event_type, {"entry_id": self._entry_id, "limit": limit})
```

**Step 4: Run** → PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/vehicle_limit.py tests/test_vehicle_limit.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: M2 disconnect reset to default SOC limit (UC09 steps 7-8)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

### Task 3.3: Vehicle→System manual adoption + echo guard (UC09 steps 4–6, exception flow; R6 AC 5)

**ADR honored:** ADR-0011 (vehicle_charge_limit change is adapter-observed, re-derived — the echo guard,
not an event); ADR-0004 (writes the native `number.smart_charging_soc_limit_override`). **Test
boundary:** HA harness.

**Step 1: Write the failing tests**

```python
async def test_manual_change_is_adopted_as_default(hass):
    """UC09 step 5 / R6 AC 5: a vehicle-side value ≠ our last write → set soc_limit_override."""
    adopted = []
    m = _manager(hass)
    m._set_default_soc_limit = adopted.append
    events = _capture(hass, "smart_charging_manual_charge_limit_adopted")
    await m.on_vehicle_limit_changed(70.0)  # user set 70% on the car
    assert adopted == [70.0]
    assert len(events) == 1


async def test_echo_of_own_write_is_ignored(hass):
    """UC09 exception flow / R6 AC (echo guard): a report equal to our last write → no adoption."""
    adopted = []
    m = _manager(hass)
    m._set_default_soc_limit = adopted.append
    m._last_written_limit = 80.0  # we just wrote 80
    await m.on_vehicle_limit_changed(80.0)  # the vehicle reflects it back
    assert adopted == []


async def test_manual_change_adopted_even_when_away(hass):
    """UC09 alt 5a: C2 gates only System→vehicle writes, never read+adopt."""
    adopted = []
    m = _manager(hass, home=False)
    m._set_default_soc_limit = adopted.append
    await m.on_vehicle_limit_changed(60.0)
    assert adopted == [60.0]


async def test_adoption_clamps_into_the_number_range(hass):
    """R6 AC 1: the default SOC limit lives in 50–100."""
    adopted = []
    m = _manager(hass)
    m._set_default_soc_limit = adopted.append
    await m.on_vehicle_limit_changed(120.0)
    assert adopted == [100.0]


async def test_none_report_is_ignored(hass):
    """A missing/unavailable vehicle read is not a manual change (design §4/§5)."""
    adopted = []
    m = _manager(hass)
    m._set_default_soc_limit = adopted.append
    await m.on_vehicle_limit_changed(None)
    assert adopted == []
```

**Step 2: Run** → FAIL (`AttributeError: on_vehicle_limit_changed`).

**Step 3: Implement**

```python
async def on_vehicle_limit_changed(self, reported: float | None) -> None:
    """React to a vehicle-side charge-limit change (design §5.2). Adopt unless it is our echo."""
    if reported is None:
        return
    if self._last_written_limit is not None and reported == self._last_written_limit:
        return  # our own write reflecting back — echo guard (design §6)
    adopted = min(max(float(reported), _SOC_MIN), _SOC_MAX)  # R6 AC 1 range
    if self._set_default_soc_limit is not None:
        self._set_default_soc_limit(adopted)
    self._fire(EVENT_MANUAL_CHARGE_LIMIT_ADOPTED, adopted)
```

(`_set_default_soc_limit` is wired at setup, Phase 5, to set the `SocLimitOverrideNumber` entity /
`coordinator.soc_limit_override`; in tests it is a spy.)

**Step 4: Run** → PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/vehicle_limit.py tests/test_vehicle_limit.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: M2 manual-change adoption with echo guard (UC09 steps 4-6)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

> **⎔ Phase 3 checkpoint:** `pytest tests/test_vehicle_limit.py -v` green; the two E3/M1-independent
> branches (adoption + disconnect reset) and the echo guard all work; no import of `coordinator` in
> `vehicle_limit.py` (grep-assert — ADR-0011 no cross-Manager call).

---

## Phase 4 — System→vehicle write branch (dormant until E3/M1; design §0)

### Task 4.1: Write the resolved active SOC limit to the vehicle, gated by C2

**ADR honored:** ADR-0011 (M2 reads the materialized `sensor.smart_charging_active_soc_limit` rather
than recomputing — Option B rejected); UC09 C2 home-only gate. **Test boundary:** HA harness, driven by
a **simulated** `sensor.smart_charging_active_soc_limit` state.

**Step 1: Write the failing tests**

```python
from custom_components.smart_charging.const import ACTIVE_SOC_LIMIT_ENTITY, STATE_CHARGING


async def test_soc_limit_change_writes_vehicle_when_connected_at_home(hass):
    """UC09 step 2 / R6 AC 2: connected + at home → write the new limit + sync event."""
    m = _manager(hass, home=True, status=STATE_CHARGING)
    events = _capture(hass, "smart_charging_vehicle_charge_limit_synced")
    await m.on_active_soc_limit_changed(90.0)
    assert m._adapters[ROLE_VEHICLE_CHARGE_LIMIT].writes == [90.0]
    assert m._last_written_limit == 90.0
    assert len(events) == 1


async def test_no_write_when_away(hass):
    """UC09 alt 2a / R6 AC 4: away → no System write to the vehicle (C2)."""
    m = _manager(hass, home=False, status=STATE_CHARGING)
    await m.on_active_soc_limit_changed(90.0)
    assert m._adapters[ROLE_VEHICLE_CHARGE_LIMIT].writes == []


async def test_no_write_when_disconnected(hass):
    m = _manager(hass, home=True, status=STATE_DISCONNECTED)
    await m.on_active_soc_limit_changed(90.0)
    assert m._adapters[ROLE_VEHICLE_CHARGE_LIMIT].writes == []


async def test_write_then_reflect_back_settles_without_a_second_write(hass):
    """UC09 exception flow: §5.1 write → vehicle echoes → §5.2 echo guard suppresses re-adoption."""
    adopted = []
    m = _manager(hass, home=True, status=STATE_CHARGING)
    m._set_default_soc_limit = adopted.append
    await m.on_active_soc_limit_changed(90.0)          # System write records 90
    await m.on_vehicle_limit_changed(90.0)             # vehicle reflects 90 back
    assert adopted == []                               # not re-adopted
    assert m._adapters[ROLE_VEHICLE_CHARGE_LIMIT].writes == [90.0]  # no second write
```

**Step 2: Run** → FAIL (`AttributeError: on_active_soc_limit_changed`).

**Step 3: Implement**

```python
async def on_active_soc_limit_changed(self, new_limit: float | None) -> None:
    """React to ActiveSocLimitChanged (design §5.1). Write to the vehicle iff connected AND
    at home (C2). new_limit is read from sensor.smart_charging_active_soc_limit by the listener
    (Phase 5) — E3/M1 materialize that entity; until then this simply never fires (design §0)."""
    if new_limit is None:
        return
    status = self._adapters[ROLE_CHARGER_STATUS] if ROLE_CHARGER_STATUS in self._adapters else None
    canonical = await status.read() if status is not None else None
    if canonical not in CHARGEABLE_STATES:
        return
    car_home = self._adapters.get(ROLE_CAR_HOME)
    if car_home is None or (await car_home.read()) is not True:  # C2 — None ⇒ cannot confirm home
        return
    if await self._write_vehicle(float(new_limit)):
        self._fire(EVENT_VEHICLE_CHARGE_LIMIT_SYNCED, float(new_limit))
```

**Step 4: Run** → PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/vehicle_limit.py tests/test_vehicle_limit.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: M2 System->vehicle write on SOC-limit change, C2-gated (UC09 step 2)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

> **⎔ Phase 4 checkpoint:** all three UC09 branches pass in the harness; the reflect-back settles
> without oscillation; the write branch is proven against a simulated `sensor.smart_charging_active_soc_limit`
> (dormant in production until E3/M1 build it — design §0).

---

## Phase 5 — Setup wiring (listeners, only for mapped roles)

### Task 5.1: Construct M2 and register its state-change listeners at `async_setup_entry`

**ADR honored:** ADR-0008 (listeners live only while the entry is loaded → reload re-registers).
**Test boundary:** HA harness, `tests/test_init.py`.

**Files:**
- Modify: `custom_components/smart_charging/__init__.py`
- Modify: `custom_components/smart_charging/vehicle_limit.py` (a `register_listeners` helper)
- Test: `tests/test_init.py`

**Step 1: Write the failing tests**

```python
async def test_m2_listeners_registered_when_vehicle_limit_mapped(hass):
    """Setup constructs M2 and tracks the mapped vehicle + status + active-soc-limit entities."""
    entry = await _setup_entry(hass, extra_data={
        CONF_VEHICLE_CHARGE_LIMIT_ENTITY: "number.car_limit",
        CONF_CAR_HOME_ENTITY: "device_tracker.car",
    })
    m = hass.data[DOMAIN][entry.entry_id]["vehicle_limit_manager"]
    assert m is not None
    # Driving the underlying vehicle entity reaches the manager and adopts the change:
    events = _capture(hass, "smart_charging_manual_charge_limit_adopted")
    hass.states.async_set("number.car_limit", "55")
    await hass.async_block_till_done()
    assert len(events) == 1  # the vehicle listener fired M2's adoption branch
    assert hass.states.get("number.smart_charging_soc_limit_override").state == "55.0"


async def test_no_m2_when_vehicle_limit_unmapped(hass):
    entry = await _setup_entry(hass)  # no vehicle_charge_limit mapping
    assert hass.data[DOMAIN][entry.entry_id].get("vehicle_limit_manager") is None
```

**Step 2: Run** → FAIL.

**Step 3: Implement**

- In `vehicle_limit.py`, add a method that wires the three listeners and returns their unsub callables,
  reading the *underlying mapped entity ids* from config-entry data and `ACTIVE_SOC_LIMIT_ENTITY`:

```python
from homeassistant.helpers.event import async_track_state_change_event

def register_listeners(self, *, vehicle_entity_id, status_entity_id):
    """Wire M2's three triggers (design §5.4). Returns a list of unsub callables.
    Only called when vehicle_charge_limit is mapped (setup gates on that)."""
    unsubs = []
    async def _vehicle(event):
        # NF3/ADR-0003 (design §5.2): external state crosses its adapter — read the vehicle
        # value THROUGH the adapter, not by parsing event.new_state.state, so the adapter's
        # numeric-coercion/None semantics are the single source of truth (mirrors _status below).
        await self.on_vehicle_limit_changed(
            await self._adapters[ROLE_VEHICLE_CHARGE_LIMIT].read()
        )
    async def _status(event):
        await self.on_status_changed(await self._adapters[ROLE_CHARGER_STATUS].read())
    async def _active(event):
        # sensor.smart_charging_active_soc_limit is an owned diagnostic entity (E3/M1), NOT a
        # hardware adapter role, so it has no adapter to read through — parse its state directly.
        await self.on_active_soc_limit_changed(_num(event))
    unsubs.append(async_track_state_change_event(self._hass, [vehicle_entity_id], _vehicle))
    unsubs.append(async_track_state_change_event(self._hass, [status_entity_id], _status))
    unsubs.append(
        async_track_state_change_event(self._hass, [ACTIVE_SOC_LIMIT_ENTITY], _active)
    )
    return unsubs
```

  (`_num` = parse the event's `new_state.state` to float or None — a tiny module helper, used only for
  the owned `active_soc_limit` diagnostic entity, which has no adapter. The two hardware-backed roles
  (`vehicle_charge_limit`, `charger_status`) are read through their adapters.)

- In `__init__.py`'s `async_setup_entry`, **after** platforms are set up (so `SocLimitOverrideNumber`
  exists to adopt into): if `entry.data.get(CONF_VEHICLE_CHARGE_LIMIT_ENTITY)`, construct
  `VehicleLimitManager` with `get_default_soc_limit=lambda: coordinator.soc_limit_override` and
  `set_default_soc_limit` wired to **call the `number.set_value` service on
  `number.smart_charging_soc_limit_override`** — the same service path the adapter uses for external
  `number` entities. This is the correct target because `SocLimitOverrideNumber` is a `RestoreNumber`
  (`number.py`): setting only `coordinator.soc_limit_override` would leave the entity's `native_value`
  stale, and on the next restart `RestoreNumber` would restore the pre-adoption value and overwrite the
  coordinator — losing the adopted default and violating UC09 step 6 ("future writes use the newly
  adopted default until the user changes it again"). Routing through `number.set_value` updates
  `native_value`, seeds the coordinator via the entity's own `async_set_native_value`, and persists
  ha_state in one path. (Do **not** try to hold the `SocLimitOverrideNumber` object from the entity
  registry — the registry yields an `entity_id`, not the instance.) Register listeners, and register
  each unsub via `entry.async_on_unload(unsub)` so unload/reload tears them down (ADR-0008). Store the
  manager under `hass.data[DOMAIN][entry.entry_id]["vehicle_limit_manager"]` (or `None` when unmapped).

**Step 4: Run** → PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/__init__.py custom_components/smart_charging/vehicle_limit.py tests/test_init.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: wire M2 + its state-change listeners at setup (mapped roles only)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

### Task 5.2: Translations / strings / README

**ADR honored:** none (surface text). **Test boundary:** hassfest validation.

**Files:**
- Modify: `custom_components/smart_charging/strings.json` + `translations/en.json` (labels for the two
  new config fields; the `required_when_vehicle_limit_mapped` error string)
- Modify: `README.md` (Configuration table: add the vehicle charge-limit + car-home mappings; note UC09
  vehicle-limit sync as a feature, with the E3/M1 dependency for the write branch called out)

**Step 1:** Run `python -m script.hassfest` (or the project validation task) → strings complete.
**Step 2: Commit**

```bash
git add custom_components/smart_charging/strings.json custom_components/smart_charging/translations/en.json README.md
git commit --author="Claude <noreply@anthropic.com>" -m "docs: strings + README for vehicle-limit sync (UC09)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

> **⎔ Phase 5 / slice checkpoint:** `ruff check . && ruff format --check . && pytest -q` all green;
> hassfest passes; on a manual HA install with `vehicle_charge_limit` + `car_home` mapped, a manual
> change on the car adopts into the default SOC limit, and unplugging resets the vehicle to the default;
> the System→vehicle write branch is present and correct but stays dormant until E3/M1 materialize
> `sensor.smart_charging_active_soc_limit` (tracked as the follow-up in design §8).

---

## Traceability summary (self-check)

| UC09 / R6 | Task |
| --- | --- |
| R6 AC 2 (write active limit while connected at home) | 4.1 |
| R6 AC 3 (reset to default on disconnect) | 3.2 |
| R6 AC 4 / C2 (never write while away) | 4.1, 2.1 |
| R6 AC 5 (adopt manual change) | 3.3 |
| R6 AC 1 (default 50–100, 80%) | 3.3 (clamp), reuses existing `soc_limit_override` |
| Echo guard (UC09 exception flow) | 3.3, 4.1 |
| UC09 precondition (unmapped → inert) | 1.2, 2.1, 5.1 |
| ADR-0011 (read materialized entity, no M1 call) | 4.1, 3.x (grep-assert) |
| ADR-0003 (RA1-VL + car_home adapters) | 1.1, 1.2 |
| ADR-0005 (data-bucket mappings) | 0.1, 2.1 |
| ADR-0008 (reload re-registers listeners) | 5.1 |

**Every task uses the HA harness** (ADR-0009) — M2 and all its adapters/config/setup are HA-coupled;
there is no pure-logic module in this slice, so no plain-pytest suite. The E3/M1 dependency (design §0)
gates only Task 4.1's *production* effect, never this plan's delivery.
