"""Plain-pytest tests for the coordinator's internal cycle-decomposition units (ADR-0012)."""

from datetime import datetime, time

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
    MODE_CAPTAR,
    MODE_OFF,
    MODE_POWER,
    MODE_SOLAR,
    ROUND_DOWN,
    STATE_CHARGING,
    STATE_CONNECTED,
    STATE_DISCONNECTED,
)
from custom_components.smart_charging.coordinator_cycle import (
    CycleContext,
    ModeHandler,
    PeakDemandState,
    SocGateResolver,
    _CaptarModeHandler,
    _OffModeHandler,
    _PowerModeHandler,
    _SolarModeHandler,
    _SolarOnlyModeHandler,
    resolve_deadline_urgency,
)
from custom_components.smart_charging.engines.soc_target import SolarStepUpState
from custom_components.smart_charging.modes import captar, solar, solar_only
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


def test_peak_demand_state_seed_sets_tracked_kw_and_month():
    """PeakDemandState.seed (#496) -- the coordinator's `seed_monthly_peak` boundary delegates
    here, so `_peak_demand`'s fields stay owned by this class regardless of which module seeds
    them (a MonthlyPeakSensor restore, `update()`'s own bookkeeping)."""
    state = PeakDemandState()
    state.seed(3.4, (2026, 7))
    assert state.tracked_kw == 3.4
    assert state.tracked_month == (2026, 7)


def test_peak_demand_state_seed_leaves_month_unchanged_when_none():
    state = PeakDemandState()
    state.tracked_month = (2026, 6)
    state.seed(3.4, None)
    assert state.tracked_kw == 3.4
    assert state.tracked_month == (2026, 6)


def test_peak_demand_state_seed_is_a_faithful_restore_not_a_clamp():
    """A negative kW passes through unchanged -- `update()` itself can produce one on a
    net-export month, so the seed path must not silently floor it to zero."""
    state = PeakDemandState()
    state.seed(-1.0, (2026, 7))
    assert state.tracked_kw == -1.0


def test_peak_demand_state_period_month_formats_tracked_month():
    state = PeakDemandState()
    state.tracked_month = (2026, 7)
    assert state.period_month == "2026-07"


def test_peak_demand_state_period_month_is_none_when_untracked():
    state = PeakDemandState()
    assert state.period_month is None


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


def test_soc_gate_resolver_first_call_always_reports_changed():
    """SocGateResolver.resolve (ADR-0012, T2.1) wraps engines/soc_target.py's
    resolve_active_soc_limit + the inline _last_active_soc_limit comparison it replaces: with
    no prior call there is no "last" value to compare against, so the very first resolve always
    reports changed -- mirroring the old code's None-vs-float first-cycle behavior."""
    resolver = SocGateResolver()
    limit, changed = resolver.resolve(
        80.0,
        solar_reserve_active=False,
        solar_reserve_soc=60.0,
        step_up_state=SolarStepUpState(),
    )
    assert limit == 80.0
    assert changed is True


def test_soc_gate_resolver_reports_unchanged_when_limit_is_stable():
    """A second resolve() call with the same inputs yields the same limit and is reported as
    unchanged -- the change-detection half of ADR-0012's replacement for
    _last_active_soc_limit."""
    resolver = SocGateResolver()
    resolver.resolve(
        80.0,
        solar_reserve_active=False,
        solar_reserve_soc=60.0,
        step_up_state=SolarStepUpState(),
    )
    limit, changed = resolver.resolve(
        80.0,
        solar_reserve_active=False,
        solar_reserve_soc=60.0,
        step_up_state=SolarStepUpState(),
    )
    assert changed is False
    assert limit == 80.0


def test_soc_gate_resolver_reports_changed_when_limit_moves():
    """A resolve() call whose resulting limit differs from the previous one is reported as
    changed -- here the second call's solar_reserve_active=True flips the R7 row-1 solar-reserve
    cap on, moving the effective limit from the override (80.0) to the reserve SOC (60.0)."""
    resolver = SocGateResolver()
    resolver.resolve(
        80.0,
        solar_reserve_active=False,
        solar_reserve_soc=60.0,
        step_up_state=SolarStepUpState(),
    )
    limit, changed = resolver.resolve(
        80.0,
        solar_reserve_active=True,
        solar_reserve_soc=60.0,
        step_up_state=SolarStepUpState(),
    )
    assert changed is True
    assert limit == 60.0


