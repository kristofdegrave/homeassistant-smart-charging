"""Charging Coordinator (M1) — the control cycle (ADR-0006/0007)."""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
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
    BASELINE_DEBOUNCE_CYCLES,
    CHARGEABLE_STATES,
    DEFAULT_SOC_LIMIT,
    DOMAIN,
    EVENT_ACTIVE_SOC_LIMIT_CHANGED,
    EVENT_DEADLINE_UNREACHABLE_CLEARED,
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
    ROLE_MONTHLY_PEAK_EXTERNAL,
    ROLE_NET_POWER,
    ROLE_SOLAR_FORECAST,
    ROLE_SOLAR_POWER,
    ROLE_SUN,
    ROLES_ADAPTER_READINGS_EXCLUDED,
    SOC_LIMIT_OVERRIDE_MAX,
    SOC_LIMIT_OVERRIDE_MIN,
)
from .coordinator_cycle import (
    ActiveCooldown,
    CycleContext,
    DeadlineUnreachableEdge,
    DeadlineUrgencyInputs,
    ModeHandler,
    PeakDemandState,
    SocGateResolver,
    SolarStepUpGate,
    build_mode_handlers,
    resolve_deadline_urgency,
    resolve_solar_reserve_gate,
)
from .engines.billing_protection import (
    BaselineDebouncer,
    PeakBreachTracker,
    apply_peak_clamp,
    debounce_baseline_w,
    peak_headroom_a,
    resolve_effective_peak_limit,
    resolve_monthly_peak_operand,
)
from .engines.cycle_invariant import apply_floor_cap
from .engines.deadline import RequiredCurrentResult, resolve_departure_deadline
from .engines.grid_safety import ceiling_headroom_a, clamp_to_ceiling
from .engines.signal_conditioning import HouseholdWindow, resolve_voltage, smooth_household_baseline
from .modes._phase import Phase
from .profiles.policy import PROFILE_POLICIES

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
        # below) even though it never goes through
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
        # Four fields whose lifecycle must survive `_reset_mode_state_if_changed`'s per-mode-
        # switch rebuild of `_mode_state` -- each is genuinely its own concern, none sharing
        # any other's reason (`_init_mode_switch_survivors`'s own docstring states each in
        # full), grouped into one call only so __init__ stays under the ADR-0046 statement
        # guard as this class keeps growing.
        self._init_mode_switch_survivors()
        # ADR-0011: resolves the active SOC limit and detects a change from the prior cycle for
        # ActiveSocLimitChanged (ADR-0012's SocGateResolver). The first resolution reached (an
        # early-faulted cycle never reaches it) always reports changed=True.
        self._soc_gate = SocGateResolver()
        # ADR-0024: pure True->False edge detection over resolve_deadline_urgency's own
        # `unreachable` flag, feeding the paired DeadlineUnreachableCleared fire below. Never
        # reset on either fault early-return -- both sit upstream of this detector's own call
        # site, so a fault cycle simply never reaches it and its prior flag is held (see the
        # comments on those two returns).
        self._unreachable_edge = DeadlineUnreachableEdge()
        # R5 (issue #1078): whether deadline urgency was in effect entering the next cycle --
        # the third flag threaded across cycles, alongside the solar step-up and (once #1006
        # lands) the missed-deadline hold. Urgency is ENTERED by the slack test and LEFT by the
        # handback test, which are not each other's inverse: charging at the escalated rate
        # closes the gap faster than the clock closes the window, so a latch-free implementation
        # would revert urgency on the cycle after it engaged and duty-cycle the charger.
        # Cleared for free on every one of urgency's own clear conditions, because each already
        # funnels through the resolved `urgent` this is assigned from -- a disconnect and an
        # unresolvable deadline both short-circuit resolve_deadline_urgency to urgent=False.
        self._urgency_latched: bool = False
        # R9/R14 inputs -- read through the Store each cycle (_read_owned_entities,
        # ADR-0018), from switch.smart_charging_home_day / time.smart_charging_departure_*.
        # These constructor defaults (no home day, no configured deadline anywhere) only
        # matter before the first read.
        # NF14: the set of calendar dates the home-day flag currently applies to -- at most
        # today's and tomorrow's at once (switch.py's own module docstring explains why a
        # single date/bool can't represent both). R14's resolve_deadline_for and R9's
        # resolve_solar_reserve_gate each query membership in this set for the concrete date
        # being resolved, so the flag for one date can never leak into another's resolution.
        self.home_day_dates: set[date] = set()
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
        # Same once-per-outage discipline as `_last_rejected_mode`, for `set_active_profile`'s
        # own registry guard (issue #718's PROFILE_POLICIES lookup) -- a corrupted stored
        # profile would otherwise re-read and re-reject identically every cycle.
        self._last_rejected_profile: str | None = None
        # R10/issue #1329: the household-baseline rolling window `smooth_household_baseline`
        # threads across cycles, plus its own one-cycle-deferral cap -- see `HouseholdWindow`.
        self._net_window = HouseholdWindow()
        self._mode_state = self._fresh_mode_state()
        self._was_faulted = False
        # ADR-0007/issue #1311: `_safe_write_zero`'s own once-per-outage dedup for the 0 A
        # write itself failing -- a distinct outage from `_was_faulted` above (the write can
        # keep failing for many cycles after the read-side fault that first forced it
        # recovers). See `_safe_write_zero`'s own docstring.
        self._write_zero_failing = False
        # M1's OWN 15-minute window (E5), distinct from R10's `_net_window` above --
        # a MonthlyPeakSensor restore may seed `_peak_demand.tracked_kw`/`.tracked_month` before
        # the first cycle; the window itself is deliberately never persisted (R21), so it
        # always starts empty here. Owned by PeakDemandState (ADR-0012).
        self._peak_demand = PeakDemandState()
        self._peak_tracker = PeakBreachTracker()
        # Issue #990: debounces peak_headroom_a/solar_surplus_w/apply_peak_clamp's own
        # baseline_w against a transient headroom-inflating reading (a charger current
        # step-down outrunning the charger_power adapter's slower poll cadence for one
        # extra cycle) -- see debounce_baseline_w's own docstring. Deliberately never reset
        # (disconnect, fault, a long adapter outage) -- same lifecycle as `_peak_tracker`
        # just above, which isn't reset either. Worst case, recovery to a genuinely lower
        # baseline after a long gap costs an extra `BASELINE_DEBOUNCE_CYCLES`, the same
        # safety-conservative direction the debounce itself always takes.
        self._baseline_debouncer = BaselineDebouncer()
        # ADR-0039/R3 case (a): the two fields `debounce_baseline_w`'s `command_changed` is
        # derived from -- see that function's docstring for what the engine does with it.
        # `_last_commanded_a` is the value `_write` last sent; `_command_stepped` is whether that
        # write changed it. Both are maintained in `_write` -- the single write site -- so the
        # fault paths' own `_write(0.0)` counts as a step exactly like a control-path write does,
        # which is correct: a fault-path drop to 0 A leaves the charger_power adapter just as
        # stale as any other step. Read once per cycle by `_run_cycle`, where `_command_stepped`
        # describes the write at the END of the PREVIOUS cycle -- which is what this cycle's
        # `charger_w` reading may not have caught up with yet. Never reset for the same reason
        # `_baseline_debouncer` above isn't: a stale `_last_commanded_a` after a long gap only
        # ever costs one extra discarded reading.
        self._last_commanded_a: float | None = None
        self._command_stepped = False
        # ADR-0021: `sensor.smart_charging_adapter_readings`' backing cache -- persisted across
        # cycles (never reset), holding each read role's most recently read value so a role not
        # read on a given cycle (e.g. `ev_soc` while disconnected) still reports its last known
        # value instead of disappearing, and a faulted cycle still reports whatever was read
        # before the fault.
        self._role_readings: dict[str, Any] = {}
        self._role_readings_at: datetime | None = None

    def _init_mode_switch_survivors(self) -> None:
        """Constructs/defaults the five fields `__init__` calls this for -- each survives
        `_reset_mode_state_if_changed`'s per-mode-switch rebuild of `_mode_state` for its own
        reason, stated here in full since none of the five has an assignment of its own left
        in `__init__` to hang a comment on:

        - `_step_up_gate` (R8's lifecycle state, threaded across cycles) -- cleared only via
          `SolarStepUpGate.resolve`'s own `is_solar_mode_charging=False` branch, never by the
          per-mode-switch reset (that would wrongly clear an in-effect step-up on a
          Solar<->SolarOnly switch, R7/UC06 alternate flow 4a). ADR-0023: `SolarStepUpGate`
          owns `SolarStepUpState` itself; `.state` is a plain mutable attribute, same seeding
          pattern as before via `self._step_up_gate.state = ...`.
        - `_has_charged` (R11's has-charged flag, issue #757) -- owned outside `_mode_state`
          for the exact same structural reason as `_step_up_gate`: `_reset_mode_state_if_changed`/
          `_fresh_mode_state` rebuild EVERY SOC-gated mode's state on any mode switch, including
          a Solar<->SolarOnly switch, but per R11/system-overview.md's `has-charged flag`
          glossary entry this flag must survive exactly that switch (scoped to the connection,
          not the active mode). A plain bool suffices here, unlike `SolarStepUpState`'s own
          richer shape -- there's no per-mode data to carry, only a single flip-once-per-
          connection bit. Set True in `_dispatch_mode` the first time a solar mode's own
          step() transitions into `Phase.CHARGING` while it was False; cleared back to False
          only on disconnect (`_dispatch_mode`'s own early branch) -- a fresh coordinator
          instance (a restart) already starts at False for free, so there is nothing to
          persist/restore for that case (R11's third clearing condition).
        - `_active_cooldown` (R11's rapid-cycling cooldown, issue #974) -- owned outside
          `_mode_state` for the exact same structural reason as the two above:
          `_reset_mode_state_if_changed`/`_fresh_mode_state` rebuild EVERY SOC-gated mode's
          state on any mode switch, including the mode that started a still-running cooldown,
          but requirements.md's R11 (and control-cycle.md's "Mode switched mid-operation" edge
          case) requires a running cooldown to survive exactly that switch, blocking a restart
          in whichever mode is active when it would otherwise happen, for the duration fixed at
          the moment charging stopped. `None` means no cooldown is running. Set in
          `_dispatch_mode` the instant a mode's own step() transitions into `Phase.COOLDOWN`;
          in `_apply_peak_clamp`, for Captar's own coordinator-forced cooldown entry (R3); and,
          since issue #1311, in `_start_fault_stop_cooldown` for a fault stop -- the latter two
          both through the shared `_start_cooldown` helper. Cleared to `None` only on disconnect
          (`_dispatch_mode`'s own early branch) -- same reset trigger as `_mode_state`/
          `_has_charged` there, per R7's resume condition for a car unplugged and replugged.
          Deliberately NOT reset by `_reset_mode_state_if_changed` -- that is the entire point
          (issue #974).
        - `_power_soc_limit_reached` (R17 AC4/R7, #1335, and UC04's *State of charge
          unavailable* exception flow, A5a/#1300) -- whether Power is currently stopped at the
          active SOC limit. Coordinator-scoped like `_active_cooldown` above -- not
          `_mode_state`, which Power never gains an entry in (`_fresh_mode_state` derives only
          from `is_soc_gated`, and `_PowerModeHandler.is_soc_gated` must stay False, ADR-0042).
          Refreshed once per cycle, whatever the active mode, by
          `_refresh_power_soc_limit_reached` -- see that method's own docstring for the full
          rule (a present reading always wins; with none, only the active SOC limit itself
          changing this cycle can clear an existing stop, never set one). Also cleared on a
          disconnect (`_dispatch_mode`'s own early branch, same trigger as `_active_cooldown`
          above -- resume condition 2, unplug/replug); neither that nor the per-cycle refresh
          is reached from `_reset_mode_state_if_changed` on a mode switch -- see that method's
          own docstring for why. A restart or reload needs no code of its own: both rebuild
          the coordinator from scratch (`__init__`), so this field is never persisted across
          either, matching NF14/UC04's "a restart or a reload clears that stop" the same way
          every other in-memory field here already does.
        - `_power_charging` (#1335) -- whether Power actually delivered current as of its own
          last dispatch, i.e. whether it is *currently in* UC04's Charging state rather than
          Idle or Cooldown. `_power_soc_limit_reached` above needs this: UC04's own words are
          "Only a stop made at the limit is held this way -- a car resting in Idle or Cooldown
          at or above the limit has no such stop behind it", so the SET side of that latch
          must tell a genuine Charging -> SocReached transition apart from a reading merely
          arriving at or above the limit while Power was never the one charging (Off active,
          a running cooldown, or Power's own first-ever cycle). Maintained only by
          `_dispatch_power` -- `True` the instant it returns a nonzero desired current, `False`
          the instant it returns 0.0 for any reason (cooldown-blocked or either of its two
          stop conditions); read by `_resolve_active_soc_limit`, before `_dispatch_mode` runs,
          as this cycle's *prior* value (last cycle's outcome), which is exactly the FSM's
          incoming state. Cleared on a disconnect alongside `_power_soc_limit_reached` (same
          trigger, same field docstring) -- **and**, unlike that field, also reset by
          `_reset_mode_state_if_changed` on every mode switch (its own docstring says why): a
          live claim that Power *is currently* delivering current stops being true the moment
          a different mode is dispatched instead, so it must not survive to be read back as
          still true once Power is selected again."""
        self._step_up_gate = SolarStepUpGate()
        self._has_charged: bool = False
        self._active_cooldown: ActiveCooldown | None = None
        self._power_soc_limit_reached: bool = False
        self._power_charging: bool = False

    async def _async_update_data(self) -> CycleResult:
        try:
            return await self._run_cycle()
        except Exception as err:  # noqa: BLE001 - every failure funnels to the fault path (ADR-0007)
            self._enter_fault(f"cycle exception: {err}")
            await self._safe_write_zero()
            self._clear_baseline_deferral()
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

    async def _read_role(self, role: str) -> Any:
        """ADR-0021: the one guarded optional-role read -- `role not in self._adapters` returns
        None without reading, otherwise reads and mirrors the value into `_role_readings` in the
        same place. Replaces every guarded optional-role read's hand-written if-guard/read/cache
        shape (issue #717); a prior extraction (ADR-0023, see the comment on
        `_resolve_deadline_and_reserve`)
        had silently dropped four of those copies' cache writes, which this single call site
        makes structurally impossible to drop again. Only for optional roles -- the three
        required reads in `_read_cycle_inputs` below have no `in self._adapters` guard at all
        and stay as they are."""
        if role not in self._adapters:
            return None
        value = await self._adapters[role].read()
        self._role_readings[role] = value
        return value

    async def _read_cycle_inputs(self) -> tuple[str, float, float, float] | None:
        """Steps 1 and 3 (ADR-0006): read the three required adapters and resolve voltage (NF4's
        fallback -- the one role where a None reading is not a fault). Returns None on a missing
        required adapter; _run_cycle performs the actual fault CycleResult itself, keeping
        ADR-0007's single fault-handling code path in _run_cycle rather than scattered across
        extracted methods (ADR-0023). Also caches each read role's value into
        `self._role_readings` (ADR-0021) -- the three required reads cache directly here,
        grid voltage's and solar power's optional reads cache inside `_read_role` (issue #717,
        #911). `_run_cycle`
        decides whether to advance `self._role_readings_at`, since that depends on whether
        this cycle succeeded as a whole (the required-adapter read succeeding is necessary
        but not sufficient, #648)."""
        status = await self._adapters[ROLE_CHARGER_STATUS].read()
        net_w = await self._adapters[ROLE_NET_POWER].read()
        charger_w = await self._adapters[ROLE_CHARGER_POWER].read()
        self._role_readings[ROLE_CHARGER_STATUS] = status
        self._role_readings[ROLE_NET_POWER] = net_w
        self._role_readings[ROLE_CHARGER_POWER] = charger_w

        # Grid voltage is the one role where None is NOT a fault (NF4).
        measured_v = await self._read_role(ROLE_GRID_VOLTAGE)
        voltage = resolve_voltage(measured_v, self._config.nominal_voltage)

        # Solar power: read every cycle, same as grid voltage, but not yet a control-path
        # operand -- issue #911 wires this role for reading (adapter_readings mirror) only.
        # R10 AC2 reads it raw and never smooths it; #587's real-consumer decision is what
        # stays deferred.
        await self._read_role(ROLE_SOLAR_POWER)

        # Any required role missing -> fault (ADR-0007).
        if status is None or net_w is None or charger_w is None:
            return None
        return status, net_w, charger_w, voltage

    async def _resolve_deadline_and_reserve(
        self, ctx: CycleContext, now_dt: datetime
    ) -> tuple[time_of_day | None, Callable[[date], time_of_day | None]]:
        """R14's departure-external/sun/low-tariff reads and the date-parameterised deadline
        table, plus R9's solar-reserve-cap gating (resolve_solar_reserve_gate,
        coordinator_cycle.py) -- the two are resolved together because R9's gate needs
        tomorrow's deadline, this same block's own result. Mutates ctx.sun_is_up/
        ctx.sun_is_down/ctx.low_tariff_active/ctx.solar_reserve_active in place (ADR-0012's
        existing "assign onto ctx as each value resolves" pattern) and returns
        (deadline_tomorrow, resolve_deadline_for) for _run_cycle's later use. deadline_tomorrow
        has two consumers, not one: R9's own gate (which deliberately fixes on tomorrow's
        calendar date) and R15's next-occurrence rule (issue #1005), which needs whichever date
        the occurrence falls on. They coincide today only because both are `now + 1 day` -- a
        future change to R9's lookahead must not silently move urgency with it, so re-resolve
        via the closure rather than widening this value's meaning if the two ever diverge.
        resolve_deadline_for is the closure `_read_deadline_urgency_inputs` (below) calls for
        today's deadline. is_holiday is
        hardcoded False -- R14's public-holiday source is not wired in yet, so row 2 of R14's
        table never matches. Each optional-role read here goes through `_read_role` (issue
        #717), which caches into `self._role_readings` (ADR-0021) as part of the same guarded
        read -- so ROLE_DEPARTURE_EXTERNAL/ROLE_SUN/ROLE_LOW_TARIFF/ROLE_SOLAR_FORECAST keep
        reporting their real reads in `sensor.smart_charging_adapter_readings` instead of a
        stale/None value forever.

        NF14/R13: `resolve_deadline_for` takes the concrete calendar date being resolved, not a
        bare weekday, and looks it up in `self.home_day_dates` -- the set of dates the home-day
        flag currently applies to (at most today's and tomorrow's at once). Resolving today's
        and tomorrow's deadline are two separate calls to the same closure with two different
        dates, so each reads the home-day flag for its own date and neither can leak into the
        other, which is what fixes the flag set in the evening for tomorrow also overriding
        today's resolution."""
        # Computed separately from the _read_role call below, not redundant with it:
        # resolve_deadline_for's `external_configured` param needs "role configured" as its
        # own signal, distinct from "value is None" -- a distinction `_read_role`'s single
        # None return can't carry.
        external_configured = ROLE_DEPARTURE_EXTERNAL in self._adapters
        external = await self._read_role(ROLE_DEPARTURE_EXTERNAL)
        sun_reading = await self._read_role(ROLE_SUN)
        ctx.sun_is_up = sun_reading == SUN_STATE_ABOVE_HORIZON
        ctx.sun_is_down = sun_reading == SUN_STATE_BELOW_HORIZON
        # An unmapped ROLE_LOW_TARIFF (or a None reading) keeps the glossary's own
        # single-tariff default -- "the signal is omitted and the flag is treated as
        # always active".
        ctx.low_tariff_active = True
        low_tariff_reading = await self._read_role(ROLE_LOW_TARIFF)
        if low_tariff_reading is not None:
            ctx.low_tariff_active = low_tariff_reading

        # R14's four-row table, evaluated for a given calendar date -- shared by both today's
        # deadline (urgency, below) and tomorrow's (R9's one-day-ahead precondition, UC07),
        # so the other six args can never drift apart between the two call sites. NF14: the
        # home-day row is looked up for THIS date alone, never for "whichever the flag was
        # last read for".
        def resolve_deadline_for(target_date: date) -> time_of_day | None:
            return resolve_departure_deadline(
                external_configured,
                external,
                is_holiday=False,
                holiday_override=self.departure_holiday_override,
                home_day_flag=target_date in self.home_day_dates,
                home_day_override=self.departure_home_day_override,
                day_of_week_default=self.departure_dow_defaults.get(target_date.weekday()),
            )

        # R9's precondition (UC07): the same R14 table evaluated one day ahead.
        tomorrow_date = now_dt.date() + timedelta(days=1)
        deadline_tomorrow = resolve_deadline_for(tomorrow_date)
        forecast_kwh = await self._read_role(ROLE_SOLAR_FORECAST)
        ctx.solar_reserve_active = resolve_solar_reserve_gate(
            profile=self.active_profile,
            home_day_flag=tomorrow_date in self.home_day_dates,
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
        today_date: date,
        resolve_deadline_for: Callable[[date], time_of_day | None],
    ) -> tuple[time_of_day | None, float]:
        """The R5/R14/R15 deadline-urgency call site's own adapter reads (today's deadline, the
        sensed battery capacity) -- must stay coordinator-side even though resolve_deadline_urgency
        itself is already a pure coordinator_cycle.py function. Only `deadline_today` is gated
        behind `deadline_resolvable`, never the sensed-capacity read: that read already feeds the
        `_role_readings` diagnostic mirror (ADR-0021) unconditionally, every cycle, so gating it
        would regress that diagnostic to a stale value whenever the deadline isn't resolvable
        (e.g. disconnected). Returns
        (deadline_today, effective_battery_capacity_kwh); deadline_today is None when
        deadline_resolvable is False, exactly as today (resolve_deadline_urgency short-circuits
        before reading it)."""
        sensed_capacity_kwh = await self._read_role(ROLE_EV_BATTERY_CAPACITY)
        effective_battery_capacity_kwh = sensed_capacity_kwh
        if effective_battery_capacity_kwh is None:
            effective_battery_capacity_kwh = self._config.ev_battery_capacity_kwh
        deadline_today = resolve_deadline_for(today_date) if deadline_resolvable else None
        return deadline_today, effective_battery_capacity_kwh

    async def _run_cycle(self) -> CycleResult:
        await self._read_owned_entities()
        now_dt = dt_util.now()
        inputs = await self._read_cycle_inputs()
        if inputs is None:
            self._enter_fault("required adapter returned None")
            await self._write(0.0)
            self._clear_baseline_deferral()
            # `_role_readings_at` deliberately does NOT advance to `now_dt` here --
            # ADR-0021 and entity-catalog.md's `sensor.smart_charging_adapter_readings` row
            # define the entity's own state as the timestamp of
            # the LAST SUCCESSFUL cycle, and a required-role fault means this cycle wasn't one;
            # the cache keeps whichever timestamp a prior successful cycle set, even though the
            # per-role values `_read_cycle_inputs` just cached are this cycle's own (possibly
            # None) readings. `self._unreachable_edge`'s prior flag is held for the same reason
            # (ADR-0024): this return sits upstream of its call site below, so a fault cycle
            # never reaches it and must not be treated as a genuine resolve.
            return CycleResult(
                commanded_current=0.0,
                fault=True,
                active_mode=self.active_mode,
                adapter_readings=self._current_adapter_readings(),
                adapter_readings_at=self._role_readings_at,
            )
        status, net_w, charger_w, voltage = inputs

        # Issue #990: debounce the raw (net_w - charger_w) baseline once here, before it feeds
        # solar_surplus_w/peak_headroom_a/apply_peak_clamp below -- a single source of truth so
        # all three stay in lockstep and none can transiently see the inflated (undebounced)
        # reading the others already reject. See debounce_baseline_w's own docstring.
        # ADR-0039: `command_changed` describes the write at the end of the PREVIOUS cycle -- the
        # one this cycle's `charger_w` may not have caught up with -- so it is read here, before
        # this cycle's own `_write` overwrites it.
        baseline_w, self._baseline_debouncer = debounce_baseline_w(
            net_w - charger_w,
            self._baseline_debouncer,
            debounce_cycles=BASELINE_DEBOUNCE_CYCLES,
            command_changed=self._command_stepped,
        )

        # entity-catalog.md's `sensor.smart_charging_solar_surplus_w` row / glossary -- raw
        # net_w, deliberately distinct from `surplus_w`
        # below (R10's smoothed control-path value). Floored at 0: a negative reading here
        # would mean the household is drawing more than the charger, never actual solar
        # surplus (glossary) -- max(), not the debounce above, is the boundary for that (issue
        # #990's Direction section: the two are separate concerns).
        solar_surplus_w = max(-baseline_w, 0.0)

        # Peak-Demand Tracker (E5) + effective-peak-limit resolution (E5) --
        # runs every cycle regardless of mode (R3's bookkeeping is not Captar-specific). Uses
        # real wall-clock (`now_dt`, read at the top of `_run_cycle`) for month rollover,
        # distinct from the monotonic `now` the mode state machines use below.
        monthly_peak_kw = self._peak_demand.update(
            net_w, now_dt, window_size=self._config.peak_window_size
        )
        # ADR-0030/ADR-0032: an optional external monthly-peak reading (DSO/smart-meter),
        # merged with the internally-tracked value into the clamp's operand. Never gated on
        # captar_available -- R21 AC7 (tracking runs every cycle regardless of which
        # capabilities are declared) requires the value to still be tracked and surfaced for
        # observability even when the CapTar capability is absent, though
        # `_peak_clamp_would_run`'s own gate
        # (R3 AC1, issue #1018) means no charging decision ends up consulting it in that case.
        # monthly_peak_kw itself keeps meaning only the internally-tracked peak: it is
        # never overwritten with the merged value, so a live spike this integration observes
        # between external-sensor refreshes is not discarded.
        external_peak_kw = await self._read_role(ROLE_MONTHLY_PEAK_EXTERNAL)
        peak_operand_kw = resolve_monthly_peak_operand(monthly_peak_kw, external_peak_kw)
        # Fallback for the ev_soc-fault early return below, where real urgency can't yet be
        # known -- overwritten with the real `urgent` value once required-current resolves.
        effective_peak_limit_kw = resolve_effective_peak_limit(
            peak_operand_kw,
            self._config.max_peak_kw,
            self._config.peak_floor_kw,
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
        # a solar mode or Captar is selected AND the car is connected (Power/Off must not
        # regress to needing an SOC sensor; a disconnected car is a clean idle
        # stop, not a fault, even if its SOC sensor also goes unavailable on unplug, per UC01/R7);
        # outside that gate a missing reading just means deadline urgency can't be computed this
        # cycle (below), not a fault.
        ev_soc = await self._read_role(ROLE_EV_SOC) if status in CHARGEABLE_STATES else None
        if (
            self._mode_handlers[self.active_mode].is_soc_gated
            and status in CHARGEABLE_STATES
            and ev_soc is None
        ):
            self._enter_fault("ev_soc required while a solar mode is active but missing/None")
            await self._write(0.0)
            # `_role_readings_at` deliberately does NOT advance to `now_dt` here -- same
            # ADR-0021 and the `sensor.smart_charging_adapter_readings` row's "last successful
            # cycle" reasoning as the
            # required-role fault path above (#648): an ev_soc fault means this cycle wasn't
            # a successful one, even though the three required-adapter reads that fed
            # `solar_surplus_w`/`monthly_peak_kw` above did succeed. (The assignment itself
            # now lives at the very end of a successful cycle, see the comment there.)
            # `self._unreachable_edge`'s prior flag is held for the same reason (ADR-0024):
            # this return also sits upstream of its call site below.
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
        # Issue #1329/R10: folds `net_w - charger_w` (the household's own load, independent of
        # what the charger itself drew) into the window -- NOT `net_w` alone with `charger_w`
        # subtracted afterwards (the old `smoothed_net_w = smooth_net_power(net_w, ...)` /
        # `surplus_w = charger_w - smoothed_net_w` shape). That old shape averaged `net_w`
        # samples taken while the charger was drawing whatever it was set to on each earlier
        # cycle, then compared the result against THIS cycle's own charger_w -- an
        # apples-to-earlier-oranges mismatch that never let Solar/SolarOnly's set-point settle
        # under steady inputs (modelled in the issue). `command_changed=self._command_stepped`
        # is the same signal `debounce_baseline_w` above already reads for R3 (ADR-0039): a
        # reading taken on a cycle whose command changed is partly a measurement of this
        # integration's own actuation, and `smooth_household_baseline` leaves the window
        # untouched on such a cycle rather than admit it. See that function's own docstring.
        smoothed_household_w, self._net_window = smooth_household_baseline(
            net_w - charger_w,
            self._net_window,
            size=self._config.smoothing_window,
            command_changed=self._command_stepped,
        )
        surplus_w = -smoothed_household_w  # shared by Solar/SolarOnly dispatch below and the
        # baseline-mode dry-run.
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
            baseline_w=baseline_w,
            ev_soc=ev_soc,
            surplus_w=surplus_w,
            # R11/issue #757: mirrors this cycle's has-charged flag onto ctx so
            # _SolarModeHandler/_SolarOnlyModeHandler (coordinator_cycle.py) can read it without
            # either the ModeHandler Protocol or CycleContext's construction elsewhere needing
            # to know about it -- _dispatch_mode (below) flips self._has_charged itself, off
            # this same ctx's is_solar_mode/new-state-phase check.
            has_charged=self._has_charged,
        )
        # R8 is Auto-only, like R9's reserve cap (resolution-rules.md) -- computed fresh every
        # cycle from THIS cycle's active_profile and active_mode. Under Manual, active_mode is
        # already this cycle's final value (set externally before the cycle runs); under Auto,
        # it's still the PRIOR cycle's resolved mode here (Auto's own mode isn't resolved until
        # later, below) -- one cycle of lag, which is what R16 allows an Auto-driven mode
        # change ("takes effect within the next control cycle").
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

        # R5/R14/R15: `today_date` stays inline -- _read_deadline_urgency_inputs (below)
        # needs it as a parameter; only `tomorrow_date` moved into
        # _resolve_deadline_and_reserve (ADR-0023).
        today_date = now_dt.date()
        deadline_tomorrow, resolve_deadline_for = await self._resolve_deadline_and_reserve(
            ctx, now_dt
        )
        active_soc_limit = self._resolve_active_soc_limit(ctx)

        # `auto_dispatchable` is also this cycle's own gate for actually resolving Auto's
        # active mode below -- computed once here and reused there (and inside
        # resolve_deadline_urgency), rather than repeating the same conjunction, so the two
        # can never drift apart. When it's False (disconnected, or Auto with no ev_soc role
        # mapped at all), Auto simply keeps whatever active_mode it last resolved -- a
        # deliberate, scope-truthful simplification, same as required-current's own guard
        # inside resolve_deadline_urgency.
        # This `active_profile` check is deliberately NOT routed through the ADR-0017
        # PROFILE_POLICIES registry: it decides WHETHER mode selection dispatches this cycle
        # at all, not WHICH mode is selected -- the one decision ADR-0017's Context scopes to
        # the registry. The actual selection (both the baseline and the real call) already
        # goes through PROFILE_POLICIES[PROFILE_AUTO].select(...) in resolve_deadline_urgency,
        # gated by this same flag.
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
        # `_read_deadline_urgency_inputs` (ADR-0023).
        deadline_resolvable = status in CHARGEABLE_STATES and ev_soc is not None
        deadline_today, effective_battery_capacity_kwh = await self._read_deadline_urgency_inputs(
            deadline_resolvable=deadline_resolvable,
            today_date=today_date,
            resolve_deadline_for=resolve_deadline_for,
        )
        deadline_urgency = resolve_deadline_urgency(
            ctx,
            DeadlineUrgencyInputs(
                deadline_resolvable=deadline_resolvable,
                active_mode=self.active_mode,
                deadline_today=deadline_today,
                # R15/issue #1005: the next occurrence may fall tomorrow (today's departure
                # time already passed), and R14's terminal row is a day-of-week default, so
                # tomorrow's own resolution is needed rather than today's time on tomorrow's
                # date. This is the same value R9's solar-reserve gate already resolved above
                # -- reused, not resolved a second time -- gated on `deadline_resolvable` here
                # so it matches `deadline_today`'s own gating (R9 needs it ungated).
                deadline_tomorrow=deadline_tomorrow if deadline_resolvable else None,
                now_dt=now_dt,
                effective_battery_capacity_kwh=effective_battery_capacity_kwh,
                escalated_maximum_permitted_rate_a=self._escalated_maximum_permitted_rate_a(
                    ctx, peak_operand_kw=peak_operand_kw
                ),
                urgency_latched=self._urgency_latched,
                auto_dispatchable=auto_dispatchable,
                solar_available=self._config.solar_available,
                captar_available=self._config.captar_available,
                solar_start_threshold_w=self._config.solar_start_threshold_w,
            ),
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
        # ADR-0024: reading `required.unreachable` itself (never any one upstream guard) is
        # what makes every exit path -- required current falling back in range, a disconnect,
        # the deadline capability withdrawn -- clear for free, since each already funnels
        # through this same flag.
        _, cleared = self._unreachable_edge.resolve(required.unreachable)
        if cleared:
            self.hass.bus.async_fire(EVENT_DEADLINE_UNREACHABLE_CLEARED)
        if required.unreachable:
            # engines/deadline.py saturates required_a to float('inf') for a deadline at or
            # before `now` -- still the pure engine's own documented contract, and since issue
            # #1005 all but unreachable from this cycle: resolve_next_occurrence yields an
            # occurrence after `now`, except inside a fall-back repeated hour where a fold=1
            # `now` can wall-clock-precede a fold=0 occurrence that is absolutely earlier. So
            # the cap below still guards a real (if once-a-year) path, not only a future
            # regression. float('inf') must never
            # cross this boundary: it doesn't round-trip through HA's JSON websocket encoding,
            # and notification_manager.py formats it straight into user-facing text (issue
            # #650). Cap it to maximum_permitted_rate_a -- the same bound the engine compared
            # required_a against to set `unreachable` in the first place, so "would need at
            # least max_current A" is exactly true, not an arbitrary numeric artifact like
            # sys.float_info.max would be. NaN needs no separate branch: it can never reach
            # here since `nan > maximum_permitted_rate_a` is always False, which would leave
            # `unreachable` False and this block unentered.
            notified_required_a = (
                self._config.max_current if math.isinf(required.required_a) else required.required_a
            )
            self.hass.bus.async_fire(
                EVENT_DEADLINE_UNREACHABLE_NOTIFIED,
                {ATTR_REQUIRED_CURRENT_A: notified_required_a},
            )

        urgent = deadline_urgency.urgent
        # The latch this cycle's resolution leaves behind. Assigned from the resolved `urgent`
        # rather than from the slack test alone, so the handback -- and every other clear
        # condition that funnels through it -- releases the latch without a second code path.
        # Both fault early-returns above sit UPSTREAM of this line, so a fault cycle holds
        # whichever latch it entered with rather than clearing it -- the same reasoning
        # `_role_readings_at` and `_unreachable_edge` carry in those blocks (ADR-0024): a cycle
        # that established nothing about the deadline must not decide anything about it either.
        # A fault is not one of R5's clear conditions, and the cycle forces 0 A regardless.
        self._urgency_latched = urgent
        effective_peak_limit_kw = resolve_effective_peak_limit(
            peak_operand_kw, self._config.max_peak_kw, self._config.peak_floor_kw, urgent=urgent
        )
        # This is the only ctx.effective_peak_limit_kw assignment -- the earlier, provisional
        # resolve_effective_peak_limit(urgent=False) call above (used only for the ev_soc-fault
        # early return) runs before `ctx` is constructed, so ctx's field intentionally carries
        # its dataclass default (None, issue #564) until this final, real value lands here.
        # `_apply_peak_clamp` (below) reads it off `ctx` rather than as a separately-passed
        # kwarg (issue #719) -- there is no second copy for the two to drift out of lockstep.
        ctx.effective_peak_limit_kw = effective_peak_limit_kw

        # entity-catalog.md's `sensor.smart_charging_peak_headroom_a` row / control-cycle.md
        # step 5 -- the same target and (issue #990:
        # debounced) baseline the R3 clamp itself holds. Since issue #1078 this shares
        # `apply_peak_clamp`'s own arithmetic through `peak_headroom_a` rather than restating
        # it, so the readout cannot drift from the clamp it reports on while the clamp runs at
        # all; with the CapTar capability absent (R3 AC1, issue #1018) the clamp does not run,
        # yet this readout still resolves and is surfaced (R21's own AC), simply consulted by
        # no charging decision in that case. Reading it here instead of returning it from
        # `_apply_peak_clamp` still avoids changing that control-path signature for a
        # display-only need.
        peak_headroom = peak_headroom_a(
            baseline_w=ctx.baseline_w,
            voltage=voltage,
            effective_peak_limit_kw=effective_peak_limit_kw,
            safety_margin_w=self._config.safety_margin_w,
        )
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

        desired = self._apply_peak_clamp(ctx, desired)

        desired = self._apply_grid_ceiling_clamp(ctx, desired)
        desired = apply_floor_cap(  # E8 invariant last
            desired, min_a=self._config.min_current, max_a=self._config.max_current
        )

        # entity-catalog.md's `sensor.smart_charging_time_to_full` row / glossary -- "the
        # charger's current applied rate"/`charger_current`
        # is the value actually written, i.e. `desired` AFTER every clamp/floor/cap, not the
        # mode's pre-clamp request -- a clamped or floored-to-0 cycle must not report an ETA
        # that assumes a rate the charger was never actually set to. `ev_soc >= active_soc_limit`
        # is checked before the 0 A case so a SOC-gated-stop cycle (which also sets desired=0.0)
        # still reports 0, not unknown, per that same catalog row.
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
        # ADR-0021 and the `sensor.smart_charging_adapter_readings` row's "last successful
        # cycle" -- deliberately the LAST
        # statement before the success return, not right after `_read_cycle_inputs` (#648):
        # any exception between the required-adapter read and this point (including the
        # ev_soc-fault gate above, and any raise from the write itself) funnels to
        # `_async_update_data`'s handler and must report a prior cycle's timestamp, not this
        # one's -- moving this assignment any earlier would resurrect #648 for those paths.
        self._role_readings_at = now_dt
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
            peak_headroom_a=peak_headroom,
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
        plain writable attribute but this is its only
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
        """RA3 (ADR-0018): reads all eight owned control-entity values -- twelve individual
        `Store.read()` calls, since `departure_dow_defaults` alone spans seven weekday entities
        -- through the Store once per cycle. A None read leaves the field unchanged -- not a
        fault: owned entities are internal, and a startup-race/transient-unavailable read is not
        the same kind of missing data as a hardware adapter returning None (ADR-0007).

        #652 investigated batching these reads with `asyncio.gather`, since none has a data
        dependency on another (the mode read's *application* depends on the profile read's
        result, handled below exactly as before -- but its *read* doesn't). Rejected:
        `Store.read()` (`adapters/store.py`) never actually awaits anything -- both
        `resolve_entity_id()` and `hass.states.get()` are synchronous in-memory lookups -- so
        `gather` would add `Task`-creation overhead for zero real concurrency, and would cost
        this method its current atomicity-with-respect-to-the-event-loop (a `gather`'d read
        yields control, letting a user's own change to one of these entities land between two
        reads within the same cycle; a plain sequential `await` chain over non-yielding
        coroutines never does). Measured harness cost confirmed the direction was wrong too: see
        #652 for the numbers. Reads stay sequential; only the readability half of #652's ask
        survives, via the `(platform, suffix, value_type, setter)` table below for the five
        reads with no cross-read dependency."""
        # Profile first: the mode read/apply immediately below needs this cycle's resolved
        # active_profile, not last cycle's.
        profile = await self._store.read(Platform.SELECT, OWNED_SUFFIX_PROFILE, str)
        if profile is not None:
            self.set_active_profile(profile)
        # Only Manual dispatches via the selector (coordinator.py's own long-standing rule,
        # applied below at the `auto_dispatchable` check) -- under Auto, self.active_mode is
        # select_mode()'s own resolution, carried across cycles; re-reading the selector's
        # raw (stale, user-facing) value here every cycle would fight that resolution and
        # falsely register as a mode *change* to _reset_mode_state_if_changed() right below,
        # silently discarding R7/R11 timers and R3's breach cooldown every single cycle.
        # Resolved via the ADR-0017 registry (issue #718) -- `ManualPolicy.select` is a pure
        # pass-through of `active_mode`, so this is behaviorally identical to assigning `mode`
        # directly, but it means Manual's own dispatch actually goes through the
        # `ModeSelectionPolicy` the registry was built for, rather than bypassing it.
        if self.active_profile != PROFILE_AUTO:
            mode = await self._store.read(Platform.SELECT, OWNED_SUFFIX_MODE, str)
            if mode is not None:
                resolved_mode = PROFILE_POLICIES[self.active_profile].select(active_mode=mode)
                self.set_active_mode(resolved_mode)

        simple_reads: tuple[tuple[str, str, type, Callable[[Any], None]], ...] = (
            (Platform.NUMBER, OWNED_SUFFIX_TARGET_CURRENT, float, self.set_target_current),
            (
                Platform.NUMBER,
                OWNED_SUFFIX_SOC_LIMIT_OVERRIDE,
                float,
                self.set_soc_limit_override,
            ),
            (
                Platform.TIME,
                OWNED_SUFFIX_DEPARTURE_HOLIDAY,
                time_of_day,
                self.set_departure_holiday_override,
            ),
            (
                Platform.TIME,
                OWNED_SUFFIX_DEPARTURE_HOME_DAY,
                time_of_day,
                self.set_departure_home_day_override,
            ),
        )
        for platform, suffix, value_type, setter in simple_reads:
            value = await self._store.read(platform, suffix, value_type)
            if value is not None:
                setter(value)

        # NF14: HomeDaySwitch (switch.py) exposes the date(s) it applies to as its own
        # ATTR_APPLIES_TO attribute rather than as a plain on/off value -- read_home_day_dates
        # is the one Store read that isn't in `simple_reads` above because of that (its own
        # docstring explains why). Same "None means unresolvable, keep current" convention as
        # every `simple_reads` row: an unregistered/unavailable switch leaves `home_day_dates`
        # untouched; a registered, available switch with nothing set resolves to an empty set,
        # which set_home_day_dates DOES apply -- that is what "an unset flag stays unset
        # (default off)" looks like.
        home_day_dates = await self._store.read_home_day_dates(OWNED_SUFFIX_HOME_DAY)
        if home_day_dates is not None:
            self.set_home_day_dates(home_day_dates)

        for weekday, suffix in enumerate(OWNED_SUFFIX_DEPARTURE_DOW):  # Monday=0 .. Sunday=6
            value = await self._store.read(Platform.TIME, suffix, time_of_day)
            if value is not None:
                self.departure_dow_defaults[weekday] = value

    def set_home_day_dates(self, dates: set[date]) -> None:
        """Coordinator's own boundary for `home_day_dates` (ADR-0014's "any future field added
        to the coordinator's externally-writable surface follows this same rule" clause) -- no
        range to clamp, unlike `set_target_current`/`set_soc_limit_override`. Since ADR-0018,
        `switch.py` never calls this directly: the coordinator reads the stored value through
        the Store each cycle (`_read_owned_entities`, via `read_home_day_dates`, #652) and
        calls this itself."""
        self.home_day_dates = dates

    def set_departure_holiday_override(self, value: time_of_day) -> None:
        """Coordinator's own boundary for `departure_holiday_override` (ADR-0014) -- see
        `set_home_day_dates`."""
        self.departure_holiday_override = value

    def set_departure_home_day_override(self, value: time_of_day) -> None:
        """Coordinator's own boundary for `departure_home_day_override` (ADR-0014) -- see
        `set_home_day_dates`."""
        self.departure_home_day_override = value

    def _start_cooldown(self, mode: str, now: float) -> None:
        """Start the coordinator-scoped R11 cooldown for `mode`, fixing its duration at
        `handler.cooldown_minutes` (not re-read later, R11: "not shortened by a change in
        conditions"), and, for a SOC-gated mode, force its own per-mode state to
        `Phase.COOLDOWN` too -- the shared shape of a coordinator-forced stop, used wherever a
        mode's own `step()` does not itself produce the transition this cycle: `_apply_peak_clamp`'s
        Captar force-stop and `_start_fault_stop_cooldown` below both call this rather than
        each repeating the pair. `_dispatch_mode`'s own generic fresh-`Phase.COOLDOWN`-transition
        detection does not use this -- there the per-mode state already came from the handler's
        own `step()`, only `_active_cooldown` itself needs starting."""
        handler = self._mode_handlers[mode]
        self._active_cooldown = ActiveCooldown(now, handler.cooldown_minutes * 60)
        if handler.is_soc_gated:
            state_cls = type(self._mode_state[mode])
            self._mode_state[mode] = state_cls(Phase.COOLDOWN, now)

    def _start_fault_stop_cooldown(self) -> None:
        """C5/R11 (issue #1311): a fault that cuts a charging current is a fault stop, and
        starts the active mode's own cooldown -- exactly as that mode's own stop condition
        would, `Power` included, whatever its `power_respect_peak` option and the CapTar
        capability (R11 AC3 as amended). A fault while the current in force is already 0 A
        starts none, which is why the gate below is on `_last_commanded_a` -- the value the
        coordinator itself last actually wrote (`_write`'s own field), never `None`-coalesced
        to 0 -- rather than on `active_mode` or on the mode's own per-mode phase. `Off`
        usually reaches the same early return as any other mode already at 0 A, since its own
        dispatch always commands 0 A -- but not always: `None` (no write has ever happened yet
        this coordinator instance, e.g. immediately after a restart) is deliberately NOT
        treated as "already 0 A", so a fault on the very first cycle after a restart while
        `Off` is active (or the cycle that switches into `Off`) DOES reach `_start_cooldown`
        and read `Off`'s own `cooldown_minutes` (0.0) -- harmlessly, since an
        already-elapsed, zero-length `ActiveCooldown` blocks nothing. The `None` case itself:
        a restart's own timers reset regardless (NF14), so a cooldown started here for a
        charger that may still be delivering current from before the restart is the
        conservative direction, not a C5 violation (C5 excuses only a current genuinely
        already at 0 A).

        Called from all three of `_async_update_data`/`_run_cycle`'s fault paths (ADR-0007's
        single fault-handling code path), before the forced 0 A write -- so `_last_commanded_a`
        still holds the pre-fault value -- and using `self.hass.loop.time()` directly, since
        none of the three call sites has a `CycleContext`/monotonic `now` of its own by the
        point it detects the fault."""
        if self._last_commanded_a == 0.0:
            return
        self._start_cooldown(self.active_mode, self.hass.loop.time())

    def _cooldown_blocks(self, proposed_phase: Phase, now: float) -> bool:
        """R11/issue #974: True when a still-running coordinator-scoped cooldown must block a
        transition into `proposed_phase`. Only Charging is ever gated -- Cooldown/Hold/Idle/
        Debouncing transitions are a mode's own timers settling, never the restart R11's
        cooldown exists to delay. Shared by `_dispatch_mode` (the real dispatch, which also
        freezes state on a block) and `_mode_desired_current` (the Auto baseline dry run,
        read-only) so the two can never drift out of lockstep -- the dry run must report the
        same 0 A a blocked real dispatch would actually deliver, or R5's required-current
        comparison would judge the baseline mode more capable than it truly is."""
        return (
            self._active_cooldown is not None
            and proposed_phase == Phase.CHARGING
            and not self._active_cooldown.elapsed(now)
        )

    def _resolve_active_soc_limit(self, ctx: CycleContext) -> float:
        """This cycle's active SOC limit (ADR-0011/ADR-0012's `SocGateResolver`): resolves it,
        fires `ActiveSocLimitChanged` on a change, writes it onto `ctx`, and -- #1335 -- feeds
        the resolution straight into `_refresh_power_soc_limit_reached`. That refresh has to
        happen here, at the one place this cycle's limit is already in hand, rather than
        waiting for `_dispatch_mode`'s Power branch to run: see that method's own docstring
        for why it must run every cycle, whatever the active mode. Reads `ctx.ev_soc` rather
        than taking it as a second parameter -- both are already on `ctx` by the time this
        runs, and threading it again would reintroduce the two-sources-of-truth problem
        `_dispatch_mode`'s own docstring warns against for the identical pair. Named and
        called as one step from `_run_cycle` (ADR-0046) rather than left inline, the same
        reason `_resolve_deadline_and_reserve` beside it already is one."""
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
        # #1335: whether Power is *currently in* Charging -- the active mode is Power, no
        # coordinator-scoped cooldown blocks it, and `self._power_charging` (updated only by
        # `_dispatch_mode`'s own Power branch) says it was actually delivering current as of
        # its own last dispatch, not merely idling at or above the limit with nothing behind
        # it. Resolved here, before `_dispatch_mode` itself runs, the same one-cycle-lag
        # caveat R8's step-up gate already carries under Auto (this cycle's `self.active_mode`
        # is Auto's own PRIOR resolution until later in `_run_cycle` -- see the comment above
        # `auto_dispatchable`'s own assignment).
        power_in_charging = (
            self.active_mode == MODE_POWER
            and not self._cooldown_blocks(Phase.CHARGING, ctx.now)
            and self._power_charging
        )
        self._refresh_power_soc_limit_reached(
            ctx.ev_soc,
            active_soc_limit,
            limit_changed=soc_limit_changed,
            power_in_charging=power_in_charging,
        )
        return active_soc_limit

    def _refresh_power_soc_limit_reached(
        self,
        ev_soc: float | None,
        active_soc_limit: float,
        *,
        limit_changed: bool,
        power_in_charging: bool,
    ) -> None:
        """R17 AC4/R7 (#1335), UC04's *State of charge unavailable* exception flow: refreshes
        `self._power_soc_limit_reached` -- Power's own stop at the active SOC limit, kept
        separate from `_PowerModeHandler.is_soc_gated` (ADR-0042 keeps that flag `False` so
        Power never *needs* a reading, and a missing one stays a non-fault in Power while
        charging, C5).

        Called once per cycle from `_resolve_active_soc_limit`, unconditionally, whatever the
        active mode, not only while `Power` is dispatching: the active SOC limit and `ev_soc`
        are cycle-wide facts, not scoped to whichever mode consumes them this cycle, so a
        limit change while a *different* mode is active still has to be reflected for the
        next time `Power` dispatches (a mode switch is deliberately NOT itself a reset trigger
        -- `_reset_mode_state_if_changed`'s own docstring says why).

        UC04's own State model draws the distinction this method has to honour: "Only a stop
        made at the limit is held this way: a car resting in Idle or Cooldown at or above the
        limit has no such stop behind it". So a present reading at or above the limit only
        *sets* the stop when `power_in_charging` -- Power was actually delivering current
        (Charging, not merely dispatchable) as of its own last cycle, the Charging ->
        SocReached transition UC04's table draws. Resting in Idle or Cooldown at or above the
        limit, or any other mode being active, reaching the same reading is not a stop being
        made, so it leaves an already-`False` latch alone (never invents one) and,
        symmetrically, never clears an already-`True` one either -- that would silently drop a
        stop the *next* Power cycle never asked to leave. A present reading *below* the limit
        always clears, regardless of which mode is active: UC04/R7 AC5's resume condition 1
        (the limit effectively no longer met) is mode-agnostic, unlike the setting side. With
        no reading at all, UC04 line 64/R7 AC5 name what can still end an already-made stop:
        "the active SOC limit changes ... not a reading" -- so `limit_changed` (the edge over
        this cycle's resolved active limit, ADR-0012's `SocGateResolver` -- not only a literal
        `soc_limit_override` write; the solar-reserve cap and step-up gate can move it too)
        clears the stop on its own. It can only ever CLEAR, never SET one there either: UC04
        line 63 is explicit that a missing reading gives the System nothing to judge the limit
        by, so it "cannot itself stop there on that cycle" -- a limit change witnessed without
        a reading is evidence of a *change*, not evidence of where `ev_soc` now stands
        against it, let alone evidence that Power was the one charging when it happened."""
        if ev_soc is not None:
            if ev_soc >= active_soc_limit:
                if power_in_charging:
                    self._power_soc_limit_reached = True
            else:
                self._power_soc_limit_reached = False
        elif limit_changed:
            self._power_soc_limit_reached = False

    def _dispatch_power(self, ctx: CycleContext) -> float:
        """`_dispatch_mode`'s own `MODE_POWER` branch, named out (ADR-0046) once #1335 gave it
        a third stop condition. ADR-0012: routed through the registry too, for observability/
        consistency with the other modes, but MODE_POWER has no entry in `_fresh_mode_state()`
        and must not gain one -- i.e. `_PowerModeHandler.is_soc_gated` must stay False. Its
        returned state is discarded, never written to `_mode_state`.

        Three stop conditions, in order, each setting `self._power_charging = False` on the
        way out (see that field's own docstring, `_init_mode_switch_survivors`) -- only the
        final, no-stop path sets it `True`:

        1. **A running coordinator-scoped cooldown** (R11/issue #974): Power has no `Phase` of
           its own -- being active and commanding `target_current` is its only "charging"
           state, so a running cooldown must block it the same way it blocks any other mode's
           Idle -> Charging transition (`_cooldown_blocks` with `Phase.CHARGING` standing in
           for that one state). Without this, switching into Power (e.g. Auto's own carve-out
           escalating to Power when CapTar is unavailable, R5/R18) would be exactly the mode-
           switch escape R11 forbids.
        2. **A genuine prior stop** (Charging -> SocReached, UC04's table): `self.
           _power_soc_limit_reached`, already refreshed for this cycle before `_dispatch_mode`
           ever runs (`_refresh_power_soc_limit_reached`, called from `_resolve_active_soc_limit`
           as soon as this cycle's `active_soc_limit` resolves) -- a plain read here, not a
           second write. Holds through a missing reading, same as every other SOC-gated
           mode's own `resume_state()` hold.
        3. **UC04's own Idle row**: "(SOC < active SOC limit or SOC unavailable) & no cooldown
           -> Charging" -- a present reading at or above the limit blocks the transition into
           Charging in the first place, exactly like every other SOC-gated mode's own guard
           (`ctx.ev_soc >= ctx.active_soc_limit`, `_dispatch_mode` below), fresh every cycle
           off `ctx` and setting no latch: "a car resting in Idle ... at or above the limit
           has no such stop behind it" (UC04), so it must NOT persist through a later missing
           reading -- unlike a genuine SocReached stop, Idle's own 0 A ends the instant the
           reading that was blocking it goes missing (UC04's Idle row again: unavailable
           satisfies the same condition as below-limit)."""
        if self._cooldown_blocks(Phase.CHARGING, ctx.now):
            self._power_charging = False
            return 0.0
        if self._power_soc_limit_reached:
            self._power_charging = False
            return 0.0
        if ctx.ev_soc is not None and ctx.ev_soc >= ctx.active_soc_limit:
            self._power_charging = False
            return 0.0
        desired, _ = self._mode_handlers[MODE_POWER].desired_current(ctx, None)
        # #1335: the only place `_power_charging` is ever set True -- a real Charging outcome
        # this cycle, which `_resolve_active_soc_limit` reads next cycle to tell a genuine
        # stop apart from a reading merely arriving at or above the limit while Power never
        # charged.
        self._power_charging = desired > 0.0
        return desired

    def _dispatch_mode(self, ctx: CycleContext) -> float:
        """The disconnect/Off/Power/SOC-gated-stop guards around the ModeHandler registry lookup
        (ADR-0012's lookup itself is untouched -- this method only names the surrounding branches
        that decide *whether* to look one up at all). Reads ev_soc/active_soc_limit off ctx rather
        than as separate parameters -- both are already there (set earlier this cycle, before this
        call), and threading them again as loose kwargs would reintroduce the two-sources-of-truth
        problem CycleContext exists to eliminate. Mutates self._mode_state exactly as today,
        plus self._active_cooldown/self._power_soc_limit_reached/self._power_charging on a
        disconnect (their own field docstrings, in `_init_mode_switch_survivors`) and,
        further, self._power_charging on every Power cycle (`_dispatch_power`'s own
        docstring); returns the desired current before any clamp (ADR-0023)."""
        if ctx.status not in CHARGEABLE_STATES:
            # R7/R11: disconnect resets every mode's state, clearing hold/cooldown -- and, for
            # a solar mode or Captar, also ends any SOC gate (resume condition 2: unplug/replug).
            self._mode_state = self._fresh_mode_state()
            # R11/issue #757: disconnect also clears the has-charged flag (system-overview.md's
            # `has-charged flag` glossary entry) -- the next connection is a fresh session's
            # first start. Deliberately NOT touched by `_reset_mode_state_if_changed` (the
            # mode-switch reset) -- see this coordinator's own `_has_charged` field docstring.
            self._has_charged = False
            # R11/issue #974: a disconnect (resume condition 2, unplug/replug) also clears any
            # running rapid-cycling cooldown -- unlike a mode switch, which must NOT clear it
            # (see `_active_cooldown`'s own field docstring). The next connection starts with
            # no cooldown pending, same as `_mode_state`/`_has_charged` above.
            self._active_cooldown = None
            # #1335/A5a resume condition 2: unplug/replug also clears Power's own SOC-limit
            # stop -- the same disconnect trigger as `_active_cooldown` right above -- and
            # whether it was in Charging, so a fresh connection starts from Idle, not from
            # whatever Power was doing before the disconnect.
            self._power_soc_limit_reached = False
            self._power_charging = False
            return 0.0
        if self.active_mode == MODE_OFF:
            return 0.0
        if self.active_mode == MODE_POWER:
            return self._dispatch_power(ctx)
        handler = self._mode_handlers[self.active_mode]
        if handler.is_soc_gated and ctx.ev_soc >= ctx.active_soc_limit:
            # R7: don't resume until the gate clears. Holding the state at resume_state()
            # (rather than dispatching into step()) means the next cycle where this branch
            # stops matching -- because soc_limit_override rose (resume condition 1) --
            # dispatches fresh from that state, re-checking the start threshold normally. No
            # latch, no SocReached phase of its own (UC01/UC02's state model draws one, but
            # M1 keeps every mode module opinion-free about SOC, per solar.py's own module
            # docstring). For Solar/SolarOnly, resume_state() is an already-elapsed Cooldown
            # (ModeState.resumed()) rather than a genuine idle_state() -- that's what makes a
            # SocReached resume exempt from R11's restart debounce when the start threshold is
            # already met (immediate, never having passed through Idle), and correctly
            # debounce-eligible the next time around when it isn't (UC01/UC02's own
            # `SocReached -> Idle` transition). This is distinct from #752 (still open), which
            # is about the STOP side -- whether reaching the limit should itself go through a
            # hold before cutting to 0 A -- not this RESUME side, which #757 already decided.
            self._mode_state[self.active_mode] = handler.resume_state()
            return 0.0
        # ADR-0012: one ModeHandler registry lookup replaces the old per-mode if/elif chain
        # (MODE_SOLAR/MODE_SOLAR_ONLY/MODE_CAPTAR -- the only modes that can still reach this
        # branch, since MODE_OFF/MODE_POWER/the SOC-gated-stop guard above all handle their own
        # case first). Each handler wraps its modes/*.py step()/desired_current() unchanged;
        # only the lookup mechanism changed.
        prior_state = self._mode_state.get(self.active_mode)
        desired, new_state = handler.desired_current(ctx, prior_state)
        # R11/issue #974: a running coordinator-scoped cooldown blocks ANY mode's Idle/
        # Debouncing/Cooldown -> Charging transition, regardless of which mode's own per-mode
        # state (possibly just rebuilt by `_reset_mode_state_if_changed`) is proposing it --
        # see `self._cooldown_blocks` and `_active_cooldown`'s own field docstring. Overriding
        # back to `prior_state` (rather than the handler's own `new_state`) freezes that mode's
        # own timer exactly where it was -- e.g. a Debouncing phase already past its own
        # debounce period simply re-proposes the same Charging transition next cycle, which
        # this check keeps blocking until `_active_cooldown` itself elapses.
        if self._cooldown_blocks(new_state.phase, ctx.now):
            desired, new_state = 0.0, prior_state
        elif new_state.phase == Phase.COOLDOWN and (
            prior_state is None or prior_state.phase != Phase.COOLDOWN
        ):
            # A fresh stop-on-a-mode's-own-condition (R1/R2's hold elapsing without recovery,
            # for Solar/SolarOnly) -- start the coordinator-scoped cooldown, fixing its
            # duration at this instant per `handler.cooldown_minutes` (R11: "not shortened by
            # a change in conditions"). Captar's only own stop condition (a sustained R3
            # breach) never reaches this branch -- it is forced by `_apply_peak_clamp` below,
            # which starts its own `_active_cooldown` directly at that call site instead. (A
            # sustained R3 breach while Solar/SolarOnly holds at the minimum current, R1/R2's
            # own grace-period stop, is a separate, pre-existing gap this issue does not
            # cover: `_apply_peak_clamp`'s force-stop is gated on Captar alone.)
            self._active_cooldown = ActiveCooldown(ctx.now, handler.cooldown_minutes * 60)
        self._mode_state[self.active_mode] = new_state
        # R11/issue #757: flips the has-charged flag the first time a solar mode's own step()
        # actually transitions into Phase.CHARGING while it was still False -- step() itself
        # stays pure/stateless about this flag (it only reads ctx.has_charged), so the
        # coordinator is the one place that decides when the connection's first-ever start
        # happened. `handler.is_solar_mode` excludes Captar, which has no has-charged/debounce
        # concept (R11) even though its state also carries a `.phase` attribute.
        #
        # Deliberately latches on the raw phase transition here, before `_apply_peak_clamp`/
        # `_apply_grid_ceiling_clamp` run in `_run_cycle` -- so a same-cycle force-stop to 0 A
        # by either clamp can still leave the flag set even though nothing was actually
        # delivered. Moving the flip to after both clamps would mean threading `new_state`
        # (or a second phase check) through `_run_cycle` and both clamp methods, which live
        # in separate methods from this one -- left as-is rather than risk a subtler behavior
        # change this late; revisit only if a real deadlock/regression traces back to it.
        if handler.is_solar_mode and not self._has_charged and new_state.phase == Phase.CHARGING:
            self._has_charged = True
        return desired

    def _apply_peak_clamp(self, ctx: CycleContext, desired: float) -> float:
        """R3 peak clamp (E5) -- never engages at all with the CapTar capability absent (R3
        AC1, R18), and, while the capability is present, skippable only for Power via its own
        R17 opt-out; both are `_peak_clamp_would_run`'s job. `desired` here
        is the already-computed mode request from `_dispatch_mode` --
        apply_peak_clamp's breach timer only starts/continues when `desired >= min_a`, so the
        disconnect/Off/SOC-gated/Power-at-its-own-SOC-limit branches (all `desired = 0.0`) can
        never trip force_stop this cycle, regardless of headroom. A separate named call from
        the C4 grid-ceiling clamp below, per ADR-0006's requirement that the two never merge
        into one routine -- merging them would let the R17 opt-out silently reach C4 too.
        Mutates self._peak_tracker and, on a force-stop while Captar is active,
        self._mode_state[MODE_CAPTAR] -- both exactly as
        before this extraction (ADR-0023). Reads baseline_w/voltage/effective_peak_limit_kw/now
        off `ctx` (issue #719, and #990 for baseline_w specifically -- already debounced by the
        time `_run_cycle` builds ctx) rather than as separately-passed kwargs -- `_run_cycle`
        already has exactly one of each by the time this is called, so there is no second copy
        for the two to drift out of lockstep."""
        if not self._peak_clamp_would_run():
            return desired
        desired, self._peak_tracker, force_stop = apply_peak_clamp(
            desired,
            baseline_w=ctx.baseline_w,
            voltage=ctx.voltage,
            effective_peak_limit_kw=ctx.effective_peak_limit_kw,
            safety_margin_w=self._config.safety_margin_w,
            min_a=self._config.min_current,
            grace_period_s=self._config.peak_grace_min * 60,
            tracker=self._peak_tracker,
            now=ctx.now,
        )
        if force_stop and self.active_mode == MODE_CAPTAR:
            desired = 0.0
            # R11/issue #974: Captar's only own stop condition (a sustained R3 breach) is
            # forced here rather than decided by captar.step() itself (that module's own
            # docstring) -- so this is the one cooldown-start site `_dispatch_mode`'s generic
            # "fresh Phase.COOLDOWN transition" detection can never see. `_start_cooldown`
            # (issue #1311) fixes the duration at this instant (R11: "not shortened by a
            # change in conditions") via Captar's own `cooldown_minutes`, and forces Captar's
            # own per-mode state to `Phase.COOLDOWN` in the same call.
            self._start_cooldown(MODE_CAPTAR, ctx.now)
        return desired

    def _apply_grid_ceiling_clamp(self, ctx: CycleContext, desired: float) -> float:
        """C4 grid-supply-ceiling clamp (E6) -- never skippable, no opt-out of any kind. A
        separate named call from the R3 clamp above, per ADR-0006 -- merging the two, or adding
        a shared parameter, would risk the R17 opt-out silently reaching C4 too. Extracted from
        `_run_cycle` per ADR-0023. Reads net_w/charger_w/voltage off `ctx` (issue #719), same
        rationale as `_apply_peak_clamp` above."""
        return clamp_to_ceiling(
            desired,
            net_w=ctx.net_w,
            charger_w=ctx.charger_w,
            voltage=ctx.voltage,
            ceiling_a=self._config.grid_ceiling_a,
            offset_a=self._config.grid_safety_offset_a,
        )

    def _peak_clamp_would_run(self) -> bool:
        """R3 AC1/R17: whether R3's peak clamp applies to the mode currently active.

        Gated on `captar_available` first (R3 AC1, R18): with the CapTar capability absent, no
        peak-protection clamp ever engages in any mode -- net import is bounded only by the grid
        supply ceiling (C4). `Power` alone may additionally disable peak protection while the
        capability IS present (R17, C3's second carve-out); every other mode is bound by it in
        that case. Shared by `_apply_peak_clamp`, which is the behaviour, and
        `_escalated_maximum_permitted_rate_a`, which predicts it -- a predictor that disagreed
        with the thing it predicts is worse than no predictor.

        One caveat the sharing does not remove: `_apply_peak_clamp` runs after mode dispatch and
        so reads the mode being dispatched, while the escalated-rate helper runs before it and
        reads the mode from the *previous* cycle. The two only disagree for `Power` with the
        opt-out off, which `Auto` never selects from its baseline rows -- reachable only on a
        CapTar-absent installation (R18), where `Auto`'s urgency row escalates to `Power`; but
        with the capability absent the `captar_available` gate above already returns `False`
        before the mode is even consulted, so the two agree in that case regardless. The
        remaining disagreement window is one cycle after a profile switch away from a `Power`
        session while the capability IS present. Passing the mode in as a parameter would close
        it properly; that is deliberately not done here, because the mode urgency *would*
        dispatch is resolved by the very call this rate is an input to.
        """
        if not self._config.captar_available:
            return False
        return not (self.active_mode == MODE_POWER and not self._config.power_respect_peak)

    def _escalated_maximum_permitted_rate_a(
        self, ctx: CycleContext, *, peak_operand_kw: float
    ) -> float:
        """R5's `escalated maximum permitted rate` (system-overview.md glossary): the maximum
        permitted rate that WOULD be in force if deadline urgency were engaged -- the same C1/C4
        bounds fitted to the peak headroom under an effective peak limit raised to the maximum
        peak.

        Resolved on every cycle whether or not urgency is actually in effect, which is the whole
        point of it: a test written against the rate CURRENTLY in force would move the moment
        urgency raised it, so engaging urgency would immediately make the deadline look
        comfortable again and revert it (resolution-rules.md, the required-current rule).

        Deliberately NOT routed through `_apply_peak_clamp`: that call mutates `self._peak_tracker`
        (R3's breach timer) and, on a force-stop, `self._mode_state`. This is a hypothetical --
        "what could urgency deliver" -- and a hypothetical must not advance a breach timer. It
        shares the clamp's own `peak_headroom_a` arithmetic instead, applied to the raised limit
        rather than the resolved one, so there is one formula and not a copy to keep in step.

        C4 is applied through `ceiling_headroom_a` rather than `clamp_to_ceiling` for the same
        reason in a different key: `clamp_to_ceiling` is one of ADR-0006's ten ordered steps, and a
        test observes the actual call order of those step functions. Calling it here -- before the
        peak clamp, for a value that never reaches the charger -- would register as a sixth,
        out-of-order control-path clamp. The headroom helper shares C4's arithmetic without being
        that step.

        `peak_operand_kw` is threaded in for symmetry with the resolved limit and is provably
        inert at this call: the effective-peak-limit rule's *Urgency raise* row returns the
        maximum peak unconditionally, so no operand value can change what `urgent=True` resolves
        to. It is passed rather than dropped so that a future row-1 that *does* consult the
        operand needs no new plumbing here.

        The glossary names two cases in which the peak clamp does not run at all and only C1/C4
        bound the rate: `Power` with its own R17 peak-protection opt-out disabled, and the CapTar
        capability being absent (R3 AC1, R18). `_peak_clamp_would_run` handles both, mirroring
        `_apply_peak_clamp`'s own early return -- without the first, a `Power` session with the
        opt-out off and a household baseline near the maximum peak would floor this rate to 0 A
        and make every required current both urgent and unreachable, which is #1078's own
        symptom in miniature; without the second, a non-CapTar installation's escalated rate
        would be floored by a clamp that (per R3 AC1) never engages for it at all.
        """
        bounds = [
            self._config.max_current,
            ceiling_headroom_a(
                net_w=ctx.net_w,
                charger_w=ctx.charger_w,
                voltage=ctx.voltage,
                ceiling_a=self._config.grid_ceiling_a,
                offset_a=self._config.grid_safety_offset_a,
            ),
        ]
        if self._peak_clamp_would_run():
            escalated_peak_limit_kw = resolve_effective_peak_limit(
                peak_operand_kw,
                self._config.max_peak_kw,
                self._config.peak_floor_kw,
                urgent=True,
            )
            bounds.append(
                peak_headroom_a(
                    baseline_w=ctx.baseline_w,
                    voltage=ctx.voltage,
                    effective_peak_limit_kw=escalated_peak_limit_kw,
                    safety_margin_w=self._config.safety_margin_w,
                )
            )
        rate_a = min(bounds)
        # Floored at 0: a household baseline at or beyond the raised limit leaves nothing for
        # urgency to deliver, and a negative rate would make `required_a > rate` fire
        # `unreachable` with a nonsense threshold rather than an honest "no headroom" one.
        #
        # One knowing divergence from `apply_peak_clamp` remains here: while headroom sits between
        # 0 and the minimum charging current, the real clamp holds at `min_a` for the whole R3
        # grace period, where this reports the sub-`min_a` headroom. The direction is safe for
        # urgency (it engages sooner, never later), but it can report `unreachable` -- and fire
        # the user-facing notice -- on a cycle the charger is in fact still delivering `min_a`.
        return max(rate_a, 0.0)

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
        """R11: switching mode resets the hold and restart-debounce timers -- fresh state for
        every mode with one, whether or not the incoming mode is one of them (a state nobody
        is dispatching to is inert either way). Idempotent -- a no-op once `_last_active_mode`
        catches up, so calling this twice in the same cycle (Manual's change is already final
        at the top of the cycle; Auto's own mode isn't resolved until later) never
        double-resets.

        Deliberately leaves `self._has_charged` untouched (issue #757) -- unlike every timer
        in `_mode_state`, the has-charged flag is scoped to the connection, not the active
        mode (R11), so a Solar<->SolarOnly switch must not reset it. See `_has_charged`'s own
        field docstring for where it IS reset (disconnect, `_dispatch_mode`).

        Also deliberately leaves `self._active_cooldown` untouched (issue #974) -- rebuilding
        `_mode_state` here DOES clear whichever per-mode `Phase.COOLDOWN` entry was tracking a
        running cooldown internally, but the coordinator-scoped `_active_cooldown` survives
        this rebuild by construction (it isn't part of `_mode_state`) and keeps blocking a
        restart in the newly-active mode for the remainder of its fixed duration -- the whole
        point of hoisting it out here, per R11's acceptance criterion that a cooldown "is not
        shortened by a change in conditions -- including a switch of the active mode". See
        `_active_cooldown`'s own field docstring.

        Also deliberately leaves `self._power_soc_limit_reached` untouched (#1335): UC04's
        *State of charge unavailable* exception flow and R7 AC5 both name the stop's only
        clearing conditions explicitly -- the active SOC limit changing, or the car being
        unplugged and replugged (`_dispatch_mode`'s own disconnect branch handles that one) --
        and neither names a mode switch. Unlike the other SOC-gated modes' own stop/resume,
        which is a stateless comparison recomputed fresh every cycle from `ctx.ev_soc` and
        never actually depends on what `_mode_state` holds (`_fresh_mode_state()` resetting it
        here only resets each such mode's *unrelated* hold/debounce timers), Power's latch
        *is* the only memory of a stop made while a reading was present, kept for exactly the
        cycles that follow with no reading at all -- clearing it here would let a mode switched
        away and back, with the reading still missing when it returns, silently resume
        charging past a limit nothing has actually changed to clear.

        DOES reset `self._power_charging` to `False` (#1335) -- unlike `_power_soc_limit_reached`
        right above, this field is not a record of a completed transition, it is a live claim
        that Power *is currently* the one delivering current. That claim is simply false the
        instant a different mode is dispatched instead (Power delivers nothing while it is not
        the active mode), so leaving it `True` across a switch away would let a later switch
        back read a stale "was genuinely charging" fact that this cycle's dispatch never
        earned -- exactly the false-latch shape `_power_soc_limit_reached`'s own SET gate
        (`_resolve_active_soc_limit`'s `power_in_charging`) exists to rule out. `_dispatch_power`
        itself, the only other writer, sets it fresh on every Power cycle regardless, so this
        reset only matters for the cycles Power is *not* dispatched -- exactly where it would
        otherwise go stale."""
        if self.active_mode != self._last_active_mode:
            self._mode_state = self._fresh_mode_state()
            self._power_charging = False
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
        a plain writable attribute. Since ADR-0018, `select.py`
        never calls this directly: the coordinator reads the stored option through the Store
        each cycle (`_read_owned_entities`) and calls this itself; the only other caller is
        tests.

        Unlike `SelectEntity`'s own `options` list (which rejects an out-of-enum value before
        ever reaching this method), a value read back from the Store has no such gate -- issue
        #718 made `_read_owned_entities` look `self.active_profile` up in `PROFILE_POLICIES`
        every cycle, so a stale/corrupted restored profile would otherwise KeyError there
        instead of degrading gracefully the way an unmapped `active_mode` already does in
        `set_active_mode` above. Guards the same way: falls back to `PROFILE_MANUAL` (the
        constructor's own starting value) and logs a warning once per rejected raw value
        (`_last_rejected_profile`, mirroring `_last_rejected_mode`'s once-per-outage
        discipline, ADR-0007) rather than raising `CycleResult.fault` -- a corrupted *setting*
        is a different class of defect than a hardware adapter returning `None`."""
        if profile not in PROFILE_POLICIES:
            if profile != self._last_rejected_profile:
                _LOGGER.warning(
                    "smart_charging: select.smart_charging_profile has an unrecognized value "
                    "%r; falling back to %s until a valid option (%s) is selected again",
                    profile,
                    PROFILE_MANUAL,
                    ", ".join(sorted(PROFILE_POLICIES)),
                )
                self._last_rejected_profile = profile
            profile = PROFILE_MANUAL
        else:
            self._last_rejected_profile = None
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

        `net_w`/`charger_w`/`baseline_w` are deliberately 0.0/0.0/0.0 here, not threaded from
        the caller: none of the five `ModeHandler.desired_current` implementations reads
        `ctx.net_w`/`ctx.charger_w`/`ctx.baseline_w` (only `ctx.surplus_w`/`ctx.voltage`/
        `ctx.now`/`ctx.status`), and this dry-run ctx is never passed to
        `_apply_peak_clamp`/`_apply_grid_ceiling_clamp` (the two real consumers, issue #719) --
        only the real `_run_cycle`-constructed ctx is. `baseline_w=0.0` here is otherwise the
        exact placeholder issue #990's own `CycleContext.baseline_w` field docstring warns
        against -- safe ONLY because of the "never reaches `_apply_peak_clamp`" guarantee above;
        if a future ModeHandler needs any of the three, thread the real values from `_run_cycle`
        at that point, not before."""
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
            baseline_w=0.0,
            ev_soc=ev_soc,
            surplus_w=surplus_w,
            active_soc_limit=active_soc_limit,
            # Deliberately NOT threaded from `self._has_charged` (unlike the real
            # `_run_cycle`-constructed ctx) -- left at CycleContext's own default (False).
            # See `test_baseline_dry_run_ignores_has_charged_after_escalation_deadlock` for
            # the full deadlock scenario this avoids.
            has_charged=False,
        )
        current, new_state = self._mode_handlers[mode].desired_current(
            ctx, self._mode_state.get(mode)
        )
        # R11/issue #974: mirrors `_dispatch_mode`'s own cooldown block (`_cooldown_blocks`) --
        # a mode still blocked by a running coordinator-scoped cooldown cannot actually deliver
        # `current` this cycle, so the baseline dry run must not report otherwise, or R5's
        # required-current comparison would judge a cooldown-blocked mode more capable than a
        # real dispatch could ever deliver. Read-only: unlike `_dispatch_mode`, there is no
        # `_mode_state`/`_active_cooldown` write here, this dry run mutates no persisted state
        # either way. `new_state` is `None` for Off/Power (neither carries a `.phase`, neither
        # is ever stored in `_mode_state`) -- Off needs no check (it always returns 0.0 anyway),
        # but Power does: like `_dispatch_mode`'s own Power branch, `Phase.CHARGING` stands in
        # for the one "charging" state Power has, since being active and commanding
        # `target_current` is Power's only state. Reachable under `Manual` + `Power` with a
        # cooldown still running from an earlier mode's forced stop (`coordinator_cycle.py`'s
        # `baseline_mode = inputs.active_mode` path) -- not just a defensive check.
        if new_state is not None:
            if self._cooldown_blocks(new_state.phase, now):
                return 0.0
        elif mode == MODE_POWER:
            # Mirrors `_dispatch_mode`'s own Power branch's three stop conditions (#1335): the
            # cooldown check, the genuine SocReached stop, and the fresh Idle-blocks-Charging
            # check. `self._power_soc_limit_reached` is already refreshed for this cycle by
            # the time `_run_cycle` reaches here (it runs `_refresh_power_soc_limit_reached`
            # as soon as `active_soc_limit` resolves, before `resolve_deadline_urgency`/this
            # method) -- a plain read, mutating nothing, matching this method's own no-
            # mutation docstring. The Idle check below reads the same `ev_soc`/
            # `active_soc_limit` this method was already called with -- `ev_soc` is never
            # `None` here (see this method's own docstring), so it needs no presence check.
            if self._cooldown_blocks(Phase.CHARGING, now):
                return 0.0
            if self._power_soc_limit_reached:
                return 0.0
            if ev_soc >= active_soc_limit:
                return 0.0
        return current

    def _clear_baseline_deferral(self) -> None:
        """ADR-0039/R3 case (a): `deferred_previous` means "the previous CONTROL CYCLE deferred
        on the command-changed ground", not "the previous call to `debounce_baseline_w` did".
        A cycle that returns before that call is reached -- the required-adapter fault in
        `_run_cycle`, or any exception funnelled to `_async_update_data` -- deferred nothing, yet
        still writes 0 A, which is a real step. Leaving the flag set would block case (a) on the
        RECOVERY cycle, which is precisely the cycle whose `charger_w` is stale from that forced
        drop to 0 A: the reading then looks far below the accepted baseline, case (a) cannot
        reject it, and the debounce window commits a contaminated, headroom-inflating value.
        Cleared here rather than in the engine, since only the coordinator knows a cycle ended
        without consulting it."""
        self._baseline_debouncer = replace(self._baseline_debouncer, deferred_previous=False)

    async def _write(self, value: float) -> None:
        """The single write site (ADR-0039's `_command_stepped`/`_last_commanded_a` are
        maintained here for exactly that reason). The step flag is recorded only after the
        adapter write actually returns: a write that raises never reached the charger, so the
        current did not change and the next cycle's `charger_w` is not stale on its account.

        Also `_write_zero_failing`'s (issue #1311) one clearing site: ANY write that reaches
        here succeeding -- not only a `_safe_write_zero` retry -- proves the charger-current
        adapter is working again, so a write outage that ends through an ordinary clean cycle
        (rather than through another faulted `_safe_write_zero` call) still logs its recovery
        and un-suppresses a later, genuinely new outage's own WARNING."""
        self._command_stepped = False
        await self._adapters[ROLE_CHARGER_CURRENT].write(value)
        self._command_stepped = (
            self._last_commanded_a is not None and value != self._last_commanded_a
        )
        self._last_commanded_a = value
        if self._write_zero_failing:
            _LOGGER.info("smart_charging recovered: charger-current write succeeded again")
            self._write_zero_failing = False

    async def _safe_write_zero(self) -> None:
        """Best-effort stop: called only from the fault path, where the charger current
        write itself may keep failing cycle after cycle (issue #1311/C5's last sentence).
        Mirrors `_log_fault`'s own once-per-outage discipline (`_was_faulted`) rather than
        ADR-0007's prior per-cycle `_LOGGER.exception` (an ERROR with a traceback on every
        cycle the write keeps failing) -- `_write_zero_failing` is a separate outage from
        `_was_faulted`: the write can keep failing for many cycles after the read-side fault
        that first triggered it recovers, or can itself be the only fault (the exception path
        funnels a write-only failure here too). The recovery half lives in `_write` itself,
        the one site every successful write (fault-path or not) passes through."""
        try:
            await self._write(0.0)
        except Exception as err:  # noqa: BLE001 - best-effort stop
            if not self._write_zero_failing:
                _LOGGER.warning("smart_charging failed to write 0 A during fault: %s", err)
                self._write_zero_failing = True

    def _log_fault(self, reason: str) -> None:
        if not self._was_faulted:
            _LOGGER.warning("smart_charging fault: %s", reason)
            self._was_faulted = True

    def _enter_fault(self, reason: str) -> None:
        """ADR-0007/C5's single fault-handling code path, one call: logs the fault
        (`_log_fault`'s own once-per-outage discipline) and starts the fault stop's cooldown
        (`_start_fault_stop_cooldown`, C5/R11, issue #1311) together, so each of the three
        fault sites is one statement in its caller's body -- ADR-0046's body rule for
        `_run_cycle` (a call to a named step, one statement each) rather than two."""
        self._log_fault(reason)
        self._start_fault_stop_cooldown()
