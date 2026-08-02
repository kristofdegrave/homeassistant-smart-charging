"""Plain-pytest tests for the coordinator's internal cycle-decomposition units (ADR-0012)."""

from datetime import datetime

from custom_components.smart_charging.const import STATE_CHARGING
from custom_components.smart_charging.coordinator_cycle import (
    CycleContext,
    PeakDemandState,
    SocGateResolver,
)
from custom_components.smart_charging.engines.soc_target import SolarStepUpState


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
