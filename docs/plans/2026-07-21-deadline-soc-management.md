# Deadline & SOC Management Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the active-SOC-limit resolution (R7 rows 1–2, UC06/UC07), add the Deadline Engine
(R5/R14/R15, UC05), the Capability-Gate Engine (R18), and the `Auto` profile (R16) — the pieces that
let deadline urgency, the solar step-up, and the solar-reserve overnight cap actually run, and let
the system select modes on its own instead of only under `Manual`.

**Architecture:** Extends the SOC-Target and Billing-Protection engines already shipped
(`engines/soc_target.py`, `engines/billing_protection.py`); adds two new engines
(`engines/deadline.py`, `engines/capability_gate.py`) to the existing `engines/` package (ADR-0010)
and one new profile (`profiles/auto.py`) to the existing `profiles/` package (ADR-0002); adds two new
owned-entity platforms (`time.py`, `switch.py`) alongside `select.py`/`sensor.py`; wires all of it into
`coordinator.py` (M1). See
[`2026-07-21-deadline-soc-management-design.md`](2026-07-21-deadline-soc-management-design.md) for
the full design and every function's exact contract.

**Tech Stack:** Same as prior slices — Python ≥3.12, Home Assistant, `pytest`,
`pytest-homeassistant-custom-component` (HA harness, test-only per ADR-0009), `ruff`. Pure logic
(`profiles/`, `engines/`) uses plain pytest; adapters/coordinator/entities/config-flow use the HA
harness (run on WSL per this project's Windows-checkout convention).

**Model:** Per CLAUDE.md, this is development work — execute on **Sonnet**.

---

## Conventions used throughout

Same as `2026-07-20-captar.md`'s conventions section (package root, tests-mirror-1:1, canonical
states, ADR-0007 fault rule, ADR-0006 two-distinct-clamps rule, engine purity, commit-after-green,
re-check `git branch --show-current` before every commit). Stateful pure functions take their prior
state and `now`/`current_month`-style clock values as explicit parameters, injected by the
coordinator — never called inside `engines/`/`profiles/`.

---

## Phase 1 — Pure engines & profile (plain pytest, no HA)

### Task 1.1: Capability-Gate Engine (E9)

**Files:**
- Create: `custom_components/smart_charging/engines/capability_gate.py`
- Test: `tests/engines/test_capability_gate.py`

**Step 1: Failing tests**

```python
"""Plain-pytest tests for the Capability-Gate Engine (E9, R18)."""

from custom_components.smart_charging.const import MODE_CAPTAR, MODE_OFF, MODE_POWER, MODE_SOLAR, MODE_SOLAR_ONLY
from custom_components.smart_charging.engines.capability_gate import resolve_available_modes


def test_neither_capability_only_off_and_power():
    assert resolve_available_modes(solar_available=False, captar_available=False) == {MODE_OFF, MODE_POWER}


def test_solar_only_adds_both_solar_modes():
    modes = resolve_available_modes(solar_available=True, captar_available=False)
    assert modes == {MODE_OFF, MODE_POWER, MODE_SOLAR, MODE_SOLAR_ONLY}


def test_captar_only_adds_captar():
    modes = resolve_available_modes(solar_available=False, captar_available=True)
    assert modes == {MODE_OFF, MODE_POWER, MODE_CAPTAR}


def test_both_capabilities_present_offers_everything():
    modes = resolve_available_modes(solar_available=True, captar_available=True)
    assert modes == {MODE_OFF, MODE_POWER, MODE_SOLAR, MODE_SOLAR_ONLY, MODE_CAPTAR}
```

**Step 2: Run** → `ImportError`. **Step 3: Implement** per design doc §7. **Step 4: Run** → PASS.
**Step 5: Commit**

```bash
git add custom_components/smart_charging/engines/capability_gate.py tests/engines/test_capability_gate.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add Capability-Gate engine (E9, R18)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 1.2: SOC-Target Engine — full three-row resolution (E3)

**Files:**
- Modify: `custom_components/smart_charging/engines/soc_target.py`
- Modify: `tests/engines/test_soc_target.py`

**Step 1: Failing tests**

```python
"""Additions: R7's full three-row table, R8's step-up lifecycle, R9's reserve trigger."""

from custom_components.smart_charging.engines.soc_target import (
    SolarStepUpState,
    resolve_active_soc_limit,
    resolve_solar_reserve_active,
    resolve_solar_step_up,
)

# --- resolve_active_soc_limit: priority order ---

def test_row1_reserve_wins_over_everything():
    state = SolarStepUpState(stepped_pct=90.0)
    assert resolve_active_soc_limit(80.0, solar_reserve_active=True, solar_reserve_soc=60.0, step_up_state=state) == 60.0


def test_row2_step_up_wins_over_default_when_reserve_inactive():
    state = SolarStepUpState(stepped_pct=90.0)
    assert resolve_active_soc_limit(80.0, solar_reserve_active=False, solar_reserve_soc=60.0, step_up_state=state) == 90.0


def test_row3_default_when_neither_reserve_nor_step_up():
    assert resolve_active_soc_limit(80.0, solar_reserve_active=False, solar_reserve_soc=60.0, step_up_state=SolarStepUpState()) == 80.0


# --- resolve_solar_step_up: lifecycle (R8/UC06) ---

def test_no_step_while_soc_outside_threshold():
    limit, state = resolve_solar_step_up(
        SolarStepUpState(), is_solar_mode_charging=True, soc=70.0, default_limit=80.0,
        step_threshold_pp=2.0, step_pp=5.0, max_solar_soc=100.0,
    )
    assert limit == 80.0
    assert state.stepped_pct is None


