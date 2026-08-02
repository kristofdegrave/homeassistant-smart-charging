"""Plain-pytest tests for the coordinator's internal cycle-decomposition units (ADR-0012)."""

from datetime import datetime

from custom_components.smart_charging.const import (
    CONF_CAPTAR_COOLDOWN_MIN,
    CONF_MAX_CURRENT,
    CONF_MIN_CURRENT,
    CONF_SOLAR_COOLDOWN_MIN,
    CONF_SOLAR_HOLD_MIN,
    CONF_SOLAR_ONLY_MIDPOINT,
    CONF_SOLAR_ONLY_START_THRESHOLD_W,
    CONF_SOLAR_ONLY_STRATEGY,
    CONF_SOLAR_START_THRESHOLD_W,
    DEFAULT_CAPTAR_COOLDOWN_MIN,
    STATE_CHARGING,
    STATE_CONNECTED,
    STATE_DISCONNECTED,
)
from custom_components.smart_charging.coordinator_cycle import (
    CycleContext,
    ModeHandler,
    PeakDemandState,
    _CaptarModeHandler,
    _OffModeHandler,
    _PowerModeHandler,
    _SolarModeHandler,
    _SolarOnlyModeHandler,
)
from custom_components.smart_charging.modes import captar, solar, solar_only
from custom_components.smart_charging.modes._amp_step import ROUND_DOWN
from custom_components.smart_charging.modes._phase import Phase


def test_cycle_context_constructs_with_required_fields_and_defaults():
    """CycleContext (ADR-0012) exposes all defaulted fields with their documented starting
    values -- the required fields (status/net_w/charger_w/voltage/now/now_dt) construct with no
    defaults, everything else is optional and starts at the value _run_cycle's old loose locals
    used to start with."""
    ctx = CycleContext(
        status=STATE_CHARGING,
        net_w=100.0,
        charger_w=1000.0,
        voltage=230.0,
        now=1.0,
        now_dt=datetime(2026, 7, 27, 12, 0),
    )
    assert ctx.ev_soc is None
    assert ctx.surplus_w == 0.0
    assert ctx.monthly_peak_kw == 0.0
    assert ctx.effective_peak_limit_kw == 0.0
    assert ctx.active_soc_limit == 0.0
    assert ctx.urgent is False
    assert ctx.sun_is_up is False
    assert ctx.sun_is_down is False
    assert ctx.low_tariff_active is True
    assert ctx.solar_reserve_active is False


def test_cycle_context_accepts_none_now_dt_for_dry_run_construction():
    """now_dt is None only in _mode_desired_current's dry-run ctx (Task 3.3), which needs no
    month/weekday context -- documented as the one legitimate None, not an accidental gap."""
    ctx = CycleContext(
        status=STATE_CHARGING, net_w=0.0, charger_w=0.0, voltage=230.0, now=1.0, now_dt=None
    )
    assert ctx.now_dt is None


def test_cycle_context_is_mutable_and_filled_progressively():
    """CycleContext is a plain (non-frozen) dataclass by design (ADR-0012): _run_cycle's steps
    fill in fields such as surplus_w as they're resolved, rather than everything being known at
    construction time -- this test exercises that mutability contract directly."""
    ctx = CycleContext(
        status=STATE_CHARGING,
        net_w=100.0,
        charger_w=1000.0,
        voltage=230.0,
        now=1.0,
        now_dt=datetime(2026, 7, 27, 12, 0),
    )
    ctx.surplus_w = 500.0
    assert ctx.surplus_w == 500.0


def test_peak_demand_state_accumulates_within_same_month():
    """PeakDemandState.update (ADR-0012) wraps signal_conditioning.smooth_net_power +
    peak_demand_tracker.update_monthly_peak_demand: within the same month the running peak is
    the max of the smoothed kW readings seen so far."""
    state = PeakDemandState()
    state.update(2000.0, datetime(2026, 7, 1, 0, 0), window_size=1)
    peak = state.update(1000.0, datetime(2026, 7, 2, 0, 0), window_size=1)
    assert peak == 2.0  # kW -- max(2.0, 1.0)


