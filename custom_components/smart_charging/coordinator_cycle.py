"""Coordinator-internal cycle decomposition: CycleContext, PeakDemandState, SocGateResolver, and
the ModeHandler Strategy (ADR-0012); SolarStepUpGate, resolve_solar_reserve_gate, and
resolve_deadline_urgency (ADR-0023).
Imported only by coordinator.py. Pure -- no HA imports (mirrors engines/ purity, ADR-0009/0010),
even though these aren't engines themselves (system-design Sec 4 rule 4: an engine may not call
another engine; these call engines).
The five _*ModeHandler classes stay private -- build_mode_handlers() is the only construction
site coordinator.py may reach across the module boundary for (issue #567)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any, Protocol

from .const import (
    CHARGEABLE_STATES,
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
    MODE_SOLAR_ONLY,
    PROFILE_AUTO,
)
from .engines.capability_gate import resolve_available_modes
from .engines.deadline import RequiredCurrentResult, resolve_required_current
from .engines.peak_demand_tracker import update_monthly_peak_demand
from .engines.signal_conditioning import smooth_net_power
from .engines.soc_target import (
    SolarStepUpState,
    resolve_active_soc_limit,
    resolve_solar_reserve_active,
    resolve_solar_step_up,
)
from .modes import captar, power, solar, solar_only
from .profiles.policy import PROFILE_POLICIES

_WATTS_PER_KILOWATT = 1000.0


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


@dataclass  # deliberately not frozen -- update() mutates window/tracked_kw/tracked_month in place
class PeakDemandState:
    """Owns the coordinator's monthly-peak-demand bookkeeping (project-plan E5 / Power-MVP Task
    1.3), replacing the three loose _peak_window/_peak_tracked_kw/_peak_tracked_month fields
    ADR-0012 flagged. Distinct from _peak_tracker (PeakBreachTracker, the R3 clamp's own
    breach-timer state) -- untouched by this decision, still threaded through the step-7 clamp
    call directly."""

    window: tuple[float, ...] = ()
    tracked_kw: float = 0.0
    tracked_month: tuple[int, int] | None = None

    def update(self, net_w: float, now_dt: datetime, *, window_size: int) -> float:
        """Fold `net_w` into the smoothing window and return the running monthly-peak kW.

        A month rollover resets the smoothing window too, not just tracked_kw (design doc
        Sec 6.4) -- else this cycle's "smoothed" reading would partly reflect last month.
        """
        current_month = (now_dt.year, now_dt.month)
        if current_month != self.tracked_month:
            self.window = ()
        smoothed_w, self.window = smooth_net_power(net_w, self.window, size=window_size)
        self.tracked_kw, self.tracked_month = update_monthly_peak_demand(
            smoothed_w / _WATTS_PER_KILOWATT, current_month, self.tracked_kw, self.tracked_month
        )
        return self.tracked_kw

    def seed(self, kw: float, month: tuple[int, int] | None) -> None:
        """Seed `tracked_kw`/`tracked_month` from a `MonthlyPeakSensor` restore (#496) -- the
        only other write path onto these fields besides `update()` itself, kept on this class
        so both stay behind one owner instead of a caller reaching into the fields directly.
        A faithful restore: no clamp, since `update()` itself can legitimately produce a
        negative `tracked_kw` on a net-export month (peak_demand_tracker.py's own contract).
        `month` is left unchanged when the restored state carries no `period_month` (an older
        stored value) -- the 15-minute `window` is deliberately never seeded (design doc
        Sec 6.4), matching `update()`'s own reset-on-rollover behavior."""
        self.tracked_kw = kw
        if month is not None:
            self.tracked_month = month

    @property
    def period_month(self) -> str | None:
        """`tracked_month` formatted as `"YYYY-MM"`, or None -- the one place that formats it,
        so callers (the coordinator's own read-direction boundary) never need to know
        `tracked_month`'s tuple shape."""
        if self.tracked_month is None:
            return None
        return f"{self.tracked_month[0]:04d}-{self.tracked_month[1]:02d}"


class ModeHandler(Protocol):
    """One thin adapter per mode module, wrapping its existing pure step()/desired_current()
    unchanged (ADR-0012) -- this decision only changes how the coordinator looks one up, not
    any mode module's own logic.

    `is_soc_gated`/`is_solar_mode`/`idle_state()` carry the per-mode facts the coordinator
    used to branch on by name (`_SOC_GATED_MODES`/`_SOLAR_MODES` tuples, and a
    Captar-vs-solar ternary picking each mode's idle state). Adding a mode with one of these
    properties now means giving its handler the right value/method, not adding a new branch
    or extending a tuple at every call site (issue #561)."""

    is_soc_gated: bool
    """R7: whether SOC reaching the active limit stops this mode. False for Off/Power."""

    is_solar_mode: bool
    """R8/R9: whether this mode counts as "charging on solar" for the step-up/reserve-cap
    Auto-only preconditions. True only for Solar/SolarOnly."""

    def desired_current(self, ctx: CycleContext, state: Any) -> tuple[float, Any]:
        """Return (desired_current_a, new_state); does not mutate ctx or state in place."""
        ...

    def idle_state(self) -> Any:
        """This mode's fresh/idle per-mode state (R7/R11) -- what disconnect, a mode switch,
        and the SOC gate all reset to. Only ever read when `is_soc_gated` is True; Off/Power
        return None since neither is ever stored in `_mode_state`."""
        ...


class _OffModeHandler:
    """Off mode has no modes/*.py module of its own to wrap -- commands 0 A unconditionally
    and passes state through unchanged, mirroring today's MODE_OFF branch, which never
    touches per-mode state (design doc Sec 3.4)."""

    is_soc_gated = False
    is_solar_mode = False

    def desired_current(self, ctx: CycleContext, state: Any) -> tuple[float, Any]:
        return 0.0, state

    def idle_state(self) -> None:
        return None


class _PowerModeHandler:
    """Wraps modes/power.py::desired_current unchanged. power.desired_current reads the
    coordinator's own mutable target_current (set externally by the number entity), not
    anything on CycleContext -- so this handler takes a zero-arg getter bound at construction
    (design doc Sec 3.4) rather than duplicating that value onto CycleContext each cycle."""

    is_soc_gated = False
    is_solar_mode = False

    def __init__(self, target_current_getter: Callable[[], float]) -> None:
        self._target_current_getter = target_current_getter

    def desired_current(self, ctx: CycleContext, state: Any) -> tuple[float, Any]:
        return power.desired_current(self._target_current_getter(), ctx.status), state

    def idle_state(self) -> None:
        return None


class _SolarModeHandler:
    """Wraps modes/solar.py::step unchanged."""

    is_soc_gated = True
    is_solar_mode = True

    def __init__(self, config: Mapping[str, Any]) -> None:
        self._config = config

    def desired_current(
        self, ctx: CycleContext, state: solar.SolarState
    ) -> tuple[float, solar.SolarState]:
        return solar.step(
            ctx.surplus_w,
            state,
            ctx.now,
            start_threshold_w=self._config[CONF_SOLAR_START_THRESHOLD_W],
            min_a=self._config[CONF_MIN_CURRENT],
            hold_minutes=self._config[CONF_SOLAR_HOLD_MIN],
            cooldown_minutes=self._config[CONF_SOLAR_COOLDOWN_MIN],
            voltage=ctx.voltage,
        )

    def idle_state(self) -> solar.SolarState:
        return solar.SolarState.idle()


class _SolarOnlyModeHandler:
    """Wraps modes/solar_only.py::step unchanged."""

    is_soc_gated = True
    is_solar_mode = True

    def __init__(self, config: Mapping[str, Any]) -> None:
        self._config = config

    def desired_current(
        self, ctx: CycleContext, state: solar_only.SolarOnlyState
    ) -> tuple[float, solar_only.SolarOnlyState]:
        return solar_only.step(
            ctx.surplus_w,
            state,
            ctx.now,
            start_threshold_w=self._config[CONF_SOLAR_ONLY_START_THRESHOLD_W],
            cooldown_minutes=self._config[CONF_SOLAR_COOLDOWN_MIN],
            strategy=self._config[CONF_SOLAR_ONLY_STRATEGY],
            midpoint=self._config[CONF_SOLAR_ONLY_MIDPOINT],
            voltage=ctx.voltage,
        )

    def idle_state(self) -> solar_only.SolarOnlyState:
        return solar_only.SolarOnlyState.idle()


class _CaptarModeHandler:
    """Wraps modes/captar.py::step unchanged."""

    is_soc_gated = True
    is_solar_mode = False

    def __init__(self, config: Mapping[str, Any]) -> None:
        self._config = config

    def desired_current(
        self, ctx: CycleContext, state: captar.CaptarState
    ) -> tuple[float, captar.CaptarState]:
        return captar.step(
            state,
            ctx.now,
            max_a=self._config[CONF_MAX_CURRENT],
            cooldown_minutes=self._config.get(
                CONF_CAPTAR_COOLDOWN_MIN, DEFAULT_CAPTAR_COOLDOWN_MIN
            ),
        )

    def idle_state(self) -> captar.CaptarState:
        return captar.CaptarState.idle()


def build_mode_handlers(
    config: Mapping[str, Any], target_current_getter: Callable[[], float]
) -> dict[str, ModeHandler]:
    """The ModeHandler registry's only construction site (issue #567) -- coordinator.py calls
    this instead of importing the five _*ModeHandler classes directly, keeping them private to
    this module. `target_current_getter` is threaded straight through to _PowerModeHandler
    (design doc Sec 3.4's own zero-arg getter, bound live rather than snapshotted); `config` to
    every handler that reads config values (all but Off/Power).

    Deliberately deviates from design doc Sec 3.4's own snippet, which shows coordinator.py
    building this same dict inline in `__init__` -- issue #567 moved that construction here so
    coordinator.py no longer needs to import the five private classes to do it; the wiring
    itself (which handler gets `config` vs. the getter) is unchanged from that snippet."""
    return {
        MODE_OFF: _OffModeHandler(),
        MODE_POWER: _PowerModeHandler(target_current_getter),
        MODE_SOLAR: _SolarModeHandler(config),
        MODE_SOLAR_ONLY: _SolarOnlyModeHandler(config),
        MODE_CAPTAR: _CaptarModeHandler(config),
    }


class SocGateResolver:
    """Owns SOC-limit resolution + change detection (ADR-0012), replacing the inline
    resolve_active_soc_limit call + _last_active_soc_limit comparison. Pure -- no hass.bus
    access; the coordinator still fires ActiveSocLimitChanged itself on a reported change
    (ADR-0009/0010 boundary: HA I/O stays coordinator-side)."""

    def __init__(self) -> None:
        self._last_limit: float | None = None

    def resolve(
        self,
        override: float,
        *,
        solar_reserve_active: bool,
        solar_reserve_soc: float,
        step_up_state: SolarStepUpState,
    ) -> tuple[float, bool]:
        """Return (this cycle's active SOC limit, whether it changed from the last resolve()).

        The first call always reports changed=True -- there is no prior resolve() to compare
        against, mirroring the old code's None-vs-float first-cycle behavior.
        """
        limit = resolve_active_soc_limit(
            override,
            solar_reserve_active=solar_reserve_active,
            solar_reserve_soc=solar_reserve_soc,
            step_up_state=step_up_state,
        )
        changed = limit != self._last_limit
        self._last_limit = limit
        return limit, changed


class SolarStepUpGate:
    """R8 solar step-up gating (ADR-0023), wrapping engines/soc_target.py::resolve_solar_step_up.
    Owns the SolarStepUpState itself -- moved off the coordinator instance -- and exposes it via
    the public `state` attribute for SocGateResolver.resolve(step_up_state=...), which already
    takes it as an argument today. `state` is a plain mutable attribute, not a read-only property
    wrapping a private field (unlike SocGateResolver's `_last_limit`) -- callers, including
    tests, seed a starting state directly (`gate.state = SolarStepUpState(...)`), the same
    public-field precedent PeakDemandState already sets for its own three fields."""

    def __init__(self) -> None:
        self.state: SolarStepUpState = SolarStepUpState()

    def resolve(
        self,
        *,
        profile: str,
        mode_is_solar: bool,
        status: str,
        soc: float | None,
        default_limit: float,
        step_threshold_pp: float,
        step_pp: float,
        max_solar_soc: float,
    ) -> None:
        """R8 is Auto-only, like R9's reserve cap (resolution-rules.md) -- is_solar_mode_charging
        gates on THIS cycle's profile/mode/status, mirroring the coordinator's own prior inline
        computation exactly. Mutates self.state in place; callers read .state afterward."""
        is_solar_mode_charging = (
            profile == PROFILE_AUTO and mode_is_solar and status in CHARGEABLE_STATES
        )
        _, self.state = resolve_solar_step_up(
            self.state,
            is_solar_mode_charging=is_solar_mode_charging,
            soc=soc if soc is not None else 0.0,
            default_limit=default_limit,
            step_threshold_pp=step_threshold_pp,
            step_pp=step_pp,
            max_solar_soc=max_solar_soc,
        )


def resolve_solar_reserve_gate(
    *,
    profile: str,
    home_day_flag: bool,
    sun_is_down: bool,
    forecast_kwh: float | None,
    forecast_threshold_kwh: float,
    deadline_tomorrow_resolved: bool,
) -> bool:
    """R9 solar-reserve-cap gating (ADR-0023) -- a thin wrapper over
    engines/soc_target.py::resolve_solar_reserve_active, folding the forecast reading's
    None-to-0.0 default in the one place that needs it. A plain function, not a class, because
    unlike SolarStepUpGate it is stateless -- nothing is threaded across cycles."""
    return resolve_solar_reserve_active(
        profile=profile,
        home_day_flag=home_day_flag,
        sun_is_down=sun_is_down,
        forecast_kwh=forecast_kwh if forecast_kwh is not None else 0.0,
        forecast_threshold_kwh=forecast_threshold_kwh,
        deadline_tomorrow_resolved=deadline_tomorrow_resolved,
    )


@dataclass(frozen=True)
class DeadlineUrgencyResult:
    """Outcome of ADR-0006 steps 3-6 (deadline/urgency resolution, #506): the
    required-current/urgency determination (R5/R15) and, when Auto actually dispatches this
    cycle, its freshly resolved active mode. `resolved_mode` is None whenever
    `auto_dispatchable` was False -- the coordinator only ever assigns `self.active_mode`
    from it in that case, mirroring the original inline `if auto_dispatchable:` guard around
    the real (non-baseline) call to the Auto policy's `select()` (ADR-0017). Firing
    `DeadlineUnreachableNotified` off
    `required.unreachable` stays the coordinator's own job (ADR-0009/0010: HA I/O stays
    coordinator-side), the same boundary `SocGateResolver` already draws for
    `ActiveSocLimitChanged`."""

    required: RequiredCurrentResult
    urgent: bool
    resolved_mode: str | None


def resolve_deadline_urgency(
    *,
    deadline_resolvable: bool,
    ev_soc: float | None,
    active_mode: str,
    active_soc_limit: float,
    deadline_today: time | None,
    now_dt: datetime,
    effective_battery_capacity_kwh: float,
    voltage: float,
    surplus_w: float,
    max_current_a: float,
    auto_dispatchable: bool,
    solar_installed: bool,
    captar_available: bool,
    solar_start_threshold_w: float,
    sun_is_up: bool,
    sun_is_down: bool,
    low_tariff_active: bool,
    solar_reserve_active: bool,
    mode_desired_current: Callable[[str], float],
) -> DeadlineUrgencyResult:
    """R5/R14/R15: today's departure deadline and the required-current/urgency it drives
    (ADR-0006 steps 3-6; ADR-0012-style extraction, #506). `deadline_resolvable` is the
    coordinator's own `status in CHARGEABLE_STATES and ev_soc is not None` check, computed
    ONCE there and passed in rather than re-derived here from `status`/`ev_soc` -- the
    coordinator already branches on that exact predicate to decide whether to even read
    today's deadline/sensed battery capacity (both async, HA-bound), so a second, separately
    written copy of the same condition on this side of the module boundary would be exactly
    the kind of lockstep-editing hazard #506 exists to remove. Without it (disconnected, or a
    non-SOC-gated mode with the role unconfigured), urgency can't be computed, mirroring R14's
    own "no deadline resolved -> urgency never applies" shape. All adapter/HA reads (today's
    resolved deadline, the sensed battery capacity) happen in the coordinator before this is
    called -- this function only ever receives already-resolved plain values, per
    ADR-0009/0010's HA-free boundary.

    The baseline mode is evaluated fresh from Auto mode-selection's rows 3-5 alone
    (urgent=False) every cycle -- never Captar's own already-escalated request, per
    resolution-rules.md's explicit warning against that (it would make urgency look satisfied
    the instant it engages and revert every cycle). The Auto policy's `select()`
    (`PROFILE_POLICIES[PROFILE_AUTO]`, ADR-0017) is consulted at most twice here -- baseline
    (urgent=False) and, only when Auto actually dispatches, the real resolution (the real
    `urgent`) -- sharing one kwargs dict so the other 9 arguments can never drift apart between
    the two calls (#506's named duplication-risk).
    """
    if not deadline_resolvable:
        return DeadlineUrgencyResult(
            required=RequiredCurrentResult(required_a=None, urgent=False, unreachable=False),
            urgent=False,
            resolved_mode=None,
        )

    baseline_mode = active_mode
    common_select_kwargs: dict[str, Any] = {}
    if auto_dispatchable:
        available_modes = resolve_available_modes(
            solar_available=solar_installed, captar_available=captar_available
        )
        common_select_kwargs = dict(
            soc=ev_soc,
            active_soc_limit=active_soc_limit,
            available_modes=available_modes,
            solar_capability_present=solar_installed,
            sun_is_up=sun_is_up,
            solar_surplus_sufficient=surplus_w >= solar_start_threshold_w,
            sun_is_down=sun_is_down,
            low_tariff_active=low_tariff_active,
            solar_reserve_active=solar_reserve_active,
        )
        baseline_mode = PROFILE_POLICIES[PROFILE_AUTO].select(urgent=False, **common_select_kwargs)

    baseline_desired_a = mode_desired_current(baseline_mode)

    required = resolve_required_current(
        deadline_today,
        # engines/deadline.py combines this with a naive `time` (the departure-time
        # entities carry no tzinfo) -- strip dt_util.now()'s tzinfo so the subtraction
        # doesn't raise (both sides represent the same local wall clock either way).
        # Wall-clock subtraction on the two DST-transition days a year can be off by
        # up to 1h (naive datetimes don't observe the transition) -- bounded, accepted.
        now_dt.replace(tzinfo=None),
        soc=ev_soc,
        active_soc_limit=active_soc_limit,
        ev_battery_capacity_kwh=effective_battery_capacity_kwh,
        voltage=voltage,
        baseline_desired_a=baseline_desired_a,
        # A deliberate simplification of "maximum permitted rate"'s full peak-clamp-fitted
        # definition (system-overview.md glossary) down to C1's hard ceiling -- refining
        # this to the actual peak-fitted rate is tracked follow-up work (issue #367),
        # not this task's job; it only affects when DeadlineUnreachableNotified fires.
        maximum_permitted_rate_a=max_current_a,
    )

    # R5/R16: Unreachable still requests the same escalated mode/peak-limit raise as
    # Urgent (UC05's Postconditions) -- this `or` makes that explicit even though
    # `unreachable` implies `urgent` by construction, per the required-current formula.
    urgent = required.urgent or required.unreachable

    resolved_mode = None
    if auto_dispatchable:
        # Manual dispatches via the selector unconditionally (NF2 regression: active_mode
        # never changes here while Manual, even under urgency) -- only Auto resolves its
        # own mode, via the real (non-baseline) urgent this time.
        resolved_mode = PROFILE_POLICIES[PROFILE_AUTO].select(urgent=urgent, **common_select_kwargs)

    return DeadlineUrgencyResult(required=required, urgent=urgent, resolved_mode=resolved_mode)
