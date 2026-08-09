"""End-to-end HA-harness regression for UC08 (R13).

Every test is driven through `hass.config_entries.async_setup` against real, mocked entity
states and fired action events, then through M3's real *scheduled* tick -- the real
`async_track_time_interval` registration `__init__.py` sets up, actually fired (not mocked
out, unlike tests/test_init.py's own tick-scheduling suite) -- never by calling
`notification_state.evaluate_prompt` directly (Phase 2's own suite owns that). This proves
the setup wiring (Phases 1-5): real adapters constructed from `entry.data` (ADR-0003), the
real Store write landing as `switch.smart_charging_home_day`'s HA state (ADR-0018), and the
real `NotifyAdapter` tag round-trip through the event bus.

Time control: `homeassistant.helpers.event._TrackTimeInterval._interval_listener` calls
`dt_util.utcnow()` at fire time -- not the value `async_fire_time_changed` patches (that
patch only reaches point-in-time trackers via `time_tracker_utcnow`). But
`pytest_homeassistant_custom_component`'s `patch_time` module replaces `dt_util.utcnow`
itself with a plain function specifically so freezegun's `datetime.now()` patch reaches it
-- so with the `freezer` fixture (pytest-freezer, already used by this project's other
end-to-end suites, e.g. tests/test_deadline_soc_management_end_to_end.py) active, freezing
the clock and firing `async_fire_time_changed` DOES deliver the frozen instant to the real
timer. `_tick` below freezes first, then fires the real scheduled callback -- both are
needed, since only the freeze controls the timestamp the callback ultimately reads.

The scenario date is pinned in the past (matching the sibling end-to-end suite's own
discipline) so the suite's very first `freezer.move_to` call, made before `_setup` runs,
never has to jump backward past the real "now" the entry's timer was registered against --
a forward jump only, avoiding any dependency on real wall-clock timing.
"""

from datetime import datetime, timedelta

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.smart_charging.adapters.notify import (
    EVENT_MOBILE_APP_NOTIFICATION_ACTION,
)
from custom_components.smart_charging.const import (
    ACTION_HOMEDAY_NO,
    ACTION_HOMEDAY_YES,
    CONF_EVENING_PROMPT_ENABLED,
    CONF_EVENING_PROMPT_TIME,
    CONF_HOME_DAY_EXTERNAL_ENTITY,
    CONF_NOTIFICATION_TARGET_ENTITY,
    CONF_SOLAR_FORECAST_ENTITY,
    CONF_SOLAR_FORECAST_THRESHOLD_KWH,
    CONF_STATUS_TRANSLATION,
    DOMAIN,
    STATE_CONNECTED,
    STATE_DISCONNECTED,
)
from tests.helpers import entry_data_base, entry_options_base, seed_charger_states

# Deliberately non-default (const.py's DEFAULT_EVENING_PROMPT_TIME/DEFAULT_SOLAR_FORECAST_
# THRESHOLD_KWH are "18:00:00"/12.0) -- an implementation that dropped __init__.py's
# option-threading entirely would still pass against the defaults.
PROMPT_TIME = "19:15:00"
FORECAST_THRESHOLD_KWH = 15.0

_NOTIFY_TARGET = "notify.mobile_app_phone"
_SOLAR_FORECAST_ENTITY_ID = "sensor.solar_forecast"
_HOME_DAY_EXTERNAL_ENTITY_ID = "input_boolean.home_day_external"
_HOME_DAY_ENTITY_ID = "switch.smart_charging_home_day"

# A fixed evening well in the past relative to any real test-run date -- see module
# docstring. BEFORE_PROMPT is where the entry's timer starts (safely ahead of its own
# 10s-later first schedule); EVENING is after PROMPT_TIME, still before midnight.
BEFORE_PROMPT = datetime(2026, 1, 17, 12, 0, 0)
EVENING = datetime(2026, 1, 17, 19, 30, 0)
MIDNIGHT_NEXT_DAY = datetime(2026, 1, 18, 0, 0, 0)


def _entry_data(**overrides):
    data = entry_data_base(
        **{
            CONF_NOTIFICATION_TARGET_ENTITY: _NOTIFY_TARGET,
            CONF_SOLAR_FORECAST_ENTITY: _SOLAR_FORECAST_ENTITY_ID,
            CONF_HOME_DAY_EXTERNAL_ENTITY: _HOME_DAY_EXTERNAL_ENTITY_ID,
        }
    )
    data.update(overrides)
    return data


def _entry_options(**overrides):
    options = entry_options_base(
        **{
            CONF_EVENING_PROMPT_ENABLED: True,
            CONF_EVENING_PROMPT_TIME: PROMPT_TIME,
            CONF_SOLAR_FORECAST_THRESHOLD_KWH: FORECAST_THRESHOLD_KWH,
        }
    )
    options.update(overrides)
    return options


