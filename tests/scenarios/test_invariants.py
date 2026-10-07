"""T2/#1578 (epic #996): the shared invariant set (`invariants.py`) is judged against every cycle
of a scenario, and reports the first violating cycle with its context.

Each mutation test below produces its violation through the seam by a `monkeypatch` mutation, so
neither depends on a product defect staying unfixed (ADR-0037's invariant-oracle rule cuts both
ways: the invariant must be quiet on a correct world, and must fire on a genuinely wrong one):

- the C4 member bypasses `clamp_to_ceiling` entirely (T1's own world, lag 0) -- `check_c4` must
  catch what a disabled clamp lets through.
- the R3 member bypasses `debounce_baseline_w` and the lower charger term (`_charger_draw_w`,
  ADR-0059) -- the #990 shape, reproduced at R3's call site through the plant's lag model
  rather than hand-seeded feedback -- `check_r3` must catch the one-cycle-removed breach the
  bypass produces.

The R3 allowance-engaging tests further down run the SAME product code unmutated -- they exist
to prove `check_r3`'s own deferral and grace-period allowances stay quiet on a world that
genuinely needs them, not only that the mutation tests above still go red.

The reaction-allowance self-tests and the ordering tests further down (the allowance helpers' own
branches; `judge_all`'s own list-order behaviour) build their trace by hand rather than through
the coordinator/plant seam: they are pure oracle self-tests, proving the oracle's own tooling
behaviour directly rather than a scenario outcome, so a hand-built trace is the right seam for
them -- unlike the mutation tests above, which must run through the real stack.
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
from custom_components.smart_charging.engines.billing_protection import (
    PeakBreachTracker,
    peak_headroom_a,
)
from tests.helpers import entry_data_base, entry_options_base, seed_charger_states
from tests.scenarios import test_grid_ceiling_under_lag as t1
from tests.scenarios.invariants import InvariantViolation, check_c4, check_r3, judge_all
from tests.scenarios.plant import Plant, StepReading
from tests.scenarios.runner import CycleTrace, ScenarioRunner
from tests.scenarios.scenario_setup import (
    effective_peak_limit_w,
    judge_c4_then_r3,
    setup_coordinator,
)

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
        hass, entry_data=t1.entry_data(), entry_options=t1.entry_options(), mode=MODE_POWER
    )
    options = t1.entry_options()
    voltage = options[CONF_NOMINAL_VOLTAGE]
    plant = Plant(household_w=t1.HOUSEHOLD_W, voltage=voltage, lag_cycles=0)
    runner = ScenarioRunner(hass, coordinator, plant, freezer=freezer, grid_voltage=voltage)
    ceiling_w = t1.ceiling_a(options) * voltage

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
    assert "(headroom -930.0 W)" in message
    assert "active_mode 'Power'" in message
    assert "commanded 16.0 A, true draw 16.0 A, reported charger 3680.0 W" in message
    # Step 0's own row, in the context table -- its headroom (2750.0 W) too, so a reader sees
    # the actuation delay's own headroom, not only the breaching step's.
    assert (
        "   0         16.0          0.0         0.0         3000.0  False        Power      2750.0"
        in message
    )


# --- C4 member: the reaction allowance's own oracle self-tests -------------------------------


def _reaction_trace(*steps: tuple[float, float, float]) -> list[CycleTrace]:
    """Builds a hand-built trace for `_household_reaction_allowed`'s own self-tests below, one
    `CycleTrace` per `(household_w, true_charger_w, true_draw_a)` triple. `reported_charger_w`
    and `net_w` never matter to the allowance (it reads only `household_w`, `true_charger_w`
    and `true_draw_a`), so both are set equal to their true counterparts."""
    trace = []
    for index, (household_w, true_charger_w, true_draw_a) in enumerate(steps):
        true_import_w = true_charger_w + household_w
        reading = StepReading(
            true_draw_a=true_draw_a,
            true_charger_w=true_charger_w,
            reported_charger_w=true_charger_w,
            household_w=household_w,
            true_import_w=true_import_w,
            net_w=true_import_w,
        )
        trace.append(
            CycleTrace(
                index=index,
                commanded_current_a=true_draw_a,
                reading=reading,
                faulted=False,
                active_mode=MODE_POWER,
            )
        )
    return trace


def test_should_not_report_a_breach_when_a_household_increase_alone_caused_it():
    """(i) An increase whose breach the change itself caused is exempt on that step: step 0
    sits exactly at the 4000 W ceiling, step 1's household rises by 500 W with the charger's
    draw unchanged -- against the PREVIOUS cycle's household reading the charger alone would not
    have breached (2000 + 2000 W <= 4000 W ceiling), so step 1's breach is the household swing's
    own, which the previous control cycle could not have foreseen."""
    # Arrange
    trace = _reaction_trace((2000.0, 2000.0, 8.0), (2500.0, 2000.0, 8.0))

    # Act
    check_c4(trace, ceiling_w=4000.0)

    # Assert
    # No InvariantViolation raised: the Act call above completing is the assertion -- the
    # allowance exempts this step from C4's otherwise-breaching 4500 W true import.


def test_should_report_a_breach_when_a_household_decrease_caused_it():
    """(ii) A decrease is never exempted -- even here, where it is the charger's own rising
    draw, not the household, that causes the breach: step 1's household actually FALLS from
    step 0's (3000 W to 2500 W) while the charger's draw rises enough to breach on its own."""
    # Arrange
    trace = _reaction_trace((3000.0, 0.0, 0.0), (2500.0, 2000.0, 8.0))

    # Act
    with pytest.raises(InvariantViolation) as excinfo:
        check_c4(trace, ceiling_w=4000.0)

    # Assert
    assert "C4 breach at step 1" in str(excinfo.value)


def test_should_report_a_breach_already_present_before_the_increase():
    """(iii) A breach already present against the PREVIOUS cycle's household reading is not
    exempted just because the household also rose this step: step 1's charger draw alone
    against step 0's household (3800 W) already breaches (2000 + 3800 W > 4000 W ceiling), so
    the 200 W household rise did not cause it and was not "unforeseen"."""
    # Arrange
    trace = _reaction_trace((3800.0, 0.0, 0.0), (4000.0, 2000.0, 8.0))

    # Act
    with pytest.raises(InvariantViolation) as excinfo:
        check_c4(trace, ceiling_w=4000.0)

    # Assert
    assert "C4 breach at step 1" in str(excinfo.value)


def test_should_not_report_a_breach_when_the_household_alone_is_above_the_ceiling_at_zero_draw():
    """(iv) Household load alone above the ceiling while the charger draws 0 A is not a
    violation -- there is no commanded current left to react with, so causation does not apply
    (`_household_reaction_allowed`'s own docstring)."""
    # Arrange
    trace = _reaction_trace((4500.0, 0.0, 0.0))

    # Act
    check_c4(trace, ceiling_w=4000.0)

    # Assert
    # No InvariantViolation raised: the Act call above completing is the assertion.


def test_should_report_a_breach_on_the_step_after_an_exempt_one():
    """(v) An exempt step does not exempt the one after it: step 1 repeats scenario (i)'s own
    exemption, but step 2 holds the same household and charger draw as step 1 -- no further
    household increase to exempt it -- so step 2's breach is judged and reported."""
    # Arrange
    trace = _reaction_trace((2000.0, 2000.0, 8.0), (2500.0, 2000.0, 8.0), (2500.0, 2000.0, 8.0))

    # Act
    with pytest.raises(InvariantViolation) as excinfo:
        check_c4(trace, ceiling_w=4000.0)

    # Assert
    assert "C4 breach at step 2" in str(excinfo.value)


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
_WARMUP_CYCLES = 7  # the pre-step world settles at 8 A after the plant's own one-cycle startup
# delay (step 0 itself still reads 0 A true draw -- nothing commanded yet; the world settles at
# 8 A from step 1 onward) -- the target current itself never exceeds the pre-step headroom, so
# no clamp/grace-period branch ever engages -- this just gives the command-history-dependent raw
# baseline a few steady cycles to read before the household step, so the step is the scenario's
# own, deliberate cause.
_STEP_CYCLES = 3  # enough for the bypass's one-cycle-removed breach to land.

# R3's grace period and the control cycle it is counted in, pinned explicitly rather than left
# to whatever production would default them to -- read back from the SAME options dict `_setup`
# hands the coordinator, never from a product constant (ADR-0037's invariant-oracle rule).
_PEAK_GRACE_MIN = 2.0
_CONTROL_INTERVAL_S = 10.0
_GRACE_CAP_CYCLES = 12  # ceil(120 s / 10 s) -- `_grace_period_allowed`'s own derivation.


def _r3_entry_data():
    """CapTar present, no solar -- R3 is in force (C3, R18); Power's own peak-protection option
    stays at its default (enabled, R17)."""
    return entry_data_base(**{CONF_SOLAR_AVAILABLE: False, CONF_CAPTAR_AVAILABLE: True})


def _r3_entry_options():
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


async def _r3_setup(hass):
    seed_charger_states(hass, status="Charging", net_w=0.0, charger_w=0.0)
    return await setup_coordinator(
        hass, entry_data=_r3_entry_data(), entry_options=_r3_entry_options(), mode=MODE_POWER
    )


# `_effective_peak_limit_w`/`_judge_r3` moved to `scenario_setup.py` as `effective_peak_limit_w`/
# `judge_c4_then_r3` -- a later tier (T3) needs both and reuses them from there rather than
# reaching into this module's private names.


async def test_should_report_a_peak_breach_when_the_baseline_debounce_and_the_lower_charger_term_are_bypassed(  # noqa: E501
    hass, freezer, monkeypatch
):
    # Arrange
    # ADR-0039: debounce_baseline_w gates the household-baseline reading against the System's
    # own actuation (`command_changed`) and debounces a headroom-increasing swing. Bypassing it
    # -- returning the raw, undistinguished reading every cycle -- is #990's shape: a reading
    # taken one cycle after the System's own current step is partly a measurement of that step,
    # not of the household, and here it is accepted anyway. ADR-0059's lower charger term is
    # bypassed too (the reading alone, as before it): it keeps that stale reading out of the
    # baseline at its source, so a mutation of the debounce alone leaves no breach to report.
    # The patch also reverts C4's ADR-0058 operand, because `_charger_draw_w` is shared; that is
    # harmless here, since C4's headroom (about 18 A) is far above the 8 A target.
    monkeypatch.setattr(
        "custom_components.smart_charging.coordinator.SmartChargingCoordinator._charger_draw_w",
        lambda _self, charger_w, _voltage: charger_w,
    )
    monkeypatch.setattr(
        "custom_components.smart_charging.coordinator.debounce_baseline_w",
        lambda raw_baseline_w, tracker, *, debounce_cycles, command_changed: (
            raw_baseline_w,
            tracker,
        ),
    )
    freezer.move_to("2026-01-15 12:00:00")
    coordinator = await _r3_setup(hass)
    options = _r3_entry_options()
    voltage = options[CONF_NOMINAL_VOLTAGE]
    plant = Plant(household_w=_HOUSEHOLD_W, voltage=voltage, lag_cycles=1)
    runner = ScenarioRunner(hass, coordinator, plant, freezer=freezer, grid_voltage=voltage)

    # Act
    # The warm-up settles the startup transient at a steady 8 A (Power's own target current,
    # below the pre-step 9 A headroom); the household step to 1100 W total (500 + 600) then
    # makes R3 step the current down (#990's shape): the bypassed debounce and lower term let the
    # command oscillate (6, 8, 7 A) for a few cycles after the step before settling, re-granting
    # headroom the household no longer has -- the breach lands once the over-granted current
    # has actually been drawn, one cycle after the household itself last changed, with no
    # command change of its own to defer it a further cycle.
    await runner.run(_WARMUP_CYCLES, judge=judge_c4_then_r3(options))
    plant.set_household_w(_HOUSEHOLD_W + _HOUSEHOLD_STEP_W)
    with pytest.raises(InvariantViolation) as excinfo:
        await runner.run(_STEP_CYCLES, judge=judge_c4_then_r3(options))

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
    household step), with `debounce_baseline_w` and `_charger_draw_w` left exactly as production
    has them -- proves the violation above is the bypasses' doing, not an artifact of the
    plant/world itself."""
    # Arrange
    freezer.move_to("2026-01-15 12:00:00")
    coordinator = await _r3_setup(hass)
    options = _r3_entry_options()
    voltage = options[CONF_NOMINAL_VOLTAGE]
    plant = Plant(household_w=_HOUSEHOLD_W, voltage=voltage, lag_cycles=1)
    runner = ScenarioRunner(hass, coordinator, plant, freezer=freezer, grid_voltage=voltage)
    target_w = effective_peak_limit_w(options)

    # Act
    await runner.run(_WARMUP_CYCLES, judge=judge_c4_then_r3(options))
    plant.set_household_w(_HOUSEHOLD_W + _HOUSEHOLD_STEP_W)
    trace = await runner.run(_STEP_CYCLES, judge=judge_c4_then_r3(options))

    # Assert
    # No InvariantViolation raised above is the control's own point; this additionally pins the
    # settled, correctly-debounced current so a future regression that merely stopped breaching
    # loudly (e.g. by never reducing at all) still fails here.
    expected_a = math.floor((target_w - (_HOUSEHOLD_W + _HOUSEHOLD_STEP_W)) / voltage)
    assert trace[-1].commanded_current_a == expected_a


# --- R3's own allowances, engaged on CORRECT (unmutated) product code -------------------------


async def test_should_sanction_the_breach_when_a_case_a_deferral_delays_the_increase_one_cycle(  # noqa: E501
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
    one, per ADR-0037's invariant-oracle rule. Also stands as the fixed cause check's own control:
    step 9's true charger draw plus step 7's household reading (1610 + 1100 = 2710 W) clears the
    2750 W target, so `_deferred_reaction_allowed` keeps exempting this genuine, correctly-
    deferred breach."""
    # Arrange
    freezer.move_to("2026-01-15 12:00:00")
    coordinator = await _r3_setup(hass)
    options = _r3_entry_options()
    voltage = options[CONF_NOMINAL_VOLTAGE]
    plant = Plant(household_w=_HOUSEHOLD_W, voltage=voltage, lag_cycles=1)
    runner = ScenarioRunner(hass, coordinator, plant, freezer=freezer, grid_voltage=voltage)
    target_w = effective_peak_limit_w(options)

    # Act
    trace = await runner.run(_WARMUP_CYCLES, judge=judge_c4_then_r3(options))
    plant.set_household_w(1100.0)
    trace = await runner.run(1, judge=judge_c4_then_r3(options))
    plant.set_household_w(1300.0)
    trace = await runner.run(6, judge=judge_c4_then_r3(options))

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


