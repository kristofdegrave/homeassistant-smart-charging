"""T6 (epic #996): a whole-stack scenario where the commanded current oscillates and C4 is not
the backstop -- R3 alone holds the peak limit. ADR-0059's reproduction, run through the tier
(ADR-0037) on the world `test_peak_and_ceiling_under_lag.py` already established.

`Power` with CapTar present and its peak protection on (R17's default). That module's household
(2300 W), peak limit (5.6 kW) and safety margin (250 W) are reused, so R3's nominal headroom is
13 A (`floor((5350 - 2300) / 230)`). The grid supply ceiling is 40 A, so C4 never binds and every
breach would be R3's. Max current 32 A, the charger power reading lagging by 1 cycle.

Power's target current (`number.smart_charging_target_current`) alternates every step between
16 A, above R3's headroom, and 6 A, below it, for `_STEPS` steps: the oscillating command
ADR-0059 describes (C4's lag drove it in the sibling module; Solar's moving request can too).
Before ADR-0059, R3's baseline took this cycle's lagging charger reading, the deferral cases
discarded each high reading and committed the low ones that followed, and the committed baseline
went negative (-690 W): true import breached the peak limit, up to 5980 W against 5350 W. With
the lower of the reading and the last set current as the charger term, every reading is bounded
by what the System set, and every step is judged green by the whole invariant set.

The scenario-intent assertion is that the commanded current changes on every step, so the world
exercises the oscillation it exists for and not a steady command that would pass vacuously.
"""

import math

from homeassistant.const import ATTR_ENTITY_ID

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
from tests.scenarios.plant import Plant
from tests.scenarios.runner import ScenarioRunner, format_trace
from tests.scenarios.scenario_setup import (
    assert_charged_without_fault,
    effective_peak_limit_w,
    judge_c4_then_r3,
    setup_coordinator,
)

_TARGET_ENTITY_ID = "number.smart_charging_target_current"
_HOUSEHOLD_W = 2300.0  # steady throughout, as in `test_peak_and_ceiling_under_lag.py`.
_HIGH_TARGET_A = 16.0  # above R3's 13 A headroom.
_LOW_TARGET_A = 6.0  # at the charger's own minimum, so E8 never lifts it.
_MAX_CURRENT_A = 32.0
_GRID_CEILING_A = 40.0  # far above any draw here, so C4 never binds.
_GRID_SAFETY_OFFSET_A = 2.0
_SAFETY_MARGIN_W = 250.0
_MAX_PEAK_KW = 5.6
_PEAK_FLOOR_KW = 5.6  # pinned equal to _MAX_PEAK_KW: the effective limit is exactly _MAX_PEAK_KW.
_PEAK_GRACE_MIN = 2.0
_CONTROL_INTERVAL_S = 10.0
_LAG_CYCLES = 1
_STEPS = 14  # at least 12 oscillating steps (the issue's bar).


def _entry_data():
    return entry_data_base(**{CONF_SOLAR_AVAILABLE: False, CONF_CAPTAR_AVAILABLE: True})


def _entry_options():
    return entry_options_base(
        **{
            CONF_MAX_CURRENT: _MAX_CURRENT_A,
            CONF_DEFAULT_TARGET_CURRENT: _HIGH_TARGET_A,
            CONF_GRID_CEILING_A: _GRID_CEILING_A,
            CONF_GRID_SAFETY_OFFSET_A: _GRID_SAFETY_OFFSET_A,
            CONF_MAX_PEAK_KW: _MAX_PEAK_KW,
            CONF_PEAK_FLOOR_KW: _PEAK_FLOOR_KW,
            CONF_SAFETY_MARGIN_W: _SAFETY_MARGIN_W,
            CONF_PEAK_GRACE_MIN: _PEAK_GRACE_MIN,
            CONF_CONTROL_INTERVAL_S: _CONTROL_INTERVAL_S,
        }
    )


async def test_should_keep_true_import_within_the_peak_limit_when_the_command_oscillates_without_a_c4_backstop(  # noqa: E501
    hass, freezer
):
    # Arrange
    freezer.move_to("2026-01-15 12:00:00")
    seed_charger_states(hass, status="Charging", net_w=0.0, charger_w=0.0)
    coordinator = await setup_coordinator(
        hass, entry_data=_entry_data(), entry_options=_entry_options(), mode=MODE_POWER
    )
    options = _entry_options()
    voltage = options[CONF_NOMINAL_VOLTAGE]
    plant = Plant(household_w=_HOUSEHOLD_W, voltage=voltage, lag_cycles=_LAG_CYCLES)
    runner = ScenarioRunner(hass, coordinator, plant, freezer=freezer, grid_voltage=voltage)
    judge = judge_c4_then_r3(options)
    r3_headroom_a = math.floor((effective_peak_limit_w(options) - _HOUSEHOLD_W) / voltage)
    # Arrange (precondition guard): R3 binds on the high target.
    assert r3_headroom_a < _HIGH_TARGET_A

    # Act
    # One step at a time, the target flipped through the real number entity before each.
    for step in range(_STEPS):
        target_a = _HIGH_TARGET_A if step % 2 == 0 else _LOW_TARGET_A
        await hass.services.async_call(
            "number",
            "set_value",
            {ATTR_ENTITY_ID: _TARGET_ENTITY_ID, "value": target_a},
            blocking=True,
        )
        trace = await runner.run(1, judge=judge)
        assert trace[-1].active_mode == MODE_POWER, (
            f"step {step}: the mode select reverted mid-timeline\n{format_trace(trace)}"
        )

    # Assert
    # The whole invariant set judged every step inside `run` (a breach raises
    # `InvariantViolation`); the world must also be the one it claims to be.
    assert_charged_without_fault(trace)
    commanded = [t.commanded_current_a for t in trace]
    assert all(a != b for a, b in zip(commanded, commanded[1:], strict=False)), (
        f"the command did not change on every step: {commanded}\n{format_trace(trace)}"
    )
