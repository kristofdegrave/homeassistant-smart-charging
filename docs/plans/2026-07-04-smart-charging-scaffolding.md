# Smart Charging Integration Scaffolding — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Scaffold the `smart_charging` HACS integration in `custom_components/smart_charging/`:
config flow with entity-role mapping, the adapter layer, the coordinator control-cycle pipeline,
the five mode modules, the `Manual` profile, and the integration's owned entities — with a
`pytest-homeassistant-custom-component` test suite that traces back to requirement IDs.

**Architecture:** Follows `docs/plans/2026-07-04-integration-architecture-design.md`: config-flow
entity mapping + a Python adapter layer (no synthetic proxy entities), integration-owned
control/diagnostic entities, config-entry `data` (mappings, capabilities) vs `options`
(thresholds, control interval), and a `DataUpdateCoordinator` driving `control-cycle.md`'s
eight-step pipeline.

**Tech stack:** Python (Home Assistant custom component conventions), `pytest` +
`pytest-homeassistant-custom-component`, `ruff` for lint/format.

---

## Scope decision — what this plan does NOT build yet

Only UC01–UC04 have been through the full analysis review cycle. `control-cycle.md`,
`resolution-rules.md`, and `entity-catalog.md` are committed, but several rows in their
tables reference use-cases that don't exist yet (UC05 departure deadline/R5, UC06 solar
step-up/R8, UC07 solar-reserve cap/R9, UC08 home-day/R13, UC09 vehicle charge-limit sync/R6,
UC10/plug-in reminder R12). Writing code for those rows now would put code ahead of analysis,
which the project's methodology (`CLAUDE.md`) rules out.

This plan therefore builds:

- **Modes:** `Off`, `Solar` (R1/UC01), `SolarOnly` (R2/UC02), `Captar` (R4/UC03), `Power`
  (R17/UC04).
- **Profile:** `Manual` only. The `select.smart_charging_profile` entity offers only `Manual`
  for now (extensible — `Auto` is added once UC05/UC07/UC09/UC10 exist; see Task 13).
- **Resolution rules:** `active_soc_limit()` implements only the "otherwise: default" row
  (rows 1–2 need R8/R9). `effective_peak_limit()` implements only the "normal operation" row
  (row 1 needs R5 deadline urgency).
- **Coordinator pipeline:** the full `control-cycle.md` pipeline (smoothing, voltage
  resolution, peak clamp R3, grid-ceiling clamp C4, C1/R11 invariants) — this mechanism doc
  is fully specified regardless of which modes plug into it.
- **NOT built:** vehicle charge-limit sync (R6/UC09), solar SOC step-up (R8/UC06),
  solar-reserve cap (R9/UC07), deadline guarantee (R5/UC05), notifications (R12/R13),
  `Auto` mode-selection.

Each deferred item is marked `TODO(UC0n)` at its natural extension point in the code, so the
next plan lands as an additive change, not a rewrite.

---

## Task 1: Package skeleton, manifest, HACS metadata

**Files:**
- Create: `custom_components/smart_charging/__init__.py` (stub — filled in Task 12)
- Create: `custom_components/smart_charging/manifest.json`
- Create: `hacs.json`
- Create: `pyproject.toml`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Test: `tests/test_manifest.py`

**Step 1: Write the failing test**

```python
# tests/test_manifest.py
import json
from pathlib import Path

MANIFEST = Path("custom_components/smart_charging/manifest.json")


def test_manifest_has_required_keys():
    data = json.loads(MANIFEST.read_text())
    assert data["domain"] == "smart_charging"
    assert data["name"] == "Smart Charging"
    assert data["config_flow"] is True
    assert data["iot_class"] == "local_polling"
    assert "codeowners" in data
    assert "version" in data


def test_hacs_json_is_valid():
    data = json.loads(Path("hacs.json").read_text())
    assert data["name"] == "Smart Charging"
```

Run: `pytest tests/test_manifest.py -v`
Expected: FAIL — `manifest.json` / `hacs.json` don't exist yet.

**Step 2: Create manifest.json**

```json
{
  "domain": "smart_charging",
  "name": "Smart Charging",
  "codeowners": ["@KristofDegrave"],
  "config_flow": true,
  "documentation": "https://github.com/KristofDegrave/homeassistant-smart-charging",
  "iot_class": "local_polling",
  "issue_tracker": "https://github.com/KristofDegrave/homeassistant-smart-charging/issues",
  "requirements": [],
  "version": "0.1.0"
}
```

**Step 3: Create hacs.json**

```json
{
  "name": "Smart Charging",
  "render_readme": true,
  "homeassistant": "2025.1.0"
}
```

**Step 4: Create the stub `__init__.py`, `tests/__init__.py`, `tests/conftest.py`**

```python
# custom_components/smart_charging/__init__.py
"""The Smart Charging integration."""
```

```python
# tests/__init__.py
"""Tests for the Smart Charging integration."""
```

```python
# tests/conftest.py
"""Shared fixtures for the Smart Charging test suite."""
import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Make custom_components/ importable in every test (pytest-homeassistant-custom-component)."""
    yield
```

**Step 5: Add `pyproject.toml` (dev dependencies + ruff config)**

```toml
[tool.ruff]
target-version = "py313"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.pytest.ini_options]
asyncio_mode = "auto"

[project]
name = "smart-charging-dev"
version = "0.1.0"
requires-python = ">=3.13"

[project.optional-dependencies]
dev = [
  "pytest",
  "pytest-homeassistant-custom-component",
  "ruff",
]
```

**Step 6: Install dev deps and run test**

Run: `pip install -e ".[dev]"` then `pytest tests/test_manifest.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add custom_components/smart_charging/__init__.py custom_components/smart_charging/manifest.json hacs.json pyproject.toml tests/__init__.py tests/conftest.py tests/test_manifest.py
git commit -m "feat: scaffold smart_charging HACS package skeleton"
```

---

## Task 2: `const.py` — domain constants, roles, config keys, defaults

Values are taken from `docs/analysis/entity-catalog.md`, minus the `sc_` prefix (that prefix
named HA helper entities in the original mechanism-doc sketch; this integration expresses the
same parameters as config-entry keys instead — see the architecture design, Decision 2).

**Files:**
- Create: `custom_components/smart_charging/const.py`
- Test: `tests/test_const.py`

**Step 1: Write the failing test**

```python
# tests/test_const.py
from custom_components.smart_charging import const


def test_domain():
    assert const.DOMAIN == "smart_charging"


def test_role_enum_has_expected_roles():
    expected = {
        "NET_POWER", "SOLAR_POWER", "CHARGER_POWER", "GRID_VOLTAGE",
        "CHARGER_STATUS", "EV_SOC", "CHARGER_CURRENT", "MONTHLY_PEAK",
    }
    assert {r.name for r in const.Role} == expected


def test_canonical_charger_states():
    assert set(const.CANONICAL_CHARGER_STATES) == {"disconnected", "connected", "charging"}


def test_defaults_match_entity_catalog():
    assert const.DEFAULT_CONTROL_INTERVAL_S == 10
    assert const.DEFAULT_SMOOTHING_WINDOW == 4
    assert const.DEFAULT_MIN_CURRENT_A == 6
    assert const.DEFAULT_MAX_CURRENT_A == 32
    assert const.DEFAULT_SAFETY_MARGIN_W == 250
    assert const.DEFAULT_MAX_PEAK_KW == 4
    assert const.DEFAULT_PEAK_GRACE_MIN == 2
    assert const.DEFAULT_GRID_SUPPLY_CEILING_A == 40
    assert const.DEFAULT_GRID_SAFETY_OFFSET_A == 2
    assert const.DEFAULT_NOMINAL_VOLTAGE_V == 230
    assert const.DEFAULT_SOLAR_START_THRESHOLD_W == 150
    assert const.DEFAULT_SOLAR_HOLD_MIN == 5
    assert const.DEFAULT_SOLAR_COOLDOWN_MIN == 2
    assert const.DEFAULT_SOLAR_ONLY_START_THRESHOLD_W == 1300
    assert const.DEFAULT_CAPTAR_COOLDOWN_MIN == 10
    assert const.DEFAULT_POWER_TARGET_CURRENT_A == 10
    assert const.DEFAULT_POWER_COOLDOWN_MIN == 10
    assert const.DEFAULT_ACTIVE_SOC_PERCENT == 80
```

Run: `pytest tests/test_const.py -v`
Expected: FAIL — `const` module doesn't exist.

**Step 2: Implement `const.py`**

