"""End-to-end HA-harness regression for UC08 (R13), setup-to-teardown.

Every test is driven through `hass.config_entries.async_setup` against real, mocked entity
states and fired action events, then triggers M3's real scheduled tick method
(`NotificationManager.async_evaluate`, retrieved from `hass.data` the same way Task 5.1's
Vehicle-Limit Manager is) -- never by calling `notification_state.evaluate_prompt` directly
(Phase 2's own suite owns that). This suite proves the setup-to-teardown wiring (Phases 1-5):
real adapters, the real Store, the real switch entity, the real `NotifyAdapter` tag-keyed
capture -- not whether `async_track_time_interval` itself schedules correctly (tests/
test_init.py's own tick-scheduling suite already owns that).

Time control: `async_track_time_interval`'s internal `_interval_listener` calls the real
`dt_util.utcnow()` at fire time (not the value `async_fire_time_changed` patches -- that
patch only reaches point-in-time trackers), so firing the real timer cannot pin a UC08
scenario to a specific evening. Instead, the `freezer` fixture (pytest-freezer, already used
by this project's other end-to-end suites, e.g. tests/test_deadline_soc_management_end_to_end.py)
freezes the real clock so `dt_util.now()` reads as the desired local moment, and the tick
method is invoked directly (still the real Manager instance from real setup, not a stub).
"""

from datetime import datetime, timedelta

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
    DATA_NOTIFICATION_MANAGER,
    DOMAIN,
)
from tests.helpers import entry_data_base, entry_options_base, seed_charger_states

PROMPT_TIME = "18:00:00"
# Naive local wall-clock times (this project's config's DEFAULT_TIME_ZONE, US/Pacific in the
# HA test harness) -- converted to UTC before freezing, since freezegun's naive move_to()
# interprets a naive value as UTC, not local.
EVENING = datetime(2026, 8, 9, 18, 30, 0)  # a Sunday, well after PROMPT_TIME, before midnight
MIDNIGHT_NEXT_DAY = datetime(2026, 8, 10, 0, 0, 0)

_HOME_DAY_ENTITY_ID = "switch.smart_charging_home_day"


def _entry_data(**overrides):
    data = entry_data_base(
        **{
            CONF_NOTIFICATION_TARGET_ENTITY: "notify.mobile_app_phone",
            CONF_SOLAR_FORECAST_ENTITY: "sensor.solar_forecast",
            CONF_HOME_DAY_EXTERNAL_ENTITY: "input_boolean.home_day_external",
        }
    )
    data.update(overrides)
    return data


def _entry_options(**overrides):
    options = entry_options_base(
        **{
            CONF_EVENING_PROMPT_ENABLED: True,
            CONF_EVENING_PROMPT_TIME: PROMPT_TIME,
            CONF_SOLAR_FORECAST_THRESHOLD_KWH: 12.0,
        }
    )
    options.update(overrides)
    return options


async def _setup(hass, *, data_overrides=None, option_overrides=None):
    seed_charger_states(hass, status="Charging")
    hass.states.async_set("sensor.solar_forecast", "20.0")
    hass.states.async_set("input_boolean.home_day_external", "off")

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


async def _tick(hass, entry, freezer, local_time):
    """Freeze the real clock at `local_time` (naive, this project's configured local zone)
    and run M3's real tick method directly -- see module docstring for why the tick can't be
    driven through the real async_track_time_interval scheduler here."""
    freezer.move_to(dt_util.as_utc(local_time))
    manager = hass.data[DOMAIN][entry.entry_id][DATA_NOTIFICATION_MANAGER]
    await manager.async_evaluate()
    await hass.async_block_till_done()