# --- the deferral allowance's own cause check --------------------------------------------------


def test_should_report_an_over_grant_when_it_lands_on_a_case_a_deferred_cycle():
    """`_deferred_reaction_allowed` must not exempt any breach SHAPED like a case-(a)-deferred
    household increase, regardless of its actual size -- only the cause check (the deferred
    reading's own true charger draw against the target) proves the deferral is what the breach
    is due to. A command written from an over-granted current (a debounce bypass, a clamp
    defect) landing on the very same cycles a genuine deferral would have landed on is
    indistinguishable from the genuine case by shape alone, and must not be hidden behind it.

    A hand-built trace isolates exactly that gap, the same technique the ordering test below
    already uses, since engineering the full coordinator/plant/bypass stack to land an over-grant
    on the exact cycle a case-(a) deferral also covers (rather than the smaller, legitimate
    over-grant the committed control above exercises) is comparatively fragile -- `check_r3`'s
    allowances are pure functions of the trace (ADR-0037's invariant-oracle rule), so judging them
    directly against a constructed trace is the same discipline, not a deviation from it.

    Shape: commanded holds at 8 A for two cycles, steps down to 6 A (a command step-down,
    index 1 -> 2); the household increases one cycle later (index 3), which case (a) correctly
    defers (the command changed between index 1 and index 2) -- the LEGITIMATE reaction to that
    deferred reading would land at index 4 and must still clear the target against the
    household reading the deferral stood in for (index 2's, 1000 W): a true charger draw up to
    `target_w - 1000` W. Here it draws far more (10 A = 2300 W, well past that bound) -- an
    over-grant no deferral causes -- while the household itself does not change again at index 4
    (ruling out the shared same-cycle allowance as an alternative explanation) and the draw is
    not the minimum current either (ruling out the grace-period allowance)."""
    # Arrange
    target_w = 3000.0
    min_current_a = 6.0

    def _row(index, commanded_a, true_draw_a, household_w):
        true_charger_w = true_draw_a * 230.0
        return CycleTrace(
            index=index,
            commanded_current_a=commanded_a,
            reading=StepReading(
                true_draw_a=true_draw_a,
                true_charger_w=true_charger_w,
                reported_charger_w=true_charger_w,
                household_w=household_w,
                true_import_w=true_charger_w + household_w,
                net_w=true_charger_w + household_w,
            ),
            faulted=False,
            active_mode=MODE_POWER,
        )

    trace = [
        _row(0, commanded_a=8.0, true_draw_a=0.0, household_w=1000.0),
        _row(1, commanded_a=8.0, true_draw_a=8.0, household_w=1000.0),
        _row(2, commanded_a=6.0, true_draw_a=8.0, household_w=1000.0),  # command step-down
        _row(3, commanded_a=6.0, true_draw_a=6.0, household_w=1800.0),  # household increase,
        # one cycle after the step-down -- case (a) defers this reading (exempted by the shared
        # same-cycle allowance here: 1380 + 1000 <= 3000).
        _row(4, commanded_a=10.0, true_draw_a=10.0, household_w=1800.0),  # the over-grant: a
        # genuine deferral reacting to index 2's household (1000 W) could draw at most
        # floor((3000 - 1000) / 230) = 8 A here, not 10 A.
    ]

    # Act
    with pytest.raises(InvariantViolation) as excinfo:
        check_r3(
            trace,
            effective_peak_limit_w=target_w,
            min_current_a=min_current_a,
            grace_period_s=120.0,
            control_interval_s=10.0,
        )

    # Assert
    assert "R3 breach at step 4" in str(excinfo.value)


