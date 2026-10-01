"""T2 (epic #996): the shared invariant set (`invariants.py`) is judged against every cycle of
a scenario, and reports the first violating cycle with its context.

The C4 member's mutation test below produces its violation through the seam by a `monkeypatch`
mutation, so it does not depend on a product defect staying unfixed (ADR-0037's invariant-oracle
rule cuts both ways: the invariant must be quiet on a correct world, and must fire on a
genuinely wrong one): it bypasses `clamp_to_ceiling` entirely (T1's own world, lag 0) --
`check_c4` must catch what a disabled clamp lets through.

The reaction-allowance self-tests and the ordering tests further down (the allowance helper's
own branches; `judge_all`'s own list-order behaviour) build their trace by hand rather than
through the coordinator/plant seam: they are pure oracle self-tests, proving the oracle's own
tooling behaviour directly rather than a scenario outcome, so a hand-built trace is the right
seam for them -- unlike the mutation test above, which must run through the real stack.

Further invariant members (R3 and beyond) follow in a later task.
"""

import pytest

from custom_components.smart_charging.const import CONF_NOMINAL_VOLTAGE, MODE_POWER
from tests.helpers import seed_charger_states
from tests.scenarios import test_grid_ceiling_under_lag as t1
from tests.scenarios.invariants import InvariantViolation, check_c4, judge_all
from tests.scenarios.plant import Plant, StepReading
from tests.scenarios.runner import CycleTrace, ScenarioRunner
from tests.scenarios.scenario_setup import setup_coordinator

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


# --- judge_all's own ordering -------------------------------------------------------------


def _both_breaching_trace() -> list[CycleTrace]:
    """One hand-built cycle that breaches two independent limits at once, with no allowance
    applicable to either -- shared by both ordering tests below, so each proves `judge_all`'s own
    list-order behaviour on the exact same trace rather than a precedence baked into an
    individual check."""
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


def _other_breaching(t):
    """A trivial second invariant, standing in for whatever further member a scenario composes
    alongside C4 (R3 and beyond, in a later task) -- the behaviour under test here is `judge_all`'s
    own list order, not any particular invariant's rule."""
    if t[-1].reading.true_import_w > 3000.0:
        raise InvariantViolation("OTHER breach (test double)")


def test_should_report_the_first_listed_invariant_when_more_than_one_would_fire():
    """`judge_all`'s documented ordering rule: the first invariant in the LIST wins."""
    # Arrange
    trace = _both_breaching_trace()

    # Act
    with pytest.raises(InvariantViolation) as excinfo:
        judge_all(trace, [_c4_breaching, _other_breaching])

    # Assert
    assert str(excinfo.value).startswith("C4 breach")


def test_should_report_the_second_listed_invariant_when_it_is_listed_first_instead():
    """The same list-order rule the test above proves, with the list reversed, on the exact same
    trace -- so it is `judge_all`'s own list order deciding the outcome, never some precedence
    baked into an individual check."""
    # Arrange
    trace = _both_breaching_trace()

    # Act
    with pytest.raises(InvariantViolation) as excinfo:
        judge_all(trace, [_other_breaching, _c4_breaching])

    # Assert
    assert str(excinfo.value).startswith("OTHER breach")
