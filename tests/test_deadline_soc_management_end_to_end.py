"""End-to-end HA-harness regression for UC05/UC06/UC07 (#328, Task 6.2).

Every test is driven through `hass.config_entries.async_setup` + a full
`coordinator.async_refresh()` cycle against mocked entity states -- never by calling the pure
engine/profile functions directly (that's Phase 1's own test suites' job; this file proves the
coordinator wiring). `active_mode`/`active_profile`/`home_day_dates`/`departure_dow_defaults`/
`departure_holiday_override`/`departure_home_day_override` are seeded via the real owned
entities' HA state (`seed_owned_entity`/`seed_home_day`, ADR-0018) -- the Coordinator reads
them through the Store each cycle, so a direct `coordinator.<field> = ...` assignment would
be silently overwritten by the next refresh.

All the thresholds this file's arithmetic depends on (battery capacity, solar step/threshold,
solar-forecast threshold) are pinned explicitly in `_entry_options` via their own `DEFAULT_*`
constants, rather than left as bare literals relying on the module defaults -- so a future
default change can't silently flip an Urgent/Unreachable or step-up boundary in these tests
without also touching this file.
"""

from datetime import timedelta

import pytest
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_charging.adapters.sun import (
    SUN_STATE_ABOVE_HORIZON,
    SUN_STATE_BELOW_HORIZON,
)
from custom_components.smart_charging.const import (
    ATTR_ACTIVE_SOC_LIMIT,
    ATTR_REQUIRED_CURRENT_A,
    CONF_CAPTAR_AVAILABLE,
    CONF_EV_BATTERY_CAPACITY_KWH,
    CONF_EV_SOC_ENTITY,
    CONF_GRID_VOLTAGE_ENTITY,
    CONF_MAX_PEAK_KW,
    CONF_MAX_SOLAR_SOC,
    CONF_SOLAR_AVAILABLE,
    CONF_SOLAR_FORECAST_ENTITY,
    CONF_SOLAR_FORECAST_THRESHOLD_KWH,
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
    STATE_DISCONNECTED,
)
from custom_components.smart_charging.engines.soc_target import SolarStepUpState
from tests.helpers import (
    capture_charger_current_writes,
    entry_data_base,
    entry_options_base,
    seed_ample_peak_headroom,
    seed_charger_states,
    seed_home_day,
    seed_owned_entity,
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
    pre-seeded so R3 never interferes with these UC05/UC06/UC07-focused assertions.

    Note (ADR-0018, issue #402): the real departure-time entities' compiled defaults
    (Mon-Fri 06:00, R14) are no longer inert once the Coordinator reads them through the
    Store -- the Coordinator's first refresh (inside `async_setup`, before this helper
    returns) already captures whichever weekday "now" is on, and a captured value is never
    cleared by a later None read (ADR-0018: None means "unresolvable, keep current", not
    "clear"). Tests that need a genuine "no deadline" starting condition must freeze time on
    a weekend date (Sat/Sun's own default is None), not rely on blanking the entity
    afterward -- blanking after this helper returns cannot undo an already-captured value."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=_entry_data(**(data_overrides or {})),
        options=_entry_options(**(option_overrides or {})),
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data.coordinator
    _seed_ample_peak_headroom(coordinator)
    return coordinator


def _active_soc_limit_entity_id(hass):
    """Looked up by unique_id, not entity_id -- its translation entry is T6.3's own job, not
    this task's (mirrors tests/test_init.py's own active_soc_limit sensor lookup)."""
    entry_id = hass.config_entries.async_entries(DOMAIN)[0].entry_id
    registry = er.async_get(hass)
    return registry.async_get_entity_id("sensor", DOMAIN, f"{entry_id}_active_soc_limit")


_seed_today_deadline = seed_today_deadline


# --- UC05: Normal -> Urgent -> Unreachable, both profiles' lever sets ---
#
# With the pinned 75 kWh battery capacity and a 10 pp SOC gap (70 -> 80), the required current
# is (75 * 10/100 * 1000) / hours / 230 A. Since #1078 urgency is judged by R5's slack test --
# required current > escalated maximum permitted rate / 1.25 -- and with ample peak headroom that
# rate is C1's 16 A ceiling, so the threshold is 12.8 A. A 2.5h deadline requires ~13.04 A
# (urgent, reachable); a 4h deadline requires only ~8.15 A and is deliberately NOT urgent, since
# four hours to deliver a two-hour charge is exactly the ample slack #1078 was about; a 0.01h
# deadline requires ~3261 A (unreachable, far past that 16 A ceiling).
#
# Every test below that asserts urgency is frozen on a SATURDAY. R14's day-of-week default is
# None at weekends, so the only deadline in play is the one the test seeds. On a weekday the
# compiled 06:00 default sits ~2 h from these tests' frozen time and needs ~16.3 A, which latches
# urgency during `_setup`'s own refresh -- the assertions then pass on that leftover latch rather
# than on the deadline they name, which is how three of these tests were silently vacuous.


async def test_uc05_auto_profile_normal_urgent_unreachable_transitions(hass, freezer):
    """UC05 main success scenario + 3a + exception flow, Auto profile with CapTar available:
    Normal (no deadline resolved) -> Urgent (escalates to Captar) -> reverts to Normal (SOC
    catches up) -> Unreachable (still Captar, but notifies) as conditions change cycle over
    cycle.

    Frozen on a Saturday (R14: day-of-week default is None on weekends) so the "Normal, no
    deadline resolved" starting condition is genuinely true of the real
    time.smart_charging_departure_sat entity's own compiled default -- once the Coordinator
    reads departure_dow_defaults through the Store (ADR-0018, issue #402), a weekday's
    06:00 default is a real, resolvable deadline, not inert."""
    freezer.move_to("2026-01-17 12:00:00")
    calls = _capture_charger_current_writes(hass)
    _seed_states(hass, status="Charging", ev_soc=70.0)
    coordinator = await _setup(
        hass,
        data_overrides={CONF_CAPTAR_AVAILABLE: True, CONF_SOLAR_AVAILABLE: False},
    )
    seed_owned_entity(hass, "select.smart_charging_profile", PROFILE_AUTO)
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_OFF)

    # Normal: no deadline resolved yet -- required_a is None, never urgent.
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator._required_current.required_a is None
    assert coordinator._required_current.urgent is False
    assert coordinator.active_mode == MODE_OFF

    # Urgent: a 2.5h deadline needing ~13.04 A. Since #1078 the Off baseline being unable to
    # meet it is NOT what makes this urgent -- the slack test is: 13.04 A exceeds the escalated
    # maximum permitted rate divided by 1.25 (16/1.25 = 12.8 A), while staying within the 16 A
    # rate itself. The old 4h deadline here needed only ~8.15 A and is deliberately no longer
    # urgent: with 4 hours to deliver a 2-hour charge there is ample slack, which is exactly the
    # live defect this replaced. Escalates Auto to Captar, whose own maximum-current request
    # (16 A) reaches the write path.
    _seed_today_deadline(hass, hours_from_now=2.5)
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
    _seed_today_deadline(hass, hours_from_now=0.01)
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
    freezer.move_to("2026-01-17 12:00:00")  # Saturday: no compiled default to latch on
    calls = _capture_charger_current_writes(hass)
    _seed_states(hass, status="Charging", ev_soc=70.0)
    coordinator = await _setup(
        hass,
        data_overrides={CONF_CAPTAR_AVAILABLE: False, CONF_SOLAR_AVAILABLE: False},
    )
    seed_owned_entity(hass, "select.smart_charging_profile", PROFILE_AUTO)
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_OFF)
    # 2.5h deadline: ~13.04 A required, over the 12.8 A slack threshold and under the 16 A
    # escalated rate -- urgent but reachable, distinct from Unreachable. Not 4h: that needs only
    # ~8.15 A and is deliberately not urgent (see this section's header comment).
    _seed_today_deadline(hass, hours_from_now=2.5)

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
    freezer.move_to("2026-01-17 12:00:00")  # Saturday: no compiled default to latch on
    _seed_states(hass, status="Charging", ev_soc=70.0)
    coordinator = await _setup(hass, option_overrides={CONF_MAX_PEAK_KW: 10.0})
    # A small tracked peak (well below max_peak_kw) makes row 1's raise distinguishable from
    # row 2 -- row 2 alone (min(monthly, max)) would otherwise also read 10.0.
    _seed_ample_peak_headroom(coordinator, kw=1.0)
    seed_owned_entity(hass, "select.smart_charging_profile", PROFILE_MANUAL)
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_SOLAR)
    _seed_today_deadline(hass, hours_from_now=2.5)  # ~13.04 A: over the 12.8 A slack threshold

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator._required_current.urgent is True
    assert coordinator._required_current.unreachable is False
    assert coordinator.active_mode == MODE_SOLAR  # unchanged (NF2)
    assert coordinator.data.effective_peak_limit_kw == 10.0  # the one lever Manual does get


