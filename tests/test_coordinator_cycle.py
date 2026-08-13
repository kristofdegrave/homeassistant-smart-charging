"""Plain-pytest tests for the coordinator's internal cycle-decomposition units
(ADR-0012, ADR-0023)."""

from datetime import datetime, time
from unittest.mock import patch

import pytest

from custom_components.smart_charging.config import SmartChargingConfig
from custom_components.smart_charging.const import (
    MODE_CAPTAR,
    MODE_OFF,
    MODE_POWER,
    MODE_SOLAR,
    MODE_SOLAR_ONLY,
    PROFILE_AUTO,
    PROFILE_MANUAL,
    ROUND_DOWN,
    ROUND_NEAREST,
    STATE_CHARGING,
    STATE_CONNECTED,
    STATE_DISCONNECTED,
)
from custom_components.smart_charging.coordinator_cycle import (
    CycleContext,
    DeadlineUnreachableEdge,
    ModeHandler,
    PeakDemandState,
    SocGateResolver,
    SolarStepUpGate,
    _CaptarModeHandler,
    _OffModeHandler,
    _PowerModeHandler,
    _SolarModeHandler,
    _SolarOnlyModeHandler,
    build_mode_handlers,
    resolve_deadline_urgency,
    resolve_solar_reserve_gate,
)
from custom_components.smart_charging.engines.soc_target import SolarStepUpState
from custom_components.smart_charging.modes import captar, solar, solar_only
from custom_components.smart_charging.modes._phase import Phase
from tests.config_factory import make_test_config


def _config(**overrides) -> SmartChargingConfig:
    """This suite's own SmartChargingConfig baseline, layered on tests/config_factory.py's
    shared production-DEFAULT_*-seeded factory (issue #570 follow-up: three near-identical
    per-suite factories collapsed to one) -- every field a real setup would populate, since the
    handlers now read typed attributes rather than `.get(CONF_X, DEFAULT_X)`/bracket lookups on
    a plain dict. `smoothing_window` is this file's own long-standing baseline (distinct from
    the production default `make_test_config` otherwise uses). `**overrides` takes the
    dataclass's own field names."""
    return make_test_config(smoothing_window=1, **overrides)


def test_cycle_context_constructs_with_required_fields_and_defaults():
    """CycleContext (ADR-0012) exposes all defaulted fields with their documented starting
    values -- the required fields (status/net_w/charger_w/voltage/now/now_dt) construct with no
    defaults. `surplus_w` starts at a meaningful zero-surplus value (the value _run_cycle's old
    loose locals used to start with); the five bool fields keep their original, genuinely-correct
    starting values (only ever read via plain truthiness, so `None` would buy no fail-loudness and
    would silently invert `low_tariff_active`'s documented-correct `True` default). The three
    numeric fields resolved partway through _run_cycle -- monthly_peak_kw/effective_peak_limit_kw/
    active_soc_limit (issue #564) -- start at `None`, not a same-typed placeholder, so a future
    premature arithmetic/comparison read fails loudly instead of silently computing on a
    plausible-looking wrong value."""
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
    assert ctx.monthly_peak_kw is None
    assert ctx.effective_peak_limit_kw is None
    assert ctx.active_soc_limit is None
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


