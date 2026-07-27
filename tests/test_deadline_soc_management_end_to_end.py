"""End-to-end HA-harness regression for UC05/UC06/UC07 (#328, Task 6.2).

Every test is driven through `hass.config_entries.async_setup` + a full
`coordinator.async_refresh()` cycle against mocked entity states -- never by calling the pure
engine/profile functions directly (that's Phase 1's own test suites' job; this file proves the
coordinator wiring). `departure_dow_defaults`/`departure_holiday_override`/
`departure_home_day_override`/`home_day_flag` are set directly on the live coordinator instance
fetched from `hass.data`, mirroring `tests/test_init.py`'s own live-wiring tests -- the
entity->coordinator wiring for those (switch.smart_charging_home_day,
time.smart_charging_departure_*) is tracked separately (issue #402) and not yet threaded, so
there is no entity to seed instead.
"""

from datetime import timedelta

from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_charging.const import (
    ATTR_ACTIVE_SOC_LIMIT,
    ATTR_REQUIRED_CURRENT_A,
    CONF_CAPTAR_AVAILABLE,
    CONF_CHARGER_CURRENT_ENTITY,
    CONF_CHARGER_POWER_ENTITY,
    CONF_CHARGER_STATUS_ENTITY,
    CONF_DEFAULT_SOC_LIMIT,
    CONF_DEFAULT_TARGET_CURRENT,
    CONF_EV_SOC_ENTITY,
    CONF_GRID_CEILING_A,
    CONF_GRID_SAFETY_OFFSET_A,
    CONF_MAX_CURRENT,
    CONF_MAX_PEAK_KW,
    CONF_MIN_CURRENT,
    CONF_NET_POWER_ENTITY,
    CONF_NOMINAL_VOLTAGE,
    CONF_SOLAR_FORECAST_ENTITY,
    CONF_SOLAR_INSTALLED,
    CONF_SOLAR_RESERVE_SOC,
    CONF_STATUS_TRANSLATION,
    DOMAIN,
    EVENT_ACTIVE_SOC_LIMIT_CHANGED,
    EVENT_DEADLINE_UNREACHABLE_NOTIFIED,
    MODE_CAPTAR,
    MODE_OFF,
    MODE_POWER,
    MODE_SOLAR,
    MODE_SOLAR_ONLY,
    PROFILE_AUTO,
    PROFILE_MANUAL,
    STATE_CHARGING,
)


def _entry_data(**overrides):
    """DATA bucket -- entity-role mappings + translation only (ADR-0005)."""
    data = {
        CONF_CHARGER_CURRENT_ENTITY: "number.charger_current",
        CONF_CHARGER_STATUS_ENTITY: "sensor.evse",
        CONF_STATUS_TRANSLATION: {"Charging": STATE_CHARGING},
        CONF_NET_POWER_ENTITY: "sensor.net_power",
        CONF_CHARGER_POWER_ENTITY: "sensor.charger_power",
        CONF_EV_SOC_ENTITY: "sensor.ev_soc",
    }
    data.update(overrides)
    return data


def _entry_options(**overrides):
    """OPTIONS bucket -- thresholds/defaults + interval (ADR-0005)."""
    options = {
        CONF_NOMINAL_VOLTAGE: 230.0,
        CONF_MIN_CURRENT: 6.0,
        CONF_MAX_CURRENT: 16.0,
        CONF_GRID_CEILING_A: 25.0,
        CONF_GRID_SAFETY_OFFSET_A: 2.0,
        CONF_DEFAULT_TARGET_CURRENT: 10.0,
        CONF_DEFAULT_SOC_LIMIT: 80.0,
        CONF_MAX_PEAK_KW: 100.0,  # ample headroom -- R3 not under test here
    }
    options.update(overrides)
    return options