# --- #1335 (R17 AC4/R6, amended by A5a/#1300's UC04 SOC-unavailable exception flow):
# Power still stops at the active SOC limit itself, and that stop survives a cycle where the
# ev_soc reading goes missing. ---


@pytest.mark.parametrize("ev_soc", [80.0, 85.0], ids=["at_limit", "above_limit"])
async def test_should_stop_power_charging_when_soc_reading_at_or_above_active_limit(
    hass, freezer, ev_soc
):
    """Should stop commanding current when Manual+Power has an ev_soc reading at or above the
    active SOC limit and no settable vehicle charge-limit entity -- #1335's confirmed
    reproduction (85% SOC against the default 80% limit kept commanding the 10 A default
    target current instead of dropping to 0 A). Parametrized over the boundary itself (80%,
    "at") and past it (85%, "above") -- R17 AC4/R6 stop "when it is reached", and `>=` is the
    operator the fix uses, so the exact boundary is load-bearing, not just the overshoot."""
    freezer.move_to("2026-01-17 12:00:00")  # Saturday: no compiled deadline default to latch on

    # Arrange: Manual + Power, an ev_soc reading already at/above the default 80% limit, and no
    # vehicle charge-limit role mapped (this suite's `_entry_data` never maps one).
    calls = _capture_charger_current_writes(hass)
    _seed_states(hass, status="Charging", ev_soc=ev_soc)
    coordinator = await _setup(
        hass, data_overrides={CONF_CAPTAR_AVAILABLE: False, CONF_SOLAR_AVAILABLE: False}
    )
    seed_owned_entity(hass, "select.smart_charging_profile", PROFILE_MANUAL)
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_POWER)

    # Act
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # Assert
    assert coordinator.active_mode == MODE_POWER
    assert coordinator.data.active_soc_limit == 80.0
    assert calls[-1]["value"] == 0.0


