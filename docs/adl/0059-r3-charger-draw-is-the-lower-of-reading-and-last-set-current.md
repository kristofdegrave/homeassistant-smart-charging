# ADR-0059: R3's charger draw is the lower of the charger power reading and the last set charger current (narrows ADR-0006 and ADR-0039)

Date: 2026-10-04
Status: Accepted

## Summary

In the context of R3's household baseline taking the charger's draw from a power reading that
lags it, facing a deferral that commits a corrupted low baseline under a sustained command
oscillation, we decided on the lower of the reading and the last set current so that a stale
reading cannot widen R3's headroom, accepting that while R3 binds on a reading above the set
current, the set current may change from one control cycle to the next.

## Context

- **R3's criteria fix the charger draw.** R3 in
  [requirements.md](../analysis/requirements.md) takes, as its household baseline's charger
  draw, the lower of the charger power reading and the last set charger current, with its
  deferral cases (a) and (b) unchanged. R10's steady-input criterion exempts both clamps while
  either binds.
- **The deferral cases admit a corrupted baseline.** Under a command alternating every cycle,
  case (a) discards each high reading and case (b) commits the low ones that follow. The
  scenario tier ([ADR-0037](0037-scenario-timeline-test-tier.md)) reproduced this on unmutated
  code: a -690 W baseline, and a peak breach of up to 5980 W against 5350 W wherever C4 was not
  the backstop. C4's lag drove that oscillation; Solar's moving request can too.
- **Which reading the R3 step consumes is ADR-0006's.**
  [ADR-0006](0006-coordinator-and-data-flow.md)'s step 7 applies R3 "on raw readings", and its
  Consequences make a change to a step's reading a new ADR.
  [ADR-0058](0058-c4-charger-draw-is-the-lower-of-reading-and-last-set-current.md) narrowed
  its step 8 for C4 with this same rule.
- **[ADR-0039](0039-baseline-reading-during-own-actuation.md) fixes how R3's baseline is read
  during the System's own actuation**: one debounced baseline for R3's clamp, `peak_headroom_a`
  and `solar_surplus_w`, formed from this cycle's charger power reading.

## Considered options

Options A and C were run in a throwaway scenario-tier probe: oscillation shapes with and without
C4 as a backstop, a household rise and drop, and the whole-stack world with both clamps binding.

### Option A — Keep this cycle's charger power reading

- Pro: nothing new to hold, and R3 keeps solving from what the two sensors report.
- Con: under a sustained command oscillation the deferral cases commit a corrupted low baseline,
  and without C4 as a backstop the peak limit is breached (up to 5980 W against 5350 W).

### Option B — A case-(a) discard also resets case (b)'s count

- Pro: stays inside R3's existing deferral rules, with no new operand, and an alternating
  command can no longer accumulate low readings toward case (b).
- Con: it filters the symptom, not the corrupted readings, and holds back a genuine household
  drop for as long as the oscillation lasts.

### Option C — The lower of the reading and the last set current

- Pro: a reading still showing the draw from before a step down can no longer widen the
  headroom, so the corrupted readings are removed at their source. It breached in no probed
  world, took up household rises and drops with today's timing, and gives R3 the charger
  operand C4 already has (ADR-0058).
- Con: where the reading exceeds the set current at the resolved supply voltage, the baseline
  depends on the current the System set, so while R3 binds, the set current may change from one
  control cycle to the next.
- Con: where that excess lasts, as with the nominal-voltage fallback (R22) on a higher grid
  voltage, the baseline overstates the household by it, and charging is slower than the limit
  allows.

### Option D — Accept and document

- Pro: no change to code or criteria; with ADR-0058, C4 holds both limits in the tier's
  whole-stack world even once R3's baseline is corrupted.
- Con: the exposure stays reachable from any other oscillating command, Solar's moving request
  among them, where C4 is not binding to catch it, against R3's every-cycle criterion.

## Decision

**Option C.** Options A and D leave a breach the tier reproduced, and Option B trades it for a
held-back household drop without removing the readings that cause it; Option C's Pro removes
them. Its costs are its two Cons, both on the conservative side of R3's limit.

ADR-0006's step 7 is narrowed accordingly: R3 still reads unsmoothed values, with this lower
charger term. ADR-0039 is narrowed in what its debounce receives: the whole debounced baseline
is formed this way, keeping R3's clamp, `peak_headroom_a` and `solar_surplus_w` in lockstep, and
its two deferral cases apply unchanged.

## Consequences

- **The R3 baseline input takes the lower charger term.** `coordinator.py`'s
  `_debounce_baseline(net_w, charger_w)` can share C4's `_ceiling_charger_w` operand, once that
  takes the reading and voltage rather than the `CycleContext` built after this step. The
  Billing-Protection Engine is unchanged. A successful fault-path write of 0 A counts as a set
  current, as for C4.