def test_steps_up_once_within_threshold():
    limit, state = resolve_solar_step_up(
        SolarStepUpState(), is_solar_mode_charging=True, soc=78.5, default_limit=80.0,
        step_threshold_pp=2.0, step_pp=5.0, max_solar_soc=100.0,
    )
    assert limit == 85.0
    assert state.stepped_pct == 85.0


def test_further_step_clamps_to_maximum():
    limit, state = resolve_solar_step_up(
        SolarStepUpState(stepped_pct=98.0), is_solar_mode_charging=True, soc=97.0, default_limit=80.0,
        step_threshold_pp=2.0, step_pp=5.0, max_solar_soc=100.0,
    )
    assert limit == 100.0  # 98 + 5 = 103, clamped (2a)
    assert state.stepped_pct == 100.0


def test_no_further_step_once_already_at_maximum():
    limit, state = resolve_solar_step_up(
        SolarStepUpState(stepped_pct=100.0), is_solar_mode_charging=True, soc=99.0, default_limit=80.0,
        step_threshold_pp=2.0, step_pp=5.0, max_solar_soc=100.0,
    )
    assert limit == 100.0
    assert state.stepped_pct == 100.0


def test_step_up_preserved_when_still_solar_charging_outside_threshold_again():
    # SOC moved away from the new limit -- still no reset (only leaving solar/disconnect resets, R7).
    limit, state = resolve_solar_step_up(
        SolarStepUpState(stepped_pct=85.0), is_solar_mode_charging=True, soc=81.0, default_limit=80.0,
        step_threshold_pp=2.0, step_pp=5.0, max_solar_soc=100.0,
    )
    assert limit == 85.0
    assert state.stepped_pct == 85.0


def test_clears_when_no_longer_solar_charging():
    # UC06 exception flow: active mode leaves solar (Auto escalation, manual switch) or disconnect --
    # the caller passes is_solar_mode_charging=False for both.
    limit, state = resolve_solar_step_up(
        SolarStepUpState(stepped_pct=85.0), is_solar_mode_charging=False, soc=81.0, default_limit=80.0,
        step_threshold_pp=2.0, step_pp=5.0, max_solar_soc=100.0,
    )
    assert limit == 80.0
    assert state.stepped_pct is None


# --- resolve_solar_reserve_active: R9/UC07's five-way AND ---

def test_reserve_active_when_all_conditions_hold():
    assert resolve_solar_reserve_active(
        profile="Auto", home_day_flag=True, sun_is_down=True,
        forecast_kwh=15.0, forecast_threshold_kwh=12.0, deadline_tomorrow_resolved=False,
    ) is True


def test_reserve_inactive_under_manual():
    assert resolve_solar_reserve_active(
        profile="Manual", home_day_flag=True, sun_is_down=True,
        forecast_kwh=15.0, forecast_threshold_kwh=12.0, deadline_tomorrow_resolved=False,
    ) is False


def test_reserve_inactive_when_deadline_resolved_for_tomorrow():
    # R9/UC07: mutually exclusive with a departure deadline resolved for tomorrow.
    assert resolve_solar_reserve_active(
        profile="Auto", home_day_flag=True, sun_is_down=True,
        forecast_kwh=15.0, forecast_threshold_kwh=12.0, deadline_tomorrow_resolved=True,
    ) is False


def test_reserve_inactive_when_forecast_at_or_below_threshold():
    assert resolve_solar_reserve_active(
        profile="Auto", home_day_flag=True, sun_is_down=True,
        forecast_kwh=12.0, forecast_threshold_kwh=12.0, deadline_tomorrow_resolved=False,
    ) is False


def test_reserve_inactive_when_home_day_flag_clear():
    assert resolve_solar_reserve_active(
        profile="Auto", home_day_flag=False, sun_is_down=True,
        forecast_kwh=15.0, forecast_threshold_kwh=12.0, deadline_tomorrow_resolved=False,
    ) is False


def test_reserve_inactive_while_sun_is_up():
    assert resolve_solar_reserve_active(
        profile="Auto", home_day_flag=True, sun_is_down=False,
        forecast_kwh=15.0, forecast_threshold_kwh=12.0, deadline_tomorrow_resolved=False,
    ) is False
```

**Step 2: Run** → `ImportError`. **Step 3: Implement** per design doc §5 (import `PROFILE_AUTO` from
`const.py` — add it alongside `PROFILE_MANUAL` in the same task, see Task 4.1's constants note; both
constants are needed here and by `profiles/auto.py`, Task 1.6, so define them once in `const.py` as
part of this task). **Step 4: Run** → PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/engines/soc_target.py custom_components/smart_charging/const.py tests/engines/test_soc_target.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: complete SOC-Target engine -- full three-row resolution (E3, R7/R8/R9)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 1.3: Deadline Engine — departure-deadline resolution (E4, R14)

**Files:**
- Create: `custom_components/smart_charging/engines/deadline.py`
- Test: `tests/engines/test_deadline.py`

**Step 1: Failing tests**

```python
"""Plain-pytest tests for the Deadline Engine's departure-deadline resolution (E4, R14)."""

from datetime import time

from custom_components.smart_charging.engines.deadline import resolve_departure_deadline

MON_DEFAULT = time(6, 0)


def test_external_sensor_wins_over_everything():
    assert resolve_departure_deadline(
        external_configured=True, external=time(7, 30), is_holiday=True, holiday_override=time(9, 0),
        home_day_flag=True, home_day_override=time(10, 0), day_of_week_default=MON_DEFAULT,
    ) == time(7, 30)


