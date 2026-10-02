"""T3 (epic #996): a whole-stack scenario runs R3 and C4 live and binding under charger-power
lag -- the tier's ADR-0037 placement rule for a tier-3 scenario (every engine live, R3 and C4
both binding at the start), on top of T1's single-clamp C4 reproduction and T2's per-member
mutation tests. Both bind only until step 4 (see "R3's own exposure").

`Power` with CapTar present and its own peak-protection option left at its default (R17's
default, `DEFAULT_POWER_RESPECT_PEAK = True`): both clamps run on every cycle (`_apply_peak_clamp`
then `_apply_grid_ceiling_clamp`, in that order, `coordinator.py`'s `_run_cycle`). CapTar's peak
target is chosen so R3's nominal headroom equals C4's ceiling headroom (13 A each) at a steady
household load, so neither clamp starts held non-binding by the other, and Power's target alone
(16 A) would take true import past the ceiling, so C4's limit is at stake and not only its clamp.

**What the run shows.** Before ADR-0058, C4 re-derived the household from the lagged `charger_w`
alone, so the commanded current banged between 0 A and the binding headroom; that oscillation
corrupted R3's baseline through its debounce (`debounce_baseline_w`, ADR-0039), and on step 5
true import breached both limits. With C4 solving around the lower of the reading and the last
set charger current (ADR-0058; requirements.md's C4 row,
`docs/analysis/requirements.md#constraints`), the command still alternates between 13 A and 0 A
on every step while C4 binds on the lagging reading (ADR-0058's Option D accepts this), but true
import stays within both limits every step, so the whole invariant set judges every step green.

**R3's own exposure.** R3's debounce still commits the corrupted baseline (-690 W) at step 4;
from then on R3's headroom is 26 A, above the 16 A target, so R3 stops binding and C4 alone
holds both limits, step for step as in the C4-alone run. That R3's debounce commits a corrupted
reading under a sustained command oscillation is R3's criteria at work, not only C4's: any
oscillating command, Solar's moving request among them (`debounce_baseline_w`'s docstring), can
trigger it. #1584 records it; this world still oscillates, so it still exercises that exposure,
and what it shows is that the oscillation now stays within both limits here.

**Attribution.** The R3-alone test (C4 bypassed) shows R3 holding its own headroom on this
world under a *steady* command; it does not show R3 stable under an oscillating one (#1584). The
C4-alone test (R3 bypassed) shows C4 alone holding the grid supply ceiling on this world, where
Power's target alone would exceed it.

**Parameters** (ADR-0037's invariant-oracle rule: honest, not tuned to dodge a member). One
steady household load, no step: the oscillation is self-sustaining from the startup transient
alone (before ADR-0058 it also breached the limits). `max_peak_kw == peak_floor_kw`, so
`resolve_effective_peak_limit` returns exactly `max_peak_kw`, from which `effective_peak_limit_w`
derives, whatever the tracked monthly peak (T2's own `_PEAK_KW` comment).
"""

import math

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
from tests.scenarios.invariants import check_c4
from tests.scenarios.plant import Plant
from tests.scenarios.runner import ScenarioRunner, format_trace
from tests.scenarios.scenario_setup import (
    assert_charged_without_fault,
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

_CYCLES = 12  # T1's value: several lag-driven step pairs.


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
    """The whole invariant set (`judge_c4_then_r3`), with T1's mode-select guard ahead of it, so
    a mid-run mode revert (#1363) fails on the step it happens (T1's `_assert_mode_select_held`
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

    # Act
    trace = await runner.run(_CYCLES, judge=_judge_with_mode_guard(options))

    # Assert
    assert_charged_without_fault(trace)
    # C4 and R3 (docs/analysis/requirements.md): true import stays within both limits, judged by
    # the whole invariant set every step; a breach raises `InvariantViolation` inside `run`.


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


async def test_should_hold_the_grid_supply_ceiling_every_cycle_when_r3_is_bypassed_under_lag(
    hass, freezer, monkeypatch
):
    """Attribution evidence (module docstring): C4 alone, `apply_peak_clamp` passed straight
    through, holds the ceiling on this world, where Power's 16 A target alone would exceed it."""
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
    ceiling_w = options[CONF_GRID_CEILING_A] * voltage

    # Act
    trace = await runner.run(_CYCLES, judge=lambda trace: check_c4(trace, ceiling_w=ceiling_w))

    # Assert
    assert_charged_without_fault(trace)
    # C4 (docs/analysis/requirements.md#constraints): judged by the shared C4 member every step;
    # a breach raises `InvariantViolation` inside `run`.
