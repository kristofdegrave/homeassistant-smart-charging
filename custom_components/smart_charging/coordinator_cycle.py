"""Coordinator-internal cycle decomposition (ADR-0012): CycleContext, PeakDemandState,
SocGateResolver, and the ModeHandler Strategy. Imported only by coordinator.py. Pure -- no HA
imports (mirrors engines/ purity, ADR-0009/0010), even though these aren't engines themselves
(system-design Sec 4 rule 4: an engine may not call another engine; these call engines)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass  # deliberately not frozen -- steps mutate fields in place as each value resolves
class CycleContext:
    """Carries one cycle's readings/derived values between _run_cycle's steps, replacing the
    loose local variables ADR-0012 flagged. Filled progressively as steps resolve each value --
    not everything is known at construction time."""

    status: str
    net_w: float  # raw, not the smoothed reading (coordinator.py's separate smoothed_net_w)
    charger_w: float
    voltage: float
    now: float
    now_dt: datetime | None  # None only in the Task 3.3 dry-run construction
    ev_soc: float | None = None
    surplus_w: float = 0.0
    monthly_peak_kw: float = 0.0
    effective_peak_limit_kw: float = 0.0
    active_soc_limit: float = 0.0
    urgent: bool = False
    sun_is_up: bool = False
    sun_is_down: bool = False
    low_tariff_active: bool = True
    solar_reserve_active: bool = False