def test_external_sensor_configured_and_currently_no_deadline_still_wins():
    # R14: the external sensor takes precedence over all configured values, including
    # when it currently reads "no deadline" -- row 2 (holiday) must NOT be consulted.
    assert resolve_departure_deadline(
        external_configured=True, external=None, is_holiday=True, holiday_override=time(9, 0),
        home_day_flag=True, home_day_override=time(10, 0), day_of_week_default=MON_DEFAULT,
    ) is None


def test_external_sensor_not_configured_falls_through_to_holiday():
    assert resolve_departure_deadline(
        external_configured=False, external=None, is_holiday=True, holiday_override=time(9, 0),
        home_day_flag=True, home_day_override=time(10, 0), day_of_week_default=MON_DEFAULT,
    ) == time(9, 0)


def test_holiday_wins_over_home_day_when_both_apply():
    assert resolve_departure_deadline(
        external_configured=False, external=None, is_holiday=True, holiday_override=time(9, 0),
        home_day_flag=True, home_day_override=time(10, 0), day_of_week_default=MON_DEFAULT,
    ) == time(9, 0)


def test_home_day_wins_when_not_a_holiday():
    assert resolve_departure_deadline(
        external_configured=False, external=None, is_holiday=False, holiday_override=time(9, 0),
        home_day_flag=True, home_day_override=time(10, 0), day_of_week_default=MON_DEFAULT,
    ) == time(10, 0)


def test_falls_through_to_day_of_week_default():
    assert resolve_departure_deadline(
        external_configured=False, external=None, is_holiday=False, holiday_override=None,
        home_day_flag=False, home_day_override=None, day_of_week_default=MON_DEFAULT,
    ) == MON_DEFAULT


def test_day_of_week_default_may_be_no_deadline():
    # Weekend default (requirements.md R14: "no deadline Sat-Sun").
    assert resolve_departure_deadline(
        external_configured=False, external=None, is_holiday=False, holiday_override=None,
        home_day_flag=False, home_day_override=None, day_of_week_default=None,
    ) is None


def test_holiday_override_itself_may_resolve_to_no_deadline():
    assert resolve_departure_deadline(
        external_configured=False, external=None, is_holiday=True, holiday_override=None,
        home_day_flag=False, home_day_override=None, day_of_week_default=MON_DEFAULT,
    ) is None


def test_home_day_override_itself_may_resolve_to_no_deadline():
    assert resolve_departure_deadline(
        external_configured=False, external=None, is_holiday=False, holiday_override=None,
        home_day_flag=True, home_day_override=None, day_of_week_default=MON_DEFAULT,
    ) is None
```

**Step 2: Run** → `ImportError`. **Step 3: Implement** per design doc §6's `resolve_departure_deadline`.
**Step 4: Run** → PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/engines/deadline.py tests/engines/test_deadline.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add Deadline engine -- departure-deadline resolution (E4, R14)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 1.4: Deadline Engine — required current & urgency (E4, R5/R15)

**Files:**
- Modify: `custom_components/smart_charging/engines/deadline.py`
- Modify: `tests/engines/test_deadline.py`

**Step 1: Failing tests**

```python
"""Additions: R5/R15's required-current formula and the Normal/Urgent/Unreachable boundaries
(UC05's state model)."""

from datetime import datetime, time

from custom_components.smart_charging.engines.deadline import resolve_required_current

NOW = datetime(2026, 7, 21, 22, 0)  # 22:00
DEADLINE = time(6, 0)  # next-day 06:00 -- 8 hours remaining


def test_no_deadline_never_urgent():
    result = resolve_required_current(
        deadline=None, now=NOW, soc=50.0, active_soc_limit=80.0, battery_capacity_kwh=75.0,
        voltage=230.0, baseline_desired_a=6.0, maximum_permitted_rate_a=32.0,
    )
    assert result.required_a is None
    assert result.urgent is False
    assert result.unreachable is False


def test_required_current_formula_worked_example():
    # energy = 75 kWh * (80-50)/100 = 22.5 kWh over 8h -> 2812.5 W -> /230V = 12.228... A
    result = resolve_required_current(
        deadline=DEADLINE, now=NOW, soc=50.0, active_soc_limit=80.0, battery_capacity_kwh=75.0,
        voltage=230.0, baseline_desired_a=6.0, maximum_permitted_rate_a=32.0,
    )
    assert result.required_a == pytest.approx(12.228, abs=0.01)


def test_normal_when_required_at_or_below_baseline():
    result = resolve_required_current(
        deadline=DEADLINE, now=NOW, soc=79.0, active_soc_limit=80.0, battery_capacity_kwh=75.0,
        voltage=230.0, baseline_desired_a=6.0, maximum_permitted_rate_a=32.0,
    )
    assert result.urgent is False
    assert result.unreachable is False


def test_urgent_when_required_between_baseline_and_max_rate():
    result = resolve_required_current(
        deadline=DEADLINE, now=NOW, soc=50.0, active_soc_limit=80.0, battery_capacity_kwh=75.0,
        voltage=230.0, baseline_desired_a=6.0, maximum_permitted_rate_a=32.0,
    )
    assert result.urgent is True
    assert result.unreachable is False


def test_unreachable_when_required_exceeds_max_rate():
    result = resolve_required_current(
        deadline=time(22, 5), now=NOW, soc=10.0, active_soc_limit=80.0, battery_capacity_kwh=75.0,
        voltage=230.0, baseline_desired_a=6.0, maximum_permitted_rate_a=32.0,
    )
    assert result.unreachable is True


