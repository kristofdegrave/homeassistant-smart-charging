"""HA-harness tests for the Notification Manager (M3 -- UC08/ADR-0011/notifications design).

Drives M3 through its public `async_evaluate` tick directly (not HA listener/timer plumbing --
that is Task 5.2's job), against fake RA1/RA2 read adapters + a fake Store (mirroring
tests/managers/test_vehicle_limit.py's doubles) and the real `NotifyAdapter` (RA4) so the
tag-keyed response capture / stale-tag guard is exercised through the genuine mechanism rather
than re-implemented in a test double.

Anchors: docs/analysis/use-cases/UC08-plan-tomorrow-home-day.md (preconditions, trigger, state
model), docs/plans/2026-07-21-notifications-design.md Sec4/Sec5/Sec6/Sec7.
"""

import logging
from datetime import date, datetime, time, timedelta

from homeassistant.const import Platform
from homeassistant.util import dt as dt_util

from custom_components.smart_charging.adapters.notify import (
    EVENT_MOBILE_APP_NOTIFICATION_ACTION,
    NotifyAdapter,
)
from custom_components.smart_charging.const import (
    ACTION_HOMEDAY_NO,
    ACTION_HOMEDAY_YES,
    CONF_EVENING_PROMPT_ENABLED,
    CONF_EVENING_PROMPT_TIME,
    CONF_SOLAR_FORECAST_THRESHOLD_KWH,
    DEFAULT_EVENING_PROMPT_ENABLED,
    DEFAULT_EVENING_PROMPT_TIME,
    DEFAULT_SOLAR_FORECAST_THRESHOLD_KWH,
    OWNED_SUFFIX_HOME_DAY,
    ROLE_CHARGER_STATUS,
    ROLE_HOME_DAY_EXTERNAL,
    ROLE_NOTIFICATION_TARGET,
    ROLE_SOLAR_FORECAST,
    STATE_CHARGING,
    STATE_CONNECTED,
    STATE_DISCONNECTED,
)
from custom_components.smart_charging.managers.notification_manager import NotificationManager
from custom_components.smart_charging.notification_state import PromptState

PROMPT_TIME = time(18, 0, 0)
EVENING = datetime(2026, 8, 9, 18, 30, 0)  # a Sunday, well after PROMPT_TIME, before midnight
MIDNIGHT_NEXT_DAY = datetime(2026, 8, 10, 0, 0, 0)


class _ReadAdapter:
    def __init__(self, value):
        self.value = value

    async def read(self):
        return self.value


class _FakeStore:
    """Mirrors tests/managers/test_vehicle_limit.py's double -- records write() calls."""

    def __init__(self):
        self.writes = []

    async def write(self, entity_domain, unique_id_suffix, value):
        self.writes.append((entity_domain, unique_id_suffix, value))
        return True


def _register_notify_capture(hass):
    calls = []

    async def _record(call):
        calls.append(call.data)

    hass.services.async_register("notify", "send_message", _record)
    return calls


def _config(**overrides):
    config = {
        CONF_EVENING_PROMPT_ENABLED: True,
        CONF_EVENING_PROMPT_TIME: PROMPT_TIME.isoformat(),
        CONF_SOLAR_FORECAST_THRESHOLD_KWH: 12.0,
    }
    config.update(overrides)
    return config


def _manager(
    hass,
    *,
    store=None,
    forecast_kwh=20.0,
    home_day_external=False,
    status=STATE_CONNECTED,
    config=None,
    notify_adapter=None,
):
    adapters = {
        ROLE_SOLAR_FORECAST: _ReadAdapter(forecast_kwh),
        ROLE_HOME_DAY_EXTERNAL: _ReadAdapter(home_day_external),
        ROLE_CHARGER_STATUS: _ReadAdapter(status),
        ROLE_NOTIFICATION_TARGET: notify_adapter or NotifyAdapter(hass, "notify.mobile_app_phone"),
    }
    return NotificationManager(
        hass,
        adapters=adapters,
        entry_id="entry1",
        store=store or _FakeStore(),
        config=config or _config(),
    )


