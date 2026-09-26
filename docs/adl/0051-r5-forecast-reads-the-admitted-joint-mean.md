# ADR-0051: R5's escalated-rate forecast reads R10's admitted joint mean (narrows ADR-0006 and ADR-0036)

Date: 2026-09-26
Status: Accepted

## Summary

In the context of R5's escalated-rate forecast needing a smoothed household baseline for both
of its household-dependent bounds, facing a forecast that would move on the system's own charger
steps, we decided on R10's admitted joint mean, negated, so that no charger step moves it, with
or without a one-cycle lag in the charger reading, accepting that a household change landing on
the same cycle as a charger step reaches the forecast one cycle later.

## Context

- **R5 requires the forecast smoothed.** Both bounds that depend on a household reading, the
  peak headroom R3 would leave and the C4 ceiling headroom, are fitted to one smoothed
  [household baseline](../analysis/system-overview.md#ubiquitous-language) without R3's
  deferrals. Which form of charger power that baseline is built from is the per-step question
  settled here; R5's text, landed first, records the outcome.
- **Which form a step consumes is ADR-0006's.** [ADR-0006](0006-coordinator-and-data-flow.md)'s
  step 2 says charger power is used raw, and [ADR-0036](0036-step-2-smooths-net-power-only.md)
  restated it while keeping that question with ADR-0006.
  [ADR-0049](0049-solar-surplus-smooths-net-and-charger-power-together.md) narrowed the clause
  for step 6's solar surplus only, and left R5's forecast out of scope.
- **The forecast must not move on the system's own actuation.** Urgency engages on it and is
  held once engaged; under an `Auto` baseline of `Off`, which never hands back, a false
  engagement holds the maximum peak for the rest of the session (R5).
- **The clamps must not move.** R3's and C4's clamps and the peak-headroom readout stay on raw
  readings, so a breach cannot hide behind a window (ADR-0006, R3, R5).

## Considered options

The errors below are the forecast's household baseline, in amperes, modelled with the shipped
Signal-Conditioning Engine primitives: a steady household, a window of 4 and a 16 A charger
step. The lag case is a charger power reading one cycle late, the most R10's steady inputs
allow. The escalated rate moves by the same amount the other way.

### Option A — Net import smoothed alone, minus raw charger power

- Pro: charger power stays raw, so ADR-0006's clause is not narrowed.
- Con: after a charger step the mean still holds samples taken at the earlier current, so the
  forecast is off by up to (N − 1)/N of the step, 12 A here, decaying over three cycles. On a step
  down it understates the rate: R5's own transient failure, caused by the system.
- Con: the Engine needs a second, net-only window beside the joint one ADR-0049 built.

### Option B — Per-sample net import minus charger power, every sample admitted

- Pro: each sample pairs its own cycle's charger power, so the error is 0 while the readings
  track the draw.
- Con: under the lag, the step-cycle sample is spoilt and stays for N cycles: 1/N of the step,
  4 A here. On a step up it deflates the rate and can engage urgency early.
- Con: the Engine needs a second, unadmitted output, and the clause is narrowed as under C.

### Option C — R10's admitted joint mean, negated

- Pro: the error is 0 with and without the lag: the lagged sample is the one R10 does not admit.
- Pro: no second output; the forecast reads the value the solar modes already dispatch on.
- Con: a genuine household change that lands on the same cycle as a charger step reaches the
  forecast one cycle later: at most one sample per step, never two in a row (R10).
- Con: the forecast consumes a smoothed form of charger power and inherits the window's reliance
  on the command history, which ADR-0049 accepted for step 6.

## Decision

**Option C.** It is the only option with no self-actuation error in either case (its first Pro
against A's first Con and B's first Con), and it needs no second output (its second Pro against
A's and B's second Cons). Its one-cycle delay is accepted.

This narrows **one clause** a second time: ADR-0006's step 2 "charger power is used raw",
restated in ADR-0036's Decision and already narrowed by ADR-0049 for step 6. For R5's
escalated-rate forecast, charger power now enters smoothed, jointly with net import: both of the
forecast's household-dependent bounds read the window ADR-0049 defines, its admitted mean
negated. This record answers ADR-0049's out-of-scope note.

Unchanged:

- R3's and C4's clamps and the peak-headroom readout, on raw readings;
- the C1 bound, which reads no household value;
- the forecast carries no R3 deferral (R5); ADR-0039's deferral stays R3's alone;
- the window itself: no new parameter, flag or output.

## Consequences

- Easier: one smoothed household value serves step 6 and the forecast, so the two cannot
  disagree about the system's own draw.
- Harder: a defect in the window's admission, such as a latched flag, now reaches the forecast
  as well as the solar modes.
- **Code** follow-up: the development task on R5's escalated bounds carries the admitted mean on
  `CycleContext` (ADR-0012) as a required field, and fits both bounds to it. Its tests step the
  charger with and without a lagging reading and assert the rate does not move.
- **Design** follow-up: `system-design.md` §3 drops the second-output hedge from the
  Signal-Conditioning row, its ADR table's ADR-0049 row drops "until R5 settles" and gains this
  record, and `project-plan.md`'s M1 and E7 cite it.
- No requirements follow-up: R5 already states this baseline, landed first, analysis first.
- ADR-0049's caveat carries over: a one-cycle admission rule assumes the charger settles within
  a cycle.
- ADR-0006, ADR-0036 and ADR-0049 keep Status `Accepted`, unedited; the ADL rows for ADR-0006
  and ADR-0036 point here.

**Blast radius.** Run from the repository root:

`rg -n -i 'smoothed_net_w|smoothed_baseline_w|smoothed_household_w|smoothed (household )?baseline|undeferred|used raw|raw .?charger(_w| power)|_escalated_maximum_permitted_rate_a|_escalated_rate\(|ceiling_headroom_a\(|peak_headroom_a\(|unadmitted|(escalated|forecast).{0,80}(smooth|raw)|(smooth|raw).{0,80}(escalated|forecast)' custom_components/ tests/ docs/ .claude/ .github/ CLAUDE.md`

— 111 hits, 13 of them in this record. It is wide enough because it is keyed on:
- the raw-charger clause, in each record and ADL row that states it;
- the function that composes the forecast, its test helper, its two bound calls and their
  helpers, and the joint window's output;
- every name the forecast's baseline has carried: smoothed, undeferred, net-only, unadmitted;
- *escalated* or *forecast* near *smooth* or *raw*, for prose that states the forecast's form.

The dot-directories are named, because a root sweep skips them.

| Site | Today | Follow-up |
|---|---|---|
| `custom_components/smart_charging/coordinator.py:1532` | C4 headroom bound on raw `net_w`, `charger_w` | Read the admitted mean (code) |
| `custom_components/smart_charging/coordinator.py:1548` | Peak headroom bound on `baseline_w`, raw and R3-debounced | Same |
| `custom_components/smart_charging/coordinator_cycle.py:65` | Comment names the joint mean only beside raw `net_w` | Name the new field (code) |
| `tests/test_coordinator.py:4491` | Test helper builds the ctx from raw `baseline_w`, `net_w`, `charger_w` | Supply the admitted-mean field (code) |
| `docs/design/system-design.md:165` | Signal-Conditioning row hedges on a second, unadmitted output | Drop it (design) |
| `docs/design/system-design.md:874` | ADR-0049 row: "until R5 settles" | Drop it; add this record (design) |
| `docs/design/project-plan.md:411` | E7: the negated mean is R5's baseline, citing no record | Cite this one (design) |
| `docs/design/project-plan.md:461` | M1: R5's forecast reads the wrong baseline, citing no record | Same |

73 other hits conform:
- `coordinator.py:672` and `:678`, the joint window and its negation, which the forecast reuses;
  `:781`, `:1470` and `:1489`, the forecast's call, a mention and its definition.
- `coordinator.py:866`, the raw peak-headroom readout; the two helpers' definitions and calls in
  `engines/grid_safety.py` and `engines/billing_protection.py`, and their four tests.
- The test helper's call and its six uses in `test_coordinator.py` (`:4513`–`:4592`), which hold
  once the helper feeds the new field, and `test_deadline.py:227`, which takes the rate as given.
- The nine in `requirements.md` R5, `system-overview.md`, `resolution-rules.md` and
  `control-cycle.md`, already stating this baseline.
- The eight other design hits: `system-design.md`'s sequence (four) and `project-plan.md` (four),
  which describe it or record it as not built.
- The 32 in `docs/plans/`, which specify the code follow-up as this option.
- The ADL rows for ADR-0006 and ADR-0036, which name this record.

Out of scope:
- ADR-0006's line 90, ADR-0036's line 193, ADR-0046's line 181 and ADR-0049's nine are
  immutable; the first two are the clause this record narrows.
- The five in `docs/archive/` record what was planned at their date.
- This record's own 13, which cite the sites above.
