"""End-to-end HA-harness regression for UC01 (Solar) / UC02 (SolarOnly) -- Task 6.2.

Drives the full stack (`hass.config_entries` setup + `coordinator.async_refresh()`), not
`modes.solar.step`/`modes.solar_only.step` directly -- Phase 1's pure-logic suites
(`tests/modes/test_solar.py`, `tests/modes/test_solar_only.py`) already cover the state
machines in isolation; this file proves the coordinator wiring (Task 5.1/6.1) dispatches to
them correctly through a real config entry.
"""

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_charging.const import (
    CONF_CHARGER_CURRENT_ENTITY,
    CONF_CHARGER_POWER_ENTITY,
    CONF_CHARGER_STATUS_ENTITY,
    CONF_DEFAULT_SOC_LIMIT,
    CONF_DEFAULT_TARGET_CURRENT,
    CONF_EV_SOC_ENTITY,
    CONF_GRID_CEILING_A,
    CONF_GRID_SAFETY_OFFSET_A,
    CONF_GRID_VOLTAGE_ENTITY,
    CONF_MAX_CURRENT,
    CONF_MIN_CURRENT,
    CONF_NET_POWER_ENTITY,
    CONF_NOMINAL_VOLTAGE,
    CONF_SOLAR_COOLDOWN_MIN,
    CONF_SOLAR_HOLD_MIN,
    CONF_SOLAR_INSTALLED,
    CONF_SOLAR_ONLY_MIDPOINT,
    CONF_SOLAR_ONLY_STRATEGY,
    CONF_STATUS_TRANSLATION,
    DOMAIN,
    MODE_SOLAR,
    MODE_SOLAR_ONLY,
)
from custom_components.smart_charging.modes._amp_step import ROUND_NEAREST, ROUND_UP
from custom_components.smart_charging.modes._phase import Phase


def _entry_data():
    """DATA bucket -- entity-role mappings + translation only (ADR-0005)."""
    return {
        CONF_CHARGER_CURRENT_ENTITY: "number.charger_current",
        CONF_CHARGER_STATUS_ENTITY: "sensor.evse",
        CONF_STATUS_TRANSLATION: {"Charging": "charging", "Connected": "connected"},
        CONF_NET_POWER_ENTITY: "sensor.net_power",
        CONF_CHARGER_POWER_ENTITY: "sensor.charger_power",
        CONF_GRID_VOLTAGE_ENTITY: "sensor.grid_voltage",
        CONF_SOLAR_INSTALLED: True,
        CONF_EV_SOC_ENTITY: "sensor.ev_soc",
    }


def _entry_options(**overrides):
    """OPTIONS bucket -- thresholds/defaults + interval (ADR-0005).

    Solar/SolarOnly thresholds are left at their real defaults (150 W / 1300 W) --
    surplus values in each test are chosen to straddle them -- so this suite exercises
    the same numbers a real install would see, not test-only shortcuts.
    """
    options = {
        CONF_NOMINAL_VOLTAGE: 230.0,
        CONF_MIN_CURRENT: 6.0,
        CONF_MAX_CURRENT: 16.0,
        CONF_GRID_CEILING_A: 25.0,
        CONF_GRID_SAFETY_OFFSET_A: 2.0,
        CONF_DEFAULT_TARGET_CURRENT: 10.0,
        CONF_DEFAULT_SOC_LIMIT: 80.0,
    }
    options.update(overrides)
    return options


def _capture_charger_current_writes(hass):
    """Capture number.set_value calls targeting the charger-current entity (see test_init.py)."""
    calls = []

    def _record(event):
        if event.data["domain"] == "number" and event.data["service"] == "set_value":
            calls.append(event.data["service_data"])

    hass.bus.async_listen("call_service", _record)
    return calls


def _seed_states(hass, *, status: str, net_w: float = 0.0, charger_w: float = 0.0) -> None:
    hass.states.async_set("number.charger_current", "0.0")
    hass.states.async_set("sensor.evse", status)
    hass.states.async_set("sensor.net_power", str(net_w))
    hass.states.async_set("sensor.charger_power", str(charger_w))
    hass.states.async_set("sensor.grid_voltage", "230.0")
    hass.states.async_set("sensor.ev_soc", "50.0")  # below the default 80% SOC limit throughout