```python
# custom_components/smart_charging/const.py
"""Constants, roles, config keys, and requirement-traced defaults."""
from enum import StrEnum

DOMAIN = "smart_charging"


class Role(StrEnum):
    """Hardware roles mapped to a real entity_id during config flow."""

    NET_POWER = "net_power"          # sensor, W — required
    SOLAR_POWER = "solar_power"      # sensor, W — required if CONF_SOLAR_AVAILABLE
    CHARGER_POWER = "charger_power"  # sensor, W — required
    GRID_VOLTAGE = "grid_voltage"    # sensor, V — optional (NF4 fallback to nominal)
    CHARGER_STATUS = "charger_status"  # sensor, enum — required, needs state translation
    EV_SOC = "ev_soc"                # sensor, % — required
    CHARGER_CURRENT = "charger_current"  # number, A — required, write role
    MONTHLY_PEAK = "monthly_peak"    # sensor, kW — required


REQUIRED_ROLES = {
    Role.NET_POWER, Role.CHARGER_POWER, Role.CHARGER_STATUS,
    Role.EV_SOC, Role.CHARGER_CURRENT, Role.MONTHLY_PEAK,
}
OPTIONAL_ROLES = {Role.GRID_VOLTAGE}
SOLAR_ROLES = {Role.SOLAR_POWER}  # required only when CONF_SOLAR_AVAILABLE is True

# Roles whose upstream entity is a plain numeric sensor/number (no state translation).
NUMERIC_ROLES = {
    Role.NET_POWER, Role.SOLAR_POWER, Role.CHARGER_POWER, Role.GRID_VOLTAGE,
    Role.EV_SOC, Role.CHARGER_CURRENT, Role.MONTHLY_PEAK,
}
# Roles whose upstream entity is enum-valued and needs a state-translation table.
ENUM_ROLES = {Role.CHARGER_STATUS}

CANONICAL_CHARGER_STATES = ("disconnected", "connected", "charging")

# --- Config entry `data` keys (immutable after setup; changed via reconfigure) ---
CONF_SOLAR_AVAILABLE = "solar_available"
CONF_ROLE_MAPPING = "role_mapping"            # dict[str, str] — Role -> entity_id
CONF_CHARGER_STATUS_MAP = "charger_status_map"  # dict[str, str] — raw state -> canonical state

# --- Config entry `options` keys (changeable any time) ---
CONF_CONTROL_INTERVAL_S = "control_interval_s"
CONF_SMOOTHING_WINDOW = "smoothing_window"
CONF_MIN_CURRENT_A = "min_current_a"
CONF_MAX_CURRENT_A = "max_current_a"
CONF_SAFETY_MARGIN_W = "safety_margin_w"
CONF_MAX_PEAK_KW = "max_peak_kw"
CONF_PEAK_GRACE_MIN = "peak_grace_min"
CONF_GRID_SUPPLY_CEILING_A = "grid_supply_ceiling_a"
CONF_GRID_SAFETY_OFFSET_A = "grid_safety_offset_a"
CONF_NOMINAL_VOLTAGE_V = "nominal_voltage_v"
CONF_SOLAR_START_THRESHOLD_W = "solar_start_threshold_w"
CONF_SOLAR_HOLD_MIN = "solar_hold_min"
CONF_SOLAR_COOLDOWN_MIN = "solar_cooldown_min"
CONF_SOLAR_ONLY_START_THRESHOLD_W = "solar_only_start_threshold_w"
CONF_CAPTAR_COOLDOWN_MIN = "captar_cooldown_min"
CONF_POWER_TARGET_CURRENT_A = "power_target_current_a"
CONF_POWER_RESPECT_PEAK = "power_respect_peak"
CONF_POWER_COOLDOWN_MIN = "power_cooldown_min"
CONF_ACTIVE_SOC_PERCENT = "active_soc_percent"

# --- Defaults (docs/analysis/entity-catalog.md is authoritative) ---
DEFAULT_CONTROL_INTERVAL_S = 10
DEFAULT_SMOOTHING_WINDOW = 4
DEFAULT_MIN_CURRENT_A = 6
DEFAULT_MAX_CURRENT_A = 32
DEFAULT_SAFETY_MARGIN_W = 250
DEFAULT_MAX_PEAK_KW = 4
DEFAULT_PEAK_GRACE_MIN = 2
DEFAULT_GRID_SUPPLY_CEILING_A = 40
DEFAULT_GRID_SAFETY_OFFSET_A = 2
DEFAULT_NOMINAL_VOLTAGE_V = 230
DEFAULT_SOLAR_START_THRESHOLD_W = 150
DEFAULT_SOLAR_HOLD_MIN = 5
DEFAULT_SOLAR_COOLDOWN_MIN = 2
DEFAULT_SOLAR_ONLY_START_THRESHOLD_W = 1300
DEFAULT_CAPTAR_COOLDOWN_MIN = 10
DEFAULT_POWER_TARGET_CURRENT_A = 10
DEFAULT_POWER_COOLDOWN_MIN = 10
DEFAULT_ACTIVE_SOC_PERCENT = 80

MODES = ("Off", "Solar", "SolarOnly", "Captar", "Power")
SOLAR_MODES = ("Solar", "SolarOnly")
PROFILES = ("Manual",)  # TODO(UC05/UC07/UC09/UC10): add "Auto" once its dependencies exist
```

**Step 3: Run tests**

Run: `pytest tests/test_const.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add custom_components/smart_charging/const.py tests/test_const.py
git commit -m "feat: add domain constants, roles, and requirement-traced defaults"
```

---

## Task 3: Adapter layer

Implements architecture-design Decision 2: numeric roles read/write the mapped entity's
native value; enum roles translate through the state-translation table captured at config
time. A `None` return means "unavailable" — the coordinator (Task 8) turns that into a fault.

**Files:**
- Create: `custom_components/smart_charging/adapters.py`
- Test: `tests/test_adapters.py`

**Step 1: Write the failing tests**

```python
# tests/test_adapters.py
import pytest
from custom_components.smart_charging.adapters import NumericAdapter, EnumAdapter


async def test_numeric_adapter_reads_float_state(hass):
    hass.states.async_set("sensor.solar", "1234.5")
    adapter = NumericAdapter(hass, "sensor.solar")
    assert await adapter.read() == 1234.5


async def test_numeric_adapter_returns_none_when_unavailable(hass):
    hass.states.async_set("sensor.solar", "unavailable")
    adapter = NumericAdapter(hass, "sensor.solar")
    assert await adapter.read() is None


async def test_numeric_adapter_returns_none_when_missing(hass):
    adapter = NumericAdapter(hass, "sensor.does_not_exist")
    assert await adapter.read() is None


async def test_numeric_adapter_write_calls_number_set_value(hass):
    calls = []
    hass.services.async_register(
        "number", "set_value", lambda call: calls.append(call.data)
    )
    hass.states.async_set("number.charger_current", "0")
    adapter = NumericAdapter(hass, "number.charger_current")
    await adapter.write(16)
    assert calls == [{"entity_id": "number.charger_current", "value": 16}]


async def test_enum_adapter_translates_raw_state_to_canonical(hass):
    hass.states.async_set("sensor.charger", "State_C")
    adapter = EnumAdapter(hass, "sensor.charger", {"State_C": "charging", "State_A": "disconnected"})
    assert await adapter.read() == "charging"


async def test_enum_adapter_returns_none_for_unmapped_state(hass):
    hass.states.async_set("sensor.charger", "State_Z")
    adapter = EnumAdapter(hass, "sensor.charger", {"State_C": "charging"})
    assert await adapter.read() is None
```

Run: `pytest tests/test_adapters.py -v`
Expected: FAIL — module doesn't exist.

**Step 2: Implement `adapters.py`**

```python
# custom_components/smart_charging/adapters.py
"""Adapter layer: translates between real HA entities and the roles charging logic uses.

Architecture design Decision 2 — the "sc_ wrapper" is this Python abstraction, not new
HA entities. One adapter instance per mapped role; the coordinator never touches a real
entity_id directly.
"""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

_UNREADABLE = {STATE_UNAVAILABLE, STATE_UNKNOWN, None}


class NumericAdapter:
    """Reads/writes a numeric role via its mapped sensor/number entity."""

    def __init__(self, hass: HomeAssistant, entity_id: str) -> None:
        self._hass = hass
        self._entity_id = entity_id

    async def read(self) -> float | None:
        state = self._hass.states.get(self._entity_id)
        if state is None or state.state in _UNREADABLE:
            return None
        try:
            return float(state.state)
        except ValueError:
            return None

    async def write(self, value: float) -> None:
        await self._hass.services.async_call(
            "number", "set_value",
            {"entity_id": self._entity_id, "value": value},
            blocking=True,
        )


class EnumAdapter:
    """Reads an enum-valued role, translating the raw state to a canonical value."""

    def __init__(self, hass: HomeAssistant, entity_id: str, state_map: dict[str, str]) -> None:
        self._hass = hass
        self._entity_id = entity_id
        self._state_map = state_map

    async def read(self) -> str | None:
        state = self._hass.states.get(self._entity_id)
        if state is None or state.state in _UNREADABLE:
            return None
        return self._state_map.get(state.state)
```

**Step 3: Run tests**

Run: `pytest tests/test_adapters.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add custom_components/smart_charging/adapters.py tests/test_adapters.py
git commit -m "feat: add NumericAdapter/EnumAdapter hardware abstraction layer"
```

---

## Task 4: Smoothing, voltage resolution, and the coordinator clamps (control-cycle.md steps 2–3, 5–7)

Pure functions — no HA dependency — so `control-cycle.md`'s invariants are unit-testable
directly against its acceptance criteria.

**Files:**
- Create: `custom_components/smart_charging/control_cycle.py`
- Test: `tests/test_control_cycle.py`

**Step 1: Write the failing tests**

