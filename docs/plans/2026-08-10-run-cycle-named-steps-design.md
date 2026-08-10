# `_run_cycle` named-step decomposition — design

**Date:** 2026-08-10
**Status:** draft (issue #560, ADR-0023)
**Type:** implementation design (a slice of an already-Accepted architectural decision — not a new
decision)

This document is the follow-up docs/plans implementation spec [ADR-0023](../adl/0023-decompose-run-cycle-into-named-steps.md)
itself calls for ("a `docs/plans` implementation spec and TDD task plan... is the next step... the
exact method names, boundaries, and test list are implementation-spec-level detail, not part of
this decision"). It derives the concrete files, classes/methods, and TDD build order for
decomposing the rest of `coordinator.py`'s `_run_cycle`, per ADR-0023's Decision — extending
[ADR-0012](../adl/0012-coordinator-internal-decomposition.md)'s `CycleContext`/`ModeHandler`/
`PeakDemandState`/`SocGateResolver` decomposition (`coordinator_cycle.py`) to the blocks it didn't
name.

**This is a pure internal refactor: no behavior, entity, config, or event change.** ADR-0006's
ten-step order, the separate R3/C4 clamp call sites, `_peak_tracker`, and the `ModeHandler`
registry lookup itself all stay exactly as they are today.

---

## 1. Why this slice

ADR-0023 named the concrete blocks in `_run_cycle` still worth extracting — everything ADR-0012
didn't already fix — and decided (Option A) to give each one a named unit: a plain private
coordinator method for I/O-bound orchestration, or a small pure object/function in
`coordinator_cycle.py` for gating decisions with real decision logic. This spec derives the build
order; it invents no new service, call direction, or behavior.

| ADR-0023 Decision item | Current code (`coordinator.py`) | This slice |
| --- | --- | --- |
| Initial adapter reads + voltage resolution + the first fault check | `:216-230` | **In scope** — `_read_cycle_inputs()`, a coordinator method (§3.1) |
| R14 departure-deadline read-and-resolve block + R9 solar-reserve-cap gating | `:328-383` | **In scope** — `_resolve_deadline_and_reserve()`, a coordinator method (§3.2), calling the new pure `resolve_solar_reserve_gate()` function (§4.2) for the R9 decision itself |
| R5/R14/R15 deadline-urgency call site's own adapter reads | `:417-435` | **In scope** — `_read_deadline_urgency_inputs()`, a coordinator method (§3.3) |
| Disconnect/`Off`/`Power`/SOC-gated-stop dispatch branches around the `ModeHandler` lookup | `:502-531` | **In scope** — `_dispatch_mode()`, a coordinator method (§3.4); the `ModeHandler` registry lookup itself is untouched, per ADR-0012 |
| The two clamp calls (R3, C4) + the floor/cap invariant | `:533-566` | **In scope** — `_apply_clamps()`, a coordinator method (§3.5); clamp *behavior*, `_peak_tracker`, and the R17 opt-out are untouched, only the call sites get a name |
| R8 solar step-up gating | `:306-326` | **In scope** — `SolarStepUpGate`, a new pure class in `coordinator_cycle.py` (§4.1), taking over ownership of `_step_up_state` from the coordinator |
| The ev_soc read + its own SOC-gated fault check | `:264-280` | **Out of scope** — ADR-0023's Decision does not name this block as its own unit (only the *first* fault check, on the required adapters, gets the sentinel-return treatment); it stays inline in `_run_cycle`, short and already isolated as its own early return |
| Net-power smoothing, both `resolve_effective_peak_limit` calls, `auto_dispatchable`, the two `hass.bus.async_fire` sites, the final write/`CycleResult` block | throughout | **Out of scope** — ADR-0023's Context explicitly lists these as staying exactly where they are (single-line pure calls, or HA I/O that must stay directly in the coordinator's own method body per ADR-0009/0010) |
| Mode dispatch's `ModeHandler` registry lookup; `_mode_desired_current`'s baseline dry-run helper | `:515-531`, `:688-726` | **Out of scope** — ADR-0012 territory, untouched; `_mode_desired_current` isn't named anywhere in ADR-0023 |
| `_peak_tracker` (R3 breach-timer) | `PeakBreachTracker`, threaded through `_apply_clamps` | **Out of scope** — untouched, per ADR-0006/ADR-0012, now per ADR-0023 too |

---

## 2. Success criteria

Since this is a no-behavior-change refactor, "works" means: **every existing coordinator test
passes unchanged, with no test-visible difference in commanded current, `active_mode`, fired
events, or `CycleResult` fields, across the full pre-existing `tests/test_coordinator.py` suite**
— the same bar ADR-0012's own implementation slice set.

1. `_run_cycle` becomes a short, literal, top-to-bottom sequence of named calls — still directly
   checkable against ADR-0006's ten steps, still with the R3/C4 clamps as two distinct calls, only
   the R3 call gated by the R17 `power_respect_peak` opt-out, still dispatching through the
   `ModeHandler` registry ADR-0012 established.
2. `_read_cycle_inputs()` returns `None` on a missing required adapter; `_run_cycle` itself
   performs the actual `return CycleResult(...)` on that sentinel — ADR-0007's single
   fault-handling code path stays in `_run_cycle`, not scattered across extracted methods
   (ADR-0023's own stated requirement).
3. `SolarStepUpGate` owns `_step_up_state` (moved off the coordinator instance) and exposes it so
   `SocGateResolver.resolve(step_up_state=...)` — which already takes it as an argument today —
   keeps working unchanged.
4. `resolve_solar_reserve_gate()` is a stateless plain function (not a class) in
   `coordinator_cycle.py`, wrapping `resolve_solar_reserve_active` — nothing threaded across
   cycles.
5. Every new `coordinator_cycle.py` unit is HA-free — no `hass.bus` or other HA I/O — and
   independently unit-testable with plain pytest (ADR-0009/0012/0023).
6. Every new `coordinator.py` method is tested via the existing HA-harness regression suite
   (`tests/test_coordinator.py`) — no new HA-harness tests are added for this slice, matching
   ADR-0012's own implementation slice: the point is that coordinator behavior is identical
   before/after, not that new tests exercise new seams.

---

## 3. New coordinator.py methods

All five are `SmartChargingCoordinator` methods (not `coordinator_cycle.py` units) because each
performs `await self._adapters[...].read()` — per ADR-0009/0010, HA/adapter I/O stays
coordinator-side and cannot become a pure object the way `PeakDemandState`/`SocGateResolver` did.

### 3.1 `_read_cycle_inputs`

```python
async def _read_cycle_inputs(self) -> tuple[str, float, float, float] | None:
    """Step 1 (ADR-0006): read the three required adapters and resolve voltage (NF4's
    fallback -- the one role where a None reading is not a fault). Returns None on a missing
    required adapter; _run_cycle performs the actual fault CycleResult itself, keeping
    ADR-0007's single fault-handling code path in _run_cycle rather than scattered across
    extracted methods (ADR-0023)."""
    status = await self._adapters[ROLE_CHARGER_STATUS].read()
    net_w = await self._adapters[ROLE_NET_POWER].read()
    charger_w = await self._adapters[ROLE_CHARGER_POWER].read()
    measured_v = None
    if ROLE_GRID_VOLTAGE in self._adapters:
        measured_v = await self._adapters[ROLE_GRID_VOLTAGE].read()
    voltage = resolve_voltage(measured_v, self._config[CONF_NOMINAL_VOLTAGE])
    if status is None or net_w is None or charger_w is None:
        return None
    return status, net_w, charger_w, voltage
```

Replaces `coordinator.py:216-224` + the fault check at `:227-230`. `_run_cycle` becomes:

```python
inputs = await self._read_cycle_inputs()
if inputs is None:
    self._log_fault("required adapter returned None")
    await self._write(0.0)
    return CycleResult(commanded_current=0.0, fault=True, active_mode=self.active_mode)
status, net_w, charger_w, voltage = inputs
```

### 3.2 `_resolve_deadline_and_reserve`

```python
async def _resolve_deadline_and_reserve(
    self, ctx: CycleContext, now_dt: datetime
) -> tuple[time_of_day | None, Callable[[int], time_of_day | None]]:
    """R14's departure-external/sun/low-tariff reads and the weekday-parameterised deadline
    table, plus R9's solar-reserve-cap gating (resolve_solar_reserve_gate, coordinator_cycle.py)
    -- the two are resolved together because R9's gate needs tomorrow's deadline, this same
    block's own result. Mutates ctx.sun_is_up/ctx.sun_is_down/ctx.low_tariff_active/
    ctx.solar_reserve_active in place (ADR-0012's existing "assign onto ctx as each value
    resolves" pattern) and returns (deadline_tomorrow, resolve_deadline_for) for _run_cycle's
    later use: deadline_tomorrow was already needed by R9's own gate; resolve_deadline_for is
    the closure `_read_deadline_urgency_inputs` (3.3) calls for today's deadline."""
    external_configured = ROLE_DEPARTURE_EXTERNAL in self._adapters
    external = (
        await self._adapters[ROLE_DEPARTURE_EXTERNAL].read() if external_configured else None
    )
    sun_reading = await self._adapters[ROLE_SUN].read() if ROLE_SUN in self._adapters else None
    ctx.sun_is_up = sun_reading == SUN_STATE_ABOVE_HORIZON
    ctx.sun_is_down = sun_reading == SUN_STATE_BELOW_HORIZON
    ctx.low_tariff_active = True
    if ROLE_LOW_TARIFF in self._adapters:
        low_tariff_reading = await self._adapters[ROLE_LOW_TARIFF].read()
        if low_tariff_reading is not None:
            ctx.low_tariff_active = low_tariff_reading

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

    tomorrow_weekday = (now_dt.weekday() + 1) % 7
    deadline_tomorrow = resolve_deadline_for(tomorrow_weekday)
    forecast_kwh = (
        await self._adapters[ROLE_SOLAR_FORECAST].read()
        if ROLE_SOLAR_FORECAST in self._adapters
        else None
    )
    ctx.solar_reserve_active = resolve_solar_reserve_gate(
        profile=self.active_profile,
        home_day_flag=self.home_day_flag,
        sun_is_down=ctx.sun_is_down,
        forecast_kwh=forecast_kwh,
        forecast_threshold_kwh=self._config.get(
            CONF_SOLAR_FORECAST_THRESHOLD_KWH, DEFAULT_SOLAR_FORECAST_THRESHOLD_KWH
        ),
        deadline_tomorrow_resolved=deadline_tomorrow is not None,
    )
    return deadline_tomorrow, resolve_deadline_for
```

Replaces `coordinator.py:328-383`. `_run_cycle` becomes:

```python
deadline_tomorrow, resolve_deadline_for = await self._resolve_deadline_and_reserve(ctx, now_dt)
active_soc_limit, soc_limit_changed = self._soc_gate.resolve(
    self.soc_limit_override,
    solar_reserve_active=ctx.solar_reserve_active,
    solar_reserve_soc=self._config.get(CONF_SOLAR_RESERVE_SOC, DEFAULT_SOLAR_RESERVE_SOC),
    step_up_state=self._step_up_gate.state,
)
```

(The `SocGateResolver.resolve(...)` call itself, and the `ActiveSocLimitChanged` event fire right
after it, are already a two-line, single-responsibility block today — ADR-0023 does not name them
as a unit, and they stay inline exactly as `PeakDemandState`'s peak-tracking call already does.)

### 3.3 `_read_deadline_urgency_inputs`

```python
async def _read_deadline_urgency_inputs(
    self,
    *,
    deadline_resolvable: bool,
    today_weekday: int,
    resolve_deadline_for: Callable[[int], time_of_day | None],
) -> tuple[time_of_day | None, float]:
    """The R5/R14/R15 deadline-urgency call site's own adapter reads (today's deadline, the
    sensed battery capacity) -- must stay coordinator-side even though resolve_deadline_urgency
    itself is already a pure coordinator_cycle.py function (#506). Returns
    (deadline_today, effective_battery_capacity_kwh); the second value is an unused 0.0 when
    deadline_resolvable is False, exactly as today (resolve_deadline_urgency short-circuits
    before reading it)."""
    if not deadline_resolvable:
        return None, 0.0
    deadline_today = resolve_deadline_for(today_weekday)
    sensed_capacity_kwh = (
        await self._adapters[ROLE_EV_BATTERY_CAPACITY].read()
        if ROLE_EV_BATTERY_CAPACITY in self._adapters
        else None
    )
    effective_battery_capacity_kwh = (
        sensed_capacity_kwh
        if sensed_capacity_kwh is not None
        else self._config.get(CONF_EV_BATTERY_CAPACITY_KWH, DEFAULT_EV_BATTERY_CAPACITY_KWH)
    )
    return deadline_today, effective_battery_capacity_kwh
```

Replaces `coordinator.py:417-435`. `_run_cycle` becomes:

```python
deadline_today, effective_battery_capacity_kwh = await self._read_deadline_urgency_inputs(
    deadline_resolvable=deadline_resolvable,
    today_weekday=today_weekday,
    resolve_deadline_for=resolve_deadline_for,
)
```

(`deadline_resolvable` and `today_weekday` stay one-line computations inline in `_run_cycle`,
exactly as `auto_dispatchable` does — neither is named as its own unit in ADR-0023.)

### 3.4 `_dispatch_mode`

```python
def _dispatch_mode(self, ctx: CycleContext, *, ev_soc: float | None, active_soc_limit: float) -> float:
    """The disconnect/Off/Power/SOC-gated-stop guards around the ModeHandler registry lookup
    (ADR-0012's lookup itself is untouched -- this method only names the surrounding branches
    that decide *whether* to look one up at all). Mutates self._mode_state exactly as today;
    returns the desired current before any clamp."""
    if ctx.status not in CHARGEABLE_STATES:
        self._mode_state = self._fresh_mode_state()
        return 0.0
    if self.active_mode == MODE_OFF:
        return 0.0
    if self.active_mode == MODE_POWER:
        desired, _ = self._mode_handlers[MODE_POWER].desired_current(ctx, None)
        return desired
    if self._mode_handlers[self.active_mode].is_soc_gated and ev_soc >= active_soc_limit:
        self._mode_state[self.active_mode] = self._mode_handlers[self.active_mode].idle_state()
        return 0.0
    desired, self._mode_state[self.active_mode] = self._mode_handlers[
        self.active_mode
    ].desired_current(ctx, self._mode_state.get(self.active_mode))
    return desired
```

Replaces `coordinator.py:502-531`. `_run_cycle` becomes:

```python
desired = self._dispatch_mode(ctx, ev_soc=ev_soc, active_soc_limit=active_soc_limit)
```

### 3.5 `_apply_clamps`

```python
def _apply_clamps(
    self, desired: float, *, net_w: float, charger_w: float, voltage: float,
    effective_peak_limit_kw: float, now: float,
) -> float:
    """R3 peak clamp (skippable only for Power via its own R17 opt-out) and C4 grid-ceiling
    clamp (never skippable) -- two distinct call sites exactly as ADR-0006 requires, plus the
    R11/C1 floor/cap invariant. Mutates self._peak_tracker and, on an R3 force-stop while
    Captar is active, self._mode_state[MODE_CAPTAR] -- both exactly as today."""
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
    desired = clamp_to_ceiling(
        desired, net_w=net_w, charger_w=charger_w, voltage=voltage,
        ceiling_a=self._config[CONF_GRID_CEILING_A], offset_a=self._config[CONF_GRID_SAFETY_OFFSET_A],
    )
    return apply_floor_cap(
        desired, min_a=self._config[CONF_MIN_CURRENT], max_a=self._config[CONF_MAX_CURRENT]
    )
```

Replaces `coordinator.py:533-566`. `_run_cycle` becomes:

```python
desired = self._apply_clamps(
    desired, net_w=net_w, charger_w=charger_w, voltage=voltage,
    effective_peak_limit_kw=effective_peak_limit_kw, now=now,
)
```

---

## 4. New `coordinator_cycle.py` units

### 4.1 `SolarStepUpGate`

```python
class SolarStepUpGate:
    """R8 solar step-up gating (ADR-0023), wrapping engines/soc_target.py::resolve_solar_step_up.
    Owns the SolarStepUpState itself -- moved off the coordinator instance, the same way
    SocGateResolver already owns _last_active_soc_limit -- and exposes it via .state for
    SocGateResolver.resolve(step_up_state=...), which already takes it as an argument today."""

    def __init__(self) -> None:
        self._state = SolarStepUpState()

    @property
    def state(self) -> SolarStepUpState:
        return self._state

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
        computation exactly. Mutates self._state in place; callers read .state afterward."""
        is_solar_mode_charging = (
            profile == PROFILE_AUTO and mode_is_solar and status in CHARGEABLE_STATES
        )
        _, self._state = resolve_solar_step_up(
            self._state,
            is_solar_mode_charging=is_solar_mode_charging,
            soc=soc if soc is not None else 0.0,
            default_limit=default_limit,
            step_threshold_pp=step_threshold_pp,
            step_pp=step_pp,
            max_solar_soc=max_solar_soc,
        )
```

Needs two new imports in `coordinator_cycle.py`: `PROFILE_AUTO` and `CHARGEABLE_STATES` from
`.const` (neither is imported there today — both already exist in `const.py`, used throughout
`coordinator.py`).

`coordinator.py` replaces `self._step_up_state: SolarStepUpState = SolarStepUpState()` in
`__init__` with `self._step_up_gate = SolarStepUpGate()`, and every other reference to
`self._step_up_state` becomes `self._step_up_gate.state` (there is exactly one other reference:
`SocGateResolver.resolve(step_up_state=self._step_up_gate.state, ...)`). `_run_cycle`'s call site
(`coordinator.py:311-326`) becomes:

```python
self._step_up_gate.resolve(
    profile=self.active_profile,
    mode_is_solar=self._mode_handlers[self.active_mode].is_solar_mode,
    status=status,
    soc=ev_soc,
    default_limit=self.soc_limit_override,
    step_threshold_pp=self._config.get(CONF_SOLAR_STEP_THRESHOLD_PP, DEFAULT_SOLAR_STEP_THRESHOLD_PP),
    step_pp=self._config.get(CONF_SOLAR_STEP_PP, DEFAULT_SOLAR_STEP_PP),
    max_solar_soc=self._config.get(CONF_MAX_SOLAR_SOC, DEFAULT_MAX_SOLAR_SOC),
)
```

### 4.2 `resolve_solar_reserve_gate`

```python
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
```

Called from `_resolve_deadline_and_reserve` (§3.2). No new imports needed —
`resolve_solar_reserve_active` is already imported into `coordinator_cycle.py`... **correction:**
it is not; `coordinator_cycle.py` today imports only `SolarStepUpState, resolve_active_soc_limit`
from `engines.soc_target`. This task adds `resolve_solar_reserve_active` to that same import line.

---

## 5. Before/after in `coordinator.py`

- `__init__`: replace `self._step_up_state: SolarStepUpState = SolarStepUpState()` with
  `self._step_up_gate = SolarStepUpGate()` (§4.1). No other `__init__` field changes — `_peak_demand`,
  `_soc_gate`, `_mode_handlers`, `_peak_tracker` are all ADR-0012 territory, untouched.
- `_run_cycle` becomes the sequence in §3's "`_run_cycle` becomes" snippets, in the same order
  as today, interleaved with the untouched one-line steps (`_reset_mode_state_if_changed()` called
  twice exactly as today, `PeakDemandState.update`, the two `resolve_effective_peak_limit` calls,
  `auto_dispatchable`, the ev_soc read + its own fault check, `resolve_deadline_urgency`, the two
  `hass.bus.async_fire` sites, Auto's `active_mode` assignment, the final `_write`/`CycleResult`
  block). No step is reordered; every extraction is "replace these lines with one named call,"
  not a behavior change.
- `_mode_desired_current` (the baseline dry-run helper, `:688-726`) is **not touched** — ADR-0023
  does not name it, and it already routes through the same `ModeHandler` registry `_dispatch_mode`
  uses (ADR-0012 territory).

No entity, config key, adapter role, or domain event changes. `CycleResult` (the public return
type) is unchanged.

---

## 6. Testing (ADR-0009/0012/0023 harness split)

Both new `coordinator_cycle.py` units are HA-free → **plain pytest**, added to the existing
`tests/test_coordinator_cycle.py`:

- `SolarStepUpGate.resolve`: `is_solar_mode_charging`'s three-way gate (wrong profile, wrong
  mode, disconnected status each independently suppress a step) produces the same
  `resolve_solar_step_up` call as calling the wrapped function directly with the equivalent
  `is_solar_mode_charging` boolean — anchored against `tests/engines/test_soc_target.py`'s own
  `resolve_solar_step_up` fixtures, not re-derived. `.state` reflects the mutation after
  `resolve()`; a fresh `SolarStepUpGate()` starts at `SolarStepUpState()`'s own default.
- `resolve_solar_reserve_gate`: delegates to `resolve_solar_reserve_active` unchanged when
  `forecast_kwh` is a real float; a `None` forecast reading is treated as `0.0` — anchored
  against `tests/engines/test_soc_target.py`'s own `resolve_solar_reserve_active` fixtures.

The five new `coordinator.py` methods are I/O-bound → tested via the existing HA-harness
regression suite (`tests/test_coordinator.py`), not new pure-unit tests, per ADR-0023's
Consequences. No new HA-harness tests are added for this slice — its whole point is that
coordinator behavior is identical before/after, the same policy ADR-0012's own implementation
slice used. The regression pass explicitly includes reading the post-refactor `_run_cycle` and
confirming the R3/C4 clamp calls, the `power_respect_peak` opt-out, and `_peak_tracker`'s
threading are byte-for-byte where they were — the exact kind of stale-line-reference mistake
ADR-0012's own implementation spec caught during its own fresh-agent review.

---

## 7. Packaging

```text
custom_components/smart_charging/
  coordinator_cycle.py    # + SolarStepUpGate, resolve_solar_reserve_gate (§4); existing
                          #   CycleContext/ModeHandler/PeakDemandState/SocGateResolver untouched
  coordinator.py           # _run_cycle delegates to 5 new named methods (§3) plus the existing
                          #   ADR-0012 units; ten-step order (ADR-0006) and the R3/C4 clamp
                          #   separation unchanged; _peak_tracker untouched; self._step_up_state
                          #   replaced by self._step_up_gate
```

`tests/` mirrors 1:1 (ADR-0002/0009): `tests/test_coordinator_cycle.py` gains the two new units'
tests (no new file); `tests/test_coordinator.py` is unchanged in content but must keep passing in
full.

---

## 8. Deliberately deferred

- Any behavior, entity, config, or event change — this slice is refactor-only.
- The ev_soc read + its own SOC-gated fault check (`coordinator.py:264-280`) — ADR-0023's Decision
  does not name this as its own unit; it stays inline, short and already an isolated early return.
- `_mode_desired_current`'s baseline dry-run helper — not named by ADR-0023; already routes
  through the ADR-0012 `ModeHandler` registry.
- A general-purpose `CycleStep` pipeline (ADR-0012 Option B / ADR-0023 Option B, both rejected) —
  not revisited here.
- Any further decomposition ADR-0023 doesn't name (e.g. `auto_dispatchable`, the
  `resolve_effective_peak_limit` calls) — a new decision at that time, per ADR-0023's own
  Consequences, not something this spec pre-answers.

---

## 9. Next step

This design feeds the `writing-plans` skill to produce the ordered, test-driven implementation
plan (`2026-08-10-run-cycle-named-steps.md`). Build order: `coordinator_cycle.py`'s two new units
(each test-first and independently green) → wire `coordinator.py` to delegate to them and to the
five new named methods, one extraction at a time, full regression pass after each → a final pass
confirming the R3/C4 clamp separation and `_peak_tracker` threading are unchanged. No
`custom_components/` code is written until the paired plan exists and is approved.