def test_deadline_already_passed_saturates_instead_of_dividing_by_zero():
    result = resolve_required_current(
        deadline=time(21, 0), now=NOW, soc=50.0, active_soc_limit=80.0, battery_capacity_kwh=75.0,
        voltage=230.0, baseline_desired_a=6.0, maximum_permitted_rate_a=32.0,
    )
    assert result.unreachable is True  # deadline in the past -> max urgency, not an exception
```

**Step 2: Run** → `ImportError`/FAIL. **Step 3: Implement** per design doc §6's
`resolve_required_current`. **Step 4: Run** → PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/engines/deadline.py tests/engines/test_deadline.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add required-current/urgency computation to Deadline engine (E4, R5/R15)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 1.5: Effective-peak-limit row 1 (extends Billing-Protection, E5)

**Files:**
- Modify: `custom_components/smart_charging/engines/billing_protection.py`
- Modify: `tests/engines/test_billing_protection.py`

**Step 1: Failing tests**

```python
"""Addition: row 1 of the effective-peak-limit rule (deadline urgency, R5/C3) -- row 2
(unchanged) is only reached when urgent=False."""

def test_urgency_raises_to_the_maximum_peak_regardless_of_monthly_peak():
    assert resolve_effective_peak_limit(monthly_peak_kw=1.0, max_peak_kw=4.0, urgent=True) == 4.0


def test_urgency_never_exceeds_the_maximum_peak():
    assert resolve_effective_peak_limit(monthly_peak_kw=1.0, max_peak_kw=4.0, urgent=True) <= 4.0


def test_row2_unchanged_when_not_urgent():
    assert resolve_effective_peak_limit(monthly_peak_kw=3.0, max_peak_kw=4.0, urgent=False) == 3.0
    assert resolve_effective_peak_limit(monthly_peak_kw=5.0, max_peak_kw=4.0, urgent=False) == 4.0
```

Every existing call to `resolve_effective_peak_limit` in `tests/engines/test_billing_protection.py`
now needs `urgent=False` added — a required keyword, not defaulted, so no call site can silently
skip the new row (design doc §9).

**Step 2: Run** → `TypeError` (missing argument) on every existing call site. **Step 3: Implement**
per design doc §9; update every existing test call with `urgent=False`. **Step 4: Run** → PASS.
**Step 5: Commit**

```bash
git add custom_components/smart_charging/engines/billing_protection.py tests/engines/test_billing_protection.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add row-1 (deadline-urgency raise) to the effective-peak-limit rule (E5, R5)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 1.6: `Auto` profile (E2)

**Files:**
- Create: `custom_components/smart_charging/profiles/auto.py`
- Test: `tests/profiles/test_auto.py`

**Step 1: Failing tests**

```python
"""Plain-pytest tests for the Auto profile's mode-selection (E2, R16)."""

from custom_components.smart_charging.const import MODE_CAPTAR, MODE_OFF, MODE_POWER, MODE_SOLAR
from custom_components.smart_charging.profiles.auto import select_mode

BASE = dict(
    soc=50.0, active_soc_limit=80.0, urgent=False, unreachable=False,
    solar_capability_present=True, sun_is_up=False, solar_surplus_sufficient=False,
    sun_is_down=True, low_tariff_active=True, solar_reserve_active=False,
)


def test_row1_soc_at_limit_selects_off():
    assert select_mode(**{**BASE, "soc": 80.0}, available_modes=frozenset({MODE_OFF, MODE_POWER})) == MODE_OFF


def test_row2_urgent_escalates_to_captar_when_available():
    modes = frozenset({MODE_OFF, MODE_POWER, MODE_CAPTAR})
    assert select_mode(**{**BASE, "urgent": True}, available_modes=modes) == MODE_CAPTAR


def test_row2_urgent_falls_back_to_power_when_captar_unavailable():
    modes = frozenset({MODE_OFF, MODE_POWER})
    assert select_mode(**{**BASE, "urgent": True}, available_modes=modes) == MODE_POWER


def test_row2_unreachable_also_escalates():
    modes = frozenset({MODE_OFF, MODE_POWER, MODE_CAPTAR})
    assert select_mode(**{**BASE, "unreachable": True}, available_modes=modes) == MODE_CAPTAR


def test_row3_solar_surplus_selects_solar():
    modes = frozenset({MODE_OFF, MODE_POWER, MODE_SOLAR})
    kwargs = {**BASE, "sun_is_up": True, "solar_surplus_sufficient": True, "sun_is_down": False}
    assert select_mode(**kwargs, available_modes=modes) == MODE_SOLAR


def test_row4_overnight_top_up_selects_captar():
    modes = frozenset({MODE_OFF, MODE_POWER, MODE_CAPTAR})
    assert select_mode(**BASE, available_modes=modes) == MODE_CAPTAR


def test_row4_withheld_when_captar_unavailable_falls_to_off():
    # R18: absent CapTar, row 4 never matches -- falls through to row 5 (Off), NOT Power.
    modes = frozenset({MODE_OFF, MODE_POWER})
    assert select_mode(**BASE, available_modes=modes) == MODE_OFF


def test_row4_withheld_when_solar_reserve_active():
    modes = frozenset({MODE_OFF, MODE_POWER, MODE_CAPTAR})
    assert select_mode(**{**BASE, "solar_reserve_active": True}, available_modes=modes) == MODE_OFF


def test_row4_withheld_when_low_tariff_inactive():
    modes = frozenset({MODE_OFF, MODE_POWER, MODE_CAPTAR})
    assert select_mode(**{**BASE, "low_tariff_active": False}, available_modes=modes) == MODE_OFF


def test_row5_otherwise_off():
    modes = frozenset({MODE_OFF, MODE_POWER})
    kwargs = {**BASE, "sun_is_down": False, "low_tariff_active": False}
    assert select_mode(**kwargs, available_modes=modes) == MODE_OFF


def test_row3_never_selects_solar_without_the_capability():
    # available_modes already excludes Solar when the capability is absent (E9), but this
    # also asserts the row's own solar_capability_present guard independently.
    modes = frozenset({MODE_OFF, MODE_POWER})
    kwargs = {**BASE, "solar_capability_present": False, "sun_is_up": True, "solar_surplus_sufficient": True, "sun_is_down": False}
    assert select_mode(**kwargs, available_modes=modes) != MODE_SOLAR
```

