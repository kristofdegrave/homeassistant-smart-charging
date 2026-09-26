"""End-to-end HA-harness regression for UC01 (Solar) / UC02 (SolarOnly) -- Task 6.2.

Drives the full stack (`hass.config_entries` setup + `coordinator.async_refresh()`), not
`modes.solar.step`/`modes.solar_only.step` directly -- Phase 1's pure-logic suites
(`tests/modes/test_solar.py`, `tests/modes/test_solar_only.py`) already cover the state
machines in isolation; this file proves the coordinator wiring (Task 5.1/6.1) dispatches to
them correctly through a real config entry.
"""

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_charging.const import (
    CONF_EV_SOC_ENTITY,
    CONF_SMOOTHING_WINDOW,
    CONF_SOLAR_AVAILABLE,
    CONF_SOLAR_COOLDOWN_MIN,
    CONF_SOLAR_HOLD_MIN,
    CONF_SOLAR_ONLY_MIDPOINT,
    CONF_SOLAR_ONLY_STRATEGY,
    DOMAIN,
    MODE_SOLAR,
    MODE_SOLAR_ONLY,
    ROUND_NEAREST,
    ROUND_UP,
    STATUS_OK,
)
from custom_components.smart_charging.coordinator_cycle import ActiveCooldown
from custom_components.smart_charging.modes._phase import Phase
from tests.helpers import (
    capture_charger_current_writes,
    entry_data_base,
    entry_options_base,
    replace_coordinator_config,
    seed_ample_peak_headroom,
    seed_charger_states,
    seed_owned_entity,
)


def _entry_data():
    """DATA bucket -- entity-role mappings + translation only (ADR-0005), plus this suite's
    own Solar/SolarOnly-specific overrides on top of the shared base shape."""
    return entry_data_base(
        **{
            CONF_SOLAR_AVAILABLE: True,
            CONF_EV_SOC_ENTITY: "sensor.ev_soc",
        }
    )


def _entry_options(**overrides):
    """OPTIONS bucket -- thresholds/defaults + interval (ADR-0005).

    Solar/SolarOnly thresholds are left at their real defaults (150 W / 1300 W) --
    surplus values in each test are chosen to straddle them -- so this suite exercises
    the same numbers a real install would see, not test-only shortcuts.
    """
    return entry_options_base(**overrides)


_capture_charger_current_writes = capture_charger_current_writes


def _seed_states(hass, *, status: str, net_w: float = 0.0, charger_w: float = 0.0) -> None:
    # below the default 80% SOC limit throughout (ev_soc left at seed_charger_states' default)
    seed_charger_states(hass, status=status, net_w=net_w, charger_w=charger_w)


_seed_ample_peak_headroom = seed_ample_peak_headroom