async def test_e2e_uc08_main_success_prompt_then_yes_sets_flag(hass, freezer):
    """UC08 main success scenario: the trigger holds -> one actionable prompt -> a "yes"
    response -> switch.smart_charging_home_day turns on."""
    calls = _register_notify_capture(hass)
    entry = await _setup(hass)

    await _tick(hass, entry, freezer, EVENING)
    assert len(calls) == 1
    tag = calls[0]["data"]["tag"]
    assert hass.states.get(_HOME_DAY_ENTITY_ID).state == "off"

    hass.bus.async_fire(
        EVENT_MOBILE_APP_NOTIFICATION_ACTION, {"tag": tag, "action": ACTION_HOMEDAY_YES}
    )
    await hass.async_block_till_done()
    await _tick(hass, entry, freezer, EVENING + timedelta(minutes=5))

    assert hass.states.get(_HOME_DAY_ENTITY_ID).state == "on"


async def test_e2e_uc08_no_response_leaves_flag_unset(hass, freezer):
    """UC08 alternate flow 3a: a "no" response leaves the flag unset."""
    calls = _register_notify_capture(hass)
    entry = await _setup(hass)

    await _tick(hass, entry, freezer, EVENING)
    tag = calls[0]["data"]["tag"]

    hass.bus.async_fire(
        EVENT_MOBILE_APP_NOTIFICATION_ACTION, {"tag": tag, "action": ACTION_HOMEDAY_NO}
    )
    await hass.async_block_till_done()
    await _tick(hass, entry, freezer, EVENING + timedelta(minutes=5))

    assert hass.states.get(_HOME_DAY_ENTITY_ID).state == "off"


async def test_e2e_uc08_timeout_at_midnight_leaves_flag_unset(hass, freezer):
    """UC08 exception flow: midnight rollover with a Pending prompt and no answer times out,
    leaving the flag unset."""
    _register_notify_capture(hass)
    entry = await _setup(hass)

    await _tick(hass, entry, freezer, EVENING)
    assert hass.states.get(_HOME_DAY_ENTITY_ID).state == "off"

    await _tick(hass, entry, freezer, MIDNIGHT_NEXT_DAY)
    assert hass.states.get(_HOME_DAY_ENTITY_ID).state == "off"


async def test_e2e_uc08_skips_when_prompt_disabled(hass, freezer):
    """UC08 1a: the evening-prompt option is disabled -> no send."""
    calls = _register_notify_capture(hass)
    entry = await _setup(hass, option_overrides={CONF_EVENING_PROMPT_ENABLED: False})

    await _tick(hass, entry, freezer, EVENING)

    assert calls == []


async def test_e2e_uc08_skips_when_forecast_below_threshold(hass, freezer):
    """UC08 1b: the solar forecast doesn't exceed the configured threshold -> no send."""
    calls = _register_notify_capture(hass)
    entry = await _setup(hass)
    hass.states.async_set("sensor.solar_forecast", "5.0")  # below the 12.0 kWh threshold

    await _tick(hass, entry, freezer, EVENING)

    assert calls == []


async def test_e2e_uc08_skips_when_external_source_already_set_flag(hass, freezer):
    """UC08 1a: an external home-day source has already set the flag -> no send."""
    calls = _register_notify_capture(hass)
    entry = await _setup(hass)
    hass.states.async_set("input_boolean.home_day_external", "on")

    await _tick(hass, entry, freezer, EVENING)

    assert calls == []


async def test_e2e_uc08_stays_not_sent_when_car_never_connects(hass, freezer):
    """UC08 1c: the car never connects (charger_status reads a non-chargeable/untranslated
    state, ADR-0007's fault signal) before midnight -> no send, stays Not-sent through the
    whole evening."""
    calls = _register_notify_capture(hass)
    entry = await _setup(hass)
    hass.states.async_set("sensor.evse", "Idle")  # not in CONF_STATUS_TRANSLATION -> None

    await _tick(hass, entry, freezer, EVENING)
    await _tick(hass, entry, freezer, MIDNIGHT_NEXT_DAY)

    assert calls == []
    assert hass.states.get(_HOME_DAY_ENTITY_ID).state == "off"
