"""T1 (epic #996): the plant/runner pair reproduces C4's known defect under charger-power lag.

`Power` mode on an installation without the CapTar capability -- C4 is by requirement the only
clamp in force (C3, R18) -- with a steady household load and a grid supply ceiling that binds
below the charger's maximum current. `clamp_to_ceiling` (E6) re-derives its baseline from
`net_w - charger_w` every cycle (`custom_components/smart_charging/engines/grid_safety.py`); with
the charger-power reading lagging true draw by 1 cycle, that re-derived baseline is wrong by
exactly the change in true draw between two cycles ago and one cycle ago, which a ramping-then-
oscillating commanded current supplies every other cycle -- the same shape #992 confirmed at this
clamp's call site. This validates the plant's lag model against that already-diagnosed defect
before anything speculative is written (ADR-0037, Consequences).

Red on `main` through C4's known defect (`docs/analysis/requirements.md#constraints`, C4's row);
lands as `xfail(strict=True, raises=AssertionError)`. Its control, lag 0, lands green: the same
world, but the charger's power reading lags nothing, and the whole-home meter is always ground
truth -- so the re-derived baseline is exactly right and C4's clamp holds the ceiling on every
step.
"""

import math

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_charging.const import (
    CONF_CAPTAR_AVAILABLE,
    CONF_DEFAULT_TARGET_CURRENT,
    CONF_GRID_CEILING_A,
    CONF_GRID_SAFETY_OFFSET_A,
    CONF_MAX_CURRENT,
    CONF_NOMINAL_VOLTAGE,
    CONF_SOLAR_AVAILABLE,
    DOMAIN,
    MODE_POWER,
)
from tests.helpers import entry_data_base, entry_options_base, seed_charger_states
from tests.scenarios.plant import Plant
from tests.scenarios.runner import ScenarioRunner, format_trace

_HOUSEHOLD_W = 3000.0  # steady -- no household-load step in this scenario
_TARGET_CURRENT_A = 16.0  # Power's target current -- above the ceiling-bound headroom (9 A)
_CYCLES = 12  # several lag-driven oscillation pairs (module docstring, "every other cycle") --
# enough for the xfail to reliably trip and for the control's steady state to show throughout.


def _entry_data():
    """No CapTar, no solar -- C4 is the only clamp in force (C3, R18)."""
    return entry_data_base(**{CONF_SOLAR_AVAILABLE: False, CONF_CAPTAR_AVAILABLE: False})


def _entry_options():
    """Default grid ceiling (25 A) and safety offset (2 A) -- 23 A effective -- with the
    steady 3000 W household load above, the correct steady-state headroom is 9 A: below
    `_TARGET_CURRENT_A`, so the ceiling binds below Power's requested current."""
    return entry_options_base(
        **{
            CONF_MAX_CURRENT: 32.0,  # above _TARGET_CURRENT_A -- E8 never caps it independently
            CONF_DEFAULT_TARGET_CURRENT: _TARGET_CURRENT_A,
        }
    )


async def _setup(hass):
    seed_charger_states(hass, status="Charging", net_w=0.0, charger_w=0.0)
    entry = MockConfigEntry(domain=DOMAIN, data=_entry_data(), options=_entry_options())
    entry.add_to_hass(hass)
    if not await hass.config_entries.async_setup(entry.entry_id):
        # A bare `assert` here would raise AssertionError, which the lag-1 test's own
        # `xfail(strict=True, raises=AssertionError)` would then swallow as though it were the
        # expected C4 breach -- a setup failure must surface as something else entirely.
        raise RuntimeError(f"config entry {entry.entry_id} failed to set up")
    await hass.async_block_till_done()
    # Set once, through the real `select.select_option` service -- never `seed_owned_entity`
    # (#1363, `tests/test_deadline_soc_management_end_to_end.py:1163-1183`'s `_select_option`):
    # a raw state write is not what a real user action produces, and the mode select is a real,
    # polled (`should_poll=True`) entity whose own poll would otherwise contend with a re-seed.
    await _select_option(hass, "select.smart_charging_mode", MODE_POWER)
    return entry.runtime_data.coordinator


async def _select_option(hass, entity_id, option):
    await hass.services.async_call(
        "select", "select_option", {"entity_id": entity_id, "option": option}, blocking=True
    )


def _ceiling_current_a(options: dict) -> float:
    """C4's effective ceiling (A): the configured grid ceiling minus its safety offset."""
    return options[CONF_GRID_CEILING_A] - options[CONF_GRID_SAFETY_OFFSET_A]