# --- the grace-period allowance's own two self-tests: the extension's `break`, 0 A reset/re-arm


def _grace_row(index, *, true_draw_a, true_charger_w, household_w, commanded_a=None):
    """One hand-built `CycleTrace` row for the grace-period cap's own self-tests below -- unlike
    `_row` above (the deferral cause check's own helper), `true_charger_w` is passed explicitly
    rather than derived from `true_draw_a * 230.0`, since the `break` self-test below needs one
    row's `true_charger_w` deliberately out of step with its own `true_draw_a` to isolate the
    extension loop's own ordering from the cause check's arithmetic -- a synthetic reading no
    real plant ever reports, same as the over-grant test above isolates its own check with an
    unphysical over-grant."""
    if commanded_a is None:
        commanded_a = true_draw_a
    return CycleTrace(
        index=index,
        commanded_current_a=commanded_a,
        reading=StepReading(
            true_draw_a=true_draw_a,
            true_charger_w=true_charger_w,
            reported_charger_w=true_charger_w,
            household_w=household_w,
            true_import_w=true_charger_w + household_w,
            net_w=true_charger_w + household_w,
        ),
        faulted=False,
        active_mode=MODE_POWER,
    )


def test_should_report_a_breach_when_a_pre_existing_breach_gets_no_leading_cycle_extension():
    """The extension loop's own `break` (`_grace_period_allowed`): once the run's first cycle
    fails both leading-cycle checks, no LATER cycle's own pass may still extend the cap -- a
    cycle deeper in the run merely happening to satisfy one of those checks is not one of the
    run's own leading divergences (that function's own docstring). Proven here by a run whose
    very first cycle (index 0, so `_household_reaction_allowed`/`_deferred_reaction_allowed` are
    both trivially `False` -- each gated on `index > 0` and `index >= 2` respectively) is already
    breaching with no prior cycle to react to -- a pre-existing breach, not something the clamp
    could have been expected to foresee -- while index 1's own check is deliberately engineered
    to pass (`true_charger_w` set out of step with `true_draw_a` there, see `_grace_row`): with
    the `break` intact, that pass is never reached, so the 13-cycle run (one past the bare
    12-cycle cap) still reports.

    Temporarily deleting the `break` (replacing it with a bare `extension += 1`, no `else`) flips
    this test green -- the removal proof's own run is quoted in this PR's own body."""
    # Arrange
    target_w = 3000.0
    min_current_a = 6.0
    trace = [
        _grace_row(0, true_draw_a=6.0, true_charger_w=1380.0, household_w=1700.0),
        # Index 1's own check is engineered to pass if ever reached: true_charger_w lowered to
        # 1000.0 (not 6.0 * 230.0) so its cause check (1000.0 + 1700.0 <= 3000.0) clears, while
        # the household increase (1700.0 -> 2050.0) still keeps this cycle itself breaching
        # (1000.0 + 2050.0 = 3050.0 > 3000.0) and at the minimum current.
        _grace_row(1, true_draw_a=6.0, true_charger_w=1000.0, household_w=2050.0),
    ] + [
        _grace_row(i, true_draw_a=6.0, true_charger_w=1380.0, household_w=2050.0)
        for i in range(2, 13)
    ]

    # Act
    with pytest.raises(InvariantViolation) as excinfo:
        check_r3(
            trace,
            effective_peak_limit_w=target_w,
            min_current_a=min_current_a,
            grace_period_s=120.0,
            control_interval_s=10.0,
        )

    # Assert
    assert "R3 breach at step 12" in str(excinfo.value)


