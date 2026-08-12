"""Charging Coordinator (M1) — the control cycle (ADR-0006/0007)."""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from datetime import time as time_of_day
from typing import Any

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .adapters.sun import SUN_STATE_ABOVE_HORIZON, SUN_STATE_BELOW_HORIZON
from .config import SmartChargingConfig
from .const import (
    ATTR_ACTIVE_SOC_LIMIT,
    ATTR_REQUIRED_CURRENT_A,
    CHARGEABLE_STATES,
    DEFAULT_SOC_LIMIT,
    DOMAIN,
    EVENT_ACTIVE_SOC_LIMIT_CHANGED,
    EVENT_DEADLINE_UNREACHABLE_NOTIFIED,
    MODE_CAPTAR,
    MODE_OFF,
    MODE_POWER,
    OWNED_SUFFIX_DEPARTURE_DOW,
    OWNED_SUFFIX_DEPARTURE_HOLIDAY,
    OWNED_SUFFIX_DEPARTURE_HOME_DAY,
    OWNED_SUFFIX_HOME_DAY,
    OWNED_SUFFIX_MODE,
    OWNED_SUFFIX_PROFILE,
    OWNED_SUFFIX_SOC_LIMIT_OVERRIDE,
    OWNED_SUFFIX_TARGET_CURRENT,
    PROFILE_AUTO,
    PROFILE_MANUAL,
    ROLE_CHARGER_CURRENT,
    ROLE_CHARGER_POWER,
    ROLE_CHARGER_STATUS,
    ROLE_DEPARTURE_EXTERNAL,
    ROLE_EV_BATTERY_CAPACITY,
    ROLE_EV_SOC,
    ROLE_GRID_VOLTAGE,
    ROLE_LOW_TARIFF,
    ROLE_NET_POWER,
    ROLE_SOLAR_FORECAST,
    ROLE_SUN,
    ROLES_ADAPTER_READINGS_EXCLUDED,
    SOC_LIMIT_OVERRIDE_MAX,
    SOC_LIMIT_OVERRIDE_MIN,
)
from .coordinator_cycle import (
    CycleContext,
    ModeHandler,
    PeakDemandState,
    SocGateResolver,
    SolarStepUpGate,
    build_mode_handlers,
    resolve_deadline_urgency,
    resolve_solar_reserve_gate,
)
from .engines.billing_protection import (
    PeakBreachTracker,
    apply_peak_clamp,
    resolve_effective_peak_limit,
)
from .engines.cycle_invariant import apply_floor_cap
from .engines.deadline import RequiredCurrentResult, resolve_departure_deadline
from .engines.grid_safety import clamp_to_ceiling
from .engines.signal_conditioning import resolve_voltage, smooth_net_power
from .modes import captar
from .modes._phase import Phase

_LOGGER = logging.getLogger(__name__)


@dataclass
class CycleResult:
    """Outcome of one control cycle: the amps actually written and whether it faulted."""

    commanded_current: float
    fault: bool
    active_mode: str
    monthly_peak_kw: float = 0.0
    effective_peak_limit_kw: float = 0.0
    active_soc_limit: float = 0.0
    solar_surplus_w: float = 0.0
    peak_headroom_a: float = 0.0
    time_to_full_min: float | None = None
    adapter_readings: dict[str, Any] = field(default_factory=dict)
    adapter_readings_at: datetime | None = None