def test_soc_gate_resolver_reports_unchanged_when_resolved_limit_matches_despite_different_inputs():
    """Change detection keys on the *resolved limit*, not the raw inputs -- an implementation
    that compared arguments instead of the resolved value would report `changed` here, since
    override and step_up_state both differ between the two calls, even though both resolve to
    the same 80.0 limit (row 2's stepped_pct wins over the override either way, R7)."""
    resolver = SocGateResolver()
    resolver.resolve(
        80.0,
        solar_reserve_active=False,
        solar_reserve_soc=60.0,
        step_up_state=SolarStepUpState(),
    )
    limit, changed = resolver.resolve(
        50.0,
        solar_reserve_active=False,
        solar_reserve_soc=60.0,
        step_up_state=SolarStepUpState(stepped_pct=80.0),
    )
    assert changed is False
    assert limit == 80.0


# --- resolve_deadline_urgency (ADR-0006 steps 3-6; extracted per #506) ---


def _base_deadline_urgency_kwargs(**overrides):
    """Shared defaults for resolve_deadline_urgency's many keyword arguments -- each test
    below overrides only the handful that matter for its scenario, mirroring the production
    function's own shared-kwargs dedup rationale (#506)."""
    kwargs = dict(
        deadline_resolvable=True,
        ev_soc=50.0,
        active_mode=MODE_OFF,
        active_soc_limit=80.0,
        deadline_today=None,
        now_dt=datetime(2026, 7, 27, 10, 0),
        effective_battery_capacity_kwh=10.0,
        voltage=230.0,
        surplus_w=0.0,
        max_current_a=32.0,
        auto_dispatchable=False,
        solar_installed=False,
        captar_available=True,
        solar_start_threshold_w=1000.0,
        sun_is_up=False,
        sun_is_down=False,
        low_tariff_active=False,
        solar_reserve_active=False,
        mode_desired_current=lambda mode: 0.0,
    )
    kwargs.update(overrides)
    return kwargs


def test_resolve_deadline_urgency_short_circuits_when_not_resolvable():
    """`deadline_resolvable=False` (the coordinator's own, already-computed `status in
    CHARGEABLE_STATES and ev_soc is not None` check -- disconnected, or ev_soc unknown/
    unmapped) short-circuits before ever calling `mode_desired_current`: no baseline-mode dry
    run, no deadline/urgency computation at all, mirroring the original inline guard exactly.
    The function itself no longer re-derives this from `status`/`ev_soc` (#506 Minor 1: a
    second copy of the same predicate on this side of the module boundary was the exact
    lockstep-editing hazard #506 exists to remove) -- the coordinator-level guard is covered
    end-to-end by tests/test_coordinator.py's own disconnected/no-ev_soc scenarios."""

    def _fail_if_called(mode):
        raise AssertionError("mode_desired_current must not be called when not resolvable")

    result = resolve_deadline_urgency(
        **_base_deadline_urgency_kwargs(
            deadline_resolvable=False,
            ev_soc=None,
            auto_dispatchable=False,
            mode_desired_current=_fail_if_called,
        )
    )
    assert result.required.required_a is None
    assert result.required.urgent is False
    assert result.required.unreachable is False
    assert result.urgent is False
    assert result.resolved_mode is None


def test_resolve_deadline_urgency_no_deadline_resolved_means_no_urgency():
    """`deadline_today=None` (R14's own "no deadline" outcome) means resolve_required_current
    returns required_a=None/urgent=False/unreachable=False regardless of SOC/capacity --
    mirrored here even under Auto dispatch, where baseline/real mode selection still runs
    (deadline is not a precondition for mode selection itself, only for urgency)."""
    result = resolve_deadline_urgency(
        **_base_deadline_urgency_kwargs(
            deadline_today=None,
            auto_dispatchable=True,
            solar_installed=True,
            sun_is_up=True,
            surplus_w=2000.0,
            solar_start_threshold_w=1000.0,
        )
    )
    assert result.required.required_a is None
    assert result.urgent is False
    # Both select_mode calls see the same urgent=False input and identical remaining
    # arguments -- row 3 (solar capability + sun up + sufficient surplus) fires for both,
    # so the real resolution matches the baseline exactly (#506's dedup, made observable).
    assert result.resolved_mode == MODE_SOLAR