async def _setup(hass, **option_overrides):
    calls = _capture_charger_current_writes(hass)
    _seed_states(hass, status="Charging")
    entry = MockConfigEntry(
        domain=DOMAIN, data=_entry_data(), options=_entry_options(**option_overrides)
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data.coordinator
    _seed_ample_peak_headroom(coordinator)
    return coordinator, calls


async def _cycle(
    hass, coordinator, *, charger_w: float, net_w: float = 0.0, status: str = "Charging"
):
    """Seed one cycle's readings and drive it through the real coordinator refresh."""
    _seed_states(hass, status=status, net_w=net_w, charger_w=charger_w)
    await coordinator.async_refresh()
    await hass.async_block_till_done()


async def _cycle_from_feedback(hass, coordinator, calls, *, solar_w: float, voltage: float = 230.0):
    """Model one real feedback cycle: the charger draws exactly what was last commanded
    (`charger_w`), and the net-import meter (`net_w`) reflects that same draw against a
    fixed solar production (`net_w = charger_w - solar_w`) -- so `surplus_w = charger_w -
    net_w` reduces back to the constant `solar_w`, as it does on real hardware. Exercises
    the closed loop `tests/modes/test_solar.py` defers to this suite (commanded current ->
    charger_w -> net_w -> next surplus_w), proving the mode holds its set-point steady
    rather than oscillating once its own draw feeds back into the readings it reacts to."""
    last_current = calls[-1]["value"]
    charger_w = last_current * voltage
    net_w = charger_w - solar_w
    await _cycle(hass, coordinator, charger_w=charger_w, net_w=net_w)


async def _cycle_from_feedback_with_lag(
    hass, coordinator, calls, prior_charger_w, *, solar_w: float, voltage: float = 230.0
) -> float:
    """Issue #1329/ADR-0039's field condition: same real feedback loop as
    `_cycle_from_feedback`, except the `charger_power` role's own reading reports the
    PREVIOUS cycle's actual draw rather than this cycle's (a slow poll can still show a
    stale value for one cycle after a step) -- `net_w` still reflects this cycle's real
    draw immediately, since the net meter is fast. `prior_charger_w` is the caller's own
    running state (what this helper returned last time, or 0.0 before the first call);
    returns this cycle's actual `charger_w` for the caller to pass back in next time."""
    last_current = calls[-1]["value"]
    actual_charger_w = last_current * voltage
    net_w = actual_charger_w - solar_w
    await _cycle(hass, coordinator, charger_w=prior_charger_w, net_w=net_w)
    return actual_charger_w


async def test_uc01_closed_loop_holds_steady_once_charging_started(hass):
    """UC01 postcondition: net grid import stays bounded once surplus sustains charging --
    the mode must not oscillate once its own commanded current starts showing up in the
    next cycle's `charger_w`/`net_w` readings (see `_cycle_from_feedback`)."""
    # smoothing_window=1 isolates this narrower regression from R10's own multi-cycle
    # settling, which the window-size closed-loop suite below covers instead.
    coordinator, calls = await _setup(hass, **{CONF_SMOOTHING_WINDOW: 1})
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_SOLAR)

    # solar_w = 2645 W = 11.5 A ideal -> round up (fixed, R1) -> 12 A, same as the main
    # success test, so a real charger drawing 12 A (2760 W) against 2645 W of solar
    # production leaves a 115 W net import -- comfortably under one amp-step (230 W).
    await _cycle_from_feedback(hass, coordinator, calls, solar_w=2645.0)
    assert calls[-1]["value"] == 12.0

    # Two more cycles with the charger now drawing its own commanded current: the
    # set-point must hold at 12 A rather than hunting, since the formula cancels the
    # charger's own contribution back out of the surplus it computes.
    await _cycle_from_feedback(hass, coordinator, calls, solar_w=2645.0)
    assert calls[-1]["value"] == 12.0
    await _cycle_from_feedback(hass, coordinator, calls, solar_w=2645.0)
    assert calls[-1]["value"] == 12.0


# R10/issue #1329: the set-point settles under steady inputs at every smoothing window, not
# only window=1 (the narrower regression above). Each scenario pre-settles at a steady
# 2645 W of solar (11.5 A ideal -> round up -> 12 A), then steps solar to 3400 W (14.78 A
# ideal -> round up -> 15 A) -- a *sustained* input change -- and asserts the set-point both
# reaches 15 A within the (N + 3)th control cycle after the step and holds there, per R10's
# own criterion. The pre-settle phase is deliberately long (18 cycles): the very first
# connection is itself an input change (0 A -> 12 A), and with a lagging charger-power
# reading it takes a few extra cycles to clear -- these scenarios test the STEP, not the
# initial connection, so the step's own "last input change" must not still be entangled
# with start-up.


async def test_should_settle_within_n_plus_3_cycles_when_solar_steps_with_the_default_window(
    hass,
):
    # Arrange -- pre-settle at a steady 2645 W; a precondition, not what's under test.
    coordinator, calls = await _setup(hass)  # CONF_SMOOTHING_WINDOW defaults to 4 (R10)
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_SOLAR)
    for _ in range(18):
        await _cycle_from_feedback(hass, coordinator, calls, solar_w=2645.0)
    assert calls[-1]["value"] == 12.0  # precondition: pre-settled before the step under test

    # Act -- step solar to 3400 W and run (N + 3) = 7 cycles, N = 4.
    for _ in range(7):
        await _cycle_from_feedback(hass, coordinator, calls, solar_w=3400.0)

    # Assert -- settled at 15 A, and holds rather than resuming the hunt (the original defect).
    assert calls[-1]["value"] == 15.0
    for _ in range(3):
        await _cycle_from_feedback(hass, coordinator, calls, solar_w=3400.0)
        assert calls[-1]["value"] == 15.0


