# ADR-0039: The peak clamp discards a baseline reading taken during its own actuation

Date: 2026-09-11
Status: Proposed

## Context

`engines/billing_protection.py`'s R3 peak clamp solves from the household baseline actually
flowing, `baseline_w = net_w - charger_w`. The two operands come from different sensors with
different latencies: the net meter reflects a change in charger draw on the cycle it happens,
while the charger's own power sensor (a slow Modbus poll on the reference install) can still
report the previous cycle's value.

Issue #990 addressed one direction of that mismatch. `debounce_baseline_w` holds a *lower*
(more permissive) reading until it has persisted `BASELINE_DEBOUNCE_CYCLES` consecutive cycles,
while a reading at or above the last accepted value — the safety-conservative direction — is
committed immediately. Its docstring records the remaining exposure as bounded:

> an accepted trade-off: it costs one extra cycle of understated headroom/`solar_surplus_w`
> once the true, lower baseline reasserts itself, but never an unsafe one.

That accounting holds for an open-loop transient. It does not hold in the loop the clamp
actually sits in, because the understated headroom is itself what actuates the next step.
Issue #1034 reproduces the result in plain pytest against the real engine code, with a steady
simulated household load and a charger power reading one cycle behind true draw: the commanded
current runs `[12, 6, 6, 12, 6, 6, ...]` indefinitely. Nothing in the simulated world moves. The
period is three cycles — one to actuate, two for the debounce to release — and field measurement
on the reference install matches it at two different control intervals (approximately 28 s at
10 s, approximately 14 s at 5 s), confirming the period is counted in cycles rather than
wall-clock time.

Three forces bear on the fix.

**The clamp's input is not an independent measurement.** On any cycle where the coordinator
changed the commanded current, `net_w - charger_w` is partly a measurement of the integration's
own actuation observed through two clocks, not of the household. On a cycle where the command
held steady, both sensors have settled and the difference is the household baseline. The
existing debounce does not distinguish these two cases; it distinguishes only the *direction* of
the change.

**Both directions carry real cost, asymmetrically.** Understating the baseline (overstating
headroom) risks exceeding the CapTar peak the clamp exists to protect — C3. Overstating it
merely charges slower. That asymmetry is why the existing debounce is one-directional, and any
replacement has to keep the conservative direction fast enough to be worth having.