- **`peak_headroom_a` and `solar_surplus_w` move with it.** Solar's decisions and R5's forecast read R10's smoothed
  surplus, unchanged ([ADR-0049](0049-solar-surplus-smooths-net-and-charger-power-together.md),
  [ADR-0051](0051-r5-forecast-reads-the-admitted-joint-mean.md)).
- **R10's exemption while R3 binds is accepted.** R10's steady-input criterion already names
  both clamps; an oscillation invariant the tier adds has to allow the change on the cycles R3 binds.
- **A lasting reading above the set current is accepted as conservative.**
- **The residual case is unchanged.** A car drawing below its set current for two or more cycles
  at a reading lag of two or more commits an understated baseline under Options A and C alike;
  the tier must model such a car before a rule for it can be judged.
- **The scenario tier's R3 mutation no longer breaches**, since the lower operand alone removes
  the lagged reading it lets through. The landing task makes it bypass that operand too, and
  adds a scenario where an oscillating command without C4 keeps true import within the peak
  limit.
- **The design documents follow.** `system-design.md` §5.1's peak clamp and readout steps
  still draw R3 on raw operands, and §8.3 needs a row for this record.
- R3's thresholds, safety margin, grace period, deferral cases and effective peak limit are
  unchanged.

**Blast radius.** Four searches, run as written:

1. `rg -n 'debounce_baseline|net_w\s*-\s*charger_w' custom_components/ tests/`: 73 hits. R3's
   baseline is formed, debounced, spied on or patched through those two names, and every
   statement of its formula writes `net_w - charger_w`.
2. `rg -n '\.(peak_headroom_a|solar_surplus_w) ==|\["baseline_w"\] ==' tests/`: 19 hits. Every
   assertion on a value this decision moves: the two readouts and the baseline a spy captured.
3. `rg -n -i "corrupt|oscillat|charger_w still|stale charger|R3's own exposure" tests/`: 29
   hits. Tests describe the lagging reading's effect on R3 in prose naming no function.
4. `rg -n -i 'baseline.*raw|raw.*baseline|clamp on raw|R3.*raw|raw.*R3' docs/design/`: 15
   hits. Every design statement of which reading R3 uses names it as raw.

