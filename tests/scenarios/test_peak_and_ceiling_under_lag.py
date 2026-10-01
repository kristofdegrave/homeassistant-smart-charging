"""T3 (epic #996): a whole-stack scenario runs R3 and C4 live and binding under charger-power
lag -- the tier's ADR-0037 placement rule for a tier-3 scenario (every engine live, R3 and C4
both binding), on top of T1's single-clamp C4 reproduction and T2's per-member mutation tests.

`Power` with CapTar present and its own peak-protection option left at its default (R17's
default, `DEFAULT_POWER_RESPECT_PEAK = True`): both clamps run on every cycle (`_apply_peak_clamp`
then `_apply_grid_ceiling_clamp`, in that order, `coordinator.py`'s `_run_cycle`). This module
carries TWO scenarios, both reproducing C4's known defect (`docs/analysis/requirements.md
#constraints`, C4's row) but through different routes, because the first attempt at a single
combined world (quoted in this PR's own notes) surfaced a second, distinct way the defect shows
up -- not a dead end, so it is kept as the second scenario rather than discarded.

**Scenario 1**
(`test_should_keep_true_import_within_both_limits_when_household_load_steps_up_under_power`)
reuses T1's own proven grid-ceiling numbers (same `household_w`, `_TARGET_CURRENT_A`, grid
ceiling and offset, max current) -- the exact world T1 already validated against #992's confirmed
shape -- with CapTar's peak protection layered on top and kept deliberately LOOSER than C4 at
every household level, and a household-load step up that makes R3 step its own commanded current
down (#990's shape, the same trigger T2's R3 mutation test uses). C4 stays the binding clamp
throughout; its own breach is what this scenario's xfail is.

**Scenario 2**
(`test_should_surface_r3_breach_as_a_consequence_of_c4s_lag_defect_when_headrooms_nearly_equal`)
sets CapTar's peak target so its own nominal headroom nearly equals C4's ceiling headroom at the
same steady household load. Running it shows C4's own undebounced lag defect (the same mechanism
as scenario 1 and T1) producing a self-sustaining bang-bang oscillation (0 A / the target current)
that keeps re-triggering R3's own `command_changed`-gated deferral (`debounce_baseline_w`,
ADR-0039) every cycle -- so R3 perpetually holds a stale baseline and over-grants on it, and the
combined trace breaches **R3's** (tighter) target before it ever reaches C4's own (looser)
ceiling. This is a genuine finding, recorded against #996/#992: C4's already-known lag defect
contaminating R3's own protection through the shared `command_changed` debounce gate, not an
independent R3 defect -- `test_should_stay_stable_through_r3_alone_when_headrooms_nearly_equal`
and `test_should_oscillate_through_c4_alone_when_headrooms_nearly_equal` isolate each clamp on
this exact world to prove it: R3 alone is quiet and stable; C4 alone reproduces the same
oscillation on its own, independent of R3 entirely.

Parameter reasoning (ADR-0037's invariant-oracle rule: honest parameters, not tuned to dodge a
member):

- **Why scenario 1 keeps C4 the binding clamp throughout, reusing T1's own numbers unchanged.**
  `min()` (both `_apply_peak_clamp` then `_apply_grid_ceiling_clamp` only ever REDUCE what they
  are given, never raise it) means whichever clamp's own headroom is smaller decides the
  committed current every cycle, regardless of what the other clamp would have allowed. T1's own
  gap (the ceiling's headroom comfortably below Power's target every cycle, never the reverse) is
  what keeps scenario 1's oscillation BOUNDED and reliably reproducing the known defect through
  C4's own criterion -- so scenario 1 keeps that gap exactly as T1 has it, and picks CapTar's own
  peak target to stay looser than C4 throughout (`_TARGET_PEAK_W`, chosen well above T1's own
  observed overshoot) rather than narrowing it.
- **Why this does not make R3 a no-op in scenario 1, and how R3's own bind is actually shown.**
  Because `min()` always reports the smaller value, R3's own reduction at the household step is
  real (its own headroom genuinely drops, `_r3_headroom_a` below) but never visible in the
  commanded current scenario 1's combined run writes -- C4's own headroom is smaller at every
  step regardless, so the committed value is always C4's.
  `test_should_step_the_current_down_through_r3_alone_at_the_household_step` isolates R3 from C4
  (`clamp_to_ceiling` bypassed to a pass-through) on the EXACT SAME entry/household script to
  show R3's own clamp genuinely reduces the commanded current at the step, in this exact world --
  not a different, cherry-picked one. C4's own bind, in turn, is what scenario 1's own xfail IS:
  `clamp_to_ceiling` only ever reduces toward its own headroom, so a true-import breach past the
  raw ceiling cannot happen unless C4's clamp was the active, binding one at the breaching cycle.
- **Why the peak target does not cap the swing below the ceiling (scenario 1).** `_TARGET_PEAK_W`
  sits well above the ceiling (`_ceiling_w`) at both household levels, so C4's own clamp is never
  fed an already-safe value by R3 upstream -- the literal case the issue warns against (a peak
  target cut deep enough that even full pass-through stays under the ceiling, which would make
  the ceiling unreachable through C4 at all).
- **Household step size (scenario 1).** Kept identical in magnitude's spirit to T1's own
  single-world design: modest enough that the post-step ceiling headroom (`_c4_headroom_a`) stays
  comfortably positive (never collapsing to a permanent, vacuously-safe "household alone exceeds
  the ceiling" floor-cap stop, C4's own other allowance), while still large enough that R3's own
  isolated post-step reduction (`_r3_headroom_a`) is an unambiguous multi-ampere drop, clear of
  `CONF_MIN_CURRENT`/the grace-period branch (a separate, already-sanctioned mechanism T2's own
  grace-period tests cover, not this scenario's point).
- **Why scenario 2's parameters are what they are.** `_CONTAM_GRID_CEILING_A`/
  `_CONTAM_GRID_SAFETY_OFFSET_A` and `_CONTAM_MAX_PEAK_KW`/`_CONTAM_PEAK_FLOOR_KW`/
  `_CONTAM_SAFETY_MARGIN_W` are chosen so C4's and R3's nominal headroom floor to the SAME whole
  ampere (14 A) at `_CONTAM_HOUSEHOLD_W` -- a steady household, no step, since the contamination
  this scenario is about needs no external trigger: C4's own undebounced recompute is
  self-sustaining from the startup transient alone (same root cause as T1 and scenario 1, just
  with a small household relative to the swing turning it into a full-amplitude 0 A/target-current
  oscillation rather than a bounded one). `_CONTAM_WARMUP_CYCLES` is pinned to the exact cycle
  count that reaches the known first violation (step 5) -- the xfail test wraps the run and
  asserts the caught `InvariantViolation`'s own message starts with that exact step and limit
  before re-raising it, so a DIFFERENT failure (a regression that changed which step/member
  breaches first) surfaces as a real failure rather than being silently accepted as "the expected
  one".
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


# --- Scenario 2: C4's lag defect contaminates R3 through the shared command-changed debounce
# gate, when both clamps' nominal headroom nearly coincide (module docstring's own section) ------

_CONTAM_HOUSEHOLD_W = 2000.0  # steady throughout -- no step: the contamination needs no external
# trigger (module docstring).
_CONTAM_TARGET_CURRENT_A = 16.0
_CONTAM_MAX_CURRENT_A = 32.0
_CONTAM_GRID_CEILING_A = 25.0
_CONTAM_GRID_SAFETY_OFFSET_A = 2.0
_CONTAM_SAFETY_MARGIN_W = 250.0
_CONTAM_MAX_PEAK_KW = 5.65
_CONTAM_PEAK_FLOOR_KW = 5.65  # pinned equal to _CONTAM_MAX_PEAK_KW -- same identity as the main
# scenario's own _MAX_PEAK_KW/_PEAK_FLOOR_KW (T2's own `_PEAK_KW` comment).
_CONTAM_PEAK_GRACE_MIN = 2.0  # default
_CONTAM_CONTROL_INTERVAL_S = 10.0  # default

_CONTAM_WARMUP_CYCLES = 6  # pinned to the exact cycle count that reaches the known first
# violation (step 5, index 5 of a 6-cycle run) -- module docstring's own reasoning.


def _contam_entry_data():
    return entry_data_base(**{CONF_SOLAR_AVAILABLE: False, CONF_CAPTAR_AVAILABLE: True})


def _contam_entry_options():
    """Peak protection left at its own default (R17), same as the main scenario's `entry_options`
    -- this world's own point is the two clamps' nominal headroom nearly coinciding at
    `_CONTAM_HOUSEHOLD_W` (14 A each: C4 = floor(23 - 2000/230), R3 = floor((5400-2000)/230))."""
    return entry_options_base(
        **{
            CONF_MAX_CURRENT: _CONTAM_MAX_CURRENT_A,
            CONF_DEFAULT_TARGET_CURRENT: _CONTAM_TARGET_CURRENT_A,
            CONF_GRID_CEILING_A: _CONTAM_GRID_CEILING_A,
            CONF_GRID_SAFETY_OFFSET_A: _CONTAM_GRID_SAFETY_OFFSET_A,
            CONF_MAX_PEAK_KW: _CONTAM_MAX_PEAK_KW,
            CONF_PEAK_FLOOR_KW: _CONTAM_PEAK_FLOOR_KW,
            CONF_SAFETY_MARGIN_W: _CONTAM_SAFETY_MARGIN_W,
            CONF_PEAK_GRACE_MIN: _CONTAM_PEAK_GRACE_MIN,
            CONF_CONTROL_INTERVAL_S: _CONTAM_CONTROL_INTERVAL_S,
        }
    )


async def _contam_setup(hass):
    seed_charger_states(hass, status="Charging", net_w=0.0, charger_w=0.0)
    return await setup_coordinator(
        hass,
        entry_data=_contam_entry_data(),
        entry_options=_contam_entry_options(),
        mode=MODE_POWER,
    )


def _bypass_peak_clamp(desired_current, *, tracker, **_kwargs):
    """Mutation for the isolation tests below: R3's own clamp (`apply_peak_clamp`) passed
    straight through, tracker unchanged -- same pass-through technique the main scenario's own
    `clamp_to_ceiling` bypass uses, applied to the other clamp instead."""
    return desired_current, tracker, False


@pytest.mark.xfail(
    strict=True,
    raises=InvariantViolation,
    reason=(
        "R3's breach here is a CONSEQUENCE of C4's known lag defect (C4's row, "
        "docs/analysis/requirements.md#constraints), not an independent R3 defect: "
        "clamp_to_ceiling's own undebounced recompute produces a self-sustaining command "
        "oscillation, which keeps re-triggering R3's own command-changed-gated deferral "
        "(debounce_baseline_w, ADR-0039) every cycle, so R3 perpetually over-grants on a stale "
        "baseline. Isolation (test_should_stay_stable_through_r3_alone_when_headrooms_nearly_"
        "equal) shows R3 alone is quiet and stable at its own correct headroom in this exact "
        "world -- the defect is C4's. Choosing C4's lag-case rule and fixing it are the epic "
        "#996 second slice's, after this task."
    ),
)
async def test_should_surface_r3_breach_as_a_consequence_of_c4s_lag_defect_when_headrooms_nearly_equal(  # noqa: E501
    hass, freezer
):
    # Arrange
    freezer.move_to("2026-01-15 12:00:00")
    coordinator = await _contam_setup(hass)
    options = _contam_entry_options()
    voltage = options[CONF_NOMINAL_VOLTAGE]
    plant = Plant(household_w=_CONTAM_HOUSEHOLD_W, voltage=voltage, lag_cycles=1)
    runner = ScenarioRunner(hass, coordinator, plant, freezer=freezer, grid_voltage=voltage)

    # Act
    # Pin the violation to exactly the known one (R3 breach at step 5) rather than letting the
    # xfail's own `raises=InvariantViolation` accept ANY InvariantViolation -- a regression that
    # changed which member/step breaches first must surface as a real failure, not be silently
    # absorbed as "the expected one" (module docstring's own reasoning).
    try:
        await runner.run(_CONTAM_WARMUP_CYCLES, judge=judge_c4_then_r3(options))
    except InvariantViolation as exc:
        assert str(exc).startswith(
            "R3 breach at step 5: true import 5680.0 W > effective peak limit 5400.0 W"
        ), f"expected the pinned R3-via-C4-contamination violation, got: {exc}"
        raise
    pytest.fail("expected an InvariantViolation (R3 breach at step 5) to have been raised")

    # Assert
    # The assertion is the `xfail` above, pinned to the exact violation by the `try`/`except`
    # block: the expected breach raises `InvariantViolation` from inside `run`, its message
    # checked before being re-raised.


async def test_should_stay_stable_through_r3_alone_when_headrooms_nearly_equal(
    hass, freezer, monkeypatch
):
    """Isolation evidence (module docstring): R3's own clamp (`apply_peak_clamp`), isolated from
    C4 entirely (`clamp_to_ceiling` bypassed to a pass-through), is quiet and stable at its own
    correct headroom throughout this exact world -- proving the oscillation scenario 2 reproduces
    is not any flaw in R3's own clamp."""
    # Arrange
    monkeypatch.setattr(
        "custom_components.smart_charging.coordinator.clamp_to_ceiling",
        lambda desired_current, *args, **kwargs: desired_current,
    )
    freezer.move_to("2026-01-15 12:00:00")
    coordinator = await _contam_setup(hass)
    options = _contam_entry_options()
    voltage = options[CONF_NOMINAL_VOLTAGE]
    plant = Plant(household_w=_CONTAM_HOUSEHOLD_W, voltage=voltage, lag_cycles=1)
    runner = ScenarioRunner(hass, coordinator, plant, freezer=freezer, grid_voltage=voltage)

    # Act
    trace = await runner.run(_CONTAM_WARMUP_CYCLES)

    # Assert
    expected_a = _r3_headroom_a(options, _CONTAM_HOUSEHOLD_W)
    for t in trace[1:]:
        assert t.commanded_current_a == expected_a, (
            f"step {t.index}: expected R3's own stable headroom-bound current {expected_a} A, "
            f"got {t.commanded_current_a} A -- R3 alone should never oscillate in this world\n"
            f"{format_trace(trace)}"
        )