**Whatever is chosen here reaches more than the clamp.** `CycleContext.baseline_w` feeds
`apply_peak_clamp`, the `peak_headroom_a` diagnostic, and `solar_surplus_w`. C4's
`clamp_to_ceiling` re-derives its own raw `net_w - charger_w` and carries the same exposure
(issue #992), so the shape chosen here is the shape that will be proposed there.

## Considered options

Each was driven through the same closed loop used to reproduce the defect — real engine
functions, a steady household baseline, then a +1214 W household step mid-run — so the rows
below are measured rather than argued.

| option | settles, steady | settles, after a household step | exceeds the clamp target |
| --- | --- | --- | --- |
| A — status quo | no | no | never |
| B — symmetric debounce | yes | yes | 1 cycle (4850 W against a 3750 W target) |
| C — settling-aware discard | yes | yes | never |
| D — time-align both operands | not measured | not measured | not measured |
| E — damping on the commanded current | no (see Con) | — | — |

### Option A — Keep the one-directional debounce as it is

- Pro: no new state, no signature change, no new coupling; the conservative direction stays as
  fast as it can be, and the clamp provably never exceeds its target in either measured
  scenario. The oscillation costs energy and charger wear, not a peak breach.
- Con: the commanded current never settles while the clamp is binding, which is the normal
  condition for `Captar` (it requests `max_a` every cycle by design, so the clamp *is* the
  controller). The charger is commanded a new current every one to three cycles indefinitely,
  and the oscillation's amplitude — 6 A in the reproduction — is large enough that a user reads
  it as the integration malfunctioning.

### Option B — Debounce both directions symmetrically

Require any change to `baseline_w`, in either direction, to persist `BASELINE_DEBOUNCE_CYCLES`
before it is accepted.

- Pro: the smallest possible change — one branch in one pure function, no new parameter, no
  coupling to the coordinator. It settles the loop, because a one-cycle transient no longer
  survives to be actuated.
- Con: it slows the safety-conservative direction, which is the one direction the existing
  debounce deliberately kept immediate. Measured: a genuine +1214 W household step leaves the
  clamp one cycle behind, drawing 4850 W against a 3750 W target before correcting. Bounded and
  small against R3's 15-minute billing window and its own 2-minute breach grace, but it is a real
  regression in the property the clamp exists for, traded for a defect that costs no peak at all.

### Option C — Discard a baseline reading taken on a cycle the command changed

Keep the existing one-directional debounce for readings taken while the command held steady, and
discard outright any reading taken on a cycle where the coordinator changed the commanded
current — that reading measures the integration's own actuation, not the household.

- Pro: the only option measured to both settle *and* never exceed the target. It reacts to a
  genuine household step on the cycle it happens, because a steady command means both sensors
  agree, so it gives up nothing in the conservative direction. It also states the underlying rule
  in the domain's own terms — do not measure while the actuator is settling — rather than tuning
  a filter constant until the symptom goes away.
- Con: it couples a pure engine to the coordinator's command history, which is new state and a
  new parameter on a control-path function — the largest structural change of the options here,
  and one that makes `debounce_baseline_w` no longer judgeable from the readings alone. It also
  assumes the charger settles within one cycle; an EVSE that ramps slower would need the discard
  to span a configurable number of cycles, which is not knowable from the reference install
  alone.

### Option D — Give both operands the same time base

Derive `baseline_w` from a smoothed net reading and an equally smoothed charger reading, so the
relative lag cancels.

- Pro: addresses the root cause in its most general form — the defect is two operands on
  different clocks, and this removes the difference rather than filtering its consequences. It
  needs no knowledge of the command history, so the engine stays judgeable from its readings
  alone.
- Con: it contradicts [ADR-0036](0036-step-2-smooths-net-power-only.md), which decided that step
  2 smooths net power only and that which readings are smoothed is an R10 matter — so this option
  cannot be taken without superseding that record, on a question (what R10 smooths) wider than
  the defect at hand. It also slows the clamp's response to a genuine household change by the
  whole smoothing window rather than by one cycle, which is strictly worse than Option B on the
  axis Option B was rejected for.

### Option E — Damp the commanded current instead of the reading

Leave `baseline_w` alone and add hysteresis, a rate limit, or a minimum-change threshold on the
value written to the charger.

- Pro: it is the general remedy for a hunting control loop, and would cover any future term that
  starts oscillating, not only this one. It needs no new coupling and no engine signature change.
- Con: it does not remove the driving transient, only filters the response to it — and the
  transient is regenerated by whatever motion survives the filter. Worked through: with the
  command at 12 A, a transient drives headroom to 6; a decrease-immediately then
  increase-after-a-band rule steps down, the true baseline reasserts, the band is cleared, it
  steps up, and the transient recurs. The cycle is slowed, not stopped, and a band wide enough to
  stop it (greater than the 6 A excursion measured) is wide enough that the clamp no longer
  tracks the peak limit it is enforcing.

## Decision

**Option C.** It is the only candidate that settles the loop without paying for it in the
conservative direction — Option B's measured cost is a real weakening of C3, and Option D's is
the same cost multiplied by the smoothing window plus a supersession of ADR-0036 on a wider
question than this defect raises. Option E was measured and reasoned to slow the cycle rather
than end it, because it leaves the driving transient in place. Option A's Pro is genuine — it
never breaches — but `Captar` makes the clamp the controller by design, so "the commanded current
never settles" is not a cosmetic complaint.

Option C's Con is accepted deliberately. The new coupling is narrow and one-directional: the
coordinator tells the engine whether this cycle's reading is trustworthy, and the engine keeps
owning what to do about it. That is a smaller surrender than moving the decision itself into the
coordinator would be, and `debounce_baseline_w` stays a pure function of its arguments — it gains
an argument, it does not gain a dependency.

## Consequences

- `debounce_baseline_w` gains a parameter naming whether the commanded current changed on the
  cycle the reading was taken; `coordinator.py` gains the previous commanded current as state to
  derive it. The engine stays HA-free and pure, so ADR-0009's tier-1 placement for its tests is
  unchanged.
- `peak_headroom_a` and `solar_surplus_w` read the same `CycleContext.baseline_w` and therefore
  inherit the same filtering. That is intended — they are meant to show what the clamp believes —
  but it means a step cycle now holds the previous displayed value rather than showing a
  transient, and `entity-catalog.md`'s entries for both should say so.
- C4's `clamp_to_ceiling` (issue #992) re-derives its own raw baseline and carries the same
  exposure. This record does not decide that case — ADR-0006 requires the two clamps to stay
  separate call sites — but it establishes the shape a proposal there should take, and that issue
  should be updated to reference this record rather than the narrower earlier fix.
- The one-cycle discard is an assumption about the reference charger, not a measured property of
  every EVSE. If a slower-settling charger is reported, the discard becomes a count rather than a
  boolean; that is a later decision, and this record should be read as deciding *what* is
  discarded, not *for how long*.
- [ADR-0037](0037-scenario-timeline-test-tier.md)'s scenario tier names "bounded oscillation" as
  a qualifying invariant and the lag class this defect belongs to as its clearest case. This
  defect is exactly that shape and reached a live install without a standing oracle; the
  closed-loop reproduction added alongside the fix is a tier-1 stand-in, not a substitute for
  that tier.
- Nothing here changes R3's own thresholds, the breach grace period, or the effective-peak-limit
  resolution — only which reading the clamp is permitted to solve from.