async def test_should_settle_within_n_plus_3_cycles_when_solar_steps_with_a_lagging_charger_reading_at_the_default_window(  # noqa: E501
    hass,
):
    # Arrange -- pre-settle at a steady 2645 W; a precondition, not what's under test.
    coordinator, calls = await _setup(hass)  # CONF_SMOOTHING_WINDOW defaults to 4 (R10)
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_SOLAR)
    prior_charger_w = 0.0
    for _ in range(18):
        prior_charger_w = await _cycle_from_feedback_with_lag(
            hass, coordinator, calls, prior_charger_w, solar_w=2645.0
        )
    assert calls[-1]["value"] == 12.0  # precondition: pre-settled before the step under test

    # Act -- step solar to 3400 W and run (N + 3) = 7 cycles, N = 4.
    for _ in range(7):
        prior_charger_w = await _cycle_from_feedback_with_lag(
            hass, coordinator, calls, prior_charger_w, solar_w=3400.0
        )

    # Assert -- settled at 15 A, identically to the no-lag scenario, and holds.
    assert calls[-1]["value"] == 15.0
    for _ in range(3):
        prior_charger_w = await _cycle_from_feedback_with_lag(
            hass, coordinator, calls, prior_charger_w, solar_w=3400.0
        )
        assert calls[-1]["value"] == 15.0


async def test_should_settle_within_n_plus_3_cycles_when_solar_steps_with_a_larger_window(hass):
    # Arrange -- pre-settle at a steady 2645 W; a precondition, not what's under test.
    coordinator, calls = await _setup(hass, **{CONF_SMOOTHING_WINDOW: 6})
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_SOLAR)
    for _ in range(18):
        await _cycle_from_feedback(hass, coordinator, calls, solar_w=2645.0)
    assert calls[-1]["value"] == 12.0  # precondition: pre-settled before the step under test

    # Act -- step solar to 3400 W and run (N + 3) = 9 cycles, N = 6.
    for _ in range(9):
        await _cycle_from_feedback(hass, coordinator, calls, solar_w=3400.0)

    # Assert -- settled at 15 A, and holds rather than resuming the hunt (the original defect).
    assert calls[-1]["value"] == 15.0
    for _ in range(3):
        await _cycle_from_feedback(hass, coordinator, calls, solar_w=3400.0)
        assert calls[-1]["value"] == 15.0


async def test_should_settle_within_n_plus_3_cycles_when_solar_steps_with_a_lagging_charger_reading_at_a_larger_window(  # noqa: E501
    hass,
):
    # Arrange -- pre-settle at a steady 2645 W; a precondition, not what's under test.
    coordinator, calls = await _setup(hass, **{CONF_SMOOTHING_WINDOW: 6})
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_SOLAR)
    prior_charger_w = 0.0
    for _ in range(18):
        prior_charger_w = await _cycle_from_feedback_with_lag(
            hass, coordinator, calls, prior_charger_w, solar_w=2645.0
        )
    assert calls[-1]["value"] == 12.0  # precondition: pre-settled before the step under test

    # Act -- step solar to 3400 W and run (N + 3) = 9 cycles, N = 6.
    for _ in range(9):
        prior_charger_w = await _cycle_from_feedback_with_lag(
            hass, coordinator, calls, prior_charger_w, solar_w=3400.0
        )

    # Assert -- settled at 15 A, identically to the no-lag scenario, and holds.
    assert calls[-1]["value"] == 15.0
    for _ in range(3):
        prior_charger_w = await _cycle_from_feedback_with_lag(
            hass, coordinator, calls, prior_charger_w, solar_w=3400.0
        )
        assert calls[-1]["value"] == 15.0