async def test_should_resume_power_charging_when_active_limit_rises_above_the_reading(
    hass, freezer
):
    """Should resume commanding Power's target current once the active SOC limit is raised back
    above an already-at-limit ev_soc reading -- UC04's Idle row, re-evaluated fresh every cycle
    off a present reading, exactly like the other SOC-gated modes' own guard: this is Idle
    blocking Charging, then no longer blocking it, not a genuine SocReached stop being left
    (see the missing-reading test below for that latch, which this one does not set at all)."""
    freezer.move_to("2026-01-17 12:00:00")  # Saturday: no compiled deadline default to latch on

    # Arrange: Manual + Power, an ev_soc reading already at the default 80% limit blocks
    # Charging (UC04's Idle row) -- one refresh to actually reach that 0 A state.
    calls = _capture_charger_current_writes(hass)
    _seed_states(hass, status="Charging", ev_soc=85.0)
    coordinator = await _setup(
        hass, data_overrides={CONF_CAPTAR_AVAILABLE: False, CONF_SOLAR_AVAILABLE: False}
    )
    seed_owned_entity(hass, "select.smart_charging_profile", PROFILE_MANUAL)
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_POWER)
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # Act: raise the active SOC limit override above the still-unchanged 85% reading. Seeded
    # through the real owned entity (ADR-0018), not a direct field assignment -- the module
    # docstring above warns a direct `coordinator.<field> = ...` write is silently overwritten
    # by the next refresh's Store read (`_read_owned_entities`).
    seed_owned_entity(hass, "number.smart_charging_soc_limit_override", "90.0")
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # Assert
    assert coordinator.data.active_soc_limit == 90.0
    assert calls[-2]["value"] == 0.0  # stopped, before the limit rose (the Arrange refresh)
    assert calls[-1]["value"] == 10.0  # CONF_DEFAULT_TARGET_CURRENT -- Power resumes


async def test_should_keep_power_stopped_when_the_soc_reading_becomes_unavailable(hass, freezer):
    """Should stay at 0 A, not resume, on a cycle where the ev_soc reading goes missing after
    Power has genuinely stopped at the active SOC limit -- UC04's *State of charge unavailable*
    exception flow (A5a/#1300), folded into #1335's I0f entry: the stop is a latch against a
    *missing* reading (unlike the rising-limit case above, which does clear it) precisely
    because a missing reading must never be read as "below the limit" -- that would silently
    resume charging on the one signal (C5's own non-fault) that carries no SOC information at
    all. Also proves the missing reading itself still doesn't fault Power (ADR-0042/C5).

    Arranged as a genuine Charging -> SocReached transition (75%, below the limit, actually
    drawing current, then 85%, crossing it) rather than starting directly at 85% -- UC04's own
    State model distinguishes a real stop from a car merely resting in Idle at or above the
    limit, and only the former survives a missing reading (see the sibling test proving the
    Idle case's own, opposite behaviour)."""
    freezer.move_to("2026-01-17 12:00:00")  # Saturday: no compiled deadline default to latch on

    # Arrange: charge below the limit first, so the stop that follows is a genuine
    # Charging -> SocReached transition, not Idle merely resting at/above the limit.
    calls = _capture_charger_current_writes(hass)
    _seed_states(hass, status="Charging", ev_soc=75.0)
    coordinator = await _setup(
        hass, data_overrides={CONF_CAPTAR_AVAILABLE: False, CONF_SOLAR_AVAILABLE: False}
    )
    seed_owned_entity(hass, "select.smart_charging_profile", PROFILE_MANUAL)
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_POWER)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    hass.states.async_set("sensor.ev_soc", "85.0")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert calls[-2]["value"] == 10.0  # was genuinely charging, below the limit
    assert calls[-1]["value"] == 0.0  # crossed it -- a real stop, not Idle

    # Act: the ev_soc sensor goes unavailable while still connected and Charging -- the reading
    # is gone, not the car.
    hass.states.async_set("sensor.ev_soc", STATE_UNAVAILABLE)
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # Assert
    assert calls[-1]["value"] == 0.0  # still stopped -- the latch, not the missing reading, held
    assert coordinator.data.fault is False  # C5: a missing reading is a non-fault in Power
    assert coordinator.active_mode == MODE_POWER


