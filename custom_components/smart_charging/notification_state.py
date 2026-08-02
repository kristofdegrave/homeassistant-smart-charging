"""UC08 evening-prompt lifecycle state machine (M3). Pure -- no HA imports (ADR-0009).

Per docs/plans/2026-07-21-notifications-design.md Sec7: the Not-sent/Pending/
Answered-yes/Answered-no/Timed-out lifecycle
(docs/analysis/use-cases/UC08-plan-tomorrow-home-day.md "State model") is a pure function
of (prior state, observed inputs, now) with no I/O -- structurally identical to the mode
state machines in ``modes/``. This module decides; ``notification_manager.py`` (HA harness)
observes the preconditions/trigger and carries out the send/write effects this module only
signals.

``evaluate_prompt`` takes the prior state **together with the calendar date that state
belongs to** (``prior_date``) -- the anchor a caller (the Notification Manager) must persist
alongside the state itself, since the enum alone cannot carry "which evening" it is for. A
call whose ``now`` has rolled past ``prior_date`` observes the midnight boundary for that
prior evening:

- A **terminal** prior state (Not-sent, Answered-yes, Answered-no, Timed-out) rearms
  directly to Not-sent for the new evening (UC08 "the cycle returns to Not sent only when
  the home-day flag resets at midnight") -- and, in the same tick, is evaluated against the
  new evening's own trigger, since the rearm and that evening's first evaluation are not
  functionally distinguishable.
- A **Pending** prior state finalizes to Timed-out for the evening it was still open for
  (UC08 "Exception flows" -- no answer before midnight is treated as "no"); the rearm to
  Not-sent for the *next* evening happens on the following call, once Timed-out is itself
  the (now terminal) prior state. This keeps each call recording at most one terminal
  transition, matching UC08's "at most once per evening" state model.

Once Pending has resolved to Answered-yes/Answered-no/Timed-out for an evening, it stays
resolved until the day rolls over -- a response observed against one of those states (a
second, contradictory answer, or a late tap after Timed-out) is not a valid transition and
is ignored. Not-sent is not latched against a *response* either (there is nothing pending
to answer), but -- unlike those three -- it is not latched against the 1a/1b *gates*
either: each tick re-observes them, so a still-Not-sent evening can still trigger later if
the caller's readings change before midnight (see the ``NOT_SENT`` branch below).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from enum import StrEnum

from .const import ACTION_HOMEDAY_NO, ACTION_HOMEDAY_YES


class PromptState(StrEnum):
    """UC08's evening-prompt lifecycle states (state model)."""

    NOT_SENT = "not_sent"
    PENDING = "pending"
    ANSWERED_YES = "answered_yes"
    ANSWERED_NO = "answered_no"
    TIMED_OUT = "timed_out"


@dataclass(frozen=True)
class PromptEvaluation:
    """Result of one ``evaluate_prompt`` call.

    ``next_date`` is the evening ``next_state`` belongs to -- pass it back as
    ``prior_date`` on the following call (see module docstring for the finalize-then-
    rearm sequencing across the midnight boundary).
    """

    should_send: bool
    next_state: PromptState
    next_date: date
    write_home_day_flag: bool


def evaluate_prompt(
    prior_state: PromptState,
    prior_date: date,
    now: datetime,
    *,
    enabled: bool,
    forecast_kwh: float,
    threshold_kwh: float,
    external_flag_set: bool,
    connected_at_home: bool,
    prompt_time: time,
    response: str | None,
) -> PromptEvaluation:
    """Decide the next prompt state for this control-tick, per UC08.

    ``response`` is the captured actionable-notification action id (e.g.
    ``ACTION_HOMEDAY_YES``/``ACTION_HOMEDAY_NO`` from ``const.py``), or ``None`` when no
    (fresh) response has been observed. All preconditions/trigger observation and the
    send/write effects are the caller's job (RA1/RA2/RA4 reads, Store writes) -- this
    function only decides.
    """
    today = now.date()

    if today > prior_date:
        if prior_state is PromptState.PENDING:
            # Midnight arrived with no answer for the evening `prior_date` was still
            # open for -- finalize it (UC08 Exception flows). The rearm to Not-sent for
            # `today`'s evening happens on the *next* call, once Timed-out is itself the
            # prior state (module docstring).
            return PromptEvaluation(
                should_send=False,
                next_state=PromptState.TIMED_OUT,
                next_date=prior_date,
                write_home_day_flag=False,
            )
        # Any terminal prior state rearms directly to Not-sent for the new evening, and
        # falls through to be evaluated against `today`'s own trigger below.
        prior_state = PromptState.NOT_SENT
        prior_date = today

    if prior_state is PromptState.NOT_SENT:
        if not enabled or forecast_kwh <= threshold_kwh or external_flag_set:
            # UC08 1a/1b -- stays Not-sent for `prior_date`. Re-evaluated every tick,
            # not latched: a gate observed false on one tick does not preclude sending
            # later the same evening if the caller's reading of `forecast_kwh`/
            # `external_flag_set` changes before midnight -- there is no distinct
            # "skipped" state, only Not-sent, per the state model.
            return PromptEvaluation(
                should_send=False,
                next_state=PromptState.NOT_SENT,
                next_date=prior_date,
                write_home_day_flag=False,
            )
        if connected_at_home and now.time() >= prompt_time:
            return PromptEvaluation(
                should_send=True,
                next_state=PromptState.PENDING,
                next_date=prior_date,
                write_home_day_flag=False,
            )
        # UC08 1c -- trigger not reached yet (or the car never connects before midnight).
        return PromptEvaluation(
            should_send=False,
            next_state=PromptState.NOT_SENT,
            next_date=prior_date,
            write_home_day_flag=False,
        )

    if prior_state is PromptState.PENDING:
        if response == ACTION_HOMEDAY_YES:
            return PromptEvaluation(
                should_send=False,
                next_state=PromptState.ANSWERED_YES,
                next_date=prior_date,
                write_home_day_flag=True,
            )
        if response == ACTION_HOMEDAY_NO:
            return PromptEvaluation(
                should_send=False,
                next_state=PromptState.ANSWERED_NO,
                next_date=prior_date,
                write_home_day_flag=False,
            )
        return PromptEvaluation(
            should_send=False,
            next_state=PromptState.PENDING,
            next_date=prior_date,
            write_home_day_flag=False,
        )

    # Already terminal for this evening (Answered-yes/no, or Timed-out awaiting rearm) --
    # no transition. A response observed here (a second/contradictory or late answer) is
    # not a valid transition and is ignored, per the state model.
    return PromptEvaluation(
        should_send=False,
        next_state=prior_state,
        next_date=prior_date,
        write_home_day_flag=False,
    )
