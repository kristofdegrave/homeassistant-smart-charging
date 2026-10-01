"""T3 (epic #996): a whole-stack scenario runs R3 and C4 live and binding under charger-power
lag -- the tier's ADR-0037 placement rule for a tier-3 scenario (every engine live, R3 and C4
both binding), on top of T1's single-clamp C4 reproduction and T2's per-member mutation tests.

`Power` with CapTar present and its own peak-protection option left at its default (R17's
default, `DEFAULT_POWER_RESPECT_PEAK = True`): both clamps run on every cycle (`_apply_peak_clamp`
then `_apply_grid_ceiling_clamp`, in that order, `coordinator.py`'s `_run_cycle`). CapTar's peak
target is chosen so R3's nominal headroom equals C4's ceiling headroom (13 A each) at a steady
household load, so neither clamp is held non-binding by the other, and Power's target alone
(16 A) would take true import past the ceiling, so C4's limit is at stake and not only its clamp.

**What the run shows.** C4's known defect (`docs/analysis/requirements.md#constraints`, C4's row)
-- `clamp_to_ceiling` re-deriving the household from the lagged `charger_w` every cycle -- makes
the commanded current bang between 0 A and the target current. That oscillation corrupts R3's
baseline through its debounce (`debounce_baseline_w`, ADR-0039): the high lagged readings, which
would reset the decrease-debounce's count, fall on command-changed cycles and are discarded
(`pending_cycles` carries through a discarded cycle); the corrupted low readings between them
reach `BASELINE_DEBOUNCE_CYCLES` and are committed, and R3 grants the full target current on a
fresh but wrong baseline. On the next cycle true import breaches both limits; the set judges C4
first, so the run goes red through C4.

**R3's own exposure.** That the debounce commits a corrupted reading under a sustained command
oscillation is R3's criteria at work, not only C4's: any oscillating command, Solar's moving
request among them (`debounce_baseline_w`'s docstring), can trigger it. #1584 records it. This
scenario's xfail is C4's alone, since C4-first ordering reports C4's breach.

**Attribution.** The R3-alone test (C4 bypassed) shows R3 holding its own headroom on this
world under a *steady* command; it does not show R3 stable under an oscillating one (#1584). The
C4-alone test (R3 bypassed) shows C4 alone oscillating between 0 A and the target on this world,
independent of R3, and at this household the target alone exceeds the ceiling: the oscillation,
and so the breach, are C4's.

**Parameters** (ADR-0037's invariant-oracle rule: honest, not tuned to dodge a member). One
steady household load, no step: the oscillation is self-sustaining from the startup transient
alone. `max_peak_kw == peak_floor_kw`, so `resolve_effective_peak_limit` returns exactly
`effective_peak_limit_w` whatever the tracked monthly peak (T2's own `_PEAK_KW` comment).
"""

import math

import pytest

from custom_components.smart_charging.const import (
    CONF_CAPTAR_AVAILABLE,
    CONF_CONTROL_INTERVAL_S,
    CONF_DEFAULT_TARGET_CURRENT,
    CONF_GRID_CEILING_A,
    CONF_GRID_SAFETY_OFFSET_A,
    CONF_MAX_CURRENT,
    CONF_MAX_PEAK_KW,
    CONF_NOMINAL_VOLTAGE,
    CONF_PEAK_FLOOR_KW,
    CONF_PEAK_GRACE_MIN,
    CONF_SAFETY_MARGIN_W,
    CONF_SOLAR_AVAILABLE,
    MODE_POWER,
)
from tests.helpers import entry_data_base, entry_options_base, seed_charger_states
from tests.scenarios.invariants import InvariantViolation
from tests.scenarios.plant import Plant
from tests.scenarios.runner import ScenarioRunner, format_trace
from tests.scenarios.scenario_setup import (
    effective_peak_limit_w,
    judge_c4_then_r3,
    setup_coordinator,
)

_HOUSEHOLD_W = 2300.0  # steady throughout (module docstring).
_TARGET_CURRENT_A = 16.0
_MAX_CURRENT_A = 32.0  # above _TARGET_CURRENT_A so E8 never caps it independently.
_GRID_CEILING_A = 25.0
_GRID_SAFETY_OFFSET_A = 2.0
_SAFETY_MARGIN_W = 250.0  # default
_MAX_PEAK_KW = 5.6
_PEAK_FLOOR_KW = 5.6  # pinned equal to _MAX_PEAK_KW (module docstring).
_PEAK_GRACE_MIN = 2.0  # default
_CONTROL_INTERVAL_S = 10.0  # default