async def test_sends_actionable_prompt_when_uc08_trigger_holds(hass):
    """UC08 main success scenario steps 1-2: enabled + forecast > threshold + no external
    flag + connected at home at/after prompt time, before midnight -> one actionable
    yes/no notify send (Not-sent -> Pending, HomeDayPromptSent)."""
    calls = _register_notify_capture(hass)
    manager = _manager(hass)

    await manager.async_evaluate(EVENING)
    await hass.async_block_till_done()

    assert len(calls) == 1
    action_ids = {a["action"] for a in calls[0]["data"]["actions"]}
    assert action_ids == {ACTION_HOMEDAY_YES, ACTION_HOMEDAY_NO}
    assert manager._state is PromptState.PENDING


async def test_yes_response_writes_home_day_flag(hass):
    """UC08 main success scenario steps 3-4: RA4 read() returns HOMEDAY_YES (tag-matched)
    before midnight -> writes switch.smart_charging_home_day on through the Store
    (Pending -> Answered-yes, HomeDaySet)."""
    calls = _register_notify_capture(hass)
    store = _FakeStore()
    manager = _manager(hass, store=store)

    await manager.async_evaluate(EVENING)
    await hass.async_block_till_done()
    tag = calls[0]["data"]["tag"]

    hass.bus.async_fire(
        EVENT_MOBILE_APP_NOTIFICATION_ACTION, {"tag": tag, "action": ACTION_HOMEDAY_YES}
    )
    await hass.async_block_till_done()

    await manager.async_evaluate(EVENING + timedelta(minutes=5))
    await hass.async_block_till_done()

    assert store.writes == [(Platform.SWITCH, OWNED_SUFFIX_HOME_DAY, True)]
    assert manager._state is PromptState.ANSWERED_YES


async def test_no_response_leaves_flag_unset(hass):
    """UC08 alternate flow 3a: HOMEDAY_NO -> flag stays unset (Answered-no,
    HomeDayPromptDeclined)."""
    calls = _register_notify_capture(hass)
    store = _FakeStore()
    manager = _manager(hass, store=store)

    await manager.async_evaluate(EVENING)
    await hass.async_block_till_done()
    tag = calls[0]["data"]["tag"]

    hass.bus.async_fire(
        EVENT_MOBILE_APP_NOTIFICATION_ACTION, {"tag": tag, "action": ACTION_HOMEDAY_NO}
    )
    await hass.async_block_till_done()

    await manager.async_evaluate(EVENING + timedelta(minutes=5))

    assert store.writes == []
    assert manager._state is PromptState.ANSWERED_NO


async def test_midnight_without_answer_times_out_and_leaves_flag_unset(hass):
    """UC08 exception flow: midnight rollover with a Pending prompt and no answer ->
    Timed-out, flag unset (HomeDayPromptTimedOut); the lifecycle re-arms to Not-sent on
    the following tick (notification_state.py's finalize-then-rearm sequencing)."""
    _register_notify_capture(hass)
    store = _FakeStore()
    manager = _manager(hass, store=store)

    await manager.async_evaluate(EVENING)
    assert manager._state is PromptState.PENDING

    await manager.async_evaluate(MIDNIGHT_NEXT_DAY)
    assert manager._state is PromptState.TIMED_OUT
    assert store.writes == []

    # Re-arm on the following tick, same evening's date has now rolled over.
    await manager.async_evaluate(MIDNIGHT_NEXT_DAY + timedelta(minutes=1))
    assert manager._state is PromptState.NOT_SENT
    assert manager._date == date(2026, 8, 10)


