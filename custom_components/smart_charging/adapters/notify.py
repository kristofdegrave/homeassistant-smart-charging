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

    Reuses the ADR-0003 `Adapter` protocol. The shared `Adapter.write` value annotation
    widens to `float | str | NotificationRequest` for this role only (design doc §6) --
    a one-line typing detail, not a structural change; no new ADR.
    """

    def __init__(self, hass: HomeAssistant, entity_id: str) -> None:
        self._hass = hass
        self._entity_id = entity_id
        self._current_tag: str | None = None
        self._last_response: tuple[str, str] | None = None  # (tag, action_id)
        hass.bus.async_listen(EVENT_MOBILE_APP_NOTIFICATION_ACTION, self._handle_action)

    @callback
    def _handle_action(self, event: Event) -> None:
        """Record every incoming (tag, action_id); the stale-tag guard lives in read()."""
        tag = event.data.get("tag")
        action = event.data.get("action")
        if tag is None or action is None:
            return
        self._last_response = (tag, action)

    async def write(self, value: NotificationRequest) -> None:
        service_data: dict = {"entity_id": self._entity_id, "message": value.message}
        if value.title is not None:
            service_data["title"] = value.title
        if value.actions:
            tag = uuid.uuid4().hex
            self._current_tag = tag
            service_data["data"] = {
                "tag": tag,
                "actions": [{"action": action, "title": action} for action in value.actions],
            }
        await self._hass.services.async_call("notify", "send_message", service_data, blocking=True)

    async def read(self) -> str | None:
        """Return the last captured action id, only if its tag matches the current send.

        The stale-response guard (design doc §6 / success criterion 2): a response tagged
        to a superseded notification -- or no response yet -- returns None, never a stale
        value.
        """
        if self._last_response is None or self._current_tag is None:
            return None
        tag, action_id = self._last_response
        if tag != self._current_tag:
            return None
        return action_id
