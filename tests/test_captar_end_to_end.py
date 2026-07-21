"""End-to-end HA-harness regression for UC03 (Captar) -- Task 6.2.

Drives the full stack (`hass.config_entries` setup + `coordinator.async_refresh()`), not
`modes.captar.step` directly -- Phase 1's pure-logic suite (`tests/modes/test_captar.py`)
already covers the state machine in isolation; this file proves the coordinator wiring
(Task 5.1/6.1) dispatches to it correctly through a real config entry, including the R3
peak clamp (Billing-Protection Engine, E5) and the SOC gate.
"""

from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_charging.const import (
    CONF_CAPTAR_AVAILABLE,
    CONF_CAPTAR_COOLDOWN_MIN,
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
    CONF_MAX_PEAK_KW,
    CONF_MIN_CURRENT,
    CONF_NET_POWER_ENTITY,
    CONF_NOMINAL_VOLTAGE,
    CONF_PEAK_GRACE_MIN,
    CONF_SAFETY_MARGIN_W,
    CONF_SMOOTHING_WINDOW,
    CONF_SOLAR_INSTALLED,
    CONF_STATUS_TRANSLATION,
    DOMAIN,
    MODE_CAPTAR,
)
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
        CONF_SOLAR_INSTALLED: False,
        CONF_CAPTAR_AVAILABLE: True,
        CONF_EV_SOC_ENTITY: "sensor.ev_soc",
    }


