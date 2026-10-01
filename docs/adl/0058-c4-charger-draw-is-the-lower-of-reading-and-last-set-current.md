# ADR-0058: C4's charger draw is the lower of the charger power reading and the last set charger current (narrows ADR-0006)

Date: 2026-10-01
Status: Accepted

## Summary

In the context of the C4 clamp solving around a household baseline built from a charger power
reading that lags the charger's draw, facing a clamp that grants current past the grid supply
ceiling on its own actuation, we decided on the lower of the reading and the last set current
so that neither signal can widen C4's headroom, accepting that the set current may alternate
while C4 binds on a lagging reading, charging at a reduced rate.

## Context

- **C4's requirement changed.** The C4 constraint in
  [requirements.md](../analysis/requirements.md) now names the charger draw the clamp solves
  around: the lower of this control cycle's charger power reading and the charger current the
  System last set, the reading alone until it has set one since the last restart or reload. It
  accepts an alternation while the clamp binds on a lagging reading, and records a car lowering
  its own draw under a lagging reading as a known defect against the constraint.
- **Which reading a step consumes is ADR-0006's.** [ADR-0006](0006-coordinator-and-data-flow.md)'s
  step 8 applies C4 "on raw readings", and its Consequences make a change to a step's reading a
  new record. [ADR-0039](0039-baseline-reading-during-own-actuation.md) settled R3's version of
  the lag and left C4's open.
- **The rule chosen before failed in closed loop.**
  [ADR-0056](0056-c4-solves-around-the-higher-of-own-and-accepted-baseline.md) is abandoned:
  solving around the higher of the raw and R3's accepted baseline still breached the ceiling,
  because R3's accepted baseline is itself corrupted by the oscillation the lag drives.
- **The scenario tier now judges candidates.** [ADR-0037](0037-scenario-timeline-test-tier.md)'s
  tier models a charger whose power reading lags its draw and checks the ceiling against the
  true draw. Its plant assumes the car draws exactly the set current, so it cannot judge a rule
  on a car drawing less.
- **C4 is the one unconditional limit (C3).** No opt-out may reach it, it must answer a genuine
  household rise on the next control cycle, and it stays a call site of its own (ADR-0006).

## Considered options

Each option was run in the scenario tier over charger-reading lags of 0 to 3 cycles, with a
steady household load, a rise, and a rise followed by a drop, with and without the CapTar
capability.

### Option A — Keep this cycle's charger power reading

- Pro: nothing new to hold, and a car drawing less than it was set to is read as it draws.
- Con: after a step down the stale reading understates the household, so C4 grants current past
  the ceiling; the tier breaches at every lag of 1 or more.

### Option B — The higher of the raw and R3's accepted baseline (ADR-0056)

- Pro: ignores the stale-low household transient after a step down, without delaying a genuine
  rise.
- Con: R3's accepted baseline commits corrupted readings under the oscillation, so the tier
  still breaches at lags 1 and 3, and C4 comes to depend on R3's resolution.

### Option C — The last set charger current

- Pro: exact in the tier at every lag, and the set current holds steady.
- Con: it assumes the car draws what it was set to; a car drawing less understates the
  household, which the tier cannot model, and a ramp back up then breaches the ceiling.

### Option D — The lower of the reading and the last set current

- Pro: never larger than either signal, so a stale-high reading after a step down cannot widen
  the headroom and a car drawing less is taken at its reading. No breach in any world the tier
  ran, and a household rise or drop is answered on the next cycle.
- Con: after a step up the stale-low reading overstates the household, so while C4 binds on a
  lagging reading the set current alternates, charging at about half rate.
- Con: a car lowering its own draw while the reading still lags makes both signals overstate the
  draw, the one case it does not cover.

### Option E — The last set current until the reading catches up, within a window of K cycles

- Pro: steady while the true lag is at most K, and falls back to the reading once the reading
  has caught up or the window ends.
- Con: needs a configured lag bound, breaches in the tier once the lag exceeds K, and carries
  Option C's assumption inside its window.

## Decision

**Option D.** It is the only option that breached nowhere in the tier while assuming nothing
the tier cannot check: Options A and B breach there, and C and E rest on a car following its
set current. Its costs are charging rate while C4 binds, and the uncovered case of its second
Con. That case is recorded as a known defect against C4 rather than accepted as an exception.

ADR-0006's step 8 is narrowed accordingly. C4 still reads unsmoothed values, a separate call
site with no opt-out. Its charger operand is the lower of the reading and the last set current
at the resolved supply voltage. ADR-0039's open case for C4 is closed by this record, and its
deferral stays R3's alone.

## Consequences

- **The C4 call site passes the lower charger operand.** The Grid-Safety Engine is unchanged: it
  solves around the operands it is handed. The last set current is the one the coordinator
  already holds for ADR-0039. A fault path's write of 0 A counts as a set current, which keeps
  the operand conservative on the recovery cycle.
- **The scenario tier's strict expected failures turn into failures** the day this lands, as
  they were written to. The task that lands it removes T1's and T3's markers and replaces T3's
  C4-alone oscillation test with one that expects C4 to hold the ceiling.