def _seed_states(hass, *, status="Charging", net_w=0.0, charger_w=0.0, ev_soc=50.0):
    hass.states.async_set("number.charger_current", "0.0")
    hass.states.async_set("sensor.evse", status)
    hass.states.async_set("sensor.net_power", str(net_w))
    hass.states.async_set("sensor.charger_power", str(charger_w))
    hass.states.async_set("sensor.ev_soc", str(ev_soc))


def _seed_ample_peak_headroom(coordinator, kw=100.0):
    """A large historical peak (the same shape a MonthlyPeakSensor restore would seed) keeps
    R3's clamp out of the way of these tests, none of which exercise R3 itself."""
    now_dt = dt_util.now()
    coordinator._peak_tracked_month = (now_dt.year, now_dt.month)
    coordinator._peak_tracked_kw = kw


async def _setup(hass, *, data_overrides=None, option_overrides=None):
    """Sets up a config entry and returns its live coordinator, with ample peak headroom
    pre-seeded so R3 never interferes with these UC05/UC06/UC07-focused assertions."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=_entry_data(**(data_overrides or {})),
        options=_entry_options(**(option_overrides or {})),
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    _seed_ample_peak_headroom(coordinator)
    return coordinator


def _seed_today_deadline(coordinator, *, hours_from_now):
    """Seeds today's day-of-week default so R14 resolves `hours_from_now` ahead of real
    wall-clock now (the coordinator's deadline resolution reads dt_util.now())."""
    now_dt = dt_util.now()
    weekday = now_dt.weekday()
    target = now_dt + timedelta(hours=hours_from_now)
    coordinator.departure_dow_defaults[weekday] = target.time()


# --- UC05: Normal -> Urgent -> Unreachable, both profiles' lever sets ---


async def test_uc05_auto_profile_normal_urgent_unreachable_transitions(hass, freezer):
    """UC05 main success scenario + 3a + exception flow, Auto profile with CapTar available:
    Normal (no urgency) -> Urgent (escalates to Captar) -> Unreachable (still Captar, but
    notifies) as the deadline tightens cycle over cycle."""
    freezer.move_to("2026-01-15 12:00:00")
    _seed_states(hass, status="Charging", ev_soc=70.0)
    coordinator = await _setup(
        hass,
        data_overrides={CONF_CAPTAR_AVAILABLE: True, CONF_SOLAR_INSTALLED: False},
    )
    coordinator.active_profile = PROFILE_AUTO
    coordinator.active_mode = MODE_OFF

    # Normal: no deadline seeded yet -- baseline (Off, no solar/low-tariff) is never urgent.
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator._required_current.urgent is False
    assert coordinator.active_mode == MODE_OFF

    # Urgent: a 4h deadline the Off baseline can't meet, but still within the maximum
    # permitted rate (~8.15 A required vs. 16 A max), escalates Auto to Captar.
    _seed_today_deadline(coordinator, hours_from_now=4)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator._required_current.urgent is True
    assert coordinator._required_current.unreachable is False
    assert coordinator.active_mode == MODE_CAPTAR
    assert hass.states.get("sensor.smart_charging_active_mode").state == MODE_CAPTAR

    # Unreachable: a much tighter deadline exceeds even Captar's maximum-current request.
    events = []
    hass.bus.async_listen(EVENT_DEADLINE_UNREACHABLE_NOTIFIED, lambda e: events.append(e))
    _seed_today_deadline(coordinator, hours_from_now=0.01)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator._required_current.unreachable is True
    assert coordinator.active_mode == MODE_CAPTAR  # still escalated (R5/R16 postcondition)
    assert len(events) == 1
    assert events[0].data[ATTR_REQUIRED_CURRENT_A] == coordinator._required_current.required_a


async def test_uc05_auto_profile_without_captar_escalates_to_power_not_captar(hass, freezer):
    """UC05 alternate flow 3a' (R18 carve-out): CapTar capability absent -- Auto's urgency
    escalation falls back to Power instead of Captar."""
    freezer.move_to("2026-01-15 12:00:00")
    _seed_states(hass, status="Charging", ev_soc=70.0)
    coordinator = await _setup(
        hass,
        data_overrides={CONF_CAPTAR_AVAILABLE: False, CONF_SOLAR_INSTALLED: False},
    )
    coordinator.active_profile = PROFILE_AUTO
    coordinator.active_mode = MODE_OFF
    _seed_today_deadline(coordinator, hours_from_now=1)

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator._required_current.urgent is True
    assert coordinator.active_mode == MODE_POWER


async def test_uc05_manual_profile_never_changes_mode_but_still_flags_urgency(hass, freezer):
    """UC05 alternate flow 3b (NF2): Manual's active mode is never second-guessed by urgency,
    even though the required-current computation still reports it (only the peak-limit lever
    is available under Manual)."""
    freezer.move_to("2026-01-15 12:00:00")
    _seed_states(hass, status="Charging", ev_soc=70.0)
    coordinator = await _setup(hass, option_overrides={CONF_MAX_PEAK_KW: 10.0})
    _seed_ample_peak_headroom(coordinator, kw=1.0)  # below max_peak_kw -- row 2 alone would apply
    coordinator.active_profile = PROFILE_MANUAL
    coordinator.active_mode = MODE_SOLAR
    _seed_today_deadline(coordinator, hours_from_now=1)

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator._required_current.urgent is True
    assert coordinator.active_mode == MODE_SOLAR  # unchanged (NF2)
    assert coordinator.data.effective_peak_limit_kw == 10.0  # the one lever Manual does get


# --- UC06: Baseline -> SteppedUp -> Baseline, across a Solar/SolarOnly switch ---


async def test_uc06_solar_step_up_lifecycle_baseline_steppedup_baseline(hass):
    """UC06 main success scenario + exception flow: SOC nears the limit while a solar mode
    charges under `Auto` (R8/R16 precondition -- UC06's own preconditions section: "under
    Manual, no step-up ever applies") -> step-up applies (Baseline -> SteppedUp); the user
    then manually switching away from Auto/solar clears it (SteppedUp -> Baseline, R7's
    shared reset)."""
    _seed_states(hass, status="Charging", ev_soc=50.0, net_w=100.0, charger_w=500.0)
    hass.states.async_set("sun.sun", "above_horizon")  # sufficient surplus keeps Auto in Solar
    coordinator = await _setup(hass, data_overrides={CONF_SOLAR_INSTALLED: True})
    coordinator.active_profile = PROFILE_AUTO
    coordinator.active_mode = MODE_SOLAR

    # Baseline: SOC (50) is far from the limit (80) -- no step applies yet.
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.data.active_soc_limit == 80.0
    assert coordinator._step_up_state.stepped_pct is None
    assert coordinator.active_mode == MODE_SOLAR  # Auto keeps selecting Solar (row 3)

    # SteppedUp: SOC now within the default 2pp step threshold of the limit.
    hass.states.async_set("sensor.ev_soc", "78.5")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.data.active_soc_limit == 85.0  # default 80 + default step 5
    assert coordinator._step_up_state.stepped_pct == 85.0
    # Looked up by unique_id, not entity_id -- its translation entry is T6.3's own job, not
    # this task's (mirrors tests/test_init.py's own active_soc_limit sensor lookup).
    entry_id = next(iter(hass.data[DOMAIN]))
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{entry_id}_active_soc_limit")
    assert float(hass.states.get(entity_id).state) == 85.0

    # Baseline again: the user manually switches away from Auto/solar charging (UC06's own
    # exception-flow example) -- the step-up clears and the limit returns to the default.
    coordinator.active_profile = PROFILE_MANUAL
    coordinator.active_mode = MODE_POWER
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator._step_up_state.stepped_pct is None
    assert coordinator.data.active_soc_limit == 80.0


async def test_uc06_step_up_survives_a_solar_to_solaronly_switch(hass):
    """UC06 alternate flow 4a: switching between Solar and SolarOnly is a self-loop within
    SteppedUp, not a reset -- only leaving solar charging entirely (R7's shared rule) clears
    it, per coordinator.py's own comment warning against conflating the two."""
    _seed_states(hass, status="Charging", ev_soc=78.5)
    coordinator = await _setup(hass, data_overrides={CONF_SOLAR_INSTALLED: True})
    coordinator.active_profile = PROFILE_AUTO
    coordinator.active_mode = MODE_SOLAR

    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator._step_up_state.stepped_pct == 85.0

    coordinator.active_mode = MODE_SOLAR_ONLY
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator._step_up_state.stepped_pct == 85.0  # preserved, not cleared
    assert coordinator.data.active_soc_limit == 85.0


# --- UC07: Normal -> Reserved -> Normal, and the UC05 mutual-exclusivity case ---


async def test_uc07_solar_reserve_normal_reserved_normal_cycle(hass):
    """UC07 main success scenario + Postconditions: sun down + home-day flag + ample forecast
    + no deadline for tomorrow engages the reserve cap (Normal -> Reserved); sun coming back up
    lifts it (Reserved -> Normal)."""
    _seed_states(hass, status="Charging", ev_soc=50.0)
    hass.states.async_set("sun.sun", "below_horizon")
    hass.states.async_set("sensor.solar_forecast", "20.0")  # above the 12 kWh default threshold
    coordinator = await _setup(
        hass,
        data_overrides={CONF_SOLAR_FORECAST_ENTITY: "sensor.solar_forecast"},
        option_overrides={CONF_SOLAR_RESERVE_SOC: 55.0},
    )
    coordinator.active_profile = PROFILE_AUTO
    coordinator.active_mode = MODE_OFF
    coordinator.home_day_flag = True  # entity->coordinator wiring pending, issue #402

    events = []
    hass.bus.async_listen(EVENT_ACTIVE_SOC_LIMIT_CHANGED, lambda e: events.append(e))

    # Reserved: every precondition holds, no deadline anywhere for tomorrow.
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.data.active_soc_limit == 55.0  # configured reserve cap, not default (80)
    assert events[-1].data[ATTR_ACTIVE_SOC_LIMIT] == 55.0
    # Row 4 (overnight top-up) withheld by the reserve -- Auto does not start Captar for it.
    assert coordinator.active_mode == MODE_OFF

    # Normal: the sun comes back up -- the reserve's own precondition lapses.
    hass.states.async_set("sun.sun", "above_horizon")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.data.active_soc_limit == 80.0  # default limit resolves again
    assert events[-1].data[ATTR_ACTIVE_SOC_LIMIT] == 80.0


async def test_uc07_deadline_appearing_lifts_the_reserve_the_same_cycle(hass):
    """UC05/UC07 mutual-exclusivity case: a departure deadline resolved for tomorrow lifts an
    already-active reserve cap on the very same cycle it becomes resolved (R9's precondition
    ceasing to hold), not one cycle later."""
    _seed_states(hass, status="Charging", ev_soc=50.0)
    hass.states.async_set("sun.sun", "below_horizon")
    hass.states.async_set("sensor.solar_forecast", "20.0")
    coordinator = await _setup(
        hass,
        data_overrides={CONF_SOLAR_FORECAST_ENTITY: "sensor.solar_forecast"},
        option_overrides={CONF_SOLAR_RESERVE_SOC: 55.0},
    )
    coordinator.active_profile = PROFILE_AUTO
    coordinator.active_mode = MODE_OFF
    coordinator.home_day_flag = True

    # Reserve engaged first.
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.data.active_soc_limit == 55.0

    # A departure deadline resolves for TOMORROW (the home-day override, since R14 row 3's
    # home-day flag is already True) -- same-cycle mutual-exclusivity lift, no other input
    # changes.
    coordinator.departure_home_day_override = dt_util.now().time()
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.data.active_soc_limit == 80.0  # reserve lifted -- default resolves again