def test_cycle_context_unresolved_numeric_fields_raise_loudly_on_premature_use():
    """issue #564: the whole point of `None` over a same-typed placeholder for the three
    numeric fields resolved partway through _run_cycle -- a hypothetical future ModeHandler
    reading e.g. `ctx.effective_peak_limit_kw`/`ctx.active_soc_limit` before `_run_cycle`
    resolves them now gets an immediate TypeError on arithmetic/comparison, not a
    silently-computed wrong answer from a plausible-looking 0.0. (The five bool fields are
    deliberately excluded -- see test_cycle_context_constructs_with_required_fields_and_defaults's
    docstring for why `None` wouldn't fail loudly for those.)"""
    ctx = CycleContext(
        status=STATE_CHARGING,
        net_w=0.0,
        charger_w=0.0,
        voltage=230.0,
        now=0.0,
        now_dt=None,
        ev_soc=50.0,
    )
    with pytest.raises(TypeError):
        ctx.effective_peak_limit_kw * 1000.0
    with pytest.raises(TypeError):
        assert ctx.ev_soc >= ctx.active_soc_limit
    with pytest.raises(TypeError):
        ctx.monthly_peak_kw + 1.0


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
    """Every _*ModeHandler (ADR-0012 Sec 3.4) satisfies the ModeHandler Protocol's
    desired_current(ctx, state) -> (current, new_state) / idle_state() / is_soc_gated /
    is_solar_mode shape -- a structural check that all five adapters share one call surface,
    not a behavior test. ModeHandler is a plain (not @runtime_checkable) Protocol per the
    design doc, so conformance is checked by static typing and by each adapter exposing the
    right callables/attributes, not by isinstance()."""
    handlers: list[ModeHandler] = [
        _OffModeHandler(),
        _PowerModeHandler(lambda: 10.0),
        _SolarModeHandler(_config()),
        _SolarOnlyModeHandler(_config()),
        _CaptarModeHandler(_config()),
    ]
    for handler in handlers:
        assert callable(handler.desired_current)
        assert callable(handler.idle_state)
        assert isinstance(handler.is_soc_gated, bool)
        assert isinstance(handler.is_solar_mode, bool)


def test_mode_handler_is_soc_gated_and_is_solar_mode_per_mode():
    """Issue #561: these two per-mode facts replace the coordinator's old
    _SOC_GATED_MODES/_SOLAR_MODES tuples. Off/Power never gate on SOC and are never "solar
    modes" for R8/R9's Auto-only preconditions; Solar/SolarOnly are both SOC-gated and solar
    modes; Captar is SOC-gated but not a solar mode (R8/R9 only ever apply to Solar/SolarOnly,
    resolution-rules.md)."""
    assert _OffModeHandler().is_soc_gated is False
    assert _OffModeHandler().is_solar_mode is False
    assert _PowerModeHandler(lambda: 10.0).is_soc_gated is False
    assert _PowerModeHandler(lambda: 10.0).is_solar_mode is False
    assert _SolarModeHandler(_config()).is_soc_gated is True
    assert _SolarModeHandler(_config()).is_solar_mode is True
    assert _SolarOnlyModeHandler(_config()).is_soc_gated is True
    assert _SolarOnlyModeHandler(_config()).is_solar_mode is True
    assert _CaptarModeHandler(_config()).is_soc_gated is True
    assert _CaptarModeHandler(_config()).is_solar_mode is False


def test_mode_handler_idle_state_per_mode():
    """Issue #561: idle_state() replaces the coordinator's old Captar-vs-solar ternary that
    picked each SOC-gated mode's idle state by name. Off/Power return None -- neither is ever
    stored in the coordinator's _mode_state (design doc Sec 3.4), so their idle_state() is
    never actually read; it exists only to satisfy the Protocol uniformly."""
    assert _OffModeHandler().idle_state() is None
    assert _PowerModeHandler(lambda: 10.0).idle_state() is None
    assert _SolarModeHandler(_config()).idle_state() == solar.SolarState.idle()
    assert _SolarOnlyModeHandler(_config()).idle_state() == solar_only.SolarOnlyState.idle()
    assert _CaptarModeHandler(_config()).idle_state() == captar.CaptarState.idle()


def test_build_mode_handlers_wires_all_five_modes_with_correct_types_and_facts():
    """Issue #567: build_mode_handlers is coordinator.py's only way to construct the mode-handler
    registry -- it must not import the five _*ModeHandler classes directly across the module
    boundary. Pins the same wiring coordinator.__init__ used to do by hand: one entry per mode
    key, each the right handler type, each carrying its documented is_soc_gated/is_solar_mode
    facts (test_mode_handler_is_soc_gated_and_is_solar_mode_per_mode's per-class assertions,
    reached this time through the factory)."""
    handlers = build_mode_handlers(_config(), lambda: 10.0)

    assert set(handlers) == {MODE_OFF, MODE_POWER, MODE_SOLAR, MODE_SOLAR_ONLY, MODE_CAPTAR}
    assert isinstance(handlers[MODE_OFF], _OffModeHandler)
    assert isinstance(handlers[MODE_POWER], _PowerModeHandler)
    assert isinstance(handlers[MODE_SOLAR], _SolarModeHandler)
    assert isinstance(handlers[MODE_SOLAR_ONLY], _SolarOnlyModeHandler)
    assert isinstance(handlers[MODE_CAPTAR], _CaptarModeHandler)

    for mode, is_soc_gated, is_solar_mode in (
        (MODE_OFF, False, False),
        (MODE_POWER, False, False),
        (MODE_SOLAR, True, True),
        (MODE_SOLAR_ONLY, True, True),
        (MODE_CAPTAR, True, False),
    ):
        assert handlers[mode].is_soc_gated is is_soc_gated
        assert handlers[mode].is_solar_mode is is_solar_mode