async def test_should_resume_power_charging_without_a_soc_reading_when_unplugged_and_replugged(
    hass, freezer
):
    """Should resume commanding Power's target current, even with no ev_soc reading, once the
    car has been disconnected and reconnected after Power stopped at the active SOC limit --
    UC04/R7 AC5's resume condition 2. Proven the same way the missing-reading test above proves
    the *opposite* case: reconnecting with the reading still unavailable would still read 0 A if
    the disconnect had left the stop's own latch untouched, so a resumed 10 A here can only come
    from the disconnect actually having cleared it, per `_dispatch_mode`'s own early branch."""
    freezer.move_to("2026-01-17 12:00:00")  # Saturday: no compiled deadline default to latch on

    # Arrange: charge below the limit first, then cross it, so the stop that follows is a
    # genuine Charging -> SocReached transition -- plus a translation entry for a disconnected
    # charger status (this suite's own `_entry_data` otherwise maps only "Charging", per its
    # docstring).
    calls = _capture_charger_current_writes(hass)
    _seed_states(hass, status="Charging", ev_soc=75.0)
    coordinator = await _setup(
        hass,
        data_overrides={
            CONF_CAPTAR_AVAILABLE: False,
            CONF_SOLAR_AVAILABLE: False,
            CONF_STATUS_TRANSLATION: {
                "Charging": STATE_CHARGING,
                "Disconnected": STATE_DISCONNECTED,
            },
        },
    )
    seed_owned_entity(hass, "select.smart_charging_profile", PROFILE_MANUAL)
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_POWER)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    hass.states.async_set("sensor.ev_soc", "85.0")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert calls[-2]["value"] == 10.0  # was genuinely charging, below the limit
    assert calls[-1]["value"] == 0.0  # crossed it -- a real stop, not Idle

    # Act: unplug (a disconnected charger status) and replug (back to Charging), with the
    # ev_soc reading gone by the time it reconnects.
    hass.states.async_set("sensor.evse", "Disconnected")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    hass.states.async_set("sensor.evse", "Charging")
    hass.states.async_set("sensor.ev_soc", STATE_UNAVAILABLE)
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # Assert
    assert calls[-1]["value"] == 10.0  # CONF_DEFAULT_TARGET_CURRENT -- the stop did not survive
    assert coordinator.data.fault is False  # C5: still no fault, missing reading or not


async def test_should_resume_power_charging_when_the_limit_changes_while_unavailable(hass, freezer):
    """Should resume commanding Power's target current when the active SOC limit itself
    changes on a cycle where the ev_soc reading is unavailable -- UC04 line 64/R7 AC5 name the
    active SOC limit changing as a clearing condition on its own, "not a reading": unlike the
    missing-reading test above (where nothing else changed), the limit override rising here is
    the coordinator's own edge-detected `soc_limit_changed` signal, which the stop's fix reads
    even with no reading to confirm SOC against the new limit. Arranged as a genuine Charging
    -> SocReached transition (see the missing-reading test's own docstring for why): with a
    latch that was never set in the first place -- the Idle case -- a missing reading alone
    already resumes charging regardless of `limit_changed`, which would prove nothing about
    this specific clearing path."""
    freezer.move_to("2026-01-17 12:00:00")  # Saturday: no compiled deadline default to latch on

    # Arrange: charge below the limit first, then cross it, so the stop that follows is a
    # genuine Charging -> SocReached transition.
    calls = _capture_charger_current_writes(hass)
    _seed_states(hass, status="Charging", ev_soc=75.0)
    coordinator = await _setup(
        hass, data_overrides={CONF_CAPTAR_AVAILABLE: False, CONF_SOLAR_AVAILABLE: False}
    )
    seed_owned_entity(hass, "select.smart_charging_profile", PROFILE_MANUAL)
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_POWER)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    hass.states.async_set("sensor.ev_soc", "85.0")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert calls[-2]["value"] == 10.0  # was genuinely charging, below the limit
    assert calls[-1]["value"] == 0.0  # crossed it -- a real stop, not Idle

    # Act: the reading goes unavailable AND the limit override rises, on the same cycle.
    hass.states.async_set("sensor.ev_soc", STATE_UNAVAILABLE)
    seed_owned_entity(hass, "number.smart_charging_soc_limit_override", "90.0")
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # Assert
    assert coordinator.data.active_soc_limit == 90.0
    assert calls[-1]["value"] == 10.0  # resumed -- the limit change alone was enough
    assert coordinator.data.fault is False  # C5: still no fault, missing reading or not