async def test_should_oscillate_through_c4_alone_when_headrooms_nearly_equal(
    hass, freezer, monkeypatch
):
    """Isolation evidence (module docstring): C4's own clamp (`clamp_to_ceiling`), isolated from
    R3 entirely (`apply_peak_clamp` bypassed to a pass-through), reproduces the SAME
    self-sustaining bang-bang oscillation on its own -- proving the defect scenario 2 surfaces
    through R3's stricter target is C4's alone, independent of R3."""
    # Arrange
    monkeypatch.setattr(
        "custom_components.smart_charging.coordinator.apply_peak_clamp",
        _bypass_peak_clamp,
    )
    freezer.move_to("2026-01-15 12:00:00")
    coordinator = await _contam_setup(hass)
    options = _contam_entry_options()
    voltage = options[CONF_NOMINAL_VOLTAGE]
    plant = Plant(household_w=_CONTAM_HOUSEHOLD_W, voltage=voltage, lag_cycles=1)
    runner = ScenarioRunner(hass, coordinator, plant, freezer=freezer, grid_voltage=voltage)

    # Act
    trace = await runner.run(_CONTAM_WARMUP_CYCLES)

    # Assert
    # Asserts the OSCILLATION itself, not merely a breach: every consecutive pair of cycles from
    # index 1 onward differs (bang-bang, never settling), and the only two values it bangs
    # between are 0 A and Power's own target current -- C4's own headroom collapsing to ~0 one
    # cycle, then recovering to let the full, uncorrected target through the next.
    tail = trace[1:]
    for previous, current in zip(tail, tail[1:], strict=False):
        assert current.commanded_current_a != previous.commanded_current_a, (
            "C4 alone should oscillate every cycle from index 1 onward, never settling\n"
            f"{format_trace(trace)}"
        )
    observed = {t.commanded_current_a for t in tail}
    assert observed == {0.0, _CONTAM_TARGET_CURRENT_A}, (
        f"expected C4 alone to bang between 0 A and Power's own target "
        f"({_CONTAM_TARGET_CURRENT_A} A), got {observed}\n{format_trace(trace)}"
    )