async def test_uc01_main_success_starts_and_recomputes_each_cycle(hass):
    """UC01 steps 1-3: starts within one cycle at >= the 150 W start threshold, rounding up,
    and recomputes the set-point every following cycle as surplus changes."""
    # Isolates mode-dispatch behaviour from R10's cross-cycle smoothing (the
    # closed-loop suite above tests that separately).
    coordinator, calls = await _setup(hass, **{CONF_SMOOTHING_WINDOW: 1})
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_SOLAR)

    # surplus = 2645 W = 11.5 A ideal -> round up (fixed, R1) -> 12 A.
    await _cycle(hass, coordinator, charger_w=2645.0)
    assert calls[-1]["value"] == 12.0
    assert hass.states.get("sensor.smart_charging_active_mode").state == MODE_SOLAR
    assert hass.states.get("sensor.smart_charging_status").state == STATUS_OK

    # surplus drops to 1840 W = 8.0 A ideal exactly -> round up -> 8 A: the set-point
    # re-tracks the (lower) available surplus rather than sticking at 12 A.
    await _cycle(hass, coordinator, charger_w=1840.0)
    assert calls[-1]["value"] == 8.0


async def test_uc01_2a_cooldown_blocks_start_until_it_elapses(hass):
    """UC01 alternate 2a: a running solar-mode cooldown blocks a start even once surplus
    reaches the threshold again; the System starts on the first qualifying cycle after the
    cooldown has fully elapsed."""
    # CONF_SMOOTHING_WINDOW: 1 isolates mode-dispatch behaviour from R10's cross-cycle
    # smoothing (the closed-loop suite above tests that separately).
    coordinator, calls = await _setup(
        hass,
        **{CONF_SOLAR_HOLD_MIN: 0.0, CONF_SOLAR_COOLDOWN_MIN: 2.0, CONF_SMOOTHING_WINDOW: 1},
    )
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_SOLAR)

    # Charging -> surplus drops below threshold -> Hold (min current).
    await _cycle(hass, coordinator, charger_w=2760.0)
    assert calls[-1]["value"] == 12.0
    await _cycle(hass, coordinator, charger_w=0.0)
    assert calls[-1]["value"] == 6.0

    # Hold period is 0 min -> elapses on the very next cycle -> Cooldown (0 A).
    await _cycle(hass, coordinator, charger_w=0.0)
    assert calls[-1]["value"] == 0.0
    assert coordinator._mode_state[MODE_SOLAR].phase == Phase.COOLDOWN

    # Surplus is back above the start threshold, but the 2-minute cooldown has not had time
    # to elapse in real wall-clock terms -- the System must stay stopped (2a).
    await _cycle(hass, coordinator, charger_w=2760.0)
    assert calls[-1]["value"] == 0.0
    assert coordinator._mode_state[MODE_SOLAR].phase == Phase.COOLDOWN

    # Simulate the cooldown having fully elapsed (avoiding a real 2-minute wall-clock wait)
    # and confirm the System starts on the next qualifying cycle. Since issue #974,
    # `replace_coordinator_config` alone no longer suffices: R11's rapid-cycling cooldown is
    # now also tracked coordinator-scoped (`_active_cooldown`), with its duration fixed at
    # the moment charging stopped precisely so a later config change can't shorten it
    # (requirements.md R11's "not shortened by a change in conditions"). Simulate elapse via
    # `ActiveCooldown.elapsed()` itself -- zero its duration rather than discarding the object
    # (discarding it would exercise disconnect semantics, not elapse semantics, and would
    # never catch a broken `elapsed()` comparison).
    replace_coordinator_config(coordinator, solar_cooldown_min=0.0)
    coordinator._active_cooldown = ActiveCooldown(coordinator._active_cooldown.stop_at, 0.0)
    await _cycle(hass, coordinator, charger_w=2760.0)
    assert calls[-1]["value"] == 12.0
    assert coordinator._mode_state[MODE_SOLAR].phase == Phase.CHARGING


