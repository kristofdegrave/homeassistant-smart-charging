"""Plain-pytest tests for the coordinator's internal cycle-decomposition units (ADR-0012)."""

from datetime import datetime

from custom_components.smart_charging.const import STATE_CHARGING
from custom_components.smart_charging.coordinator_cycle import CycleContext


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