def test_should_stay_quiet_when_a_momentary_0a_cycle_re_arms_a_fresh_grace_period():
    """The 0 A cycle's own reset/re-arm (`_grace_period_allowed`'s own docstring): a momentary
    0 A cycle -- the force-stop itself -- ends the counted run rather than letting it continue
    through, so a breach that resumes right after is a FRESH occurrence with its own, fully
    budgeted cap. 12 breaching-at-minimum cycles, one 0 A (non-breaching) cycle, then 12 more
    breaching-at-minimum cycles stays quiet throughout -- each run is within the bare 12-cycle
    cap on its own -- while the SAME 13 cycles with no 0 A cycle between them (the control
    directly below) reports, proving the quiet run above is not simply "under the cap either
    way"."""
    # Arrange
    target_w = 3000.0
    min_current_a = 6.0
    first_run = [
        _grace_row(i, true_draw_a=6.0, true_charger_w=1380.0, household_w=2000.0) for i in range(12)
    ]
    force_stop = [
        _grace_row(12, true_draw_a=0.0, true_charger_w=0.0, household_w=2000.0, commanded_a=0.0)
    ]
    second_run = [
        _grace_row(i, true_draw_a=6.0, true_charger_w=1380.0, household_w=2000.0)
        for i in range(13, 25)
    ]
    trace = first_run + force_stop + second_run

    # Act
    check_r3(
        trace,
        effective_peak_limit_w=target_w,
        min_current_a=min_current_a,
        grace_period_s=120.0,
        control_interval_s=10.0,
    )

    # Assert
    # No InvariantViolation raised above is this test's own point -- the control below proves the
    # same 25-cycle shape, minus the 0 A re-arm, does NOT stay quiet.