def _entry_options(**overrides):
    """OPTIONS bucket -- thresholds/defaults + interval (ADR-0005).

    R3's peak-protection numbers (`safety_margin_w`, `max_peak_kw`, `peak_grace_min`) are
    left at their real defaults unless a test needs to override one to exercise a specific
    boundary -- this suite exercises the same numbers a real install would see.
    """
    options = {
        CONF_NOMINAL_VOLTAGE: 230.0,
        CONF_MIN_CURRENT: 6.0,
        CONF_MAX_CURRENT: 16.0,
        CONF_GRID_CEILING_A: 25.0,
        CONF_GRID_SAFETY_OFFSET_A: 2.0,
        CONF_DEFAULT_TARGET_CURRENT: 10.0,
        CONF_DEFAULT_SOC_LIMIT: 80.0,
        CONF_SMOOTHING_WINDOW: 1,  # isolate raw readings from R10's rolling average
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


def _seed_states(
    hass, *, status: str, net_w: float = 0.0, charger_w: float = 0.0, ev_soc: float = 50.0
) -> None:
    hass.states.async_set("number.charger_current", "0.0")
    hass.states.async_set("sensor.evse", status)
    hass.states.async_set("sensor.net_power", str(net_w))
    hass.states.async_set("sensor.charger_power", str(charger_w))
    hass.states.async_set("sensor.grid_voltage", "230.0")
    hass.states.async_set("sensor.ev_soc", str(ev_soc))


def _seed_ample_peak_headroom(coordinator, kw=100.0):
    """Pre-seed the Peak-Demand Tracker as though a large historical peak already exists
    (Captar T5.1/#228) -- effective_peak_limit_kw = min(monthly_peak_kw, max_peak_kw)
    collapses to the configured `max_peak_kw` regardless of this cycle's raw readings, so a
    test can control the effective peak limit purely through options (see
    `tests/test_solar_end_to_end.py` for the identical pattern predating Captar's clamp)."""
    now_dt = dt_util.now()
    coordinator._peak_tracked_month = (now_dt.year, now_dt.month)
    coordinator._peak_tracked_kw = kw


def _effective_peak_limit_state(hass):
    """Look up the diagnostic EffectivePeakLimitSensor by unique_id, not entity_id -- its
    friendly-name-derived entity_id depends on the select.mode-style translation entry T6.3
    (translations/strings) adds, not this task (see tests/test_init.py's identical note)."""
    entry_id = next(iter(hass.data[DOMAIN]))
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{entry_id}_effective_peak_limit")
    return hass.states.get(entity_id)


async def _setup(hass, **option_overrides):
    calls = _capture_charger_current_writes(hass)
    _seed_states(hass, status="Connected")
    entry = MockConfigEntry(
        domain=DOMAIN, data=_entry_data(), options=_entry_options(**option_overrides)
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    _seed_ample_peak_headroom(coordinator)
    coordinator.active_mode = MODE_CAPTAR
    return coordinator, calls


async def _cycle(
    hass,
    coordinator,
    *,
    net_w: float = 0.0,
    charger_w: float = 0.0,
    status: str = "Connected",
    ev_soc: float = 50.0,
):
    """Seed one cycle's readings and drive it through the real coordinator refresh."""
    _seed_states(hass, status=status, net_w=net_w, charger_w=charger_w, ev_soc=ev_soc)
    await coordinator.async_refresh()
    await hass.async_block_till_done()


async def test_uc03_main_success_starts_at_max_current_within_headroom(hass):
    """UC03 steps 1-3: with Captar active, the car connected, SOC below the active limit,
    no cooldown running, and ample peak headroom, the System starts grid charging within
    one control cycle and requests the maximum charging current."""
    coordinator, calls = await _setup(hass, **{CONF_MAX_PEAK_KW: 4.0})

    # baseline household load (net_w - charger_w) = 0 W -> ample headroom -> the R3 clamp
    # does not reduce the max-current request (16 A).
    await _cycle(hass, coordinator, net_w=0.0, charger_w=0.0)
    assert calls[-1]["value"] == 16.0
    assert coordinator._mode_state[MODE_CAPTAR].phase == Phase.CHARGING
    assert hass.states.get("sensor.smart_charging_active_mode").state == MODE_CAPTAR
    assert hass.states.get("sensor.smart_charging_status").state == "OK"
    # C3: the effective-peak-limit sensor reflects the configured max_peak_kw this cycle
    # (min(monthly_peak_kw, max_peak_kw) with the ample seeded peak) -- ties this set-point
    # to the clamp bound that produced it, the whole point of this suite.
    assert _effective_peak_limit_state(hass).state == "4.0"


async def test_uc03_2a_cooldown_blocks_restart_until_it_elapses(hass):
    """UC03 alternate 2a: a running Captar cooldown -- entered via a sustained R3 breach
    stop -- blocks a restart even once headroom is restored, and the System starts again
    only on the first qualifying cycle after the cooldown has fully elapsed."""
    coordinator, calls = await _setup(hass, **{CONF_MAX_PEAK_KW: 4.0, CONF_PEAK_GRACE_MIN: 0.0})

    # Charging starts, then a breach at the minimum current that is immediately "sustained"
    # (0-minute grace period) forces a stop into cooldown.
    await _cycle(hass, coordinator, net_w=0.0, charger_w=0.0)
    assert calls[-1]["value"] == 16.0
    await _cycle(hass, coordinator, net_w=3600.0, charger_w=0.0)
    assert calls[-1]["value"] == 0.0
    assert coordinator._mode_state[MODE_CAPTAR].phase == Phase.COOLDOWN

    # Headroom is fully restored, but the (default 10-minute) cooldown has not had time to
    # elapse in real wall-clock terms -- the System must stay stopped (2a).
    await _cycle(hass, coordinator, net_w=0.0, charger_w=0.0)
    assert calls[-1]["value"] == 0.0
    assert coordinator._mode_state[MODE_CAPTAR].phase == Phase.COOLDOWN

    # Simulate the cooldown having fully elapsed (avoiding a real 10-minute wall-clock wait)
    # and confirm the System starts again on the next qualifying cycle.
    coordinator._config[CONF_CAPTAR_COOLDOWN_MIN] = 0.0
    await _cycle(hass, coordinator, net_w=0.0, charger_w=0.0)
    assert calls[-1]["value"] == 16.0
    assert coordinator._mode_state[MODE_CAPTAR].phase == Phase.CHARGING


async def test_uc03_peak_clamp_reduces_set_point_within_headroom(hass):
    """UC03 exception flow: the R3 peak clamp fits the max-current request (raw) to the
    available peak headroom when household load leaves less than the maximum -- but still
    at least the minimum -- charging current of headroom, reducing (not stopping) the
    set-point this cycle.

    (UC03's exception flow also names the C4 grid-supply-ceiling clamp as a second way the
    set-point can be reduced/stopped -- that clamp is mode-agnostic and already covered at
    engine level by `tests/engines/test_grid_safety.py`, so it is deferred there rather than
    duplicated here, the same call the sibling `test_solar_end_to_end.py` makes for its own
    out-of-scope alternates.)"""
    coordinator, calls = await _setup(hass, **{CONF_MAX_PEAK_KW: 4.0, CONF_SAFETY_MARGIN_W: 250.0})

    await _cycle(hass, coordinator, net_w=0.0, charger_w=0.0)
    assert calls[-1]["value"] == 16.0

    # target_w = 4000 - 250 = 3750 W; baseline_w = 2000 W (household load) -> headroom_a =
    # floor(1750 / 230) = 7 A -- between the 6 A minimum and the 16 A maximum, so the clamp
    # reduces the set-point without stopping charging.
    await _cycle(hass, coordinator, net_w=2000.0, charger_w=0.0)
    assert calls[-1]["value"] == 7.0
    assert coordinator._mode_state[MODE_CAPTAR].phase == Phase.CHARGING


async def test_uc03_sustained_r3_breach_stops_and_starts_cooldown(hass):
    """UC03 exception flow: a momentary breach at the minimum charging current holds at
    the minimum rather than stopping (R3: "a momentary breach does not stop charging"),
    but once that breach has held continuously for the configured grace period, the System
    stops (0 A) and starts the Captar cooldown (R11)."""
    coordinator, calls = await _setup(hass, **{CONF_MAX_PEAK_KW: 4.0})

    await _cycle(hass, coordinator, net_w=0.0, charger_w=0.0)
    assert calls[-1]["value"] == 16.0

    # target_w = 4000 - 250 = 3750 W; baseline_w = 3600 W -> headroom_a = floor(150 / 230) =
    # 0 A, below the 6 A minimum -- a breach, but the default grace period has not elapsed
    # yet, so the System holds at the minimum current rather than stopping.
    await _cycle(hass, coordinator, net_w=3600.0, charger_w=0.0)
    assert calls[-1]["value"] == 6.0
    assert coordinator._mode_state[MODE_CAPTAR].phase == Phase.CHARGING

    # Simulate the grace period having fully elapsed (avoiding a real wall-clock wait) --
    # the same continuing breach now forces a stop and starts the Captar cooldown.
    coordinator._config[CONF_PEAK_GRACE_MIN] = 0.0
    await _cycle(hass, coordinator, net_w=3600.0, charger_w=0.0)
    assert calls[-1]["value"] == 0.0
    assert coordinator._mode_state[MODE_CAPTAR].phase == Phase.COOLDOWN


async def test_uc03_soc_limit_reached_stops_charging(hass):
    """UC03 exception flow: state of charge reaching the active SOC limit stops charging
    (0 A) and does not resume above that limit while it continues to hold."""
    coordinator, calls = await _setup(hass, **{CONF_MAX_PEAK_KW: 4.0})

    await _cycle(hass, coordinator, net_w=0.0, charger_w=0.0, ev_soc=50.0)
    assert calls[-1]["value"] == 16.0

    # SOC reaches the (default 80%) active SOC limit -> stop, and stay stopped on the next
    # cycle too even though headroom is still ample.
    await _cycle(hass, coordinator, net_w=0.0, charger_w=0.0, ev_soc=80.0)
    assert calls[-1]["value"] == 0.0
    await _cycle(hass, coordinator, net_w=0.0, charger_w=0.0, ev_soc=80.0)
    assert calls[-1]["value"] == 0.0
