"""Notify adapter: send + tag-keyed response capture (RA4, V11, ADR-0003 role extension).

No new ADR (design doc §6) -- the same shape RA2/RA3 already extend: one class per role,
config-flow entity mapping, `ROLE_*` constant, factory wiring.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from homeassistant.core import Event, HomeAssistant, callback

# HA's standard mobile-app action event (human-partner decision 2, design doc §6) -- fired
# when the user taps an action button on an actionable notification.
EVENT_MOBILE_APP_NOTIFICATION_ACTION = "mobile_app_notification_action"

# Shared "tag"/"action" key names: HA uses the same field names in both the
# notify.send_message actionable-notification service-call data and the resulting
# mobile_app_notification_action event's payload, so one pair of constants covers both.
_DATA_KEY_TAG = "tag"
_DATA_KEY_ACTION = "action"
_DATA_KEY_ACTIONS = "actions"
_DATA_KEY_TITLE = "title"


@dataclass
class NotificationRequest:
    """RA4 write payload (design doc §6).

    `message`/`title` reach `notify.send_message` unchanged. `actions`, when given, are the
    action ids (e.g. `ACTION_HOMEDAY_YES`/`ACTION_HOMEDAY_NO`) HA renders as tappable
    buttons; a tap fires `EVENT_MOBILE_APP_NOTIFICATION_ACTION` carrying the tag stamped by
    `NotifyAdapter.write` below -- callers never set a tag themselves.
    """

    message: str
    title: str | None = None
    actions: list[str] | None = None


class NotifyAdapter:
    """RA4 (V11): sends notify messages and captures the tag-keyed action response.

    Reuses the ADR-0003 `Adapter` protocol as a role extension (design doc §6): the
    shared `Adapter.write` value is typed `float | str | bool | time` today; this role's
    payload is the small structured `NotificationRequest` instead, so in practice the
    contract this adapter satisfies is `float | str | bool | time | NotificationRequest`
    -- a one-line typing widening, not a structural change; no new ADR.
    """

    def __init__(self, hass: HomeAssistant, entity_id: str) -> None:
        self._hass = hass
        self._entity_id = entity_id
        self._current_tag: str | None = None
        self._last_action: str | None = None
        # Stored so a future teardown (Task 5.2) can unsubscribe; this task does not call it.
        self._unsub = hass.bus.async_listen(
            EVENT_MOBILE_APP_NOTIFICATION_ACTION, self._handle_action
        )

    @callback
    def _handle_action(self, event: Event) -> None:
        """Record the action id, but only for the current actionable tag.

        `mobile_app_notification_action` is HA's shared, integration-wide event -- a
        foreign action (from some other actionable notification) can fire after the
        user's real answer. Filtering here, not just in read(), stops a later foreign
        event from ever overwriting a genuine answer already captured for the current
        tag (the stale-response guard, design doc §6 / success criterion 2).
        """
        tag = event.data.get(_DATA_KEY_TAG)
        action = event.data.get(_DATA_KEY_ACTION)
        if tag is None or action is None or tag != self._current_tag:
            return
        self._last_action = action

    async def write(self, value: NotificationRequest) -> None:
        service_data: dict = {"entity_id": self._entity_id, "message": value.message}
        if value.title is not None:
            service_data[_DATA_KEY_TITLE] = value.title
        if value.actions:
            self._current_tag = uuid.uuid4().hex
            self._last_action = None
            service_data["data"] = {
                _DATA_KEY_TAG: self._current_tag,
                _DATA_KEY_ACTIONS: [
                    {_DATA_KEY_ACTION: action, _DATA_KEY_TITLE: action} for action in value.actions
                ],
            }
        await self._hass.services.async_call("notify", "send_message", service_data, blocking=True)

    async def read(self) -> str | None:
        """Return the action captured for the current actionable tag, else None.

        The stale-response guard (design doc §6 / success criterion 2): a response
        tagged to a superseded notification -- filtered out in _handle_action, so it
        never reaches here -- or no response yet, returns None, never a stale value.
        """
        return self._last_action