**Step 2: Run** → `ImportError`. **Step 3: Implement** per design doc §8. **Step 4: Run** → PASS.
**Step 5: Commit**

```bash
git add custom_components/smart_charging/profiles/auto.py tests/profiles/test_auto.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add Auto profile mode-selection (E2, R16)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

> **⎔ Phase 1 checkpoint:** `pytest tests/engines tests/profiles -v` all green; grep-confirm no
> `import homeassistant` and no cross-engine import under `engines/`/`profiles/`. Every R7/R8/R9/R14/
> R15/R16/R18 acceptance criterion has a corresponding test above.

---

## Phase 2 — Adapters (HA harness, RA1 extension)

### Task 2.1: `battery_capacity`, `departure_external`, `home_day_external`, `solar_forecast` adapter roles

**Files:**
- Modify: `custom_components/smart_charging/const.py` (four new `ROLE_*` + `CONF_*_ENTITY` constants,
  design doc §3)
- Modify: `custom_components/smart_charging/adapters/factory.py`
- Modify: `tests/adapters/test_factory.py`

**Step 1: Failing tests** — one pair per role, mirroring the existing `grid_voltage`/`ev_soc`
optional-role tests:

```python
async def test_factory_builds_battery_capacity_role_when_configured(hass):
    data = _data()
    data[CONF_BATTERY_CAPACITY_ENTITY] = "sensor.ev_battery_capacity"
    adapters = build_adapters(hass, data)
    assert isinstance(adapters[ROLE_BATTERY_CAPACITY], NumericReadAdapter)


async def test_battery_capacity_role_absent_when_not_configured(hass):
    assert ROLE_BATTERY_CAPACITY not in build_adapters(hass, _data())

# ... same shape for departure_external (StatusReadAdapter or a plain read adapter -- time-typed,
# see design doc §4 note: use whichever existing adapter class already reads a non-numeric native
# value; if none fits a `time` value, extend adapters/base.py minimally, flagging this in review
# rather than inventing a new adapter class silently), home_day_external (bool -- NumericReadAdapter
# or a boolean-typed equivalent, same judgment call), and solar_forecast (NumericReadAdapter, kWh).
```

**Step 2: Run** → fails (constants don't exist). **Step 3: Implement** — add the four `CONF_*_ENTITY`
constants and four `ROLE_*` constants to `const.py`; extend `build_adapters` with the same
`if data.get(CONF_..._ENTITY): adapters[ROLE_...] = ...Adapter(...)` optional pattern `grid_voltage`
already uses. **Flag for review:** if `departure_external`/`home_day_external` don't cleanly fit
`NumericReadAdapter`/`StatusReadAdapter`, this task's implementer states the gap explicitly (e.g. a
minimal `adapters/base.py` addition) rather than silently reshaping an existing adapter class —
this is a plain data-typing detail, not a new architectural decision, but it must be visible in the
PR. **Step 4: Run** → PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/const.py custom_components/smart_charging/adapters/factory.py tests/adapters/test_factory.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add battery_capacity, departure_external, home_day_external, solar_forecast adapter roles (RA1 extension)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

> **⎔ Phase 2 checkpoint:** `pytest tests/adapters -v` green.

---

## Phase 3 — Config/options flow (ADR-0005 extension)

### Task 3.1: New config keys

**Files:** Modify `custom_components/smart_charging/const.py`

**Step 1: Append** every `CONF_*`/`DEFAULT_*` constant from design doc §3 (`CONF_SOLAR_FORECAST_ENTITY`
into DATA; `CONF_BATTERY_CAPACITY_KWH`, `CONF_MAX_SOLAR_SOC`, `CONF_SOLAR_STEP_PP`,
`CONF_SOLAR_STEP_THRESHOLD_PP`, `CONF_SOLAR_RESERVE_SOC`, `CONF_SOLAR_FORECAST_THRESHOLD_KWH` into
OPTIONS, each with its `DEFAULT_*`). **Step 2: Commit**

```bash
git add custom_components/smart_charging/const.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add config keys for battery capacity, solar step-up, and solar-reserve cap (R8/R9/R15)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 3.2: Extend the config/options flow

**Files:**
- Modify: `custom_components/smart_charging/config_flow.py`
- Modify: `tests/test_config_flow.py`

**Step 1: Failing tests**

