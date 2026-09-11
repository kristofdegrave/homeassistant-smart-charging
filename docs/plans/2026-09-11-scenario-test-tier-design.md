# Scenario/timeline test tier — plant simulator + cycle-invariant runner — design

**Date:** 2026-09-11
**Status:** draft (issue #998, epic #996, ADR-0037)
**Type:** implementation design (test-infrastructure slice — **not** a
`docs/design/project-plan.md` build slice; this spec derives from epic #996's work breakdown and
[ADR-0037](../adl/0037-scenario-timeline-test-tier.md), the same way a feature slice's design
derives from `project-plan.md`, and following the precedent set by
[`2026-08-17-real-perf-tests-design.md`](2026-08-17-real-perf-tests-design.md))

This document is the paired implementation spec ADR-0037 calls for. ADR-0037 decided *that* the
tier exists, where a contributor puts a test, and what a passing scenario is allowed to mean. It
deliberately left three questions open for this spec, all three of which are settled below: how
simulated time relates to the coordinator's update interval (§4), how the simulator's outputs
reach HA state (§5.4), and where a scenario file physically lives (§10).

**Almost test-infrastructure only.** One real `custom_components/` change ships in this slice:
issue #992's fix, routing the C4 grid-supply-ceiling clamp through the already-debounced
`baseline_w` (§9). Everything else — the plant simulator, the invariant runner, the first
scenario — is test-only code that product code takes no dependency on.

---

## 1. Why this slice

`tests/test_captar_end_to_end.py:207` seeds `net_w=3600.0, charger_w=0.0` one line after the
charger was commanded 16 A (≈3680 W) — a world in which the charger draws nothing while
charging. R3 genuinely binds in that test, and the test is correct for what it asserts, but the
two readings are hand-picked in the *conservative* direction: a charger power reading that is
stale-**low** overstates the household baseline and makes the clamp under-command. The real
defect class needs the opposite: after a current step-down `charger_w` is stale-**high** while
`net_w` has already dropped, so the derived `baseline_w = net_w - charger_w` swings negative and
*inflates* headroom.

No seeded reading pair produces that, because the author picks both numbers and nobody encodes
a lag they have not thought of. That is the structural gap, in one line.

Two instances of the class are already on record. Issue #990 (R3's peak clamp) was diagnosed by
a human overlaying two sensors' history on a live install; issue #992 (C4's grid-supply-ceiling
clamp, which re-derives `net_w - charger_w` itself at `engines/grid_safety.py:30`) was found by
a reader of #990's diff, not by any test. ADR-0037's Context weighs that cost and decides the
tier; this spec builds the minimum that reproduces the class from a scripted *world* rather than
from scripted readings, and lands #992's fix through it.

---

## 2. Scope

| Piece | This slice |
| --- | --- |
| Plant simulator — charger lag, meter derivation from true draw, scheduled exogenous events | **In scope** (§5) |
| Plant simulator — SOC integration | **Deferred** (§3) |
| Scenario runner — one virtual clock driving `coordinator.async_refresh()` per tick | **In scope** (§4, §6) |
| Invariant runner — per-cycle checks, fail-fast, contextual failure report | **In scope** (§7) |
| Invariant set | **Exactly one ships**: INV-1, headroom against true draw (§7.1) |
| Bounded-oscillation invariant | **Deferred** (§7.3) |
| First scenario | **Exactly one ships**: Manual + Power, commanded-current step-down (§8) |
| Issue #992's product fix (C4 reads the debounced baseline) | **In scope** (§9) |
| File placement + harness classification | **In scope** (§10) |
| Runtime budget (pytest marker / separate CI job) | **Deferred, with a named trigger** (§11) |

### Explicitly out of scope

- **Rebuilding per-mode coverage.** `test_solar_end_to_end.py`, `test_captar_end_to_end.py` and
  `test_deadline_soc_management_end_to_end.py` stay exactly as they are — not migrated, not
  retrofitted onto the simulator, and `_cycle_from_feedback` is left in place. ADR-0037's
  Decision says so outright: their single-engine focus is what makes their failures diagnostic.