```python
# tests/test_control_cycle.py
from custom_components.smart_charging.control_cycle import (
    SmoothingWindow, resolve_voltage, apply_peak_clamp, apply_grid_ceiling_clamp,
    enforce_current_invariant,
)


def test_r10_smoothing_window_averages_last_n_samples():
    w = SmoothingWindow(size=4)
    for v in [100, 100, 100, 100]:
        w.push(v)
    assert w.value() == 100
    w.push(500)  # 5th sample evicts the oldest
    assert w.value() == 200  # (100+100+100+500)/4


def test_r10_single_cycle_spike_is_smoothed_out():
    w = SmoothingWindow(size=4)
    for v in [0, 0, 0, 0]:
        w.push(v)
    w.push(4000)  # one-cycle spike
    assert w.value() == 1000  # doesn't jump straight to 4000


def test_r10_window_not_yet_full_averages_available_samples():
    w = SmoothingWindow(size=4)
    w.push(100)
    w.push(300)
    assert w.value() == 200


def test_nf4_uses_measured_voltage_when_healthy():
    assert resolve_voltage(measured=228.0, nominal=230) == 228.0


def test_nf4_falls_back_to_nominal_when_measured_missing():
    assert resolve_voltage(measured=None, nominal=230) == 230


def test_r3_peak_clamp_reduces_current_to_headroom():
    # raw net import 3000 W, effective peak limit 4000 W, safety margin 250 W -> target 3750 W
    # headroom above current draw = 750 W = 3.26 A @ 230V -> floor to 3 A, but floor is min 6 A
    # so use numbers that land cleanly: desired 20A, raw_net_w=3500, limit=4000, margin=250 -> target=3750
    # headroom = 3750-3500 = 250W = ~1.08A @230V -> current can only add ~1A -> current draw before + 1
    result = apply_peak_clamp(
        desired_a=20, raw_net_w=3500, effective_peak_limit_w=4000, safety_margin_w=250,
        voltage=230, min_a=6, max_a=32,
    )
    assert result <= 20
    assert result >= 6


def test_r3_peak_clamp_no_reduction_when_within_target():
    result = apply_peak_clamp(
        desired_a=10, raw_net_w=500, effective_peak_limit_w=4000, safety_margin_w=250,
        voltage=230, min_a=6, max_a=32,
    )
    assert result == 10


def test_c4_grid_ceiling_clamp_bounds_below_ceiling():
    result = apply_grid_ceiling_clamp(
        desired_a=32, raw_net_w=8000, ceiling_a=40, safety_offset_a=2, voltage=230,
    )
    assert result < 32


def test_c1_invariant_zero_or_at_least_minimum():
    assert enforce_current_invariant(0, min_a=6, max_a=32) == 0
    assert enforce_current_invariant(3, min_a=6, max_a=32) == 0  # below min -> 0, never in-between
    assert enforce_current_invariant(6, min_a=6, max_a=32) == 6
    assert enforce_current_invariant(40, min_a=6, max_a=32) == 32  # capped at max
```

Run: `pytest tests/test_control_cycle.py -v`
Expected: FAIL — module doesn't exist.

**Step 2: Implement `control_cycle.py`**

```python
# custom_components/smart_charging/control_cycle.py
"""Pure mechanism functions from docs/analysis/control-cycle.md.

No Home Assistant dependency — these implement R10, NF4, R3, and C4 as plain
functions so they're unit-testable directly against the flow doc's acceptance criteria.
The coordinator (Task 8) wires these into the eight-step pipeline.
"""
from __future__ import annotations

from collections import deque


class SmoothingWindow:
    """R10 — rolling mean over the last N samples."""

    def __init__(self, size: int) -> None:
        self._samples: deque[float] = deque(maxlen=size)

    def push(self, value: float) -> None:
        self._samples.append(value)

    def value(self) -> float:
        if not self._samples:
            return 0.0
        return sum(self._samples) / len(self._samples)


def resolve_voltage(measured: float | None, nominal: float) -> float:
    """NF4 — measured grid voltage when healthy, else the configured nominal voltage."""
    return measured if measured is not None else nominal


def _watts_to_amps(watts: float, voltage: float) -> float:
    return watts / voltage


def apply_peak_clamp(
    desired_a: float, raw_net_w: float, effective_peak_limit_w: float,
    safety_margin_w: float, voltage: float, min_a: float, max_a: float,
) -> float:
    """R3 — clamp desired_a so raw net import stays <= effective peak limit - safety margin."""
    target_w = effective_peak_limit_w - safety_margin_w
    headroom_w = target_w - raw_net_w
    if headroom_w >= 0:
        return min(desired_a, max_a)
    # Reduce by the shortfall, converted to amps, floored to a whole ampere.
    reduction_a = _watts_to_amps(-headroom_w, voltage)
    clamped = desired_a - reduction_a
    return max(min(clamped, max_a), 0)


def apply_grid_ceiling_clamp(
    desired_a: float, raw_net_w: float, ceiling_a: float, safety_offset_a: float, voltage: float,
) -> float:
    """C4 — hard fuse-protection clamp; applies in every mode, even when R3 is disabled."""
    ceiling_w = (ceiling_a - safety_offset_a) * voltage
    headroom_w = ceiling_w - raw_net_w
    if headroom_w >= 0:
        return desired_a
    reduction_a = _watts_to_amps(-headroom_w, voltage)
    return max(desired_a - reduction_a, 0)


def enforce_current_invariant(current_a: float, min_a: float, max_a: float) -> float:
    """C1 — the final current is always 0, or a whole ampere within [min_a, max_a]."""
    import math

    if current_a < min_a:
        return 0
    return min(math.floor(current_a), max_a)
```

**Step 3: Run tests, iterate on the peak/ceiling clamp math until they pass**

Run: `pytest tests/test_control_cycle.py -v`
Expected: PASS. (If the two clamp tests' bounds don't match — these are the first
peak/ceiling functions built against R3/C4, so tighten the assertions during this step
rather than treating the numbers above as gospel; the invariant that must hold is
"never raises current, only reduces it, and rounds via `enforce_current_invariant`".)

**Step 4: Commit**

```bash
git add custom_components/smart_charging/control_cycle.py tests/test_control_cycle.py
git commit -m "feat: implement R10 smoothing, NF4 voltage resolution, R3/C4/C1 clamps"
```

---

## Task 5: `resolution_rules.py` — active SOC limit & effective peak limit (partial)

**Files:**
- Create: `custom_components/smart_charging/resolution_rules.py`
- Test: `tests/test_resolution_rules.py`

**Step 1: Write the failing tests**

```python
# tests/test_resolution_rules.py
from custom_components.smart_charging.resolution_rules import (
    active_soc_limit, effective_peak_limit,
)


def test_r7_active_soc_limit_returns_configured_default():
    # Rows 1 (solar-reserve cap, R9) and 2 (solar step-up, R8) are TODO(UC07)/TODO(UC06).
    assert active_soc_limit(default_percent=80) == 80


def test_effective_peak_limit_normal_operation_is_min_of_billed_and_max():
    # Row 1 (deadline urgency, R5) is TODO(UC05) — always falls through to row 2.
    assert effective_peak_limit(monthly_peak_kw=2.5, max_peak_kw=4) == 2.5
    assert effective_peak_limit(monthly_peak_kw=5.0, max_peak_kw=4) == 4
```

Run: `pytest tests/test_resolution_rules.py -v`
Expected: FAIL.

**Step 2: Implement**

```python
# custom_components/smart_charging/resolution_rules.py
"""Shared, priority-ordered lookups from docs/analysis/resolution-rules.md.

Only the rows reachable without UC05-UC10 are implemented; each omitted row is marked
TODO so the next plan (once those use-cases exist) extends this file additively.
"""
from __future__ import annotations


def active_soc_limit(default_percent: float) -> float:
    """R7 — resolve the active SOC limit.

    TODO(UC07): row 1, the Auto-only solar-reserve cap (R9).
    TODO(UC06): row 2, the solar step-up (R8).
    """
    return default_percent


def effective_peak_limit(monthly_peak_kw: float, max_peak_kw: float) -> float:
    """Resolve the effective peak limit (ceiling on net import).

    TODO(UC05): row 1, deadline urgency (R5) raises this to max_peak_kw.
    """
    return min(monthly_peak_kw, max_peak_kw)
```

**Step 3: Run tests**

Run: `pytest tests/test_resolution_rules.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add custom_components/smart_charging/resolution_rules.py tests/test_resolution_rules.py
git commit -m "feat: add R7/effective-peak-limit resolution rules (default rows only)"
```

---

## Task 6: Mode module — `Off`

**Files:**
- Create: `custom_components/smart_charging/modes/__init__.py`
- Create: `custom_components/smart_charging/modes/base.py`
- Create: `custom_components/smart_charging/modes/off.py`
- Test: `tests/modes/test_off.py`

**Step 1: Write the failing test**

```python
# tests/modes/test_off.py
from custom_components.smart_charging.modes.off import OffMode


def test_off_mode_always_requests_zero():
    mode = OffMode()
    assert mode.tick(readings={}, config={}) == 0
```

Run: `pytest tests/modes/test_off.py -v`
Expected: FAIL.