def test_should_report_a_breach_when_13_consecutive_cycles_never_re_arm_the_grace_period():
    """Control for the test above: the SAME breaching-at-minimum cycles, with no 0 A cycle to
    reset the count -- 13 consecutive cycles overruns the bare 12-cycle cap (no leading-cycle
    extension applies here either -- index 0 of this run is its own trace's first cycle, same as
    the `break` self-test above) and must report, proving the quiet 12/0A/12 shape above is
    genuinely due to the reset, not to both runs independently fitting under the cap regardless."""
    # Arrange
    target_w = 3000.0
    min_current_a = 6.0
    trace = [
        _grace_row(i, true_draw_a=6.0, true_charger_w=1380.0, household_w=2000.0) for i in range(13)
    ]

    # Act
    with pytest.raises(InvariantViolation) as excinfo:
        check_r3(
            trace,
            effective_peak_limit_w=target_w,
            min_current_a=min_current_a,
            grace_period_s=120.0,
            control_interval_s=10.0,
        )

    # Assert
    assert "R3 breach at step 12" in str(excinfo.value)


# --- the grace-period allowance: cap, extension and non-reset on a household wiggle ------------


async def test_should_sanction_the_breach_when_the_grace_period_at_the_minimum_current_holds(  # noqa: E501
    hass, freezer
):
    """R3's own grace-period allowance (`invariants.py`'s `_grace_period_allowed`): a household
    step large enough (500 -> 2400 W) that the post-step headroom falls below the minimum
    charging current holds the clamp at that minimum while a continuous breach rides out R3's
    configured grace period -- "a momentary breach does not stop charging". Unmutated product
    code throughout, same as the test above."""
    # Arrange
    freezer.move_to("2026-01-15 12:00:00")
    coordinator = await _r3_setup(hass)
    options = _r3_entry_options()
    voltage = options[CONF_NOMINAL_VOLTAGE]
    plant = Plant(household_w=_HOUSEHOLD_W, voltage=voltage, lag_cycles=1)
    runner = ScenarioRunner(hass, coordinator, plant, freezer=freezer, grid_voltage=voltage)
    target_w = effective_peak_limit_w(options)

    # Act
    await runner.run(_WARMUP_CYCLES, judge=judge_c4_then_r3(options))
    plant.set_household_w(2400.0)
    trace = await runner.run(6, judge=judge_c4_then_r3(options))

    # Assert
    # Nothing raised above is this test's own point. This additionally proves the breach was
    # real (not vacuous) and that it is genuinely the grace period doing the sanctioning: the
    # charger is already down at the minimum current (6 A) and stays breaching for several
    # cycles running, well inside the configured grace period's cap (12 cycles -- the pinned
    # 2 min grace at a 10 s control interval, `ceil(120 / 10)`) -- never once reaching 0 A.
    held_at_minimum = trace[_WARMUP_CYCLES + 1 :]
    assert len(held_at_minimum) >= 5
    for t in held_at_minimum:
        assert t.reading.true_draw_a == options[CONF_MIN_CURRENT]
        assert t.reading.true_import_w > target_w, "the hold should have genuinely breached"
        assert not t.faulted


def _r3_entry_options_at_minimum_target():
    """Same world as `_r3_entry_options` above, but Power's OWN target current is already the
    minimum (`CONF_MIN_CURRENT`'s default, 6 A) before anything breaches -- the leading-cycle
    coincidence `_grace_period_allowed`'s own docstring derives the cap's extension from: the
    charger sits at the minimum for its own reasons, long before a breach even begins, and the
    household jump that finally breaches lands on that same, already-at-minimum cycle."""
    return entry_options_base(
        **{
            CONF_DEFAULT_TARGET_CURRENT: 6.0,
            CONF_MAX_PEAK_KW: _PEAK_KW,
            CONF_PEAK_FLOOR_KW: _PEAK_KW,
            CONF_SAFETY_MARGIN_W: _SAFETY_MARGIN_W,
            CONF_PEAK_GRACE_MIN: _PEAK_GRACE_MIN,
            CONF_CONTROL_INTERVAL_S: _CONTROL_INTERVAL_S,
        }
    )


