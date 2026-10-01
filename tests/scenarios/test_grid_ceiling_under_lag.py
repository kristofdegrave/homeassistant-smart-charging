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
lands as `xfail(strict=True, raises=InvariantViolation)` (T2, `invariants.py`'s `check_c4` --
`InvariantViolation` subclasses `AssertionError`). Its control, lag 0, lands green: the same
world, but the charger's power reading lags nothing, and the whole-home meter is always ground
truth -- so the re-derived baseline is exactly right and C4's clamp holds the ceiling on every
step.

`HOUSEHOLD_W` and `CYCLES` are public -- `test_invariants.py`'s C4 member replays this exact
world (its own module docstring says so), rather than keeping a second copy of these numbers.
"""

import math

import pytest

from custom_components.smart_charging.const import (
    CONF_CAPTAR_AVAILABLE,
    CONF_DEFAULT_TARGET_CURRENT,
    CONF_GRID_CEILING_A,
    CONF_GRID_SAFETY_OFFSET_A,
    CONF_MAX_CURRENT,
    CONF_NOMINAL_VOLTAGE,
    CONF_SOLAR_AVAILABLE,
    MODE_POWER,
)
from tests.helpers import entry_data_base, entry_options_base, seed_charger_states
from tests.scenarios.invariants import InvariantViolation, check_c4
from tests.scenarios.plant import Plant
from tests.scenarios.runner import ScenarioRunner, format_trace
from tests.scenarios.setup import setup_coordinator

HOUSEHOLD_W = 3000.0  # steady -- no household-load step in this scenario
_TARGET_CURRENT_A = 16.0  # Power's target current -- above the ceiling-bound headroom (9 A)
CYCLES = 12  # several lag-driven oscillation pairs (module docstring, "every other cycle") --
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
    return await setup_coordinator(
        hass, entry_data=_entry_data(), entry_options=_entry_options(), mode=MODE_POWER
    )


def _ceiling_a(options: dict) -> float:
    """C4's hard limit (A): the configured grid supply ceiling itself -- the fuse rating, never
    reduced by the safety offset. C4's row (`docs/analysis/requirements.md#constraints`) states
    the ceiling as the limit and the offset as what the charger *targets* below it, not a second,
    lower ceiling."""
    return options[CONF_GRID_CEILING_A]


def _target_current_a(options: dict) -> float:
    """What the clamp itself aims for: the ceiling minus its configured safety offset -- the
    number `clamp_to_ceiling` (E6) actually solves around, never the hard limit C4 is judged
    against (`_ceiling_a` above)."""
    return options[CONF_GRID_CEILING_A] - options[CONF_GRID_SAFETY_OFFSET_A]


def _expected_ceiling_bound_current_a(options: dict, household_w: float, voltage: float) -> float:
    """The commanded current C4's clamp holds the control to once it binds: `ceiling_headroom_a`'s
    own formula (`custom_components/smart_charging/engines/grid_safety.py`) -- floored to a whole
    ampere -- against a baseline that, lag or no lag, is exactly the steady household load here.
    Kept in one place so the control test derives it rather than hard-coding a number the entry's
    options already determine."""
    return float(math.floor(_target_current_a(options) - household_w / voltage))


def _assert_mode_select_held(trace):
    """Guards the precondition both tests share: the mode select, set once in `_setup`, must
    still read `Power` on every step -- a real regression in the polled mode select entity
    (#1363) would otherwise pass a breach off as C4's own defect, or a control-test green off as
    proof C4 held, when neither ran under Power at all. Not an invariant of the shared set
    (`invariants.py`) -- it is a precondition of THIS harness wiring, not a property of the
    plant's true draw -- so it stays a plain assertion here rather than joining that module.
    Raises a plain `AssertionError` (never `InvariantViolation`), and is composed into the
    lag-1 test's `judge` callback AHEAD of `check_c4` (`_judge_c4_with_mode_guard` below) so a
    mid-run mode revert is not swallowed by that test's `xfail(raises=InvariantViolation)`."""
    for t in trace:
        assert t.active_mode == MODE_POWER, (
            f"step {t.index}: expected active_mode {MODE_POWER!r}, got {t.active_mode!r} -- "
            f"the mode select reverted mid-timeline\n{format_trace(trace)}"
        )


def _judge_c4(ceiling_w):
    """T2 (epic #996): routes C4 through the shared invariant set (`invariants.py`) rather than
    restating the check locally -- `ScenarioRunner.run`'s own `judge` callback."""
    return lambda trace: check_c4(trace, ceiling_w=ceiling_w)


def _judge_c4_with_mode_guard(ceiling_w):
    """The lag-1 test's own `judge`: `_assert_mode_select_held` runs first, so a mode revert
    raises a plain `AssertionError` that `xfail(raises=InvariantViolation)` cannot swallow,
    before `check_c4` gets a chance to raise `InvariantViolation` for the (expected) C4 breach."""

    def _judge(trace):
        _assert_mode_select_held(trace)
        check_c4(trace, ceiling_w=ceiling_w)

    return _judge


@pytest.mark.xfail(
    strict=True,
    raises=InvariantViolation,
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
    plant = Plant(household_w=HOUSEHOLD_W, voltage=voltage, lag_cycles=1)
    runner = ScenarioRunner(hass, coordinator, plant, freezer=freezer, grid_voltage=voltage)
    ceiling_w = _ceiling_a(options) * voltage

    # Act
    # C4 (docs/analysis/requirements.md#constraints): true import never exceeds the grid
    # supply ceiling, judged by the shared invariant set every cycle (T2, `invariants.py`) --
    # the mode-select guard runs first (`_judge_c4_with_mode_guard`'s own docstring).
    await runner.run(CYCLES, judge=_judge_c4_with_mode_guard(ceiling_w))


async def test_should_keep_true_import_within_the_grid_supply_ceiling_when_the_charger_reading_does_not_lag(  # noqa: E501
    hass, freezer
):
    # Arrange
    freezer.move_to("2026-01-15 12:00:00")
    coordinator = await _setup(hass)
    options = _entry_options()
    voltage = options[CONF_NOMINAL_VOLTAGE]
    plant = Plant(household_w=HOUSEHOLD_W, voltage=voltage, lag_cycles=0)
    runner = ScenarioRunner(hass, coordinator, plant, freezer=freezer, grid_voltage=voltage)
    ceiling_w = _ceiling_a(options) * voltage

    # Act
    # C4, judged by the shared invariant set every cycle (T2, `invariants.py`) -- this control
    # runs green under the whole set, as #996's T2 requires.
    trace = await runner.run(CYCLES, judge=_judge_c4(ceiling_w))

    # Assert
    _assert_mode_select_held(trace)
    # Without lag, the plant's own ground truth can prove more than "never breached": no cycle
    # faulted (a faulted cycle's safe write is 0 A, which would hold the ceiling vacuously), and
    # the control actually reaches and holds C4's ceiling-bound current -- so a regression that
    # stopped charging altogether, or broke the seeding/capture wiring, fails loudly here instead
    # of reading as "the ceiling held".
    assert not any(t.faulted for t in trace), (
        f"a faulted cycle writes 0 A, which would pass the ceiling check vacuously\n"
        f"{format_trace(trace)}"
    )
    expected_a = _expected_ceiling_bound_current_a(options, HOUSEHOLD_W, voltage)
    for t in trace:
        assert t.commanded_current_a == expected_a, (
            f"step {t.index}: expected the ceiling-bound current {expected_a} A, got "
            f"{t.commanded_current_a} A -- the control never reached C4's bound\n"
            f"{format_trace(trace)}"
        )