def test_peak_demand_state_threads_window_size_and_averages_within_the_month():
    """Distinct from the two tests above: proves window_size is actually threaded through to
    smooth_net_power (not hard-coded/dropped) and that the smoothed *mean* -- not the raw last
    sample -- is what reaches update_monthly_peak_demand. window_size=1 or identical samples
    would let a broken implementation pass the other two tests undetected."""
    state = PeakDemandState()
    state.update(2000.0, datetime(2026, 7, 1, 0, 0), window_size=2)
    peak = state.update(0.0, datetime(2026, 7, 1, 0, 5), window_size=2)
    assert state.window == (2000.0, 0.0)  # both samples kept -- window preserved within the month
    assert peak == 2.0  # running peak still 2.0 kW -- the 1.0 kW mean of this cycle doesn't beat it


def test_peak_demand_state_resets_window_and_tracked_kw_on_month_rollover():
    """A month rollover resets both the smoothing window and tracked_kw (design doc Sec 6.4) --
    window_size=2 so the pre-rollover window would carry 2 samples if NOT cleared, proving the
    reset actually happens (window_size=1 would always show a 1-element window regardless, since
    smooth_net_power always appends the new sample before returning)."""
    state = PeakDemandState()
    state.update(5000.0, datetime(2026, 7, 30, 0, 0), window_size=2)
    state.update(5000.0, datetime(2026, 7, 31, 0, 0), window_size=2)
    peak = state.update(1000.0, datetime(2026, 8, 1, 0, 0), window_size=2)
    assert peak == 1.0  # not max(5.0, 1.0) -- rollover resets tracked_kw to this cycle's reading
    assert state.window == (1000.0,)  # only this cycle's sample -- last month's were cleared


def test_mode_handler_protocol_is_satisfied_by_each_adapter():
    """Every _*ModeHandler (ADR-0012 Sec 3.4) satisfies the ModeHandler Protocol's single
    desired_current(ctx, state) -> (current, new_state) shape -- a structural check that all
    five adapters share one call surface, not a behavior test. ModeHandler is a plain (not
    @runtime_checkable) Protocol per the design doc, so conformance is checked by static typing
    and by each adapter exposing a callable desired_current, not by isinstance()."""
    handlers: list[ModeHandler] = [
        _OffModeHandler(),
        _PowerModeHandler(lambda: 10.0),
        _SolarModeHandler({}),
        _SolarOnlyModeHandler({}),
        _CaptarModeHandler({}),
    ]
    for handler in handlers:
        assert callable(handler.desired_current)


def test_off_mode_handler_always_commands_zero_and_passes_state_through():
    """_OffModeHandler (ADR-0012) is a no-op adapter: Off mode has no modes/*.py module of its
    own to wrap, so it commands 0 A unconditionally and returns whatever state it was given
    unchanged (mirrors today's MODE_OFF branch, which never touches per-mode state)."""
    handler = _OffModeHandler()
    sentinel_state = object()
    current, new_state = handler.desired_current(
        CycleContext(
            status=STATE_CHARGING, net_w=0.0, charger_w=0.0, voltage=230.0, now=1.0, now_dt=None
        ),
        sentinel_state,
    )
    assert current == 0.0
    assert new_state is sentinel_state


def test_power_mode_handler_delegates_to_modes_power_desired_current():
    """_PowerModeHandler (ADR-0012) wraps modes/power.py::desired_current unchanged, reading
    the coordinator's mutable target_current through a zero-arg getter bound at construction
    (design doc Sec 3.4) rather than duplicating it onto CycleContext. Anchor: tests/modes/
    test_power.py's own STATE_CHARGING/target_current=10.0 -> 10.0 A expectation."""
    handler = _PowerModeHandler(lambda: 10.0)
    ctx = CycleContext(
        status=STATE_CHARGING, net_w=0.0, charger_w=0.0, voltage=230.0, now=1.0, now_dt=None
    )
    current, new_state = handler.desired_current(ctx, None)
    assert current == 10.0
    assert new_state is None