**Step 2: Implement the shared `Reading`/`ModeConfig` shapes and `OffMode`**

```python
# custom_components/smart_charging/modes/base.py
"""Shared shapes passed into every mode module. No mode-specific logic lives here (NF2)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Readings:
    """Smoothed + raw inputs for one control cycle, plus resolved lookups."""

    smoothed_net_w: float
    smoothed_solar_w: float
    charger_status: str  # "disconnected" | "connected" | "charging"
    ev_soc_percent: float
    active_soc_limit_percent: float
```

```python
# custom_components/smart_charging/modes/off.py
"""Off mode — requests 0 A unconditionally."""
from __future__ import annotations

from .base import Readings


class OffMode:
    def tick(self, readings: Readings | dict, config: dict) -> float:
        return 0
```

```python
# custom_components/smart_charging/modes/__init__.py
"""Mode modules — one self-contained unit per charging mode (NF2)."""
```

**Step 3: Run tests**

Run: `pytest tests/modes/test_off.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add custom_components/smart_charging/modes/ tests/modes/test_off.py
git commit -m "feat: add mode module scaffolding and Off mode"
```

---

## Task 7: Mode module — `Solar` (R1/UC01)

State machine per UC01's state table: `Idle → Charging → Hold → Cooldown`, plus
`SocReached`. Cooldown/hold durations are injected as seconds; the mode takes an
injected monotonic clock (`now_fn`) so tests don't sleep.

**Files:**
- Create: `custom_components/smart_charging/modes/solar.py`
- Test: `tests/modes/test_solar.py`

**Step 1: Write the failing tests (one per UC01 acceptance criterion)**

```python
# tests/modes/test_solar.py
from custom_components.smart_charging.modes.solar import SolarMode
from custom_components.smart_charging.modes.base import Readings


def make_readings(net_w, soc=50, limit=80, status="connected"):
    return Readings(
        smoothed_net_w=net_w, smoothed_solar_w=0, charger_status=status,
        ev_soc_percent=soc, active_soc_limit_percent=limit,
    )


CONFIG = dict(
    start_threshold_w=150, hold_s=300, cooldown_s=120, min_a=6, max_a=32, voltage=230,
)


def test_r1_idle_below_threshold_stays_at_zero():
    clock = [0.0]
    mode = SolarMode(now_fn=lambda: clock[0])
    assert mode.tick(make_readings(net_w=100), CONFIG) == 0


def test_r1_starts_charging_at_highest_ampere_keeping_net_import_at_zero():
    clock = [0.0]
    mode = SolarMode(now_fn=lambda: clock[0])
    # net import 500W positive means charger is drawing 500W from the grid beyond solar;
    # surplus = -net_w when charging at 0. Model: smoothed_net_w already reflects the
    # charger's current draw, so "surplus available" = -smoothed_net_w when net_w < 0.
    readings = make_readings(net_w=-2300)  # 2300W exported = 10A of surplus @230V
    result = mode.tick(readings, CONFIG)
    assert result == 10


def test_r1_grid_fallback_holds_at_minimum_when_surplus_below_minimum_current():
    clock = [0.0]
    mode = SolarMode(now_fn=lambda: clock[0])
    mode.tick(make_readings(net_w=-2300), CONFIG)  # start charging first
    readings = make_readings(net_w=-200)  # surplus (200W=~0.87A) below min current (6A) but >= 150W threshold
    result = mode.tick(readings, CONFIG)
    assert result == CONFIG["min_a"]


def test_r1_post_surplus_hold_then_resumes_if_surplus_returns():
    clock = [0.0]
    mode = SolarMode(now_fn=lambda: clock[0])
    mode.tick(make_readings(net_w=-2300), CONFIG)  # charging
    mode.tick(make_readings(net_w=100), CONFIG)  # surplus drops below threshold -> Hold
    assert mode.state == "Hold"
    clock[0] += 60  # still within the 300s hold
    result = mode.tick(make_readings(net_w=-2300), CONFIG)  # surplus returns
    assert result == 10
    assert mode.state == "Charging"


def test_r1_post_surplus_hold_elapses_then_stops_and_cooldown_starts():
    clock = [0.0]
    mode = SolarMode(now_fn=lambda: clock[0])
    mode.tick(make_readings(net_w=-2300), CONFIG)
    mode.tick(make_readings(net_w=100), CONFIG)  # -> Hold
    clock[0] += 301  # hold period elapses
    result = mode.tick(make_readings(net_w=100), CONFIG)
    assert result == 0
    assert mode.state == "Cooldown"


def test_r1_cooldown_blocks_restart_until_elapsed():
    clock = [0.0]
    mode = SolarMode(now_fn=lambda: clock[0])
    mode.tick(make_readings(net_w=-2300), CONFIG)
    mode.tick(make_readings(net_w=100), CONFIG)
    clock[0] += 301
    mode.tick(make_readings(net_w=100), CONFIG)  # -> Cooldown
    clock[0] += 60  # cooldown is 120s, not yet elapsed
    result = mode.tick(make_readings(net_w=-2300), CONFIG)
    assert result == 0
    assert mode.state == "Cooldown"
    clock[0] += 61  # now elapsed
    result = mode.tick(make_readings(net_w=-2300), CONFIG)
    assert result == 10


def test_r7_stops_at_active_soc_limit_and_does_not_resume():
    clock = [0.0]
    mode = SolarMode(now_fn=lambda: clock[0])
    mode.tick(make_readings(net_w=-2300, soc=79, limit=80), CONFIG)
    result = mode.tick(make_readings(net_w=-2300, soc=80, limit=80), CONFIG)
    assert result == 0
    assert mode.state == "SocReached"
    # surplus still available, but SOC still at/above limit -> stays at 0
    result = mode.tick(make_readings(net_w=-2300, soc=80, limit=80), CONFIG)
    assert result == 0


def test_r11_switching_mode_resets_timers():
    clock = [0.0]
    mode = SolarMode(now_fn=lambda: clock[0])
    mode.tick(make_readings(net_w=-2300), CONFIG)
    mode.tick(make_readings(net_w=100), CONFIG)  # -> Hold
    mode.reset()
    assert mode.state == "Idle"
```

Run: `pytest tests/modes/test_solar.py -v`
Expected: FAIL.

**Step 2: Implement `SolarMode`**

```python
# custom_components/smart_charging/modes/solar.py
"""Solar mode (R1/UC01) — solar-first with grid fallback and a post-surplus hold."""
from __future__ import annotations

import math

from .base import Readings


class SolarMode:
    """One self-contained unit implementing UC01's state table (NF2)."""

    def __init__(self, now_fn=None) -> None:
        import time

        self._now = now_fn or time.monotonic
        self.state = "Idle"
        self._hold_started_at: float | None = None
        self._cooldown_started_at: float | None = None

    def reset(self) -> None:
        self.state = "Idle"
        self._hold_started_at = None
        self._cooldown_started_at = None

    def _surplus_w(self, readings: Readings) -> float:
        # Net import is positive when importing from the grid; surplus is the negative of it.
        return -readings.smoothed_net_w

    def _set_point_a(self, readings: Readings, config: dict) -> float:
        surplus_w = self._surplus_w(readings)
        raw_a = surplus_w / config["voltage"]
        floored = math.floor(raw_a)
        return max(min(floored, config["max_a"]), config["min_a"])

    def tick(self, readings: Readings, config: dict) -> float:
        if readings.ev_soc_percent >= readings.active_soc_limit_percent:
            self.state = "SocReached"
            return 0

        if self.state == "SocReached":
            # R7: never resumes above the limit until it changes or a reconnect (handled
            # by the coordinator calling reset() on disconnect) — here SOC is still >= limit
            # so we already returned above; if it dropped back down, fall through to Idle.
            self.state = "Idle"

        surplus_w = self._surplus_w(readings)
        threshold_w = config["start_threshold_w"]

        if self.state == "Cooldown":
            if self._now() - self._cooldown_started_at < config["cooldown_s"]:
                return 0
            self.state = "Idle"

        if self.state == "Idle":
            if surplus_w >= threshold_w:
                self.state = "Charging"
            else:
                return 0

        if self.state == "Charging":
            if surplus_w < threshold_w:
                self.state = "Hold"
                self._hold_started_at = self._now()
                return config["min_a"]
            return self._set_point_a(readings, config)

        if self.state == "Hold":
            if surplus_w >= threshold_w:
                self.state = "Charging"
                return self._set_point_a(readings, config)
            if self._now() - self._hold_started_at >= config["hold_s"]:
                self.state = "Cooldown"
                self._cooldown_started_at = self._now()
                return 0
            return config["min_a"]

        raise AssertionError(f"unreachable state {self.state!r}")
```

**Step 3: Run tests, iterate**

Run: `pytest tests/modes/test_solar.py -v`
Expected: PASS. If a specific transition test fails, re-read the corresponding row of
UC01's state table before changing the assertion — the table is the source of truth.

**Step 4: Commit**

```bash
git add custom_components/smart_charging/modes/solar.py tests/modes/test_solar.py
git commit -m "feat: implement Solar mode (R1/UC01)"
```

---

## Task 8: Mode module — `SolarOnly` (R2/UC02)