async def test_should_resume_power_without_a_reading_when_the_limit_rose_under_another_mode(
    hass, freezer
):
    """Should resume commanding Power's target current on switching back to it, with no ev_soc
    reading of its own yet, when the active SOC limit rose while a *different* mode was active
    -- the active SOC limit and ev_soc are cycle-wide facts, resolved once per cycle regardless
    of which mode consumes them (#1335), so the limit rising while Solar was active (with its
    own reading) has to be visible to Power immediately on switching back. The reading is
    deliberately unavailable on the switch-back cycle itself: with a reading present there,
    Power's own comparison would resume it anyway, proving nothing about the cross-mode
    refresh this test targets. Arranged as a genuine Charging -> SocReached transition (see
    the missing-reading test's own docstring for why) -- with a latch that was never set in
    the first place, a missing reading on the switch-back cycle already resumes charging on
    its own, proving nothing about the cross-mode refresh either."""
    freezer.move_to("2026-01-17 12:00:00")  # Saturday: no compiled deadline default to latch on

    # Arrange: Power charges below the default 80% limit, then genuinely stops there once the
    # reading crosses it, then switches to Solar with the reading still at 85% (Solar is
    # itself SOC-gated, so it stays stopped too -- proven below, not just assumed).
    calls = _capture_charger_current_writes(hass)
    _seed_states(hass, status="Charging", ev_soc=75.0, net_w=100.0, charger_w=500.0)
    hass.states.async_set("sun.sun", SUN_STATE_ABOVE_HORIZON)
    coordinator = await _setup(
        hass, data_overrides={CONF_CAPTAR_AVAILABLE: False, CONF_SOLAR_AVAILABLE: True}
    )
    seed_owned_entity(hass, "select.smart_charging_profile", PROFILE_MANUAL)
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_POWER)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    hass.states.async_set("sensor.ev_soc", "85.0")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert calls[-2]["value"] == 10.0  # was genuinely charging, below the limit
    assert calls[-1]["value"] == 0.0  # crossed it -- a real stop, not Idle
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_SOLAR)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert calls[-1]["value"] == 0.0  # Solar gated too (still 85% against the 80% limit)

    # Act: the limit override rises above the still-85% reading while Solar (not Power) is
    # active, then Manual switches back to Power on a cycle where the reading has since gone
    # unavailable -- so only the earlier, cross-mode refresh can be what resumes it.
    seed_owned_entity(hass, "number.smart_charging_soc_limit_override", "90.0")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    hass.states.async_set("sensor.ev_soc", STATE_UNAVAILABLE)
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_POWER)
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # Assert
    assert coordinator.data.active_soc_limit == 90.0
    assert calls[-1]["value"] == 10.0  # resumes with no reading of its own -- Solar's refreshed it
    assert coordinator.data.fault is False  # C5: still no fault, missing reading or not


async def test_should_start_power_charging_without_a_reading_when_it_never_actually_stopped(
    hass, freezer
):
    """Should command Power's target current on a cycle with no ev_soc reading, when Power has
    never actually been charging at the active SOC limit before -- UC04's own State model draws
    this distinction explicitly: "Only a stop made at the limit is held this way -- a car
    resting in Idle or Cooldown at or above the limit has no such stop behind it". A reading at
    or above the limit taken while `Off` (not `Power`) was active never makes a stop, so it must
    not be read back as one once Power is selected with the reading now gone."""
    freezer.move_to("2026-01-17 12:00:00")  # Saturday: no compiled deadline default to latch on

    # Arrange: Off active with an 85% reading against the default 80% limit -- Off always
    # commands 0 A on its own, so this proves nothing about Power's own stop.
    calls = _capture_charger_current_writes(hass)
    _seed_states(hass, status="Charging", ev_soc=85.0)
    coordinator = await _setup(
        hass, data_overrides={CONF_CAPTAR_AVAILABLE: False, CONF_SOLAR_AVAILABLE: False}
    )
    seed_owned_entity(hass, "select.smart_charging_profile", PROFILE_MANUAL)
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_OFF)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert calls[-1]["value"] == 0.0  # Off's own 0 A, not a Power stop

    # Act: switch to Power on a cycle where the reading has since gone unavailable -- if the
    # 85%-while-Off reading had wrongly latched a Power stop, this cycle would still read 0 A.
    hass.states.async_set("sensor.ev_soc", STATE_UNAVAILABLE)
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_POWER)
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # Assert
    assert calls[-1]["value"] == 10.0  # CONF_DEFAULT_TARGET_CURRENT -- never actually stopped
    assert coordinator.data.fault is False  # C5: still no fault, missing reading or not