def test_power_mode_handler_commands_zero_when_disconnected():
    """Confirms the handler re-reads status from ctx each call (not cached at construction) --
    anchored to tests/modes/test_power.py's disconnected -> 0.0 A expectation."""
    handler = _PowerModeHandler(lambda: 10.0)
    ctx = CycleContext(
        status=STATE_DISCONNECTED, net_w=0.0, charger_w=0.0, voltage=230.0, now=1.0, now_dt=None
    )
    current, _ = handler.desired_current(ctx, None)
    assert current == 0.0


def test_power_mode_handler_reads_target_current_fresh_each_call():
    """target_current is coordinator-owned mutable state (set externally by the number entity),
    not part of "this cycle's readings" -- the getter must be re-invoked each call, not
    memoized at construction (design doc Sec 3.4's stated rationale for the getter shape)."""
    current_target = [10.0]
    handler = _PowerModeHandler(lambda: current_target[0])
    ctx = CycleContext(
        status=STATE_CONNECTED, net_w=0.0, charger_w=0.0, voltage=230.0, now=1.0, now_dt=None
    )
    first, _ = handler.desired_current(ctx, None)
    current_target[0] = 16.0
    second, _ = handler.desired_current(ctx, None)
    assert first == 10.0
    assert second == 16.0


def test_solar_mode_handler_delegates_to_modes_solar_step():
    # Surplus (150 W) clears the 150 W start threshold -> solar.step's own idle->charging
    # transition sets 6 A (min_a), the SolarState's documented start behavior (tests/modes/
    # test_solar.py's test_starts_charging_at_start_threshold_rounding_up anchors this same
    # 6 A expectation) -- hardcoded here as the anchor, not recomputed by calling solar.step
    # again, so this test actually proves correct delegation rather than mirroring the
    # implementation.
    config = {
        CONF_SOLAR_START_THRESHOLD_W: 150.0,
        CONF_MIN_CURRENT: 6.0,
        CONF_SOLAR_HOLD_MIN: 5.0,
        CONF_SOLAR_COOLDOWN_MIN: 2.0,
    }
    handler = _SolarModeHandler(config)
    ctx = CycleContext(
        status=STATE_CHARGING,
        net_w=0.0,
        charger_w=0.0,
        voltage=230.0,
        now=0.0,
        now_dt=datetime(2026, 7, 27, 12, 0),
        surplus_w=150.0,
    )
    current, new_state = handler.desired_current(ctx, solar.SolarState.idle())
    assert current == 6.0
    assert new_state.phase == Phase.CHARGING


def test_solar_only_mode_handler_delegates_to_modes_solar_only_step():
    # Surplus (1450 W) clears the 1300 W start threshold -> ideal = 1450 / 230 = 6.304 A,
    # a deliberately non-integral value (unlike 1380 W, whose 6.0 A ideal is identical
    # across round_down/round_up/round_nearest and so wouldn't prove strategy/midpoint are
    # threaded through -- code-reviewer finding on PR #451). round_down floors 6.304 A to
    # 6 A, matching the pattern tests/modes/test_solar_only.py uses for its own
    # strategy-threading tests.
    config = {
        CONF_SOLAR_ONLY_START_THRESHOLD_W: 1300.0,
        CONF_MIN_CURRENT: 6.0,
        CONF_SOLAR_COOLDOWN_MIN: 2.0,
        CONF_SOLAR_ONLY_STRATEGY: ROUND_DOWN,
        CONF_SOLAR_ONLY_MIDPOINT: 0.5,
    }
    handler = _SolarOnlyModeHandler(config)
    ctx = CycleContext(
        status=STATE_CHARGING,
        net_w=0.0,
        charger_w=0.0,
        voltage=230.0,
        now=0.0,
        now_dt=datetime(2026, 7, 27, 12, 0),
        surplus_w=1450.0,
    )
    current, new_state = handler.desired_current(ctx, solar_only.SolarOnlyState.idle())
    assert current == 6.0
    assert new_state.phase == Phase.CHARGING


