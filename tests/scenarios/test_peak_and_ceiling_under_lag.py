"""T3 (epic #996): a whole-stack scenario runs R3 and C4 live and binding under charger-power
lag -- the tier's ADR-0037 placement rule for a tier-3 scenario (every engine live, R3 and C4
both binding), on top of T1's single-clamp C4 reproduction and T2's per-member mutation tests.

`Power` with CapTar present and its own peak-protection option left at its default (R17's
default, `DEFAULT_POWER_RESPECT_PEAK = True`): both clamps run on every cycle (`_apply_peak_clamp`
then `_apply_grid_ceiling_clamp`, in that order, `coordinator.py`'s `_run_cycle`) against a world
that reuses T1's own proven grid-ceiling numbers (same `household_w`, `_TARGET_CURRENT_A`,
grid ceiling and offset, max current) -- the exact world T1 already validated against #992's
confirmed shape -- with CapTar's peak protection layered on top, and a household-load step up
that makes R3 step its own commanded current down (#990's shape, the same trigger T2's R3
mutation test uses).

Parameter reasoning (ADR-0037's invariant-oracle rule: honest parameters, not tuned to dodge a
member):

- **Why C4 stays the binding clamp throughout, reusing T1's own numbers unchanged.** `min()`
  (both `_apply_peak_clamp` then `_apply_grid_ceiling_clamp` only ever REDUCE what they are
  given, never raise it) means whichever clamp's own headroom is smaller decides the committed
  current every cycle, regardless of what the other clamp would have allowed. An early version of
  this test tried to pick R3's own target so its headroom nearly equalled C4's, hoping to see
  each bind at a different moment -- running it (this PR's own notes quote the trace) showed that
  only widens the startup transient into a full bang-bang oscillation between 0 A and the target
  current, which breaches R3's own target during warm-up for a reason that has nothing to do with
  C4's lag defect at all (an oracle-genuine, but uninteresting, R3 violation). T1's own gap (the
  ceiling's headroom comfortably below Power's target every cycle, never the reverse) is what
  keeps the oscillation BOUNDED and reliably reproduces the known defect instead -- so this test
  keeps that gap exactly as T1 has it, and picks CapTar's own peak target to stay looser than C4
  throughout (`_TARGET_PEAK_W`, chosen well above T1's own observed overshoot) rather than
  fighting it.
- **Why this does not make R3 a no-op, and how R3's own bind is actually shown.** Because `min()`
  always reports the smaller value, R3's own reduction at the household step is real (its own
  headroom genuinely drops, `_r3_headroom_a` below) but never visible in the commanded current
  THIS test's combined run writes -- C4's own headroom is smaller at every step regardless, so
  the committed value is always C4's.
  `test_should_step_the_current_down_through_r3_alone_at_the_household_step` isolates R3 from C4
  (`clamp_to_ceiling` bypassed to a pass-through) on the EXACT SAME entry/household script to
  show R3's own clamp genuinely reduces the commanded current at the step, in this exact world --
  not a different, cherry-picked one. C4's own bind, in turn, is what the main test's own xfail
  IS: `clamp_to_ceiling` only ever reduces toward its own headroom, so a true-import breach past
  the raw ceiling cannot happen unless C4's clamp was the active, binding one at the breaching
  cycle.
- **Why the peak target does not cap the swing below the ceiling.** `_TARGET_PEAK_W` sits well
  above the ceiling (`_ceiling_w`) at both household levels, so C4's own clamp is never fed an
  already-safe value by R3 upstream -- the literal case the issue warns against (a peak target cut
  deep enough that even full pass-through stays under the ceiling, which would make the ceiling
  unreachable through C4 at all).
- **Household step size.** Kept identical in magnitude's spirit to T1's own single-world design:
  modest enough that the post-step ceiling headroom (`_c4_headroom_a`) stays comfortably positive
  (never collapsing to a permanent, vacuously-safe "household alone exceeds the ceiling" floor-cap
  stop, C4's own other allowance), while still large enough that R3's own isolated post-step
  reduction (`_r3_headroom_a`) is an unambiguous multi-ampere drop, clear of
  `CONF_MIN_CURRENT`/the grace-period branch (a separate, already-sanctioned mechanism T2's own
  grace-period tests cover, not this scenario's point).
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
    CONF_MIN_CURRENT,
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

_HOUSEHOLD_W = 3000.0  # pre-step -- T1's own steady household load, unchanged.
_HOUSEHOLD_STEP_W = 1500.0  # post-step total 4500 W (#990's shape) -- see the module docstring's
# "Household step size" paragraph for why this magnitude.
_TARGET_CURRENT_A = 16.0  # T1's own Power target -- clearly above the ceiling's own headroom at
# both household levels, so the committed current always reflects whichever clamp binds.
_MAX_CURRENT_A = 32.0  # T1's own override -- above _TARGET_CURRENT_A so E8 never caps it
# independently.

# C4: T1's own grid ceiling and offset, unchanged (module docstring) -- the known-good world that
# already validates the plant's lag model against #992's confirmed shape.
_GRID_CEILING_A = 25.0
_GRID_SAFETY_OFFSET_A = 2.0

# R3: a peak target kept looser than C4 at both household levels (module docstring's parameter
# reasoning), pinned to max_peak_kw == peak_floor_kw so resolve_effective_peak_limit always
# returns exactly this regardless of the internally-tracked monthly peak (T2's own `_PEAK_KW`
# comment explains the identity).
_SAFETY_MARGIN_W = 250.0  # default
_MAX_PEAK_KW = 6.75
_PEAK_FLOOR_KW = 6.75
_TARGET_PEAK_W = _MAX_PEAK_KW * 1000.0 - _SAFETY_MARGIN_W  # 6500 W
_PEAK_GRACE_MIN = 2.0  # default
_CONTROL_INTERVAL_S = 10.0  # default

_WARMUP_CYCLES = 12  # T1's own CYCLES -- enough for the xfail to reliably reproduce C4's known
# defect (several lag-driven oscillation pairs), proven by T1 itself.
_STEP_CYCLES = 8  # enough for R3's own isolated post-step reduction to settle and be read back.


def entry_data():
    return entry_data_base(**{CONF_SOLAR_AVAILABLE: False, CONF_CAPTAR_AVAILABLE: True})


def entry_options():
    """Peak protection is left at its own default (R17, `DEFAULT_POWER_RESPECT_PEAK = True`) --
    not overridden -- since this scenario's own point is that Power's *default* peak protection
    is what is live here."""
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


def _ceiling_w(options: dict) -> float:
    """C4's hard limit (W): the configured grid supply ceiling itself, never reduced by the
    safety offset -- same rule as T1's own `ceiling_a` (C4's row,
    `docs/analysis/requirements.md#constraints`)."""
    return options[CONF_GRID_CEILING_A] * options[CONF_NOMINAL_VOLTAGE]


def _c4_headroom_a(options: dict, household_w: float) -> int:
    """C4's own nominal (lag-free) headroom at a given steady household load --
    `ceiling_headroom_a`'s own formula, read back from the SAME options dict the scenario hands
    the coordinator rather than hard-coded, so the module docstring's own numbers stay honest if
    an option above changes."""
    eff_a = options[CONF_GRID_CEILING_A] - options[CONF_GRID_SAFETY_OFFSET_A]
    return math.floor(eff_a - household_w / options[CONF_NOMINAL_VOLTAGE])


def _r3_headroom_a(options: dict, household_w: float) -> int:
    """R3's own nominal headroom at a given steady household load -- `effective_peak_limit_w`'s
    target against that household, floored the same way `apply_peak_clamp`/`peak_headroom_a`
    would (ADR-0037's invariant-oracle rule: derived from the options, never a product call)."""
    target_w = effective_peak_limit_w(options)
    return math.floor((target_w - household_w) / options[CONF_NOMINAL_VOLTAGE])


@pytest.mark.xfail(
    strict=True,
    raises=InvariantViolation,
    reason=(
        "C4's known defect under charger-power lag (docs/analysis/requirements.md#constraints, "
        "C4's row): clamp_to_ceiling re-derives net_w - charger_w from the lagged reading every "
        "cycle, so a lag-driven swing breaches the grid supply ceiling -- the same mechanism T1 "
        "validates, now with CapTar's own peak protection live (and looser, C3/R17) alongside it. "
        "Choosing C4's lag-case rule and fixing it are the epic #996 second slice's, after this "
        "task."
    ),
)
async def test_should_keep_true_import_within_both_limits_when_household_load_steps_up_under_power(  # noqa: E501
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
    # The whole invariant set (C4 first, then R3 -- judge_c4_then_r3/judge_all's own ordering
    # rule) judges every step, warm-up included (#996's T3 own text). The household step is
    # scripted regardless of whether this particular run reaches it: C4's known defect reproduces
    # from T1's own numbers alone (module docstring), same as T1 itself needed no step at all.
    await runner.run(_WARMUP_CYCLES, judge=judge_c4_then_r3(options))
    plant.set_household_w(_HOUSEHOLD_W + _HOUSEHOLD_STEP_W)
    await runner.run(_STEP_CYCLES, judge=judge_c4_then_r3(options))

    # Assert
    # C4 (docs/analysis/requirements.md#constraints) and R3
    # (docs/analysis/requirements.md#r3--captar-peak-protection): true import never exceeds
    # either limit, judged by the shared invariant set every cycle (T2, `invariants.py`). The
    # assertion is the `xfail` above: the expected breach raises `InvariantViolation` from inside
    # `run` itself.


async def test_should_step_the_current_down_through_r3_alone_at_the_household_step(
    hass, freezer, monkeypatch
):
    """Proves R3 genuinely engages in this exact world, isolated from C4's own lag defect: the
    SAME entry/household script as the xfail test above, with `clamp_to_ceiling` bypassed
    (passed straight through) so the committed current is R3's own output alone -- `min()` means
    the two clamps' combined output can never show R3's own reduction directly whenever C4 also
    binds (module docstring's parameter reasoning), so isolating R3 this way is the only way to
    observe its own magnitude rather than inferring it.
    """
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

    # Act
    await runner.run(_WARMUP_CYCLES)
    pre_step_a = runner.trace[-1].commanded_current_a
    plant.set_household_w(_HOUSEHOLD_W + _HOUSEHOLD_STEP_W)
    await runner.run(_STEP_CYCLES)
    post_step_a = runner.trace[-1].commanded_current_a

    # Assert
    # R3 alone (C4 bypassed) settles the pre-step world at its own headroom-bound current, then
    # genuinely steps it DOWN once the household load rises -- the clamp this scenario is about
    # to prove binds, isolated from C4's own.
    assert pre_step_a == _r3_headroom_a(options, _HOUSEHOLD_W), (
        f"expected R3's own pre-step bound {_r3_headroom_a(options, _HOUSEHOLD_W)} A, got "
        f"{pre_step_a} A\n{format_trace(runner.trace)}"
    )
    expected_post_step_a = _r3_headroom_a(options, _HOUSEHOLD_W + _HOUSEHOLD_STEP_W)
    assert post_step_a == expected_post_step_a, (
        f"expected R3's own post-step bound {expected_post_step_a} A, got {post_step_a} A\n"
        f"{format_trace(runner.trace)}"
    )
    assert post_step_a < pre_step_a, (
        "R3 should have stepped the commanded current down at the household step\n"
        f"{format_trace(runner.trace)}"
    )
    assert post_step_a > options[CONF_MIN_CURRENT], (
        "the post-step world must stay clear of R3's grace-period/force-stop branch -- a "
        "separate, already-sanctioned mechanism this test is not about"
    )


async def test_should_clamp_to_the_ceiling_headroom_through_c4_before_the_defect_fires(
    hass, freezer
):
    """Proves C4 genuinely binds in this exact world -- not merely configured, present but
    inert: the FIRST cycle already commits a current well below Power's own target
    (`_TARGET_CURRENT_A`, 16 A) and well below R3's own, looser headroom at this household level
    (`_r3_headroom_a`, 15 A) -- the ceiling's own headroom (`_c4_headroom_a`, 9 A) is the only
    thing that explains it. Stops at cycle 1, one cycle before the xfail test's own first
    violation (step 3) -- this is a precondition check, not a race with that violation."""
    # Arrange
    freezer.move_to("2026-01-15 12:00:00")
    coordinator = await _setup(hass)
    options = entry_options()
    voltage = options[CONF_NOMINAL_VOLTAGE]
    plant = Plant(household_w=_HOUSEHOLD_W, voltage=voltage, lag_cycles=1)
    runner = ScenarioRunner(hass, coordinator, plant, freezer=freezer, grid_voltage=voltage)

    # Act
    await runner.run(1)

    # Assert
    expected_a = _c4_headroom_a(options, _HOUSEHOLD_W)
    assert expected_a < _r3_headroom_a(options, _HOUSEHOLD_W), (
        "this test's own precondition: C4 must be the tighter clamp at this household level, or "
        "the committed current below would reflect R3's headroom instead and prove nothing about "
        "C4"
    )
    assert runner.trace[0].commanded_current_a == expected_a, (
        f"expected C4's own ceiling-bound current {expected_a} A, got "
        f"{runner.trace[0].commanded_current_a} A -- C4 should already be the binding clamp\n"
        f"{format_trace(runner.trace, target_w=_ceiling_w(options))}"
    )
