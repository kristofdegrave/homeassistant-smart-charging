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

All the thresholds this file's arithmetic depends on (battery capacity, solar step/threshold,
solar-forecast threshold) are pinned explicitly in `_entry_options` via their own `DEFAULT_*`
constants, rather than left as bare literals relying on the module defaults -- so a future
default change can't silently flip an Urgent/Unreachable or step-up boundary in these tests
without also touching this file.
"""

from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_charging.const import (
    ATTR_ACTIVE_SOC_LIMIT,
    ATTR_REQUIRED_CURRENT_A,
    CONF_CAPTAR_AVAILABLE,
    CONF_EV_BATTERY_CAPACITY_KWH,
    CONF_EV_SOC_ENTITY,
    CONF_GRID_VOLTAGE_ENTITY,
    CONF_MAX_PEAK_KW,
    CONF_MAX_SOLAR_SOC,
    CONF_SOLAR_FORECAST_ENTITY,
    CONF_SOLAR_FORECAST_THRESHOLD_KWH,
    CONF_SOLAR_INSTALLED,
    CONF_SOLAR_RESERVE_SOC,
    CONF_SOLAR_STEP_PP,
    CONF_SOLAR_STEP_THRESHOLD_PP,
    CONF_STATUS_TRANSLATION,
    DEFAULT_EV_BATTERY_CAPACITY_KWH,
    DEFAULT_MAX_SOLAR_SOC,
    DEFAULT_SOLAR_FORECAST_THRESHOLD_KWH,
    DEFAULT_SOLAR_STEP_PP,
    DEFAULT_SOLAR_STEP_THRESHOLD_PP,
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
from custom_components.smart_charging.engines.soc_target import SolarStepUpState
from tests.helpers import (
    capture_charger_current_writes,
    entry_data_base,
    entry_options_base,
    seed_ample_peak_headroom,
    seed_charger_states,
    seed_today_deadline,
)


def _entry_data(**overrides):
    """DATA bucket -- entity-role mappings + translation only (ADR-0005), narrowing the
    shared base's two-way status translation down to this suite's own single-status one
    (only "Charging" is ever seeded here) before layering the caller's overrides on top.

    Also drops the shared base's grid-voltage role mapping -- this suite predates that role
    and deliberately exercises the NF4 unmapped-role voltage path (falls back to the nominal
    voltage), not the sensed-voltage path."""
    data = entry_data_base(
        **{
            CONF_STATUS_TRANSLATION: {"Charging": STATE_CHARGING},
            CONF_EV_SOC_ENTITY: "sensor.ev_soc",
            **overrides,
        }
    )
    data.pop(CONF_GRID_VOLTAGE_ENTITY, None)
    return data


def _entry_options(**overrides):
    """OPTIONS bucket -- thresholds/defaults + interval (ADR-0005). Every R5/R8/R9 threshold
    this file's arithmetic relies on is pinned explicitly (via its own DEFAULT_* constant), not
    left implicit, so the module's own defaults can change without silently moving this file's
    Urgent/Unreachable/step-up boundaries."""
    return entry_options_base(
        **{
            CONF_MAX_PEAK_KW: 100.0,  # ample headroom -- R3 not under test here
            CONF_EV_BATTERY_CAPACITY_KWH: DEFAULT_EV_BATTERY_CAPACITY_KWH,
            CONF_MAX_SOLAR_SOC: DEFAULT_MAX_SOLAR_SOC,
            CONF_SOLAR_STEP_PP: DEFAULT_SOLAR_STEP_PP,
            CONF_SOLAR_STEP_THRESHOLD_PP: DEFAULT_SOLAR_STEP_THRESHOLD_PP,
            CONF_SOLAR_FORECAST_THRESHOLD_KWH: DEFAULT_SOLAR_FORECAST_THRESHOLD_KWH,
            **overrides,
        }
    )


def _seed_states(hass, *, status="Charging", net_w=0.0, charger_w=0.0, ev_soc=50.0):
    seed_charger_states(hass, status=status, net_w=net_w, charger_w=charger_w, ev_soc=ev_soc)


_capture_charger_current_writes = capture_charger_current_writes
_seed_ample_peak_headroom = seed_ample_peak_headroom


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


def _active_soc_limit_entity_id(hass):
    """Looked up by unique_id, not entity_id -- its translation entry is T6.3's own job, not
    this task's (mirrors tests/test_init.py's own active_soc_limit sensor lookup)."""
    entry_id = next(iter(hass.data[DOMAIN]))
    registry = er.async_get(hass)
    return registry.async_get_entity_id("sensor", DOMAIN, f"{entry_id}_active_soc_limit")


_seed_today_deadline = seed_today_deadline


# --- UC05: Normal -> Urgent -> Unreachable, both profiles' lever sets ---
#
# With the pinned 75 kWh battery capacity and a 10 pp SOC gap (70 -> 80), the required current
# is (75 * 10/100 * 1000) / hours / 230 A. A 4h deadline requires ~8.15 A (urgent, reachable);
# a 0.01h deadline requires ~3261 A (unreachable, far past the 16 A CONF_MAX_CURRENT ceiling).


async def test_uc05_auto_profile_normal_urgent_unreachable_transitions(hass, freezer):
    """UC05 main success scenario + 3a + exception flow, Auto profile with CapTar available:
    Normal (no deadline resolved) -> Urgent (escalates to Captar) -> reverts to Normal (SOC
    catches up) -> Unreachable (still Captar, but notifies) as conditions change cycle over
    cycle."""
    freezer.move_to("2026-01-15 12:00:00")
    calls = _capture_charger_current_writes(hass)
    _seed_states(hass, status="Charging", ev_soc=70.0)
    coordinator = await _setup(
        hass,
        data_overrides={CONF_CAPTAR_AVAILABLE: True, CONF_SOLAR_INSTALLED: False},
    )
    coordinator.active_profile = PROFILE_AUTO
    coordinator.active_mode = MODE_OFF

    # Normal: no deadline resolved yet -- required_a is None, never urgent.
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator._required_current.required_a is None
    assert coordinator._required_current.urgent is False
    assert coordinator.active_mode == MODE_OFF

    # Urgent: a 4h deadline the Off baseline can't meet, but still within the maximum
    # permitted rate (~8.15 A required vs. 16 A max), escalates Auto to Captar -- whose own
    # maximum-current request (16 A) reaches the write path.
    _seed_today_deadline(coordinator, hours_from_now=4)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator._required_current.urgent is True
    assert coordinator._required_current.unreachable is False
    assert coordinator.active_mode == MODE_CAPTAR
    assert hass.states.get("sensor.smart_charging_active_mode").state == MODE_CAPTAR
    assert calls[-1]["value"] == 16.0  # CONF_MAX_CURRENT -- Captar's own maximum-current request

    # Revert to Normal: the SOC catches up to the active limit -- nothing left to charge, so
    # urgency reverts even with the same (now-irrelevant) deadline still seeded.
    hass.states.async_set("sensor.ev_soc", "80.0")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator._required_current.urgent is False
    assert coordinator.active_mode != MODE_CAPTAR  # Auto falls back through rows 3-5

    # Unreachable: SOC back below the limit, but a much tighter deadline exceeds even
    # Captar's maximum-current request.
    hass.states.async_set("sensor.ev_soc", "70.0")
    events = []
    hass.bus.async_listen(EVENT_DEADLINE_UNREACHABLE_NOTIFIED, lambda e: events.append(e))
    _seed_today_deadline(coordinator, hours_from_now=0.01)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator._required_current.unreachable is True
    assert coordinator.active_mode == MODE_CAPTAR  # still escalated (R5/R16 postcondition)
    assert calls[-1]["value"] == 16.0  # clamped to the maximum permitted rate, not the
    # (huge) required current itself
    assert len(events) == 1
    expected_required_a = coordinator._required_current.required_a
    assert expected_required_a is not None and expected_required_a > 16.0
    assert events[0].data[ATTR_REQUIRED_CURRENT_A] == expected_required_a


async def test_uc05_auto_profile_without_captar_escalates_to_power_not_captar(hass, freezer):
    """UC05 alternate flow 3a' (R18 carve-out): CapTar capability absent -- Auto's urgency
    escalation falls back to Power instead of Captar, whose own configured target current (not
    a maximum-current request) is what reaches the write path."""
    freezer.move_to("2026-01-15 12:00:00")
    calls = _capture_charger_current_writes(hass)
    _seed_states(hass, status="Charging", ev_soc=70.0)
    coordinator = await _setup(
        hass,
        data_overrides={CONF_CAPTAR_AVAILABLE: False, CONF_SOLAR_INSTALLED: False},
    )
    coordinator.active_profile = PROFILE_AUTO
    coordinator.active_mode = MODE_OFF
    # 4h deadline: urgent (~8.15 A required), but reachable -- distinct from Unreachable.
    _seed_today_deadline(coordinator, hours_from_now=4)

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator._required_current.urgent is True
    assert coordinator._required_current.unreachable is False
    assert coordinator.active_mode == MODE_POWER
    assert calls[-1]["value"] == 10.0  # CONF_DEFAULT_TARGET_CURRENT -- Power's own request


async def test_uc05_manual_profile_never_changes_mode_but_still_flags_urgency(hass, freezer):
    """UC05 alternate flow 3b (NF2): Manual's active mode is never second-guessed by urgency,
    even though the required-current computation still reports it (only the peak-limit lever
    is available under Manual)."""
    freezer.move_to("2026-01-15 12:00:00")
    _seed_states(hass, status="Charging", ev_soc=70.0)
    coordinator = await _setup(hass, option_overrides={CONF_MAX_PEAK_KW: 10.0})
    # A small tracked peak (well below max_peak_kw) makes row 1's raise distinguishable from
    # row 2 -- row 2 alone (min(monthly, max)) would otherwise also read 10.0.
    _seed_ample_peak_headroom(coordinator, kw=1.0)
    coordinator.active_profile = PROFILE_MANUAL
    coordinator.active_mode = MODE_SOLAR
    _seed_today_deadline(coordinator, hours_from_now=4)

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator._required_current.urgent is True
    assert coordinator._required_current.unreachable is False
    assert coordinator.active_mode == MODE_SOLAR  # unchanged (NF2)
    assert coordinator.data.effective_peak_limit_kw == 10.0  # the one lever Manual does get


# --- UC06: Baseline -> SteppedUp -> Baseline, across a Solar/SolarOnly switch ---


async def test_uc06_solar_step_up_lifecycle_baseline_steppedup_baseline(hass):
    """UC06 main success scenario + exception flow: SOC nears the limit while a solar mode
    charges under `Auto` (R8/R16 precondition) -> step-up applies (Baseline -> SteppedUp); an
    Auto-driven escalation away from solar (e.g. Captar under urgency, simulated here by
    flipping only `active_mode`, profile staying `Auto`) clears it (SteppedUp -> Baseline,
    R7's shared reset) -- isolated from UC06's separate `Manual`-precondition case below."""
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
    entity_id = _active_soc_limit_entity_id(hass)
    assert float(hass.states.get(entity_id).state) == 85.0

    # Baseline again: the active mode leaves solar charging entirely (still under Auto) --
    # the step-up clears and the limit returns to the default.
    coordinator.active_mode = MODE_POWER
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator._step_up_state.stepped_pct is None
    assert coordinator.data.active_soc_limit == 80.0


async def test_uc06_step_up_survives_a_solar_to_solaronly_switch(hass):
    """UC06 alternate flow 4a: switching between Solar and SolarOnly is a self-loop within
    SteppedUp, not a reset -- only leaving solar charging entirely (R7's shared rule) clears
    it, per coordinator.py's own comment warning against conflating the two. The second
    cycle's SOC (76, below even the un-stepped 78 threshold) is chosen so the assertion can
    only pass if the step-up state was genuinely preserved across the switch, not accidentally
    re-derived fresh from the default limit (which would also apply a step at a higher SOC,
    making the two cases indistinguishable)."""
    _seed_states(hass, status="Charging", ev_soc=78.5)
    coordinator = await _setup(hass, data_overrides={CONF_SOLAR_INSTALLED: True})
    coordinator.active_profile = PROFILE_AUTO
    coordinator.active_mode = MODE_SOLAR

    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator._step_up_state.stepped_pct == 85.0

    hass.states.async_set("sensor.ev_soc", "76.0")
    coordinator.active_mode = MODE_SOLAR_ONLY
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator._step_up_state.stepped_pct == 85.0  # preserved, not cleared
    assert coordinator.data.active_soc_limit == 85.0


async def test_uc06_no_further_step_once_maximum_already_reached(hass):
    """UC06 alternate flow 2a: a step-up already clamped to `sc_max_solar_soc` applies no
    further step, even though SOC is again within the step threshold of that (maximum)
    limit."""
    _seed_states(hass, status="Charging", ev_soc=98.0)
    coordinator = await _setup(
        hass,
        data_overrides={CONF_SOLAR_INSTALLED: True},
        option_overrides={CONF_MAX_SOLAR_SOC: 100.0},
    )
    coordinator.active_profile = PROFILE_AUTO
    coordinator.active_mode = MODE_SOLAR
    # A prior step-up already clamped to the maximum -- seeded directly on the coordinator,
    # the same way tests/test_coordinator.py's own Task 5.1 suite seeds a pre-existing
    # step-up, since there is no owning entity for this state.
    coordinator._step_up_state = SolarStepUpState(stepped_pct=100.0)

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.data.active_soc_limit == 100.0  # unchanged -- no further step possible
    assert coordinator._step_up_state.stepped_pct == 100.0


async def test_uc06_manual_profile_never_applies_a_step_up(hass):
    """UC06 Preconditions: "under `Manual`, no step-up ever applies, regardless of which solar
    mode is selected" (R8/R16) -- SOC within the step threshold, charging in Solar, but under
    `Manual` the active SOC limit stays the plain default."""
    _seed_states(hass, status="Charging", ev_soc=78.5)
    coordinator = await _setup(hass, data_overrides={CONF_SOLAR_INSTALLED: True})
    coordinator.active_profile = PROFILE_MANUAL
    coordinator.active_mode = MODE_SOLAR

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator._step_up_state.stepped_pct is None
    assert coordinator.data.active_soc_limit == 80.0


# --- UC07: Normal -> Reserved -> Normal, and the UC05 mutual-exclusivity case ---


async def test_uc07_solar_reserve_normal_reserved_normal_cycle(hass):
    """UC07 main success scenario + Postconditions: starts in Normal (home-day flag clear);
    setting the flag with every other precondition already holding (sun down, ample forecast,
    no deadline for tomorrow) engages the reserve cap (Normal -> Reserved); the sun coming
    back up lifts it again (Reserved -> Normal)."""
    calls = _capture_charger_current_writes(hass)
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

    events = []
    hass.bus.async_listen(EVENT_ACTIVE_SOC_LIMIT_CHANGED, lambda e: events.append(e))

    # Normal: the home-day flag isn't set yet -- the reserve's own precondition doesn't hold.
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.data.active_soc_limit == 80.0  # default limit, reserve not engaged

    # Reserved: every precondition now holds, no deadline anywhere for tomorrow.
    coordinator.home_day_flag = True  # entity->coordinator wiring pending, issue #402
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.data.active_soc_limit == 55.0  # configured reserve cap, not default (80)
    assert events[-1].data[ATTR_ACTIVE_SOC_LIMIT] == 55.0
    # Row 4 (overnight top-up) withheld by the reserve -- Auto does not start Captar for it.
    assert coordinator.active_mode == MODE_OFF
    assert calls[-1]["value"] == 0.0

    # Normal: the sun comes back up -- the reserve's own precondition lapses.
    hass.states.async_set("sun.sun", "above_horizon")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.data.active_soc_limit == 80.0  # default limit resolves again
    assert events[-1].data[ATTR_ACTIVE_SOC_LIMIT] == 80.0


async def test_uc07_manual_profile_never_engages_the_reserve(hass):
    """UC07 alternate flow 1a: under `Manual`, the reserve's own precondition (R16's "Auto
    profile is active") never holds, regardless of the home-day flag or the solar forecast --
    the active SOC limit resolves as if this use-case weren't coordinating it at all."""
    _seed_states(hass, status="Charging", ev_soc=50.0)
    hass.states.async_set("sun.sun", "below_horizon")
    hass.states.async_set("sensor.solar_forecast", "20.0")
    coordinator = await _setup(
        hass,
        data_overrides={CONF_SOLAR_FORECAST_ENTITY: "sensor.solar_forecast"},
        option_overrides={CONF_SOLAR_RESERVE_SOC: 55.0},
    )
    coordinator.active_profile = PROFILE_MANUAL
    coordinator.active_mode = MODE_SOLAR
    coordinator.home_day_flag = True

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.data.active_soc_limit == 80.0  # default -- reserve never engages


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
