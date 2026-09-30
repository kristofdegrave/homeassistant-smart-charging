# ADR-0056: C4 solves around the higher of this cycle's own and the accepted household baseline (narrows ADR-0006)

Date: 2026-09-30
Status: Abandoned — the rule it chose is unsafe in closed loop under charger-power lag, and C4's baseline rule is to be chosen against the scenario tier's simulation in a new record.

## Summary

In the context of the C4 clamp solving around a household baseline built from two sensors with
different latencies, facing a stale charger power reading after a step-down that lets it grant
current past its target, we decided on the higher of this cycle's own and the accepted baseline
so that no stale reading ever widens C4's headroom and a genuine rise still applies at once,
accepting that the current may alternate between adjacent values while C4 binds on a lagging
charger.

## Context

- **C4's requirement changed.** The C4 constraint in
  [requirements.md](../analysis/requirements.md) now names the
  [household baseline](../analysis/system-overview.md#ubiquitous-language) the clamp solves
  around: the higher of this control cycle's own reading and the accepted one R3 resolves. It
  also accepts the alternation that follows while the clamp binds on a lagging charger.
- **Which reading a step consumes is ADR-0006's.** [ADR-0006](0006-coordinator-and-data-flow.md)'s
  step 8 applies C4 "on raw readings", and its Consequences make a change to a step's reading a
  new ADR, not a silent refactor.
- **The two sensors lag differently.** Just after the system lowers the charger current, the net
  meter already shows the drop while the charger power reading still shows the old draw. The
  baseline, `net_w - charger_w`, then reads too low, and a clamp solving around it overstates its
  headroom. [ADR-0039](0039-baseline-reading-during-own-actuation.md) settled this for R3's clamp
  and left C4's version of it undecided.
- **C4 is the one unconditional limit (C3).** No opt-out may reach it, and it must react to a
  genuine household rise on the cycle it happens: that is why it reads raw values rather than
  smoothed ones.
- **The clamps stay separate call sites (ADR-0006).** Whatever C4 reads must not become a shared
  clamp or a shared opt-out with R3.

## Considered options

### Option A — Keep this cycle's raw baseline alone

- Pro: C4 depends on nothing R3 resolves, and a genuine household rise always reaches it on the
  cycle it happens.
- Con: after a step-down the stale charger reading understates the baseline, so C4 grants
  current past its target — past the ceiling itself when the lag is large enough — on a transient
  the system caused by its own actuation.
- Con: while C4 binds on a charger whose power reading lags a change by a cycle, each step's
  stale charger reading shifts the next cycle's baseline by that step, so the current swings from
  cycle to cycle, the swing growing until the charging-current bounds (C1) stop it, and
  overshooting the target on the step up that follows each step down.

### Option B — R3's accepted baseline as it is

- Pro: one baseline for both clamps, already resolved every cycle, and the stale-low transient
  after a step-down is ignored.
- Con: ADR-0039's discard on a cycle the command changed works in either direction, so a genuine
  household rise landing on such a cycle reaches C4 a cycle late — the sudden swing C4's raw
  reading exists to catch.

### Option C — The higher of this cycle's own and the accepted baseline

- Pro: never less conservative than Option A, so no reading can widen C4's headroom past what the
  raw reading allows; the stale-low transient is ignored, and a genuine rise applies on the cycle
  it happens.
- Con: a genuine household drop reaches C4 only once R3 accepts it, which costs headroom for up
  to a few cycles.
- Con: while C4 binds on a charger whose power reading lags, the step-up's stale-low charger
  reading looks like a rise and is taken at once, so the current alternates between adjacent
  values from cycle to cycle, never above the ceiling.
- Con: C4's operand now depends on R3's baseline resolution, which must therefore run every cycle
  whatever the capabilities; were it ever gated off, C4 would fall back to Option A, overshoot
  included.

## Decision

**Option C.** It is the only option that removes Option A's overshoot without taking on Option B's
delayed rise. Its first two Cons cost charging rate or charger steadiness, never import above the
ceiling, and its alternation is a bounded form of Option A's swing (its second Con), here
without A's overshoot. Its third is a coupling whose cost is Option A's overshoot, returning if
R3's baseline resolution were ever gated off; the Consequences guard against that.

C4 reads the accepted baseline as a shared **input**, not a shared clamp. The resolution runs once
per cycle, before either clamp. R17's opt-out skips R3's clamp, never R3's baseline resolution,
and without the CapTar capability (R18) that resolution still runs every cycle (R3's first
criterion), so nothing that can skip R3 reaches C4, and ADR-0006's separate call sites stand.
ADR-0006's step 8 is narrowed accordingly: C4 still reads unsmoothed values, and it solves around
the higher of the two baselines. ADR-0039's discard is not extended to C4: taking it over as it
is would be Option B.

## Consequences

- **The C4 call site passes the higher of the two baselines.** The Grid-Safety Engine needs no
  change: it solves around the operands it is handed and cannot tell which baseline they came
  from. The change lands as its own development task, reproduced first as a scenario in
  ADR-0037's tier, the lag class that tier exists for. That tier and the invariants below are not
  built yet, so the task depends on them.
- **The baseline resolution becomes load-bearing for C4 on every installation.** A later change
  that gates it on a capability, or skips it with R3's clamp, would put C4 back on this cycle's
  reading alone without any test naming C4 failing, so the scenario tier's C4 invariant has to
  cover an installation without the CapTar capability.
- **The alternation is accepted, and the tier's bounded-oscillation invariant has to say so.**
  R10's steady-input criterion already exempts C4 while it binds. An invariant that counts
  set-point direction flips excludes the cycles on which C4 binds, or allows this two-cycle
  alternation there.
- **The design documents follow.** `system-design.md` §5.1's sequence and §8.3's account, and
  `project-plan.md`'s shipped-slice notes, still describe C4 as solving around raw operands alone.
- **ADR-0039's open case for C4 is closed** by this record, and its discard stays R3's alone.
- Nothing here changes C4's thresholds, its safety offset, or R5's forecast, which keeps fitting
  its C4 bound to the smoothed joint mean ([ADR-0051](0051-r5-forecast-reads-the-admitted-joint-mean.md)).

**Blast radius.** Four searches, run as written:

1. `rg -n 'clamp_to_ceiling|ceiling_headroom_a' custom_components/ tests/` — 26 hits. Every C4
   headroom calculation goes through `ceiling_headroom_a`, which `clamp_to_ceiling` delegates to,
   and both are imported only under their own names, so this finds every call and every spy.
2. `rg -n -U -i 'C4[^0-9][^\n]*(\n[^\n]*)?raw|raw[^\n]*(\n[^\n]*)?C4[^0-9]' custom_components/ tests/`
   — 15 matches (27 lines); each is listed by its first line. Comments and docstrings name C4's
   operand in prose, often across a line break, and every such statement calls it raw; the
   `test_grid_safety.py` matches and `test_coordinator.py:4821` match only because "draw"
   contains "raw".
3. `rg -n -i 'C4[^0-9].*raw|raw.*C4[^0-9]|ceiling.*raw|raw.*ceiling' docs/design/` — 6 hits. Every
   design statement of which reading C4 uses names it as raw.
4. `rg -n '_debounce_baseline|debounce_baseline_w|_baseline_debouncer' custom_components/ tests/`
   — 55 hits. C4 becomes a consumer of the accepted baseline, so every site that names that
   resolution's consumers, or could gate it, is reached through the resolution's own names.

| Site | Today | Follow-up |
|---|---|---|
| `custom_components/smart_charging/coordinator.py:1554` | `_apply_grid_ceiling_clamp` passes this cycle's raw `net_w`/`charger_w` | Pass the higher of this cycle's own and the accepted baseline |
| `custom_components/smart_charging/coordinator.py:241` (search 4) | The comment it closes (from :238) lists the resolution's consumers as `peak_headroom_a`, `solar_surplus_w` and `apply_peak_clamp` | Add C4 |
| `custom_components/smart_charging/coordinator.py:687` (search 4) | `_debounce_baseline`'s docstring: the same three, "all three stay in lockstep" | The same |
| `custom_components/smart_charging/coordinator_cycle.py:75` and `:81` (searches 4 and 2) | Says R3 reads the debounced baseline and C4 keeps reading the raw `ctx.net_w`/`ctx.charger_w` | Name the higher-of baseline |
| `custom_components/smart_charging/coordinator_cycle.py:91` | Says C4 reads the raw, undebounced `net_w`/`charger_w` | The same |
| `custom_components/smart_charging/coordinator.py:1596` | Says the real C4 clamp still uses the raw operands | The same |
| `custom_components/smart_charging/coordinator.py:1640` | Says C4 itself clamps against the raw `ctx.net_w`/`ctx.charger_w` | The same |
| `tests/test_coordinator.py:4663` | Docstring: the raw operands the real C4 clamp still uses | The same |
| `tests/test_coordinator.py:4814` | Section comment: the C4 clamp stays raw | The same |
| `tests/test_coordinator.py:4901` (searches 1 and 2) | Docstring: the real C4 clamp must stay on the raw operand | Assert the higher-of operand |
| `tests/test_coordinator.py:4918` | Asserts the real C4 clamp receives the raw `net_w` | The same |
| `tests/test_coordinator.py:4919` | Asserts the real C4 clamp receives the raw `charger_w` | The same |
| `tests/test_captar_end_to_end.py:254` | Docstring: C4 still reads raw on the cycle R3 defers | Name the higher-of baseline; the asserted 7 A stands, since the raw baseline is the higher there |
| `tests/test_captar_end_to_end.py:262` | Comment: C4 reads raw regardless | The same |
| `docs/design/system-design.md:459` | §5.1's escalated-rate note: "the clamps below fit this instant and read raw" | Name C4's higher-of baseline in the smoothed/raw contrast |
| `docs/design/system-design.md:476` | §5.1's sequence: "grid-supply-ceiling clamp on raw (C4, always)" | Name the higher-of baseline |
| `docs/design/project-plan.md:394` | "the C4 clamp stays on the raw operands" | Note the change, or leave the shipped slice's history as it was |
| `docs/design/project-plan.md:468` | "the real C4 clamp stays on the raw, undebounced `net_w`/`charger_w`" | The same |

Conforming, 70 hits:
- search 1's 13: the import at `coordinator.py:86`; `grid_safety.py:12`, `:32` and `:42`, which
  solve around the operands their caller passes; the six in `tests/engines/test_grid_safety.py`,
  which test that engine; and `test_coordinator.py:4333`, `:4351` and `:4837`, the step-order
  list and a spy's registration, whose order is unchanged;
- search 2's 3: `test_grid_safety.py:22`, `:51` and `:65`, the same engine tests;
- search 3's 2: `system-design.md:875` and `:876`, whose "raw" means unsmoothed, which still
  holds;
- search 4's 52: the resolution and its state, run every cycle with no gate —
  `coordinator.py:79`, `:246`, `:627`, `:695` and `:697`; how it defers, which is unchanged —
  `coordinator.py:247`, `:256`, `:783`, `:816`, `:1893`, `:1907`, `:1912`, `:1973`, `:1976` and
  `:1981`, `signal_conditioning.py:72` and `:78`, `const.py:211` and `:214`, and
  `billing_protection.py:73` and `:150`; and the tests of that resolution — the 22 in
  `tests/engines/test_billing_protection.py`, `test_coordinator.py:700`, `:702`, `:707`, `:716`,
  `:726`, `:728` and `:729`, and `test_captar_end_to_end.py:284` and `:292`.

Out of scope, 12 hits: R5's escalated-rate forecast and its tests, which keep fitting their C4
bound to the smoothed joint mean (ADR-0051):
- search 1's 9: `coordinator.py:1616`, `:1617` and `:1644`; `grid_safety.py:52` and `:54`;
  `test_coordinator.py:4835`, `:4891`, `:4962` and `:4963`;
- search 2's 3: `coordinator.py:1660`; `test_coordinator.py:4821` and `:4870`.

Reconciled: search 1, 4 rows + 13 conforming + 9 out of scope = 26; search 2, 9 rows + 3 + 3 =
15 matches, with `test_coordinator.py:4901` a hit of searches 1 and 2; search 3, 4 rows + 2
conforming = 6; search 4, 3 rows + 52 conforming = 55, with `coordinator_cycle.py:75` in the same
row as search 2's `:81`.