async def test_should_sanction_the_breach_through_the_grace_period_when_already_at_the_minimum(  # noqa: E501
    hass, freezer
):
    """Control (i): the charger already sits at the minimum current -- by Power's OWN target
    (6 A), not yet any clamp reaction -- for 15 cycles before the household rise (500 -> 2400 W)
    makes it a genuine breach. Those 15 pre-existing cycles must NOT count against the grace
    budget (they are never breaching, so `_breaching_at_minimum` excludes them); the household-
    jump cycle itself coincidentally reads as both at-minimum and breaching from its own first
    cycle, one cycle before the clamp's own reaction could possibly reach true draw -- without
    the cap's own extension for that leading cycle (`_grace_period_allowed`'s own docstring), the
    run would overrun the cap by exactly the one cycle the coincidence costs, on this CORRECT,
    unmutated world. Runs through the whole grace period and past it, into the real product's own
    (on-time) force-stop, and stays quiet throughout."""
    # Arrange
    freezer.move_to("2026-01-15 12:00:00")
    options = _r3_entry_options_at_minimum_target()
    seed_charger_states(hass, status="Charging", net_w=0.0, charger_w=0.0)
    coordinator = await setup_coordinator(
        hass, entry_data=_r3_entry_data(), entry_options=options, mode=MODE_POWER
    )
    voltage = options[CONF_NOMINAL_VOLTAGE]
    plant = Plant(household_w=_HOUSEHOLD_W, voltage=voltage, lag_cycles=1)
    runner = ScenarioRunner(hass, coordinator, plant, freezer=freezer, grid_voltage=voltage)
    target_w = effective_peak_limit_w(options)

    # Act
    await runner.run(15, judge=judge_c4_then_r3(options))
    plant.set_household_w(2400.0)
    trace = await runner.run(_GRACE_CAP_CYCLES + 1, judge=judge_c4_then_r3(options))

    # Assert
    # Nothing raised above is this test's own point. This additionally proves the breach was
    # real throughout the grace period, and that the real product's own force-stop lands
    # exactly on schedule (never a cycle early or late) once it does.
    breaching = trace[15:]
    assert len(breaching) == _GRACE_CAP_CYCLES + 1
    for t in breaching[:-1]:
        assert t.reading.true_draw_a == options[CONF_MIN_CURRENT]
        assert t.reading.true_import_w > target_w, "the hold should have genuinely breached"
    # Precondition, not a second behaviour under test: the force-stop landing exactly on schedule
    # is what makes `breaching`'s own slicing above correct (the cap's extension is this test's
    # one point) -- not itself asserted as a separate outcome.
    assert breaching[-1].commanded_current_a == 0.0, (
        "the force-stop command should have fired by now, on schedule"
    )


async def test_should_sanction_the_breach_when_a_case_a_deferral_delays_the_grace_timer_start(  # noqa: E501
    hass, freezer
):
    """A case-(a) deferral delaying the household increase that starts this run's breach delays,
    by that same cycle, the PRODUCT's own request-side timer start (`apply_peak_clamp`'s own
    `is_breaching`, computed from the debounced baseline the deferral holds stale) -- not true
    draw, which still lags whatever is actually commanded by its usual one cycle either way. This
    run also engages the OTHER leading-cycle extension (`_household_reaction_allowed`'s own cycle,
    step 13, where the jump itself lands on a command already coincidentally at the minimum),
    stacked with the deferral's own extension (step 14) -- together widening the cap from 12 to
    14, exactly the breaching run's own length. Without both extensions the oracle would overrun
    by two and fire on this CORRECT, unmutated world.

    Repro: 7 cycles at 500 W, ~5 at 1100 W, 1 at 1300 W, then 14 at 2400 W -- expect quiet
    throughout; the breaching run itself spans steps 13..26 (14 cycles, ending one cycle past the
    point the undefended 12-cycle cap alone would have fired)."""
    # Arrange
    freezer.move_to("2026-01-15 12:00:00")
    coordinator = await _r3_setup(hass)
    options = _r3_entry_options()
    voltage = options[CONF_NOMINAL_VOLTAGE]
    plant = Plant(household_w=_HOUSEHOLD_W, voltage=voltage, lag_cycles=1)
    runner = ScenarioRunner(hass, coordinator, plant, freezer=freezer, grid_voltage=voltage)
    target_w = effective_peak_limit_w(options)

    # Act
    await runner.run(7, judge=judge_c4_then_r3(options))
    plant.set_household_w(1100.0)
    await runner.run(5, judge=judge_c4_then_r3(options))
    plant.set_household_w(1300.0)
    await runner.run(1, judge=judge_c4_then_r3(options))
    plant.set_household_w(2400.0)
    trace = await runner.run(14, judge=judge_c4_then_r3(options))

    # Assert
    # Nothing raised above is this test's own point: both leading-cycle extensions engage here
    # (the at-minimum coincidence at step 13, the deferral's own at step 14), widening the cap
    # from 12 to 14 -- exactly the breaching run's own length pinned below. This additionally
    # proves the tail end genuinely breached at the minimum current, so the allowances were
    # actually exercised, not vacuously unneeded.
    breaching_run = trace[13:]
    assert len(breaching_run) == 14, (
        "the run should span steps 13..26 -- the cap's own 12 plus both leading-cycle extensions"
    )
    assert breaching_run[0].reading.true_draw_a == options[CONF_MIN_CURRENT], (
        "step 13, the run's own leading cycle, should already sit at the minimum"
    )
    assert trace[-1].reading.true_draw_a == options[CONF_MIN_CURRENT]
    assert trace[-1].reading.true_import_w > target_w, "the tail should have genuinely breached"


