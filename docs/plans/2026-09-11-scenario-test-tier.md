# TDD plan: scenario/timeline test tier — plant simulator + cycle-invariant runner (#998)

Derived from [`2026-09-11-scenario-test-tier-design.md`](2026-09-11-scenario-test-tier-design.md).
Test-infrastructure slice from epic #996 and [ADR-0037](../adl/0037-scenario-timeline-test-tier.md)
— **not** a `docs/design/project-plan.md` build slice (same provenance shape as
[`2026-08-17-real-perf-tests.md`](2026-08-17-real-perf-tests.md)).

**Goal:** land the scenario tier's two reusable pieces (plant simulator, invariant runner), the one
invariant and the one scenario that prove them, and the issue #992 product fix that scenario
unblocks.

**Model:** per CLAUDE.md, T1–T6 are `testing` work and T7 is `development` work — execute both on
**Sonnet**, via the `develop-task` skill, one task per issue and one issue per PR.

**Test boundary (ADR-0009 as extended by ADR-0037):** everything under `tests/scenarios/` is
**tier 3 / HA harness**, by directory, with no `tests/conftest.py` `_PURE_FILES` registration —
design doc §10 has the reasoning. T7 is the only task that touches other tiers: `tests/engines/`
is tier 1 (plain pytest) and `tests/test_coordinator.py` is tier 2 (HA harness).

**No `custom_components/` change before T7.** T1–T6 are test-only.

---

## Conventions used throughout

- **Named constants, no magic strings** (CLAUDE.md) — canonical status strings come from
  `const.py` (`STATE_CHARGING`, `STATE_CONNECTED`), never re-typed.
- `git commit --author="Claude <noreply@anthropic.com>"` with the trailer
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- Re-check `git branch --show-current` before every commit.
- Both `ruff check .` and `ruff format --check .` before each commit.
- Commit prefix `T<n>:` matching the issue's anchored `Plan:` line.
- Every task: failing test first, minimal implementation, green, commit.

---

## T1 — Plant simulator: charger lag and meter derivation

**ADR honored:** ADR-0037 (the tier and its placement rule). **Test boundary:** tier 3 / HA
harness, `tests/scenarios/test_plant.py`.

**Files:**
- Create: `tests/scenarios/__init__.py` (empty, matching `tests/engines/__init__.py` etc. —
  `tests.scenarios.*` must be importable the way `tests.helpers` already is)
- Create: `tests/scenarios/plant.py`
- Create: `tests/scenarios/test_plant.py`

**Failing tests first** (`tests/scenarios/test_plant.py`):

- `test_true_draw_follows_the_command_after_the_response_lag` — with `response_lag_cycles=1`, a
  command of 16 A issued on cycle `n` leaves `true_draw_w` unchanged on cycle `n` and equal to
  `16 × 230` on cycle `n+1`.
- `test_reported_charger_power_lags_true_draw_by_the_sensor_lag` — with `sensor_lag_cycles=1`,
  the reported `charger_w` on cycle `n` equals `true_draw_w` on cycle `n−1`; after a step-down to
  0 A the reported value is still the *previous, higher* draw for exactly one cycle (design doc
  §5.1 — this is the property the whole tier rests on).
- `test_net_power_is_derived_from_true_draw_house_load_and_solar` —
  `net_w == house_load_w − solar_w + true_draw_w`, checked with solar at 0 W and at a non-zero
  value.
- `test_true_baseline_excludes_the_chargers_own_draw_exactly` — `true_baseline_w ==
  house_load_w − solar_w` regardless of what the charger is drawing or what the sensor reports;
  it diverges from the derived `net_w − charger_w` exactly on a lagged cycle. This is the
  ground-truth property INV-1 is built on (design doc §5.2).
- `test_priming_starts_the_plant_in_a_settled_state` — a plant primed at 16 A reports a
  `charger_w` that already agrees with `true_draw_w` on cycle 0, so a scenario's opening cycles
  are steady state rather than a start-up transient of the lag model (design doc §8.1).

**Implementation** — `tests/scenarios/plant.py`:

- A `WorldState` dataclass: `house_load_w`, `solar_w`, `status`, `ev_soc`, `grid_voltage`.
- A `PlantConfig` dataclass: `voltage`, `response_lag_cycles` (default 1), `sensor_lag_cycles`
  (default 1).
- A `Plant` class holding the command and true-draw histories, with:
  - `apply_command(amps)` — record the current the coordinator just commanded.
  - `advance()` — move one cycle; true draw follows the command history at `response_lag_cycles`.
  - `true_draw_w` / `true_baseline_w` properties — ground truth, never written to `hass.states`.
  - `readings()` — the reported `net_w`, `charger_w`, `status`, `ev_soc`, `grid_voltage` a cycle
    will see.
  - a priming argument on construction that seeds the command and true-draw histories so cycle 0
    starts settled.