- **UC04/Power tier-2 coverage.** Power has no full-stack end-to-end suite of its own; that gap
  is a conventional seeded-reading suite belonging beside the three existing ones, tracked
  separately (issue #1003), not folded in here.
- **Auto-profile paths.** Under `Auto` the active mode becomes an output of the timeline rather
  than a fixed variable, which is a different and larger problem; tracked as its own epic
  (#1004), one path per issue, after this lands.
- **Scenarios for UC01..UC12.** Filed per use-case against this plan once it is approved.

---

## 3. Deliberate deferrals

**SOC integration is deferred.** Issue #998 lists an EV model whose state of charge integrates
delivered energy over simulated time. No path in this slice charges toward a SOC limit — the
only scenario is Power mode against a grid ceiling, with `ev_soc` held constant and well below
the active limit — so building the integrator now would be an unexercised model, which is
exactly the speculative work ADR-0037's wrong-simulator risk warns against. `ev_soc` is a plain
scenario-scripted world field until a scenario genuinely charges toward a limit; the first
deadline or SOC scenario adds the integrator, driven by its own failing test.

**No protective-device model.** The plant does not trip a fuse. A scenario that drives true
import above the grid supply ceiling is demonstrating exactly what would trip a real one — which
is the point of C4 and the point of INV-1 — so modelling the trip would hide the violation the
invariant exists to catch.

**No solar production curve abstraction.** The meter derivation takes a `solar_w` world field
(§5.2) because `net_w` is derived from true draw *against* solar and house load; a production
curve is then just a sequence of scheduled events setting that field (§5.3), not separate
machinery. The first scenario holds it at 0 W throughout.

**Bounded oscillation** — see §7.3, which records the reasoning rather than deferring it
silently.

---

## 4. Time model — one virtual clock, two faces

**The simulator owns one virtual clock.** Each tick advances it by the coordinator's configured
update interval (`CONF_CONTROL_INTERVAL_S`, default 10 s), and presents that one advance through
both of the clocks the control cycle actually reads:

1. **`hass.loop.time()`** — monkeypatched to return the runner's virtual monotonic value.
   `coordinator.py:535` reads it once per cycle (`now = self.hass.loop.time()  # injected, not
   read inside modes/engines`) and threads it onto `CycleContext.now`, which is what every mode
   state machine's hold/cooldown/debounce timer compares against. **freezegun does not control
   this clock.** That is why `tests/test_captar_end_to_end.py:213` mutates `peak_grace_min` to
   0 instead of waiting, why the same suite zeroes an `ActiveCooldown`'s duration in place, and
   why the solar cooldown test relies on a 2-minute cooldown simply not elapsing during a fast
   test. A tier whose whole premise is a *timeline* cannot keep borrowing those workarounds.
2. **`dt_util.now()`** — moved by `freezegun` (the `freezer` fixture) in lockstep with the same
   advance. `coordinator.py:417` reads it at the top of `_run_cycle` for the departure-deadline
   resolution and the monthly-peak month rollover.

Both must advance together, by the same delta, on the same tick, or a scenario that runs long
enough to cross a cooldown would cross it on one clock and not the other.

### 4.1 Tick sequence

Per tick `n`:

1. Advance the virtual monotonic clock by `interval_s`; `freezer.move_to(start + n × interval_s)`.
2. Apply any exogenous events scheduled for cycle `n` (§5.3).
3. Advance the plant: true charger draw follows the command issued at the previous tick; the
   reported `charger_power` follows true draw by the configured sensor lag (§5.1).
4. Write the plant's reported readings into `hass.states` (§5.4).
5. `await coordinator.async_refresh()`, then `await hass.async_block_till_done()`.
6. Read the commanded current off the observation surface (§6) and hand it back to the plant as
   the charger's new setpoint.
7. Check every registered invariant against this cycle's observation (§7).

Step 6 after step 5 is what makes the loop closed: a command issued at tick `n` physically takes
effect at tick `n+1`, exactly as a real charger's setpoint does.

### 4.2 Known coupling: monkeypatching a loop-internal clock

`hass.loop.time` is asyncio's own scheduling clock, not an application-level one. Patching it is
the only way to move `CycleContext.now`, since the coordinator reads it inline, but it means
asyncio's timer handles are compared against a clock the test controls. Recorded here as a known
coupling, with three mitigations the runner implements and one test that guards them:

- **The virtual clock starts at 0.0**, far below the real loop's monotonic value at setup time.
  Every handle scheduled during config-entry setup therefore sits in the virtual far future and
  cannot fire mid-scenario. The patch is installed *after* `async_setup` completes, so setup
  itself schedules against the real clock.
- **The coordinator's own auto-refresh is unscheduled** (`coordinator.update_interval = None`
  plus cancelling the pending refresh handle) before the first tick. The scenario tier owns the
  cycle cadence; every cycle in a scenario is one the runner drove deliberately. Without this, a
  jumping loop clock could fire `DataUpdateCoordinator`'s own timer and insert cycles the runner
  never counted.
- **`await hass.async_block_till_done()` after every refresh**, so anything that does fire
  settles at a controlled point in the tick rather than mid-assertion.
- **A guard test** (T3) asserts the runner drives exactly `N` cycles for `N` ticks — the canary
  that catches a stray scheduled refresh if any of the above stops holding.

### 4.3 Rejected alternative

Driving the real `async_track_time_interval` tick with `freezer` + `async_fire_time_changed`
(the idiom `tests/test_notifications_end_to_end.py` uses for M3's dispatch) is the more
idiomatic HA approach and needs no monkeypatch — but it moves `dt_util.now()` only. Every
mode timer would stay frozen at the same `hass.loop.time()` value for the whole run, so a
scenario could never cross a cooldown, a hold, or R3's grace period. That is precisely the
limitation this tier exists to lift.

---

## 5. Plant simulator

A model of the physical world a scenario scripts *instead of* scripting readings.

### 5.1 Charger

Two independent lags, both configurable in cycles:

| Quantity | Model |
| --- | --- |
| True draw | `true_draw_w[n] = commanded_a[n − response_lag] × voltage` — the charger obeys a new setpoint after `response_lag` cycles (default 1: a command issued this tick is drawn next tick). |
| Reported `charger_power` | `charger_w[n] = true_draw_w[n − sensor_lag]` — the slow-polled power sensor reports a true draw from `sensor_lag` cycles ago (default 1). |

`true_draw_w` is the simulator's ground truth and is **never** written to `hass.states`. This
separation is the whole mechanism: with `sensor_lag = 1`, a step-down leaves `charger_w`
reporting the *previous, higher* draw for one cycle while the meter (§5.2) has already followed
the drop — which is #990/#992's defect shape, produced by the model rather than by a scenario
author who knows the defect exists.

A permanent one-cycle sensor lag against a zero-lag meter is the deliberate **worst case**. Real
hardware's mismatch is partial (a Modbus poll returns a value from somewhere inside the last
interval); the worst case is what produces the observed defect, so it is what the first scenario
uses. `sensor_lag` is a per-scenario knob, not a constant, so a later scenario can model a
gentler sensor.

### 5.2 Meter

`net_w[n] = house_load_w[n] − solar_w[n] + true_draw_w[n]`, reported with no lag.

This closes the loop `commanded current → true draw → net_w → next cycle's clamp headroom` for
real, generalizing what `tests/test_solar_end_to_end.py::_cycle_from_feedback` does by hand for
one mode and one suite. It also defines the tier's ground truth:

> **True baseline** = `house_load_w − solar_w` — the household load the charger is competing
> with, with the charger's own draw removed exactly rather than subtracted via a lagging sensor.

The coordinator structurally cannot compute this: its only route to the same quantity is
`net_w − charger_w`, and `charger_w` lags. That asymmetry is what lets INV-1 be an oracle rather
than a mirror of the code under test (ADR-0037's invariant-oracle rule).

### 5.3 Scheduled exogenous events

A scenario registers world changes on the same timeline: `at_cycle=N` applies a set of
world-field overrides (`house_load_w`, `solar_w`, `status`, `ev_soc`, `grid_voltage`) from cycle
`N` onward. Plug/unplug is a `status` change, a tariff-window or departure change is a world
field like any other, and a solar production curve is a sequence of these — one mechanism, not
several. A sensor fault is modelled by setting a reading to `None`/unavailable; the first
scenario schedules exactly one event and exercises no fault path.

### 5.4 How the plant reaches HA state

**Through `tests/helpers.py`'s existing `seed_charger_states`**, not a replacement path. ADR-0037
lists this as an open question; the answer is that the seeding helper is already the one place
that knows which five/six entity ids a cycle reads, and the difference between the tiers is
*where the numbers come from*, not how they land in `hass.states`. The plant computes the
readings; `seed_charger_states` writes them. A scenario never calls `seed_charger_states` itself.

The one tier-2 helper a scenario deliberately does **not** use is `seed_ample_peak_headroom`. Its
own docstring says it "keeps R3's clamp out of the way of tests that exercise unrelated
behavior" — engine-muting, which is the tier-2 idiom ADR-0037's placement rule contrasts tier 3
against. A scenario seeds a *representative* monthly peak instead, via the same public
`coordinator.seed_monthly_peak(...)` boundary: the household's billing history is part of the
world being scripted, and the value is chosen to be plausible for the installation, not to be
large enough to neutralize a clamp.

---

## 6. Observation surface

Invariants and scenario-intent assertions read exactly three things:

1. **Captured `number.set_value` service calls** —
   `tests/helpers.py::capture_charger_current_writes`. `SmartChargingCoordinator._write` writes
   unconditionally every cycle (`adapters/numeric.py:48` calls the service every time), so this
   is a one-entry-per-cycle record of the commanded current. The runner takes the entries added
   during a tick and carries the previous value forward if a cycle added none, which is also
   physically faithful: a charger holds its last setpoint.
2. **The coordinator's public attributes** — `coordinator.data` (a `CycleResult`:
   `commanded_current`, `fault`, `active_mode`, `effective_peak_limit_kw`, …) and the owned
   diagnostic entities' HA states.
3. **The simulator's own ground truth** — the world fields and `true_draw_w`.

**Nothing hooks the private `_step_*` methods, and `CycleContext` is not captured.** ADR-0037's
rationale is the reason: true instantaneous charger draw is exactly what the coordinator does not
have, and an assertion computed from the coordinator's own intermediate values is a mirror of the
code under test rather than an oracle for it. `CycleContext` is also not retained after a cycle —
it is a per-cycle carrier that `_run_cycle` mutates and drops, so there is nothing to capture even
if the rule allowed it.

One value is read from the coordinator rather than from ground truth: R3's per-cycle
`effective_peak_limit_kw` (§7.1), because it is resolved from the monthly-peak tracker's own
history rather than from a world field. That is an *input bound* the invariant judges against,
not the *value being judged* — the judged quantity (commanded current) and the quantity that
makes the judgement hard (true baseline) both come from outside the coordinator, which is what
ADR-0037's rule requires.

---

## 7. The invariant set

### 7.1 INV-1 — headroom is never overshot against true charger draw

> On every cycle, the current the coordinator commands, drawn in full against the **true**
> household baseline the simulator knows (`house_load_w − solar_w`), must not push total grid
> import above either enforced ceiling:
>
> - **C4** — `true_baseline_w / voltage + commanded_a ≤ ceiling_a − offset_a`, always;
> - **R3** — `true_baseline_w + commanded_a × voltage ≤ effective_peak_limit_kw × 1000 −
>   safety_margin_w`, while R3 is in force.

This single invariant covers **R3 and C4 together**, which is exactly ADR-0037's stated value for
the first one: not a reproduction of the instance R3 already handles, but the property that holds
across *both* clamp call sites and would fail for a third if one appears.

**Why it is an oracle and not a mirror.** Production computes its headroom from
`net_w − charger_w` — lagged sensor readings, debounced at R3 and (before §9) raw at C4. INV-1
computes the same physical quantity from `house_load_w − solar_w`, which no production code path
can see. The two agree in steady state and diverge exactly when a reading is stale, which is the
defect class.

**Which cycle's baseline.** INV-1 judges `commanded_a[n]` against `true_baseline_w[n]` — the true
baseline behind the readings the coordinator acted on *this* cycle. It deliberately does not
judge against `true_baseline_w[n+1]`: an exogenous load change between two cycles is not
something the cycle that preceded it could have known, and the next cycle's own INV-1 check is
what covers it.

**Narrow, named exemptions**, each pinned to a requirement rather than to the code:

- **R3's grace-period hold** (R3 AC5, R11 AC1). When the commanded current equals the charger
  minimum and the mode requested at least the minimum, R3 deliberately holds at the minimum
  rather than cutting — "a momentary breach does not stop charging". The R3 half of INV-1 is
  not asserted on such a cycle. **C4 gets no such exemption**: R11 AC1 names it as "a hard
  safety limit that cuts immediately", and `coordinator.py:1068`'s own docstring calls it "never
  skippable, no opt-out of any kind".
- **R3 not in force** (R17 AC2, R18). With the CapTar capability absent, or with `Power`'s
  peak-protection option disabled, R3 does not run at all and C3 says net import is bounded by
  C4 alone — so the R3 half is not asserted. The first scenario runs in exactly this
  configuration (§8), but the exemption is encoded now rather than when the catalog first needs
  it, because an invariant that misfires is worse than one that is absent.
- **Whole-ampere flooring.** Both clamps floor their headroom to a whole ampere, which errs
  conservative. INV-1 therefore compares against the real-valued ceiling with no slack in the
  permissive direction.

### 7.2 The runner's contract

- **Every registered invariant runs on every cycle of every scenario.** That is what makes a
  newly understood bug class re-checked everywhere at once, which is ADR-0037's Option A Pro.
- **Fail fast on the first violation.** Once an invariant has failed, the world state after it is
  the product of a command that should never have been issued, so later cycles are not
  independent evidence.
- **The failure report is the deliverable, not the assertion.** A bare `assert False` on cycle 63
  of 96 is not actionable (issue #998's own wording). The runner raises a single
  `AssertionError` carrying a formatted table of the violating cycle and the preceding few,
  each row showing: cycle index, virtual monotonic time and wall-clock time, world fields
  (`house_load_w`, `solar_w`, `status`), `true_draw_w`, `true_baseline_w`, the *reported*
  `net_w`/`charger_w`, the commanded current, `active_mode`, the fault flag, and both headroom
  figures — the one the invariant computed from ground truth and the one the coordinator could
  have computed from the readings it was given. Side by side, those two columns name the cause.

### 7.3 Why bounded oscillation is deferred

ADR-0037 lists bounded oscillation among the properties that qualify as invariants, and issue
#998 lists it as a candidate. It does not ship here.

The decision's stated reason is that the only scenario in this slice is Power mode, which holds a
fixed target and so structurally cannot oscillate — asserting it against this scenario would be
the tautological assertion ADR-0037's oracle rule forbids. That is right about the **mode**:
`modes/power.py::desired_current` returns the configured target whenever the car is present, full
stop, and `profiles/manual.py::ManualPolicy` passes the selection straight through, so nothing in
the mode-selection or set-point path can hunt.

It is worth recording that it is not the whole story about the **commanded** current. Under a
binding C4 with a one-cycle charger-power lag, the command can still flip between cycles — the
plant's own worked timeline (§8) settles at 0 A, but a scenario that stepped the household load
back *down* would show a repeating flip as the debounce alternately holds and commits. So the
sharper reason the invariant is deferred is this: a bounded-oscillation invariant needs a
threshold — no more than *N* set-point direction flips per *M* cycles — and one scenario, whose
flips are an artifact of the deliberately worst-case lag model, cannot calibrate *N* or *M*.
Shipping it now would encode an arbitrary number as a system property.

It becomes worth writing when a **Solar** feedback path exists to threaten it: there the
set-point is a continuous function of a reading the charger's own draw feeds back into, so a flip
count is a real property of the control law rather than of the lag model. Recorded as a follow-up
in §13.

---

## 8. The first scenario — Manual + Power, commanded-current step-down

**One scenario ships.** `ManualPolicy` is a pass-through of the user's selection, so mode
selection is a fixed variable, and Power holds a constant target — making this simultaneously the
simplest possible closed loop and the cleanest reproduction of the stale-`charger_power` class.
It validates the simulator's lag model against an already-diagnosed real defect before anything
speculative is built on it, which is ADR-0037's own stated mitigation for the wrong-simulator
risk.

### 8.1 The world

| Setting | Value | Why |
| --- | --- | --- |
| Profile / mode | `Manual` / `Power`, seeded on `select.smart_charging_profile` and `select.smart_charging_mode` | Mode selection is a fixed variable (`ManualPolicy`) |
| `power_respect_peak` (R17) | `False` | Puts the world in C3's case (b): C4 is the **only** import limit in force. This is a user-facing configuration option, part of the world being scripted — not a harness neutralization like `seed_ample_peak_headroom` |
| CapTar capability (R18) | present | R17's option "only ever has an effect while the CapTar capability is present"; with it absent the scenario would be exercising a different clause |
| `grid_ceiling_a` / `grid_safety_offset_a` | 25 A / 2 A → **23 A enforced** = 5290 W | Defaults |
| `min_current` / `max_current` / Power target | 6 A / 16 A / 16 A | Defaults; target at max so a clamp is the only thing that can reduce it |
| `nominal_voltage`, `grid_voltage` | 230 V | Defaults |
| `smoothing_window` (R10) | **default (4), not 1** | Unlike the tier-2 suites, which set it to 1 to isolate raw readings, tier 3 leaves R10 at its real default: both clamps read raw by construction (R3 AC3, C4), so the smoothing window is provably irrelevant here and the scenario is more faithful for leaving it alone |
| Monthly peak seed | representative, via `coordinator.seed_monthly_peak` | §5.4 — world history, not engine-muting |
| `ev_soc` | 50 %, constant (active limit 80 %) | SOC integration is deferred (§3) |
| `status` | `Charging`, constant | No plug/unplug in this scenario |
| `house_load_w` | 1000 W, stepping to 5000 W at cycle 3 | The one scheduled exogenous event |
| `solar_w` | 0 W throughout | No solar capability in this world |
| charger `sensor_lag` / `response_lag` | 1 / 1 cycle | The worst case that produces the defect (§5.1) |

The plant is primed so cycle 0 starts in a settled state: the charger is already commanded and
drawing 16 A, and the reported `charger_power` already agrees with it. Priming matters — without
it the scenario's first cycles would be a start-up transient of the lag model rather than the
steady state the step-down disturbs.

Every number is physically coherent: the settled state draws 20.35 A of a 25 A supply, and the
4000 W household step (an oven, a heat pump) takes the *baseline* alone to 21.74 A — still under
the 23 A enforced ceiling and under the fuse.

### 8.2 The timeline (8 cycles), and what C4 sees

`V = 230 V`, enforced ceiling `23 A = 5290 W`, house load `H`.

| Cycle | Event | True draw | Reported `net_w` | Reported `charger_w` | Derived baseline (C4, **raw**) | C4 headroom | Commanded | True import |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0–2 | settled, `H` = 1000 W | 3680 W | 4680 W | 3680 W | 1000 W | `floor(23 − 4.35)` = 18 A | **16 A** | 20.35 A ✓ |
| 3 | `H` → 5000 W | 3680 W | 8680 W | 3680 W | 5000 W | `floor(23 − 21.74)` = 1 A | **0 A** (E8 floors a sub-minimum result to a stop) | 21.74 A ✓ |
| 4 | — | 0 W | 5000 W | **3680 W (stale)** | **1320 W** | `floor(23 − 5.74)` = 17 A | **16 A** | **37.7 A ✗** |
| 5–7 | — | (follows the command) | — | — | — | — | — | — |

Cycle 4 is the defect, in one row: the charger has already stopped, the meter has already
followed, and the power sensor still reports the pre-step-down draw — so the derived baseline
drops by 3680 W, headroom is inflated by 16 A, and C4 hands the charger back the full 16 A on top
of a 21.74 A household baseline. **INV-1 fails at cycle 4.**

With §9's fix, C4 reads the debounced `baseline_w` instead. `debounce_baseline_w` accepts a
*higher* baseline immediately and requires `BASELINE_DEBOUNCE_CYCLES` (2) consecutive readings
before accepting a *lower* one, so at cycle 4 it still reports 5000 W, headroom stays at 1 A, E8
floors it to a stop, and the timeline settles at 0 A with true import at the household's own
21.74 A. INV-1 then holds on all eight cycles.

### 8.3 Scenario-intent assertions

Beyond INV-1 running on every cycle, the scenario asserts what it is *for*:

- Cycles 0–2 command **16 A** — Power holds its configured target while C4 is non-binding.
- Cycle 3 commands **0 A** — the commanded-current step-down, caused by a clamp reacting to a
  real world event rather than by a hand-picked reading.
- Cycle 4 commands **0 A, not 16 A** — named in the test as the #992 regression: the stale
  `charger_power` reading must not inflate C4's headroom for even one cycle.
- Cycles 5–7 stay at **0 A** — the timeline settles rather than flapping.

The timeline deliberately ends in the settled state rather than stepping the household load back
down. The recovery half exercises the debounce's accepted trade-off (one extra cycle of
understated headroom) and, under this worst-case lag model, a repeating command flip — which is
the deferred bounded-oscillation invariant's territory (§7.3), not this scenario's.

---

## 9. The product change: issue #992

`engines/grid_safety.py::clamp_to_ceiling` re-derives `baseline_w = net_w - charger_w` itself
(`grid_safety.py:30`) from the raw readings, while R3's `apply_peak_clamp` reads the
already-debounced `ctx.baseline_w` that `coordinator.py:443` computes once per cycle. Route C4
through that same debounced value:

- `clamp_to_ceiling(desired_current, baseline_w, voltage, ceiling_a, offset_a)` — the `net_w`
  and `charger_w` parameters are replaced by the single `baseline_w` the caller resolves, exactly
  as `apply_peak_clamp` already takes it.
- `coordinator.py::_apply_grid_ceiling_clamp` passes `baseline_w=ctx.baseline_w`.
- `coordinator_cycle.py`'s `CycleContext.baseline_w` field comment, which currently records that
  "`_apply_grid_ceiling_clamp` (C4) keeps reading the raw `ctx.net_w`/`ctx.charger_w` … tracked
  separately (issue #992)", is updated to say both clamps now read it.

**This does not merge the clamps.** ADR-0006's rule is that steps 7 and 8 stay separate methods
and separate call sites, so the R17 opt-out can only ever skip step 7 — `_apply_peak_clamp`'s own
`if self.active_mode == MODE_POWER and not self._config.power_respect_peak: return desired` guard
stays exactly where it is, and `_apply_grid_ceiling_clamp` gains no conditional of any kind.
Sharing an *input reading* is not merging a *call site*; the two clamps already share
`ctx.net_w`, `ctx.charger_w` and `ctx.voltage`. Issue #992's own Direction section says the same.

**Why no ADR is opened for this.** ADR-0006's Consequences require a new ADR for "a change to
step order or to which reading (raw/smoothed) a step consumes". Three reasons that clause does
not bite here, recorded so a reviewer can disagree with the reasoning rather than guess at it:

1. The clause exists to protect one specific distinction — that the clamps must not silently
   start reading R10's *smoothed* (lagged) net power, which is the failure ADR-0006's Context
   names. The debounced baseline is derived from the same raw readings, is strictly more
   conservative than the raw value, and is never the smoothed channel.
2. Issue #990 made the identical change to step 7 without an ADR, and ADR-0037's Consequences
   already record C4's alignment as expected follow-up ("R3's clamp reads a debounced
   `baseline_w` … while C4's `clamp_to_ceiling` still re-derives its own").
3. CLAUDE.md's domain/business-rule carve-out covers which reading a clamp's formula consumes;
   ADR-0006's actual *structural* rule — two call sites, no shared opt-out — is preserved
   unchanged.

---

## 10. File placement and harness classification

```text
tests/scenarios/
  __init__.py
  plant.py                      — the plant simulator (§5)
  invariants.py                 — the Invariant protocol and INV-1 (§7)
  runner.py                     — virtual clock, tick loop, invariant checking, failure report (§4, §7.2)
  test_plant.py                 — the plant's own tests
  test_runner.py                — the runner's own tests
  test_invariants.py            — INV-1's own tests
  test_power_step_down.py       — the first scenario (§8)
```

**`tests/conftest.py` needs no functional change.** `_is_pure_logic_test` classifies by directory
and filename: a new directory that is not in `_PURE_DIRS` and whose files are not in
`_PURE_FILES` is automatically treated as HA-harness. That is the correct answer here —
ADR-0037's Decision says tier 3 runs in the **same** `pytest-homeassistant-custom-component`
harness as tier 2, because it drives the real config entry and real coordinator cycles and could
not run anywhere else. What separates the tiers is scope and oracle, not harness.

The plant's and the invariant's own tests need no `hass` fixture in substance, and they are
deliberately **not** added to `_PURE_FILES`. ADR-0037's placement rule exists so a contributor
knows where a test goes; "everything in `tests/scenarios/` is tier 3" is a rule that survives
being read quickly, and a split-classification directory is not. The cost is a few milliseconds
of harness setup per test, which is the right trade.

**On ADR-0002's `tests/`-mirrors-the-package layout** (restated as a live rule in ADR-0009's
Consequences and again in ADR-0010, ADR-0015 and ADR-0019): it has no slot for a tier that
mirrors no package. This is a precedent to cite, not a contradiction to resolve — the existing
`test_*_end_to_end.py` suites already sit outside that mirror, for the same reason (they test a
cross-cutting behaviour, not a module). ADR-0037's own Consequences flag that a placement rule
"whose whole purpose is answering *where does this test go*" should not leave the literal
directory unstated; `tests/scenarios/` is that answer.

`tests/conftest.py`'s module docstring, which enumerates the taxonomy for a contributor reading
it, gains one line recording that `tests/scenarios/` is ADR-0037's tier 3 and is HA-harness by
design rather than by omission.

---

## 11. Testing approach, and what each piece is tested by

The tier's own machinery is code that can be wrong, and ADR-0037 names "a wrong simulator" as a
new failure mode with no analogue in the existing tiers. Each piece therefore gets its own tests,
built test-first, before the scenario that depends on it:

| Piece | Tested by | Tier |
| --- | --- | --- |
| Plant: charger lag, meter derivation | `tests/scenarios/test_plant.py` — reported `charger_w` lags true draw; `net_w` tracks true draw against house/solar; priming settles | 3 |
| Plant: scheduled events | `tests/scenarios/test_plant.py` — an event at cycle `N` takes effect from cycle `N` and persists | 3 |
| Runner: clock + cadence | `tests/scenarios/test_runner.py` — both clocks advance by the interval per tick; exactly `N` cycles for `N` ticks (§4.2's canary) | 3 |
| Runner: invariant checking + report | `tests/scenarios/test_runner.py` — a stub always-failing invariant raises on the first violating cycle, and the message carries the preceding cycles | 3 |
| INV-1 | `tests/scenarios/test_invariants.py` — overshoot flagged, compliant cycle not flagged, both exemptions honoured, whole-ampere flooring given no slack | 3 |
| The scenario | `tests/scenarios/test_power_step_down.py` | 3 |
| §9's C4 fix | `tests/engines/test_grid_safety.py` (new signature, debounced-baseline behaviour) | 1 — plain pytest |
| §9's C4 fix, through the real cycle | `tests/test_coordinator.py` — a coordinator-cycle regression mirroring #990's, for `commanded_current` against `grid_ceiling_a`/`grid_safety_offset_a` | 2 — HA harness |

**Runtime budget.** ADR-0037 flags suite runtime as a cost this decision knowingly incurs. One
scenario of eight cycles is negligible, so **no pytest marker and no separate CI job ship in this
slice**. The deferral gets a named trigger rather than an open end: revisit when
`tests/scenarios/` passes roughly six scenarios, or when it accounts for more than about a tenth
of the suite's wall-clock — whichever comes first. Either is a `testing` issue at that point, not
a silent drift.

---

## 12. What this slice does not claim

- It does not catch **requirement drift** (#754/#755/#757): a scenario written from a stale
  understanding of a requirement is equally stale. Epic #996 says so, and this spec inherits it.
- It does not replace the three tier-2 end-to-end suites. A scenario failure says *the system*
  misbehaved; a Solar end-to-end failure says *Solar* misbehaved, and both questions still need
  answering.
- One scenario covering one mode is one scenario. The tier's value is realized as the catalog and
  the invariant set grow; what ships here is the harness plus the proof that it reproduces a real
  defect.

---

## 13. Follow-ups this plan records

Filed as `testing` issues **once this plan is approved and merged** — per
[idea-to-issues.md](../reference/idea-to-issues.md) step 4, each needs the anchored
`Plan: docs/plans/2026-09-11-scenario-test-tier.md#T<n>` line that only an approved plan can
provide, so filing them earlier would file them wrong. Filing them is part of finishing issue
#998; implementing them is separate work. Each is appended to epic #996.

1. **Bounded-oscillation invariant**, once a Solar feedback path exists to threaten it — §7.3
   has the reasoning and the calibration problem to solve.
2. **#974 — a cooldown surviving a mode switch.** R11 AC4 is explicit that a cooldown is scoped
   to the stop that started it, not to the mode active at the time; the scenario tier's virtual
   clock (§4) is what makes a cooldown actually elapse in a test.
3. **#546 — a latch resetting per occasion rather than per reload.**
4. **#648 — `adapter_readings_at` not advancing on a fault cycle.** Both fault early-returns in
   `_run_cycle` deliberately hold the prior timestamp; a scenario with a scheduled sensor fault
   (§5.3) is the natural home for the standing check.

One further follow-up is **not** a `testing` issue and is created by ADR-0037 rather than by this
spec: `.claude/skills/write-tests/SKILL.md` (its frontmatter description and its "Choose the
harness first (ADR-0009)" section) and `docs/reference/definition-of-done.md`'s "Tests green"
bullet both state the harness split as two-way, and go stale the moment this tier lands.
ADR-0037's Consequences call for a `workflow` issue for that pair, reviewed by
`workflow-reviewer`; it is recorded here so it is filed alongside the tasks above rather than
lost between the two documents.
