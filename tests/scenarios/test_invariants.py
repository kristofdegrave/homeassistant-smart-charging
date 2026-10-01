"""T2 (epic #996): the shared invariant set (`invariants.py`) is judged against every cycle of
a scenario, and reports the first violating cycle with its context.

Each test below produces its violation through the seam by a `monkeypatch` mutation, so neither
depends on a product defect staying unfixed (ADR-0037's invariant-oracle rule cuts both ways:
the invariant must be quiet on a correct world, and must fire on a genuinely wrong one):

- the C4 member bypasses `clamp_to_ceiling` entirely (T1's own world, lag 0) -- `check_c4` must
  catch what a disabled clamp lets through.
- the R3 member bypasses `debounce_baseline_w` (the #990 shape, now reproduced at R3's call site
  through the plant's lag model rather than hand-seeded feedback) -- `check_r3` must catch the
  one-cycle-removed breach the bypass produces.
"""

import math

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_charging.const import (
    CONF_CAPTAR_AVAILABLE,
    CONF_DEFAULT_TARGET_CURRENT,
    CONF_MAX_PEAK_KW,
    CONF_NOMINAL_VOLTAGE,
    CONF_PEAK_FLOOR_KW,
    CONF_SAFETY_MARGIN_W,
    CONF_SOLAR_AVAILABLE,
    DOMAIN,
    MODE_POWER,
)
from tests.helpers import entry_data_base, entry_options_base, seed_charger_states
from tests.scenarios import test_grid_ceiling_under_lag as t1
from tests.scenarios.invariants import InvariantViolation, check_c4, check_r3
from tests.scenarios.plant import Plant
from tests.scenarios.runner import ScenarioRunner

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
    coordinator = await t1._setup(hass)
    options = t1._entry_options()
    voltage = options[CONF_NOMINAL_VOLTAGE]
    plant = Plant(household_w=t1._HOUSEHOLD_W, voltage=voltage, lag_cycles=0)
    runner = ScenarioRunner(hass, coordinator, plant, freezer=freezer, grid_voltage=voltage)
    ceiling_w = t1._ceiling_current_a(options) * voltage

    # Act / Assert
    with pytest.raises(InvariantViolation) as excinfo:
        await runner.run(t1._CYCLES, judge=lambda trace: check_c4(trace, ceiling_w=ceiling_w))

    # The bypassed clamp never reduces Power's own target current (16 A) at all, so the very
    # first cycle the charger actually draws already breaches -- names that cycle, the commanded
    # current, the readings and the active mode.
    message = str(excinfo.value)
    assert "C4 breach at step" in message
    assert f"ceiling {ceiling_w} W" in message
    assert f"active_mode {MODE_POWER!r}" in message


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
        }
    )


async def _setup(hass):
    seed_charger_states(hass, status="Charging", net_w=0.0, charger_w=0.0)
    entry = MockConfigEntry(domain=DOMAIN, data=_entry_data(), options=_entry_options())
    entry.add_to_hass(hass)
    if not await hass.config_entries.async_setup(entry.entry_id):
        raise RuntimeError(f"config entry {entry.entry_id} failed to set up")
    await hass.async_block_till_done()
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.smart_charging_mode", "option": MODE_POWER},
        blocking=True,
    )
    return entry.runtime_data.coordinator


def _effective_peak_limit_w(options: dict) -> float:
    """R3's own target: `resolve_effective_peak_limit`'s formula, pinned for this scenario by
    `max_peak_kw == peak_floor_kw` (above) to exactly `max_peak_kw` regardless of the
    internally-tracked monthly peak -- not restated as a bare number."""
    return options[CONF_MAX_PEAK_KW] * 1000.0 - options[CONF_SAFETY_MARGIN_W]


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
    target_w = _effective_peak_limit_w(options)

    def _judge(trace):
        check_r3(trace, effective_peak_limit_w=target_w)

    # Act
    # The warm-up settles the startup transient at a steady 8 A (Power's own target current,
    # below the pre-step 9 A headroom); the household step to 1100 W total (500 + 600) then
    # makes R3 step the current down to 7 A (#990's shape) -- the correctly-debounced control
    # (below) shows the reduction holds, while this run's bypassed debounce lets a stale,
    # one-cycle-old charger reading understate the baseline one cycle later, re-granting
    # headroom (back up to 8 A) the household no longer has -- which this breaches at the cycle
    # after that, once the over-granted current has actually been drawn.
    await runner.run(_WARMUP_CYCLES, judge=_judge)
    plant.set_household_w(_HOUSEHOLD_W + _HOUSEHOLD_STEP_W)
    with pytest.raises(InvariantViolation) as excinfo:
        await runner.run(_STEP_CYCLES, judge=_judge)

    # Assert
    message = str(excinfo.value)
    assert "R3 breach at step" in message
    assert f"effective peak limit {target_w} W" in message
    assert f"active_mode {MODE_POWER!r}" in message


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

    def _judge(trace):
        check_r3(trace, effective_peak_limit_w=target_w)

    # Act
    await runner.run(_WARMUP_CYCLES, judge=_judge)
    plant.set_household_w(_HOUSEHOLD_W + _HOUSEHOLD_STEP_W)
    trace = await runner.run(_STEP_CYCLES, judge=_judge)

    # Assert
    # No InvariantViolation raised above is the control's own point; this additionally pins the
    # settled, correctly-debounced current so a future regression that merely stopped breaching
    # loudly (e.g. by never reducing at all) still fails here.
    expected_a = math.floor((target_w - (_HOUSEHOLD_W + _HOUSEHOLD_STEP_W)) / voltage)
    assert trace[-1].commanded_current_a == expected_a
