"""Plain-pytest tests for the pure notification state machine (M3 -- UC08).

Anchors: UC08 preconditions, trigger, and state model (R13) --
docs/analysis/use-cases/UC08-plan-tomorrow-home-day.md. This module owns none of those
rules -- it cites them as test anchors, per docs/plans/2026-07-21-notifications-design.md
Sec7 and Sec11 (pure state machine -> plain pytest, ADR-0009).
"""

from datetime import date, datetime, time

from custom_components.smart_charging.const import ACTION_HOMEDAY_NO, ACTION_HOMEDAY_YES
from custom_components.smart_charging.notification_state import (
    PromptState,
    evaluate_prompt,
)

DAY_1 = date(2026, 8, 1)
DAY_2 = date(2026, 8, 2)

PROMPT_TIME = time(18, 0)
THRESHOLD_KWH = 12.0

# Baseline "everything holds" inputs for the trigger -- override per test.
BASE_KWARGS = {
    "enabled": True,
    "forecast_kwh": 15.0,
    "threshold_kwh": THRESHOLD_KWH,
    "external_flag_set": False,
    "connected_at_home": True,
    "prompt_time": PROMPT_TIME,
    "response": None,
}


def _evaluate(prior_state, prior_date, now, **overrides):
    kwargs = {**BASE_KWARGS, **overrides}
    return evaluate_prompt(prior_state, prior_date, now, **kwargs)


def test_not_sent_to_pending_on_trigger():
    """Enabled + forecast > threshold + no external flag + connected at/after prompt time
    before midnight -> send, Not-sent -> Pending (HomeDayPromptSent)."""
    now = datetime.combine(DAY_1, time(18, 0))

    result = _evaluate(PromptState.NOT_SENT, DAY_1, now)

    assert result.should_send is True
    assert result.next_state is PromptState.PENDING
    assert result.next_date == DAY_1
    assert result.write_home_day_flag is False


def test_pending_to_answered_yes_writes_flag_intent():
    """HOMEDAY_YES before midnight -> Answered-yes, flag-write intent True (HomeDaySet)."""
    now = datetime.combine(DAY_1, time(20, 0))

    result = _evaluate(PromptState.PENDING, DAY_1, now, response=ACTION_HOMEDAY_YES)

    assert result.should_send is False
    assert result.next_state is PromptState.ANSWERED_YES
    assert result.next_date == DAY_1
    assert result.write_home_day_flag is True


def test_pending_to_answered_no_leaves_flag_unset():
    """HOMEDAY_NO before midnight -> Answered-no, no flag write (HomeDayPromptDeclined)."""
    now = datetime.combine(DAY_1, time(20, 0))

    result = _evaluate(PromptState.PENDING, DAY_1, now, response=ACTION_HOMEDAY_NO)

    assert result.should_send is False
    assert result.next_state is PromptState.ANSWERED_NO
    assert result.next_date == DAY_1
    assert result.write_home_day_flag is False


def test_pending_to_timed_out_at_midnight_leaves_flag_unset():
    """Midnight with no answer -> Timed-out, no flag write (HomeDayPromptTimedOut)."""
    now = datetime.combine(DAY_2, time(0, 0))

    result = _evaluate(PromptState.PENDING, DAY_1, now, response=None)

    assert result.should_send is False
    assert result.next_state is PromptState.TIMED_OUT
    # The evening being finalized is DAY_1's -- the date only rolls forward to DAY_2
    # on the *next* evaluation, once this evening's terminal state has been recorded.
    assert result.next_date == DAY_1
    assert result.write_home_day_flag is False


def test_skips_when_prompt_disabled_or_forecast_below_threshold_or_external_flag_set():
    """UC08 1a/1b: stays Not-sent, no send."""
    now = datetime.combine(DAY_1, time(19, 0))

    disabled = _evaluate(PromptState.NOT_SENT, DAY_1, now, enabled=False)
    low_forecast = _evaluate(PromptState.NOT_SENT, DAY_1, now, forecast_kwh=5.0)
    external_set = _evaluate(PromptState.NOT_SENT, DAY_1, now, external_flag_set=True)

    for result in (disabled, low_forecast, external_set):
        assert result.should_send is False
        assert result.next_state is PromptState.NOT_SENT
        assert result.next_date == DAY_1
        assert result.write_home_day_flag is False


def test_stays_not_sent_when_car_never_connects_before_midnight():
    """UC08 1c: no trigger before midnight -> stays Not-sent."""
    now = datetime.combine(DAY_1, time(23, 0))

    result = _evaluate(PromptState.NOT_SENT, DAY_1, now, connected_at_home=False)

    assert result.should_send is False
    assert result.next_state is PromptState.NOT_SENT
    assert result.next_date == DAY_1
    assert result.write_home_day_flag is False


def test_rearms_to_not_sent_at_day_rollover():
    """Terminal states -> Not-sent at the midnight date rollover (fresh each evening)."""
    now = datetime.combine(DAY_2, time(0, 5))

    for prior_state in (
        PromptState.NOT_SENT,
        PromptState.ANSWERED_YES,
        PromptState.ANSWERED_NO,
        PromptState.TIMED_OUT,
    ):
        # No trigger yet this new evening (before prompt time) -- isolates the rearm
        # itself from a same-tick re-trigger.
        result = _evaluate(prior_state, DAY_1, now, connected_at_home=False)

        assert result.next_state is PromptState.NOT_SENT
        assert result.next_date == DAY_2
        assert result.should_send is False
        assert result.write_home_day_flag is False