def test_captar_mode_handler_delegates_to_modes_captar_step():
    # Idle -> charging always requests max_a (tests/modes/test_captar.py's
    # test_idle_starts_charging_immediately_requesting_max_current anchors this 32 A
    # expectation) -- captar.step has no surplus/voltage dependency, unlike its siblings.
    # cooldown_minutes=1.0 is deliberately distinct from DEFAULT_CAPTAR_COOLDOWN_MIN (10.0)
    # so this test and the fallback test below are behaviorally distinguishable
    # (code-reviewer finding on PR #451); exercised via the cooldown-elapsing assertions.
    config = {CONF_MAX_CURRENT: 32.0, CONF_CAPTAR_COOLDOWN_MIN: 1.0}
    handler = _CaptarModeHandler(config)
    ctx = CycleContext(
        status=STATE_CHARGING, net_w=0.0, charger_w=0.0, voltage=230.0, now=0.0, now_dt=None
    )
    current, new_state = handler.desired_current(ctx, captar.CaptarState.idle())
    assert current == 32.0
    assert new_state.phase == Phase.CHARGING

    # Prove cooldown_minutes=1.0 is actually threaded through, not just present in the
    # config dict: at 59s (< 1 min) cooldown still blocks; at 61s (> 1 min) it's re-armed.
    cooldown_state = captar.CaptarState(Phase.COOLDOWN, phase_started_at=0.0)
    blocked, _ = handler.desired_current(ctx, cooldown_state)
    assert blocked == 0.0
    ctx_later = CycleContext(
        status=STATE_CHARGING, net_w=0.0, charger_w=0.0, voltage=230.0, now=61.0, now_dt=None
    )
    rearmed, rearmed_state = handler.desired_current(ctx_later, cooldown_state)
    assert rearmed == 32.0
    assert rearmed_state.phase == Phase.CHARGING


def test_captar_mode_handler_uses_default_cooldown_when_config_key_absent():
    """_CaptarModeHandler falls back to DEFAULT_CAPTAR_COOLDOWN_MIN when the config mapping
    omits CONF_CAPTAR_COOLDOWN_MIN (design doc Sec 3.4's .get(..., DEFAULT_CAPTAR_COOLDOWN_MIN)
    call) -- distinct from the other four handlers' plain bracket lookups, which require the
    key to be present. Proven via the cooldown phase (idle/charging never read
    cooldown_minutes at all -- code-reviewer finding on PR #451): just before
    DEFAULT_CAPTAR_COOLDOWN_MIN elapses, cooldown still blocks; just after, it re-arms."""
    config = {CONF_MAX_CURRENT: 32.0}
    handler = _CaptarModeHandler(config)
    cooldown_state = captar.CaptarState(Phase.COOLDOWN, phase_started_at=0.0)

    still_blocked_now = DEFAULT_CAPTAR_COOLDOWN_MIN * 60 - 1
    ctx_before = CycleContext(
        status=STATE_CHARGING,
        net_w=0.0,
        charger_w=0.0,
        voltage=230.0,
        now=still_blocked_now,
        now_dt=None,
    )
    current, new_state = handler.desired_current(ctx_before, cooldown_state)
    assert current == 0.0
    assert new_state.phase == Phase.COOLDOWN

    rearmed_now = DEFAULT_CAPTAR_COOLDOWN_MIN * 60 + 1
    ctx_after = CycleContext(
        status=STATE_CHARGING,
        net_w=0.0,
        charger_w=0.0,
        voltage=230.0,
        now=rearmed_now,
        now_dt=None,
    )
    current, new_state = handler.desired_current(ctx_after, cooldown_state)
    assert current == 32.0
    assert new_state.phase == Phase.CHARGING