def _apply_peak_clamp_without_force_stop(
    desired_current,
    baseline_w,
    voltage,
    effective_peak_limit_kw,
    safety_margin_w,
    min_a,
    grace_period_s,
    tracker,
    now,
):
    """Mutation: the grace period's force-stop never lands -- a continuous breach at the
    minimum current rides out forever, never force-stopping to 0 A. Reimplements
    `apply_peak_clamp`'s own breach-tracking (`engines/billing_protection.py`) with the
    force-stop branch removed, rather than monkeypatching the real function's result, since the
    real function's own force-stop IS the behaviour under test -- there is nothing to call
    through to."""
    headroom_a = peak_headroom_a(
        baseline_w=baseline_w,
        voltage=voltage,
        effective_peak_limit_kw=effective_peak_limit_kw,
        safety_margin_w=safety_margin_w,
    )
    clamped = min(desired_current, headroom_a)
    is_breaching = desired_current >= min_a and headroom_a < min_a
    if is_breaching:
        breached_since = tracker.breached_since if tracker.breached_since is not None else now
        return min_a, PeakBreachTracker(breached_since=breached_since), False
    return clamped, PeakBreachTracker(breached_since=None), False


async def test_should_report_a_breach_when_the_force_stop_never_lands(hass, freezer, monkeypatch):
    """Mutation: with the force-stop disabled (`_apply_peak_clamp_without_force_stop`), a
    genuine, continuous breach at the minimum current rides out the grace period and then keeps
    going -- `check_r3` must catch it exactly at the first cycle past the cap
    (`_GRACE_CAP_CYCLES`), proving the cap is a real bound and not merely never reached in
    practice."""
    # Arrange
    monkeypatch.setattr(
        "custom_components.smart_charging.coordinator.apply_peak_clamp",
        _apply_peak_clamp_without_force_stop,
    )
    freezer.move_to("2026-01-15 12:00:00")
    coordinator = await _r3_setup(hass)
    options = _r3_entry_options()
    voltage = options[CONF_NOMINAL_VOLTAGE]
    plant = Plant(household_w=_HOUSEHOLD_W, voltage=voltage, lag_cycles=1)
    runner = ScenarioRunner(hass, coordinator, plant, freezer=freezer, grid_voltage=voltage)

    # Act
    await runner.run(_WARMUP_CYCLES, judge=judge_c4_then_r3(options))
    plant.set_household_w(2400.0)
    with pytest.raises(InvariantViolation) as excinfo:
        await runner.run(_GRACE_CAP_CYCLES + 2, judge=judge_c4_then_r3(options))

    # Assert
    # Pinned to the exact cycle the cap says must be the first violating one -- the first
    # breaching-at-minimum cycle is step 8 (_WARMUP_CYCLES + 1, the plant's one-cycle lag after
    # the household step), so the cap's own count (12 further cycles still allowed) puts the
    # first unsanctioned one at step 8 + 12 = 20, still drawing the minimum current.
    message = str(excinfo.value)
    assert "R3 breach at step 20" in message
    assert "true draw 6.0 A" in message


async def test_should_report_a_breach_when_a_household_wiggle_lands_mid_run(
    hass, freezer, monkeypatch
):
    """A household change PARTWAY through an already-running breach must not reset, or break,
    the grace count -- R3's "continuously" tracks true import against target, not the household
    trace, and `apply_peak_clamp`'s own timer does not reset on a household change either. The
    force-stop is disabled, same as the mutation above, so the breach is genuinely never-ending
    on its own; a small household wiggle midway through (2400 -> 2410 W) must not let it ride out
    indefinitely by restarting the count each time."""
    # Arrange
    monkeypatch.setattr(
        "custom_components.smart_charging.coordinator.apply_peak_clamp",
        _apply_peak_clamp_without_force_stop,
    )
    freezer.move_to("2026-01-15 12:00:00")
    coordinator = await _r3_setup(hass)
    options = _r3_entry_options()
    voltage = options[CONF_NOMINAL_VOLTAGE]
    plant = Plant(household_w=_HOUSEHOLD_W, voltage=voltage, lag_cycles=1)
    runner = ScenarioRunner(hass, coordinator, plant, freezer=freezer, grid_voltage=voltage)

    # Act
    # The breach run starts at step 8 (the plant's one-cycle lag after the household step), same
    # as the mutation above -- the first 6 further cycles (steps 7-12) stay within the cap, same
    # as the committed grace-period control above, before the wiggle lands.
    await runner.run(_WARMUP_CYCLES, judge=judge_c4_then_r3(options))
    plant.set_household_w(2400.0)
    await runner.run(6, judge=judge_c4_then_r3(options))
    plant.set_household_w(2410.0)  # a small mid-run wiggle -- well after the run's own leading
    # cycle, and not itself exempted by any allowance (the increase alone does not clear the
    # cause check at this headroom) -- must not restart the count.
    with pytest.raises(InvariantViolation) as excinfo:
        await runner.run(_GRACE_CAP_CYCLES + 2 - 6, judge=judge_c4_then_r3(options))

    # Assert
    # The same first-cycle-past-the-cap step (8 + 12 = 20) as the mutation above -- the wiggle,
    # mid-run, changed nothing about where the cap bites.
    message = str(excinfo.value)
    assert "R3 breach at step 20" in message
    assert "true draw 6.0 A" in message