def test_rollover_from_pending_finalizes_timeout_before_rearming():
    """A Pending prompt that crosses midnight finalizes to Timed-out on the tick that
    observes the rollover; only the *following* tick (once Timed-out is the prior state)
    rearms to Not-sent -- exactly one terminal transition per evening."""
    midnight = datetime.combine(DAY_2, time(0, 0))

    finalized = _evaluate(PromptState.PENDING, DAY_1, midnight, response=None)
    assert finalized.next_state is PromptState.TIMED_OUT
    assert finalized.next_date == DAY_1

    rearmed = _evaluate(
        finalized.next_state, finalized.next_date, midnight, connected_at_home=False
    )
    assert rearmed.next_state is PromptState.NOT_SENT
    assert rearmed.next_date == DAY_2


def test_answered_yes_is_terminal_a_later_no_is_ignored():
    """No-transition-once-terminal: a second, contradictory response the same evening
    must not flip an already-terminal Answered-yes."""
    now = datetime.combine(DAY_1, time(20, 30))

    result = _evaluate(PromptState.ANSWERED_YES, DAY_1, now, response=ACTION_HOMEDAY_NO)

    assert result.next_state is PromptState.ANSWERED_YES
    assert result.should_send is False
    assert result.write_home_day_flag is False


def test_timed_out_is_terminal_a_late_yes_is_ignored():
    """A response arriving after the prompt already timed out (e.g. a stale/late tap)
    must not resurrect the prompt or write the flag."""
    now = datetime.combine(DAY_1, time(23, 59))

    result = _evaluate(PromptState.TIMED_OUT, DAY_1, now, response=ACTION_HOMEDAY_YES)

    assert result.next_state is PromptState.TIMED_OUT
    assert result.should_send is False
    assert result.write_home_day_flag is False


def test_not_sent_with_no_pending_prompt_a_response_is_ignored():
    """Not-sent has nothing pending to answer -- a response arriving anyway (e.g. a
    1a/1b evening, or before the trigger has fired) must not be treated as an answer."""
    now = datetime.combine(DAY_1, time(19, 0))

    result = _evaluate(
        PromptState.NOT_SENT,
        DAY_1,
        now,
        external_flag_set=True,
        response=ACTION_HOMEDAY_YES,
    )

    assert result.next_state is PromptState.NOT_SENT
    assert result.should_send is False
    assert result.write_home_day_flag is False


def test_not_sent_re_evaluates_the_1a_1b_gates_every_tick_not_latched():
    """Not-sent is not a terminal 'skipped' state distinct from 'not yet triggered':
    a gate observed false on one tick (e.g. the external flag still set at 18:00) does
    not preclude sending later the same evening once the gate clears, before midnight --
    there is no separate skipped state in the UC08 state model, only Not-sent."""
    still_gated = _evaluate(
        PromptState.NOT_SENT,
        DAY_1,
        datetime.combine(DAY_1, time(18, 0)),
        external_flag_set=True,
    )
    assert still_gated.next_state is PromptState.NOT_SENT
    assert still_gated.should_send is False

    gate_cleared_later = _evaluate(
        PromptState.NOT_SENT,
        DAY_1,
        datetime.combine(DAY_1, time(19, 0)),
        external_flag_set=False,
    )
    assert gate_cleared_later.next_state is PromptState.PENDING
    assert gate_cleared_later.should_send is True


def test_pending_stays_pending_same_evening_when_unanswered_so_far():
    """A Pending prompt with no response yet, still the same evening (no midnight
    crossed), stays Pending and does not re-send (UC08 sends the notification once)."""
    now = datetime.combine(DAY_1, time(20, 0))

    result = _evaluate(PromptState.PENDING, DAY_1, now, response=None)

    assert result.should_send is False
    assert result.next_state is PromptState.PENDING
    assert result.next_date == DAY_1
    assert result.write_home_day_flag is False


def test_rearm_and_new_evenings_trigger_can_fire_on_the_same_tick():
    """The module docstring's same-tick 'rearm, then evaluate against the new evening's
    own trigger' path: a terminal prior state from yesterday, observed on a tick where
    today's own trigger already holds, sends immediately rather than waiting a tick."""
    now = datetime.combine(DAY_2, time(18, 5))

    result = _evaluate(PromptState.ANSWERED_YES, DAY_1, now)

    assert result.should_send is True
    assert result.next_state is PromptState.PENDING
    assert result.next_date == DAY_2
    assert result.write_home_day_flag is False


def test_connected_before_prompt_time_does_not_trigger_yet():
    """UC08 1c (partial): connected at home, but before the configured prompt time --
    the trigger has not been reached yet, stays Not-sent."""
    now = datetime.combine(DAY_1, time(17, 59))

    result = _evaluate(PromptState.NOT_SENT, DAY_1, now, connected_at_home=True)

    assert result.should_send is False
    assert result.next_state is PromptState.NOT_SENT