def test_build_mode_handlers_threads_the_same_config_into_solar_only_and_captar_handlers():
    """A construction-site typo swapping in a stray fresh config for one of the three
    config-reading handlers (Solar/SolarOnly/Captar) would pass the type/facts checks above
    unnoticed -- pin that build_mode_handlers threads the SAME SmartChargingConfig OBJECT
    (not just an equal copy) into all three, both directly (identity) and behaviorally (by
    round-tripping a real config value through each handler's own dispatch and checking it
    took effect). The identity half matters beyond this test: tests/helpers.py's
    `replace_coordinator_config` relies on every mode handler holding the exact object
    `coordinator._config` points to, not a separate copy, to propagate a config change
    end-to-end."""
    config = _config(
        solar_start_threshold_w=500.0,
        min_current=6.0,
        solar_hold_min=5,
        solar_cooldown_min=5,
        solar_only_start_threshold_w=700.0,
        solar_only_strategy=ROUND_NEAREST,
        solar_only_midpoint=0.5,
        max_current=16.0,
        captar_cooldown_min=30,
    )
    handlers = build_mode_handlers(config, lambda: 10.0)
    assert handlers[MODE_SOLAR]._config is config
    assert handlers[MODE_SOLAR_ONLY]._config is config
    assert handlers[MODE_CAPTAR]._config is config
    ctx = CycleContext(
        status=STATE_CHARGING,
        net_w=0.0,
        charger_w=0.0,
        voltage=230.0,
        now=0.0,
        now_dt=None,
        surplus_w=400.0,  # below CONF_SOLAR_START_THRESHOLD_W/CONF_SOLAR_ONLY_START_THRESHOLD_W
    )

    solar_current, _ = handlers[MODE_SOLAR].desired_current(ctx, solar.SolarState.idle())
    solar_only_current, _ = handlers[MODE_SOLAR_ONLY].desired_current(
        ctx, solar_only.SolarOnlyState.idle()
    )
    captar_current, _ = handlers[MODE_CAPTAR].desired_current(ctx, captar.CaptarState.idle())

    # Below both configured start thresholds -- both solar handlers stay idle at 0 A, proving
    # THEIR OWN configured threshold (not a stray fresh-config default) gated the decision.
    assert solar_current == 0.0
    assert solar_only_current == 0.0
    # Captar's own configured max_current is what it commands once idle -> active.
    assert captar_current == config.max_current