- **The alternation is accepted.** R10's steady-input criterion already exempts C4 while it
  binds. An oscillation invariant the tier adds later has to allow it on the cycles C4 binds.
- **The uncovered case needs the tier first.** The plant must model a car drawing below its set
  current before a rule for it, such as Option E, can be judged.
- **The control interval's 30 s upper bound** (NF11) follows from C4's excursion bound in the
  same requirement change. It is a requirement, not part of this decision: ADR-0005 fixes where
  the interval is kept, not its range.
- **The design documents follow.** `system-design.md` §5.1's sequence still draws C4 on raw
  operands alone.
- Nothing here changes C4's thresholds, its safety offset, or R5's forecast, which keeps fitting
  its C4 bound to the smoothed joint mean
  ([ADR-0051](0051-r5-forecast-reads-the-admitted-joint-mean.md)).

**Blast radius.** Three searches, run as written:

1. `rg -n 'clamp_to_ceiling|ceiling_headroom_a' custom_components/ tests/`: 37 hits. Every C4
   headroom calculation goes through `ceiling_headroom_a`, which `clamp_to_ceiling` delegates
   to, and both are imported only under their own names, so this finds every call and spy.
2. `rg -n -U -i 'C4[^0-9][^\n]*(\n[^\n]*)?raw|raw[^\n]*(\n[^\n]*)?C4[^0-9]' custom_components/ tests/`:
   15 matches, each listed by its first line. Comments and docstrings name C4's operand in
   prose, often across a line break, and every such statement calls it raw.
3. `rg -n -i 'C4[^0-9].*raw|raw.*C4[^0-9]|ceiling.*raw|raw.*ceiling' docs/design/`: 6 hits.
   Every design statement of which reading C4 uses names it as raw.

| Site | Today | Follow-up |
|---|---|---|
| `custom_components/smart_charging/coordinator.py:1554` (search 1) | `_apply_grid_ceiling_clamp` passes this cycle's `ctx.charger_w` | Pass the lower of it and the last set current at the supply voltage |
| `custom_components/smart_charging/coordinator.py:1640` (search 2) | Says C4 clamps against the raw `ctx.net_w`/`ctx.charger_w` | Name the lower charger operand |
| `custom_components/smart_charging/coordinator_cycle.py:81` (search 2) | Says C4 keeps reading the raw `ctx.net_w`/`ctx.charger_w`, with the same staleness exposure | Name the lower charger operand; the exposure is closed |
| `custom_components/smart_charging/coordinator_cycle.py:91` (search 2) | Says C4 reads the raw, undebounced `net_w`/`charger_w` | The same |
| `tests/test_coordinator.py:4901` (searches 1 and 2) | Docstring: the real C4 clamp stays on the raw operand | Name the lower charger operand |
| `tests/test_coordinator.py:4919` (search 1) | Asserts the real C4 clamp receives the raw 500 W `charger_w` | Assert the lower of 500 W and the last set current at the supply voltage |
| `tests/scenarios/test_grid_ceiling_under_lag.py:5` (search 1) | Module docstring: `clamp_to_ceiling` re-derives its baseline from the lagged reading | Describe the held ceiling |
| `tests/scenarios/test_grid_ceiling_under_lag.py:142` (search 1) | The strict xfail's reason names C4's lag defect | Remove the marker |
| `tests/scenarios/test_peak_and_ceiling_under_lag.py:13` (search 1) | Module docstring: C4's lag defect drives the oscillation | Describe the held ceiling |
| `tests/scenarios/test_peak_and_ceiling_under_lag.py:152` (search 1) | The strict xfail's reason names C4's lag defect | Remove the marker |
| `docs/design/system-design.md:476` (search 3) | §5.1's sequence: "grid-supply-ceiling clamp on raw (C4, always)" | Name the lower charger operand |

The remaining hits conform:
- **22 of search 1:** the Engine and its tests, the call-order spies, the scenario tier's
  bypass mutations and target formulas, the import, and `tests/test_coordinator.py:4918`'s
  `net_w` assertion, which the decision leaves as it is.
- **5 of search 2:** the Engine's worked examples, and `tests/test_captar_end_to_end.py:254` and
  `:262`, whose charger reading of 0 W is already the lower operand.
- **3 of search 3:** §5.1's forecast note and the ADR-0049 and ADR-0051 table rows, which state
  that the clamps do not read the smoothed baseline.

Out of scope:
- **R5's escalated-rate forecast** keeps fitting its C4 bound to the smoothed joint mean
  (ADR-0051). That is the other 8 hits of search 1 (`coordinator.py:1616`, `:1617`, `:1644`;
  `test_coordinator.py:4835`, `:4837`, `:4891`, `:4962`, `:4963`) and 6 of search 2
  (`coordinator.py:1596`, `:1660`; `test_coordinator.py:4663`, `:4814`, `:4821`, `:4870`).
- **`docs/design/project-plan.md:394` and `:468`** keep recording what earlier slices shipped.