def _expected_ceiling_bound_current_a(options: dict, household_w: float, voltage: float) -> float:
    """The commanded current C4 holds the control to once it binds: `ceiling_headroom_a`'s own
    formula (`custom_components/smart_charging/engines/grid_safety.py`) -- floored to a whole
    ampere -- against a baseline that, lag or no lag, is exactly the steady household load here.
    Kept in one place so the control test derives it rather than hard-coding a number the entry's
    options already determine."""
    return float(math.floor(_ceiling_current_a(options) - household_w / voltage))


def _assert_ceiling_held(trace, *, ceiling_w):
    """The scenario-intent assertion: true net import at or below the grid supply ceiling on
    every step. C4's own reaction allowance (a swing the previous command could not have
    foreseen -- a household-load step, or household load alone above the ceiling at 0 A charger
    current) is NOT implemented by this helper: the household load is steady throughout this
    scenario, so no step needs it here. T2's load-step scenario is what adds it.

    Also guards the precondition both tests share: the mode select, set once in `_setup`, must
    still read `Power` on every step -- a real regression in the polled mode select entity
    (#1363) would otherwise pass a breach off as C4's own defect, or a control-test green off as
    proof C4 held, when neither ran under Power at all."""
    for t in trace:
        assert t.active_mode == MODE_POWER, (
            f"step {t.index}: expected active_mode {MODE_POWER!r}, got {t.active_mode!r} -- "
            f"the mode select reverted mid-timeline\n{format_trace(trace)}"
        )
        assert t.reading.true_import_w <= ceiling_w, (
            f"C4 breach at step {t.index}: true import {t.reading.true_import_w} W > "
            f"ceiling {ceiling_w} W\n{format_trace(trace)}"
        )


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "C4's known defect under charger-power lag (docs/analysis/requirements.md#constraints, "
        "C4's row): clamp_to_ceiling re-derives net_w - charger_w from the lagged reading every "
        "cycle, so a lag-driven swing breaches the grid supply ceiling. Choosing C4's lag-case "
        "rule and fixing it are the epic #996 second slice's, after T3."
    ),
)
async def test_should_keep_true_import_within_the_grid_supply_ceiling_when_the_charger_reading_lags_under_power(  # noqa: E501
    hass, freezer
):
    # Arrange
    freezer.move_to("2026-01-15 12:00:00")
    coordinator = await _setup(hass)
    options = _entry_options()
    voltage = options[CONF_NOMINAL_VOLTAGE]
    plant = Plant(household_w=_HOUSEHOLD_W, voltage=voltage, lag_cycles=1)
    runner = ScenarioRunner(hass, coordinator, plant, freezer=freezer, grid_voltage=voltage)

    # Act
    trace = await runner.run(_CYCLES)

    # Assert
    # C4 (docs/analysis/requirements.md#constraints): true import never exceeds the grid
    # supply ceiling.
    _assert_ceiling_held(trace, ceiling_w=_ceiling_current_a(options) * voltage)


async def test_should_keep_true_import_within_the_grid_supply_ceiling_when_the_charger_reading_does_not_lag(  # noqa: E501
    hass, freezer
):
    # Arrange
    freezer.move_to("2026-01-15 12:00:00")
    coordinator = await _setup(hass)
    options = _entry_options()
    voltage = options[CONF_NOMINAL_VOLTAGE]
    plant = Plant(household_w=_HOUSEHOLD_W, voltage=voltage, lag_cycles=0)
    runner = ScenarioRunner(hass, coordinator, plant, freezer=freezer, grid_voltage=voltage)

    # Act
    trace = await runner.run(_CYCLES)

    # Assert
    _assert_ceiling_held(trace, ceiling_w=_ceiling_current_a(options) * voltage)
    # Without lag, the plant's own ground truth can prove more than "never breached": no cycle
    # faulted (a faulted cycle's safe write is 0 A, which would hold the ceiling vacuously), and
    # the control actually reaches and holds C4's ceiling-bound current -- so a regression that
    # stopped charging altogether, or broke the seeding/capture wiring, fails loudly here instead
    # of reading as "the ceiling held".
    assert not any(t.faulted for t in trace), (
        f"a faulted cycle writes 0 A, which would pass the ceiling check vacuously\n"
        f"{format_trace(trace)}"
    )
    expected_a = _expected_ceiling_bound_current_a(options, _HOUSEHOLD_W, voltage)
    for t in trace:
        assert t.commanded_current_a == expected_a, (
            f"step {t.index}: expected the ceiling-bound current {expected_a} A, got "
            f"{t.commanded_current_a} A -- the control never reached C4's bound\n"
            f"{format_trace(trace)}"
        )