Same shape as `Solar`, minus grid fallback and the hold state (UC02: immediate stop).

**Files:**
- Create: `custom_components/smart_charging/modes/solar_only.py`
- Test: `tests/modes/test_solar_only.py`

**Step 1: Write the failing tests**

```python
# tests/modes/test_solar_only.py
from custom_components.smart_charging.modes.solar_only import SolarOnlyMode
from custom_components.smart_charging.modes.base import Readings

CONFIG = dict(start_threshold_w=1300, cooldown_s=120, min_a=6, max_a=32, voltage=230)


def make_readings(net_w, soc=50, limit=80):
    return Readings(
        smoothed_net_w=net_w, smoothed_solar_w=0, charger_status="connected",
        ev_soc_percent=soc, active_soc_limit_percent=limit,
    )


def test_r2_idle_below_threshold():
    mode = SolarOnlyMode(now_fn=lambda: 0.0)
    assert mode.tick(make_readings(net_w=-1000), CONFIG) == 0  # 1000W < 1300W threshold


def test_r2_starts_and_tracks_surplus():
    mode = SolarOnlyMode(now_fn=lambda: 0.0)
    result = mode.tick(make_readings(net_w=-2300), CONFIG)  # 10A worth of surplus
    assert result == 10


def test_r2_no_hold_immediate_stop_and_cooldown():
    clock = [0.0]
    mode = SolarOnlyMode(now_fn=lambda: clock[0])
    mode.tick(make_readings(net_w=-2300), CONFIG)
    result = mode.tick(make_readings(net_w=-100), CONFIG)  # surplus drops below threshold
    assert result == 0
    assert mode.state == "Cooldown"  # no Hold state exists for SolarOnly


def test_r2_never_falls_back_to_grid():
    mode = SolarOnlyMode(now_fn=lambda: 0.0)
    # surplus of 100W (below min current 6A=1380W) never floors at min_a; must be 0.
    result = mode.tick(make_readings(net_w=-100), CONFIG)
    assert result == 0
```

Run: `pytest tests/modes/test_solar_only.py -v`
Expected: FAIL.

**Step 2: Implement `SolarOnlyMode`**

```python
# custom_components/smart_charging/modes/solar_only.py
"""SolarOnly mode (R2/UC02) — solar-first, no grid fallback, no post-surplus hold."""
from __future__ import annotations

import math

from .base import Readings


class SolarOnlyMode:
    def __init__(self, now_fn=None) -> None:
        import time

        self._now = now_fn or time.monotonic
        self.state = "Idle"
        self._cooldown_started_at: float | None = None

    def reset(self) -> None:
        self.state = "Idle"
        self._cooldown_started_at = None

    def _set_point_a(self, readings: Readings, config: dict) -> float:
        surplus_w = -readings.smoothed_net_w
        raw_a = surplus_w / config["voltage"]
        floored = math.floor(raw_a)
        if floored < config["min_a"]:
            return 0  # SolarOnly never floors at the minimum via grid fallback
        return min(floored, config["max_a"])

    def tick(self, readings: Readings, config: dict) -> float:
        if readings.ev_soc_percent >= readings.active_soc_limit_percent:
            self.state = "SocReached"
            return 0
        if self.state == "SocReached":
            self.state = "Idle"

        surplus_w = -readings.smoothed_net_w
        threshold_w = config["start_threshold_w"]

        if self.state == "Cooldown":
            if self._now() - self._cooldown_started_at < config["cooldown_s"]:
                return 0
            self.state = "Idle"

        if self.state == "Idle":
            if surplus_w >= threshold_w:
                self.state = "Charging"
                return self._set_point_a(readings, config)
            return 0

        if self.state == "Charging":
            if surplus_w < threshold_w:
                self.state = "Cooldown"
                self._cooldown_started_at = self._now()
                return 0
            return self._set_point_a(readings, config)

        raise AssertionError(f"unreachable state {self.state!r}")
```

**Step 3: Run tests**

Run: `pytest tests/modes/test_solar_only.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add custom_components/smart_charging/modes/solar_only.py tests/modes/test_solar_only.py
git commit -m "feat: implement SolarOnly mode (R2/UC02)"
```

---

## Task 9: Mode module — `Captar` (R4/UC03)

Per UC03: the mode always *requests* the maximum charging current; the coordinator's R3/C4
clamps (Task 4) do the fitting to headroom. So the mode itself is simple — the interesting
behaviour (fitting to headroom, stopping on a sustained breach) lives in the coordinator,
not here. This mode owns only its own Idle/Charging/Cooldown/SocReached state and cooldown.

**Files:**
- Create: `custom_components/smart_charging/modes/captar.py`
- Test: `tests/modes/test_captar.py`

**Step 1: Write the failing tests**

```python
# tests/modes/test_captar.py
from custom_components.smart_charging.modes.captar import CaptarMode
from custom_components.smart_charging.modes.base import Readings

CONFIG = dict(cooldown_s=600, max_a=32)


def make_readings(soc=50, limit=80):
    return Readings(
        smoothed_net_w=0, smoothed_solar_w=0, charger_status="connected",
        ev_soc_percent=soc, active_soc_limit_percent=limit,
    )


def test_r4_requests_maximum_current_when_below_limit():
    mode = CaptarMode(now_fn=lambda: 0.0)
    assert mode.tick(make_readings(soc=50, limit=80), CONFIG) == CONFIG["max_a"]


def test_r4_defaults_to_zero_at_or_above_limit():
    mode = CaptarMode(now_fn=lambda: 0.0)
    assert mode.tick(make_readings(soc=80, limit=80), CONFIG) == 0
    assert mode.state == "SocReached"


def test_r11_cooldown_after_coordinator_reports_a_stop():
    clock = [0.0]
    mode = CaptarMode(now_fn=lambda: clock[0])
    mode.tick(make_readings(), CONFIG)  # Charging
    mode.notify_stopped_by_clamp()  # R3 sustained breach at minimum -> coordinator calls this
    assert mode.state == "Cooldown"
    result = mode.tick(make_readings(), CONFIG)
    assert result == 0
    clock[0] += 601
    result = mode.tick(make_readings(), CONFIG)
    assert result == CONFIG["max_a"]
```

Run: `pytest tests/modes/test_captar.py -v`
Expected: FAIL.

**Step 2: Implement `CaptarMode`**

```python
# custom_components/smart_charging/modes/captar.py
"""Captar mode (R4/UC03) — always requests the maximum current; the coordinator's R3
peak clamp fits it to headroom and reports a sustained-breach stop via
notify_stopped_by_clamp(), which is what starts this mode's cooldown (R11)."""
from __future__ import annotations

from .base import Readings


class CaptarMode:
    def __init__(self, now_fn=None) -> None:
        import time

        self._now = now_fn or time.monotonic
        self.state = "Idle"
        self._cooldown_started_at: float | None = None

    def reset(self) -> None:
        self.state = "Idle"
        self._cooldown_started_at = None

    def notify_stopped_by_clamp(self) -> None:
        """Called by the coordinator on a sustained R3 breach at the minimum current."""
        self.state = "Cooldown"
        self._cooldown_started_at = self._now()

    def tick(self, readings: Readings, config: dict) -> float:
        if readings.ev_soc_percent >= readings.active_soc_limit_percent:
            self.state = "SocReached"
            return 0
        if self.state == "SocReached":
            self.state = "Idle"

        if self.state == "Cooldown":
            if self._now() - self._cooldown_started_at < config["cooldown_s"]:
                return 0
            self.state = "Idle"

        self.state = "Charging"
        return config["max_a"]
```

**Step 3: Run tests**

Run: `pytest tests/modes/test_captar.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add custom_components/smart_charging/modes/captar.py tests/modes/test_captar.py
git commit -m "feat: implement Captar mode (R4/UC03)"
```

---

## Task 10: Mode module — `Power` (R17/UC04)

Requests the configured target current unconditionally. Whether R3 applies is a flag the
coordinator reads from config (`power_respect_peak`) when deciding whether to run the peak
clamp at all — the mode itself doesn't know about clamps, matching UC04's description that
the mode's own law is "request the target current," full stop.

**Files:**
- Create: `custom_components/smart_charging/modes/power.py`
- Test: `tests/modes/test_power.py`

**Step 1: Write the failing tests**

```python
# tests/modes/test_power.py
from custom_components.smart_charging.modes.power import PowerMode
from custom_components.smart_charging.modes.base import Readings

CONFIG = dict(cooldown_s=600, target_a=10)


def make_readings(soc=50, limit=80):
    return Readings(
        smoothed_net_w=0, smoothed_solar_w=0, charger_status="connected",
        ev_soc_percent=soc, active_soc_limit_percent=limit,
    )


def test_r17_requests_configured_target_current():
    mode = PowerMode(now_fn=lambda: 0.0)
    assert mode.tick(make_readings(), CONFIG) == 10


def test_r17_stops_at_active_soc_limit():
    mode = PowerMode(now_fn=lambda: 0.0)
    assert mode.tick(make_readings(soc=80, limit=80), CONFIG) == 0
    assert mode.state == "SocReached"


def test_r11_cooldown_after_coordinator_reports_a_stop():
    clock = [0.0]
    mode = PowerMode(now_fn=lambda: clock[0])
    mode.tick(make_readings(), CONFIG)
    mode.notify_stopped_by_clamp()
    assert mode.tick(make_readings(), CONFIG) == 0
    clock[0] += 601
    assert mode.tick(make_readings(), CONFIG) == 10
```