```python
async def test_solar_forecast_required_when_solar_installed(hass):
    result = await _run_user_flow(hass, overrides={CONF_SOLAR_INSTALLED: True}, omit=[CONF_SOLAR_FORECAST_ENTITY])
    assert result["type"] == FlowResultType.FORM
    assert result["errors"][CONF_SOLAR_FORECAST_ENTITY] == "required_when_solar_installed"


async def test_solar_forecast_not_required_when_solar_not_installed(hass):
    result = await _run_user_flow(hass, overrides={CONF_SOLAR_INSTALLED: False}, omit=[CONF_SOLAR_FORECAST_ENTITY])
    assert result["type"] == FlowResultType.CREATE_ENTRY


async def test_new_thresholds_seeded_with_defaults(hass):
    result = await _run_user_flow(hass)
    assert result["options"][CONF_BATTERY_CAPACITY_KWH] == DEFAULT_BATTERY_CAPACITY_KWH
    assert result["options"][CONF_MAX_SOLAR_SOC] == DEFAULT_MAX_SOLAR_SOC
    assert result["options"][CONF_SOLAR_STEP_PP] == DEFAULT_SOLAR_STEP_PP
    assert result["options"][CONF_SOLAR_STEP_THRESHOLD_PP] == DEFAULT_SOLAR_STEP_THRESHOLD_PP
    assert result["options"][CONF_SOLAR_RESERVE_SOC] == DEFAULT_SOLAR_RESERVE_SOC
    assert result["options"][CONF_SOLAR_FORECAST_THRESHOLD_KWH] == DEFAULT_SOLAR_FORECAST_THRESHOLD_KWH


async def test_options_flow_edits_the_new_thresholds(hass):
    entry = await _create_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**_current_options(entry), CONF_SOLAR_RESERVE_SOC: 55.0}
    )
    assert entry.options[CONF_SOLAR_RESERVE_SOC] == 55.0
```

**Step 2: Run** → FAIL. **Step 3: Implement** — add `vol.Optional(CONF_SOLAR_FORECAST_ENTITY):
_entity("sensor")` to `MAPPING_SCHEMA`; extend the existing `_ev_soc_missing_error`-style guard
function (or add a sibling `_solar_forecast_missing_error`, composed the same way) so
`CONF_SOLAR_INSTALLED=True` without `CONF_SOLAR_FORECAST_ENTITY` is rejected with
`required_when_solar_installed`, reusing that same error key `CONF_EV_SOC_ENTITY`'s own
`required_when_solar_installed` case already established. Add the six new options fields (with
`DEFAULT_*`) to `OPTION_KEYS` and `_threshold_schema()`. **Step 4: Run** → PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/config_flow.py tests/test_config_flow.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: extend config/options flow with solar_forecast mapping and R8/R9/R15 thresholds

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

> **⎔ Phase 3 checkpoint:** the options flow round-trips every new field; a pre-existing entry
> without these fields still loads via `DEFAULT_*` fallback (no migration needed).

---

## Phase 4 — Owned entities (C2/C3 extension)

### Task 4.1: `select.smart_charging_profile`

**Files:**
- Modify: `custom_components/smart_charging/const.py` (add `PROFILE_MANUAL = "Manual"`,
  `PROFILE_AUTO = "Auto"` — consumed by Task 1.2/1.6 already; if those tasks ran first, this task
  only adds the entity, not the constants)
- Modify: `custom_components/smart_charging/select.py`
- Modify: `tests/test_select.py`

**Step 1: Failing tests**

```python
"""HA-harness tests for the profile selector (C2, R16)."""

from custom_components.smart_charging.select import ProfileSelect


class _StubCoordinator:
    def __init__(self):
        self.active_profile = None
        self.refreshed = False

    async def async_request_refresh(self):
        self.refreshed = True


async def test_default_profile_is_manual():
    entity = ProfileSelect(entry_id="abc", coordinator=_StubCoordinator())
    assert entity.current_option == "Manual"
    assert entity.options == ["Manual", "Auto"]


async def test_select_auto_pushes_to_coordinator_and_refreshes(hass):
    coord = _StubCoordinator()
    entity = ProfileSelect(entry_id="abc", coordinator=coord)
    await entity.async_select_option("Auto")
    assert coord.active_profile == "Auto"
    assert coord.refreshed is True


async def test_restores_prior_selection_across_restart(hass):
    """Mirrors ModeSelect's RestoreEntity test: a restored 'Auto' state is adopted on
    async_added_to_hass instead of resetting to the 'Manual' default."""
```

**Step 2: Run** → `ImportError`. **Step 3: Implement** — `ProfileSelect(SmartChargingEntity,
RestoreEntity, SelectEntity)`, mirrors `ModeSelect` exactly (`_attr_options = [PROFILE_MANUAL,
PROFILE_AUTO]`, default `PROFILE_MANUAL`, pushes to `coordinator.active_profile`). **Step 4: Run** →
PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/select.py custom_components/smart_charging/const.py tests/test_select.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add select.smart_charging_profile (C2, R16)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 4.2: Departure-time entities (new `time.py` platform)

**Files:**
- Create: `custom_components/smart_charging/time.py`
- Test: `tests/test_time.py`
- Modify: `custom_components/smart_charging/__init__.py` (register the new `Platform.TIME`)

**Step 1: Failing tests**

```python
"""HA-harness tests for the departure-time entities (R14)."""

async def test_seven_dow_entities_created_with_weekday_default(hass, ...):
    """time.smart_charging_departure_mon .. _fri default to 06:00; _sat/_sun default to None
    (entity-catalog.md)."""


async def test_holiday_and_home_day_overrides_default_to_none(hass, ...):
    """time.smart_charging_departure_holiday / _home_day both start unset."""


async def test_user_can_set_a_departure_time(hass, ...):
    """Setting time.smart_charging_departure_mon persists the new value (native HA
    time-entity state, no RestoreEntity needed)."""
```

**Step 2: Run** → `ImportError`. **Step 3: Implement** — a single `SmartChargingDepartureTime(
SmartChargingEntity, TimeEntity)` class parameterized by id-suffix and default, instantiated ten
times (seven `_dow` + `_holiday` + `_home_day`... eight total, per catalog) in `async_setup_entry`.
Add `Platform.TIME` to `PLATFORMS` in `__init__.py`. **Step 4: Run** → PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/time.py custom_components/smart_charging/__init__.py tests/test_time.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add departure-time entities (time.py platform, R14)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 4.3: `switch.smart_charging_home_day` (new `switch.py` platform)