def test_build_mode_handlers_power_handler_reads_target_current_getter_live():
    """_PowerModeHandler must be wired to the live getter passed in, not a snapshot of its
    value at construction time -- the getter is coordinator.py's `lambda: self.target_current`,
    which changes across cycles."""
    current = [5.0]
    handlers = build_mode_handlers(_config(), lambda: current[0])
    ctx = CycleContext(
        status=STATE_CHARGING, net_w=0.0, charger_w=0.0, voltage=230.0, now=1.0, now_dt=None
    )

    desired_before, _ = handlers[MODE_POWER].desired_current(ctx, None)
    current[0] = 12.0
    desired_after, _ = handlers[MODE_POWER].desired_current(ctx, None)

    assert desired_before == 5.0
    assert desired_after == 12.0


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
    config = _config(
        solar_start_threshold_w=150.0,
        min_current=6.0,
        solar_hold_min=5.0,
        solar_cooldown_min=2.0,
    )
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
    config = _config(
        solar_only_start_threshold_w=1300.0,
        solar_cooldown_min=2.0,
        solar_only_strategy=ROUND_DOWN,
        solar_only_midpoint=0.5,
    )
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
    # cooldown_minutes=1.0 is deliberately distinct from this file's _config() default (10.0)
    # (code-reviewer finding on PR #451); exercised via the cooldown-elapsing assertions.
    config = _config(max_current=32.0, captar_cooldown_min=1.0)
    handler = _CaptarModeHandler(config)
    ctx = CycleContext(
        status=STATE_CHARGING, net_w=0.0, charger_w=0.0, voltage=230.0, now=0.0, now_dt=None
    )
    current, new_state = handler.desired_current(ctx, captar.CaptarState.idle())
    assert current == 32.0
    assert new_state.phase == Phase.CHARGING

    # Prove cooldown_minutes=1.0 is actually threaded through, not just present in the
    # config object: at 59s (< 1 min) cooldown still blocks; at 61s (> 1 min) it's re-armed.
    cooldown_state = captar.CaptarState(Phase.COOLDOWN, phase_started_at=0.0)
    blocked, _ = handler.desired_current(ctx, cooldown_state)
    assert blocked == 0.0
    ctx_later = CycleContext(
        status=STATE_CHARGING, net_w=0.0, charger_w=0.0, voltage=230.0, now=61.0, now_dt=None
    )
    rearmed, rearmed_state = handler.desired_current(ctx_later, cooldown_state)
    assert rearmed == 32.0
    assert rearmed_state.phase == Phase.CHARGING


# issue #570: `test_captar_mode_handler_uses_default_cooldown_when_config_key_absent` (the
# fallback-when-the-key-is-absent case) was removed here -- SmartChargingConfig.captar_cooldown_min
# is now a required, always-populated field (resolved once in __init__.py), so "the config key is
# absent" is no longer a reachable state for _CaptarModeHandler to fall back from.


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


# --- DeadlineUnreachableEdge (ADR-0024: pure True->False edge detection for the paired
# DeadlineUnreachableCleared event) ---


def test_deadline_unreachable_edge_first_call_reports_no_clear():
    """ADR-0024: the prior-cycle flag starts False, so a first resolve() reports
    cleared=False for BOTH inputs -- unlike SocGateResolver's first call, which always
    reports changed=True. There is no occasion to clear before one has been observed, and
    a spurious clear on the very first cycle would re-arm a consumer that never notified."""
    edge = DeadlineUnreachableEdge()
    assert edge.resolve(True) == (True, False)


def test_deadline_unreachable_edge_first_call_reports_no_clear_when_reachable():
    edge = DeadlineUnreachableEdge()
    assert edge.resolve(False) == (False, False)


def test_deadline_unreachable_edge_reports_cleared_on_true_to_false():
    """The one edge the event exists for: the prior cycle resolved unreachable=True and this
    one resolves False -> (False, True)."""
    edge = DeadlineUnreachableEdge()
    edge.resolve(True)
    assert edge.resolve(False) == (False, True)


def test_deadline_unreachable_edge_reports_no_clear_while_still_unreachable():
    """True -> True is the level signal's territory (Task 5.2 re-fires
    DeadlineUnreachableNotified there); no clear edge, so (True, False)."""
    edge = DeadlineUnreachableEdge()
    edge.resolve(True)
    assert edge.resolve(True) == (True, False)


def test_deadline_unreachable_edge_reports_no_clear_on_false_to_false():
    """Steady-state reachable cycles must stay silent -- (False, False) -- or the consumer's
    latch would be re-armed on every cycle and the event would become a second level signal."""
    edge = DeadlineUnreachableEdge()
    edge.resolve(False)
    assert edge.resolve(False) == (False, False)


def test_deadline_unreachable_edge_clears_only_once_per_occasion():
    """True -> False -> False fires the clear on the first False cycle only; the flag is
    updated on every resolve() call, so the second False is an ordinary no-edge cycle."""
    edge = DeadlineUnreachableEdge()
    edge.resolve(True)
    assert edge.resolve(False) == (False, True)
    assert edge.resolve(False) == (False, False)