async def _setup(hass, freezer, *, data_overrides=None, option_overrides=None):
    freezer.move_to(dt_util.as_utc(BEFORE_PROMPT))
    seed_charger_states(hass, status="Charging")
    hass.states.async_set(_SOLAR_FORECAST_ENTITY_ID, "20.0")
    hass.states.async_set(_HOME_DAY_EXTERNAL_ENTITY_ID, STATE_OFF)

    entry = MockConfigEntry(
        domain=DOMAIN,
        data=_entry_data(**(data_overrides or {})),
        options=_entry_options(**(option_overrides or {})),
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _register_notify_capture(hass):
    calls = []

    async def _record(call):
        calls.append(call.data)

    hass.services.async_register("notify", "send_message", _record)
    return calls


async def _tick(hass, freezer, local_time):
    """Freeze the real clock at `local_time` (naive, this HA test harness's configured
    local zone -- US/Pacific) and fire the real, already-scheduled evaluation tick -- see
    module docstring for why both steps are needed."""
    freezer.move_to(dt_util.as_utc(local_time))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


async def test_e2e_uc08_main_success_prompt_then_yes_sets_flag(hass, freezer):
    """UC08 main success scenario: the trigger holds -> one actionable prompt, addressed to
    the configured notification target -> a "yes" response -> the flag turns on."""
    calls = _register_notify_capture(hass)
    await _setup(hass, freezer)

    await _tick(hass, freezer, EVENING)
    assert len(calls) == 1
    assert calls[0]["entity_id"] == _NOTIFY_TARGET
    tag = calls[0]["data"]["tag"]
    assert hass.states.get(_HOME_DAY_ENTITY_ID).state == STATE_OFF

    hass.bus.async_fire(
        EVENT_MOBILE_APP_NOTIFICATION_ACTION, {"tag": tag, "action": ACTION_HOMEDAY_YES}
    )
    await hass.async_block_till_done()
    await _tick(hass, freezer, EVENING + timedelta(minutes=5))

    assert hass.states.get(_HOME_DAY_ENTITY_ID).state == STATE_ON


async def test_e2e_uc08_no_response_leaves_flag_unset(hass, freezer):
    """UC08 alternate flow 3a: a "no" response leaves the flag unset."""
    calls = _register_notify_capture(hass)
    await _setup(hass, freezer)

    await _tick(hass, freezer, EVENING)
    tag = calls[0]["data"]["tag"]

    hass.bus.async_fire(
        EVENT_MOBILE_APP_NOTIFICATION_ACTION, {"tag": tag, "action": ACTION_HOMEDAY_NO}
    )
    await hass.async_block_till_done()
    await _tick(hass, freezer, EVENING + timedelta(minutes=5))

    assert hass.states.get(_HOME_DAY_ENTITY_ID).state == STATE_OFF


async def test_e2e_uc08_timeout_at_midnight_leaves_flag_unset(hass, freezer):
    """UC08 exception flow: midnight rollover with a Pending prompt and no answer times out,
    leaving the flag unset -- and a late answer for the now-stale tag is not adopted."""
    calls = _register_notify_capture(hass)
    await _setup(hass, freezer)

    await _tick(hass, freezer, EVENING)
    assert len(calls) == 1
    tag = calls[0]["data"]["tag"]

    await _tick(hass, freezer, MIDNIGHT_NEXT_DAY)
    assert len(calls) == 1  # no re-prompt just from the rollover tick itself
    assert hass.states.get(_HOME_DAY_ENTITY_ID).state == STATE_OFF

    hass.bus.async_fire(
        EVENT_MOBILE_APP_NOTIFICATION_ACTION, {"tag": tag, "action": ACTION_HOMEDAY_YES}
    )
    await hass.async_block_till_done()
    await _tick(hass, freezer, MIDNIGHT_NEXT_DAY + timedelta(minutes=1))

    assert hass.states.get(_HOME_DAY_ENTITY_ID).state == STATE_OFF


async def test_e2e_uc08_skips_when_prompt_disabled(hass, freezer):
    """UC08 1a: the evening-prompt option is disabled -> no send, even though every other
    precondition holds (a positive control confirms this in test 1's own default setup)."""
    calls = _register_notify_capture(hass)
    await _setup(hass, freezer, option_overrides={CONF_EVENING_PROMPT_ENABLED: False})

    await _tick(hass, freezer, EVENING)

    assert calls == []


async def test_e2e_uc08_skips_when_forecast_below_threshold(hass, freezer):
    """UC08 1b: the solar forecast doesn't exceed the configured threshold -> no send --
    and re-evaluated, not latched: raising the forecast on a later tick still sends."""
    calls = _register_notify_capture(hass)
    await _setup(hass, freezer)
    hass.states.async_set(_SOLAR_FORECAST_ENTITY_ID, "5.0")  # below the 15.0 kWh threshold

    await _tick(hass, freezer, EVENING)
    assert calls == []

    hass.states.async_set(_SOLAR_FORECAST_ENTITY_ID, "20.0")
    await _tick(hass, freezer, EVENING + timedelta(minutes=5))
    assert len(calls) == 1


async def test_e2e_uc08_skips_when_external_source_already_set_flag(hass, freezer):
    """UC08 1a: an external home-day source has already set the flag -> no send -- and
    re-evaluated, not latched: the source clearing on a later tick still sends."""
    calls = _register_notify_capture(hass)
    await _setup(hass, freezer)
    hass.states.async_set(_HOME_DAY_EXTERNAL_ENTITY_ID, STATE_ON)

    await _tick(hass, freezer, EVENING)
    assert calls == []

    hass.states.async_set(_HOME_DAY_EXTERNAL_ENTITY_ID, STATE_OFF)
    await _tick(hass, freezer, EVENING + timedelta(minutes=5))
    assert len(calls) == 1


async def test_e2e_uc08_stays_not_sent_when_car_never_connects(hass, freezer):
    """UC08 1c: the car never connects (charger_status translates to disconnected, not one
    of CHARGEABLE_STATES) before midnight -> no send, stays Not-sent through the evening."""
    calls = _register_notify_capture(hass)
    translation = {"Charging": STATE_CONNECTED, "Idle": STATE_DISCONNECTED}
    await _setup(hass, freezer, data_overrides={CONF_STATUS_TRANSLATION: translation})
    hass.states.async_set("sensor.evse", "Idle")  # translates to STATE_DISCONNECTED

    await _tick(hass, freezer, EVENING)
    await _tick(hass, freezer, MIDNIGHT_NEXT_DAY)

    assert calls == []
    assert hass.states.get(_HOME_DAY_ENTITY_ID).state == STATE_OFF