async def test_uc01_2b_restart_debounce_gates_a_later_idle_crossing(hass):
    """UC01 alternate 2b: once the has-charged flag is set, a start-threshold crossing while
    dwelling in Idle must hold for the restart debounce period before charging actually
    starts. Driven through the real coordinator (not modes.solar.step directly), so this
    exercises the coordinator's own has-charged flag wiring (issue #757) too, not just the
    pure state machine `tests/modes/test_solar.py` already covers."""
    # CONF_SMOOTHING_WINDOW: 1 isolates mode-dispatch behaviour from R10's cross-cycle
    # smoothing (the closed-loop suite above tests that separately).
    coordinator, calls = await _setup(
        hass,
        **{CONF_SOLAR_HOLD_MIN: 0.0, CONF_SOLAR_COOLDOWN_MIN: 0.0, CONF_SMOOTHING_WINDOW: 1},
    )
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_SOLAR)

    # First-ever start: immediate, no debounce -- and sets the has-charged flag.
    await _cycle(hass, coordinator, charger_w=2760.0)
    assert calls[-1]["value"] == 12.0
    assert coordinator._has_charged is True

    # Surplus drops -> Hold (elapses next cycle, hold_min=0) -> Cooldown (elapses next
    # cycle, cooldown_min=0) -> Idle, since surplus is still below threshold throughout.
    await _cycle(hass, coordinator, charger_w=0.0)
    assert coordinator._mode_state[MODE_SOLAR].phase == Phase.HOLD
    await _cycle(hass, coordinator, charger_w=0.0)
    assert coordinator._mode_state[MODE_SOLAR].phase == Phase.COOLDOWN
    await _cycle(hass, coordinator, charger_w=0.0)
    assert coordinator._mode_state[MODE_SOLAR].phase == Phase.IDLE

    # Surplus recovers while dwelling in Idle -- the flag is set, so this crossing
    # debounces instead of resuming immediately.
    await _cycle(hass, coordinator, charger_w=2760.0)
    assert calls[-1]["value"] == 0.0
    assert coordinator._mode_state[MODE_SOLAR].phase == Phase.DEBOUNCING

    # Simulate the debounce period having fully elapsed (avoiding a real wall-clock wait).
    replace_coordinator_config(coordinator, solar_restart_debounce_min=0.0)
    await _cycle(hass, coordinator, charger_w=2760.0)
    assert calls[-1]["value"] == 12.0
    assert coordinator._mode_state[MODE_SOLAR].phase == Phase.CHARGING


async def test_uc01_3a_grid_fallback_holds_at_minimum_and_draws_from_grid(hass):
    """UC01 alternate 3a: surplus at/above the start threshold but below the minimum
    charging current (expressed as power) holds at the minimum current, drawing the
    shortfall from the grid -- while charging continues (this is a set-point condition
    within Charging, not a transition to Hold)."""
    # Isolates mode-dispatch behaviour from R10's cross-cycle smoothing (the
    # closed-loop suite above tests that separately).
    coordinator, calls = await _setup(hass, **{CONF_SMOOTHING_WINDOW: 1})
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_SOLAR)

    await _cycle(hass, coordinator, charger_w=2760.0)
    assert calls[-1]["value"] == 12.0

    # surplus = 700 W (between the 150 W threshold and the min-current's 1380 W) ->
    # ideal 3.04 A, floored at the 6 A minimum -- grid fallback.
    await _cycle(hass, coordinator, charger_w=700.0)
    assert calls[-1]["value"] == 6.0
    assert coordinator._mode_state[MODE_SOLAR].phase == Phase.CHARGING