Run: `pytest tests/modes/test_power.py -v`
Expected: FAIL.

**Step 2: Implement `PowerMode`**

```python
# custom_components/smart_charging/modes/power.py
"""Power mode (R17/UC04) — requests the configured target current unconditionally.

Whether the R3 peak clamp applies is decided by the coordinator from the
power_respect_peak option; this mode neither knows nor cares about clamps.
"""
from __future__ import annotations

from .base import Readings


class PowerMode:
    def __init__(self, now_fn=None) -> None:
        import time

        self._now = now_fn or time.monotonic
        self.state = "Idle"
        self._cooldown_started_at: float | None = None

    def reset(self) -> None:
        self.state = "Idle"
        self._cooldown_started_at = None

    def notify_stopped_by_clamp(self) -> None:
        self.state = "Cooldown"
        self._cooldown_started_at = self._now()

    def tick(self, readings: Readings, config: dict) -> float:
        if readings.ev_soc_percent >= readings.active_soc_limit_percent:
            self.state = "SocReached"
            return 0
        if self.state == "SocReached":
            self.state = "Idle"

        if self.state == "Cooldown":
            if self._now() - self._cooldown_started_at < config["cooldown_s"]:
                return 0
            self.state = "Idle"

        self.state = "Charging"
        return config["target_a"]
```

**Step 3: Run tests**

Run: `pytest tests/modes/test_power.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add custom_components/smart_charging/modes/power.py tests/modes/test_power.py
git commit -m "feat: implement Power mode (R17/UC04)"
```

---

## Task 11: `profiles/manual.py`

**Files:**
- Create: `custom_components/smart_charging/profiles/__init__.py`
- Create: `custom_components/smart_charging/profiles/manual.py`
- Test: `tests/profiles/test_manual.py`

**Step 1: Write the failing test**

```python
# tests/profiles/test_manual.py
from custom_components.smart_charging.profiles.manual import ManualProfile


def test_r16_manual_returns_whatever_mode_is_currently_selected():
    profile = ManualProfile()
    assert profile.active_mode(selected_mode="Captar") == "Captar"
    assert profile.active_mode(selected_mode="Off") == "Off"
```

Run: `pytest tests/profiles/test_manual.py -v`
Expected: FAIL.

**Step 2: Implement**

```python
# custom_components/smart_charging/profiles/__init__.py
"""Profile modules — select the active mode (NF1, NF2)."""
```

```python
# custom_components/smart_charging/profiles/manual.py
"""Manual profile (R16) — the active mode is whatever the user (or an external
source) has set directly; this profile makes no automatic changes."""
from __future__ import annotations


class ManualProfile:
    def active_mode(self, selected_mode: str) -> str:
        return selected_mode
```

**Step 3: Run tests**

Run: `pytest tests/profiles/test_manual.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add custom_components/smart_charging/profiles/ tests/profiles/test_manual.py
git commit -m "feat: implement Manual profile (R16)"
```

---

## Task 12: Config flow — entity-role mapping, capability, and state translation

**Files:**
- Create: `custom_components/smart_charging/config_flow.py`
- Test: `tests/test_config_flow.py`

**Step 1: Write the failing tests**

```python
# tests/test_config_flow.py
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from custom_components.smart_charging.const import DOMAIN, Role


async def test_user_step_then_charger_status_map_step_creates_entry(hass: HomeAssistant):
    hass.states.async_set("sensor.net", "0")
    hass.states.async_set("sensor.solar", "0")
    hass.states.async_set("sensor.charger_power", "0")
    hass.states.async_set("sensor.charger_status", "connected")
    hass.states.async_set("sensor.ev_soc", "50")
    hass.states.async_set("number.charger_current", "0")
    hass.states.async_set("sensor.monthly_peak", "1.0")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "solar_available": True,
            Role.NET_POWER: "sensor.net",
            Role.SOLAR_POWER: "sensor.solar",
            Role.CHARGER_POWER: "sensor.charger_power",
            Role.CHARGER_STATUS: "sensor.charger_status",
            Role.EV_SOC: "sensor.ev_soc",
            Role.CHARGER_CURRENT: "number.charger_current",
            Role.MONTHLY_PEAK: "sensor.monthly_peak",
        },
    )
    assert result["type"] == "form"
    assert result["step_id"] == "charger_status_map"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"disconnected": "unplugged", "connected": "plugged", "charging": "charging"},
    )
    assert result["type"] == "create_entry"
    assert result["data"]["role_mapping"][Role.NET_POWER] == "sensor.net"
    assert result["data"]["charger_status_map"] == {
        "unplugged": "disconnected", "plugged": "connected", "charging": "charging",
    }


async def test_user_step_rejects_mapping_to_nonexistent_entity(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "solar_available": False,
            Role.NET_POWER: "sensor.does_not_exist",
            Role.CHARGER_POWER: "sensor.does_not_exist",
            Role.CHARGER_STATUS: "sensor.does_not_exist",
            Role.EV_SOC: "sensor.does_not_exist",
            Role.CHARGER_CURRENT: "number.does_not_exist",
            Role.MONTHLY_PEAK: "sensor.does_not_exist",
        },
    )
    assert result["type"] == "form"
    assert result["errors"]
```

Run: `pytest tests/test_config_flow.py -v`
Expected: FAIL — module doesn't exist.

**Step 2: Implement `config_flow.py`**

Build this incrementally against the two tests above. Key shape:

```python
# custom_components/smart_charging/config_flow.py
"""Config flow: capability + entity-role mapping, then enum state translation."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    DOMAIN, Role, REQUIRED_ROLES, SOLAR_ROLES, CANONICAL_CHARGER_STATES,
    CONF_SOLAR_AVAILABLE, CONF_ROLE_MAPPING, CONF_CHARGER_STATUS_MAP,
)


class SmartChargingConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._role_mapping: dict[str, str] = {}
        self._solar_available: bool = True

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}
        roles_to_ask = REQUIRED_ROLES | (SOLAR_ROLES if True else set())

        if user_input is not None:
            self._solar_available = user_input[CONF_SOLAR_AVAILABLE]
            roles_to_ask = REQUIRED_ROLES | (SOLAR_ROLES if self._solar_available else set())
            for role in roles_to_ask:
                entity_id = user_input.get(role)
                if entity_id is None or self.hass.states.get(entity_id) is None:
                    errors[role] = "entity_not_found"
            if not errors:
                self._role_mapping = {role: user_input[role] for role in roles_to_ask}
                return await self.async_step_charger_status_map()

        schema = vol.Schema(
            {
                vol.Required(CONF_SOLAR_AVAILABLE, default=True): bool,
                **{vol.Required(role): str for role in roles_to_ask},
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_charger_status_map(self, user_input=None):
        if user_input is not None:
            # user_input maps {raw_state: canonical_state}; invert to {raw: canonical}
            return self.async_create_entry(
                title="Smart Charging",
                data={
                    CONF_SOLAR_AVAILABLE: self._solar_available,
                    CONF_ROLE_MAPPING: self._role_mapping,
                    CONF_CHARGER_STATUS_MAP: dict(user_input),
                },
            )
        schema = vol.Schema(
            {vol.Required(state): str for state in CANONICAL_CHARGER_STATES}
        )
        return self.async_show_form(step_id="charger_status_map", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        from .options_flow import SmartChargingOptionsFlow

        return SmartChargingOptionsFlow(config_entry)
```