Keep the module docstring explicit that this is test-only code product code takes no dependency
on (ADR-0037's Decision), and that `true_draw_w` is deliberately unobservable to the integration.

**Commit:** `T1: plant simulator with charger lag and meter derivation (ADR-0037, #998)`

---

## T2 — Plant simulator: scheduled exogenous events

**ADR honored:** ADR-0037. **Test boundary:** tier 3 / HA harness,
`tests/scenarios/test_plant.py`.

**Files:**
- Edit: `tests/scenarios/plant.py`
- Edit: `tests/scenarios/test_plant.py`

**Failing tests first:**

- `test_a_scheduled_event_takes_effect_from_its_own_cycle` — an event registered at
  `at_cycle=3` changing `house_load_w` leaves cycles 0–2 unchanged and is reflected in cycle 3's
  own `net_w`.
- `test_a_scheduled_event_persists_after_its_cycle` — the world keeps the new value on cycles
  4+ until another event changes it (a world change is a step, not a pulse).
- `test_two_events_on_the_same_cycle_both_apply` — a plug-in and a load change scheduled
  together both land, so a scenario never has to order them by hand.
- `test_a_scheduled_status_change_is_how_plug_and_unplug_are_modelled` — setting `status` to the
  canonical disconnected/connected constants from `const.py` is the whole mechanism; there is no
  second plug/unplug API (design doc §5.3).

**Implementation:** a `schedule(at_cycle, **world_overrides)` method recording overrides per
cycle, applied at the top of `advance()` before the charger/meter model runs, mutating the
`WorldState` in place. No separate event types, no callbacks — one mechanism.

**Commit:** `T2: schedule exogenous world events on the plant timeline (ADR-0037, #998)`

---

## T3 — Scenario runner: the virtual clock and cycle cadence

**ADR honored:** ADR-0037 (tier 3 drives real config entries and real coordinator cycles);
ADR-0006 (the cycle being driven is the coordinator's own, unchanged). **Test boundary:** tier 3 /
HA harness, `tests/scenarios/test_runner.py`.

**Files:**
- Create: `tests/scenarios/runner.py`
- Create: `tests/scenarios/test_runner.py`
- Edit: `tests/conftest.py` (module docstring only — see Step 0)

**Step 0 — record the tier in `tests/conftest.py`'s docstring.** No functional change: a
directory not in `_PURE_DIRS` and files not in `_PURE_FILES` are already routed through the HA
harness, which is correct for tier 3 (design doc §10). Add one paragraph to the module docstring
saying `tests/scenarios/` is ADR-0037's scenario/timeline tier, runs in the same harness as tier
2 by design rather than by omission, and is deliberately **not** split across `_PURE_FILES` even
though its `plant.py`/`invariants.py` tests need no `hass`.

**Failing tests first** (`tests/scenarios/test_runner.py`, each driving a real `MockConfigEntry`
setup like the existing end-to-end suites):

- `test_each_tick_advances_the_monotonic_clock_by_the_control_interval` — `hass.loop.time()` as
  the coordinator sees it advances by exactly `control_interval_s` per tick, starting at 0.0
  (design doc §4.2's first mitigation).
- `test_each_tick_advances_wall_clock_time_in_lockstep` — `dt_util.now()` advances by the same
  delta on the same tick, from a fixed start instant away from midnight and a month boundary.
- `test_the_runner_drives_exactly_one_cycle_per_tick` — `N` ticks produce exactly `N` captured
  `number.set_value` calls. **This is §4.2's canary**: it fails if the coordinator's own
  auto-refresh ever fires against the jumped loop clock. Name it so the next reader knows that.
- `test_the_coordinator_auto_refresh_is_unscheduled_before_the_first_tick` — asserts the
  cadence is the runner's, not `DataUpdateCoordinator`'s.
- `test_a_command_takes_physical_effect_on_the_following_tick` — the current captured on tick
  `n` is what the plant draws on tick `n+1` (design doc §4.1 step 6: the loop is closed).

**Implementation** — `tests/scenarios/runner.py`, a `ScenarioRunner` that owns:

- construction from `(hass, coordinator, plant, freezer, monkeypatch, interval_s, start_dt)`;
- the virtual monotonic clock (starting at 0.0), installed with
  `monkeypatch.setattr(hass.loop, "time", ...)` **after** config-entry setup completes;
- unscheduling the coordinator's own refresh (`update_interval = None` plus cancelling the
  pending handle);
- `async def tick()` running design doc §4.1's seven steps, writing the plant's readings through
  `tests/helpers.py::seed_charger_states` (§5.4) and reading the commanded current off the
  captured `number.set_value` calls (§6), carrying the previous value forward if a tick added
  none;
- `async def run(cycles)` looping `tick()`;
- a per-cycle `CycleObservation` record (cycle index, both clock values, world fields,
  `true_draw_w`, `true_baseline_w`, reported `net_w`/`charger_w`, commanded current,
  `coordinator.data.active_mode`, `coordinator.data.fault`) kept in a list for T4's report.

The runner's docstring records the loop-clock monkeypatch as a known coupling with design doc
§4.2's mitigations, and states the observation-surface rule (§6): no `_step_*` hooks, no
`CycleContext` capture.

**Commit:** `T3: scenario runner with one virtual clock driving real coordinator cycles (ADR-0037, #998)`

---

## T4 — Invariant protocol, per-cycle checking, and the failure report

**ADR honored:** ADR-0037 (the invariant-oracle rule and what a passing scenario may mean).
**Test boundary:** tier 3 / HA harness, `tests/scenarios/test_runner.py`.

**Files:**
- Create: `tests/scenarios/invariants.py` (protocol + violation type only; INV-1 lands in T5)
- Edit: `tests/scenarios/runner.py`
- Edit: `tests/scenarios/test_runner.py`

**Failing tests first:**

- `test_every_registered_invariant_runs_on_every_cycle` — two stub invariants, both called once
  per cycle for the whole run.
- `test_the_run_fails_on_the_first_violating_cycle` — a stub that violates from cycle 2 stops the
  run at cycle 2; cycles 3+ are never driven (design doc §7.2's fail-fast rule, with its reason:
  the world after a bad command is not independent evidence).
- `test_the_failure_report_names_the_invariant_and_the_violating_cycle`.
- `test_the_failure_report_carries_the_preceding_cycles` — the message includes the rows for the
  few cycles before the violation, each with the world fields, `true_draw_w`,
  `true_baseline_w`, the reported `net_w`/`charger_w`, the commanded current and the active mode.
  A bare `assert False` on cycle 63 of 96 is not actionable (issue #998).
- `test_a_clean_run_raises_nothing` — the negative control, so the runner cannot pass by never
  checking.

**Implementation:**

- `invariants.py`: an `Invariant` protocol (`name`, `check(observation) -> Violation | None`) and
  a frozen `Violation` dataclass carrying the invariant name, a one-line reason, and the two
  headroom figures the report prints side by side (ground truth vs. what the coordinator could
  have computed from the readings it was given).
- `runner.py`: check every registered invariant after each cycle; on the first `Violation`, raise
  a single `AssertionError` built from a formatted table of the ring buffer of recent
  observations plus the violating one.

**Commit:** `T4: run shared invariants per cycle with a contextual failure report (ADR-0037, #998)`

---

## T5 — INV-1: headroom is never overshot against true charger draw

**ADR honored:** ADR-0037 (the invariant-oracle rule — INV-1 qualifies because it compares
against ground truth the production code structurally cannot see). **Requirements anchored:** R3
(and its AC5 grace-period hold), C4, C3, R11 AC1, R17 AC2, R18. **Test boundary:** tier 3 / HA
harness, `tests/scenarios/test_invariants.py`.

**Files:**
- Edit: `tests/scenarios/invariants.py`
- Create: `tests/scenarios/test_invariants.py`

**Failing tests first** — all against hand-built `CycleObservation` values, so INV-1 is proven
before any scenario depends on it:

- `test_c4_overshoot_against_true_baseline_is_flagged` — a commanded current that, drawn in full
  against `true_baseline_w`, exceeds `ceiling_a − offset_a`.
- `test_a_compliant_cycle_is_not_flagged` — the negative control.
- `test_a_cycle_that_only_looks_compliant_against_the_reported_readings_is_still_flagged` — the
  #992 shape in miniature: reported `charger_w` stale-high, derived headroom ample, true headroom
  exceeded. This is the test that proves INV-1 is an oracle and not a mirror (design doc §7.1).
- `test_r3_overshoot_against_true_baseline_is_flagged_while_r3_is_in_force`.
- `test_r3_is_not_asserted_when_the_clamp_is_not_in_force` — CapTar capability absent (R18), and
  `Power` with its peak-protection option off (R17 AC2); C4 is still asserted in both, because
  C3 names it as the only unconditional import limit.
- `test_r3_is_not_asserted_on_a_grace_period_hold_at_the_minimum` — R3 AC5 / R11 AC1: holding at
  the charger minimum during a momentary breach is required behaviour, not a violation. **C4 is
  still asserted on such a cycle** — R11 AC1 names C4 as a hard limit that cuts immediately, and
  `_apply_grid_ceiling_clamp`'s own docstring calls it never skippable.
- `test_whole_ampere_flooring_is_given_no_permissive_slack` — the comparison is against the
  real-valued ceiling; a clamp flooring to a whole ampere only ever errs conservative, so INV-1
  must not add tolerance that would hide a genuine overshoot.

**Implementation:** `HeadroomAgainstTrueDrawInvariant` in `invariants.py`, reading
`true_baseline_w` and the commanded current from the observation, the C4 bounds from the
scenario's configured `grid_ceiling_a`/`grid_safety_offset_a`, and R3's per-cycle
`effective_peak_limit_kw` from `coordinator.data` (design doc §6 explains why reading that one
bound from the coordinator does not make the invariant a mirror). Exemptions expressed as named
predicates with the requirement id in the comment, never as bare conditionals.

**Commit:** `T5: INV-1 — headroom never overshot against true charger draw (ADR-0037, #998)`

---

## T6 — The first scenario: Manual + Power, commanded-current step-down (red)

**ADR honored:** ADR-0037 (bug-first sequencing — the simulator's lag model is validated by
reproducing an already-diagnosed real defect before any speculative scenario is written);
ADR-0017 (`ManualPolicy` as the mode-selection policy being passed through). **Test boundary:**
tier 3 / HA harness, `tests/scenarios/test_power_step_down.py`.

**Files:**
- Create: `tests/scenarios/test_power_step_down.py`

**This task lands the test red, on purpose.** It is marked
`@pytest.mark.xfail(strict=True, reason="#992: C4 re-derives its own baseline from the stale charger_power reading")`.
`strict=True` matters: if the scenario ever passes before T7's fix lands, the task fails rather
than silently becoming a no-op. T7 removes the marker as part of turning it green, so git history
carries the red-before-green proof that the simulator reproduces a real defect rather than an
imagined one.

**The test** builds design doc §8's world: `Manual` profile and `Power` mode seeded on
`select.smart_charging_profile`/`select.smart_charging_mode`, `power_respect_peak=False` with the
CapTar capability present (C3 case (b) — C4 is the only import limit in force), grid ceiling 25 A
with a 2 A offset, min/max current and Power target at their defaults, `smoothing_window` left at
its real default (not 1 — both clamps read raw by construction), a representative monthly peak
seeded via `coordinator.seed_monthly_peak` (**not** `seed_ample_peak_headroom`, which is the
tier-2 engine-muting idiom), `ev_soc` constant at 50 %, `status` constant, `solar_w` 0 W,
`house_load_w` 1000 W with one scheduled event stepping it to 5000 W at cycle 3, and charger
`response_lag`/`sensor_lag` of 1 cycle each. The plant is primed at 16 A so cycle 0 starts
settled.

Run 8 cycles with INV-1 registered, and assert the scenario-intent properties (design doc §8.3):

- cycles 0–2 command 16 A — Power holds its target while C4 is non-binding;
- cycle 3 commands 0 A — the commanded-current step-down, caused by a clamp reacting to a world
  event rather than to a hand-picked reading;
- cycle 4 commands 0 A, not 16 A — named in the test as the #992 regression;
- cycles 5–7 stay at 0 A.

INV-1 fails at cycle 4 until T7 lands; design doc §8.2 has the cycle-by-cycle arithmetic to
check the implementation against.

Do not extend the timeline to step the household load back down — the recovery half belongs to
the deferred bounded-oscillation invariant (design doc §7.3), and adding it here would make this
scenario assert a number it cannot calibrate.

**Commit:** `T6: scenario reproducing #992's stale-charger_power headroom inflation (xfail) (ADR-0037, #998)`

---

## T7 — Route C4's clamp through the debounced baseline (#992)

**ADR honored:** ADR-0006 (steps 7 and 8 stay two separate methods and two separate call sites;
only step 7 is gated by the R17 opt-out — sharing an *input reading* is not merging a *call
site*); ADR-0010 (`engines/` package home); ADR-0009/ADR-0037 (the three tiers this task touches).
**Requirements anchored:** C4, C3, R3. **Test boundaries:** tier 1 (plain pytest,
`tests/engines/test_grid_safety.py`), tier 2 (HA harness, `tests/test_coordinator.py`), tier 3
(the T6 scenario turning green).

**This is the one product change in the slice.** Design doc §9 records why no ADR is opened for
it; if a reviewer disagrees with that reasoning, that disagreement is the gate on this task, not
on T1–T6.

**Files:**
- Edit: `tests/engines/test_grid_safety.py`
- Edit: `tests/test_coordinator.py`
- Edit: `custom_components/smart_charging/engines/grid_safety.py`
- Edit: `custom_components/smart_charging/coordinator.py`
- Edit: `custom_components/smart_charging/coordinator_cycle.py` (comment only)
- Edit: `tests/scenarios/test_power_step_down.py` (remove T6's `xfail`)

**Failing tests first, tier 1** (`tests/engines/test_grid_safety.py`) — rewrite the existing cases
against the new signature and add the behavioural one:

- `clamp_to_ceiling` takes `baseline_w` directly and clamps to
  `floor((ceiling_a − offset_a) − baseline_w / voltage)`, with the existing boundary cases
  (headroom above the request, below it, below the charger minimum, negative) unchanged in
  substance.
- `test_a_lower_caller_supplied_baseline_is_the_callers_business` — the engine no longer derives
  anything from `net_w`/`charger_w`, so a stale reading can only reach it through the value its
  caller resolved. This is what moves the debounce responsibility to exactly one place.

**Failing test first, tier 2** (`tests/test_coordinator.py`) — the regression issue #992 asks for
by name, mirroring #990's own but for `commanded_current` against
`grid_ceiling_a`/`grid_safety_offset_a` rather than `max_peak_kw`/`peak_floor_kw`: drive a cycle
with a current step-down, then a cycle whose `charger_w` is stale-high while `net_w` has already
dropped, and assert the commanded current does **not** rise on the strength of the transiently
negative derived baseline.

**Implementation:**

- `engines/grid_safety.py`: `clamp_to_ceiling(desired_current, baseline_w, voltage, ceiling_a,
  offset_a)` — drop the internal `baseline_w = net_w - charger_w` derivation. Update the
  docstring's "Solves from the baseline actually flowing (`net_w - charger_w`)" sentence to say
  the caller resolves it, debounced, and why.
- `coordinator.py::_apply_grid_ceiling_clamp`: pass `baseline_w=ctx.baseline_w`. **Leave the
  method exactly where it is, with no conditional of any kind** — ADR-0006's Consequences require
  step 8 to have no opt-out path that the R17 gate could ever reach.
- `coordinator_cycle.py`: update `CycleContext.baseline_w`'s field comment, which currently says
  C4 keeps reading the raw readings with its staleness "tracked separately (issue #992)", to
  record that both clamps now read this one debounced value while remaining separate call sites.
- `tests/scenarios/test_power_step_down.py`: remove the `xfail` marker; the scenario is now green.

**Green:** the three existing `test_*_end_to_end.py` suites pass unchanged — none of them exercise
a stale-high `charger_w` against a binding C4, so a changed commanded current in any of them would
be a real finding, not an expected churn.

**Commit:** `T7: route C4's grid-ceiling clamp through the debounced baseline (ADR-0006, #992)`

---

## Integration checkpoint

After T7: run the full suite (`pytest -q`) plus `ruff check .` and `ruff format --check .`. The
things worth reading rather than skimming:

- `tests/scenarios/` is collected and green, with `test_power_step_down.py` passing on its own
  merits and not as an `xfail`.
- No test outside `tests/scenarios/` changed behaviour except the two T7 explicitly edits.
- Suite wall-clock is essentially unchanged (design doc §11's runtime budget — eight cycles in one
  scenario is negligible; the named trigger for revisiting it is roughly six scenarios or a tenth
  of the suite's wall-clock).

---

## Follow-ups to file once this plan is approved

Per [idea-to-issues.md](../reference/idea-to-issues.md) step 4, and **not before** — each needs
the anchored `Plan:` line only an approved plan can provide. Filing them is part of finishing
issue #998; implementing them is separate work. Append each to epic #996.

**`testing` issues** (design doc §13 has the reasoning for each):

1. Bounded-oscillation invariant, once a Solar feedback path exists to threaten it.
2. #974 — a cooldown surviving a mode switch (R11 AC4); the virtual clock is what makes a
   cooldown actually elapse in a test.
3. #546 — a latch resetting per occasion rather than per reload.
4. #648 — `adapter_readings_at` not advancing on a fault cycle, via a scheduled sensor-fault
   event.

**One `workflow` issue**, created by ADR-0037 rather than by this plan: `.claude/skills/write-tests/SKILL.md`
and `docs/reference/definition-of-done.md`'s "Tests green" bullet both state the ADR-0009 harness
split as two-way and go stale the moment this tier lands. Reviewed by `workflow-reviewer`, not
`test-reviewer`.