async def test_uc01_3b_post_surplus_hold_resumes_or_stops_after_the_hold_period(hass):
    """UC01 alternate 3b: surplus falling below the start threshold holds at the minimum
    current for the hold period; if surplus returns in time the System resumes normal
    charging (hold cancelled), and if the hold period elapses while surplus is still low
    the System stops (0 A) and starts the solar-mode cooldown."""
    # CONF_SMOOTHING_WINDOW: 1 isolates mode-dispatch behaviour from R10's cross-cycle
    # smoothing (the closed-loop suite above tests that separately).
    coordinator, calls = await _setup(
        hass, **{CONF_SOLAR_COOLDOWN_MIN: 5.0, CONF_SMOOTHING_WINDOW: 1}
    )
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_SOLAR)

    await _cycle(hass, coordinator, charger_w=2760.0)
    assert calls[-1]["value"] == 12.0

    # Surplus falls below the 150 W threshold -> Hold at the minimum current.
    await _cycle(hass, coordinator, charger_w=0.0)
    assert calls[-1]["value"] == 6.0
    assert coordinator._mode_state[MODE_SOLAR].phase == Phase.HOLD

    # Surplus returns within the (default 5-minute) hold period -> resumes normal charging.
    await _cycle(hass, coordinator, charger_w=2645.0)
    assert calls[-1]["value"] == 12.0
    assert coordinator._mode_state[MODE_SOLAR].phase == Phase.CHARGING

    # Surplus drops again -> Hold, then simulate the hold period having fully elapsed
    # (avoiding a real 5-minute wall-clock wait) while surplus is still low.
    await _cycle(hass, coordinator, charger_w=0.0)
    assert coordinator._mode_state[MODE_SOLAR].phase == Phase.HOLD
    replace_coordinator_config(coordinator, solar_hold_min=0.0)
    await _cycle(hass, coordinator, charger_w=0.0)
    assert calls[-1]["value"] == 0.0
    assert coordinator._mode_state[MODE_SOLAR].phase == Phase.COOLDOWN


async def test_uc02_main_success_starts_and_recomputes_with_round_down_default(hass):
    """UC02 steps 1-3: starts within one cycle at >= the 1300 W start threshold, converting
    surplus into a whole-ampere set-point with the default round-down strategy (never
    importing), recomputing every following cycle."""
    # Isolates mode-dispatch behaviour from R10's cross-cycle smoothing (the
    # closed-loop suite above tests that separately).
    coordinator, calls = await _setup(hass, **{CONF_SMOOTHING_WINDOW: 1})
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_SOLAR_ONLY)

    # surplus = 1955 W = 8.5 A ideal -> round down (default, R2) -> 8 A.
    await _cycle(hass, coordinator, charger_w=1955.0)
    assert calls[-1]["value"] == 8.0
    assert hass.states.get("sensor.smart_charging_active_mode").state == MODE_SOLAR_ONLY

    # surplus rises to 2760 W = 12.0 A ideal exactly -> round down -> 12 A: recomputed,
    # not stuck at the previous cycle's 8 A.
    await _cycle(hass, coordinator, charger_w=2760.0)
    assert calls[-1]["value"] == 12.0