def _apply_peak_clamp_stopping_one_cycle_late(
    desired_current,
    baseline_w,
    voltage,
    effective_peak_limit_kw,
    safety_margin_w,
    min_a,
    grace_period_s,
    tracker,
    now,
):
    """Mutation: the force-stop fires one control cycle later than R3's own grace period
    allows (`grace_period_s + control cycle`, hard-coded to the scenario's own 10 s interval
    rather than threaded through as a parameter -- this mutation IS the one-cycle slip, not a
    configurable one)."""
    headroom_a = peak_headroom_a(
        baseline_w=baseline_w,
        voltage=voltage,
        effective_peak_limit_kw=effective_peak_limit_kw,
        safety_margin_w=safety_margin_w,
    )
    clamped = min(desired_current, headroom_a)
    is_breaching = desired_current >= min_a and headroom_a < min_a
    if is_breaching:
        breached_since = tracker.breached_since if tracker.breached_since is not None else now
        if now - breached_since >= grace_period_s + 10.0:
            return 0.0, PeakBreachTracker(breached_since=None), True
        return min_a, PeakBreachTracker(breached_since=breached_since), False
    return clamped, PeakBreachTracker(breached_since=None), False


async def test_should_report_a_breach_when_the_force_stop_lands_one_cycle_late(
    hass, freezer, monkeypatch
):
    """Mutation: the force-stop still lands, but one control cycle later than R3's own grace
    period allows (`_apply_peak_clamp_stopping_one_cycle_late`) -- `check_r3` must catch this
    too, at the same first-cycle-past-the-cap step as the "never stops" mutation above, since
    both mutations are indistinguishable from the trace alone until that cycle."""
    # Arrange
    monkeypatch.setattr(
        "custom_components.smart_charging.coordinator.apply_peak_clamp",
        _apply_peak_clamp_stopping_one_cycle_late,
    )
    freezer.move_to("2026-01-15 12:00:00")
    coordinator = await _r3_setup(hass)
    options = _r3_entry_options()
    voltage = options[CONF_NOMINAL_VOLTAGE]
    plant = Plant(household_w=_HOUSEHOLD_W, voltage=voltage, lag_cycles=1)
    runner = ScenarioRunner(hass, coordinator, plant, freezer=freezer, grid_voltage=voltage)

    # Act
    await runner.run(_WARMUP_CYCLES, judge=judge_c4_then_r3(options))
    plant.set_household_w(2400.0)
    with pytest.raises(InvariantViolation) as excinfo:
        await runner.run(_GRACE_CAP_CYCLES + 2, judge=judge_c4_then_r3(options))

    # Assert
    message = str(excinfo.value)
    assert "R3 breach at step 20" in message
    assert "true draw 6.0 A" in message


# --- judge_all's own ordering -------------------------------------------------------------


def _both_breaching_trace() -> list[CycleTrace]:
    """One hand-built cycle that breaches both C4's and R3's limits at once, with no allowance
    applicable to either -- shared by both ordering tests below, so each proves `judge_all`'s own
    list-order behaviour on the exact same trace rather than a precedence baked into
    `check_c4`/`check_r3` themselves."""
    reading = StepReading(
        true_draw_a=10.0,
        true_charger_w=2300.0,
        reported_charger_w=2300.0,
        household_w=2700.0,
        true_import_w=5000.0,
        net_w=5000.0,
    )
    return [
        CycleTrace(
            index=0,
            commanded_current_a=10.0,
            reading=reading,
            faulted=False,
            active_mode=MODE_POWER,
        )
    ]


def _c4_breaching(t):
    check_c4(t, ceiling_w=4000.0)


def _r3_breaching(t):
    check_r3(
        t,
        effective_peak_limit_w=3000.0,
        min_current_a=6.0,
        grace_period_s=_PEAK_GRACE_MIN * 60.0,
        control_interval_s=_CONTROL_INTERVAL_S,
    )


def test_should_report_a_c4_breach_when_c4_is_listed_first_and_both_would_fire():
    """`judge_all`'s documented ordering rule: the first invariant in the LIST wins -- C4 lists
    first in a scenario that wires both, since R3 only ever applies where C4 does too."""
    # Arrange
    trace = _both_breaching_trace()

    # Act
    with pytest.raises(InvariantViolation) as excinfo:
        judge_all(trace, [_c4_breaching, _r3_breaching])

    # Assert
    assert str(excinfo.value).startswith("C4 breach")


def test_should_report_an_r3_breach_when_r3_is_listed_first_and_both_would_fire():
    """The same list-order rule the test above proves, with the list reversed, on the exact same
    trace -- so it is `judge_all`'s own list order deciding the outcome, never some precedence
    baked into `check_c4`/`check_r3` themselves."""
    # Arrange
    trace = _both_breaching_trace()

    # Act
    with pytest.raises(InvariantViolation) as excinfo:
        judge_all(trace, [_r3_breaching, _c4_breaching])

    # Assert
    assert str(excinfo.value).startswith("R3 breach")
