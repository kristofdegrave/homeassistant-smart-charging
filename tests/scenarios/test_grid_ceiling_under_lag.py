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

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_charging.const import (
    CONF_CAPTAR_AVAILABLE,
    CONF_DEFAULT_TARGET_CURRENT,
    CONF_MAX_CURRENT,
    CONF_SOLAR_AVAILABLE,
    DOMAIN,
    MODE_POWER,
)
from tests.helpers import (
    entry_data_base,
    entry_options_base,
    seed_charger_states,
    seed_owned_entity,
)
from tests.scenarios.plant import Plant
from tests.scenarios.runner import ScenarioRunner, format_trace

_HOUSEHOLD_W = 3000.0  # steady -- no household-load step in this scenario
_TARGET_CURRENT_A = 16.0  # Power's target current -- above the ceiling-bound headroom (9 A)
_CONTROL_INTERVAL_S = 10


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
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_POWER)
    return entry.runtime_data.coordinator


def _assert_ceiling_held(trace, *, ceiling_w):
    """The scenario-intent assertion: true net import at or below the grid supply ceiling on
    every step, with C4's own reaction allowance -- a swing the previous command could not have
    foreseen (a household-load step, or household load alone above the ceiling at 0 A charger
    current) is not a violation. The household load is steady throughout this scenario, so
    neither exception is ever in play here: every breach below is a real one."""
    for t in trace:
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
    freezer.move_to("2026-01-15 12:00:00")
    coordinator = await _setup(hass)
    plant = Plant(household_w=_HOUSEHOLD_W, voltage=230.0, lag_cycles=1)
    runner = ScenarioRunner(
        hass, coordinator, plant, freezer=freezer, control_interval_s=_CONTROL_INTERVAL_S
    )

    trace = await runner.run(12)

    # C4 (docs/analysis/requirements.md#constraints): true import never exceeds the grid
    # supply ceiling. ceiling_a=25, offset_a=2 (entry_options_base defaults) -> 23 A effective.
    _assert_ceiling_held(trace, ceiling_w=23.0 * 230.0)


async def test_should_keep_true_import_within_the_grid_supply_ceiling_when_the_charger_reading_does_not_lag(  # noqa: E501
    hass, freezer
):
    freezer.move_to("2026-01-15 12:00:00")
    coordinator = await _setup(hass)
    plant = Plant(household_w=_HOUSEHOLD_W, voltage=230.0, lag_cycles=0)
    runner = ScenarioRunner(
        hass, coordinator, plant, freezer=freezer, control_interval_s=_CONTROL_INTERVAL_S
    )

    trace = await runner.run(12)

    _assert_ceiling_held(trace, ceiling_w=23.0 * 230.0)