async def test_should_start_power_charging_without_a_reading_after_a_mode_switch_mid_charge(
    hass, freezer
):
    """Should command Power's target current on a cycle with no ev_soc reading, when Power was
    genuinely charging before the user switched away from it -- not the case a genuine
    Charging -> SocReached stop protects. Power's own "is it currently charging" fact must not
    survive a mode switch: without that reset, a reading taken at or above the limit while a
    *different* mode was active would be misread, on switching back, as evidence Power itself
    had just made a stop there, even though this session's Power dispatch never saw a reading
    above the limit at all."""
    freezer.move_to("2026-01-17 12:00:00")  # Saturday: no compiled deadline default to latch on

    # Arrange: Power charges below the limit, then the user switches to Off before the reading
    # ever reaches the limit.
    calls = _capture_charger_current_writes(hass)
    _seed_states(hass, status="Charging", ev_soc=75.0)
    coordinator = await _setup(
        hass, data_overrides={CONF_CAPTAR_AVAILABLE: False, CONF_SOLAR_AVAILABLE: False}
    )
    seed_owned_entity(hass, "select.smart_charging_profile", PROFILE_MANUAL)
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_POWER)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert calls[-1]["value"] == 10.0  # genuinely charging, below the limit
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_OFF)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert calls[-1]["value"] == 0.0  # Off's own 0 A

    # Act: the reading reaches the limit while Off (not Power) is active, then Power is
    # selected again on a cycle where the reading has since gone unavailable.
    hass.states.async_set("sensor.ev_soc", "85.0")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    hass.states.async_set("sensor.ev_soc", STATE_UNAVAILABLE)
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_POWER)
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # Assert
    assert calls[-1]["value"] == 10.0  # never actually stopped in this Power session
    assert coordinator.data.fault is False  # C5: still no fault, missing reading or not


# --- UC06: Baseline -> SteppedUp -> Baseline, across a Solar/SolarOnly switch ---


async def test_uc06_solar_step_up_lifecycle_baseline_steppedup_baseline(hass, freezer):
    """UC06 main success scenario + exception flow: SOC nears the limit while a solar mode
    charges under `Auto` (R8/R16 precondition) -> step-up applies (Baseline -> SteppedUp); an
    Auto-driven escalation away from solar (e.g. Captar under urgency, simulated here by
    flipping only `active_mode`, profile staying `Auto`) clears it (SteppedUp -> Baseline,
    R7's shared reset) -- isolated from UC06's separate `Manual`-precondition case below.

    Frozen on a Saturday (R14: day-of-week default is None) so Auto's mode selection isn't
    contaminated by a real, resolvable weekday deadline (ADR-0018, issue #402) -- this test
    is about step-up, not deadline urgency."""
    freezer.move_to("2026-01-17 12:00:00")
    _seed_states(hass, status="Charging", ev_soc=50.0, net_w=100.0, charger_w=500.0)
    # Sufficient surplus keeps Auto in Solar.
    hass.states.async_set("sun.sun", SUN_STATE_ABOVE_HORIZON)
    coordinator = await _setup(hass, data_overrides={CONF_SOLAR_AVAILABLE: True})
    seed_owned_entity(hass, "select.smart_charging_profile", PROFILE_AUTO)
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_SOLAR)

    # Baseline: SOC (50) is far from the limit (80) -- no step applies yet.
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.data.active_soc_limit == 80.0
    assert coordinator._step_up_gate.state.stepped_pct is None
    assert coordinator.active_mode == MODE_SOLAR  # Auto keeps selecting Solar (row 3)

    # SteppedUp: SOC now within the default 2pp step threshold of the limit.
    hass.states.async_set("sensor.ev_soc", "78.5")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.data.active_soc_limit == 85.0  # default 80 + default step 5
    assert coordinator._step_up_gate.state.stepped_pct == 85.0
    entity_id = _active_soc_limit_entity_id(hass)
    assert float(hass.states.get(entity_id).state) == 85.0

    # Baseline again: the active mode leaves solar charging entirely (still under Auto) --
    # the step-up clears and the limit returns to the default. R8's own check reads
    # active_mode with a one-cycle lag under Auto (coordinator.py:322-326: "still the PRIOR
    # cycle's resolved mode" -- Auto's own resolution runs later in the same cycle), so this
    # simulates "last cycle resolved Power" via the coordinator's own setter directly --
    # seeding the real selector wouldn't reach active_mode at all under Auto (ADR-0018's
    # fix for the every-cycle-reset bug this same technique originally exposed).
    coordinator.set_active_mode(MODE_POWER)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator._step_up_gate.state.stepped_pct is None
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
    coordinator = await _setup(hass, data_overrides={CONF_SOLAR_AVAILABLE: True})
    seed_owned_entity(hass, "select.smart_charging_profile", PROFILE_AUTO)
    # R8's step-up check reads active_mode with a one-cycle lag under Auto
    # (coordinator.py:322-326) -- seeding the real selector has no effect on active_mode
    # under Auto (ADR-0018), so "solar was charging last cycle" is simulated via the
    # coordinator's own setter directly.
    coordinator.set_active_mode(MODE_SOLAR)

    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator._step_up_gate.state.stepped_pct == 85.0

    hass.states.async_set("sensor.ev_soc", "76.0")
    # Same one-cycle-lag reasoning as the sibling test above: simulate "last cycle resolved
    # SolarOnly" via the coordinator's own setter, not the (Auto-ignored) real selector.
    coordinator.set_active_mode(MODE_SOLAR_ONLY)
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator._step_up_gate.state.stepped_pct == 85.0  # preserved, not cleared
    assert coordinator.data.active_soc_limit == 85.0


