"""Notify adapter: send + tag-keyed response capture (RA4, V11, ADR-0003 role extension).

No new ADR (design doc §6) -- the same shape RA2/RA3 already extend: one class per role,
config-flow entity mapping, `ROLE_*` constant, factory wiring.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from homeassistant.components.notify import (
    ATTR_DATA,
    ATTR_MESSAGE,
    ATTR_TITLE,
    SERVICE_SEND_MESSAGE,
)
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import Event, HomeAssistant, callback

# HA's standard mobile-app action event (human-partner decision 2, design doc §6) -- fired
# when the user taps an action button on an actionable notification.
EVENT_MOBILE_APP_NOTIFICATION_ACTION = "mobile_app_notification_action"

# Shared "tag"/"action" key names: HA uses the same field names in both the
# notify.send_message actionable-notification service-call data and the resulting
# mobile_app_notification_action event's payload, so one pair of constants covers both.
# These are mobile_app-specific (not defined in homeassistant.components.notify), unlike
# the top-level "message"/"title"/"data" fields above, which use HA's own ATTR_* constants.
_DATA_KEY_TAG = "tag"
_DATA_KEY_ACTION = "action"
_DATA_KEY_ACTIONS = "actions"
# The per-action button label (mobile_app's own "title" field on each action dict) is a
# distinct schema from the top-level notification title (ATTR_TITLE below) even though HA
# happens to spell both "title" -- kept as its own constant so the two never get conflated.
_ACTION_BUTTON_LABEL_KEY = "title"


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
        # Unsubscribed via close() -- the factory's owner calls it on config-entry unload,
        # so a reload doesn't leave a dangling bus listener behind.
        self._unsub = hass.bus.async_listen(
            EVENT_MOBILE_APP_NOTIFICATION_ACTION, self._handle_action
        )

    def close(self) -> None:
        """Unsubscribe the action-event listener, preventing a dangling bus listener on reload."""
        self._unsub()

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
        service_data: dict = {ATTR_ENTITY_ID: self._entity_id, ATTR_MESSAGE: value.message}
        if value.title is not None:
            service_data[ATTR_TITLE] = value.title
        if value.actions:
            self._current_tag = uuid.uuid4().hex
            self._last_action = None
            service_data[ATTR_DATA] = {
                _DATA_KEY_TAG: self._current_tag,
                _DATA_KEY_ACTIONS: [
                    {_DATA_KEY_ACTION: action, _ACTION_BUTTON_LABEL_KEY: action}
                    for action in value.actions
                ],
            }
        # A non-actionable send (e.g. the R5 deadline-unreachable notice) does not supersede
        # a still-outstanding actionable prompt -- clearing `_current_tag`
        # here would make `_handle_action` drop a genuine answer that arrives for the prompt
        # still in flight. `_current_tag`/`_last_action` are therefore only ever reset by a
        # *new actionable* write (above) or consumed by `read()` (below).
        await self._hass.services.async_call(
            Platform.NOTIFY, SERVICE_SEND_MESSAGE, service_data, blocking=True
        )

    async def read(self) -> str | None:
        """Return the action captured for the current actionable tag, else None.

        The stale-response guard (design doc §6 / success criterion 2): a response
        tagged to a superseded notification -- filtered out in _handle_action, so it
        never reaches here -- or no response yet, returns None, never a stale value.

        The returned answer is consumed: once read, it is cleared so it
        is valid for exactly one read() of its own tag/prompt cycle, not replayed on
        every subsequent call. This narrows design doc §4/§6's "returns the last captured
        actionable response" to "returns it once" -- a deliberate deviation from the
        design doc, not yet reflected back into it; `managers/notification_manager.py`
        calls `read()` exactly once per resolved prompt-state transition, not polling it
        speculatively.
        """
        action = self._last_action
        self._last_action = None
        return action