async def test_skips_prompt_on_uc08_1a_1b_1c(hass):
    """UC08 1a/1b/1c: disabled, forecast <= threshold, external flag already set, or the
    car never connects before midnight -> no send, stays Not-sent."""
    disabled = _register_notify_capture(hass)
    manager = _manager(hass, config=_config(**{CONF_EVENING_PROMPT_ENABLED: False}))
    await manager.async_evaluate(EVENING)
    assert disabled == []
    assert manager._state is PromptState.NOT_SENT

    low_forecast_calls = _register_notify_capture(hass)
    manager = _manager(hass, forecast_kwh=5.0)
    await manager.async_evaluate(EVENING)
    assert low_forecast_calls == []
    assert manager._state is PromptState.NOT_SENT

    external_calls = _register_notify_capture(hass)
    manager = _manager(hass, home_day_external=True)
    await manager.async_evaluate(EVENING)
    assert external_calls == []
    assert manager._state is PromptState.NOT_SENT

    disconnected_calls = _register_notify_capture(hass)
    manager = _manager(hass, status=STATE_DISCONNECTED)
    await manager.async_evaluate(EVENING)
    assert disconnected_calls == []
    assert manager._state is PromptState.NOT_SENT


async def test_connected_while_charging_also_triggers(hass):
    """UC08 trigger: `charger_status` is `connected` OR `charging` -- design §4's sole
    "connected at home" signal."""
    calls = _register_notify_capture(hass)
    manager = _manager(hass, status=STATE_CHARGING)

    await manager.async_evaluate(EVENING)

    assert len(calls) == 1


async def test_stale_prompt_response_is_not_misread(hass):
    """RA4 stale-tag guard (design §6): a prior evening's response tag must not resolve
    tonight's prompt. Exercises the real NotifyAdapter end-to-end through M3 rather than
    re-implementing the tag guard in a test double."""
    calls = _register_notify_capture(hass)
    store = _FakeStore()
    notify_adapter = NotifyAdapter(hass, "notify.mobile_app_phone")
    manager = _manager(hass, store=store, notify_adapter=notify_adapter)

    # Evening 1: prompt sent, times out unanswered at midnight -- its tag becomes stale.
    await manager.async_evaluate(EVENING)
    await hass.async_block_till_done()
    stale_tag = calls[0]["data"]["tag"]
    await manager.async_evaluate(MIDNIGHT_NEXT_DAY)
    await manager.async_evaluate(MIDNIGHT_NEXT_DAY + timedelta(minutes=1))
    assert manager._state is PromptState.NOT_SENT

    # Evening 2: a fresh prompt is sent (new tag).
    evening_2 = EVENING + timedelta(days=1)
    await manager.async_evaluate(evening_2)
    await hass.async_block_till_done()
    assert len(calls) == 2
    current_tag = calls[1]["data"]["tag"]
    assert current_tag != stale_tag

    # A stale response (evening 1's tag) arrives late -- must not resolve evening 2's prompt.
    hass.bus.async_fire(
        EVENT_MOBILE_APP_NOTIFICATION_ACTION, {"tag": stale_tag, "action": ACTION_HOMEDAY_YES}
    )
    await hass.async_block_till_done()
    await manager.async_evaluate(evening_2 + timedelta(minutes=1))
    assert store.writes == []
    assert manager._state is PromptState.PENDING

    # The genuine response for evening 2's own tag resolves it.
    hass.bus.async_fire(
        EVENT_MOBILE_APP_NOTIFICATION_ACTION, {"tag": current_tag, "action": ACTION_HOMEDAY_YES}
    )
    await hass.async_block_till_done()
    await manager.async_evaluate(evening_2 + timedelta(minutes=2))
    assert store.writes == [(Platform.SWITCH, OWNED_SUFFIX_HOME_DAY, True)]
    assert manager._state is PromptState.ANSWERED_YES