_CYCLES = 12  # T1's own CYCLES: long enough that a C4 fix which only delays the first breach
# past the known step still shows up as a breach rather than as "fixed".
_FIRST_BREACH_STEP = 5  # the known first violation on main (the xfail test's pin).


def entry_data():
    return entry_data_base(**{CONF_SOLAR_AVAILABLE: False, CONF_CAPTAR_AVAILABLE: True})


def entry_options():
    """Peak protection left at its own default (R17) -- this scenario's point is that Power's
    *default* peak protection is live. R3's and C4's nominal headroom coincide at
    `_HOUSEHOLD_W` (13 A each: C4 = floor(23 - 2300/230), R3 = floor((5350 - 2300)/230))."""
    return entry_options_base(
        **{
            CONF_MAX_CURRENT: _MAX_CURRENT_A,
            CONF_DEFAULT_TARGET_CURRENT: _TARGET_CURRENT_A,
            CONF_GRID_CEILING_A: _GRID_CEILING_A,
            CONF_GRID_SAFETY_OFFSET_A: _GRID_SAFETY_OFFSET_A,
            CONF_MAX_PEAK_KW: _MAX_PEAK_KW,
            CONF_PEAK_FLOOR_KW: _PEAK_FLOOR_KW,
            CONF_SAFETY_MARGIN_W: _SAFETY_MARGIN_W,
            CONF_PEAK_GRACE_MIN: _PEAK_GRACE_MIN,
            CONF_CONTROL_INTERVAL_S: _CONTROL_INTERVAL_S,
        }
    )


async def _setup(hass):
    seed_charger_states(hass, status="Charging", net_w=0.0, charger_w=0.0)
    return await setup_coordinator(
        hass, entry_data=entry_data(), entry_options=entry_options(), mode=MODE_POWER
    )


def _r3_headroom_a(options: dict, household_w: float) -> int:
    """R3's own nominal headroom at a given steady household load -- `effective_peak_limit_w`'s
    target against that household, floored the same way `apply_peak_clamp`/`peak_headroom_a`
    would (ADR-0037's invariant-oracle rule: derived from the options, never a product call)."""
    target_w = effective_peak_limit_w(options)
    return math.floor((target_w - household_w) / options[CONF_NOMINAL_VOLTAGE])


def _judge_with_mode_guard(options: dict):
    """The whole invariant set (`judge_c4_then_r3`), with T1's mode-select guard ahead of it: a
    mid-run mode revert (#1363) raises a plain `AssertionError` that the xfail's
    `raises=InvariantViolation` cannot swallow as C4's defect (T1's `_assert_mode_select_held`
    docstring has the reasoning)."""
    judge = judge_c4_then_r3(options)

    def _judge(trace):
        for t in trace:
            assert t.active_mode == MODE_POWER, (
                f"step {t.index}: expected active_mode {MODE_POWER!r}, got {t.active_mode!r} -- "
                f"the mode select reverted mid-timeline\n{format_trace(trace)}"
            )
        judge(trace)

    return _judge


def _bypass_peak_clamp(desired_current, *, tracker, **_kwargs):
    """Mutation for the C4-alone test: R3's own clamp (`apply_peak_clamp`) passed straight
    through, tracker unchanged."""
    return desired_current, tracker, False