def test_resolve_deadline_urgency_manual_profile_baseline_is_the_active_mode_itself():
    """When Auto isn't dispatching (Manual profile, or Auto with no ev_soc role mapped),
    the baseline is simply the already-active mode (NF2: Manual's own selection), never
    routed through `select_mode` -- and `resolved_mode` stays None since only Auto ever
    reassigns `active_mode` from this result."""
    calls = []

    def fake_mode_desired_current(mode):
        calls.append(mode)
        return 5.0  # Power's own baseline desired current in this scenario

    result = resolve_deadline_urgency(
        **_base_deadline_urgency_kwargs(
            active_mode=MODE_POWER,
            auto_dispatchable=False,
            deadline_today=time(11, 0),
            ev_soc=50.0,
            active_soc_limit=80.0,
            effective_battery_capacity_kwh=10.0,
            mode_desired_current=fake_mode_desired_current,
        )
    )
    assert calls == [MODE_POWER]  # baseline dry-run used the active mode, not a selected one
    # energy_needed = 10 * (80-50)/100 = 3 kWh over 1h = 3000 W = 13.04 A > baseline (5.0 A)
    assert result.urgent is True
    assert result.resolved_mode is None  # Manual: coordinator never reassigns active_mode


def test_resolve_deadline_urgency_escalates_from_baseline_off_to_captar_when_urgent():
    """Auto dispatch, required current exceeds the row-3/4/5 baseline (Off, since neither
    solar nor low-tariff/sun-down conditions match) -- the real (non-baseline) select_mode
    call sees the escalated `urgent=True` and jumps straight to row 2 (Captar), proving the
    two select_mode calls inside resolve_deadline_urgency use the real, not the baseline,
    urgent value for the final resolution (#506)."""
    calls = []

    def fake_mode_desired_current(mode):
        calls.append(mode)
        return 0.0  # Off's own baseline desired current is always 0 A

    result = resolve_deadline_urgency(
        **_base_deadline_urgency_kwargs(
            active_mode=MODE_OFF,
            auto_dispatchable=True,
            deadline_today=time(11, 0),
            ev_soc=50.0,
            active_soc_limit=80.0,
            effective_battery_capacity_kwh=10.0,
            solar_installed=False,
            captar_available=True,
            sun_is_up=False,
            sun_is_down=False,  # row 4 doesn't match at baseline -- falls through to Off
            low_tariff_active=False,
            solar_reserve_active=False,
            mode_desired_current=fake_mode_desired_current,
        )
    )
    assert calls == [MODE_OFF]  # baseline (rows 3-5, urgent=False) resolved to Off
    # energy_needed = 10 * (80-50)/100 = 3 kWh over 1h = 3000 W = 13.04 A > baseline (0 A)
    assert result.required.urgent is True
    assert result.required.unreachable is False  # 13.04 A < max_current_a (32.0)
    assert result.urgent is True
    assert result.resolved_mode == MODE_CAPTAR  # row 2: urgent -> Captar (available)


def test_resolve_deadline_urgency_no_escalation_when_baseline_already_meets_deadline():
    """Auto dispatch where the baseline mode's own desired current (Solar, row 3) already
    exceeds what the deadline requires -- urgent stays False and the real select_mode call,
    seeing the identical (urgent=False) input as the baseline call, resolves to the same
    mode. Proves the two calls agree when nothing escalates, not just when it does."""

    def fake_mode_desired_current(mode):
        return 16.0 if mode == MODE_SOLAR else 0.0

    result = resolve_deadline_urgency(
        **_base_deadline_urgency_kwargs(
            active_mode=MODE_OFF,
            auto_dispatchable=True,
            deadline_today=time(11, 0),
            ev_soc=79.0,
            active_soc_limit=80.0,
            effective_battery_capacity_kwh=10.0,
            solar_installed=True,
            captar_available=True,
            sun_is_up=True,
            surplus_w=2000.0,
            solar_start_threshold_w=1000.0,
            mode_desired_current=fake_mode_desired_current,
        )
    )
    # energy_needed = 10 * (80-79)/100 = 0.1 kWh over 1h = 100 W = 0.435 A < baseline (16 A)
    assert result.required.urgent is False
    assert result.urgent is False
    assert result.resolved_mode == MODE_SOLAR  # same row-3 match as the baseline, unchanged