async def test_missing_notification_target_adapter_stays_inert(hass):
    """No ROLE_NOTIFICATION_TARGET mapped -- M3 stays inert (mirrors M2's design
    success-criterion 6 analog for a missing required adapter)."""
    manager = NotificationManager(
        hass,
        adapters={
            ROLE_SOLAR_FORECAST: _ReadAdapter(20.0),
            ROLE_HOME_DAY_EXTERNAL: _ReadAdapter(False),
            ROLE_CHARGER_STATUS: _ReadAdapter(STATE_CONNECTED),
        },
        entry_id="entry1",
        store=_FakeStore(),
        config=_config(),
    )
    await manager.async_evaluate(EVENING)
    assert manager._state is PromptState.NOT_SENT


async def test_missing_config_keys_fall_back_to_defaults(hass):
    """Design doc §3: an entry that predates these options keys reads each with its
    DEFAULT_* fallback -- no config-entry migration. A bare dict (no CONF_* keys at all)
    must not raise KeyError at construction."""
    manager = NotificationManager(
        hass,
        adapters={ROLE_NOTIFICATION_TARGET: NotifyAdapter(hass, "notify.mobile_app_phone")},
        entry_id="entry1",
        store=_FakeStore(),
        config={},
    )
    assert manager._enabled == DEFAULT_EVENING_PROMPT_ENABLED
    assert manager._threshold_kwh == DEFAULT_SOLAR_FORECAST_THRESHOLD_KWH
    assert manager._prompt_time == time.fromisoformat(DEFAULT_EVENING_PROMPT_TIME)


async def test_send_failure_does_not_advance_lifecycle_state(hass):
    """A raising notify.send_message (notify entity/integration transiently gone) is
    best-effort, not fatal -- the lifecycle must not advance to Pending for a prompt that
    was never actually delivered, so the next tick retries the send (mirrors
    VehicleLimitManager._write_vehicle's swallow-and-report contract)."""

    class _RaisingNotifyAdapter:
        async def read(self):
            return None

        async def write(self, value):
            raise RuntimeError("notify service unavailable")

    manager = _manager(hass, notify_adapter=_RaisingNotifyAdapter())

    await manager.async_evaluate(EVENING)  # must not raise

    assert manager._state is PromptState.NOT_SENT


async def test_failed_home_day_flag_write_is_logged(hass, caplog):
    """Store.write() returning False after a "yes" answer (e.g. the switch entity is
    transiently unregistered) is logged at warning -- the answer was already consumed by
    RA4's read() and cannot be re-observed on a later tick, so a silent loss would be
    unrecoverable and invisible."""

    class _FailingStore:
        async def write(self, entity_domain, unique_id_suffix, value):
            return False

    calls = _register_notify_capture(hass)
    manager = _manager(hass, store=_FailingStore())
    await manager.async_evaluate(EVENING)
    await hass.async_block_till_done()
    tag = calls[0]["data"]["tag"]

    hass.bus.async_fire(
        EVENT_MOBILE_APP_NOTIFICATION_ACTION, {"tag": tag, "action": ACTION_HOMEDAY_YES}
    )
    await hass.async_block_till_done()

    with caplog.at_level(logging.WARNING):
        await manager.async_evaluate(EVENING + timedelta(minutes=5))

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("home-day flag" in r.message.lower() for r in warnings)
    assert manager._state is PromptState.ANSWERED_YES


async def test_unmapped_solar_forecast_role_stays_not_sent(hass):
    """Fail-closed default (UC08 1b analog): no solar_forecast role mapped at all ->
    treated as 0.0 kWh, never exceeds the threshold, no send."""
    calls = _register_notify_capture(hass)
    manager = NotificationManager(
        hass,
        adapters={
            ROLE_HOME_DAY_EXTERNAL: _ReadAdapter(False),
            ROLE_CHARGER_STATUS: _ReadAdapter(STATE_CONNECTED),
            ROLE_NOTIFICATION_TARGET: NotifyAdapter(hass, "notify.mobile_app_phone"),
        },
        entry_id="entry1",
        store=_FakeStore(),
        config=_config(),
    )

    await manager.async_evaluate(EVENING)

    assert calls == []
    assert manager._state is PromptState.NOT_SENT


