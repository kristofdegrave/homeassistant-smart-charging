"""HA-harness tests for the notify adapter (RA4 -- ADR-0003 role extension, ADR-0009).

Anchors: notifications design doc §6 (adapter mechanics), success criteria 1-2.
"""

from custom_components.smart_charging.adapters.notify import (
    EVENT_MOBILE_APP_NOTIFICATION_ACTION,
    NotificationRequest,
    NotifyAdapter,
)
from custom_components.smart_charging.const import ACTION_HOMEDAY_NO, ACTION_HOMEDAY_YES


def _register_capture(hass):
    calls = []

    async def _record(call):
        calls.append(call.data)

    hass.services.async_register("notify", "send_message", _record)
    return calls


async def test_write_sends_message_and_title_to_the_mapped_notify_entity(hass):
    calls = _register_capture(hass)
    adapter = NotifyAdapter(hass, "notify.mobile_app_phone")

    await adapter.write(NotificationRequest(message="Deadline unreachable", title="Smart Charging"))
    await hass.async_block_till_done()

    assert len(calls) == 1
    assert calls[0]["entity_id"] == "notify.mobile_app_phone"
    assert calls[0]["message"] == "Deadline unreachable"
    assert calls[0]["title"] == "Smart Charging"


async def test_write_includes_action_buttons_when_payload_is_actionable(hass):
    calls = _register_capture(hass)
    adapter = NotifyAdapter(hass, "notify.mobile_app_phone")

    await adapter.write(
        NotificationRequest(
            message="Home tomorrow?",
            title="Smart Charging",
            actions=[ACTION_HOMEDAY_YES, ACTION_HOMEDAY_NO],
        )
    )
    await hass.async_block_till_done()

    assert len(calls) == 1
    action_ids = {a["action"] for a in calls[0]["data"]["actions"]}
    assert action_ids == {ACTION_HOMEDAY_YES, ACTION_HOMEDAY_NO}
    assert calls[0]["data"]["tag"]  # a unique tag was stamped


async def test_read_returns_the_action_for_the_current_tag(hass):
    calls = _register_capture(hass)
    adapter = NotifyAdapter(hass, "notify.mobile_app_phone")

    await adapter.write(
        NotificationRequest(
            message="Home tomorrow?", actions=[ACTION_HOMEDAY_YES, ACTION_HOMEDAY_NO]
        )
    )
    await hass.async_block_till_done()
    current_tag = calls[0]["data"]["tag"]

    hass.bus.async_fire(
        EVENT_MOBILE_APP_NOTIFICATION_ACTION, {"tag": current_tag, "action": ACTION_HOMEDAY_YES}
    )
    await hass.async_block_till_done()

    assert await adapter.read() == ACTION_HOMEDAY_YES


async def test_read_ignores_a_stale_tag_response(hass):
    calls = _register_capture(hass)
    adapter = NotifyAdapter(hass, "notify.mobile_app_phone")

    # First (stale) actionable send.
    await adapter.write(
        NotificationRequest(
            message="Home tomorrow?", actions=[ACTION_HOMEDAY_YES, ACTION_HOMEDAY_NO]
        )
    )
    await hass.async_block_till_done()
    stale_tag = calls[0]["data"]["tag"]

    # Second (current) actionable send supersedes the first.
    await adapter.write(
        NotificationRequest(
            message="Home tomorrow?", actions=[ACTION_HOMEDAY_YES, ACTION_HOMEDAY_NO]
        )
    )
    await hass.async_block_till_done()

    # A response carrying the superseded (stale) tag arrives.
    hass.bus.async_fire(
        EVENT_MOBILE_APP_NOTIFICATION_ACTION, {"tag": stale_tag, "action": ACTION_HOMEDAY_YES}
    )
    await hass.async_block_till_done()

    assert await adapter.read() is None


async def test_read_is_none_before_any_response(hass):
    adapter = NotifyAdapter(hass, "notify.mobile_app_phone")
    assert await adapter.read() is None


async def test_write_omits_data_and_tag_when_payload_is_not_actionable(hass):
    calls = _register_capture(hass)
    adapter = NotifyAdapter(hass, "notify.mobile_app_phone")

    await adapter.write(NotificationRequest(message="Deadline unreachable", title="Smart Charging"))
    await hass.async_block_till_done()

    assert "data" not in calls[0]


async def test_read_is_none_after_a_non_actionable_write(hass):
    _register_capture(hass)
    adapter = NotifyAdapter(hass, "notify.mobile_app_phone")

    await adapter.write(NotificationRequest(message="Deadline unreachable"))
    await hass.async_block_till_done()

    assert await adapter.read() is None


async def test_registers_the_action_listener_exactly_once(hass):
    _register_capture(hass)
    baseline = hass.bus.async_listeners().get(EVENT_MOBILE_APP_NOTIFICATION_ACTION, 0)

    adapter = NotifyAdapter(hass, "notify.mobile_app_phone")
    for _ in range(3):
        await adapter.write(
            NotificationRequest(
                message="Home tomorrow?", actions=[ACTION_HOMEDAY_YES, ACTION_HOMEDAY_NO]
            )
        )
    await hass.async_block_till_done()

    # One listener registered at construction; repeated write() calls do not add more.
    after = hass.bus.async_listeners().get(EVENT_MOBILE_APP_NOTIFICATION_ACTION, 0)
    assert after - baseline == 1
