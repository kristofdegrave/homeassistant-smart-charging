# ADR-0049: Step 6's solar surplus is smoothed from net import and charger power together (narrows ADR-0006 and ADR-0036)

Date: 2026-09-26
Status: Accepted

## Summary

In the context of the solar modes setting their rate from a surplus that nets this cycle's raw
charger power against a mean of net import, facing a set-point that hunts under steady inputs, we
decided on smoothing net import and charger power together, per sample, so that the solar
set-point settles under steady inputs, accepting that step 6 now consumes a smoothed form of
charger power, so a lagging charger reading has to be kept out of the window.

## Context

- **R10 requires the set-point to settle under steady inputs**, in every mode, by the (N + 3)th
  control cycle after the last input change. The solar path fails it. Step 6's
  [solar surplus](../analysis/system-overview.md#ubiquitous-language) is `charger_w − mean(net_w)`,
  and the net-import mean still holds samples taken while the charger drew earlier currents. A
  model against the real `modes/solar.py` hunts over 3 A with an 8-cycle period at the default
  window of 4, and alternates between two currents when the charger power reading lags one
  cycle. It settles only at a window of 1 without the lag.
- **Which form a step consumes is ADR-0006's, not R10's.**
  [ADR-0036](0036-step-2-smooths-net-power-only.md) gave R10 the question of which readings have a
  smoothing window. It kept with [ADR-0006](0006-coordinator-and-data-flow.md), changeable only by
  a superseding ADR, the question of which form, raw or smoothed, a step consumes. Both records
  state that charger power is used raw, "not an operand of solar surplus via the smoothed
  channel". Any fix that smooths charger power for step 6 is that kind of change.
- **ADR-0039's rejection of a charger window does not carry over.**
  [ADR-0039](0039-baseline-reading-during-own-actuation.md) rejected giving `charger_w` a window
  for R3's clamp for two reasons: R3 is exempt from smoothing, and a window slows the clamp. Step
  6 is already smoothed, and it clamps nothing.
- **A reading taken on a cycle the command changed measures the integration's own actuation.**
  ADR-0039 settled that for R3's household baseline. It holds equally for a sample entering a
  window.
- **R3, C4 and the raw net-power reading must not move.** Steps 7 and 8 clamp on raw readings so
  that a breach cannot hide behind a window (ADR-0006, R3).
- **The evidence is the author's simulation and the HA-harness regressions.** At every window
  above 1, Option A settles in simulation with and without the one-cycle lag, and Option B at
  none. The regressions pin windows 4 and 6. At a window of 1 there is no history and nothing is
  frozen, so the three options coincide and that size does not tell them apart.

## Considered options

### Option A — Smooth net import and charger power together, per sample

Each cycle's sample is `net_w − charger_w`, the
[household baseline](../analysis/system-overview.md#ubiquitous-language). Step 6's surplus is the
negated window mean. A sample taken on a cycle whose command changed is not admitted, at most once
in a row, which is ADR-0039's rule and cap. At a window of 1 nothing is frozen.

- Pro: each sample's own charger draw cancels, so the window holds no past actuation. It settles in
  simulation at every window above 1, with and without the lag.
- Pro: it matches the operand R1, R2 and UC01, and UC02's start and stop conditions, already
  name: *smoothed solar surplus*.
- Con: step 6 consumes a smoothed form of `charger_w` for the first time, so a lagging charger
  reading enters the window too. A sample taken with one stays for N cycles, which is why the
  option needs ADR-0039's freeze, not merely the per-sample subtraction.
- Con: the smoothing engine gains the command-changed parameter and a second deferral flag. The
  window no longer averages simply the last N samples, so R10's wording no longer fits.

### Option B — Keep `charger_w` raw; freeze net import's window on a command-changed cycle

- Pro: it keeps ADR-0036's raw charger operand and R10's "net grid power is the only reading it
  smooths".
- Con: it does not settle, in simulation, at any window above 1. A one-cycle freeze leaves every
  earlier-current sample in the window, so raw `charger_w` still meets a mean of other currents.
- Con: its freeze couples the smoothing engine to the command history, as Option A's does.

### Option C — Keep the status quo

- Pro: no change anywhere; every record and requirement stays true as written.
- Con: it fails R10's steady-input criterion at the default window, with and without the lag.

## Decision

**Option A.** It is the only option that settles above a window of 1 (Option A's first Pro
against B's and C's first Cons).
It takes nothing from R3 or C4.

This narrows **one clause**, stated in ADR-0006's step 2 and repeated in ADR-0036's Decision:
charger power is used raw and is not an operand of solar surplus via the smoothed channel. For
step 6's solar surplus, charger power now enters smoothed, jointly with net import, sample by
sample. Every consumer of that one surplus reads it: the `Solar` and `SolarOnly` dispatch,
`Auto`'s solar-surplus test and the baseline-mode dry-run. Both records keep Status `Accepted`
and are not edited.

Unchanged:

- steps 7 and 8 on raw readings, with ADR-0039's deferral for R3;
- the raw net-power reading kept in scope for the whole cycle;
- the displayed `solar_surplus_w`, which stays R3's accepted baseline, negated;
- ADR-0036's split: R10 owns which readings have a window, ADR-0006 which form a step reads.

The window's freeze is ADR-0039's rule for its second reading: *what* is withheld is a sample
taken while the actuator settles. It reuses the coordinator's existing command-changed signal,
and its one-in-a-row flag, separate from R3's, travels with the window the coordinator already
threads.

## Consequences

- Easier: the solar path meets R10's steady-input criterion, so its tests need not pin a window
  of 1 to see a set-point hold.
- Harder: the smoothing engine now reads the command history, so its window can no longer be
  judged from the readings alone, the price ADR-0039 already paid for R3's baseline.
- Follow-up, requirements: a `requirement` task rewords R10's What and its window criterion, the
  glossary, `entity-catalog.md`, UC02's set-point and `control-cycle.md` to say the solar
  surplus is smoothed from the household baseline and to admit the freeze. Until then the analysis layer
  describes Option C.
- Follow-up, code: the development task for R10's steady-input criterion builds Option A in
  `engines/signal_conditioning.py` and `coordinator.py`. Every early-return path that clears
  ADR-0039's deferral clears this flag too, or a fault cycle leaves the freeze latched.
- Follow-up, design: `system-design.md`'s Signal-Conditioning row, its smoothing sequence line and
  its ADR table gain this record.
- ADR-0039's caveat carries over: the one-cycle freeze assumes the charger settles within a
  cycle. If one does not, it becomes a count, and that is a later decision.
- `docs/adl/README.md`'s rows for ADR-0006 and ADR-0036 point here. Their Status stays
  `Accepted`.

**Blast radius.** Run from the repository root:

`rg -n -i 'smoothed_net_w|smooth_net_power|smoothed channel|raw .?charger_w|from net grid power alone|only reading (it|R10) smooths|smooth(ed)? .?net_w|smooth\w*.{0,40}.charger_w.|.charger_w..{0,40}smooth|smoothed (solar )?surplus|smooth\w* (the )?net (grid )?(power|import)|smoothed net|one reading R10 smooths|net grid power is sampled|smoothed value' custom_components/ tests/ docs/ .claude/ .github/ CLAUDE.md`

— 158 hits, 27 of them in this record. It is wide enough because it is keyed on the net-import
mean step 6 reads today and its function, on the raw-charger clause, on R10's net-only rule and the glossary's `smoothed
value` in their code and prose spellings, and on *smoothed surplus*, the consumers' own name for
step 6's operand. The dot-directories are named,
because a root sweep skips them.

| Site | Today | Follow-up |
|---|---|---|
| `custom_components/smart_charging/coordinator.py:85` | Imports the net-only smoother for step 6 | Import the joint one |
| `custom_components/smart_charging/coordinator.py:637` | Smooths `net_w` alone for step 6 | Smooth `net_w − charger_w` per sample, with the freeze |
| `custom_components/smart_charging/coordinator.py:640` | `surplus_w = charger_w − smoothed_net_w` | The negated window mean |
| `custom_components/smart_charging/coordinator.py:643` | Comment: the net window dampens a stale `charger_w` | Drop it with that line |
| `custom_components/smart_charging/coordinator_cycle.py:62` | Comment names `smoothed_net_w` as the smoothed reading | Rename with it |
| `custom_components/smart_charging/engines/signal_conditioning.py:3` | Docstring: R10 smooths `net_w` only | Name the joint window |
| `tests/test_coordinator.py:3978` | Spies the net-only smoother as step 2's call | Spy the joint one |
| `tests/test_coordinator.py:3995` | Asserts it in the call order | Same |
| `tests/test_solar_end_to_end.py:113` | Pins a window of 1 because the net-only mean blends in stale readings | The pin may go |
| `docs/analysis/requirements.md:176` | R10: net grid power is the only reading smoothed | The requirements follow-up |
| `docs/analysis/requirements.md:180` | R10's window criterion: net grid power is sampled and averaged | The requirements follow-up |
| `docs/analysis/system-overview.md:59` | Overview: the loop smooths net grid power | The requirements follow-up |
| `docs/analysis/system-overview.md:127` | `coordinator`: smooths net grid power | The requirements follow-up |
| `docs/analysis/system-overview.md:129` | `control cycle`: smooth net grid power | The requirements follow-up |
| `docs/analysis/system-overview.md:163` | `smoothed value`: a mean of `net_w` only | The requirements follow-up |
| `docs/analysis/entity-catalog.md:127` | `net_power`: the one reading R10 smooths | The requirements follow-up |
| `docs/analysis/entity-catalog.md:130` | The solar set-point converges the smoothed net value toward 0 W | The requirements follow-up |
| `docs/analysis/control-cycle.md:17` | Purpose: smooth the net grid power reading | The requirements follow-up |
| `docs/analysis/control-cycle.md:74` | Step 2 node: smooth `net_w` | The requirements follow-up |
| `docs/analysis/control-cycle.md:106` | Step 2: raw `net_w` enters the window | The requirements follow-up |
| `docs/analysis/control-cycle.md:79` | Step 6 node: smoothed `net_w`, raw `charger_w` | The requirements follow-up |
| `docs/analysis/control-cycle.md:149` | Step 6 passes smoothed `net_w` with the raw readings | The requirements follow-up |
| `docs/analysis/use-cases/UC02-charge-from-solar-only.md:94` | Set-point keeps smoothed net grid import ≤ 0 W | The requirements follow-up |
| `docs/analysis/use-cases/UC02-charge-from-solar-only.md:142` | Charging row: the same | The requirements follow-up |
| `docs/analysis/use-cases/UC02-charge-from-solar-only.md:181` | Diagram: the same | The requirements follow-up |
| `docs/design/system-design.md:165` | Signal-Conditioning row: smoothed `net_w` | The design follow-up |
| `docs/design/system-design.md:442` | Sequence: smooth `net_w` | The design follow-up |
| `docs/design/system-design.md:443` | Sequence: returns smoothed `net_w` | The design follow-up |

51 other hits conform:
- `signal_conditioning.py:16` and the seven in `test_signal_conditioning.py`: the net-only
  primitive stays, and the joint window reuses it.
- The 34 in `requirements.md` (six), `system-overview.md:173`, `resolution-rules.md:454`, UC01
  (12), UC02 (13) and `.github/create-uc-issues.sh:42`: they already set the rate from
  *smoothed surplus*.
- Seven that hold under either form: `requirements.md:50` (R3 reads raw) and `:505`,
  `entity-catalog.md:112` and `:113`, `control-cycle.md:108` and `:110`, and
  `coordinator_cycle.py:79`.
- `system-design.md:867` and the ADL's ADR-0036 row, both still true.

Out of scope:
- The seven in `coordinator_cycle.py:34` and `:129`, `peak_demand_tracker.py` and their tests
  keep R21's own net-power window.
- The 15 in ADR-0006, ADR-0036 and ADR-0039 are immutable. `0006…:91` and `0036…:193` are the
  clause this record narrows.
- The 11 in `docs/plans/`, the 18 in `docs/archive/` and `project-plan.md:407` record what was
  planned or built at their date.
- The 27 in this record itself.