async def test_uc06_no_further_step_once_maximum_already_reached(hass):
    """UC06 alternate flow 2a: a step-up already clamped to `sc_max_solar_soc` applies no
    further step, even though SOC is again within the step threshold of that (maximum)
    limit."""
    _seed_states(hass, status="Charging", ev_soc=98.0)
    coordinator = await _setup(
        hass,
        data_overrides={CONF_SOLAR_AVAILABLE: True},
        option_overrides={CONF_MAX_SOLAR_SOC: 100.0},
    )
    seed_owned_entity(hass, "select.smart_charging_profile", PROFILE_AUTO)
    # R8's step-up check reads active_mode with a one-cycle lag under Auto
    # (coordinator.py:322-326) -- seeding the real selector has no effect on active_mode
    # under Auto (ADR-0018), so "solar was charging last cycle" is simulated via the
    # coordinator's own setter directly, the same way tests/test_coordinator.py's own
    # Task 5.1 suite seeds pre-existing cycle state.
    coordinator.set_active_mode(MODE_SOLAR)
    # A prior step-up already clamped to the maximum -- seeded directly on the coordinator,
    # the same way tests/test_coordinator.py's own Task 5.1 suite seeds a pre-existing
    # step-up, since there is no owning entity for this state.
    coordinator._step_up_gate.state = SolarStepUpState(stepped_pct=100.0)

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.data.active_soc_limit == 100.0  # unchanged -- no further step possible
    assert coordinator._step_up_gate.state.stepped_pct == 100.0


async def test_uc06_manual_profile_never_applies_a_step_up(hass):
    """UC06 Preconditions: "under `Manual`, no step-up ever applies, regardless of which solar
    mode is selected" (R8/R16) -- SOC within the step threshold, charging in Solar, but under
    `Manual` the active SOC limit stays the plain default."""
    _seed_states(hass, status="Charging", ev_soc=78.5)
    coordinator = await _setup(hass, data_overrides={CONF_SOLAR_AVAILABLE: True})
    seed_owned_entity(hass, "select.smart_charging_profile", PROFILE_MANUAL)
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_SOLAR)

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator._step_up_gate.state.stepped_pct is None
    assert coordinator.data.active_soc_limit == 80.0


# --- UC07: Normal -> Reserved -> Normal, and the UC05 mutual-exclusivity case ---