async def test_unavailable_solar_forecast_reading_stays_not_sent(hass):
    """Fail-closed default: solar_forecast role mapped but read() returns None (ADR-0003
    fault signal) -> treated as 0.0 kWh, no send."""
    calls = _register_notify_capture(hass)
    manager = _manager(hass, forecast_kwh=None)

    await manager.async_evaluate(EVENING)

    assert calls == []
    assert manager._state is PromptState.NOT_SENT


async def test_unmapped_charger_status_role_stays_not_sent(hass):
    """Fail-closed default: no charger_status role mapped -> connected_at_home is False,
    no send."""
    calls = _register_notify_capture(hass)
    manager = NotificationManager(
        hass,
        adapters={
            ROLE_SOLAR_FORECAST: _ReadAdapter(20.0),
            ROLE_HOME_DAY_EXTERNAL: _ReadAdapter(False),
            ROLE_NOTIFICATION_TARGET: NotifyAdapter(hass, "notify.mobile_app_phone"),
        },
        entry_id="entry1",
        store=_FakeStore(),
        config=_config(),
    )

    await manager.async_evaluate(EVENING)

    assert calls == []
    assert manager._state is PromptState.NOT_SENT


async def test_unavailable_charger_status_reading_stays_not_sent(hass):
    """Fail-closed default: charger_status role mapped but read() returns None -> not
    treated as connected, no send."""
    calls = _register_notify_capture(hass)
    manager = _manager(hass, status=None)

    await manager.async_evaluate(EVENING)

    assert calls == []
    assert manager._state is PromptState.NOT_SENT


async def test_unavailable_home_day_external_reading_sends_normally(hass):
    """Fail-OPEN default (deliberate, unlike the other two roles' fail-closed reads):
    home_day_external is mapped but read() returns None (ADR-0003 fault signal) -> folds
    to False, same as unmapped, so the prompt still sends -- a transient misread must not
    silently skip a genuine evening (design: the driver can always answer "no")."""
    calls = _register_notify_capture(hass)
    manager = _manager(hass, home_day_external=None)

    await manager.async_evaluate(EVENING)

    assert len(calls) == 1


async def test_now_normalizes_a_utc_aware_datetime_to_local_prompt_time(hass):
    """Task 5.2's async_track_time_interval caller hands its callback a UTC-aware
    datetime -- the prompt-time-of-day comparison and midnight rollover are local-clock
    concepts (notification_state.py), so `now` must be normalized to local time, not
    compared against `prompt_time`/the date boundary in UTC."""
    calls = _register_notify_capture(hass)
    manager = _manager(hass)

    # EVENING is naive local wall-clock time (18:30); as_local() attaches HA's configured
    # local zone, as_utc() then converts to the equivalent aware UTC instant -- the same
    # round trip the fix must reverse to compare correctly against PROMPT_TIME/the date.
    utc_now = dt_util.as_utc(dt_util.as_local(EVENING))

    await manager.async_evaluate(utc_now)

    assert len(calls) == 1
    assert manager._state is PromptState.PENDING


async def test_unmapped_home_day_external_role_sends_normally(hass):
    """No home_day_external role mapped at all -> treated as "no external source has set
    the flag" (UC08's own default absent a mechanism), so the prompt still sends when
    every other precondition holds."""
    calls = _register_notify_capture(hass)
    manager = NotificationManager(
        hass,
        adapters={
            ROLE_SOLAR_FORECAST: _ReadAdapter(20.0),
            ROLE_CHARGER_STATUS: _ReadAdapter(STATE_CONNECTED),
            ROLE_NOTIFICATION_TARGET: NotifyAdapter(hass, "notify.mobile_app_phone"),
        },
        entry_id="entry1",
        store=_FakeStore(),
        config=_config(),
    )

    await manager.async_evaluate(EVENING)

    assert len(calls) == 1