async def test_uc02_3a_surplus_below_threshold_holds_then_stops_no_ongoing_fallback(hass):
    """UC02 alternate 3a (post-#755): surplus falling below the start threshold no longer
    stops charging immediately -- it holds at the minimum current first (the one bounded
    exception to SolarOnly's zero-grid-import guarantee); if surplus returns in time the
    System resumes normal charging (hold cancelled), and if the hold period elapses while
    surplus is still low the System stops (0 A) and starts the cooldown. Unlike the
    sibling UC01, there is still no *ongoing* grid fallback while `Charging` -- the hold
    below is the only, time-bounded circumstance in which SolarOnly draws from the grid.

    (UC02's alternate 2a -- cooldown blocks a restart -- has no dedicated end-to-end test
    here: it's the same idle/cooldown-gate code path already proven end-to-end by UC01's
    2a test above, plus `tests/modes/test_solar_only.py`'s own cooldown coverage.)"""
    # CONF_SMOOTHING_WINDOW: 1 isolates mode-dispatch behaviour from R10's cross-cycle
    # smoothing (the closed-loop suite above tests that separately).
    coordinator, calls = await _setup(
        hass, **{CONF_SOLAR_COOLDOWN_MIN: 5.0, CONF_SMOOTHING_WINDOW: 1}
    )
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_SOLAR_ONLY)

    await _cycle(hass, coordinator, charger_w=1955.0)
    assert calls[-1]["value"] == 8.0

    # surplus = 500 W, below the 1300 W threshold -- and also below the min-current's
    # 1380 W. Enters the hold at the minimum current, not an immediate stop.
    await _cycle(hass, coordinator, charger_w=500.0)
    assert calls[-1]["value"] == 6.0
    assert coordinator._mode_state[MODE_SOLAR_ONLY].phase == Phase.HOLD

    # Surplus returns within the (default 1-minute) hold period -> resumes normal
    # charging, hold cancelled.
    await _cycle(hass, coordinator, charger_w=1955.0)
    assert calls[-1]["value"] == 8.0
    assert coordinator._mode_state[MODE_SOLAR_ONLY].phase == Phase.CHARGING

    # Surplus drops again -> Hold, then simulate the hold period having fully elapsed
    # (avoiding a real 1-minute wall-clock wait) while surplus is still low.
    await _cycle(hass, coordinator, charger_w=500.0)
    assert coordinator._mode_state[MODE_SOLAR_ONLY].phase == Phase.HOLD
    replace_coordinator_config(coordinator, solar_only_hold_min=0.0)
    await _cycle(hass, coordinator, charger_w=500.0)
    assert calls[-1]["value"] == 0.0
    assert coordinator._mode_state[MODE_SOLAR_ONLY].phase == Phase.COOLDOWN


async def test_uc02_3b_round_up_strategy_accepts_bounded_grid_import(hass):
    """UC02 alternate 3b: with the amp-step rounding strategy configured to round up, the
    System rounds up to the next whole ampere instead of the default round-down, accepting
    a bounded grid top-up to use all available surplus."""
    # CONF_SMOOTHING_WINDOW: 1 isolates mode-dispatch behaviour from R10's cross-cycle
    # smoothing (the closed-loop suite above tests that separately).
    coordinator, calls = await _setup(
        hass, **{CONF_SOLAR_ONLY_STRATEGY: ROUND_UP, CONF_SMOOTHING_WINDOW: 1}
    )
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_SOLAR_ONLY)

    # surplus = 1955 W = 8.5 A ideal -> round up -> 9 A (vs. 8 A under the default strategy).
    await _cycle(hass, coordinator, charger_w=1955.0)
    assert calls[-1]["value"] == 9.0


async def test_uc02_3c_round_nearest_strategy_pendel_behavior(hass):
    """UC02 alternate 3c: with the amp-step rounding strategy configured to round to
    nearest, the set-point rounds to whichever whole ampere is closer to the ideal value
    using the configured midpoint rounding boundary -- crossing it flips the outcome
    between the two nearest amp steps, which is how surplus hovering near that boundary
    across cycles produces the "pendel" edge case (not exercised cycle-to-cycle here)."""
    # CONF_SMOOTHING_WINDOW: 1 isolates mode-dispatch behaviour from R10's cross-cycle
    # smoothing (the closed-loop suite above tests that separately).
    coordinator, calls = await _setup(
        hass,
        **{
            CONF_SOLAR_ONLY_STRATEGY: ROUND_NEAREST,
            CONF_SOLAR_ONLY_MIDPOINT: 0.5,
            CONF_SMOOTHING_WINDOW: 1,
        },
    )
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_SOLAR_ONLY)

    # surplus = 1932 W = 8.4 A ideal -- below the 50% midpoint -> rounds down to 8 A.
    await _cycle(hass, coordinator, charger_w=1932.0)
    assert calls[-1]["value"] == 8.0

    # surplus = 1955 W = 8.5 A ideal -- at the 50% midpoint -> rounds up to 9 A: the
    # set-point toggles between the two nearest amp steps as surplus hovers around it.
    await _cycle(hass, coordinator, charger_w=1955.0)
    assert calls[-1]["value"] == 9.0