def test_deadline_unreachable_edge_reports_cleared_again_on_a_second_occasion():
    """True -> False -> True -> False: the detector is re-usable, so a later occasion gets its
    own clear -- this is the per-occasion behavior ADR-0024's Decision exists to produce."""
    edge = DeadlineUnreachableEdge()
    edge.resolve(True)
    assert edge.resolve(False) == (False, True)
    edge.resolve(True)
    assert edge.resolve(False) == (False, True)


# --- SolarStepUpGate (ADR-0023, T0.1: R8 solar step-up gating, coordinator.py:306-326) ---


def test_solar_step_up_gate_starts_at_default_state():
    gate = SolarStepUpGate()
    assert gate.state == SolarStepUpState()


def test_solar_step_up_gate_steps_up_when_solar_mode_charging_and_within_threshold():
    """Anchored to tests/engines/test_soc_target.py::test_steps_up_once_within_threshold's own
    fixture values -- the gate must produce the identical resolve_solar_step_up outcome for an
    equivalent is_solar_mode_charging=True call, proving the wrapper computes the gate correctly,
    not just that it calls something."""
    gate = SolarStepUpGate()
    gate.resolve(
        profile=PROFILE_AUTO,
        mode_is_solar=True,
        status=STATE_CHARGING,
        soc=78.5,
        default_limit=80.0,
        step_threshold_pp=2.0,
        step_pp=5.0,
        max_solar_soc=100.0,
    )
    assert gate.state == SolarStepUpState(stepped_pct=85.0)


def test_solar_step_up_gate_clears_when_profile_is_manual():
    """is_solar_mode_charging's PROFILE_AUTO-only gate (R8) suppresses the step even with a
    solar mode charging within threshold -- Manual never steps up. Seeds an already-stepped-up
    state first so this exercises the reset-to-default branch (engines/soc_target.py's
    is_solar_mode_charging=False row), not merely "starts at default and stays there"."""
    gate = SolarStepUpGate()
    gate.state = SolarStepUpState(stepped_pct=85.0)
    gate.resolve(
        profile=PROFILE_MANUAL,
        mode_is_solar=True,
        status=STATE_CHARGING,
        soc=78.5,
        default_limit=80.0,
        step_threshold_pp=2.0,
        step_pp=5.0,
        max_solar_soc=100.0,
    )
    assert gate.state == SolarStepUpState()


def test_solar_step_up_gate_clears_when_mode_is_not_solar():
    """Seeded stepped-up (see test above) so this proves the reset branch, not a no-op."""
    gate = SolarStepUpGate()
    gate.state = SolarStepUpState(stepped_pct=85.0)
    gate.resolve(
        profile=PROFILE_AUTO,
        mode_is_solar=False,
        status=STATE_CHARGING,
        soc=78.5,
        default_limit=80.0,
        step_threshold_pp=2.0,
        step_pp=5.0,
        max_solar_soc=100.0,
    )
    assert gate.state == SolarStepUpState()


def test_solar_step_up_gate_clears_when_disconnected():
    """Seeded stepped-up (see test above) so this proves the reset branch, not a no-op. Also
    the hard requirement that `state` is a plain assignable public attribute (T2.1 needs
    `coord._step_up_gate.state = SolarStepUpState(...)` to work as a drop-in test-seeding
    replacement) -- a read-only property here would fail this seeding step, not just T2.1's."""
    gate = SolarStepUpGate()
    gate.state = SolarStepUpState(stepped_pct=85.0)
    gate.resolve(
        profile=PROFILE_AUTO,
        mode_is_solar=True,
        status=STATE_DISCONNECTED,
        soc=78.5,
        default_limit=80.0,
        step_threshold_pp=2.0,
        step_pp=5.0,
        max_solar_soc=100.0,
    )
    assert gate.state == SolarStepUpState()


