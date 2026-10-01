"""T2 (epic #996): the shared invariant set (`invariants.py`) is judged against every cycle of
a scenario, and reports the first violating cycle with its context.

Each mutation test below produces its violation through the seam by a `monkeypatch` mutation, so
neither depends on a product defect staying unfixed (ADR-0037's invariant-oracle rule cuts both
ways: the invariant must be quiet on a correct world, and must fire on a genuinely wrong one):

- the C4 member bypasses `clamp_to_ceiling` entirely (T1's own world, lag 0) -- `check_c4` must
  catch what a disabled clamp lets through.
- the R3 member bypasses `debounce_baseline_w` (the #990 shape, now reproduced at R3's call site
  through the plant's lag model rather than hand-seeded feedback) -- `check_r3` must catch the
  one-cycle-removed breach the bypass produces.

The R3 allowance-engaging tests further down run the SAME product code unmutated -- they exist
to prove `check_r3`'s own deferral and grace-period allowances stay quiet on a world that
genuinely needs them, not only that the mutation tests above still go red.
"""

import math

import pytest

from custom_components.smart_charging.const import (
    CONF_CAPTAR_AVAILABLE,
    CONF_CONTROL_INTERVAL_S,
    CONF_DEFAULT_TARGET_CURRENT,
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
from tests.scenarios import test_grid_ceiling_under_lag as t1
from tests.scenarios.invariants import InvariantViolation, check_c4, check_r3, judge_all
from tests.scenarios.plant import Plant, StepReading
from tests.scenarios.runner import CycleTrace, ScenarioRunner
from tests.scenarios.setup import setup_coordinator

# --- C4 member: T1's own lag-0 world, with the clamp itself bypassed -------------------------


async def test_should_report_the_first_violating_cycle_with_its_context_when_the_grid_ceiling_is_breached(  # noqa: E501
    hass, freezer, monkeypatch
):
    # Arrange
    # T1's lag-0 world is the control precisely because, unmutated, it never breaches C4
    # (test_grid_ceiling_under_lag.py's own control test) -- bypassing clamp_to_ceiling here is
    # the only thing that changes.
    monkeypatch.setattr(
        "custom_components.smart_charging.coordinator.clamp_to_ceiling",
        lambda desired_current, *args, **kwargs: desired_current,
    )
    freezer.move_to("2026-01-15 12:00:00")
    seed_charger_states(hass, status="Charging", net_w=0.0, charger_w=0.0)
    coordinator = await setup_coordinator(
        hass, entry_data=t1._entry_data(), entry_options=t1._entry_options(), mode=MODE_POWER
    )
    options = t1._entry_options()
    voltage = options[CONF_NOMINAL_VOLTAGE]
    plant = Plant(household_w=t1.HOUSEHOLD_W, voltage=voltage, lag_cycles=0)
    runner = ScenarioRunner(hass, coordinator, plant, freezer=freezer, grid_voltage=voltage)
    ceiling_w = t1._ceiling_a(options) * voltage

    # Act
    with pytest.raises(InvariantViolation) as excinfo:
        await runner.run(t1.CYCLES, judge=lambda trace: check_c4(trace, ceiling_w=ceiling_w))

    # Assert
    # The bypassed clamp never reduces Power's own target current (16 A) at all: step 0's own
    # command (16 A) has not reached true draw yet (the plant's own one-cycle actuation delay,
    # `plant.py`), so step 0 itself only shows the household's 3000 W; step 1 is the first cycle
    # the charger actually draws, and it already breaches -- true import 6680 W (household
    # 3000 W + 16 A * 230 V = 3680 W) against the 5750 W ceiling (25 A). Pinned exactly, not by
    # substring, and the context includes the preceding step (0) so a reader sees the actuation
    # delay too.
    message = str(excinfo.value)
    assert "C4 breach at step 1: true import 6680.0 W > grid supply ceiling 5750.0 W" in message
    assert "active_mode 'Power'" in message
    assert "commanded 16.0 A, true draw 16.0 A" in message
    assert "   0         16.0          0.0" in message  # step 0's own row, in the context table


# --- R3 member: CapTar, a tight peak, lag 1, a household-load step (#990's shape) -------------

_HOUSEHOLD_W = 500.0
_HOUSEHOLD_STEP_W = 600.0  # household totals 1100 W post-step
_TARGET_CURRENT_A = 8.0  # between the pre-step (9 A) and post-step (7 A) headroom -- the clamp
# is already engaged (so the lag/bypass interaction is live) but the pre-step world is stable,
# and the post-step headroom (7 A) never dips below the minimum current (6 A): R3's own
# grace-period/force-stop branch (a separate, already-sanctioned momentary breach) never
# engages in either run, so the only breach either run can produce is the one this test is
# about.
_PEAK_KW = 3.0  # max_peak_kw == peak_floor_kw: resolve_effective_peak_limit then always
# returns exactly 3.0 kW regardless of the internally-tracked monthly peak (min(max(x, 3.0),
# 3.0) == 3.0 for any x) -- "a tight peak" pinned to a known number rather than left to drift
# with the tracker.
_SAFETY_MARGIN_W = 250.0  # default -- target_w = 3000 - 250 = 2750 W.
_WARMUP_CYCLES = 7  # the pre-step world is steady at 8 A from the very first cycle (the target
# current itself never exceeds the pre-step headroom, so no clamp/grace-period branch ever
# engages) -- this just gives the command-history-dependent raw baseline a few steady cycles to
# read before the household step, so the step is the scenario's own, deliberate cause.
_STEP_CYCLES = 3  # enough for the bypass's one-cycle-removed breach to land.

# R3's grace period and the control cycle it is counted in, pinned explicitly rather than left
# to whatever production would default them to -- read back from the SAME options dict `_setup`
# hands the coordinator, never from a product constant (ADR-0037's invariant-oracle rule).
_PEAK_GRACE_MIN = 2.0
_CONTROL_INTERVAL_S = 10.0


def _entry_data():
    """CapTar present, no solar -- R3 is in force (C3, R18); Power's own peak-protection option
    stays at its default (enabled, R17)."""
    return entry_data_base(**{CONF_SOLAR_AVAILABLE: False, CONF_CAPTAR_AVAILABLE: True})


def _entry_options():
    return entry_options_base(
        **{
            CONF_DEFAULT_TARGET_CURRENT: _TARGET_CURRENT_A,
            CONF_MAX_PEAK_KW: _PEAK_KW,
            CONF_PEAK_FLOOR_KW: _PEAK_KW,
            CONF_SAFETY_MARGIN_W: _SAFETY_MARGIN_W,
            CONF_PEAK_GRACE_MIN: _PEAK_GRACE_MIN,
            CONF_CONTROL_INTERVAL_S: _CONTROL_INTERVAL_S,
        }
    )


async def _setup(hass):
    seed_charger_states(hass, status="Charging", net_w=0.0, charger_w=0.0)
    return await setup_coordinator(
        hass, entry_data=_entry_data(), entry_options=_entry_options(), mode=MODE_POWER
    )


def _effective_peak_limit_w(options: dict) -> float:
    """R3's own target: `resolve_effective_peak_limit`'s formula, pinned for this scenario by
    `max_peak_kw == peak_floor_kw` (above) to exactly `max_peak_kw` regardless of the
    internally-tracked monthly peak -- not restated as a bare number."""
    return options[CONF_MAX_PEAK_KW] * 1000.0 - options[CONF_SAFETY_MARGIN_W]


def _judge_r3(options: dict):
    target_w = _effective_peak_limit_w(options)
    min_current_a = options[CONF_MIN_CURRENT]
    grace_period_s = options[CONF_PEAK_GRACE_MIN] * 60.0
    control_interval_s = options[CONF_CONTROL_INTERVAL_S]

    def _judge(trace):
        check_r3(
            trace,
            effective_peak_limit_w=target_w,
            min_current_a=min_current_a,
            grace_period_s=grace_period_s,
            control_interval_s=control_interval_s,
        )

    return _judge


async def test_should_report_a_peak_breach_when_the_baseline_debounce_is_bypassed(
    hass, freezer, monkeypatch
):
    # Arrange
    # ADR-0039: debounce_baseline_w gates the household-baseline reading against the System's
    # own actuation (`command_changed`) and debounces a headroom-increasing swing. Bypassing it
    # -- returning the raw, undistinguished reading every cycle -- is #990's shape: a reading
    # taken one cycle after the System's own current step is partly a measurement of that step,
    # not of the household, and here it is accepted anyway.
    monkeypatch.setattr(
        "custom_components.smart_charging.coordinator.debounce_baseline_w",
        lambda raw_baseline_w, tracker, *, debounce_cycles, command_changed: (
            raw_baseline_w,
            tracker,
        ),
    )
    freezer.move_to("2026-01-15 12:00:00")
    coordinator = await _setup(hass)
    options = _entry_options()
    voltage = options[CONF_NOMINAL_VOLTAGE]
    plant = Plant(household_w=_HOUSEHOLD_W, voltage=voltage, lag_cycles=1)
    runner = ScenarioRunner(hass, coordinator, plant, freezer=freezer, grid_voltage=voltage)

    # Act
    # The warm-up settles the startup transient at a steady 8 A (Power's own target current,
    # below the pre-step 9 A headroom); the household step to 1100 W total (500 + 600) then
    # makes R3 step the current down (#990's shape): the bypassed debounce lets the command
    # oscillate (6, 8, 7 A) for a few cycles after the step before settling, re-granting
    # headroom the household no longer has -- the breach lands once the over-granted current
    # has actually been drawn, one cycle after the household itself last changed, with no
    # command change of its own to defer it a further cycle.
    await runner.run(_WARMUP_CYCLES, judge=_judge_r3(options))
    plant.set_household_w(_HOUSEHOLD_W + _HOUSEHOLD_STEP_W)
    with pytest.raises(InvariantViolation) as excinfo:
        await runner.run(_STEP_CYCLES, judge=_judge_r3(options))

    # Assert
    # Pinned exactly: step 9, true import 2940 W (household 1100 W + 8 A * 230 V) against the
    # 2750 W target, with the preceding step (8) present in the context table.
    message = str(excinfo.value)
    assert "R3 breach at step 9: true import 2940.0 W > effective peak limit 2750.0 W" in message
    assert "active_mode 'Power'" in message
    assert "commanded 6.0 A, true draw 8.0 A" in message
    assert "   8          8.0          7.0" in message  # step 8's own row, in the context table


async def test_should_keep_the_effective_peak_limit_when_the_baseline_debounce_is_not_bypassed(
    hass, freezer
):
    """The control for the test above: the SAME world (CapTar, tight peak, lag 1, the same
    household step), with `debounce_baseline_w` left exactly as production has it -- proves the
    violation above is the bypass's doing, not an artifact of the plant/world itself."""
    # Arrange
    freezer.move_to("2026-01-15 12:00:00")
    coordinator = await _setup(hass)
    options = _entry_options()
    voltage = options[CONF_NOMINAL_VOLTAGE]
    plant = Plant(household_w=_HOUSEHOLD_W, voltage=voltage, lag_cycles=1)
    runner = ScenarioRunner(hass, coordinator, plant, freezer=freezer, grid_voltage=voltage)
    target_w = _effective_peak_limit_w(options)

    # Act
    await runner.run(_WARMUP_CYCLES, judge=_judge_r3(options))
    plant.set_household_w(_HOUSEHOLD_W + _HOUSEHOLD_STEP_W)
    trace = await runner.run(_STEP_CYCLES, judge=_judge_r3(options))

    # Assert
    # No InvariantViolation raised above is the control's own point; this additionally pins the
    # settled, correctly-debounced current so a future regression that merely stopped breaching
    # loudly (e.g. by never reducing at all) still fails here.
    expected_a = math.floor((target_w - (_HOUSEHOLD_W + _HOUSEHOLD_STEP_W)) / voltage)
    assert trace[-1].commanded_current_a == expected_a


# --- R3's own allowances, engaged on CORRECT (unmutated) product code -------------------------


async def test_should_keep_the_effective_peak_limit_when_a_household_increase_is_deferred(
    hass, freezer
):
    """R3's case-(a) deferral allowance (`invariants.py`'s `_deferred_reaction_allowed`): two
    household increases land back to back (500 -> 1100 -> 1300 W), each stepping the command
    down in turn. The SECOND increase's own reading is itself deferred by case (a) -- the
    command changed on the cycle just before it (ADR-0039's `command_changed`) -- so the clamp
    does not react to it until the cycle after, which is where the breach this test is about
    actually lands; the household itself does not change again on that cycle, so the shared
    same-cycle allowance (`_household_reaction_allowed`) does not cover it. Unmutated product
    code throughout -- `check_r3` must stay quiet on this world, not merely raise on a mutated
    one, per ADR-0037's invariant-oracle rule."""
    # Arrange
    freezer.move_to("2026-01-15 12:00:00")
    coordinator = await _setup(hass)
    options = _entry_options()
    voltage = options[CONF_NOMINAL_VOLTAGE]
    plant = Plant(household_w=_HOUSEHOLD_W, voltage=voltage, lag_cycles=1)
    runner = ScenarioRunner(hass, coordinator, plant, freezer=freezer, grid_voltage=voltage)
    target_w = _effective_peak_limit_w(options)

    # Act
    trace = await runner.run(_WARMUP_CYCLES, judge=_judge_r3(options))
    plant.set_household_w(1100.0)
    trace = await runner.run(1, judge=_judge_r3(options))
    plant.set_household_w(1300.0)
    trace = await runner.run(6, judge=_judge_r3(options))

    # Assert
    # Nothing raised above is this test's own point. This additionally proves step 9 really did
    # breach -- the allowance was actually exercised, not vacuously unneeded -- and that it is
    # the deferral allowance doing the sanctioning: the household did NOT change between step 8
    # and step 9 (same_household), so only the deferral (not the shared same-cycle allowance)
    # can be covering it.
    step8, step9 = trace[8], trace[9]
    assert step9.reading.true_import_w > target_w, "step 9 should have genuinely breached"
    assert step9.reading.household_w == step8.reading.household_w, (
        "the household must NOT have changed again at step 9 -- otherwise the shared same-cycle "
        "allowance, not the deferral this test is about, would be what sanctions it"
    )
    expected_a = math.floor((target_w - 1300.0) / voltage)
    assert trace[-1].commanded_current_a == expected_a


async def test_should_keep_the_effective_peak_limit_during_the_grace_period_at_the_minimum_current(  # noqa: E501
    hass, freezer
):
    """R3's own grace-period allowance (`invariants.py`'s `_grace_period_allowed`): a household
    step large enough (500 -> 2400 W) that the post-step headroom falls below the minimum
    charging current holds the clamp at that minimum while a continuous breach rides out R3's
    configured grace period -- "a momentary breach does not stop charging". Unmutated product
    code throughout, same as the test above."""
    # Arrange
    freezer.move_to("2026-01-15 12:00:00")
    coordinator = await _setup(hass)
    options = _entry_options()
    voltage = options[CONF_NOMINAL_VOLTAGE]
    plant = Plant(household_w=_HOUSEHOLD_W, voltage=voltage, lag_cycles=1)
    runner = ScenarioRunner(hass, coordinator, plant, freezer=freezer, grid_voltage=voltage)
    target_w = _effective_peak_limit_w(options)

    # Act
    await runner.run(_WARMUP_CYCLES, judge=_judge_r3(options))
    plant.set_household_w(2400.0)
    trace = await runner.run(6, judge=_judge_r3(options))

    # Assert
    # Nothing raised above is this test's own point. This additionally proves the breach was
    # real (not vacuous) and that it is genuinely the grace period doing the sanctioning: the
    # charger is already down at the minimum current (6 A) and stays breaching for several
    # cycles running, well inside the configured grace period (12 cycles at the default 2 min /
    # 10 s, plus the one extra the plant's lag costs) -- never once reaching 0 A.
    held_at_minimum = trace[_WARMUP_CYCLES + 1 :]
    assert len(held_at_minimum) >= 5
    for t in held_at_minimum:
        assert t.reading.true_draw_a == options[CONF_MIN_CURRENT]
        assert t.reading.true_import_w > target_w, "the hold should have genuinely breached"
        assert not t.faulted


# --- judge_all's own ordering -------------------------------------------------------------


def test_should_report_a_c4_breach_as_c4s_when_both_c4_and_r3_would_fire():
    """`judge_all`'s documented ordering rule: the first invariant in the LIST wins, whichever
    one that is -- C4 lists first in a scenario that wires both, since R3 only ever applies
    where C4 does too. Proven both ways with the same hand-built cycle (breaching both limits
    at once, no allowance applicable to either) so this is about `judge_all`'s own list-order
    behaviour, not some precedence baked into `check_c4`/`check_r3` themselves."""
    # Arrange
    reading = StepReading(
        true_draw_a=10.0,
        true_charger_w=2300.0,
        reported_charger_w=2300.0,
        household_w=2700.0,
        true_import_w=5000.0,
        net_w=5000.0,
    )
    trace = [
        CycleTrace(
            index=0,
            commanded_current_a=10.0,
            reading=reading,
            faulted=False,
            active_mode=MODE_POWER,
        )
    ]

    def _c4(t):
        check_c4(t, ceiling_w=4000.0)

    def _r3(t):
        check_r3(
            t,
            effective_peak_limit_w=3000.0,
            min_current_a=6.0,
            grace_period_s=_PEAK_GRACE_MIN * 60.0,
            control_interval_s=_CONTROL_INTERVAL_S,
        )

    # Act / Assert -- C4 listed first reports C4's
    with pytest.raises(InvariantViolation) as excinfo:
        judge_all(trace, [_c4, _r3])
    assert str(excinfo.value).startswith("C4 breach")

    # Act / Assert -- R3 listed first reports R3's instead, on the exact same trace
    with pytest.raises(InvariantViolation) as excinfo:
        judge_all(trace, [_r3, _c4])
    assert str(excinfo.value).startswith("R3 breach")
