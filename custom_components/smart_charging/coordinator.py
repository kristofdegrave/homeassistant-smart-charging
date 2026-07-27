"""Charging Coordinator (M1) — the control cycle (ADR-0006/0007)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import time as time_of_day
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_ACTIVE_SOC_LIMIT,
    ATTR_REQUIRED_CURRENT_A,
    CHARGEABLE_STATES,
    CONF_CAPTAR_AVAILABLE,
    CONF_CAPTAR_COOLDOWN_MIN,
    CONF_EV_BATTERY_CAPACITY_KWH,
    CONF_GRID_CEILING_A,
    CONF_GRID_SAFETY_OFFSET_A,
    CONF_MAX_CURRENT,
    CONF_MAX_PEAK_KW,
    CONF_MAX_SOLAR_SOC,
    CONF_MIN_CURRENT,
    CONF_NOMINAL_VOLTAGE,
    CONF_PEAK_GRACE_MIN,
    CONF_PEAK_WINDOW_SIZE,
    CONF_POWER_RESPECT_PEAK,
    CONF_SAFETY_MARGIN_W,
    CONF_SMOOTHING_WINDOW,
    CONF_SOLAR_COOLDOWN_MIN,
    CONF_SOLAR_FORECAST_THRESHOLD_KWH,
    CONF_SOLAR_HOLD_MIN,
    CONF_SOLAR_INSTALLED,
    CONF_SOLAR_ONLY_MIDPOINT,
    CONF_SOLAR_ONLY_START_THRESHOLD_W,
    CONF_SOLAR_ONLY_STRATEGY,
    CONF_SOLAR_RESERVE_SOC,
    CONF_SOLAR_START_THRESHOLD_W,
    CONF_SOLAR_STEP_PP,
    CONF_SOLAR_STEP_THRESHOLD_PP,
    DEFAULT_CAPTAR_AVAILABLE,
    DEFAULT_CAPTAR_COOLDOWN_MIN,
    DEFAULT_EV_BATTERY_CAPACITY_KWH,
    DEFAULT_MAX_PEAK_KW,
    DEFAULT_MAX_SOLAR_SOC,
    DEFAULT_PEAK_GRACE_MIN,
    DEFAULT_POWER_RESPECT_PEAK,
    DEFAULT_SAFETY_MARGIN_W,
    DEFAULT_SMOOTHING_WINDOW,
    DEFAULT_SOC_LIMIT,
    DEFAULT_SOLAR_FORECAST_THRESHOLD_KWH,
    DEFAULT_SOLAR_RESERVE_SOC,
    DEFAULT_SOLAR_STEP_PP,
    DEFAULT_SOLAR_STEP_THRESHOLD_PP,
    DOMAIN,
    EVENT_ACTIVE_SOC_LIMIT_CHANGED,
    EVENT_DEADLINE_UNREACHABLE_NOTIFIED,
    MODE_CAPTAR,
    MODE_OFF,
    MODE_POWER,
    MODE_SOLAR,
    MODE_SOLAR_ONLY,
    PEAK_WINDOW_SECONDS,
    PROFILE_AUTO,
    PROFILE_MANUAL,
    ROLE_CHARGER_CURRENT,
    ROLE_CHARGER_POWER,
    ROLE_CHARGER_STATUS,
    ROLE_DEPARTURE_EXTERNAL,
    ROLE_EV_BATTERY_CAPACITY,
    ROLE_EV_SOC,
    ROLE_GRID_VOLTAGE,
    ROLE_NET_POWER,
    ROLE_SOLAR_FORECAST,
)
from .engines.billing_protection import (
    PeakBreachTracker,
    apply_peak_clamp,
    resolve_effective_peak_limit,
)
from .engines.capability_gate import resolve_available_modes
from .engines.cycle_invariant import apply_floor_cap
from .engines.deadline import (
    RequiredCurrentResult,
    resolve_departure_deadline,
    resolve_required_current,
)
from .engines.grid_safety import clamp_to_ceiling
from .engines.peak_demand_tracker import update_monthly_peak_demand
from .engines.signal_conditioning import resolve_voltage, smooth_net_power
from .engines.soc_target import (
    SolarStepUpState,
    resolve_active_soc_limit,
    resolve_solar_reserve_active,
    resolve_solar_step_up,
)
from .modes import captar, power, solar, solar_only
from .modes._phase import Phase
from .profiles.auto import select_mode

SUN_ENTITY_ID = "sun.sun"  # entity-catalog.md: read directly, not through an adapter role.
SUN_STATE_ABOVE_HORIZON = "above_horizon"  # HA's own sun.sun states (glossary: "sun is down"
SUN_STATE_BELOW_HORIZON = "below_horizon"  # is the below_horizon state; "sun is up" its mirror)

_LOGGER = logging.getLogger(__name__)

_SOC_GATED_MODES = (MODE_SOLAR, MODE_SOLAR_ONLY, MODE_CAPTAR)
_SOLAR_MODES = (MODE_SOLAR, MODE_SOLAR_ONLY)  # R8's (and R9's, Task 5.2) Auto-only precondition


def _fresh_mode_state() -> dict:
    """R7/R11: the idle state every mode with one resets to -- disconnect, mode switch,
    and the SOC gate all rebuild from this same shape."""
    return {
        MODE_SOLAR: solar.SolarState.idle(),
        MODE_SOLAR_ONLY: solar_only.SolarOnlyState.idle(),
        MODE_CAPTAR: captar.CaptarState.idle(),
    }


@dataclass
class CycleResult:
    """Outcome of one control cycle: the amps actually written and whether it faulted."""

    commanded_current: float
    fault: bool
    active_mode: str
    monthly_peak_kw: float = 0.0
    effective_peak_limit_kw: float = 0.0
    active_soc_limit: float = 0.0


class SmartChargingCoordinator(DataUpdateCoordinator[CycleResult]):
    """Runs the control cycle every interval, dispatching to the active mode (M1)."""

    def __init__(self, hass: HomeAssistant, *, adapters, config, interval_s: int) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval_s),
        )
        self._adapters = adapters
        self._config = config
        self._interval_s = interval_s
        # Single source of truth for the setpoint is the number entity, which seeds this on
        # add (restored value, else configured default). 0 A is the safe default for cycle 0.
        self.target_current: float = 0.0
        # Single source of truth for these is their owning entity (select/number), which seeds
        # them on add (restored value, else configured default) before the first refresh --
        # this MODE_POWER default only matters for a coordinator instance never wired to a
        # select entity (e.g. a unit test constructing one directly).
        self.active_mode: str = MODE_POWER
        # Mirrors active_mode (R16): seeded Manual, written by select.smart_charging_profile.
        self.active_profile: str = PROFILE_MANUAL
        self.soc_limit_override: float = DEFAULT_SOC_LIMIT
        # R8's lifecycle state, threaded across cycles -- cleared only via
        # resolve_solar_step_up's own is_solar_mode_charging=False branch (Task 5.1), never by
        # the generic per-mode-switch reset below (that would wrongly clear an in-effect
        # step-up on a Solar<->SolarOnly switch, R7/UC06 alternate flow 4a).
        self._step_up_state: SolarStepUpState = SolarStepUpState()
        # ADR-0011: the prior cycle's resolved active SOC limit, for ActiveSocLimitChanged's
        # change-detection. None on cycle 1, so the first resolution always fires the event.
        self._last_active_soc_limit: float | None = None
        # R9/R14 inputs -- single source of truth is meant to be the owning entity
        # (switch.smart_charging_home_day / time.smart_charging_departure_*, mirroring
        # ModeSelect/ProfileSelect's own push-on-change), but that entity->coordinator wiring
        # is not yet threaded (follow-up, alongside Task 6.1's config threading); until then
        # these default conservatively (no home day, no configured deadline anywhere), and
        # tests set them directly, the same way they already set soc_limit_override.
        self.home_day_flag: bool = False
        self.departure_dow_defaults: dict[int, time_of_day | None] = dict.fromkeys(range(7))
        self.departure_holiday_override: time_of_day | None = None
        self.departure_home_day_override: time_of_day | None = None
        # R5: the last cycle's required-current/urgency determination -- exposed for Task 5.3's
        # own use and inspected directly by tests, the same way `_step_up_state` already is.
        self._required_current = RequiredCurrentResult(
            required_a=None, urgent=False, unreachable=False
        )
        self._last_active_mode: str | None = None
        self._net_window: tuple[float, ...] = ()
        self._mode_state = _fresh_mode_state()
        self._was_faulted = False
        # M1's OWN 15-minute window (E5, Task 1.3), distinct from R10's `_net_window` above --
        # a MonthlyPeakSensor restore may seed `_peak_tracked_kw`/`_peak_tracked_month` before
        # the first cycle (Task 4.2); the window itself is deliberately never persisted (design
        # doc Sec 6.4), so it always starts empty here.
        self._peak_window: tuple[float, ...] = ()
        self._peak_tracked_kw: float = 0.0
        self._peak_tracked_month: tuple[int, int] | None = None
        self._peak_tracker = PeakBreachTracker()

    async def _async_update_data(self) -> CycleResult:
        try:
            return await self._run_cycle()
        except Exception as err:  # noqa: BLE001 - every failure funnels to the fault path (ADR-0007)
            self._log_fault(f"cycle exception: {err}")
            await self._safe_write_zero()
            return CycleResult(commanded_current=0.0, fault=True, active_mode=self.active_mode)

    async def _run_cycle(self) -> CycleResult:
        status = await self._adapters[ROLE_CHARGER_STATUS].read()
        net_w = await self._adapters[ROLE_NET_POWER].read()
        charger_w = await self._adapters[ROLE_CHARGER_POWER].read()

        # Grid voltage is the one role where None is NOT a fault (NF4).
        measured_v = None
        if ROLE_GRID_VOLTAGE in self._adapters:
            measured_v = await self._adapters[ROLE_GRID_VOLTAGE].read()
        voltage = resolve_voltage(measured_v, self._config[CONF_NOMINAL_VOLTAGE])

        # Any required role missing -> fault (ADR-0007).
        if status is None or net_w is None or charger_w is None:
            self._log_fault("required adapter returned None")
            await self._write(0.0)
            return CycleResult(commanded_current=0.0, fault=True, active_mode=self.active_mode)

        # Peak-Demand Tracker (E5, Task 1.3) + effective-peak-limit resolution (E5, Task 1.2) --
        # runs every cycle regardless of mode (R3's bookkeeping is not Captar-specific). Uses
        # real wall-clock (dt_util.now()) for month rollover, distinct from the monotonic `now`
        # the mode state machines use below.
        now_dt = dt_util.now()
        current_month = (now_dt.year, now_dt.month)
        if current_month != self._peak_tracked_month:
            # Month rollover resets the SMOOTHING WINDOW too, not just the tracked value --
            # otherwise this cycle's "smoothed" reading would still partly reflect last month's
            # raw samples (design doc Sec 6.4's month-rollover note).
            self._peak_window = ()
        peak_window_size = self._config.get(
            CONF_PEAK_WINDOW_SIZE, max(1, round(PEAK_WINDOW_SECONDS / self._interval_s))
        )
        smoothed_peak_w, self._peak_window = smooth_net_power(
            net_w, self._peak_window, size=peak_window_size
        )
        monthly_peak_kw, self._peak_tracked_month = update_monthly_peak_demand(
            smoothed_peak_w / 1000.0,
            current_month,
            self._peak_tracked_kw,
            self._peak_tracked_month,
        )
        self._peak_tracked_kw = monthly_peak_kw
        # Placeholder urgent=False reproduces today's row-2-only behavior; Task 5.3 wires the
        # real resolved urgency (E4) into this call.
        effective_peak_limit_kw = resolve_effective_peak_limit(
            monthly_peak_kw,
            self._config.get(CONF_MAX_PEAK_KW, DEFAULT_MAX_PEAK_KW),
            urgent=False,
        )

        if self.active_mode != self._last_active_mode:
            # R11: switching mode resets timers -- fresh state for every mode with one, whether
            # or not the incoming mode is one of them (a state nobody is dispatching to is inert
            # either way).
            self._mode_state = _fresh_mode_state()
            self._last_active_mode = self.active_mode

        # ev_soc is read whenever the car is connected and the role is configured -- Task 5.2's
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
        if self.active_mode in _SOC_GATED_MODES and status in CHARGEABLE_STATES and ev_soc is None:
            self._log_fault("ev_soc required while a solar mode is active but missing/None")
            await self._write(0.0)
            return CycleResult(
                commanded_current=0.0,
                fault=True,
                active_mode=self.active_mode,
                monthly_peak_kw=monthly_peak_kw,
                effective_peak_limit_kw=effective_peak_limit_kw,
            )

        # .get(): the smoothing-window option is only wired into the config entry once Task 6.1
        # threads it through __init__.py; smoothing runs every cycle regardless of mode.
        smoothing_window = self._config.get(CONF_SMOOTHING_WINDOW, DEFAULT_SMOOTHING_WINDOW)
        smoothed_net_w, self._net_window = smooth_net_power(
            net_w, self._net_window, size=smoothing_window
        )
        surplus_w = charger_w - smoothed_net_w  # shared by Solar/SolarOnly dispatch below and
        # the baseline-mode dry-run (Task 5.2)
        now = self.hass.loop.time()  # injected, not read inside modes/engines
        # R8 is Auto-only, like R9's reserve cap (resolution-rules.md) -- computed fresh every
        # cycle from THIS cycle's resolved active_mode/active_profile, not the prior one.
        is_solar_mode_charging = (
            self.active_profile == PROFILE_AUTO
            and self.active_mode in _SOLAR_MODES
            and status in CHARGEABLE_STATES
        )
        _, self._step_up_state = resolve_solar_step_up(
            self._step_up_state,
            is_solar_mode_charging=is_solar_mode_charging,
            soc=ev_soc if ev_soc is not None else 0.0,
            default_limit=self.soc_limit_override,
            step_threshold_pp=self._config.get(
                CONF_SOLAR_STEP_THRESHOLD_PP, DEFAULT_SOLAR_STEP_THRESHOLD_PP
            ),
            step_pp=self._config.get(CONF_SOLAR_STEP_PP, DEFAULT_SOLAR_STEP_PP),
            max_solar_soc=self._config.get(CONF_MAX_SOLAR_SOC, DEFAULT_MAX_SOLAR_SOC),
        )

        # R14: departure-external role + sun state, shared by both today's and tomorrow's
        # (one-day-ahead, R9) deadline resolution below. is_holiday is hardcoded False in both
        # calls -- UC11 (public-holiday recognition) is out of this slice's scope, no holiday
        # source is wired in yet, so row 2 of R14's table never matches until UC11 lands.
        external_configured = ROLE_DEPARTURE_EXTERNAL in self._adapters
        external = (
            await self._adapters[ROLE_DEPARTURE_EXTERNAL].read() if external_configured else None
        )
        sun_state = self.hass.states.get(SUN_ENTITY_ID)
        sun_is_up = sun_state is not None and sun_state.state == SUN_STATE_ABOVE_HORIZON
        sun_is_down = sun_state is not None and sun_state.state == SUN_STATE_BELOW_HORIZON
        today_weekday = now_dt.weekday()
        tomorrow_weekday = (today_weekday + 1) % 7

        # R9's precondition (UC07): the same R14 table evaluated one day ahead.
        deadline_tomorrow = resolve_departure_deadline(
            external_configured,
            external,
            is_holiday=False,
            holiday_override=self.departure_holiday_override,
            home_day_flag=self.home_day_flag,
            home_day_override=self.departure_home_day_override,
            day_of_week_default=self.departure_dow_defaults.get(tomorrow_weekday),
        )
        forecast_kwh = (
            await self._adapters[ROLE_SOLAR_FORECAST].read()
            if ROLE_SOLAR_FORECAST in self._adapters
            else None
        )
        solar_reserve_active = resolve_solar_reserve_active(
            profile=self.active_profile,
            home_day_flag=self.home_day_flag,
            sun_is_down=sun_is_down,
            forecast_kwh=forecast_kwh if forecast_kwh is not None else 0.0,
            forecast_threshold_kwh=self._config.get(
                CONF_SOLAR_FORECAST_THRESHOLD_KWH, DEFAULT_SOLAR_FORECAST_THRESHOLD_KWH
            ),
            deadline_tomorrow_resolved=deadline_tomorrow is not None,
        )
        active_soc_limit = resolve_active_soc_limit(
            self.soc_limit_override,
            solar_reserve_active=solar_reserve_active,
            solar_reserve_soc=self._config.get(CONF_SOLAR_RESERVE_SOC, DEFAULT_SOLAR_RESERVE_SOC),
            step_up_state=self._step_up_state,
        )
        if active_soc_limit != self._last_active_soc_limit:
            self.hass.bus.async_fire(
                EVENT_ACTIVE_SOC_LIMIT_CHANGED, {ATTR_ACTIVE_SOC_LIMIT: active_soc_limit}
            )
        self._last_active_soc_limit = active_soc_limit

        # R5/R14/R15: today's departure deadline and the required-current/urgency it drives.
        # Guarded on ev_soc being known -- without an SOC reading (disconnected, or a
        # non-SOC-gated mode with the role unconfigured), urgency can't be computed, mirroring
        # R14's own "no deadline resolved -> urgency never applies" shape.
        if status in CHARGEABLE_STATES and ev_soc is not None:
            deadline_today = resolve_departure_deadline(
                external_configured,
                external,
                is_holiday=False,
                holiday_override=self.departure_holiday_override,
                home_day_flag=self.home_day_flag,
                home_day_override=self.departure_home_day_override,
                day_of_week_default=self.departure_dow_defaults.get(today_weekday),
            )
            sensed_capacity_kwh = (
                await self._adapters[ROLE_EV_BATTERY_CAPACITY].read()
                if ROLE_EV_BATTERY_CAPACITY in self._adapters
                else None
            )
            # R15: prefer the sensed role's current reading, falling back to the configured
            # value both when the role is unmapped and when it currently reads None.
            effective_battery_capacity_kwh = (
                sensed_capacity_kwh
                if sensed_capacity_kwh is not None
                else self._config.get(CONF_EV_BATTERY_CAPACITY_KWH, DEFAULT_EV_BATTERY_CAPACITY_KWH)
            )
            if self.active_profile == PROFILE_AUTO:
                # The baseline mode is evaluated fresh from Auto mode-selection's rows 3-5 alone
                # (urgent=False) every cycle -- never Captar's own already-escalated request,
                # per resolution-rules.md's explicit warning against that (it would make urgency
                # look satisfied the instant it engages and revert every cycle).
                available_modes = resolve_available_modes(
                    solar_available=self._config.get(CONF_SOLAR_INSTALLED, False),
                    captar_available=self._config.get(
                        CONF_CAPTAR_AVAILABLE, DEFAULT_CAPTAR_AVAILABLE
                    ),
                )
                baseline_mode = select_mode(
                    soc=ev_soc,
                    active_soc_limit=active_soc_limit,
                    available_modes=available_modes,
                    urgent=False,
                    solar_capability_present=self._config.get(CONF_SOLAR_INSTALLED, False),
                    sun_is_up=sun_is_up,
                    solar_surplus_sufficient=surplus_w
                    >= self._config[CONF_SOLAR_START_THRESHOLD_W],
                    sun_is_down=sun_is_down,
                    # No low-tariff source is wired in this slice -- the glossary's own
                    # single-tariff default ("the signal is omitted and the flag is treated as
                    # always active") applies unconditionally.
                    low_tariff_active=True,
                    solar_reserve_active=solar_reserve_active,
                )
            else:
                baseline_mode = self.active_mode
            baseline_desired_a = self._mode_desired_current(
                baseline_mode,
                status=status,
                ev_soc=ev_soc,
                active_soc_limit=active_soc_limit,
                surplus_w=surplus_w,
                voltage=voltage,
                now=now,
            )
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
                maximum_permitted_rate_a=self._config[CONF_MAX_CURRENT],
            )
        else:
            required = RequiredCurrentResult(required_a=None, urgent=False, unreachable=False)
        # Exposed for Task 5.3's own use (the effective-peak-limit `urgent` parameter and Auto
        # mode-selection's escalation) and for tests, the same way `_step_up_state` already is.
        self._required_current = required
        if required.unreachable:
            self.hass.bus.async_fire(
                EVENT_DEADLINE_UNREACHABLE_NOTIFIED, {ATTR_REQUIRED_CURRENT_A: required.required_a}
            )

        if status not in CHARGEABLE_STATES:
            desired = 0.0
            # R7/R11: disconnect resets every mode's state, clearing hold/cooldown -- and, for
            # a solar mode or Captar, also ends any SOC gate (resume condition 2: unplug/replug).
            self._mode_state = _fresh_mode_state()
        elif self.active_mode == MODE_OFF:
            desired = 0.0
        elif self.active_mode == MODE_POWER:
            desired = power.desired_current(self.target_current, status)  # unchanged, no SOC gate
        elif self.active_mode in _SOC_GATED_MODES and ev_soc >= active_soc_limit:
            # R7: don't resume until the gate clears. Holding the state at idle() (rather than
            # dispatching into step()) means the next cycle where this branch stops matching --
            # because soc_limit_override rose (resume condition 1) -- dispatches fresh from
            # idle(), re-checking the start threshold normally. No latch, no separate phase.
            desired = 0.0
            if self.active_mode == MODE_CAPTAR:
                self._mode_state[MODE_CAPTAR] = captar.CaptarState.idle()
            else:
                self._mode_state[self.active_mode] = (
                    solar.SolarState.idle()
                    if self.active_mode == MODE_SOLAR
                    else solar_only.SolarOnlyState.idle()
                )
        elif self.active_mode == MODE_SOLAR:
            desired, self._mode_state[MODE_SOLAR] = solar.step(
                surplus_w,
                self._mode_state[MODE_SOLAR],
                now,
                start_threshold_w=self._config[CONF_SOLAR_START_THRESHOLD_W],
                min_a=self._config[CONF_MIN_CURRENT],
                hold_minutes=self._config[CONF_SOLAR_HOLD_MIN],
                cooldown_minutes=self._config[CONF_SOLAR_COOLDOWN_MIN],
                voltage=voltage,
            )
        elif self.active_mode == MODE_SOLAR_ONLY:
            desired, self._mode_state[MODE_SOLAR_ONLY] = solar_only.step(
                surplus_w,
                self._mode_state[MODE_SOLAR_ONLY],
                now,
                start_threshold_w=self._config[CONF_SOLAR_ONLY_START_THRESHOLD_W],
                min_a=self._config[CONF_MIN_CURRENT],
                cooldown_minutes=self._config[CONF_SOLAR_COOLDOWN_MIN],
                strategy=self._config[CONF_SOLAR_ONLY_STRATEGY],
                midpoint=self._config[CONF_SOLAR_ONLY_MIDPOINT],
                voltage=voltage,
            )
        else:  # MODE_CAPTAR
            desired, self._mode_state[MODE_CAPTAR] = captar.step(
                self._mode_state[MODE_CAPTAR],
                now,
                max_a=self._config[CONF_MAX_CURRENT],
                cooldown_minutes=self._config.get(
                    CONF_CAPTAR_COOLDOWN_MIN, DEFAULT_CAPTAR_COOLDOWN_MIN
                ),
            )

        # R3 peak clamp (E5) -- skippable only for Power via its own R17 opt-out (design doc
        # Sec 7). `desired` here is the already-computed mode request from dispatch above --
        # apply_peak_clamp's breach timer only starts/continues when `desired >= min_a`, so the
        # disconnect/Off/SOC-gated branches above (all `desired = 0.0`) can never trip
        # force_stop this cycle, regardless of headroom.
        power_respect_peak = self._config.get(CONF_POWER_RESPECT_PEAK, DEFAULT_POWER_RESPECT_PEAK)
        if not (self.active_mode == MODE_POWER and not power_respect_peak):
            desired, self._peak_tracker, force_stop = apply_peak_clamp(
                desired,
                net_w=net_w,
                charger_w=charger_w,
                voltage=voltage,
                effective_peak_limit_kw=effective_peak_limit_kw,
                safety_margin_w=self._config.get(CONF_SAFETY_MARGIN_W, DEFAULT_SAFETY_MARGIN_W),
                min_a=self._config[CONF_MIN_CURRENT],
                grace_period_s=self._config.get(CONF_PEAK_GRACE_MIN, DEFAULT_PEAK_GRACE_MIN) * 60,
                tracker=self._peak_tracker,
                now=now,
            )
            if force_stop and self.active_mode == MODE_CAPTAR:
                desired = 0.0
                self._mode_state[MODE_CAPTAR] = captar.CaptarState(Phase.COOLDOWN, now)

        desired = clamp_to_ceiling(  # E6 (before E8)
            desired,
            net_w=net_w,
            charger_w=charger_w,
            voltage=voltage,
            ceiling_a=self._config[CONF_GRID_CEILING_A],
            offset_a=self._config[CONF_GRID_SAFETY_OFFSET_A],
        )
        desired = apply_floor_cap(  # E8 invariant last
            desired, min_a=self._config[CONF_MIN_CURRENT], max_a=self._config[CONF_MAX_CURRENT]
        )

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
        )

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
        """`mode`'s own desired current this cycle, from the same dispatch table `_run_cycle`
        uses below, without mutating any persisted per-mode state -- Task 5.2's baseline-mode
        comparison needs a candidate mode's request without actually charging on it."""
        if status not in CHARGEABLE_STATES or mode == MODE_OFF:
            return 0.0
        if mode == MODE_POWER:
            return power.desired_current(self.target_current, status)
        if mode in _SOC_GATED_MODES and ev_soc >= active_soc_limit:
            return 0.0
        if mode == MODE_SOLAR:
            desired, _ = solar.step(
                surplus_w,
                self._mode_state[MODE_SOLAR],
                now,
                start_threshold_w=self._config[CONF_SOLAR_START_THRESHOLD_W],
                min_a=self._config[CONF_MIN_CURRENT],
                hold_minutes=self._config[CONF_SOLAR_HOLD_MIN],
                cooldown_minutes=self._config[CONF_SOLAR_COOLDOWN_MIN],
                voltage=voltage,
            )
            return desired
        if mode == MODE_SOLAR_ONLY:
            desired, _ = solar_only.step(
                surplus_w,
                self._mode_state[MODE_SOLAR_ONLY],
                now,
                start_threshold_w=self._config[CONF_SOLAR_ONLY_START_THRESHOLD_W],
                min_a=self._config[CONF_MIN_CURRENT],
                cooldown_minutes=self._config[CONF_SOLAR_COOLDOWN_MIN],
                strategy=self._config[CONF_SOLAR_ONLY_STRATEGY],
                midpoint=self._config[CONF_SOLAR_ONLY_MIDPOINT],
                voltage=voltage,
            )
            return desired
        # MODE_CAPTAR
        desired, _ = captar.step(
            self._mode_state[MODE_CAPTAR],
            now,
            max_a=self._config[CONF_MAX_CURRENT],
            cooldown_minutes=self._config.get(
                CONF_CAPTAR_COOLDOWN_MIN, DEFAULT_CAPTAR_COOLDOWN_MIN
            ),
        )
        return desired

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