@pytest.mark.xfail(
    strict=True,
    raises=InvariantViolation,
    reason=(
        "C4's known defect under charger-power lag (C4's row, "
        "docs/analysis/requirements.md#constraints): clamp_to_ceiling re-derives the household "
        "from the lagged reading every cycle, so the command oscillates and true import breaches "
        "the grid supply ceiling while the swing lasts. R3's debounce lets the same swing "
        "through (two corrupted low readings reach its count and the second is committed), "
        "which is #1584's, not this marker's. Choosing C4's lag-case rule and fixing it are the "
        "epic #996 second slice's, after this task."
    ),
)
async def test_should_keep_true_import_within_both_limits_when_r3_and_c4_headrooms_coincide_under_lag(  # noqa: E501
    hass, freezer
):
    # Arrange
    freezer.move_to("2026-01-15 12:00:00")
    coordinator = await _setup(hass)
    options = entry_options()
    voltage = options[CONF_NOMINAL_VOLTAGE]
    plant = Plant(household_w=_HOUSEHOLD_W, voltage=voltage, lag_cycles=1)
    runner = ScenarioRunner(hass, coordinator, plant, freezer=freezer, grid_voltage=voltage)
    known_breach = (
        f"C4 breach at step {_FIRST_BREACH_STEP}: true import "
        f"{_HOUSEHOLD_W + _TARGET_CURRENT_A * voltage} W > grid supply ceiling "
        f"{options[CONF_GRID_CEILING_A] * voltage} W"
    )

    # Act
    # The whole invariant set judges every step. A violation other than the known one (another
    # member or step) fails the pin below as a plain AssertionError rather than being absorbed
    # by `raises=InvariantViolation`; no violation at all is an XPASS, which `strict` fails.
    try:
        await runner.run(_CYCLES, judge=_judge_with_mode_guard(options))
    except InvariantViolation as exc:
        # Assert
        assert str(exc).startswith(known_breach), f"expected {known_breach!r}, got: {exc}"
        raise


async def test_should_hold_r3s_headroom_every_cycle_when_c4_is_bypassed_under_lag(
    hass, freezer, monkeypatch
):
    """Attribution evidence (module docstring): R3 alone, `clamp_to_ceiling` passed straight
    through, holds its own headroom on this world under a steady command, every cycle."""
    # Arrange
    monkeypatch.setattr(
        "custom_components.smart_charging.coordinator.clamp_to_ceiling",
        lambda desired_current, *args, **kwargs: desired_current,
    )
    freezer.move_to("2026-01-15 12:00:00")
    coordinator = await _setup(hass)
    options = entry_options()
    voltage = options[CONF_NOMINAL_VOLTAGE]
    plant = Plant(household_w=_HOUSEHOLD_W, voltage=voltage, lag_cycles=1)
    runner = ScenarioRunner(hass, coordinator, plant, freezer=freezer, grid_voltage=voltage)
    expected_a = _r3_headroom_a(options, _HOUSEHOLD_W)

    # Act
    trace = await runner.run(_CYCLES)

    # Assert
    for t in trace:
        assert t.commanded_current_a == expected_a, (
            f"step {t.index}: expected R3's own stable headroom-bound current {expected_a} A, "
            f"got {t.commanded_current_a} A\n{format_trace(trace)}"
        )


async def test_should_bang_between_zero_and_the_target_when_r3_is_bypassed_under_lag(
    hass, freezer, monkeypatch
):
    """Attribution evidence (module docstring): C4 alone, `apply_peak_clamp` passed straight
    through, oscillates on this world independent of R3. This pins C4's known defect as a green
    test, so it goes red the day C4 is fixed -- that is expected, and the fix retires it with the
    xfail above. Step 0 is skipped: it commits C4's nominal headroom from the startup reading,
    before the first lagged reading arrives."""
    # Arrange
    monkeypatch.setattr(
        "custom_components.smart_charging.coordinator.apply_peak_clamp",
        _bypass_peak_clamp,
    )
    freezer.move_to("2026-01-15 12:00:00")
    coordinator = await _setup(hass)
    options = entry_options()
    voltage = options[CONF_NOMINAL_VOLTAGE]
    plant = Plant(household_w=_HOUSEHOLD_W, voltage=voltage, lag_cycles=1)
    runner = ScenarioRunner(hass, coordinator, plant, freezer=freezer, grid_voltage=voltage)

    # Act
    trace = await runner.run(_CYCLES)

    # Assert
    # Every consecutive pair from step 1 differs, and the only values are 0 A and the target.
    tail = trace[1:]
    for previous, current in zip(tail, tail[1:], strict=False):
        assert current.commanded_current_a != previous.commanded_current_a, (
            f"C4 alone should oscillate every cycle from step 1, never settling\n"
            f"{format_trace(trace)}"
        )
    observed = {t.commanded_current_a for t in tail}
    assert observed == {0.0, _TARGET_CURRENT_A}, (
        f"expected C4 alone to bang between 0 A and the target ({_TARGET_CURRENT_A} A), got "
        f"{observed}\n{format_trace(trace)}"
    )