| Site | Today | Follow-up |
|---|---|---|
| `custom_components/smart_charging/coordinator.py:629` (search 1) | Passes this cycle's `charger_w` to the baseline step | Pass the lower operand |
| `custom_components/smart_charging/coordinator.py:689` (search 1) | `_debounce_baseline` takes the reading alone | Take the lower operand, shared with C4's |
| `custom_components/smart_charging/coordinator.py:690` (search 1) | Docstring: debounces the raw `net_w - charger_w` baseline | Name the lower charger term |
| `custom_components/smart_charging/coordinator.py:698` (search 1) | Hands the engine `net_w - charger_w` | Subtract the lower charger term |
| `custom_components/smart_charging/coordinator.py:1906` (search 1) | Docstring: a fault-recovery cycle's stale reading contaminates the baseline | The 0 A set current now bounds it; keep the clear for case (a) |
| `custom_components/smart_charging/coordinator_cycle.py:75` (search 1) | `baseline_w`'s comment: `net_w - charger_w`, debounced | Name the lower charger term |
| `custom_components/smart_charging/engines/billing_protection.py:61` (search 1) | `BaselineDebouncer`'s docstring: `net_w - charger_w` | The same |
| `custom_components/smart_charging/engines/billing_protection.py:149` (search 1) | `apply_peak_clamp`'s docstring: solves from `net_w - charger_w` | The same |
| `tests/engines/test_billing_protection.py:380` (search 1) | A step down's stale reading plunges the baseline | Name a headroom increase the lower term leaves to case (b) |
| `tests/engines/test_billing_protection.py:569` (search 1) | The closed-loop model subtracts the lagging reading alone | Take the lower operand, as the coordinator will |
| `tests/test_coordinator.py:1174` (search 1) | Docstring: cycle 2's baseline is 2000 - 3000 W | Re-derive with the lower term |
| `tests/test_coordinator.py:1197` (search 2) | Asserts `solar_surplus_w` from the 3000 W reading | Assert it from the set current at the supply voltage |
| `tests/test_coordinator.py:1209` (search 1) | Docstring: a stale reading swings the baseline to -1500 W | Restate the swing the lower term leaves |
| `tests/test_coordinator.py:1227` (search 3) | Comment: the reading still reports the prior draw | The same |
| `tests/test_coordinator.py:1264` (search 2) | Asserts the 440 A readout from the -1500 W baseline | Assert it from the lower term |
| `tests/test_coordinator.py:1265` (search 2) | Asserts `solar_surplus_w` of 1500 W | The same |
| `tests/test_coordinator.py:1290` (search 3) | Comment: the baseline swings to -3000 W, 27 A | Re-derive: -2300 W, 24 A, still above the 16 A request |
| `tests/test_coordinator.py:4946` (search 2) | Asserts the R3 clamp's baseline is 5500 - 500 W | Assert 5500 W: under `Off` the lower term is 0 W |
| `tests/test_coordinator.py:4968` (search 2) | Asserts the readout's baseline is 5000 W | The same |
| `tests/test_coordinator.py:4971` (search 2) | Asserts a -6 A readout | Re-derive from the lower term |
| `tests/scenarios/test_invariants.py:10` (search 1) | Module docstring: the R3 mutation bypasses the debounce alone | Bypass the lower operand too |
| `tests/scenarios/test_invariants.py:281` (search 1) | The mutation's comment | The same |
| `tests/scenarios/test_invariants.py:287` (search 1) | Patches the debounce alone; no breach once the lower term lands | The same |
| `tests/scenarios/test_invariants.py:304` (search 3) | Comment: the bypass lets the command oscillate | The same |
| `tests/scenarios/test_peak_and_ceiling_under_lag.py:4` (search 3) | Module docstring: both clamps bind only until step 4 | R3 keeps binding |
| `tests/scenarios/test_peak_and_ceiling_under_lag.py:22` (search 3) | "R3's own exposure": the corrupted baseline is committed at step 4 | Describe R3 binding throughout |
| `tests/scenarios/test_peak_and_ceiling_under_lag.py:24` (search 3) | The same paragraph | The same |
| `tests/scenarios/test_peak_and_ceiling_under_lag.py:25` (search 3) | The same paragraph | The same |
| `tests/scenarios/test_peak_and_ceiling_under_lag.py:26` (searches 1 and 3) | The same paragraph | The same |
| `tests/scenarios/test_peak_and_ceiling_under_lag.py:27` (search 3) | The same paragraph | The same |
| `tests/scenarios/test_peak_and_ceiling_under_lag.py:28` (search 3) | The same paragraph | The same |
| `tests/scenarios/test_peak_and_ceiling_under_lag.py:31` (search 3) | Attribution: nothing shows R3 stable under oscillation | The whole-stack test now does |
| `docs/design/system-design.md:472` (search 4) | §5.1's sequence: "peak clamp on raw" | Name the lower charger operand |
| `docs/design/system-design.md:474` (search 4) | §5.1's readout step: fitted to the RAW baseline | The same |

The remaining hits conform:
- **46 of search 1:** the Engine and its unit tests, which take the baseline as a parameter;
  `coordinator.py`'s import, call and fault-path comments and their tests, `const.py` and
  `invariants.py`, on unchanged deferral rules; `test_captar_end_to_end.py:121`'s 0 W reading;
  the mutation's control test; and `test_peak_and_ceiling_under_lag.py:15`'s history.
- **12 of search 2:** a fault's zero readouts, and readouts on a first cycle, on a cycle whose
  reading is at or below the set current, or on one whose value the debounce still holds.
- **7 of search 3:** case (a)'s step-up transient, the closed-loop block, a stale-reading
  premise, and the scenario module's history and C4-driven alternation.
- **5 of search 4:** §3's Signal-Conditioning row, §5.1's forecast note, the C4 step, and the
  ADR-0049 and ADR-0051 table rows, which contrast the clamps with the smoothed baseline.

Out of scope:
- **R10's smoothed baseline and C4's Engine** keep their own `net_w - charger_w`: 11 hits of
  search 1
  (`signal_conditioning.py:55`, `:58`, `:72`, `:78`; `grid_safety.py:22`, `:62`;
  `coordinator.py:815`, `:1615`; `coordinator_cycle.py:85`; `test_signal_conditioning.py:68`;
  `test_coordinator.py:5038`) and R5's escalated-rate assertion `test_coordinator.py:4894` of
  search 2.
- **A corrupted stored value** keeps being rejected: 7 hits of search 3
  (`test_coordinator.py:1991`, `:2015`, `:4398`; `test_config_flow.py:1814`;
  `test_sensor.py:261`; `test_time.py:135`; `test_switch.py:269`).
- **Solar's own set-point oscillation** keeps being judged by R10: 4 hits of search 3
  (`test_amp_step.py:29`, `test_solar.py:35`, `test_solar_end_to_end.py:102`, `:128`).
- **`docs/design/project-plan.md`'s 8 hits of search 4** keep recording what earlier slices
  shipped.
