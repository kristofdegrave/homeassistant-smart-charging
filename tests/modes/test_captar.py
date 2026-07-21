"""Plain-pytest tests for the Captar mode engine (E1 -- UC03)."""

import pytest

from custom_components.smart_charging.modes._phase import Phase
from custom_components.smart_charging.modes.captar import CaptarState, step

DEFAULTS = dict(max_a=32.0, cooldown_minutes=10.0)


def test_idle_starts_charging_immediately_requesting_max_current():
    # Unlike Solar/SolarOnly, Captar has no start threshold -- it charges whenever
    # its own connection/SOC/cooldown conditions hold (gated at the coordinator).
    desired, state = step(state=CaptarState.idle(), now=0.0, **DEFAULTS)
    assert desired == DEFAULTS["max_a"]
    assert state.phase == Phase.CHARGING


def test_charging_keeps_requesting_max_current():
    state = CaptarState(Phase.CHARGING, phase_started_at=0.0)
    desired, state = step(state=state, now=10.0, **DEFAULTS)
    assert desired == DEFAULTS["max_a"]
    assert state.phase == Phase.CHARGING


def test_deterministic_given_identical_inputs():
    state = CaptarState(Phase.CHARGING, phase_started_at=0.0)
    desired1, state1 = step(state=state, now=10.0, **DEFAULTS)
    desired2, state2 = step(state=state, now=10.0, **DEFAULTS)
    assert desired1 == desired2
    assert state1 == state2


def test_cooldown_blocks_restart_until_elapsed():
    # Cooldown entry itself is coordinator-driven (a sustained R3 breach, or a
    # mode-switch/disconnect reset) -- this module only knows how to sit in
    # cooldown and re-arm once it elapses, per design doc Sec 6.3.
    state = CaptarState(Phase.COOLDOWN, phase_started_at=0.0)
    desired, state = step(state=state, now=5 * 60, **DEFAULTS)
    assert desired == 0.0
    assert state.phase == Phase.COOLDOWN  # still within the 10 min cooldown
    desired, state = step(state=state, now=10 * 60, **DEFAULTS)  # exact boundary
    assert desired == DEFAULTS["max_a"]
    assert state.phase == Phase.CHARGING


def test_no_soc_related_phase():
    # Design doc Sec 5/6.3: SOC gating is entirely the coordinator's job -- there
    # is no way to construct a "soc reached" CaptarState at all, and any
    # non-Idle/Charging/Cooldown phase (e.g. the shared enum's Hold) is rejected
    # rather than silently treated as charging.
    with pytest.raises(ValueError, match="unknown CaptarState.phase"):
        step(state=CaptarState(Phase.HOLD), now=0.0, **DEFAULTS)
