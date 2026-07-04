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
    assert const.DEFAULT_POWER_RESPECT_PEAK is True
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
DEFAULT_POWER_RESPECT_PEAK = True
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
import pytest

from custom_components.smart_charging.control_cycle import (
    SmoothingWindow, resolve_voltage, apply_peak_clamp, apply_grid_ceiling_clamp,
    enforce_current_invariant, PeakBreachTracker,
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
    # The clamp must solve for the ampere that keeps net import at the target — using the
    # ampere actually flowing, not subtracting a "reduction" from the *requested* ampere
    # (that was a bug in an earlier draft: it under-clamped whenever desired_a > the
    # current already flowing, e.g. Captar requesting 32 A while only 6 A is flowing).
    # baseline = raw_net_w - raw_charger_w = import from everything EXCEPT the charger
    #          = 4380 - 1380 = 3000 W (household load, charger currently at 6 A = 1380 W)
    # target = effective_peak_limit_w - safety_margin_w = 4000 - 250 = 3750 W
    # max ampere the charger can draw while holding to target = (3750-3000)/230 = 3.26 A
    result = apply_peak_clamp(
        desired_a=32, raw_net_w=4380, raw_charger_w=1380, effective_peak_limit_w=4000,
        safety_margin_w=250, voltage=230, min_a=6, max_a=32,
    )
    assert result == pytest.approx(3.26, abs=0.05)


def test_r3_peak_clamp_no_reduction_when_within_target():
    result = apply_peak_clamp(
        desired_a=10, raw_net_w=500, raw_charger_w=0, effective_peak_limit_w=4000,
        safety_margin_w=250, voltage=230, min_a=6, max_a=32,
    )
    assert result == 10


def test_c4_grid_ceiling_clamp_bounds_below_ceiling():
    # ceiling_w = (40-2)*230 = 8740 W; baseline (excluding the charger's own 32A/7360W
    # draw) = 9360-7360 = 2000 W -> max ampere for the ceiling = (8740-2000)/230 = 29.3 A
    result = apply_grid_ceiling_clamp(
        desired_a=32, raw_net_w=9360, raw_charger_w=7360, ceiling_a=40, safety_offset_a=2,
        voltage=230,
    )
    assert result == pytest.approx(29.3, abs=0.05)


def test_c4_grid_ceiling_clamp_no_reduction_within_ceiling():
    result = apply_grid_ceiling_clamp(
        desired_a=10, raw_net_w=500, raw_charger_w=0, ceiling_a=40, safety_offset_a=2, voltage=230,
    )
    assert result == 10


def test_c1_invariant_zero_or_at_least_minimum():
    assert enforce_current_invariant(0, min_a=6, max_a=32) == 0
    assert enforce_current_invariant(3, min_a=6, max_a=32) == 0  # below min -> 0, never in-between
    assert enforce_current_invariant(6, min_a=6, max_a=32) == 6
    assert enforce_current_invariant(40, min_a=6, max_a=32) == 32  # capped at max


def test_r3_peak_breach_tracker_holds_at_minimum_during_grace_then_stops():
    # R3 AC: "stops (0 A) only when it is already at the minimum charging current and
    # net import still exceeds the target continuously for a grace period; a momentary
    # breach does not stop charging." So a below-minimum clamp result holds at the
    # minimum until the grace period elapses, then forces a stop.
    clock = [0.0]
    tracker = PeakBreachTracker(now_fn=lambda: clock[0])

    applied, stopped = tracker.evaluate(clamped_a=3.26, min_a=6, grace_s=120)
    assert applied == 6 and stopped is False  # momentary breach: hold at minimum

    clock[0] += 60
    applied, stopped = tracker.evaluate(clamped_a=3.26, min_a=6, grace_s=120)
    assert applied == 6 and stopped is False  # still within the grace period

    clock[0] += 61  # grace period (120s) now elapsed
    applied, stopped = tracker.evaluate(clamped_a=3.26, min_a=6, grace_s=120)
    assert applied == 0 and stopped is True


def test_r3_peak_breach_tracker_resets_once_headroom_returns():
    clock = [0.0]
    tracker = PeakBreachTracker(now_fn=lambda: clock[0])
    tracker.evaluate(clamped_a=3.26, min_a=6, grace_s=120)
    clock[0] += 60
    applied, stopped = tracker.evaluate(clamped_a=10, min_a=6, grace_s=120)  # headroom returns
    assert applied == 10 and stopped is False
    clock[0] += 61  # if the timer hadn't reset, this would now exceed the old grace window
    applied, stopped = tracker.evaluate(clamped_a=3.26, min_a=6, grace_s=120)
    assert applied == 6 and stopped is False  # fresh breach, grace restarts
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


def apply_peak_clamp(
    desired_a: float, raw_net_w: float, raw_charger_w: float, effective_peak_limit_w: float,
    safety_margin_w: float, voltage: float, min_a: float, max_a: float,
) -> float:
    """R3 — the highest ampere that keeps raw net import <= effective peak limit - margin.

    `raw_net_w` already includes the charger's own current draw (`raw_charger_w`), so the
    clamp must solve for the absolute ampere against the *baseline* (import excluding the
    charger), not subtract a "reduction" from `desired_a` — desired_a is a *request*
    (e.g. Captar always requests max_a), not the ampere presently flowing. Subtracting from
    the request instead of solving from the baseline under-clamps whenever the mode is
    asking for more current than is actually flowing right now.
    """
    target_w = effective_peak_limit_w - safety_margin_w
    baseline_w = raw_net_w - raw_charger_w  # import from everything except the charger itself
    max_a_for_target = (target_w - baseline_w) / voltage
    return max(min(desired_a, max_a_for_target, max_a), 0)


def apply_grid_ceiling_clamp(
    desired_a: float, raw_net_w: float, raw_charger_w: float, ceiling_a: float,
    safety_offset_a: float, voltage: float,
) -> float:
    """C4 — hard fuse-protection clamp; applies in every mode, even when R3 is disabled.

    Same baseline-relative math as `apply_peak_clamp`, and no grace period — a C4 breach
    clamps down immediately (UC03/UC04 exception flows: "without starting a cooldown").
    """
    ceiling_w = (ceiling_a - safety_offset_a) * voltage
    baseline_w = raw_net_w - raw_charger_w
    max_a_for_ceiling = (ceiling_w - baseline_w) / voltage
    return max(min(desired_a, max_a_for_ceiling), 0)


def enforce_current_invariant(current_a: float, min_a: float, max_a: float) -> float:
    """C1 — the final current is always 0, or a whole ampere within [min_a, max_a]."""
    import math

    if current_a < min_a:
        return 0
    return min(math.floor(current_a), max_a)


class PeakBreachTracker:
    """R3's grace-period stop rule: a clamp result below the minimum current holds at the
    minimum (accepting the momentary overshoot) until the breach has persisted continuously
    for the grace period, at which point it reports a stop so the coordinator can call the
    active mode's `notify_stopped_by_clamp()` and start its cooldown (R11). Resets the timer
    the moment headroom returns, per "a momentary breach does not stop charging."
    """

    def __init__(self, now_fn=None) -> None:
        import time

        self._now = now_fn or time.monotonic
        self._breach_started_at: float | None = None

    def evaluate(self, clamped_a: float, min_a: float, grace_s: float) -> tuple[float, bool]:
        if clamped_a >= min_a:
            self._breach_started_at = None
            return clamped_a, False
        if self._breach_started_at is None:
            self._breach_started_at = self._now()
        if self._now() - self._breach_started_at >= grace_s:
            return 0, True
        return min_a, False
```

**Step 3: Run tests, iterate on the peak/ceiling clamp math until they pass**

Run: `pytest tests/test_control_cycle.py -v`
Expected: PASS. The invariant that must hold for both clamps: they solve for the absolute
ampere against the baseline (`raw_net_w - raw_charger_w`), never subtract from the
*requested* ampere — verify this explicitly, since a plausible-looking-but-wrong
implementation (subtracting a shortfall from `desired_a`) passes a test that only checks
"some reduction happened" but silently breaches the peak whenever a mode requests more
than is currently flowing (this was caught in review of an earlier draft — see the comment
in `test_r3_peak_clamp_reduces_current_to_headroom`).

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
    """Smoothed + raw inputs for one control cycle, plus resolved lookups.

    `charger_w` is raw, not smoothed — entity-catalog.md's note on `sc_charger_power_w`
    is explicit that it "is not an operand of solar surplus" via the smoothed channel;
    only `net_w` and `solar_w` go through R10's rolling window (control-cycle.md step 2).
    Solar surplus is `charger_w - net_w` (UC01/UC02, entity-catalog.md line 128) — the
    charger's own draw is already included in net import, so a mode that computed
    surplus as `-net_w` alone would see its own charging current pull surplus back down
    every cycle it charges, oscillating instead of converging (caught in review of an
    earlier draft of this plan).
    """

    smoothed_net_w: float
    smoothed_solar_w: float
    charger_w: float
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
    def reset(self) -> None:
        pass

    def notify_stopped_by_clamp(self) -> None:
        pass  # already at 0 A; nothing to do

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


def make_readings(net_w, charger_w=0, soc=50, limit=80, status="connected"):
    # Surplus is charger_w - net_w (UC01/entity-catalog.md), not -net_w: charger_w=0
    # models "not currently charging," so these two formulas coincide for the tests
    # below that start from a stopped charger. Tests that continue an already-charging
    # session pass a nonzero charger_w explicitly — see test_r1_grid_fallback_* and
    # test_r1_post_surplus_hold_then_resumes_if_surplus_returns.
    return Readings(
        smoothed_net_w=net_w, smoothed_solar_w=0, charger_w=charger_w, charger_status=status,
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
    # charger_w=0 (not yet charging), net_w=-2300 (2300W exported) -> surplus = 0-(-2300) = 2300W = 10A
    readings = make_readings(net_w=-2300)
    result = mode.tick(readings, CONFIG)
    assert result == 10


def test_r1_grid_fallback_holds_at_minimum_when_surplus_below_minimum_current():
    clock = [0.0]
    mode = SolarMode(now_fn=lambda: clock[0])
    mode.tick(make_readings(net_w=-2300), CONFIG)  # start charging at 10A (2300W)
    # Now charging at 2300W (charger_w) while solar drops: surplus = 2300-2100 = 200W —
    # below the minimum current (6A=1380W) but still >= the 150W start threshold.
    readings = make_readings(net_w=2100, charger_w=2300)
    result = mode.tick(readings, CONFIG)
    assert result == CONFIG["min_a"]


def test_r1_surplus_formula_is_closed_loop_stable_across_cycles():
    # Regression test for a formula bug caught in review: using -net_w alone (ignoring
    # charger_w) makes the mode see its OWN charging draw as reducing surplus, causing it
    # to oscillate between 10A and the minimum every cycle instead of holding steady.
    # Steady state: solar = 2300W, no other household load, charging at 10A (2300W).
    clock = [0.0]
    mode = SolarMode(now_fn=lambda: clock[0])
    # Cycle 1: charger not yet drawing -> net_w = -2300 (all solar exported).
    assert mode.tick(make_readings(net_w=-2300, charger_w=0), CONFIG) == 10
    # Cycle 2: charger now draws the 2300W it was just set to -> net_w settles to 0.
    # Correct surplus = charger_w - net_w = 2300 - 0 = 2300 -> still 10A, not a drop to 6A.
    assert mode.tick(make_readings(net_w=0, charger_w=2300), CONFIG) == 10
    # Cycle 3: still steady -> still 10A.
    assert mode.tick(make_readings(net_w=0, charger_w=2300), CONFIG) == 10


def test_r1_post_surplus_hold_then_resumes_if_surplus_returns():
    clock = [0.0]
    mode = SolarMode(now_fn=lambda: clock[0])
    mode.tick(make_readings(net_w=-2300), CONFIG)  # charging at 10A (2300W)
    # Surplus drops to 100W (below the 150W threshold) while charger_w=2300 -> Hold.
    mode.tick(make_readings(net_w=2200, charger_w=2300), CONFIG)
    assert mode.state == "Hold"
    clock[0] += 60  # still within the 300s hold
    # Hold requested the minimum (6A=1380W); surplus returns to 2300W while charger_w=1380.
    result = mode.tick(make_readings(net_w=-920, charger_w=1380), CONFIG)
    assert result == 10
    assert mode.state == "Charging"


def test_r1_post_surplus_hold_elapses_then_stops_and_cooldown_starts():
    clock = [0.0]
    mode = SolarMode(now_fn=lambda: clock[0])
    mode.tick(make_readings(net_w=-2300), CONFIG)
    mode.tick(make_readings(net_w=2200, charger_w=2300), CONFIG)  # -> Hold
    clock[0] += 301  # hold period elapses
    result = mode.tick(make_readings(net_w=2200, charger_w=2300), CONFIG)
    assert result == 0
    assert mode.state == "Cooldown"


def test_r1_cooldown_blocks_restart_until_elapsed():
    clock = [0.0]
    mode = SolarMode(now_fn=lambda: clock[0])
    mode.tick(make_readings(net_w=-2300), CONFIG)
    mode.tick(make_readings(net_w=2200, charger_w=2300), CONFIG)
    clock[0] += 301
    mode.tick(make_readings(net_w=2200, charger_w=2300), CONFIG)  # -> Cooldown
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


def test_r7_soc_noise_does_not_resume_charging_while_socreached(monkeypatch=None):
    # A SOC sensor dipping fractionally below the limit due to noise must NOT resume
    # charging — R7 exits SocReached only when the limit itself changes, or on
    # unplug/replug, never merely because SOC re-reads below the limit at the same limit.
    clock = [0.0]
    mode = SolarMode(now_fn=lambda: clock[0])
    mode.tick(make_readings(net_w=-2300, soc=80, limit=80), CONFIG)
    assert mode.state == "SocReached"
    result = mode.tick(make_readings(net_w=-2300, soc=79.9, limit=80), CONFIG)  # noise dip
    assert result == 0
    assert mode.state == "SocReached"
    # The limit actually changing does clear it.
    result = mode.tick(make_readings(net_w=-2300, soc=79.9, limit=85), CONFIG)
    assert result == 10


def test_precondition_disconnected_forces_zero_and_resets():
    clock = [0.0]
    mode = SolarMode(now_fn=lambda: clock[0])
    mode.tick(make_readings(net_w=-2300), CONFIG)  # charging
    result = mode.tick(make_readings(net_w=2200, charger_w=2300, status="disconnected"), CONFIG)
    assert result == 0
    assert mode.state == "Idle"  # disconnect fully resets (R7: reset on unplug)


def test_r11_switching_mode_resets_timers():
    clock = [0.0]
    mode = SolarMode(now_fn=lambda: clock[0])
    mode.tick(make_readings(net_w=-2300), CONFIG)
    mode.tick(make_readings(net_w=2200, charger_w=2300), CONFIG)  # -> Hold
    mode.reset()
    assert mode.state == "Idle"


def test_r3_notify_stopped_by_clamp_starts_cooldown():
    # The coordinator calls this when a sustained R3 peak breach at the minimum current
    # forces a stop (control-cycle.md step 5 / PeakBreachTracker) — applies to every mode,
    # not just Captar/Power, since R3 is a coordinator-level invariant.
    clock = [0.0]
    mode = SolarMode(now_fn=lambda: clock[0])
    mode.tick(make_readings(net_w=-2300), CONFIG)  # charging
    mode.notify_stopped_by_clamp()
    assert mode.state == "Cooldown"
    assert mode.tick(make_readings(net_w=-2300), CONFIG) == 0
    clock[0] += 121
    assert mode.tick(make_readings(net_w=-2300), CONFIG) == 10
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
        self._limit_at_soc_reached: float | None = None

    def reset(self) -> None:
        self.state = "Idle"
        self._hold_started_at = None
        self._cooldown_started_at = None
        self._limit_at_soc_reached = None

    def notify_stopped_by_clamp(self) -> None:
        """Coordinator hook: a sustained R3 peak breach at the minimum current forced a
        stop (control-cycle.md step 5). R3 is a coordinator-level invariant that applies
        regardless of mode, so this mirrors Captar/Power's cooldown hook (Tasks 9-10)."""
        self.state = "Cooldown"
        self._cooldown_started_at = self._now()

    def _surplus_w(self, readings: Readings) -> float:
        # charger_w - net_w (UC01/entity-catalog.md) — NOT -net_w. net_w already includes
        # the charger's own draw, so -net_w alone would make the mode see its own charging
        # current as reducing surplus, oscillating instead of converging (see the
        # closed-loop regression test).
        return readings.charger_w - readings.smoothed_net_w

    def _set_point_a(self, readings: Readings, config: dict) -> float:
        surplus_w = self._surplus_w(readings)
        raw_a = surplus_w / config["voltage"]
        floored = math.floor(raw_a)
        return max(min(floored, config["max_a"]), config["min_a"])

    def tick(self, readings: Readings, config: dict) -> float:
        # Preconditions (UC01): car must be connected/charging; a disconnect (R7) resets
        # everything and exits to Idle rather than merely returning 0 for one cycle.
        if readings.charger_status not in ("connected", "charging"):
            self.reset()
            return 0

        if self.state == "SocReached":
            # R7: exits only when the active SOC limit itself changes, or on
            # unplug/replug (handled above) — NOT merely because SOC noise dips below
            # the same limit again, which would otherwise resume charging spuriously.
            if readings.active_soc_limit_percent != self._limit_at_soc_reached:
                self.state = "Idle"
            else:
                return 0

        if readings.ev_soc_percent >= readings.active_soc_limit_percent:
            self.state = "SocReached"
            self._limit_at_soc_reached = readings.active_soc_limit_percent
            return 0

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


def make_readings(net_w, charger_w=0, soc=50, limit=80, status="connected"):
    return Readings(
        smoothed_net_w=net_w, smoothed_solar_w=0, charger_w=charger_w, charger_status=status,
        ev_soc_percent=soc, active_soc_limit_percent=limit,
    )


def test_r2_idle_below_threshold():
    mode = SolarOnlyMode(now_fn=lambda: 0.0)
    assert mode.tick(make_readings(net_w=-1000), CONFIG) == 0  # 1000W < 1300W threshold


def test_r2_starts_and_tracks_surplus():
    mode = SolarOnlyMode(now_fn=lambda: 0.0)
    result = mode.tick(make_readings(net_w=-2300), CONFIG)  # 10A worth of surplus
    assert result == 10


def test_r2_surplus_formula_is_closed_loop_stable_across_cycles():
    # Same regression as Solar (Task 7): surplus is charger_w - net_w, not -net_w.
    clock = [0.0]
    mode = SolarOnlyMode(now_fn=lambda: clock[0])
    assert mode.tick(make_readings(net_w=-2300, charger_w=0), CONFIG) == 10
    assert mode.tick(make_readings(net_w=0, charger_w=2300), CONFIG) == 10  # holds, no dip


def test_r2_no_hold_immediate_stop_and_cooldown():
    clock = [0.0]
    mode = SolarOnlyMode(now_fn=lambda: clock[0])
    mode.tick(make_readings(net_w=-2300), CONFIG)
    # surplus drops to 100W while charger_w=2300 (charging) -> below threshold, immediate stop
    result = mode.tick(make_readings(net_w=2200, charger_w=2300), CONFIG)
    assert result == 0
    assert mode.state == "Cooldown"  # no Hold state exists for SolarOnly


def test_r2_never_falls_back_to_grid():
    mode = SolarOnlyMode(now_fn=lambda: 0.0)
    # surplus of 100W (below min current 6A=1380W) never floors at min_a; must be 0.
    result = mode.tick(make_readings(net_w=-100), CONFIG)
    assert result == 0


def test_precondition_disconnected_forces_zero_and_resets():
    clock = [0.0]
    mode = SolarOnlyMode(now_fn=lambda: clock[0])
    mode.tick(make_readings(net_w=-2300), CONFIG)
    result = mode.tick(make_readings(net_w=2200, charger_w=2300, status="disconnected"), CONFIG)
    assert result == 0
    assert mode.state == "Idle"


def test_r7_soc_noise_does_not_resume_charging_while_socreached():
    clock = [0.0]
    mode = SolarOnlyMode(now_fn=lambda: clock[0])
    mode.tick(make_readings(net_w=-2300, soc=80, limit=80), CONFIG)
    assert mode.state == "SocReached"
    result = mode.tick(make_readings(net_w=-2300, soc=79.9, limit=80), CONFIG)  # noise dip
    assert result == 0
    assert mode.state == "SocReached"
    result = mode.tick(make_readings(net_w=-2300, soc=79.9, limit=85), CONFIG)  # limit changes
    assert result == 10
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
        self._limit_at_soc_reached: float | None = None

    def reset(self) -> None:
        self.state = "Idle"
        self._cooldown_started_at = None
        self._limit_at_soc_reached = None

    def notify_stopped_by_clamp(self) -> None:
        self.state = "Cooldown"
        self._cooldown_started_at = self._now()

    def _surplus_w(self, readings: Readings) -> float:
        return readings.charger_w - readings.smoothed_net_w  # UC02/entity-catalog.md

    def _set_point_a(self, readings: Readings, config: dict) -> float:
        surplus_w = self._surplus_w(readings)
        raw_a = surplus_w / config["voltage"]
        floored = math.floor(raw_a)
        if floored < config["min_a"]:
            return 0  # SolarOnly never floors at the minimum via grid fallback
        return min(floored, config["max_a"])

    def tick(self, readings: Readings, config: dict) -> float:
        if readings.charger_status not in ("connected", "charging"):
            self.reset()
            return 0

        if self.state == "SocReached":
            if readings.active_soc_limit_percent != self._limit_at_soc_reached:
                self.state = "Idle"
            else:
                return 0

        if readings.ev_soc_percent >= readings.active_soc_limit_percent:
            self.state = "SocReached"
            self._limit_at_soc_reached = readings.active_soc_limit_percent
            return 0

        surplus_w = self._surplus_w(readings)
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


def make_readings(soc=50, limit=80, status="connected"):
    return Readings(
        smoothed_net_w=0, smoothed_solar_w=0, charger_w=0, charger_status=status,
        ev_soc_percent=soc, active_soc_limit_percent=limit,
    )


def test_r4_requests_maximum_current_when_below_limit():
    mode = CaptarMode(now_fn=lambda: 0.0)
    assert mode.tick(make_readings(soc=50, limit=80), CONFIG) == CONFIG["max_a"]


def test_r4_defaults_to_zero_at_or_above_limit():
    mode = CaptarMode(now_fn=lambda: 0.0)
    assert mode.tick(make_readings(soc=80, limit=80), CONFIG) == 0
    assert mode.state == "SocReached"


def test_r7_soc_noise_does_not_resume_charging_while_socreached():
    mode = CaptarMode(now_fn=lambda: 0.0)
    mode.tick(make_readings(soc=80, limit=80), CONFIG)
    assert mode.tick(make_readings(soc=79.9, limit=80), CONFIG) == 0  # noise dip, stays put
    assert mode.state == "SocReached"
    assert mode.tick(make_readings(soc=79.9, limit=85), CONFIG) == CONFIG["max_a"]  # limit changed


def test_precondition_disconnected_forces_zero_and_resets():
    mode = CaptarMode(now_fn=lambda: 0.0)
    mode.tick(make_readings(), CONFIG)  # Charging
    result = mode.tick(make_readings(status="disconnected"), CONFIG)
    assert result == 0
    assert mode.state == "Idle"


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
        self._limit_at_soc_reached: float | None = None

    def reset(self) -> None:
        self.state = "Idle"
        self._cooldown_started_at = None
        self._limit_at_soc_reached = None

    def notify_stopped_by_clamp(self) -> None:
        """Called by the coordinator on a sustained R3 breach at the minimum current."""
        self.state = "Cooldown"
        self._cooldown_started_at = self._now()

    def tick(self, readings: Readings, config: dict) -> float:
        if readings.charger_status not in ("connected", "charging"):
            self.reset()
            return 0

        if self.state == "SocReached":
            if readings.active_soc_limit_percent != self._limit_at_soc_reached:
                self.state = "Idle"
            else:
                return 0

        if readings.ev_soc_percent >= readings.active_soc_limit_percent:
            self.state = "SocReached"
            self._limit_at_soc_reached = readings.active_soc_limit_percent
            return 0

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


def make_readings(soc=50, limit=80, status="connected"):
    return Readings(
        smoothed_net_w=0, smoothed_solar_w=0, charger_w=0, charger_status=status,
        ev_soc_percent=soc, active_soc_limit_percent=limit,
    )


def test_r17_requests_configured_target_current():
    mode = PowerMode(now_fn=lambda: 0.0)
    assert mode.tick(make_readings(), CONFIG) == 10


def test_r17_stops_at_active_soc_limit():
    mode = PowerMode(now_fn=lambda: 0.0)
    assert mode.tick(make_readings(soc=80, limit=80), CONFIG) == 0
    assert mode.state == "SocReached"


def test_r7_soc_noise_does_not_resume_charging_while_socreached():
    mode = PowerMode(now_fn=lambda: 0.0)
    mode.tick(make_readings(soc=80, limit=80), CONFIG)
    assert mode.tick(make_readings(soc=79.9, limit=80), CONFIG) == 0
    assert mode.state == "SocReached"
    assert mode.tick(make_readings(soc=79.9, limit=85), CONFIG) == 10


def test_precondition_disconnected_forces_zero_and_resets():
    mode = PowerMode(now_fn=lambda: 0.0)
    mode.tick(make_readings(), CONFIG)
    result = mode.tick(make_readings(status="disconnected"), CONFIG)
    assert result == 0
    assert mode.state == "Idle"


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
        self._limit_at_soc_reached: float | None = None

    def reset(self) -> None:
        self.state = "Idle"
        self._cooldown_started_at = None
        self._limit_at_soc_reached = None

    def notify_stopped_by_clamp(self) -> None:
        self.state = "Cooldown"
        self._cooldown_started_at = self._now()

    def tick(self, readings: Readings, config: dict) -> float:
        if readings.charger_status not in ("connected", "charging"):
            self.reset()
            return 0

        if self.state == "SocReached":
            if readings.active_soc_limit_percent != self._limit_at_soc_reached:
                self.state = "Idle"
            else:
                return 0

        if readings.ev_soc_percent >= readings.active_soc_limit_percent:
            self.state = "SocReached"
            self._limit_at_soc_reached = readings.active_soc_limit_percent
            return 0

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
            # The form asks "what's your hardware's raw value for each canonical
            # state?" — user_input is {canonical_state: raw_value}. EnumAdapter
            # (Task 3) expects the opposite direction, {raw_value: canonical_state},
            # so invert it once here at storage time.
            charger_status_map = {raw: canonical for canonical, raw in user_input.items()}
            return self.async_create_entry(
                title="Smart Charging",
                data={
                    CONF_SOLAR_AVAILABLE: self._solar_available,
                    CONF_ROLE_MAPPING: self._role_mapping,
                    CONF_CHARGER_STATUS_MAP: charger_status_map,
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

The form's field names are the canonical states (`disconnected`/`connected`/`charging`);
the user fills in their hardware's raw value for each (e.g. `disconnected: "unplugged"`).
Storage inverts that to `{raw: canonical}` — the direction `EnumAdapter` (Task 3) actually
reads — so the test's expected `{"unplugged": "disconnected", ...}` shape falls straight
out of the inversion above rather than being reconciled by trial and error.

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
    c.CONF_POWER_RESPECT_PEAK: c.DEFAULT_POWER_RESPECT_PEAK,
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


def _configure_entry(mock_config_entry, missing=False):
    suffix = "missing" if missing else "net"
    mock_config_entry.data = {
        c.CONF_SOLAR_AVAILABLE: False,
        c.CONF_ROLE_MAPPING: {
            c.Role.NET_POWER: f"sensor.{'missing' if missing else 'net'}",
            c.Role.CHARGER_POWER: f"sensor.{'missing' if missing else 'charger_power'}",
            c.Role.CHARGER_STATUS: f"sensor.{'missing' if missing else 'charger_status'}",
            c.Role.EV_SOC: f"sensor.{'missing' if missing else 'ev_soc'}",
            c.Role.CHARGER_CURRENT: f"number.{'missing' if missing else 'charger_current'}",
            c.Role.MONTHLY_PEAK: f"sensor.{'missing' if missing else 'monthly_peak'}",
        },
        c.CONF_CHARGER_STATUS_MAP: {} if missing else {"connected": "connected"},
    }


async def test_coordinator_dispatches_to_off_when_mode_is_off(hass, mock_config_entry):
    hass.states.async_set("sensor.net", "0")
    hass.states.async_set("sensor.charger_power", "0")
    hass.states.async_set("sensor.charger_status", "connected")
    hass.states.async_set("sensor.ev_soc", "50")
    hass.states.async_set("number.charger_current", "0")
    hass.states.async_set("sensor.monthly_peak", "1.0")
    _configure_entry(mock_config_entry)
    calls = []
    hass.services.async_register("number", "set_value", lambda call: calls.append(call.data))

    coordinator = SmartChargingCoordinator(hass, mock_config_entry)
    coordinator.set_active_mode("Off")
    await coordinator.async_refresh()

    assert calls[-1] == {"entity_id": "number.charger_current", "value": 0}


async def test_coordinator_sets_fault_status_when_a_required_role_is_unavailable(
    hass, mock_config_entry
):
    _configure_entry(mock_config_entry, missing=True)
    coordinator = SmartChargingCoordinator(hass, mock_config_entry)
    coordinator.set_active_mode("Off")
    await coordinator.async_refresh()

    assert coordinator.status == "Fault"


async def test_coordinator_peak_clamp_uses_actual_charger_draw_not_the_request(
    hass, mock_config_entry
):
    # Regression test for the C-2 clamp bug caught in review: Captar requests max_a (32)
    # while the charger is currently only drawing 6A/1380W. Household load excluding the
    # charger is 3000W, so raw net = 3000+1380 = 4380W. With a 4000W effective peak limit
    # (monthly_peak sensor reads 4.0 kW) and a 250W safety margin, target = 3750W, so the
    # clamp must land near (3750-3000)/230 ~= 3.26A -> held at the minimum (6A) by the
    # grace-period tracker on this first breaching cycle, NOT left near the 32A request.
    hass.states.async_set("sensor.net", "4380")
    hass.states.async_set("sensor.charger_power", "1380")
    hass.states.async_set("sensor.charger_status", "connected")
    hass.states.async_set("sensor.ev_soc", "50")
    hass.states.async_set("number.charger_current", "6")
    hass.states.async_set("sensor.monthly_peak", "4.0")
    _configure_entry(mock_config_entry)
    calls = []
    hass.services.async_register("number", "set_value", lambda call: calls.append(call.data))

    coordinator = SmartChargingCoordinator(hass, mock_config_entry)
    coordinator.set_active_mode("Captar")
    await coordinator.async_refresh()

    assert calls[-1] == {"entity_id": "number.charger_current", "value": 6}


async def test_coordinator_switching_mode_resets_the_incoming_modes_state(
    hass, mock_config_entry
):
    hass.states.async_set("sensor.net", "-2300")  # 2300W solar surplus, not yet charging
    hass.states.async_set("sensor.charger_power", "0")
    hass.states.async_set("sensor.charger_status", "connected")
    hass.states.async_set("sensor.ev_soc", "50")
    hass.states.async_set("number.charger_current", "0")
    hass.states.async_set("sensor.monthly_peak", "1.0")
    _configure_entry(mock_config_entry)
    mock_config_entry.data[c.CONF_SOLAR_AVAILABLE] = True
    hass.services.async_register("number", "set_value", lambda call: None)

    coordinator = SmartChargingCoordinator(hass, mock_config_entry)
    coordinator.set_active_mode("Solar")
    await coordinator.async_refresh()  # Solar starts Charging
    assert coordinator._modes["Solar"].state == "Charging"

    coordinator.set_active_mode("Off")
    coordinator.set_active_mode("Solar")  # R11: the incoming mode must start fresh
    assert coordinator._modes["Solar"].state == "Idle"
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
    enforce_current_invariant, PeakBreachTracker,
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
        self._peak_breach_tracker = PeakBreachTracker()

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

    def set_active_mode(self, mode: str) -> None:
        """R11: switching the active mode resets the incoming mode's hold/cooldown
        timers so it starts fresh, and resets the shared R3 breach-grace timer, which
        is a coordinator-level (not mode-specific) invariant."""
        self._modes[mode].reset()
        self._peak_breach_tracker = PeakBreachTracker()
        self.active_mode = mode

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

        # Step 2: smoothing (R10) — net_w and solar_w only; charger_w is used raw
        # (entity-catalog.md's note on sc_charger_power_w: "not an operand of solar
        # surplus" via the smoothed channel).
        self._net_window.push(raw[c.Role.NET_POWER])
        self._solar_window.push(raw.get(c.Role.SOLAR_POWER) or 0)
        smoothed_net_w = self._net_window.value()
        smoothed_solar_w = self._solar_window.value()
        raw_charger_w = raw[c.Role.CHARGER_POWER]

        # Step 3: voltage resolution (NF4).
        voltage = resolve_voltage(
            raw.get(c.Role.GRID_VOLTAGE), opts.get(c.CONF_NOMINAL_VOLTAGE_V, c.DEFAULT_NOMINAL_VOLTAGE_V)
        )

        # Step 4: dispatch to the active mode module (NF1).
        limit = active_soc_limit(opts.get(c.CONF_ACTIVE_SOC_PERCENT, c.DEFAULT_ACTIVE_SOC_PERCENT))
        readings = Readings(
            smoothed_net_w=smoothed_net_w, smoothed_solar_w=smoothed_solar_w,
            charger_w=raw_charger_w, charger_status=raw[c.Role.CHARGER_STATUS],
            ev_soc_percent=raw[c.Role.EV_SOC], active_soc_limit_percent=limit,
        )
        mode = self._modes[self.active_mode]
        min_a = opts.get(c.CONF_MIN_CURRENT_A, c.DEFAULT_MIN_CURRENT_A)
        max_a = opts.get(c.CONF_MAX_CURRENT_A, c.DEFAULT_MAX_CURRENT_A)
        mode_config = self._mode_config(opts, voltage)
        desired_a = mode.tick(readings, mode_config)

        # Step 5: peak-protection clamp (R3) — skipped only for Power with peak disabled.
        # A clamp result below the minimum holds at the minimum until the configured
        # grace period elapses (PeakBreachTracker), per "a momentary breach does not
        # stop charging" — only a *sustained* breach at the minimum stops and starts
        # the active mode's cooldown via notify_stopped_by_clamp().
        skip_peak = self.active_mode == "Power" and not opts.get(c.CONF_POWER_RESPECT_PEAK, True)
        if not skip_peak:
            limit_w = effective_peak_limit(
                raw[c.Role.MONTHLY_PEAK] * 1000, opts.get(c.CONF_MAX_PEAK_KW, c.DEFAULT_MAX_PEAK_KW) * 1000
            )
            clamped_a = apply_peak_clamp(
                desired_a, raw[c.Role.NET_POWER], raw_charger_w, limit_w,
                opts.get(c.CONF_SAFETY_MARGIN_W, c.DEFAULT_SAFETY_MARGIN_W), voltage, min_a, max_a,
            )
            grace_s = opts.get(c.CONF_PEAK_GRACE_MIN, c.DEFAULT_PEAK_GRACE_MIN) * 60
            desired_a, stopped = self._peak_breach_tracker.evaluate(clamped_a, min_a, grace_s)
            if stopped:
                mode.notify_stopped_by_clamp()

        # Step 6: grid-supply-ceiling clamp (C4) — always applies, no grace period; a C4
        # breach clamps down immediately without starting a cooldown (UC03/UC04).
        desired_a = apply_grid_ceiling_clamp(
            desired_a, raw[c.Role.NET_POWER], raw_charger_w,
            opts.get(c.CONF_GRID_SUPPLY_CEILING_A, c.DEFAULT_GRID_SUPPLY_CEILING_A),
            opts.get(c.CONF_GRID_SAFETY_OFFSET_A, c.DEFAULT_GRID_SAFETY_OFFSET_A), voltage,
        )

        # Step 7: invariants (C1). R11 cooldown/hold state lives inside each mode module.
        final_a = enforce_current_invariant(desired_a, min_a, max_a)

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

Note: Captar and Power each have their own `cooldown_s` option
(`captar_cooldown_min`/`power_cooldown_min`) distinct from the solar modes' shared one —
`_mode_config` above only wires the solar cooldown for brevity; when implementing, select
the right cooldown option by `self.active_mode` (or pass all three and let each mode read
its own key) so Captar/Power don't end up running the solar cooldown by mistake.

These tests are a minimal smoke test of the wiring, not full coverage of every mode/clamp
interaction — Tasks 6–10 already cover each mode/clamp in isolation, and the C-2 regression
test above specifically guards against a real bug caught in review (an earlier draft's
clamp math used the *requested* current as the baseline instead of the current actually
flowing, which under-clamped Captar/Power and could breach the peak).

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
        self.coordinator.set_active_mode(option)  # R11: resets the incoming mode's timers
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
