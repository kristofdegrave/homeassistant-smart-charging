"""Notification Manager (M3, V11) -- UC08 evening home-day prompt orchestration, plus R5
deadline-unreachable notice delivery.

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
(`dt_util.now()` date rollover), driven by the caller's own tick -- no new HA
timer/scheduler primitive. `async_evaluate`'s `now` parameter defaults to `dt_util.now()`
for production callers and is overridable by tests, the same shape `evaluate_prompt`
itself takes explicitly.

R5 delivery: `on_deadline_unreachable`/`register_listeners`
subscribe to the Coordinator's already-published `DeadlineUnreachableNotified` event
(coordinator.py, `EVENT_DEADLINE_UNREACHABLE_NOTIFIED`) -- consuming it, never re-deriving
urgency (ADR-0011). Unlike the UC08 prompt, this is a plain, non-actionable notice with no
response to capture -- but it does have one bit of lifecycle state, `_deadline_unreachable_
notified`: const.py documents that the Coordinator fires this event on *every* cycle the
deadline stays unreachable (design's own R5/ADR-0011 comment), not only on the transition
edge, while ADR-0011 itself describes the event as having "notify-once semantics" -- a real
tension between the producer's actual behavior and the documented consumer contract. This
Manager resolves it on the consumer side (the side ADR-0011 assigns the semantics to):
deliver once, then suppress further deliveries for the lifetime of this Manager instance
(reset only by a reload/restart). See the class docstring's "Known gaps" for what this
does and doesn't cover.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from datetime import date, datetime, time
from typing import Any

from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant
from homeassistant.util import dt as dt_util

from ..adapters.base import Adapter
from ..adapters.notify import NotificationRequest
from ..adapters.store import Store
from ..const import (
    ACTION_HOMEDAY_NO,
    ACTION_HOMEDAY_YES,
    ATTR_REQUIRED_CURRENT_A,
    CHARGEABLE_STATES,
    CONF_EVENING_PROMPT_ENABLED,
    CONF_EVENING_PROMPT_TIME,
    CONF_SOLAR_FORECAST_THRESHOLD_KWH,
    DEFAULT_EVENING_PROMPT_ENABLED,
    DEFAULT_EVENING_PROMPT_TIME,
    DEFAULT_SOLAR_FORECAST_THRESHOLD_KWH,
    EVENT_DEADLINE_UNREACHABLE_NOTIFIED,
    OWNED_SUFFIX_HOME_DAY,
    ROLE_CHARGER_STATUS,
    ROLE_HOME_DAY_EXTERNAL,
    ROLE_NOTIFICATION_TARGET,
    ROLE_SOLAR_FORECAST,
)
from ..notification_state import PromptState, evaluate_prompt

_LOGGER = logging.getLogger(__name__)

# UC08 main success scenario step 2's actionable prompt text -- no analysis doc catalogues an
# exact wording, so it is this Manager's own presentation detail, not a cited anchor.
_PROMPT_TITLE = "Smart Charging"
_PROMPT_MESSAGE = "Will the car be home tomorrow?"
# R5's deadline-unreachable notice (design Sec9) -- also this Manager's own presentation
# detail; required_a is the current the deadline would need, per DeadlineUnreachableNotified's
# own payload (ATTR_REQUIRED_CURRENT_A, coordinator.py) -- included for the driver's context,
# not re-derived (ADR-0011: consume the published event, never recompute urgency).
_DEADLINE_UNREACHABLE_MESSAGE = (
    "Charging at the maximum rate but still won't reach your target by departure "
    "(would need {required_a:.1f} A)."
)


class NotificationManager:
    """Notification Manager (M3). Holds the UC08 prompt lifecycle state + evening options.

    `_state`/`_date` are `evaluate_prompt`'s own persisted (prior_state, prior_date) pair
    (notification_state.py module docstring) -- this Manager is exactly the caller that
    docstring describes as owning that anchor across ticks.

    Known gaps:
    - `_state`/`_date` are in-memory only and reset to Not-sent on every HA restart, so a
      restart between a prompt being sent and midnight can cause a second prompt the same
      evening (UC08's "at most once per evening" is only guaranteed within one HA session).
    - `_deadline_unreachable_notified` latches permanently once set -- a deadline that
      becomes unreachable, resolves (car disconnects, SOC catches up), and later becomes
      unreachable again on a *different* occasion delivers only the first notice for the
      lifetime of this Manager instance (until the next reload/restart), not one notice per
      occasion. The Coordinator's `DeadlineUnreachableNotified` event carries no "resolved"
      counterpart to re-arm on (it only ever fires while unreachable, const.py), so a
      correct per-occasion re-arm needs a producer-side signal not yet implemented --
      tracked as a follow-up, not silently accepted as "done".
    Restart persistence and the re-arm signal are not part of the notifications design doc
    and are left for a follow-up if either proves to matter in practice.
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
        # `entry_id` is unused -- this Manager fires no domain events of its own (unlike
        # VehicleLimitManager's _fire), so it never needs entry-scoping in a payload. Kept
        # for the same reason every other Manager's constructor takes it: a consistent shape,
        # and available if a future need arises (e.g. diagnostics). `hass` IS used, by
        # register_listeners' hass.bus.async_listen.
        self._hass = hass
        self._adapters = adapters
        self._entry_id = entry_id
        self._store = store
        # .get(..., DEFAULT_*) -- design doc §3: "an entry that predates these keys reads
        # each with its DEFAULT_* fallback, no config-entry migration is needed", the same
        # pattern __init__.py/coordinator.py already use for every options-bucket value.
        self._enabled = bool(
            config.get(CONF_EVENING_PROMPT_ENABLED, DEFAULT_EVENING_PROMPT_ENABLED)
        )
        self._threshold_kwh = float(
            config.get(CONF_SOLAR_FORECAST_THRESHOLD_KWH, DEFAULT_SOLAR_FORECAST_THRESHOLD_KWH)
        )
        self._prompt_time = time.fromisoformat(
            config.get(CONF_EVENING_PROMPT_TIME, DEFAULT_EVENING_PROMPT_TIME)
        )
        self._state = PromptState.NOT_SENT
        # Seeded lazily on the first tick (below), from that tick's own `now` -- not here from
        # the real wall clock, which would make this Manager's behavior depend on which day it
        # happens to be constructed, not just the `now` its own tests and caller supply.
        self._date: date | None = None
        # R5 delivery's own latch -- see the class docstring's "Known gaps" for
        # why this is a permanent-until-reload latch, not a per-occasion one.
        self._deadline_unreachable_notified = False

    async def async_evaluate(self, now: datetime | None = None) -> None:
        """Run one UC08 evaluation tick (the scheduled caller supplies `now`; tests
        override it directly). No-ops entirely when the notification target isn't mapped --
        RA4 is this use-case's only delivery channel, so M3 has nothing to do without it.

        `now` is normalized to local time -- the `async_track_time_interval` caller
        hands its callback a UTC-aware datetime, and both the prompt-time-of-day comparison
        and the midnight date rollover (`evaluate_prompt`) are local-clock concepts.
        """
        now = dt_util.as_local(now) if now is not None else dt_util.now()
        if self._date is None:
            self._date = now.date()
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

        if response is not None and evaluation.next_state is PromptState.TIMED_OUT:
            # The day rolled over between the driver's answer and this tick observing it
            # (notification_state.py's finalize-on-rollover branch ignores `response`
            # entirely once today > prior_date) -- an answer given before midnight is lost
            # here, not adopted. Not this Manager's to fix (the finalize decision belongs to
            # evaluate_prompt), but silence would hide a real, if narrow, loss of UC08's
            # "answer counts if given before midnight" -- log it so it's at least visible.
            _LOGGER.warning(
                "A prompt response (%s) arrived before midnight but wasn't observed until "
                "after -- the evening timed out and the response was not adopted",
                response,
            )

        if evaluation.should_send:
            try:
                await notify_adapter.write(
                    NotificationRequest(
                        message=_PROMPT_MESSAGE,
                        title=_PROMPT_TITLE,
                        actions=[ACTION_HOMEDAY_YES, ACTION_HOMEDAY_NO],
                    )
                )
            except Exception as err:  # noqa: BLE001 - best-effort delivery (mirrors
                # VehicleLimitManager._write_vehicle); the notify entity/integration may be
                # transiently gone. Not raising here also means `_state` is not advanced
                # below -- nothing was actually sent, so the lifecycle stays Not-sent and
                # retries on the next tick, rather than raising once and then silently
                # never trying again.
                _LOGGER.debug("notification_target write failed: %s", err)
                return

        if evaluation.write_home_day_flag:
            # Store.write is itself best-effort (never raises, ADR-0018) -- only its bool
            # result can signal failure. Logged at warning, not silently accepted: the
            # driver's "yes" answer has already been consumed by RA4's read() above and
            # cannot be re-observed on a later tick, so a failed write here is otherwise an
            # unrecoverable, invisible loss of UC08's postcondition ("flag set on yes").
            if not await self._store.write(Platform.SWITCH, OWNED_SUFFIX_HOME_DAY, True):
                _LOGGER.warning(
                    "Failed to write home-day flag after a 'yes' answer -- flag left unset"
                )

        self._state = evaluation.next_state
        self._date = evaluation.next_date

    async def on_deadline_unreachable(self, required_a: float) -> None:
        """React to R5's DeadlineUnreachableNotified (ADR-0011 published event, Decision row
        1: consume it, never re-derive urgency). Delivers a plain (non-actionable) notice via
        RA4 -- once: the Coordinator fires this event on every cycle the deadline stays
        unreachable (const.py), not only on the transition edge, so without this latch a
        single unreachable deadline would deliver one push notification per control cycle
        for as long as it remains unreachable (class docstring's "Known gaps" covers what
        this latch does and doesn't do).

        A delivery failure is logged at warning, not swallowed quietly -- unlike the UC08
        prompt's own best-effort send (which retries every tick, so a debug-level miss is
        cheap), this is a single, permanently-latched attempt: a failed delivery here is not
        retried on the next event, since the latch is already set to prevent exactly that.

        No-ops when the notification target isn't mapped -- the same inertness contract
        `async_evaluate` already has, RA4 being this Manager's only delivery channel."""
        if self._deadline_unreachable_notified:
            return
        notify_adapter = self._adapters.get(ROLE_NOTIFICATION_TARGET)
        if notify_adapter is None:
            return
        self._deadline_unreachable_notified = True
        try:
            await notify_adapter.write(
                NotificationRequest(
                    message=_DEADLINE_UNREACHABLE_MESSAGE.format(required_a=required_a),
                    title=_PROMPT_TITLE,
                )
            )
        except Exception as err:  # noqa: BLE001 - best-effort delivery (mirrors async_evaluate)
            _LOGGER.warning(
                "Failed to deliver the deadline-unreachable notice (not retried -- the "
                "notify-once latch is already set): %s",
                err,
            )

    def register_listeners(self) -> list[Callable[[], None]]:
        """Wire M3's R5 delivery trigger (design Sec9): subscribes to the Coordinator's
        published `DeadlineUnreachableNotified` bus event. Called once at setup; the caller
        registers each returned unsub via `entry.async_on_unload` (ADR-0008, mirrors
        VehicleLimitManager.register_listeners)."""

        async def _on_deadline_unreachable(event: Event) -> None:
            required_a = event.data.get(ATTR_REQUIRED_CURRENT_A)
            if required_a is None:
                # hass.bus is a shared surface (any automation, or Developer Tools -> Events,
                # can fire this event type) -- a malformed/foreign payload is silently
                # skipped rather than raising out of this listener coroutine, the same
                # ADR-0003-style tolerance the rest of this integration gives external input.
                _LOGGER.debug(
                    "%s event missing %s -- ignoring",
                    EVENT_DEADLINE_UNREACHABLE_NOTIFIED,
                    ATTR_REQUIRED_CURRENT_A,
                )
                return
            await self.on_deadline_unreachable(required_a)

        return [
            self._hass.bus.async_listen(
                EVENT_DEADLINE_UNREACHABLE_NOTIFIED, _on_deadline_unreachable
            )
        ]

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
        """An unmapped home_day_external role reads as False -- UC08's own default when no
        external source is configured at all. A *mapped* role's read() returning None (an
        ADR-0003 fault signal: unavailable/unknown entity) also folds to False here, which
        is a deliberate fail-open choice, not a second instance of the same default: it
        risks a redundant prompt on a transient reading (harmless -- the driver can still
        answer "no") rather than risking a silently-skipped evening on a real external
        home-day flag misread as absent."""
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