**Files:**
- Create: `custom_components/smart_charging/switch.py`
- Test: `tests/test_switch.py`
- Modify: `custom_components/smart_charging/__init__.py` (register `Platform.SWITCH`)

**Step 1: Failing tests**

```python
"""HA-harness tests for the home-day flag switch (R9, R13)."""

async def test_defaults_off(hass, ...):
    """switch.smart_charging_home_day starts off."""


async def test_user_can_turn_on_and_off(hass, ...):
    """async_turn_on/async_turn_off toggle native state."""


async def test_resets_to_off_at_local_midnight(hass, freezer, ...):
    """Turn on, advance HA's time-tracking helper past local midnight (async_fire_time_changed
    or the harness's own time-travel fixture), assert state is back to off (R13)."""
```

**Step 2: Run** → `ImportError`. **Step 3: Implement** — `HomeDaySwitch(SmartChargingEntity,
SwitchEntity)`; register `async_track_time_change(hass, self._reset, hour=0, minute=0, second=0)` in
`async_added_to_hass`, cancel it in `async_will_remove_from_hass`. Add `Platform.SWITCH` to
`PLATFORMS`. **Step 4: Run** → PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/switch.py custom_components/smart_charging/__init__.py tests/test_switch.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add switch.smart_charging_home_day with midnight reset (R9/R13)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 4.4: `sensor.smart_charging_active_soc_limit`

**Files:**
- Modify: `custom_components/smart_charging/sensor.py`
- Modify: `tests/test_sensor.py`

**Step 1: Failing tests**

```python
async def test_active_soc_limit_sensor_reflects_the_resolved_value(hass, ...):
    """After a cycle, sensor.smart_charging_active_soc_limit's native_value equals the
    coordinator's resolved R7 value this cycle."""
```

**Step 2: Run** → FAIL. **Step 3: Implement** — `ActiveSocLimitSensor(SmartChargingEntity,
CoordinatorEntity, SensorEntity)`, plain read-only like `EffectivePeakLimitSensor` (no restore). Add
to `async_setup_entry`'s entity list. **Step 4: Run** → PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/sensor.py tests/test_sensor.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add sensor.smart_charging_active_soc_limit diagnostic (R7)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

> **⎔ Phase 4 checkpoint:** every entity in design doc §4 materializes at setup with its catalogued
> default; the home-day switch demonstrably resets at midnight in an HA-harness time-travel test.

---

## Phase 5 — Coordinator (M1 wiring)

### Task 5.1: Wire the full active-SOC-limit resolution + `ActiveSocLimitChanged`

**Files:**
- Modify: `custom_components/smart_charging/coordinator.py`
- Modify: `tests/test_coordinator.py`

**Step 1: Failing tests** (extend the existing HA-harness suite):

```python
async def test_active_soc_limit_resolves_via_the_three_row_table(hass, ...):
    """With a solar step-up state seeded, active_soc_limit reflects the stepped value,
    not the raw override."""

async def test_solar_step_up_clears_on_mode_switch_away_from_solar(hass, ...):
    """Switching from Solar to Power resets self._step_up_state (UC06 exception flow)."""

async def test_solar_step_up_clears_on_disconnect(hass, ...):

async def test_solar_step_up_survives_solar_to_solaronly_switch(hass, ...):

async def test_active_soc_limit_changed_event_fires_on_change(hass, ...):
    """ADR-0011: ActiveSocLimitChanged emitted only when the resolved value differs from
    the prior cycle's."""
```