Note: the test expects `result["data"]["charger_status_map"]` keyed by canonical state
(`{"unplugged": "disconnected", ...}`) — i.e. the form asks "what's your raw value for
`disconnected`?" and stores `{raw: canonical}` inverted from the form's own field names.
Reconcile the exact key direction between the form schema and `EnumAdapter`'s expected
`{raw: canonical}` shape while making this test pass — the test is the executable spec;
adjust the implementation (not the test's intent) until `EnumAdapter` and the flow agree.

**Step 3: Run tests, fix the mapping direction until green**

Run: `pytest tests/test_config_flow.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add custom_components/smart_charging/config_flow.py tests/test_config_flow.py
git commit -m "feat: add config flow (entity-role mapping + charger-status translation)"
```

---

## Task 13: Options flow — thresholds and control interval

**Files:**
- Create: `custom_components/smart_charging/options_flow.py`
- Test: `tests/test_options_flow.py`

**Step 1: Write the failing test**

```python
# tests/test_options_flow.py
from custom_components.smart_charging.const import DOMAIN, CONF_CONTROL_INTERVAL_S


async def test_options_flow_updates_control_interval(hass, mock_config_entry):
    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] == "form"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_CONTROL_INTERVAL_S: 30}
    )
    assert result["type"] == "create_entry"
    assert mock_config_entry.options[CONF_CONTROL_INTERVAL_S] == 30
```

Add a `mock_config_entry` fixture to `tests/conftest.py`:

```python
# append to tests/conftest.py
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from custom_components.smart_charging.const import DOMAIN


@pytest.fixture
def mock_config_entry(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    return entry
```

Run: `pytest tests/test_options_flow.py -v`
Expected: FAIL.

**Step 2: Implement `options_flow.py`**

```python
# custom_components/smart_charging/options_flow.py
"""Options flow — all config-entry `options` keys (architecture design, Decision 4)."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries

from . import const as c

_OPTION_DEFAULTS = {
    c.CONF_CONTROL_INTERVAL_S: c.DEFAULT_CONTROL_INTERVAL_S,
    c.CONF_SMOOTHING_WINDOW: c.DEFAULT_SMOOTHING_WINDOW,
    c.CONF_MIN_CURRENT_A: c.DEFAULT_MIN_CURRENT_A,
    c.CONF_MAX_CURRENT_A: c.DEFAULT_MAX_CURRENT_A,
    c.CONF_SAFETY_MARGIN_W: c.DEFAULT_SAFETY_MARGIN_W,
    c.CONF_MAX_PEAK_KW: c.DEFAULT_MAX_PEAK_KW,
    c.CONF_PEAK_GRACE_MIN: c.DEFAULT_PEAK_GRACE_MIN,
    c.CONF_GRID_SUPPLY_CEILING_A: c.DEFAULT_GRID_SUPPLY_CEILING_A,
    c.CONF_GRID_SAFETY_OFFSET_A: c.DEFAULT_GRID_SAFETY_OFFSET_A,
    c.CONF_NOMINAL_VOLTAGE_V: c.DEFAULT_NOMINAL_VOLTAGE_V,
    c.CONF_SOLAR_START_THRESHOLD_W: c.DEFAULT_SOLAR_START_THRESHOLD_W,
    c.CONF_SOLAR_HOLD_MIN: c.DEFAULT_SOLAR_HOLD_MIN,
    c.CONF_SOLAR_COOLDOWN_MIN: c.DEFAULT_SOLAR_COOLDOWN_MIN,
    c.CONF_SOLAR_ONLY_START_THRESHOLD_W: c.DEFAULT_SOLAR_ONLY_START_THRESHOLD_W,
    c.CONF_CAPTAR_COOLDOWN_MIN: c.DEFAULT_CAPTAR_COOLDOWN_MIN,
    c.CONF_POWER_TARGET_CURRENT_A: c.DEFAULT_POWER_TARGET_CURRENT_A,
    c.CONF_POWER_RESPECT_PEAK: True,
    c.CONF_POWER_COOLDOWN_MIN: c.DEFAULT_POWER_COOLDOWN_MIN,
    c.CONF_ACTIVE_SOC_PERCENT: c.DEFAULT_ACTIVE_SOC_PERCENT,
}


class SmartChargingOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = {**_OPTION_DEFAULTS, **self._config_entry.options}
        schema = vol.Schema(
            {vol.Required(key, default=default): type(default) for key, default in current.items()}
        )
        return self.async_show_form(step_id="init", data_schema=schema)
```

**Step 3: Run tests**

Run: `pytest tests/test_options_flow.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add custom_components/smart_charging/options_flow.py tests/test_options_flow.py tests/conftest.py
git commit -m "feat: add options flow for thresholds and control interval"
```

---

## Task 14: Coordinator — wire the control-cycle pipeline

Wires Tasks 3–11 into `control-cycle.md`'s eight steps. This is the integration point —
keep it thin; all interesting logic already lives in the pure functions/modules above.

**Files:**
- Create: `custom_components/smart_charging/coordinator.py`
- Test: `tests/test_coordinator.py`

**Step 1: Write the failing integration tests**

```python
# tests/test_coordinator.py
from custom_components.smart_charging.coordinator import SmartChargingCoordinator
from custom_components.smart_charging import const as c


async def test_coordinator_dispatches_to_off_when_mode_is_off(hass, mock_config_entry):
    hass.states.async_set("sensor.net", "0")
    hass.states.async_set("sensor.charger_power", "0")
    hass.states.async_set("sensor.charger_status", "connected")
    hass.states.async_set("sensor.ev_soc", "50")
    hass.states.async_set("number.charger_current", "0")
    hass.states.async_set("sensor.monthly_peak", "1.0")
    mock_config_entry.data = {
        c.CONF_SOLAR_AVAILABLE: False,
        c.CONF_ROLE_MAPPING: {
            c.Role.NET_POWER: "sensor.net", c.Role.CHARGER_POWER: "sensor.charger_power",
            c.Role.CHARGER_STATUS: "sensor.charger_status", c.Role.EV_SOC: "sensor.ev_soc",
            c.Role.CHARGER_CURRENT: "number.charger_current", c.Role.MONTHLY_PEAK: "sensor.monthly_peak",
        },
        c.CONF_CHARGER_STATUS_MAP: {"connected": "connected"},
    }
    calls = []
    hass.services.async_register("number", "set_value", lambda call: calls.append(call.data))

    coordinator = SmartChargingCoordinator(hass, mock_config_entry)
    coordinator.active_mode = "Off"
    await coordinator.async_refresh()

    assert calls[-1] == {"entity_id": "number.charger_current", "value": 0}


async def test_coordinator_sets_fault_status_when_a_required_role_is_unavailable(
    hass, mock_config_entry
):
    mock_config_entry.data = {
        c.CONF_SOLAR_AVAILABLE: False,
        c.CONF_ROLE_MAPPING: {
            c.Role.NET_POWER: "sensor.missing", c.Role.CHARGER_POWER: "sensor.missing",
            c.Role.CHARGER_STATUS: "sensor.missing", c.Role.EV_SOC: "sensor.missing",
            c.Role.CHARGER_CURRENT: "number.missing", c.Role.MONTHLY_PEAK: "sensor.missing",
        },
        c.CONF_CHARGER_STATUS_MAP: {},
    }
    coordinator = SmartChargingCoordinator(hass, mock_config_entry)
    coordinator.active_mode = "Off"
    await coordinator.async_refresh()

    assert coordinator.status == "Fault"
```

Run: `pytest tests/test_coordinator.py -v`
Expected: FAIL.

**Step 2: Implement `coordinator.py`**

```python
# custom_components/smart_charging/coordinator.py
"""The control-cycle coordinator (docs/analysis/control-cycle.md)."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import const as c
from .adapters import NumericAdapter, EnumAdapter
from .control_cycle import (
    SmoothingWindow, resolve_voltage, apply_peak_clamp, apply_grid_ceiling_clamp,
    enforce_current_invariant,
)
from .resolution_rules import active_soc_limit, effective_peak_limit
from .modes.base import Readings
from .modes.off import OffMode
from .modes.solar import SolarMode
from .modes.solar_only import SolarOnlyMode
from .modes.captar import CaptarMode
from .modes.power import PowerMode


class SmartChargingCoordinator(DataUpdateCoordinator):
    """NF1 — executes the active mode; never chooses it."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        options = entry.options
        interval = options.get(c.CONF_CONTROL_INTERVAL_S, c.DEFAULT_CONTROL_INTERVAL_S)
        super().__init__(
            hass, logger=__import__("logging").getLogger(__name__),
            name=c.DOMAIN, update_interval=timedelta(seconds=interval),
        )
        self.entry = entry
        self.active_mode = "Off"
        self.status = "OK"

        mapping = entry.data.get(c.CONF_ROLE_MAPPING, {})
        status_map = entry.data.get(c.CONF_CHARGER_STATUS_MAP, {})

        def numeric(role):
            entity_id = mapping.get(role)
            return NumericAdapter(hass, entity_id) if entity_id else None

        self._adapters = {
            c.Role.NET_POWER: numeric(c.Role.NET_POWER),
            c.Role.SOLAR_POWER: numeric(c.Role.SOLAR_POWER),
            c.Role.CHARGER_POWER: numeric(c.Role.CHARGER_POWER),
            c.Role.GRID_VOLTAGE: numeric(c.Role.GRID_VOLTAGE),
            c.Role.EV_SOC: numeric(c.Role.EV_SOC),
            c.Role.CHARGER_CURRENT: numeric(c.Role.CHARGER_CURRENT),
            c.Role.MONTHLY_PEAK: numeric(c.Role.MONTHLY_PEAK),
            c.Role.CHARGER_STATUS: (
                EnumAdapter(hass, mapping[c.Role.CHARGER_STATUS], status_map)
                if c.Role.CHARGER_STATUS in mapping else None
            ),
        }
        self._net_window = SmoothingWindow(options.get(c.CONF_SMOOTHING_WINDOW, c.DEFAULT_SMOOTHING_WINDOW))
        self._solar_window = SmoothingWindow(options.get(c.CONF_SMOOTHING_WINDOW, c.DEFAULT_SMOOTHING_WINDOW))
        self._modes = {
            "Off": OffMode(), "Solar": SolarMode(), "SolarOnly": SolarOnlyMode(),
            "Captar": CaptarMode(), "Power": PowerMode(),
        }

    async def _async_update_data(self):
        opts = self.entry.options

        # Step 1: read raw values through adapters.
        raw = {}
        for role, adapter in self._adapters.items():
            raw[role] = await adapter.read() if adapter else None

        required_missing = [
            role for role in (c.REQUIRED_ROLES) if raw.get(role) is None
        ]
        if required_missing:
            self.status = "Fault"
            return None
        self.status = "OK"

        # Step 2: smoothing (R10).
        self._net_window.push(raw[c.Role.NET_POWER])
        self._solar_window.push(raw.get(c.Role.SOLAR_POWER) or 0)
        smoothed_net_w = self._net_window.value()
        smoothed_solar_w = self._solar_window.value()

        # Step 3: voltage resolution (NF4).
        voltage = resolve_voltage(
            raw.get(c.Role.GRID_VOLTAGE), opts.get(c.CONF_NOMINAL_VOLTAGE_V, c.DEFAULT_NOMINAL_VOLTAGE_V)
        )

        # Step 4: dispatch to the active mode module (NF1).
        limit = active_soc_limit(opts.get(c.CONF_ACTIVE_SOC_PERCENT, c.DEFAULT_ACTIVE_SOC_PERCENT))
        readings = Readings(
            smoothed_net_w=smoothed_net_w, smoothed_solar_w=smoothed_solar_w,
            charger_status=raw[c.Role.CHARGER_STATUS], ev_soc_percent=raw[c.Role.EV_SOC],
            active_soc_limit_percent=limit,
        )
        mode = self._modes[self.active_mode]
        mode_config = self._mode_config(opts, voltage)
        desired_a = mode.tick(readings, mode_config)

        # Step 5: peak-protection clamp (R3) — skipped only for Power with peak disabled.
        skip_peak = self.active_mode == "Power" and not opts.get(c.CONF_POWER_RESPECT_PEAK, True)
        if not skip_peak:
            limit_w = effective_peak_limit(
                raw[c.Role.MONTHLY_PEAK] * 1000, opts.get(c.CONF_MAX_PEAK_KW, c.DEFAULT_MAX_PEAK_KW) * 1000
            )
            desired_a = apply_peak_clamp(
                desired_a, raw[c.Role.NET_POWER], limit_w,
                opts.get(c.CONF_SAFETY_MARGIN_W, c.DEFAULT_SAFETY_MARGIN_W), voltage,
                opts.get(c.CONF_MIN_CURRENT_A, c.DEFAULT_MIN_CURRENT_A),
                opts.get(c.CONF_MAX_CURRENT_A, c.DEFAULT_MAX_CURRENT_A),
            )

        # Step 6: grid-supply-ceiling clamp (C4) — always applies.
        desired_a = apply_grid_ceiling_clamp(
            desired_a, raw[c.Role.NET_POWER],
            opts.get(c.CONF_GRID_SUPPLY_CEILING_A, c.DEFAULT_GRID_SUPPLY_CEILING_A),
            opts.get(c.CONF_GRID_SAFETY_OFFSET_A, c.DEFAULT_GRID_SAFETY_OFFSET_A), voltage,
        )

        # Step 7: invariants (C1). R11 cooldown/hold state lives inside each mode module.
        final_a = enforce_current_invariant(
            desired_a, opts.get(c.CONF_MIN_CURRENT_A, c.DEFAULT_MIN_CURRENT_A),
            opts.get(c.CONF_MAX_CURRENT_A, c.DEFAULT_MAX_CURRENT_A),
        )

        # Step 8: set the charger current.
        await self._adapters[c.Role.CHARGER_CURRENT].write(final_a)
        return {"desired_current_a": final_a, "active_mode": self.active_mode}

    def _mode_config(self, opts: dict, voltage: float) -> dict:
        return {
            "start_threshold_w": opts.get(c.CONF_SOLAR_START_THRESHOLD_W, c.DEFAULT_SOLAR_START_THRESHOLD_W),
            "hold_s": opts.get(c.CONF_SOLAR_HOLD_MIN, c.DEFAULT_SOLAR_HOLD_MIN) * 60,
            "cooldown_s": opts.get(c.CONF_SOLAR_COOLDOWN_MIN, c.DEFAULT_SOLAR_COOLDOWN_MIN) * 60,
            "min_a": opts.get(c.CONF_MIN_CURRENT_A, c.DEFAULT_MIN_CURRENT_A),
            "max_a": opts.get(c.CONF_MAX_CURRENT_A, c.DEFAULT_MAX_CURRENT_A),
            "voltage": voltage,
            "target_a": opts.get(c.CONF_POWER_TARGET_CURRENT_A, c.DEFAULT_POWER_TARGET_CURRENT_A),
        }
```

Note: this task's two tests are a minimal smoke test of the wiring, not full coverage of
every mode/clamp interaction — Tasks 6–10 already cover each mode/clamp in isolation.
Adjust field names/shapes above as needed to make the tests pass; the point of this task
is the wiring being correct, not re-deriving the modes' internal logic.

**Step 3: Run tests, iterate**

Run: `pytest tests/test_coordinator.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add custom_components/smart_charging/coordinator.py tests/test_coordinator.py
git commit -m "feat: wire the control-cycle coordinator pipeline"
```

---

## Task 15: `__init__.py` — setup/unload entry, and owned entities

**Files:**
- Modify: `custom_components/smart_charging/__init__.py`
- Create: `custom_components/smart_charging/entity.py`
- Create: `custom_components/smart_charging/select.py`
- Create: `custom_components/smart_charging/sensor.py`
- Test: `tests/test_init.py`

**Step 1: Write the failing test**

```python
# tests/test_init.py
from homeassistant.setup import async_setup_component
from custom_components.smart_charging.const import DOMAIN


async def test_setup_entry_creates_select_and_sensor_entities(hass, mock_config_entry):
    mock_config_entry.data = {
        "solar_available": False,
        "role_mapping": {}, "charger_status_map": {},
    }
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("select.smart_charging_mode") is not None
    assert hass.states.get("sensor.smart_charging_status") is not None


async def test_unload_entry(hass, mock_config_entry):
    mock_config_entry.data = {"solar_available": False, "role_mapping": {}, "charger_status_map": {}}
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
```

Run: `pytest tests/test_init.py -v`
Expected: FAIL.

**Step 2: Implement `__init__.py`, `entity.py`, `select.py`, `sensor.py`**

```python
# custom_components/smart_charging/__init__.py
"""The Smart Charging integration."""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN
from .coordinator import SmartChargingCoordinator

PLATFORMS = ["select", "sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = SmartChargingCoordinator(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
```

```python
# custom_components/smart_charging/entity.py
"""Base entity for owned control/diagnostic entities (architecture design, Decision 3)."""
from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN


class SmartChargingEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)}, name="Smart Charging",
        )
        self._attr_unique_id = f"{entry_id}_{self._attr_translation_key}"
```

```python
# custom_components/smart_charging/select.py
"""select.smart_charging_mode — sets the active mode (Manual profile, R16)."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity

from .const import DOMAIN, MODES, SOLAR_MODES
from .entity import SmartChargingEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SmartChargingModeSelect(coordinator, entry)])


class SmartChargingModeSelect(SmartChargingEntity, SelectEntity):
    _attr_translation_key = "mode"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry.entry_id)
        solar_available = entry.data.get("solar_available", True)
        self._attr_options = [
            m for m in MODES if solar_available or m not in SOLAR_MODES
        ]
        self._attr_current_option = coordinator.active_mode

    async def async_select_option(self, option: str) -> None:
        self.coordinator.active_mode = option
        self._attr_current_option = option
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
```

```python
# custom_components/smart_charging/sensor.py
"""Diagnostic sensors owned by the integration."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity

from .const import DOMAIN
from .entity import SmartChargingEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SmartChargingStatusSensor(coordinator, entry)])


class SmartChargingStatusSensor(SmartChargingEntity, SensorEntity):
    _attr_translation_key = "status"

    @property
    def native_value(self) -> str:
        return self.coordinator.status
```

**Step 3: Run tests, iterate on entity setup order (coordinator's first refresh vs.
entity availability) until green**

Run: `pytest tests/test_init.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add custom_components/smart_charging/__init__.py custom_components/smart_charging/entity.py custom_components/smart_charging/select.py custom_components/smart_charging/sensor.py tests/test_init.py
git commit -m "feat: wire setup/unload entry and owned select/sensor entities"
```

---

## Task 16: Full-suite check and ruff pass

**Files:** none new — verification task.

**Step 1: Run the whole suite**

Run: `pytest -v`
Expected: All tests from Tasks 1–15 PASS.

**Step 2: Run ruff**

Run: `ruff check custom_components/ tests/` then `ruff format --check custom_components/ tests/`
Expected: No errors. Fix any it reports (unused imports, import order) and re-run.

**Step 3: Commit if ruff made changes**

```bash
git add -A
git commit -m "chore: ruff fixes across smart_charging scaffolding"
```

---

## After this plan

Follow-up work, in suggested order:
1. Open the dev-tooling design (skills/agents, GitHub Actions CI, issue labels) — deliberately
   deferred from this plan.
2. Reword `NF3` in `requirements.md` to describe the adapter abstraction rather than implying
   wrapper entities (flagged in the architecture design, Decision 2) — a behavioral-doc change,
   so open a GitHub issue first per the project's issue-first workflow.
3. Write UC05 (departure deadline) through UC10, then extend `resolution_rules.py` and add
   `profiles/auto.py` against them.