async def test_uc07_solar_reserve_normal_reserved_normal_cycle(hass, freezer):
    """UC07 main success scenario + Postconditions: starts in Normal (home-day flag clear);
    setting the flag with every other precondition already holding (sun down, ample forecast,
    no deadline for tomorrow) engages the reserve cap (Normal -> Reserved); the sun coming
    back up lifts it again (Reserved -> Normal).

    Frozen on a Saturday so "no deadline for tomorrow" (Sunday, R14 default None) is
    genuinely true of the real departure-time entities (ADR-0018, issue #402) -- unfrozen,
    this precondition would depend on whatever the real wall-clock weekday happened to be."""
    freezer.move_to("2026-01-17 12:00:00")
    calls = _capture_charger_current_writes(hass)
    _seed_states(hass, status="Charging", ev_soc=50.0)
    hass.states.async_set("sun.sun", SUN_STATE_BELOW_HORIZON)
    hass.states.async_set("sensor.solar_forecast", "20.0")  # above the 12 kWh default threshold
    coordinator = await _setup(
        hass,
        data_overrides={CONF_SOLAR_FORECAST_ENTITY: "sensor.solar_forecast"},
        option_overrides={CONF_SOLAR_RESERVE_SOC: 55.0},
    )
    seed_owned_entity(hass, "select.smart_charging_profile", PROFILE_AUTO)
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_OFF)

    events = []
    hass.bus.async_listen(EVENT_ACTIVE_SOC_LIMIT_CHANGED, lambda e: events.append(e))

    # Normal: the home-day flag isn't set yet -- the reserve's own precondition doesn't hold.
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.data.active_soc_limit == 80.0  # default limit, reserve not engaged

    # Reserved: every precondition now holds, no deadline anywhere for tomorrow.
    seed_home_day(hass, {dt_util.now().date() + timedelta(days=1)})
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.data.active_soc_limit == 55.0  # configured reserve cap, not default (80)
    assert events[-1].data[ATTR_ACTIVE_SOC_LIMIT] == 55.0
    # Row 4 (overnight top-up) withheld by the reserve -- Auto does not start Captar for it.
    assert coordinator.active_mode == MODE_OFF
    assert calls[-1]["value"] == 0.0

    # Normal: the sun comes back up -- the reserve's own precondition lapses.
    hass.states.async_set("sun.sun", SUN_STATE_ABOVE_HORIZON)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.data.active_soc_limit == 80.0  # default limit resolves again
    assert events[-1].data[ATTR_ACTIVE_SOC_LIMIT] == 80.0


async def test_uc07_manual_profile_never_engages_the_reserve(hass, freezer):
    """UC07 alternate flow 1a: under `Manual`, the reserve's own precondition (R16's "Auto
    profile is active") never holds, regardless of the home-day flag or the solar forecast --
    the active SOC limit resolves as if this use-case weren't coordinating it at all."""
    freezer.move_to("2026-01-17 12:00:00")
    _seed_states(hass, status="Charging", ev_soc=50.0)
    hass.states.async_set("sun.sun", SUN_STATE_BELOW_HORIZON)
    hass.states.async_set("sensor.solar_forecast", "20.0")
    coordinator = await _setup(
        hass,
        data_overrides={CONF_SOLAR_FORECAST_ENTITY: "sensor.solar_forecast"},
        option_overrides={CONF_SOLAR_RESERVE_SOC: 55.0},
    )
    seed_owned_entity(hass, "select.smart_charging_profile", PROFILE_MANUAL)
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_SOLAR)
    seed_home_day(hass, {dt_util.now().date() + timedelta(days=1)})

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.data.active_soc_limit == 80.0  # default -- reserve never engages


async def test_uc07_deadline_appearing_lifts_the_reserve_the_same_cycle(hass, freezer):
    """UC05/UC07 mutual-exclusivity case: a departure deadline resolved for tomorrow lifts an
    already-active reserve cap on the very same cycle it becomes resolved (R9's precondition
    ceasing to hold), not one cycle later."""
    freezer.move_to("2026-01-17 12:00:00")
    _seed_states(hass, status="Charging", ev_soc=50.0)
    hass.states.async_set("sun.sun", SUN_STATE_BELOW_HORIZON)
    hass.states.async_set("sensor.solar_forecast", "20.0")
    coordinator = await _setup(
        hass,
        data_overrides={CONF_SOLAR_FORECAST_ENTITY: "sensor.solar_forecast"},
        option_overrides={CONF_SOLAR_RESERVE_SOC: 55.0},
    )
    seed_owned_entity(hass, "select.smart_charging_profile", PROFILE_AUTO)
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_OFF)
    seed_home_day(hass, {dt_util.now().date() + timedelta(days=1)})

    # Reserve engaged first.
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.data.active_soc_limit == 55.0

    # A departure deadline resolves for TOMORROW (the home-day override, since R14 row 3's
    # home-day flag is already True) -- same-cycle mutual-exclusivity lift, no other input
    # changes.
    seed_owned_entity(
        hass, "time.smart_charging_departure_home_day", dt_util.now().time().isoformat()
    )
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.data.active_soc_limit == 80.0  # reserve lifted -- default resolves again
