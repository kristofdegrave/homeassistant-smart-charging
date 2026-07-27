# Coordinator internal decomposition — design

**Date:** 2026-07-27
**Status:** draft (issue #384, ADR-0012 issue #372, epic n/a — internal refactor)
**Type:** implementation design (a slice of an already-Accepted architectural decision — not a new
decision)

This document is the follow-up docs/plans implementation spec [ADR-0012](../adl/0012-coordinator-internal-decomposition.md)
itself calls for ("the four new units, the `CycleContext` shape, and the before/after diff are
implementation-spec-level detail, not part of this decision"). It derives the concrete files,
classes, and TDD build order for extracting `CycleContext`, a `ModeHandler` Strategy, `PeakDemandState`,
and `SocGateResolver` out of `coordinator.py`'s `_run_cycle`, per ADR-0012's Option D.

**This is a pure internal refactor: no behavior, entity, or event change.** Nothing here revisits
ADR-0006's ten-step order or the separate R3/C4 clamp call sites — both stay exactly as they are today.

---

## 1. Why this slice

ADR-0012 named three concrete SOLID violations in `coordinator.py::_run_cycle` and decided (Option D)
to extract four units to address them, while leaving ADR-0006's step order and the R3/C4 clamp
separation untouched. This spec derives the build order; it invents no new service, call direction, or
behavior.

`_run_cycle` has grown substantially since ADR-0012 was drafted — Auto mode-selection (#326/#373),
deadline/urgency (E4), and the SOC-gate/step-up lifecycle are now interleaved with the three original
pain points. The extraction targets themselves are unchanged and still clearly present; this spec scopes
`CycleContext` to the **current** set of values threaded across steps, not just the smaller set that
existed when ADR-0012 was drafted (confirmed with the human partner, since `CycleContext`'s shape is
explicitly implementation-spec detail per ADR-0012's Consequences, not a re-opening of the ADR).

| ADR-0012 violation | Current code | This slice |
| --- | --- | --- |
| Mode-dispatch `if/elif` chain | `coordinator.py` real dispatch (~500-554) **and** a near-duplicate dry-run copy in `_mode_desired_current` (~614-668), the latter added by Task 5.2 after the ADR was drafted | **In scope** — one `ModeHandler` registry serving **both** call sites (confirmed with the human partner; removes the duplication ADR-0012 didn't know about) |
| Three loose peak-tracking fields | `_peak_window`/`_peak_tracked_kw`/`_peak_tracked_month`, mutated inline | **In scope** — `PeakDemandState` |
| Inlined SOC-gate resolution + change detection | `active_soc_limit` resolution + `_last_active_soc_limit` comparison + event fire, inlined | **In scope** — `SocGateResolver` (resolution only; the coordinator still fires `ActiveSocLimitChanged`, per ADR-0012) |
| (new, cross-cutting) | Every step now reads/writes local variables (`ev_soc`, `surplus_w`, `voltage`, `urgent`, deadline results, ...) by hand | **In scope** — `CycleContext` carries the full current set, not just the ADR's original three |
| `_peak_tracker` (R3 breach-timer) | `PeakBreachTracker`, threaded through the step-7 clamp only | **Out of scope** — untouched, per ADR-0012 |
| Disconnect / Off / SOC-gate stop-charging branches | The `if status not in CHARGEABLE_STATES: ... elif MODE_OFF: ... elif SOC-gated and ev_soc>=limit: ...` guards around dispatch | **Out of scope** — coordinator orchestration, per ADR-0012's own text; `ModeHandler` replaces only the per-mode `step()` calls these guards lead into |

---

## 2. Success criteria

Since this is a no-behavior-change refactor, "works" means: **every existing coordinator test passes
unchanged, with no test-visible difference in commanded current, `active_mode`, fired events, or
`CycleResult` fields, across the full pre-existing `tests/test_coordinator.py` suite.**

1. `CycleContext` exists and carries every value `_run_cycle` currently threads by hand between steps.
2. A `dict[str, ModeHandler]` lookup replaces both the real-dispatch `if/elif` and `_mode_desired_current`'s
   duplicate chain; adding a mode is "write `modes/<mode>.py` + register one handler", no chain edit.
3. `PeakDemandState.update(...)` replaces the three loose fields and their inline mutation.
4. `SocGateResolver.resolve(...)` replaces the inline `resolve_active_soc_limit` call + `_last_active_soc_limit`
   comparison; the coordinator still fires `ActiveSocLimitChanged` itself on a reported change.
5. ADR-0006's ten explicit steps remain a literal, readable sequence of calls in `_run_cycle`; the R3
   peak clamp and C4 ceiling clamp remain two separate call sites, `_peak_tracker` untouched.
6. Every new unit (`CycleContext`, `PeakDemandState`, `SocGateResolver`, each `ModeHandler`) is pure —
   no `hass.bus` or other HA I/O — and independently unit-testable with plain pytest (ADR-0009/0012).

---

## 3. New module: `coordinator_cycle.py`

All four units are coordinator-internal orchestration objects, not reusable policy (system-design §4
rule 4: an engine may not call another engine; these call engines, so they aren't engines themselves),
so they get one new sibling module, imported only by `coordinator.py` — the same "private helper" home
`modes/_phase.py` already establishes for a module with exactly one consumer:

```text
custom_components/smart_charging/coordinator_cycle.py
```

### 3.1 `CycleContext`

A mutable dataclass, constructed once per cycle and progressively filled as `_run_cycle`'s steps run (the
values aren't all known up front — e.g. `active_soc_limit` is resolved mid-cycle, `urgent` later still).
Replaces the current crop of local variables threaded by hand:

```python
@dataclass
class CycleContext:
    status: str
    net_w: float
    charger_w: float
    voltage: float
    now: float          # monotonic (hass.loop.time()), for mode state machines
    now_dt: datetime     # wall-clock (dt_util.now()), for month rollover / weekday
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
```

No behavior lives on `CycleContext` itself — it is a data carrier, matching ADR-0012's own description
("a `CycleContext` dataclass carrying raw/smoothed readings, voltage, and `now` between steps").

### 3.2 `PeakDemandState`

Wraps `engines/peak_demand_tracker.py` + the smoothing call the peak window already needs, owning the
three fields as one cohesive object:

```python
@dataclass
class PeakDemandState:
    window: tuple[float, ...] = ()
    tracked_kw: float = 0.0
    tracked_month: tuple[int, int] | None = None

    def update(self, net_w: float, now_dt: datetime, *, window_size: int) -> float:
        """Returns the updated monthly_peak_kw; mutates self in place."""
        current_month = (now_dt.year, now_dt.month)
        if current_month != self.tracked_month:
            self.window = ()
        smoothed_w, self.window = smooth_net_power(net_w, self.window, size=window_size)
        self.tracked_kw, self.tracked_month = update_monthly_peak_demand(
            smoothed_w / 1000.0, current_month, self.tracked_kw, self.tracked_month
        )
        return self.tracked_kw
```

`coordinator.py` holds one `self._peak_demand: PeakDemandState` (replacing the three fields), constructed
in `__init__`. `_peak_tracker` (`PeakBreachTracker`, the R3 clamp's own breach-timer) is a different
concern and stays a separate field, untouched (ADR-0012 Decision).

### 3.3 `SocGateResolver`

Pure resolution + change detection, wrapping `engines/soc_target.py::resolve_active_soc_limit`:

```python
class SocGateResolver:
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
        """Returns (active_soc_limit, changed_since_last_cycle)."""
        limit = resolve_active_soc_limit(
            override,
            solar_reserve_active=solar_reserve_active,
            solar_reserve_soc=solar_reserve_soc,
            step_up_state=step_up_state,
        )
        changed = limit != self._last_limit
        self._last_limit = limit
        return limit, changed
```

`coordinator.py` holds `self._soc_gate: SocGateResolver` (replacing `_last_active_soc_limit`), and still
fires `EVENT_ACTIVE_SOC_LIMIT_CHANGED` itself when `changed` is `True` — the HA I/O stays coordinator-side,
per ADR-0009/0010/ADR-0012's boundary.

### 3.4 `ModeHandler` Strategy

A `Protocol` with one method, wrapping each `modes/*.py` module's existing `step()` (or `desired_current()`
for `power`) unchanged:

```python
class ModeHandler(Protocol):
    def desired_current(self, ctx: CycleContext, state: Any) -> tuple[float, Any]:
        """Returns (desired_current_a, new_state); does not mutate ctx or state in place."""
        ...
```

One thin adapter per mode, each holding whatever config values its wrapped `step()` needs (bound at
construction, from `self._config`), e.g.:

```python
class _SolarModeHandler:
    def __init__(self, config: Mapping) -> None:
        self._config = config

    def desired_current(self, ctx: CycleContext, state: solar.SolarState) -> tuple[float, solar.SolarState]:
        return solar.step(
            ctx.surplus_w, state, ctx.now,
            start_threshold_w=self._config[CONF_SOLAR_START_THRESHOLD_W],
            min_a=self._config[CONF_MIN_CURRENT],
            hold_minutes=self._config[CONF_SOLAR_HOLD_MIN],
            cooldown_minutes=self._config[CONF_SOLAR_COOLDOWN_MIN],
            voltage=ctx.voltage,
        )
```

`_OffModeHandler`/`_PowerModeHandler`/`_SolarOnlyModeHandler`/`_CaptarModeHandler` follow the same shape,
wrapping `modes/power.py::desired_current` / `modes/solar_only.py::step` / `modes/captar.py::step`
unchanged. `coordinator.py` builds the registry once in `__init__`:

```python
self._mode_handlers: dict[str, ModeHandler] = {
    MODE_OFF: _OffModeHandler(),
    MODE_POWER: _PowerModeHandler(),
    MODE_SOLAR: _SolarModeHandler(config),
    MODE_SOLAR_ONLY: _SolarOnlyModeHandler(config),
    MODE_CAPTAR: _CaptarModeHandler(config),
}
```

**Both call sites use it** (confirmed with the human partner): the real dispatch (after the
disconnect/Off/SOC-gate guards already decide `desired = 0.0` and skip the lookup, exactly as today) calls
`self._mode_handlers[self.active_mode].desired_current(ctx, self._mode_state.get(self.active_mode))`; the
baseline dry-run (`_mode_desired_current`, Task 5.2) calls the same lookup against a *candidate* mode
without persisting the returned state. `_mode_desired_current` becomes a thin wrapper around the same
registry instead of its own duplicated chain.

The disconnect / `MODE_OFF` / SOC-gated-stop guards **stay inline in `_run_cycle`**, unchanged — they are
coordinator orchestration deciding *whether* to dispatch at all, not per-mode logic (ADR-0012: out of
scope).

---

## 4. Before/after in `coordinator.py`

- `__init__`: replace `_peak_window`/`_peak_tracked_kw`/`_peak_tracked_month` with one `self._peak_demand
  = PeakDemandState()`; replace `_last_active_soc_limit` with `self._soc_gate = SocGateResolver()`; add
  `self._mode_handlers` (the registry, §3.4).
- `_run_cycle`: construct one `CycleContext` early (once `status`/`net_w`/`charger_w`/`voltage` are known),
  fill in each field as its step resolves it (same order as today — no step reordered), and pass `ctx` to
  the peak-demand, SOC-gate, and mode-dispatch calls instead of loose locals. The disconnect/fault early
  returns keep constructing a `CycleResult` exactly as today.
- `_mode_desired_current`: becomes `self._mode_handlers[mode].desired_current(ctx, self._mode_state.get(mode))`,
  dropping its own `if/elif`.
- Step 7 (R3 clamp) and step 8 (C4 ceiling clamp) call sites, and `_peak_tracker`'s threading through step 7,
  are **not touched**.

No entity, config key, adapter role, or domain event changes. `CycleResult` (the public return type) is
unchanged.

---

## 5. Testing (ADR-0009/0012 harness split)

All four new units are pure (no `hass.bus`/HA I/O) → **plain pytest**, in a new `tests/test_coordinator_cycle.py`:

- `PeakDemandState.update`: same-month accumulation (max of tracked vs. smoothed); month rollover resets
  both `tracked_kw` and the smoothing `window` (not just the tracked value) — the exact existing
  `_run_cycle` behavior (design doc Sec 6.4's rollover note), now unit-tested in isolation.
- `SocGateResolver.resolve`: first call always reports `changed=True` (mirrors today's `None` sentinel);
  an unchanged limit reports `changed=False`; a changed limit reports `changed=True` and updates the
  remembered value.
- Each `ModeHandler.desired_current`: delegates to its wrapped `modes/*.py` function with the right
  config/state, returns `(current, new_state)` unchanged from what that function returns — one test per
  mode, reusing the existing `modes/*.py` test fixtures' expected values as the anchor (not re-deriving
  mode behavior).
- `CycleContext`: constructible with defaults; no behavior to test beyond that (it is a data carrier).

**Regression**, HA harness (`tests/test_coordinator.py`, already exists — no new file): the full existing
suite must pass unchanged after the refactor, proving no observable-behavior drift. No new coordinator
tests are added for this slice — its whole point is that coordinator behavior is identical before/after.

---

## 6. Packaging

```text
custom_components/smart_charging/
  coordinator_cycle.py    # NEW — CycleContext, PeakDemandState, SocGateResolver, ModeHandler
                          #   Protocol + per-mode adapters (§3)
  coordinator.py           # _run_cycle delegates to the above; ten-step order (ADR-0006) and the
                          #   R3/C4 clamp separation unchanged; _peak_tracker untouched
```

`tests/` mirrors 1:1 (ADR-0002/0009): new `tests/test_coordinator_cycle.py` (plain pytest); no change to
`tests/test_coordinator.py`'s file location, only that it must keep passing.

---

## 7. Deliberately deferred

- Any behavior, entity, config, or event change — this slice is refactor-only.
- A general-purpose `CycleStep` pipeline (ADR-0012 Option B, rejected) — not revisited here.
- A fifth mode, or any new cross-cutting concern discovered later that doesn't fit these four units — a
  new decision at that time, per ADR-0012's own Consequences, not something this spec pre-answers.

---

## 8. Next step

This design feeds the `writing-plans` skill to produce the ordered, test-driven implementation plan
(`2026-07-27-coordinator-decomposition.md`). Build order: `coordinator_cycle.py` (the four units, each
test-first and independently green) → wire `coordinator.py` to delegate to them, one extraction at a time
(peak-demand, then SOC-gate, then mode dispatch, then the dry-run unification) → full regression pass
against the existing coordinator suite. No `custom_components/` code is written until the paired plan
exists and is approved.