class SmartChargingCoordinator(DataUpdateCoordinator[CycleResult]):
    """Runs the control cycle every interval, dispatching to the active mode (M1)."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        adapters,
        store,
        config: SmartChargingConfig,
        interval_s: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval_s),
        )
        self._adapters = adapters
        self._store = store
        self._config = config
        self._interval_s = interval_s
        # ADR-0012: one thin adapter per mode, looked up by active_mode instead of the old
        # if/elif dispatch chain. MODE_POWER is registered too (for the discard-state branch
        # below, kept as its own elif per design doc Sec 3.4) even though it never goes through
        # the registry's shared state-write path. `self.active_mode` is always one of these
        # five keys in practice (profiles/auto.select_mode only returns a registered mode; a
        # Manual selection is validated against the select entity's own options before it ever
        # reaches the Store) -- an out-of-registry value would otherwise KeyError on lookup.
        # `set_active_mode` (below) now guards against that directly, rejecting any value
        # outside this registry's keys and falling back to MODE_OFF with a warning rather
        # than letting it KeyError deep inside the cycle every tick. The five
        # handlers themselves are built by `build_mode_handlers` (coordinator_cycle.py),
        # which keeps the concrete `_*ModeHandler` classes private to that module.
        self._mode_handlers: dict[str, ModeHandler] = build_mode_handlers(
            config, lambda: self.target_current
        )
        # Single source of truth for the setpoint is the number entity, read through the
        # Store each cycle (_read_owned_entities, ADR-0018). 0 A is the safe default for
        # cycle 0, before the first read.
        self.target_current: float = 0.0
        # Read through the Store each cycle (_read_owned_entities, ADR-0018) -- this
        # MODE_POWER default only matters for a coordinator instance never wired to a Store
        # read (e.g. a unit test constructing one directly).
        self.active_mode: str = MODE_POWER
        # Mirrors active_mode (R16): read through the Store each cycle, from
        # select.smart_charging_profile.
        self.active_profile: str = PROFILE_MANUAL
        self.soc_limit_override: float = DEFAULT_SOC_LIMIT
        # R8's lifecycle state, threaded across cycles -- cleared only via
        # SolarStepUpGate.resolve's own is_solar_mode_charging=False branch, never by
        # the generic per-mode-switch reset below (that would wrongly clear an in-effect
        # step-up on a Solar<->SolarOnly switch, R7/UC06 alternate flow 4a). ADR-0023:
        # SolarStepUpGate owns the SolarStepUpState itself; `.state` is a plain mutable
        # attribute, same seeding pattern as before via `self._step_up_gate.state = ...`.
        self._step_up_gate = SolarStepUpGate()
        # ADR-0011: resolves the active SOC limit and detects a change from the prior cycle for
        # ActiveSocLimitChanged (ADR-0012's SocGateResolver). The first resolution reached (an
        # early-faulted cycle never reaches it) always reports changed=True.
        self._soc_gate = SocGateResolver()
        # R9/R14 inputs -- read through the Store each cycle (_read_owned_entities,
        # ADR-0018), from switch.smart_charging_home_day / time.smart_charging_departure_*.
        # These constructor defaults (no home day, no configured deadline anywhere) only
        # matter before the first read.
        self.home_day_flag: bool = False
        self.departure_dow_defaults: dict[int, time_of_day | None] = dict.fromkeys(range(7))
        self.departure_holiday_override: time_of_day | None = None
        self.departure_home_day_override: time_of_day | None = None
        # R5: the last cycle's required-current/urgency determination -- exposed for
        # external consumption (Auto mode-selection's escalation) and inspected directly by
        # tests, the same way `_step_up_gate.state` already is.
        self._required_current = RequiredCurrentResult(
            required_a=None, urgent=False, unreachable=False
        )
        self._last_active_mode: str | None = None
        # Latches the last raw value set_active_mode rejected -- None once a valid
        # mode is set again. Lets set_active_mode log its warning once per bad-value "outage"
        # rather than once per cycle (ADR-0007's once-per-outage discipline, same idea as
        # `_was_faulted`/`_log_fault` below), since a corrupted Store-read value would otherwise
        # re-reject identically every cycle.
        self._last_rejected_mode: str | None = None
        self._net_window: tuple[float, ...] = ()
        self._mode_state = self._fresh_mode_state()
        self._was_faulted = False
        # M1's OWN 15-minute window (E5), distinct from R10's `_net_window` above --
        # a MonthlyPeakSensor restore may seed `_peak_demand.tracked_kw`/`.tracked_month` before
        # the first cycle; the window itself is deliberately never persisted (design
        # doc Sec 6.4), so it always starts empty here. Owned by PeakDemandState (ADR-0012).
        self._peak_demand = PeakDemandState()
        self._peak_tracker = PeakBreachTracker()
        # ADR-0021: `sensor.smart_charging_adapter_readings`' backing cache -- persisted across
        # cycles (never reset), holding each read role's most recently read value so a role not
        # read on a given cycle (e.g. `ev_soc` while disconnected) still reports its last known
        # value instead of disappearing, and a faulted cycle still reports whatever was read
        # before the fault.
        self._role_readings: dict[str, Any] = {}
        self._role_readings_at: datetime | None = None

    async def _async_update_data(self) -> CycleResult:
        try:
            return await self._run_cycle()
        except Exception as err:  # noqa: BLE001 - every failure funnels to the fault path (ADR-0007)
            self._log_fault(f"cycle exception: {err}")
            await self._safe_write_zero()
            return CycleResult(
                commanded_current=0.0,
                fault=True,
                active_mode=self.active_mode,
                adapter_readings=self._current_adapter_readings(),
                adapter_readings_at=self._role_readings_at,
            )

    def _current_adapter_readings(self) -> dict[str, Any]:
        """ADR-0021: the persisted role-readings cache, filtered to currently-wired *read*
        roles -- a role that stops being wired disappears here even though the cache may
        still hold its stale value internally."""
        return {
            role: self._role_readings.get(role)
            for role in self._adapters
            if role not in ROLES_ADAPTER_READINGS_EXCLUDED
        }

    async def _read_cycle_inputs(self) -> tuple[str, float, float, float] | None:
        """Steps 1 and 3 (ADR-0006): read the three required adapters and resolve voltage (NF4's
        fallback -- the one role where a None reading is not a fault). Returns None on a missing
        required adapter; _run_cycle performs the actual fault CycleResult itself, keeping
        ADR-0007's single fault-handling code path in _run_cycle rather than scattered across
        extracted methods (ADR-0023). Also caches each read role's value into
        `self._role_readings` (ADR-0021) -- `_run_cycle` decides whether to advance
        `self._role_readings_at`, since that depends on whether this cycle's read succeeded."""
        status = await self._adapters[ROLE_CHARGER_STATUS].read()
        net_w = await self._adapters[ROLE_NET_POWER].read()
        charger_w = await self._adapters[ROLE_CHARGER_POWER].read()
        self._role_readings[ROLE_CHARGER_STATUS] = status
        self._role_readings[ROLE_NET_POWER] = net_w
        self._role_readings[ROLE_CHARGER_POWER] = charger_w

        # Grid voltage is the one role where None is NOT a fault (NF4).
        measured_v = None
        if ROLE_GRID_VOLTAGE in self._adapters:
            measured_v = await self._adapters[ROLE_GRID_VOLTAGE].read()
            self._role_readings[ROLE_GRID_VOLTAGE] = measured_v
        voltage = resolve_voltage(measured_v, self._config.nominal_voltage)

        # Any required role missing -> fault (ADR-0007).
        if status is None or net_w is None or charger_w is None:
            return None
        return status, net_w, charger_w, voltage

    async def _resolve_deadline_and_reserve(
        self, ctx: CycleContext, now_dt: datetime
    ) -> tuple[time_of_day | None, Callable[[int], time_of_day | None]]:
        """R14's departure-external/sun/low-tariff reads and the weekday-parameterised deadline
        table, plus R9's solar-reserve-cap gating (resolve_solar_reserve_gate,
        coordinator_cycle.py) -- the two are resolved together because R9's gate needs
        tomorrow's deadline, this same block's own result. Mutates ctx.sun_is_up/
        ctx.sun_is_down/ctx.low_tariff_active/ctx.solar_reserve_active in place (ADR-0012's
        existing "assign onto ctx as each value resolves" pattern) and returns
        (deadline_tomorrow, resolve_deadline_for) for _run_cycle's later use: deadline_tomorrow
        was already needed by R9's own gate; resolve_deadline_for is the closure
        `_read_deadline_urgency_inputs` (below) calls for today's deadline. is_holiday is
        hardcoded False -- R14's public-holiday source is not wired in yet, so row 2 of R14's
        table never matches. Also caches each read role's value into `self._role_readings`
        (ADR-0021) -- a prior extraction (ADR-0023) had dropped these four writes,
        which `_read_cycle_inputs`/`_read_deadline_urgency_inputs` still do for their own reads;
        restored here so ROLE_DEPARTURE_EXTERNAL/ROLE_SUN/ROLE_LOW_TARIFF/
        ROLE_SOLAR_FORECAST keep reporting their real reads in
        `sensor.smart_charging_adapter_readings` instead of a stale/None value forever."""
        external_configured = ROLE_DEPARTURE_EXTERNAL in self._adapters
        external = (
            await self._adapters[ROLE_DEPARTURE_EXTERNAL].read() if external_configured else None
        )
        if external_configured:
            self._role_readings[ROLE_DEPARTURE_EXTERNAL] = external
        sun_reading = await self._adapters[ROLE_SUN].read() if ROLE_SUN in self._adapters else None
        if ROLE_SUN in self._adapters:
            self._role_readings[ROLE_SUN] = sun_reading
        ctx.sun_is_up = sun_reading == SUN_STATE_ABOVE_HORIZON
        ctx.sun_is_down = sun_reading == SUN_STATE_BELOW_HORIZON
        # An unmapped ROLE_LOW_TARIFF (or a None reading) keeps the glossary's own
        # single-tariff default -- "the signal is omitted and the flag is treated as
        # always active".
        ctx.low_tariff_active = True
        if ROLE_LOW_TARIFF in self._adapters:
            low_tariff_reading = await self._adapters[ROLE_LOW_TARIFF].read()
            self._role_readings[ROLE_LOW_TARIFF] = low_tariff_reading
            if low_tariff_reading is not None:
                ctx.low_tariff_active = low_tariff_reading

        # R14's four-row table, evaluated for a given weekday -- shared by both today's
        # deadline (urgency, below) and tomorrow's (R9's one-day-ahead precondition, UC07),
        # so the other six args can never drift apart between the two call sites.
        def resolve_deadline_for(weekday: int) -> time_of_day | None:
            return resolve_departure_deadline(
                external_configured,
                external,
                is_holiday=False,
                holiday_override=self.departure_holiday_override,
                home_day_flag=self.home_day_flag,
                home_day_override=self.departure_home_day_override,
                day_of_week_default=self.departure_dow_defaults.get(weekday),
            )

        # R9's precondition (UC07): the same R14 table evaluated one day ahead.
        tomorrow_weekday = (now_dt.weekday() + 1) % 7
        deadline_tomorrow = resolve_deadline_for(tomorrow_weekday)
        forecast_kwh = (
            await self._adapters[ROLE_SOLAR_FORECAST].read()
            if ROLE_SOLAR_FORECAST in self._adapters
            else None
        )
        if ROLE_SOLAR_FORECAST in self._adapters:
            self._role_readings[ROLE_SOLAR_FORECAST] = forecast_kwh
        ctx.solar_reserve_active = resolve_solar_reserve_gate(
            profile=self.active_profile,
            home_day_flag=self.home_day_flag,
            sun_is_down=ctx.sun_is_down,
            forecast_kwh=forecast_kwh,
            forecast_threshold_kwh=self._config.solar_forecast_threshold_kwh,
            deadline_tomorrow_resolved=deadline_tomorrow is not None,
        )
        return deadline_tomorrow, resolve_deadline_for

    async def _read_deadline_urgency_inputs(
        self,
        *,
        deadline_resolvable: bool,
        today_weekday: int,
        resolve_deadline_for: Callable[[int], time_of_day | None],
    ) -> tuple[time_of_day | None, float]:
        """The R5/R14/R15 deadline-urgency call site's own adapter reads (today's deadline, the
        sensed battery capacity) -- must stay coordinator-side even though resolve_deadline_urgency
        itself is already a pure coordinator_cycle.py function. Deliberately deviates from
        design doc Sec 3.3's snippet, which gates the sensed-capacity read behind
        `deadline_resolvable` too: that read already feeds the `_role_readings`
        diagnostic mirror (ADR-0021) unconditionally, every cycle, so it must not be gated here --
        doing so would regress that diagnostic to a stale value whenever the deadline isn't
        resolvable (e.g. disconnected). Only `deadline_today` itself stays gated. Returns
        (deadline_today, effective_battery_capacity_kwh); deadline_today is None when
        deadline_resolvable is False, exactly as today (resolve_deadline_urgency short-circuits
        before reading it)."""
        sensed_capacity_kwh = None
        if ROLE_EV_BATTERY_CAPACITY in self._adapters:
            sensed_capacity_kwh = await self._adapters[ROLE_EV_BATTERY_CAPACITY].read()
            self._role_readings[ROLE_EV_BATTERY_CAPACITY] = sensed_capacity_kwh
        effective_battery_capacity_kwh = sensed_capacity_kwh
        if effective_battery_capacity_kwh is None:
            effective_battery_capacity_kwh = self._config.ev_battery_capacity_kwh
        deadline_today = resolve_deadline_for(today_weekday) if deadline_resolvable else None
        return deadline_today, effective_battery_capacity_kwh

    async def _run_cycle(self) -> CycleResult:
        await self._read_owned_entities()
        now_dt = dt_util.now()
        inputs = await self._read_cycle_inputs()
        if inputs is None:
            self._log_fault("required adapter returned None")
            await self._write(0.0)
            # `_role_readings_at` deliberately does NOT advance to `now_dt` here --
            # ADR-0021/entity-catalog.md:154 define the entity's own state as the timestamp of
            # the LAST SUCCESSFUL cycle, and a required-role fault means this cycle wasn't one;
            # the cache keeps whichever timestamp a prior successful cycle set, even though the
            # per-role values `_read_cycle_inputs` just cached are this cycle's own (possibly
            # None) readings.
            return CycleResult(
                commanded_current=0.0,
                fault=True,
                active_mode=self.active_mode,
                adapter_readings=self._current_adapter_readings(),
                adapter_readings_at=self._role_readings_at,
            )
        status, net_w, charger_w, voltage = inputs
        self._role_readings_at = now_dt

        # entity-catalog.md:151/glossary -- raw net_w, deliberately distinct from `surplus_w`
        # below (R10's smoothed control-path value).
        solar_surplus_w = charger_w - net_w

        # Peak-Demand Tracker (E5) + effective-peak-limit resolution (E5) --
        # runs every cycle regardless of mode (R3's bookkeeping is not Captar-specific). Uses
        # real wall-clock (`now_dt`, read at the top of `_run_cycle`) for month rollover,
        # distinct from the monotonic `now` the mode state machines use below.
        monthly_peak_kw = self._peak_demand.update(
            net_w, now_dt, window_size=self._config.peak_window_size
        )
        # Fallback for the ev_soc-fault early return below, where real urgency can't yet be
        # known -- overwritten with the real `urgent` value once required-current resolves.
        effective_peak_limit_kw = resolve_effective_peak_limit(
            monthly_peak_kw,
            self._config.max_peak_kw,
            urgent=False,
        )
        # R11: catches a Manual mode change here (already final -- set externally before this
        # cycle runs), before the baseline-mode dry run below reads _mode_state, so that dry
        # run sees fresh state on the very cycle the user switches modes. Idempotent -- a no-op
        # if nothing has changed yet, which is always true for Auto at this point (its own mode
        # isn't resolved until later, below); the same check runs again after that resolution,
        # to catch an Auto mode change too.
        self._reset_mode_state_if_changed()

        # ev_soc is read whenever the car is connected and the role is configured -- the
        # deadline-urgency comparison needs it regardless of mode (R5 is cross-cutting), not
        # only while a solar mode or Captar is selected. Its absence is only ever a FAULT while
        # a solar mode or Captar is selected AND the car is connected (success-criterion 6 / S2:
        # Power/Off must not regress to needing an SOC sensor; a disconnected car is a clean idle
        # stop, not a fault, even if its SOC sensor also goes unavailable on unplug, per UC01/R7);
        # outside that gate a missing reading just means deadline urgency can't be computed this
        # cycle (below), not a fault.
        ev_soc = None
        if status in CHARGEABLE_STATES and ROLE_EV_SOC in self._adapters:
            ev_soc = await self._adapters[ROLE_EV_SOC].read()
            self._role_readings[ROLE_EV_SOC] = ev_soc
        if (
            self._mode_handlers[self.active_mode].is_soc_gated
            and status in CHARGEABLE_STATES
            and ev_soc is None
        ):
            self._log_fault("ev_soc required while a solar mode is active but missing/None")
            await self._write(0.0)
            return CycleResult(
                commanded_current=0.0,
                fault=True,
                active_mode=self.active_mode,
                monthly_peak_kw=monthly_peak_kw,
                effective_peak_limit_kw=effective_peak_limit_kw,
                solar_surplus_w=solar_surplus_w,
                adapter_readings=self._current_adapter_readings(),
                adapter_readings_at=self._role_readings_at,
            )

        # __init__.py's SmartChargingConfig already applies DEFAULT_SMOOTHING_WINDOW for a
        # pre-solar config entry that predates this option; smoothing runs every cycle
        # regardless of mode.
        smoothed_net_w, self._net_window = smooth_net_power(
            net_w, self._net_window, size=self._config.smoothing_window
        )
        surplus_w = charger_w - smoothed_net_w  # shared by Solar/SolarOnly dispatch below and
        # the baseline-mode dry-run
        now = self.hass.loop.time()  # injected, not read inside modes/engines
        # ADR-0012: carries this cycle's readings/derived values into the ModeHandler registry
        # lookup below, replacing the loose local variables the old dispatch chain threaded by
        # hand. Filled progressively as later steps resolve each remaining value -- not
        # everything is known yet at this point in the cycle.
        ctx = CycleContext(
            status=status,
            net_w=net_w,
            charger_w=charger_w,
            voltage=voltage,
            now=now,
            now_dt=now_dt,
            ev_soc=ev_soc,
            surplus_w=surplus_w,
            monthly_peak_kw=monthly_peak_kw,
        )
        # R8 is Auto-only, like R9's reserve cap (resolution-rules.md) -- computed fresh every
        # cycle from THIS cycle's active_profile and active_mode. Under Manual, active_mode is
        # already this cycle's final value (set externally before the cycle runs); under Auto,
        # it's still the PRIOR cycle's resolved mode here (Auto's own mode isn't resolved until
        # later, below) -- one cycle of lag, matching R8's own "next control cycle" framing.
        # ADR-0023: SolarStepUpGate computes is_solar_mode_charging internally from these same
        # inputs and mutates its own `.state` in place; callers read `.state` afterward.
        self._step_up_gate.resolve(
            profile=self.active_profile,
            mode_is_solar=self._mode_handlers[self.active_mode].is_solar_mode,
            status=status,
            soc=ev_soc,
            default_limit=self.soc_limit_override,
            step_threshold_pp=self._config.solar_step_threshold_pp,
            step_pp=self._config.solar_step_pp,
            max_solar_soc=self._config.max_solar_soc,
        )

        # R5/R14/R15: `today_weekday` stays inline -- _read_deadline_urgency_inputs (below)
        # needs it as a parameter; only `tomorrow_weekday` moved into
        # _resolve_deadline_and_reserve (ADR-0023).
        today_weekday = now_dt.weekday()
        deadline_tomorrow, resolve_deadline_for = await self._resolve_deadline_and_reserve(
            ctx, now_dt
        )
        active_soc_limit, soc_limit_changed = self._soc_gate.resolve(
            self.soc_limit_override,
            solar_reserve_active=ctx.solar_reserve_active,
            solar_reserve_soc=self._config.solar_reserve_soc,
            step_up_state=self._step_up_gate.state,
        )
        if soc_limit_changed:
            self.hass.bus.async_fire(
                EVENT_ACTIVE_SOC_LIMIT_CHANGED, {ATTR_ACTIVE_SOC_LIMIT: active_soc_limit}
            )
        ctx.active_soc_limit = active_soc_limit

        # `auto_dispatchable` is also this cycle's own gate for actually resolving Auto's
        # active mode below -- computed once here and reused there (and inside
        # resolve_deadline_urgency), rather than repeating the same conjunction, so the two
        # can never drift apart. When it's False (disconnected, or Auto with no ev_soc role
        # mapped at all), Auto simply keeps whatever active_mode it last resolved -- a
        # deliberate, scope-truthful simplification, same as required-current's own guard
        # inside resolve_deadline_urgency.
        auto_dispatchable = (
            self.active_profile == PROFILE_AUTO
            and status in CHARGEABLE_STATES
            and ev_soc is not None
        )
        # R5/R14/R15: today's departure deadline and the required-current/urgency it drives
        # (ADR-0006 steps 3-6 -- see resolve_deadline_urgency's own
        # docstring for the guard/dedup rationale). The adapter/HA reads (today's deadline, the
        # sensed battery capacity) stay coordinator-side, in `_read_deadline_urgency_inputs`
        # above; everything else moves to coordinator_cycle.py, pure and HA-import-free
        # (ADR-0012's boundary). `deadline_resolvable` itself is computed once here and passed
        # into both `_read_deadline_urgency_inputs` and `resolve_deadline_urgency` rather than
        # re-derived from status/ev_soc on the other side of the module boundary -- a second,
        # separately written copy of the same predicate is exactly the lockstep-editing hazard
        # this design exists to remove. Stays inline in `_run_cycle` rather than moving into
        # `_read_deadline_urgency_inputs` (ADR-0023, design doc Sec 3.3).
        deadline_resolvable = status in CHARGEABLE_STATES and ev_soc is not None
        deadline_today, effective_battery_capacity_kwh = await self._read_deadline_urgency_inputs(
            deadline_resolvable=deadline_resolvable,
            today_weekday=today_weekday,
            resolve_deadline_for=resolve_deadline_for,
        )
        deadline_urgency = resolve_deadline_urgency(
            deadline_resolvable=deadline_resolvable,
            ev_soc=ev_soc,
            active_mode=self.active_mode,
            active_soc_limit=active_soc_limit,
            deadline_today=deadline_today,
            now_dt=now_dt,
            effective_battery_capacity_kwh=effective_battery_capacity_kwh,
            voltage=voltage,
            surplus_w=surplus_w,
            max_current_a=self._config.max_current,
            auto_dispatchable=auto_dispatchable,
            solar_installed=self._config.solar_installed,
            captar_available=self._config.captar_available,
            solar_start_threshold_w=self._config.solar_start_threshold_w,
            sun_is_up=ctx.sun_is_up,
            sun_is_down=ctx.sun_is_down,
            low_tariff_active=ctx.low_tariff_active,
            solar_reserve_active=ctx.solar_reserve_active,
            mode_desired_current=lambda mode: self._mode_desired_current(
                mode,
                status=status,
                ev_soc=ev_soc,
                active_soc_limit=active_soc_limit,
                surplus_w=surplus_w,
                voltage=voltage,
                now=now,
            ),
        )
        required = deadline_urgency.required
        # Exposed for the effective-peak-limit `urgent` parameter and Auto
        # mode-selection's escalation, and for tests, the same way `_step_up_gate.state` already is.
        self._required_current = required
        if required.unreachable:
            self.hass.bus.async_fire(
                EVENT_DEADLINE_UNREACHABLE_NOTIFIED, {ATTR_REQUIRED_CURRENT_A: required.required_a}
            )

        urgent = deadline_urgency.urgent
        ctx.urgent = urgent
        effective_peak_limit_kw = resolve_effective_peak_limit(
            monthly_peak_kw, self._config.max_peak_kw, urgent=urgent
        )
        # This is the only ctx.effective_peak_limit_kw assignment -- the earlier, provisional
        # resolve_effective_peak_limit(urgent=False) call above (used only for the ev_soc-fault
        # early return) runs before `ctx` is constructed, so ctx's field intentionally carries
        # its dataclass default (0.0) until this final, real value lands here. No ModeHandler
        # reads this field today; if one later does, thread the provisional value onto ctx too.
        ctx.effective_peak_limit_kw = effective_peak_limit_kw

        # entity-catalog.md:153/control-cycle.md step 5 -- the same raw-reading target the R3
        # clamp itself holds (apply_peak_clamp's own headroom_a). Both the `safety_margin_w`
        # read and the resulting computation are duplicated here rather than returned from
        # _apply_peak_clamp, to avoid changing its control-path signature for a display-only
        # need -- keep the two lookups in lockstep if either side changes.
        peak_target_w = effective_peak_limit_kw * 1000.0 - self._config.safety_margin_w
        peak_baseline_w = net_w - charger_w
        peak_headroom_a = math.floor((peak_target_w - peak_baseline_w) / voltage)
        if auto_dispatchable and deadline_urgency.resolved_mode is not None:
            # Manual dispatches via the selector unconditionally (NF2 regression: active_mode
            # never changes here while Manual, even under urgency) -- only Auto resolves its
            # own mode, via resolve_deadline_urgency's real (non-baseline) urgent resolution.
            # The explicit None-check is defense in depth: `resolved_mode` is None exactly
            # when `auto_dispatchable` was False inside resolve_deadline_urgency too (the two
            # booleans are computed from the same inputs), so this should never trigger --
            # but self.active_mode is typed `str`, and silently assigning None would surface
            # far downstream as a `KeyError` on the mode-handler lookup instead of here. Routed
            # through set_active_mode rather than a direct assignment, so this
            # site gets the same registry-membership guard as the Store-read path -- keeping
            # `self.active_mode`'s one mutation point (ADR-0014) genuinely singular.
            self.set_active_mode(deadline_urgency.resolved_mode)

        # Checked again here, after Auto's own mode resolution above -- catches a same-cycle
        # Auto escalation/revert in time for this cycle's own dispatch below, not one cycle
        # late (the earlier call above only ever catches a Manual change, since Auto's mode
        # isn't resolved yet at that point).
        self._reset_mode_state_if_changed()

        desired = self._dispatch_mode(ctx)

        desired = self._apply_peak_clamp(
            desired,
            net_w=net_w,
            charger_w=charger_w,
            voltage=voltage,
            effective_peak_limit_kw=effective_peak_limit_kw,
            now=now,
        )

        desired = self._apply_grid_ceiling_clamp(
            desired, net_w=net_w, charger_w=charger_w, voltage=voltage
        )
        desired = apply_floor_cap(  # E8 invariant last
            desired, min_a=self._config.min_current, max_a=self._config.max_current
        )

        # entity-catalog.md:152/glossary -- "the charger's current applied rate"/`charger_current`
        # is the value actually written, i.e. `desired` AFTER every clamp/floor/cap, not the
        # mode's pre-clamp request -- a clamped or floored-to-0 cycle must not report an ETA
        # that assumes a rate the charger was never actually set to. `ev_soc >= active_soc_limit`
        # is checked before the 0 A case so a SOC-gated-stop cycle (which also sets desired=0.0)
        # still reports 0, not unknown, per entity-catalog.md:152.
        if ev_soc is None:
            time_to_full_min = None
        elif ev_soc >= active_soc_limit:
            time_to_full_min = 0.0
        elif desired == 0.0:
            time_to_full_min = None
        else:
            energy_needed_kwh = effective_battery_capacity_kwh * (active_soc_limit - ev_soc) / 100
            time_to_full_min = energy_needed_kwh * 1000 / (desired * voltage) * 60

        await self._write(desired)
        if self._was_faulted:
            _LOGGER.info("smart_charging recovered from fault")
            self._was_faulted = False
        return CycleResult(
            commanded_current=desired,
            fault=False,
            active_mode=self.active_mode,
            monthly_peak_kw=monthly_peak_kw,
            effective_peak_limit_kw=effective_peak_limit_kw,
            active_soc_limit=active_soc_limit,
            solar_surplus_w=solar_surplus_w,
            peak_headroom_a=peak_headroom_a,
            time_to_full_min=time_to_full_min,
            adapter_readings=self._current_adapter_readings(),
            adapter_readings_at=self._role_readings_at,
        )

    def set_soc_limit_override(self, value: float) -> None:
        """Coordinator's own boundary for `soc_limit_override` (ADR-0014). Clamps to
        `[SOC_LIMIT_OVERRIDE_MIN, SOC_LIMIT_OVERRIDE_MAX]` -- the same bound
        `SocLimitOverrideNumber` already enforces on its own restored value, now also enforced at
        the coordinator's own field. Since ADR-0018, `number.py` never calls this directly: the
        coordinator reads the stored value through the Store each cycle (`_read_owned_entities`)
        and calls this itself; the only other caller is tests."""
        self.soc_limit_override = min(max(value, SOC_LIMIT_OVERRIDE_MIN), SOC_LIMIT_OVERRIDE_MAX)

    def set_active_mode(self, mode: str) -> None:
        """Coordinator's own boundary for `active_mode` (ADR-0014) -- the field itself stays a
        plain writable attribute (ADR-0014's design doc §2, criterion 1) but this is its only
        mutation point. Since ADR-0018, `select.py` never calls this directly: the coordinator
        reads the stored option through the Store each cycle (`_read_owned_entities`) and calls
        this itself. The other production caller is `_run_cycle`'s own Auto-mode resolution
        (`self.set_active_mode(deadline_urgency.resolved_mode)`); tests call it directly too.

        Unlike `SelectEntity`'s own `options` list (which rejects an out-of-enum value before
        ever reaching this method), a value read back from the Store has no such gate --
        a stale/corrupted restored option would otherwise reach `self._mode_handlers` unchecked
        and KeyError every cycle (a fault loop rather than ADR-0007's intended clean
        0 A/Fault outcome). Falls back to `MODE_OFF` and logs a warning instead -- deliberately
        without raising `CycleResult.fault`: this is a corrupted/unrecognized *setting*, a
        different class of defect than a hardware adapter returning `None` (ADR-0007's fault
        path), and `_read_owned_entities`' docstring's "a None read is not a fault" rationale
        does not extend to it. The warning is only re-logged when the rejected raw value
        changes (`_last_rejected_mode`, mirroring `_log_fault`'s once-per-outage discipline,
        ADR-0007) -- a corrupted stored option would otherwise re-read and re-reject identically
        every cycle, one warning per control interval forever."""
        if mode not in self._mode_handlers:
            if mode != self._last_rejected_mode:
                _LOGGER.warning(
                    "smart_charging: select.smart_charging_mode has an unrecognized value %r; "
                    "falling back to %s until a valid option (%s) is selected again",
                    mode,
                    MODE_OFF,
                    ", ".join(sorted(self._mode_handlers)),
                )
                self._last_rejected_mode = mode
            mode = MODE_OFF
        else:
            self._last_rejected_mode = None
        self.active_mode = mode

    async def _read_owned_entities(self) -> None:
        """RA3 (ADR-0018): reads all eight owned control-entity values through the Store once
        per cycle. A None read leaves the field unchanged -- not a fault: owned entities are
        internal, and a startup-race/transient-unavailable read is not the same kind of
        missing data as a hardware adapter returning None (ADR-0007)."""
        profile = await self._store.read(Platform.SELECT, OWNED_SUFFIX_PROFILE, str)
        if profile is not None:
            self.set_active_profile(profile)
        # Only Manual dispatches via the selector (coordinator.py's own long-standing rule,
        # applied below at the `auto_dispatchable` check) -- under Auto, self.active_mode is
        # select_mode()'s own resolution, carried across cycles; re-reading the selector's
        # raw (stale, user-facing) value here every cycle would fight that resolution and
        # falsely register as a mode *change* to _reset_mode_state_if_changed() right below,
        # silently discarding R7/R11 timers and R3's breach cooldown every single cycle.
        if self.active_profile != PROFILE_AUTO:
            mode = await self._store.read(Platform.SELECT, OWNED_SUFFIX_MODE, str)
            if mode is not None:
                self.set_active_mode(mode)
        target_current = await self._store.read(Platform.NUMBER, OWNED_SUFFIX_TARGET_CURRENT, float)
        if target_current is not None:
            self.set_target_current(target_current)
        soc_limit = await self._store.read(Platform.NUMBER, OWNED_SUFFIX_SOC_LIMIT_OVERRIDE, float)
        if soc_limit is not None:
            self.set_soc_limit_override(soc_limit)
        home_day = await self._store.read(Platform.SWITCH, OWNED_SUFFIX_HOME_DAY, bool)
        if home_day is not None:
            self.home_day_flag = home_day
        for weekday, suffix in enumerate(OWNED_SUFFIX_DEPARTURE_DOW):  # Monday=0 .. Sunday=6
            value = await self._store.read(Platform.TIME, suffix, time_of_day)
            if value is not None:
                self.departure_dow_defaults[weekday] = value
        holiday = await self._store.read(Platform.TIME, OWNED_SUFFIX_DEPARTURE_HOLIDAY, time_of_day)
        if holiday is not None:
            self.departure_holiday_override = holiday
        home_day_override = await self._store.read(
            Platform.TIME, OWNED_SUFFIX_DEPARTURE_HOME_DAY, time_of_day
        )
        if home_day_override is not None:
            self.departure_home_day_override = home_day_override

    def _dispatch_mode(self, ctx: CycleContext) -> float:
        """The disconnect/Off/Power/SOC-gated-stop guards around the ModeHandler registry lookup
        (ADR-0012's lookup itself is untouched -- this method only names the surrounding branches
        that decide *whether* to look one up at all). Reads ev_soc/active_soc_limit off ctx rather
        than as separate parameters -- both are already there (set earlier this cycle, before this
        call), and threading them again as loose kwargs would reintroduce the two-sources-of-truth
        problem CycleContext exists to eliminate. Mutates self._mode_state exactly as today;
        returns the desired current before any clamp (ADR-0023)."""
        if ctx.status not in CHARGEABLE_STATES:
            # R7/R11: disconnect resets every mode's state, clearing hold/cooldown -- and, for
            # a solar mode or Captar, also ends any SOC gate (resume condition 2: unplug/replug).
            self._mode_state = self._fresh_mode_state()
            return 0.0
        if self.active_mode == MODE_OFF:
            return 0.0
        if self.active_mode == MODE_POWER:
            # ADR-0012: routed through the registry too, for observability/consistency with the
            # other modes, but MODE_POWER has no entry in _fresh_mode_state() and must not gain
            # one -- i.e. _PowerModeHandler.is_soc_gated must stay False (design doc Sec 3.4).
            # Its returned state is discarded, never written to _mode_state. Unchanged
            # behavior: no SOC gate.
            desired, _ = self._mode_handlers[MODE_POWER].desired_current(ctx, None)
            return desired
        handler = self._mode_handlers[self.active_mode]
        if handler.is_soc_gated and ctx.ev_soc >= ctx.active_soc_limit:
            # R7: don't resume until the gate clears. Holding the state at idle() (rather than
            # dispatching into step()) means the next cycle where this branch stops matching --
            # because soc_limit_override rose (resume condition 1) -- dispatches fresh from
            # idle(), re-checking the start threshold normally. No latch, no separate phase.
            self._mode_state[self.active_mode] = handler.idle_state()
            return 0.0
        # ADR-0012: one ModeHandler registry lookup replaces the old per-mode if/elif chain
        # (MODE_SOLAR/MODE_SOLAR_ONLY/MODE_CAPTAR -- the only modes that can still reach this
        # branch, since MODE_OFF/MODE_POWER/the SOC-gated-stop guard above all handle their own
        # case first). Each handler wraps its modes/*.py step()/desired_current() unchanged;
        # only the lookup mechanism changed.
        desired, self._mode_state[self.active_mode] = handler.desired_current(
            ctx, self._mode_state.get(self.active_mode)
        )
        return desired

    def _apply_peak_clamp(
        self,
        desired: float,
        *,
        net_w: float,
        charger_w: float,
        voltage: float,
        effective_peak_limit_kw: float,
        now: float,
    ) -> float:
        """R3 peak clamp (E5) -- skippable only for Power via its own R17 opt-out (design doc
        Sec 7). `desired` here is the already-computed mode request from `_dispatch_mode` --
        apply_peak_clamp's breach timer only starts/continues when `desired >= min_a`, so the
        disconnect/Off/SOC-gated branches (all `desired = 0.0`) can never trip force_stop this
        cycle, regardless of headroom. A separate named call from the C4 grid-ceiling clamp
        below, per ADR-0006's requirement that the two never merge into one routine -- merging
        them would let the R17 opt-out silently reach C4 too. Mutates self._peak_tracker and, on a
        force-stop while Captar is active, self._mode_state[MODE_CAPTAR] -- both exactly as
        before this extraction (ADR-0023)."""
        if self.active_mode == MODE_POWER and not self._config.power_respect_peak:
            return desired
        desired, self._peak_tracker, force_stop = apply_peak_clamp(
            desired,
            net_w=net_w,
            charger_w=charger_w,
            voltage=voltage,
            effective_peak_limit_kw=effective_peak_limit_kw,
            safety_margin_w=self._config.safety_margin_w,
            min_a=self._config.min_current,
            grace_period_s=self._config.peak_grace_min * 60,
            tracker=self._peak_tracker,
            now=now,
        )
        if force_stop and self.active_mode == MODE_CAPTAR:
            desired = 0.0
            self._mode_state[MODE_CAPTAR] = captar.CaptarState(Phase.COOLDOWN, now)
        return desired

    def _apply_grid_ceiling_clamp(
        self, desired: float, *, net_w: float, charger_w: float, voltage: float
    ) -> float:
        """C4 grid-supply-ceiling clamp (E6) -- never skippable, no opt-out of any kind. A
        separate named call from the R3 clamp above, per ADR-0006 -- merging the two, or adding
        a shared parameter, would risk the R17 opt-out silently reaching C4 too. Extracted from
        `_run_cycle` per ADR-0023."""
        return clamp_to_ceiling(
            desired,
            net_w=net_w,
            charger_w=charger_w,
            voltage=voltage,
            ceiling_a=self._config.grid_ceiling_a,
            offset_a=self._config.grid_safety_offset_a,
        )

    def _fresh_mode_state(self) -> dict:
        """R7/R11: the idle state every SOC-gated mode resets to -- disconnect, mode switch,
        and the SOC gate all rebuild from this same shape. Derived from the ModeHandler
        registry (ADR-0012) rather than a hand-maintained per-mode dict, so a new SOC-gated
        mode only needs a registry entry with `is_soc_gated = True`, not a new branch here."""
        return {
            mode: handler.idle_state()
            for mode, handler in self._mode_handlers.items()
            if handler.is_soc_gated
        }

    def _reset_mode_state_if_changed(self) -> None:
        """R11: switching mode resets timers -- fresh state for every mode with one, whether
        or not the incoming mode is one of them (a state nobody is dispatching to is inert
        either way). Idempotent -- a no-op once `_last_active_mode` catches up, so calling
        this twice in the same cycle (Manual's change is already final at the top of the
        cycle; Auto's own mode isn't resolved until later) never double-resets."""
        if self.active_mode != self._last_active_mode:
            self._mode_state = self._fresh_mode_state()
            self._last_active_mode = self.active_mode

    def set_target_current(self, value: float) -> None:
        """Coordinator's own boundary for `target_current` (ADR-0014). Clamps to the
        configured `[CONF_MIN_CURRENT, CONF_MAX_CURRENT]` bound -- previously enforced only by
        `TargetCurrentNumber`'s own native_min_value/native_max_value, bypassable by any other
        caller writing the field directly. Never the write path for a commanded stop -- ADR-0007's
        fault path writes 0 A via `self._write(0.0)` directly, not through this field. Since
        ADR-0018, `number.py` never calls this directly: the coordinator reads the stored value
        through the Store each cycle (`_read_owned_entities`) and calls this itself; the only
        other caller is tests."""
        self.target_current = min(max(value, self._config.min_current), self._config.max_current)

    def seed_monthly_peak(self, kw: float, month: tuple[int, int] | None) -> None:
        """Coordinator's own boundary for seeding `_peak_demand` from MonthlyPeakSensor's
        restored state (ADR-0012) -- the intended write path for sensor.py, replacing its
        previous direct reach into `_peak_demand`'s private fields. Delegates the actual
        clamping/assignment to `PeakDemandState.seed()` itself, so `_peak_demand`'s fields stay
        owned by one method regardless of which module calls in."""
        self._peak_demand.seed(kw, month)

    @property
    def monthly_peak_period_month(self) -> str | None:
        """The read-direction counterpart to `seed_monthly_peak` -- lets sensor.py read
        the tracked month without reaching into `_peak_demand`'s private fields itself."""
        return self._peak_demand.period_month

    def set_active_profile(self, profile: str) -> None:
        """Coordinator's own boundary for `active_profile` (ADR-0014) -- the field itself stays
        a plain writable attribute (design doc §2, criterion 1). No range to clamp:
        `SelectEntity`'s own `options` list already rejects any value outside the enum before
        it is ever stored. Since ADR-0018, `select.py` never calls this directly: the
        coordinator reads the stored option through the Store each cycle
        (`_read_owned_entities`) and calls this itself; the only other caller is tests."""
        self.active_profile = profile

    def _mode_desired_current(
        self,
        mode: str,
        *,
        status: str,
        ev_soc: float,
        active_soc_limit: float,
        surplus_w: float,
        voltage: float,
        now: float,
    ) -> float:
        """`mode`'s own desired current this cycle, via the same `ModeHandler` registry the
        real dispatch uses (ADR-0012), without mutating any persisted per-mode
        state -- the baseline-mode comparison needs a candidate mode's request
        without actually charging on it.

        `net_w`/`charger_w`/`now_dt` are deliberately 0.0/0.0/None here, not threaded from
        the caller: none of the five `ModeHandler.desired_current` implementations reads
        `ctx.net_w`, `ctx.charger_w`, or `ctx.now_dt` (only `ctx.surplus_w`/`ctx.voltage`/
        `ctx.now`/`ctx.status`) -- the one intentional exception `CycleContext.now_dt`'s
        `datetime | None` typing documents. If a future ModeHandler needs any of these
        three, thread the real values from `_run_cycle` at that point, not before."""
        if status not in CHARGEABLE_STATES:
            return 0.0
        if self._mode_handlers[mode].is_soc_gated and ev_soc >= active_soc_limit:
            return 0.0
        ctx = CycleContext(
            status=status,
            net_w=0.0,
            charger_w=0.0,
            voltage=voltage,
            now=now,
            now_dt=None,
            ev_soc=ev_soc,
            surplus_w=surplus_w,
            active_soc_limit=active_soc_limit,
        )
        current, _ = self._mode_handlers[mode].desired_current(ctx, self._mode_state.get(mode))
        return current

    async def _write(self, value: float) -> None:
        await self._adapters[ROLE_CHARGER_CURRENT].write(value)

    async def _safe_write_zero(self) -> None:
        try:
            await self._write(0.0)
        except Exception:  # noqa: BLE001 - best-effort stop
            _LOGGER.exception("smart_charging failed to write 0 A during fault")

    def _log_fault(self, reason: str) -> None:
        if not self._was_faulted:
            _LOGGER.warning("smart_charging fault: %s", reason)
            self._was_faulted = True