**Step 2: Run** → FAIL. **Step 3: Implement** — add `self._step_up_state = SolarStepUpState()`
to `__init__`; in `_run_cycle`, after resolving `active_soc_limit`'s prior inputs, call
`resolve_solar_step_up` then `resolve_active_soc_limit` (design doc §10 step 3); reset
`self._step_up_state` on the same mode-switch/disconnect branches that already reset per-mode state.
Emit `ActiveSocLimitChanged` (per ADR-0011's existing publish mechanism) when the resolved value
differs from `self._last_active_soc_limit`. **Step 4: Run** → PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/coordinator.py tests/test_coordinator.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: wire full active-SOC-limit resolution + ActiveSocLimitChanged into M1 (R7/R8/R9)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 5.2: Wire deadline resolution, required-current/urgency, and the baseline-mode comparison

**Files:**
- Modify: `custom_components/smart_charging/coordinator.py`
- Modify: `tests/test_coordinator.py`

**Step 1: Failing tests**

```python
async def test_urgency_engages_when_required_current_exceeds_baseline(hass, ...):

async def test_urgency_reverts_when_baseline_alone_would_meet_the_deadline(hass, ...):

async def test_baseline_comparison_uses_rows_3_5_not_the_escalated_mode(hass, ...):
    """Regression per resolution-rules.md's own warning: comparing against Captar's own
    (already-maximum) desired current would make urgency look satisfied instantly and
    revert every cycle -- this test drives that exact scenario and asserts urgency holds."""

async def test_tomorrow_deadline_resolved_disables_solar_reserve(hass, ...):
    """The one-day-ahead deadline resolution feeds resolve_solar_reserve_active (R9's
    mutual-exclusivity clause)."""
```

**Step 2: Run** → FAIL. **Step 3: Implement** — call `resolve_departure_deadline` twice per cycle
(today's inputs, and tomorrow's per design doc §10 step 2); under `Auto`, compute the baseline mode
by calling `select_mode` (Task 1.6) with `urgent=False`/`unreachable=False` first, get that mode's
own desired current from the same dispatch table (without actually charging on it), then call
`resolve_required_current` with that baseline current; under `Manual`, the baseline is simply the
manually selected mode's own desired current for this cycle (already computed). **Step 4: Run** →
PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/coordinator.py tests/test_coordinator.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: wire deadline resolution and required-current/urgency detection into M1 (R5/R14/R15)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 5.3: Wire `Auto` mode-selection, Capability-Gate, and the effective-peak-limit row-1 raise

**Files:**
- Modify: `custom_components/smart_charging/coordinator.py`
- Modify: `tests/test_coordinator.py`

**Step 1: Failing tests**

```python
async def test_auto_profile_selects_solar_when_surplus_sufficient(hass, ...):

async def test_auto_profile_escalates_to_captar_under_urgency(hass, ...):

async def test_auto_profile_falls_back_to_power_when_captar_unavailable_under_urgency(hass, ...):

async def test_manual_profile_never_changes_mode_regardless_of_urgency(hass, ...):
    """NF2 regression: active_mode stays whatever the user selected even while urgent=True."""

async def test_effective_peak_limit_raises_to_maximum_during_urgency(hass, ...):

async def test_effective_peak_limit_resolves_normally_once_urgency_reverts(hass, ...):

async def test_manual_selector_unaffected_by_available_modes_gate_already_true_today(hass, ...):
    """Regression: existing ModeSelect option-gating behavior (R18) is untouched by
    the new resolve_available_modes call this task adds for Auto's own use."""
```

**Step 2: Run** → FAIL. **Step 3: Implement** — call `resolve_available_modes` (E9) each cycle;
under `Auto`, dispatch the resolved mode via `select_mode` (E2) using the real `urgent`/`unreachable`
result from Task 5.2 instead of the manual selector; pass `urgent` into `resolve_effective_peak_limit`
(Task 1.5) before the R3 clamp call. **Step 4: Run** → PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/coordinator.py tests/test_coordinator.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: wire Auto mode-selection, Capability-Gate, and peak-limit urgency raise into M1 (R16/R18/R5)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

> **⎔ Phase 5 checkpoint:** the full ordered cycle (read → tomorrow's deadline → SOC-limit → today's
> deadline/urgency → available modes → mode selection/dispatch → peak clamp → grid clamp →
> invariants → write) runs correctly for both profiles against a mocked hardware state; `Manual`
> demonstrably never changes mode under urgency; `Auto` demonstrably escalates and reverts.

---

## Phase 6 — Integration wiring & docs

### Task 6.1: Seed new coordinator/config fields at setup

**Files:**
- Modify: `custom_components/smart_charging/__init__.py` (thread every new option into the
  coordinator's `config` dict; register the `time`/`switch` platforms if Tasks 4.2/4.3 didn't already
  add them to `PLATFORMS`)
- Modify: `tests/test_init.py`

**Step 1: Failing test** — setup wires every new option into the coordinator's config; both new
platforms are registered. **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
**Step 5: Commit**

```bash
git add custom_components/smart_charging/__init__.py tests/test_init.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: thread deadline/SOC-management config into the coordinator at setup

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 6.2: End-to-end HA-harness regression per UC05/UC06/UC07

**Files:** Create `tests/test_deadline_soc_management_end_to_end.py`

**Step 1–4:** One test per main-success-scenario + each alternate/exception flow across all three
use-cases: UC05's Normal→Urgent→Unreachable transitions and both profiles' lever sets; UC06's
Baseline→SteppedUp→Baseline lifecycle across a Solar/SolarOnly switch; UC07's Normal→Reserved→Normal
cycle including the mutual-exclusivity-with-UC05 case (a deadline appearing while the reserve cap is
active lifts it the same cycle). Driven through `hass.config_entries` + a full
`async_update_data()` cycle against mocked entity states, not calling the pure functions directly
(that's Phase 1's job; this suite proves the wiring). **Step 5: Commit.**

```bash
git add tests/test_deadline_soc_management_end_to_end.py
git commit --author="Claude <noreply@anthropic.com>" -m "test: add end-to-end HA-harness regression for UC05/UC06/UC07

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 6.3: Translations, strings, README

**Files:**
- Modify: `custom_components/smart_charging/strings.json` + `translations/en.json`/`nl.json` (new
  `select.profile` labels, `time.departure_*` labels, `switch.home_day` label,
  `sensor.active_soc_limit` label, new config/options field labels)
- Modify: `README.md` (Configuration table: battery capacity, solar step-up/reserve fields,
  departure-time entities, home-day switch; move `Auto` profile from "Deferred" to the feature list;
  update the status banner)

**Step 1:** Run `python -m script.hassfest` (or the project's validation task) to confirm strings
completeness. **Step 2: Commit.**

```bash
git add custom_components/smart_charging/strings.json custom_components/smart_charging/translations/en.json custom_components/smart_charging/translations/nl.json README.md
git commit --author="Claude <noreply@anthropic.com>" -m "docs: translations + README for Auto profile, deadline, and SOC management

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

> **⎔ Phase 6 / slice checkpoint:** `ruff check . && ruff format --check . && pytest -q` all green
> (WSL harness); HACS/hassfest validation passes; a manual HA install can select `Auto` from the
> profile selector and observe correct mode escalation/reversion around a departure deadline, solar
> step-up behavior during a solar session, and the overnight solar-reserve cap withholding grid
> top-up when tomorrow looks sunny and no deadline is set.
