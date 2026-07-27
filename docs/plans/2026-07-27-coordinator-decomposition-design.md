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
| Mode-dispatch `if/elif` chain | `coordinator.py` real dispatch (`:477-508`) **and** a near-duplicate dry-run copy in `_mode_desired_current` (`:558-612`), the latter added by Task 5.2 after the ADR was drafted | **In scope** — one `ModeHandler` registry serving **both** call sites (confirmed with the human partner; removes the duplication ADR-0012 didn't know about) |
| Three loose peak-tracking fields | `_peak_window`/`_peak_tracked_kw`/`_peak_tracked_month`, mutated inline | **In scope** — `PeakDemandState` |
| Inlined SOC-gate resolution + change detection | `active_soc_limit` resolution + `_last_active_soc_limit` comparison + event fire, inlined | **In scope** — `SocGateResolver` (resolution only; the coordinator still fires `ActiveSocLimitChanged`, per ADR-0012) |
| (new, cross-cutting) | The values the four extracted units read/produce (`ev_soc`, `surplus_w`, `voltage`, `active_soc_limit`, ...) plus other already-resolved cross-cutting values (`urgent` at `:473`, `sun_is_up`/`sun_is_down` at `:321-322`, `low_tariff_active` at `:325-329`, `solar_reserve_active` at `:348-357`) that later steps already read by hand | **In scope** — `CycleContext` carries this current set (§3.1); §4 names exactly where each field is assigned |
| `_peak_tracker` (R3 breach-timer) | `PeakBreachTracker`, threaded through the step-7 clamp only | **Out of scope** — untouched, per ADR-0012 |
| Disconnect / Off / SOC-gate stop-charging branches | The `if status not in CHARGEABLE_STATES: ... elif MODE_OFF: ... elif SOC-gated and ev_soc>=limit: ...` guards around dispatch | **Out of scope** — coordinator orchestration, per ADR-0012's own text; `ModeHandler` replaces only the per-mode `step()` calls these guards lead into |
| `MonthlyPeakSensor`'s restore/attribute reads of the three peak-tracking fields (`sensor.py`) | Reads `coordinator._peak_tracked_kw`/`_peak_tracked_month` directly for restore-state and `extra_state_attributes` | **In scope** — `sensor.py` reads/writes through `coordinator._peak_demand` instead (§4); missed in the first draft, added after fresh-agent review |

---

## 2. Success criteria

Since this is a no-behavior-change refactor, "works" means: **every existing coordinator test passes
unchanged, with no test-visible difference in commanded current, `active_mode`, fired events, or
`CycleResult` fields, across the full pre-existing `tests/test_coordinator.py` suite.**

1. `CycleContext` exists and carries the values the four extracted units consume, plus the other
   cross-cutting values named in §1's table row 4 — each assigned at the exact point in `_run_cycle`
   where it's resolved today (§4 names each assignment; nothing is left unpopulated).
2. A `dict[str, ModeHandler]` lookup replaces both the real-dispatch `if/elif` and `_mode_desired_current`'s
   duplicate chain; adding a mode is "write `modes/<mode>.py` + register one handler", no chain edit.
3. `PeakDemandState.update(...)` replaces the three loose fields and their inline mutation, **and**
   `sensor.py`'s `MonthlyPeakSensor` reads/writes through it instead of the old fields directly (§4).
4. `SocGateResolver.resolve(...)` replaces the inline `resolve_active_soc_limit` call + `_last_active_soc_limit`
   comparison; the coordinator still fires `ActiveSocLimitChanged` itself on a reported change.
5. ADR-0006's ten explicit steps remain a literal, readable sequence of calls in `_run_cycle`; the R3
   peak clamp and C4 ceiling clamp remain two separate call sites, `_peak_tracker` untouched — verified
   by an explicit check (plan Task 4.1), not just a dead-code grep.
6. Every new unit (`CycleContext`, `PeakDemandState`, `SocGateResolver`, each `ModeHandler`) is HA-free —
   no `hass.bus` or other HA I/O — and independently unit-testable with plain pytest (ADR-0009/0012).
   `PeakDemandState` and `SocGateResolver` hold cross-cycle state (they are *stateful*, not stateless,
   per system-design's engine taxonomy); "HA-free" is the property that matters for their test boundary,
   not statelessness.

---

## 3. New module: `coordinator_cycle.py`

All four units are coordinator-internal orchestration objects, not reusable policy (system-design §4
rule 4: an engine may not call another engine; these call engines, so they aren't engines themselves),
so they get one new sibling module, imported only by `coordinator.py`:

```text
custom_components/smart_charging/coordinator_cycle.py
```

**Deviation from ADR-0002, stated explicitly.** ADR-0002 rejected keeping HA-free logic in the same
namespace as HA-coupled code (its Option A), and ADR-0010 established `engines/` as the home for
HA-free *policy*. `coordinator_cycle.py` is HA-free but is **not** policy — it holds no domain rule of
its own, only orchestration wiring (a data carrier, two thin state-tracking wrappers, and adapters over
existing `modes/*.py` functions) that exists solely to serve `coordinator.py`, exactly as ADR-0012
describes it. It is accepted as a root-level module — not `engines/`, which is reserved for reusable
policy other Managers could import, and these four units never will be — on the same basis ADR-0002
grandfathers `coordinator.py` itself at the root. `modes/_phase.py` is not offered as precedent for this
placement (it lives inside the already-HA-free `modes/` subpackage, a different situation); the
precedent here is `coordinator.py`'s own root placement.

### 3.1 `CycleContext`

A mutable dataclass, constructed once per cycle and progressively filled as `_run_cycle`'s steps run —
the values aren't all known up front (e.g. `active_soc_limit` is resolved mid-cycle, `urgent` later
still). Every field below is assigned at a specific, named point in `_run_cycle` today (§4 lists each
one); none is a placeholder for behavior this slice doesn't build. Replaces the current crop of local
variables threaded by hand:

```python
@dataclass
class CycleContext:
    status: str
    net_w: float
    charger_w: float
    voltage: float
    now: float                 # monotonic (hass.loop.time()), for mode state machines
    now_dt: datetime | None     # wall-clock (dt_util.now()); None only in _mode_desired_current's
                                # dry-run construction (§3.4), which needs no month/weekday context
    ev_soc: float | None = None
    surplus_w: float = 0.0
    monthly_peak_kw: float = 0.0
    effective_peak_limit_kw: float = 0.0
    active_soc_limit: float = 0.0
    urgent: bool = False              # real value from :473 (required.urgent or required.unreachable)
    sun_is_up: bool = False           # from :321
    sun_is_down: bool = False         # from :322
    low_tariff_active: bool = True    # from :325-329 (adapter override of the single-tariff default)
    solar_reserve_active: bool = False  # from :348-357
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
construction, from `self._config`). `_PowerModeHandler` is the one exception — `power.desired_current`
reads the coordinator's own mutable `target_current` (set externally by the number entity each cycle,
not part of "this cycle's readings"), so its handler takes a zero-arg getter bound at construction
(`lambda: self.target_current`) instead:

```python
class _PowerModeHandler:
    def __init__(self, target_current_getter: Callable[[], float]) -> None:
        self._target_current_getter = target_current_getter

    def desired_current(self, ctx: CycleContext, state: Any) -> tuple[float, Any]:
        return power.desired_current(self._target_current_getter(), ctx.status), state
```

`_SolarModeHandler` (and the other three) follow the shared shape:

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
    MODE_POWER: _PowerModeHandler(lambda: self.target_current),
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

**Resolved decision on `MODE_OFF`/`MODE_POWER`'s state lookup (was left open in the first draft):**
`self._mode_state` has entries only for `MODE_SOLAR`/`MODE_SOLAR_ONLY`/`MODE_CAPTAR` (`_fresh_mode_state()`)
— `MODE_OFF` and `MODE_POWER` never had state and must not gain any. Every call site therefore uses
`self._mode_state.get(self.active_mode)` (never `[...]`, which would `KeyError` for those two modes),
and the returned `new_state` for `MODE_OFF`/`MODE_POWER` is **discarded**, not written back — mirroring
today's behavior where those two branches never touch `_mode_state` at all. `_OffModeHandler`/
`_PowerModeHandler.desired_current` both simply return whatever `state` they were given unchanged
(`None`, since `.get()` on a missing key), so discarding it is a no-op either way; the discard is the
rule that keeps the invariant explicit rather than relying on that no-op.

The disconnect / `MODE_OFF` / SOC-gated-stop guards **stay inline in `_run_cycle`**, unchanged — they are
coordinator orchestration deciding *whether* to dispatch at all, not per-mode logic (ADR-0012: out of
scope).

---

## 4. Before/after in `coordinator.py`

- `__init__`: replace `_peak_window`/`_peak_tracked_kw`/`_peak_tracked_month` with one `self._peak_demand
  = PeakDemandState()`; replace `_last_active_soc_limit` with `self._soc_gate = SocGateResolver()`; add
  `self._mode_handlers` (the registry, §3.4).
- `_run_cycle`: construct one `CycleContext` once `status`/`net_w`/`charger_w`/`voltage`/`now`/`now_dt` are
  known (today's lines `:204-224`). From there, **each field is assigned at its existing computation site,
  not moved** — `ctx.surplus_w = surplus_w` right after `:287`, `ctx.ev_soc = ev_soc` after `:269`,
  `ctx.sun_is_up`/`ctx.sun_is_down` after `:321-322`, `ctx.low_tariff_active` after `:325-329`,
  `ctx.solar_reserve_active` after `:348-357`, `ctx.active_soc_limit` from the `SocGateResolver.resolve(...)`
  call (§3.3), `ctx.urgent` after `:473`, `ctx.monthly_peak_kw`/`ctx.effective_peak_limit_kw` from the
  `PeakDemandState.update(...)` call (§3.2) and the `resolve_effective_peak_limit` calls (`:246-250`,
  `:474-476`). No step is reordered; this is purely "also write it onto `ctx`" alongside each existing
  assignment. The disconnect/fault early returns keep constructing a `CycleResult` exactly as today.
- `_mode_desired_current`: becomes `self._mode_handlers[mode].desired_current(ctx, self._mode_state.get(mode))`,
  dropping its own `if/elif`.
- Step 7 (R3 clamp) and step 8 (C4 ceiling clamp) call sites, and `_peak_tracker`'s threading through step 7,
  are **not touched**.
- **`sensor.py`'s `MonthlyPeakSensor`** currently reads/writes `coordinator._peak_tracked_kw` and
  `coordinator._peak_tracked_month` directly (restore-state seeding on `async_added_to_hass`, and
  `extra_restore_state_data`/`extra_state_attributes`). These become `coordinator._peak_demand.tracked_kw`
  / `coordinator._peak_demand.tracked_month` — the same values, same restore/read semantics, just reached
  through the new object instead of the old fields. Missed in the first draft (the fields looked
  coordinator-private but aren't); found by fresh-agent review. This is the one place outside
  `coordinator.py`/`coordinator_cycle.py` this slice touches, and it is why plan Task 1.2 now includes an
  explicit sub-step for it (§5).

No entity, config key, adapter role, or domain event changes. `CycleResult` (the public return type) is
unchanged.

---

## 5. Testing (ADR-0009/0012 harness split)

All four new units are HA-free (no `hass.bus`/HA I/O) → **plain pytest**, in a new `tests/test_coordinator_cycle.py`:

- `PeakDemandState.update`: same-month accumulation (max of tracked vs. smoothed); month rollover resets
  both `tracked_kw` and the smoothing `window` (not just the tracked value) — the exact behavior
  `_run_cycle` already implements today (a rollover must reset the window too, or that cycle's "smoothed"
  reading would still partly reflect last month's raw samples), now unit-tested in isolation.
- `SocGateResolver.resolve`: first call always reports `changed=True` (mirrors today's `None` sentinel);
  an unchanged limit reports `changed=False`; a changed limit reports `changed=True` and updates the
  remembered value.
- Each `ModeHandler.desired_current`: delegates to its wrapped `modes/*.py` function with the right
  config/state, returns `(current, new_state)` unchanged from what that function returns — one test per
  mode, asserting against a **hardcoded expected current** anchored to the corresponding `tests/modes/`
  fixture's own expected value (not computed by re-calling the same wrapped function, which would only
  prove the wrapper calls *something*, not that it calls it correctly).
- `CycleContext`: constructible with defaults; no behavior to test beyond that (it is a data carrier).

**Regression**, HA harness (`tests/test_coordinator.py`, already exists — no new file, and
`tests/test_sensor.py` for the `MonthlyPeakSensor` restore path, §4): the full existing suite must pass
unchanged after the refactor, proving no observable-behavior drift. No new coordinator tests are added
for this slice — its whole point is that coordinator behavior is identical before/after. Given how easy
it is to accidentally touch the R3/C4 clamp region while wiring `ModeHandler` in (the exact mistake a
stale line-number reference caused in this spec's first draft), the regression pass explicitly includes
reading the post-refactor `_run_cycle` and confirming both clamp calls and `_peak_tracker`'s threading
are byte-for-byte where they were, not just running the test suite and trusting green.

---

## 6. Packaging

```text
custom_components/smart_charging/
  coordinator_cycle.py    # NEW — CycleContext, PeakDemandState, SocGateResolver, ModeHandler
                          #   Protocol + per-mode adapters (§3)
  coordinator.py           # _run_cycle delegates to the above; ten-step order (ADR-0006) and the
                          #   R3/C4 clamp separation unchanged; _peak_tracker untouched
  sensor.py                # MonthlyPeakSensor reads/writes coordinator._peak_demand.tracked_kw /
                          #   .tracked_month instead of the old _peak_tracked_kw/_peak_tracked_month
                          #   fields directly (§4) — same values, same restore semantics
```

`tests/` mirrors 1:1 (ADR-0002/0009): new `tests/test_coordinator_cycle.py` (plain pytest); no change to
`tests/test_coordinator.py`'s or `tests/test_sensor.py`'s file locations, only that both must keep
passing. `tests/test_coordinator.py`'s peak-headroom seeding helpers (e.g. `_seed_ample_peak_headroom`)
and the equivalent seeding in `tests/test_init.py`, `tests/test_solar_end_to_end.py`, and
`tests/test_captar_end_to_end.py` are updated to seed `coordinator._peak_demand`'s fields instead of the
removed ones — a mechanical rename at each seeding call site, not a behavior change to what's seeded.

---

## 7. Deliberately deferred

- Any behavior, entity, config, or event change — this slice is refactor-only.
- A general-purpose `CycleStep` pipeline (ADR-0012 Option B, rejected) — not revisited here.
- A fifth mode, or any new cross-cutting concern discovered later that doesn't fit these four units — a
  new decision at that time, per ADR-0012's own Consequences, not something this spec pre-answers.

**Sequencing note (resolved).** Task 5.3 (deadline/SOC management plan, issue #326 — wiring the real
`urgent` value and Auto's mode escalation into this same `_run_cycle` region) was flagged during review as
a possible in-flight collision. It is **not** in flight: issue #326 is closed and its PR (#377) already
merged to `main` before this branch was cut, so `urgent`/Auto-dispatch are already the real, final values
this design's §3.1 cites (`:473`, `:481`) — no rebase or landing-order coordination is needed.

---

## 8. Next step

This design feeds the `writing-plans` skill to produce the ordered, test-driven implementation plan
(`2026-07-27-coordinator-decomposition.md`). Build order: `coordinator_cycle.py` (the four units, each
test-first and independently green) → wire `coordinator.py` to delegate to them, one extraction at a time
(peak-demand, then SOC-gate, then mode dispatch, then the dry-run unification) → full regression pass
against the existing coordinator suite. No `custom_components/` code is written until the paired plan
exists and is approved.
