"""Notification Manager (M3, V11) -- UC08 evening home-day prompt orchestration.

A Manager (system-design Sec4 rule 5 / ADR-0011): reads RA1/RA2 adapter roles, sends and
reads back the actionable prompt through RA4 (adapters/notify.py), and writes the
resolved answer through the RA3 Store (ADR-0018) onto switch.smart_charging_home_day.
Decides nothing itself -- notification_state.evaluate_prompt (M3's pure logic, plain
pytest, docs/plans/2026-07-21-notifications-design.md Sec7) is the single source of the
UC08 lifecycle; this module only observes the preconditions/trigger and carries out the
send/write effects that function only signals. This module NEVER calls or is called by
the Coordinator (M1) -- system-design Sec4 rule 5 -- and imports nothing from
coordinator.py.

Per the design doc Sec5: midnight is a per-evaluation wall-clock comparison
(`dt_util.now()` date rollover), driven by the caller's own tick (Task 5.2, not built
here) -- no new HA timer/scheduler primitive. `async_evaluate`'s `now` parameter defaults
to `dt_util.now()` for production callers and is overridable by tests, the same shape
`evaluate_prompt` itself takes explicitly.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime, time
from typing import Any

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .adapters.base import Adapter
from .adapters.notify import NotificationRequest
from .adapters.store import Store
from .const import (
    ACTION_HOMEDAY_NO,
    ACTION_HOMEDAY_YES,
    CHARGEABLE_STATES,
    CONF_EVENING_PROMPT_ENABLED,
    CONF_EVENING_PROMPT_TIME,
    CONF_SOLAR_FORECAST_THRESHOLD_KWH,
    OWNED_SUFFIX_HOME_DAY,
    ROLE_CHARGER_STATUS,
    ROLE_HOME_DAY_EXTERNAL,
    ROLE_NOTIFICATION_TARGET,
    ROLE_SOLAR_FORECAST,
)
from .notification_state import PromptState, evaluate_prompt

_LOGGER = logging.getLogger(__name__)

# UC08 main success scenario step 2's actionable prompt text -- no analysis doc catalogues an
# exact wording, so it is this Manager's own presentation detail, not a cited anchor.
_PROMPT_TITLE = "Smart Charging"
_PROMPT_MESSAGE = "Will the car be home tomorrow?"


class NotificationManager:
    """Notification Manager (M3). Holds the UC08 prompt lifecycle state + evening options.

    `_state`/`_date` are `evaluate_prompt`'s own persisted (prior_state, prior_date) pair
    (notification_state.py module docstring) -- this Manager is exactly the caller that
    docstring describes as owning that anchor across ticks.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        adapters: dict[str, Adapter],
        entry_id: str,
        store: Store,
        config: Mapping[str, Any],
    ) -> None:
        self._hass = hass
        self._adapters = adapters
        self._entry_id = entry_id
        self._store = store
        self._enabled = bool(config[CONF_EVENING_PROMPT_ENABLED])
        self._threshold_kwh = float(config[CONF_SOLAR_FORECAST_THRESHOLD_KWH])
        self._prompt_time = time.fromisoformat(config[CONF_EVENING_PROMPT_TIME])
        self._state = PromptState.NOT_SENT
        self._date = dt_util.now().date()

    async def async_evaluate(self, now: datetime | None = None) -> None:
        """Run one UC08 evaluation tick (Task 5.2's scheduled caller supplies `now`; tests
        override it directly). No-ops entirely when the notification target isn't mapped --
        RA4 is this use-case's only delivery channel, so M3 has nothing to do without it."""
        now = now or dt_util.now()
        notify_adapter = self._adapters.get(ROLE_NOTIFICATION_TARGET)
        if notify_adapter is None:
            _LOGGER.debug("notification_target not mapped -- M3 stays inert")
            return

        # RA4's read() consumes the answer it returns (adapters/notify.py docstring) -- only
        # call it while a prompt is actually outstanding, matching that contract.
        response = None
        if self._state is PromptState.PENDING:
            response = await notify_adapter.read()

        forecast_kwh = await self._read_float(ROLE_SOLAR_FORECAST)
        external_flag_set = await self._read_bool(ROLE_HOME_DAY_EXTERNAL)
        status = await self._read_status()
        connected_at_home = status in CHARGEABLE_STATES

        evaluation = evaluate_prompt(
            self._state,
            self._date,
            now,
            enabled=self._enabled,
            forecast_kwh=forecast_kwh,
            threshold_kwh=self._threshold_kwh,
            external_flag_set=external_flag_set,
            connected_at_home=connected_at_home,
            prompt_time=self._prompt_time,
            response=response,
        )

        if evaluation.should_send:
            await notify_adapter.write(
                NotificationRequest(
                    message=_PROMPT_MESSAGE,
                    title=_PROMPT_TITLE,
                    actions=[ACTION_HOMEDAY_YES, ACTION_HOMEDAY_NO],
                )
            )

        if evaluation.write_home_day_flag:
            await self._store.write(Platform.SWITCH, OWNED_SUFFIX_HOME_DAY, True)

        self._state = evaluation.next_state
        self._date = evaluation.next_date

    async def _read_float(self, role: str) -> float:
        """Missing/unavailable solar_forecast reads as 0.0 -- fails closed against UC08's
        forecast gate (never triggers on an absent reading) rather than guessing a value
        that could send an unwarranted prompt."""
        adapter = self._adapters.get(role)
        if adapter is None:
            return 0.0
        value = await adapter.read()
        return value if value is not None else 0.0

    async def _read_bool(self, role: str) -> bool:
        """Missing/unavailable home_day_external reads as False -- no external source has
        set the flag, UC08's own default absent a mapped role."""
        adapter = self._adapters.get(role)
        if adapter is None:
            return False
        value = await adapter.read()
        return bool(value)

    async def _read_status(self) -> str | None:
        adapter = self._adapters.get(ROLE_CHARGER_STATUS)
        if adapter is None:
            return None
        return await adapter.read()