async def _setup(hass, **option_overrides):
    calls = _capture_charger_current_writes(hass)
    _seed_states(hass, status="Charging")
    entry = MockConfigEntry(
        domain=DOMAIN, data=_entry_data(), options=_entry_options(**option_overrides)
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    return coordinator, calls


async def _cycle(
    hass, coordinator, *, charger_w: float, net_w: float = 0.0, status: str = "Charging"
):
    """Seed one cycle's readings and drive it through the real coordinator refresh."""
    _seed_states(hass, status=status, net_w=net_w, charger_w=charger_w)
    await coordinator.async_refresh()
    await hass.async_block_till_done()


async def test_uc01_main_success_starts_and_recomputes_each_cycle(hass):
    """UC01 steps 1-3: starts within one cycle at >= the 150 W start threshold, rounding up,
    and recomputes the set-point every following cycle as surplus changes."""
    coordinator, calls = await _setup(hass)
    coordinator.active_mode = MODE_SOLAR

    # surplus = 2645 W = 11.5 A ideal -> round up (fixed, R1) -> 12 A.
    await _cycle(hass, coordinator, charger_w=2645.0)
    assert calls[-1]["value"] == 12.0
    assert hass.states.get("sensor.smart_charging_active_mode").state == MODE_SOLAR
    assert hass.states.get("sensor.smart_charging_status").state == "OK"

    # surplus drops to 1840 W = 8.0 A ideal exactly -> round up -> 8 A: the set-point
    # re-tracks the (lower) available surplus rather than sticking at 12 A.
    await _cycle(hass, coordinator, charger_w=1840.0)
    assert calls[-1]["value"] == 8.0


async def test_uc01_2a_cooldown_blocks_start_until_it_elapses(hass):
    """UC01 alternate 2a: a running solar-mode cooldown blocks a start even once surplus
    reaches the threshold again; the System starts on the first qualifying cycle after the
    cooldown has fully elapsed."""
    coordinator, calls = await _setup(
        hass, **{CONF_SOLAR_HOLD_MIN: 0.0, CONF_SOLAR_COOLDOWN_MIN: 2.0}
    )
    coordinator.active_mode = MODE_SOLAR

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
    # and confirm the System starts on the next qualifying cycle.
    coordinator._config[CONF_SOLAR_COOLDOWN_MIN] = 0.0
    await _cycle(hass, coordinator, charger_w=2760.0)
    assert calls[-1]["value"] == 12.0
    assert coordinator._mode_state[MODE_SOLAR].phase == Phase.CHARGING


async def test_uc01_3a_grid_fallback_holds_at_minimum_and_draws_from_grid(hass):
    """UC01 alternate 3a: surplus at/above the start threshold but below the minimum
    charging current (expressed as power) holds at the minimum current, drawing the
    shortfall from the grid -- while charging continues (this is a set-point condition
    within Charging, not a transition to Hold)."""
    coordinator, calls = await _setup(hass)
    coordinator.active_mode = MODE_SOLAR

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
    coordinator, calls = await _setup(hass, **{CONF_SOLAR_COOLDOWN_MIN: 5.0})
    coordinator.active_mode = MODE_SOLAR

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
    coordinator._config[CONF_SOLAR_HOLD_MIN] = 0.0
    await _cycle(hass, coordinator, charger_w=0.0)
    assert calls[-1]["value"] == 0.0
    assert coordinator._mode_state[MODE_SOLAR].phase == Phase.COOLDOWN


async def test_uc02_main_success_starts_and_recomputes_with_round_down_default(hass):
    """UC02 steps 1-3: starts within one cycle at >= the 1300 W start threshold, converting
    surplus into a whole-ampere set-point with the default round-down strategy (never
    importing), recomputing every following cycle."""
    coordinator, calls = await _setup(hass)
    coordinator.active_mode = MODE_SOLAR_ONLY

    # surplus = 1955 W = 8.5 A ideal -> round down (default, R2) -> 8 A.
    await _cycle(hass, coordinator, charger_w=1955.0)
    assert calls[-1]["value"] == 8.0
    assert hass.states.get("sensor.smart_charging_active_mode").state == MODE_SOLAR_ONLY

    # surplus rises to 2760 W = 12.0 A ideal exactly -> round down -> 12 A: recomputed,
    # not stuck at the previous cycle's 8 A.
    await _cycle(hass, coordinator, charger_w=2760.0)
    assert calls[-1]["value"] == 12.0


async def test_uc02_3a_surplus_below_threshold_stops_immediately_no_hold_no_fallback(hass):
    """UC02 alternate 3a: surplus falling below the start threshold stops charging (0 A)
    within one cycle -- no hold, and no grid fallback to the minimum current, unlike the
    sibling UC01."""
    coordinator, calls = await _setup(hass)
    coordinator.active_mode = MODE_SOLAR_ONLY

    await _cycle(hass, coordinator, charger_w=1955.0)
    assert calls[-1]["value"] == 8.0

    # surplus = 500 W, below the 1300 W threshold -- and also below the min-current's
    # 1380 W, so a grid-fallback floor (UC01's behaviour) would have held at 6 A.
    await _cycle(hass, coordinator, charger_w=500.0)
    assert calls[-1]["value"] == 0.0
    assert coordinator._mode_state[MODE_SOLAR_ONLY].phase == Phase.COOLDOWN


async def test_uc02_3b_round_up_strategy_accepts_bounded_grid_import(hass):
    """UC02 alternate 3b: with the amp-step rounding strategy configured to round up, the
    System rounds up to the next whole ampere instead of the default round-down, accepting
    a bounded grid top-up to use all available surplus."""
    coordinator, calls = await _setup(hass, **{CONF_SOLAR_ONLY_STRATEGY: ROUND_UP})
    coordinator.active_mode = MODE_SOLAR_ONLY

    # surplus = 1955 W = 8.5 A ideal -> round up -> 9 A (vs. 8 A under the default strategy).
    await _cycle(hass, coordinator, charger_w=1955.0)
    assert calls[-1]["value"] == 9.0


async def test_uc02_3c_round_nearest_strategy_pendel_behavior(hass):
    """UC02 alternate 3c: with the amp-step rounding strategy configured to round to
    nearest, the set-point rounds to whichever whole ampere is closer to the ideal value
    using the configured midpoint, so it can toggle between two amp steps as surplus
    hovers near that midpoint (the "pendel" edge case)."""
    coordinator, calls = await _setup(
        hass, **{CONF_SOLAR_ONLY_STRATEGY: ROUND_NEAREST, CONF_SOLAR_ONLY_MIDPOINT: 0.5}
    )
    coordinator.active_mode = MODE_SOLAR_ONLY

    # surplus = 1932 W = 8.4 A ideal -- below the 50% midpoint -> rounds down to 8 A.
    await _cycle(hass, coordinator, charger_w=1932.0)
    assert calls[-1]["value"] == 8.0

    # surplus = 1955 W = 8.5 A ideal -- at the 50% midpoint -> rounds up to 9 A: the
    # set-point toggles between the two nearest amp steps as surplus hovers around it.
    await _cycle(hass, coordinator, charger_w=1955.0)
    assert calls[-1]["value"] == 9.0