def test_solar_step_up_gate_treats_none_soc_as_zero():
    """Mirrors coordinator.py's own `soc=ev_soc if ev_soc is not None else 0.0` -- a
    disconnected-adjacent read of None must not raise, and 0.0 never triggers a step (soc=0.0 is
    never within step_threshold_pp of any positive current_limit here)."""
    gate = SolarStepUpGate()
    gate.resolve(
        profile=PROFILE_AUTO,
        mode_is_solar=True,
        status=STATE_CHARGING,
        soc=None,
        default_limit=80.0,
        step_threshold_pp=2.0,
        step_pp=5.0,
        max_solar_soc=100.0,
    )
    assert gate.state == SolarStepUpState()


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
        solar_available=False,
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
            solar_available=True,
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
            solar_available=False,
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
            solar_available=True,
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


def test_resolve_deadline_urgency_consults_the_auto_policy_registry_entry():
    """Proves BOTH call sites (baseline urgent=False, and the real resolution) genuinely route
    through PROFILE_POLICIES[PROFILE_AUTO] -- the five behavior-preservation tests above would
    stay green even if only one of the two call sites were swapped (or neither), since they
    assert on resolve_deadline_urgency's output, not its import path (ADR-0017 T3)."""
    with patch(
        "custom_components.smart_charging.coordinator_cycle.PROFILE_POLICIES"
    ) as mock_policies:
        mock_policies.__getitem__.return_value.select.return_value = MODE_OFF
        result = resolve_deadline_urgency(
            **_base_deadline_urgency_kwargs(
                auto_dispatchable=True,
                deadline_today=time(11, 0),
                ev_soc=50.0,
                active_soc_limit=80.0,
            )
        )
        # auto_dispatchable=True with no deadline slack (see the sibling escalation test above
        # for the same energy-needed math) makes both call sites fire: the baseline dry run
        # (urgent=False) and the real resolution (urgent=True, once required exceeds baseline).
        mock_policies.__getitem__.assert_called_with(PROFILE_AUTO)
        select = mock_policies.__getitem__.return_value.select
        assert [call.kwargs["urgent"] for call in select.call_args_list] == [False, True]
        # The registry's return value is what actually lands in resolved_mode -- not just
        # looked up and ignored.
        assert result.resolved_mode == MODE_OFF


# --- resolve_solar_reserve_gate (ADR-0023) ---


def test_resolve_solar_reserve_gate_active_when_all_conditions_hold():
    """Anchored to engines/test_soc_target.py::test_reserve_active_when_all_conditions_hold's
    own fixture values."""
    assert (
        resolve_solar_reserve_gate(
            profile=PROFILE_AUTO,
            home_day_flag=True,
            sun_is_down=True,
            forecast_kwh=15.0,
            forecast_threshold_kwh=12.0,
            deadline_tomorrow_resolved=False,
        )
        is True
    )


def test_resolve_solar_reserve_gate_treats_none_forecast_as_zero():
    """Mirrors coordinator.py's own `forecast_kwh if forecast_kwh is not None else 0.0` -- an
    unmapped/unavailable forecast role must not raise and must never activate the cap."""
    assert (
        resolve_solar_reserve_gate(
            profile=PROFILE_AUTO,
            home_day_flag=True,
            sun_is_down=True,
            forecast_kwh=None,
            forecast_threshold_kwh=12.0,
            deadline_tomorrow_resolved=False,
        )
        is False
    )


def test_resolve_solar_reserve_gate_inactive_under_manual():
    """Anchored to engines/test_soc_target.py::test_reserve_inactive_under_manual."""
    assert (
        resolve_solar_reserve_gate(
            profile=PROFILE_MANUAL,
            home_day_flag=True,
            sun_is_down=True,
            forecast_kwh=15.0,
            forecast_threshold_kwh=12.0,
            deadline_tomorrow_resolved=False,
        )
        is False
    )


def test_resolve_solar_reserve_gate_inactive_when_deadline_resolved_for_tomorrow():
    """Anchored to engines/test_soc_target.py::
    test_reserve_inactive_when_deadline_resolved_for_tomorrow -- proves
    deadline_tomorrow_resolved is actually threaded through to the wrapped engine call, not
    just accepted and ignored (all other tests here pass False)."""
    assert (
        resolve_solar_reserve_gate(
            profile=PROFILE_AUTO,
            home_day_flag=True,
            sun_is_down=True,
            forecast_kwh=15.0,
            forecast_threshold_kwh=12.0,
            deadline_tomorrow_resolved=True,
        )
        is False
    )
