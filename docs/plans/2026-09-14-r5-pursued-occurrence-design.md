# Design: R5's pursued occurrence, and the escalated rate's smoothed forecast (#1154)

The analysis layer changed under the code. `requirements.md` R5 now specifies urgency state as a
single **pursued occurrence** — the departure occurrence being chased — from which the
**missed-deadline hold** is *read* rather than separately tracked, and specifies the **escalated
maximum permitted rate** as a forecast fitted to a **smoothed** household baseline while delivery
stays clamped on raw. The code carries a boolean and reads the raw baseline for both.

This slice closes that gap. It writes no new behaviour: every rule it implements is already stated
in `requirements.md` (R5, R10, R3), `resolution-rules.md` and `UC05`, and is cited here as a test
anchor rather than restated.

## Scope

| In | Out |
| --- | --- |
| `engines/deadline.py` — `resolve_required_current`'s urgency-state parameter and return | Any change to the required-current formula itself (R5/R15, unchanged) |
| The backstop's two operands reaching the engine | The `Urgent`/`Unreachable` notification rules (ADR-0024, unchanged) |
| `coordinator.py` / `coordinator_cycle.py` — threading one occurrence where a boolean is threaded | R9's reserve-cap rule itself; only the input it reads changes shape |
| The smoothed household baseline as a distinct cycle value, feeding the escalated-rate forecast only | R3's clamp, its deferrals, and the `peak_headroom` readout — all stay on raw |
| Closing #1006 (there is no separate hold left to build) | The `debounce_baseline_w` guard (ADR-0039) — not on this path; see D-3 |

## Project-plan slice this derives from

`docs/design/project-plan.md`: **E4** (Deadline Engine — "R5's pursued occurrence, threaded in and
out by M1"), **E5** (Billing-Protection — the peak headroom under a given limit as a value, the
readout on a raw reading and R5's escalated rate on the smoothed baseline), and **M1** (Coordinator
— "Owns and threads every Engine's cross-cycle state, the Deadline Engine's included"). E5's
integration checkpoint already names the two-baseline call; this slice is what makes that true of
the code.

`docs/design/system-design.md` §5.1's sequence is unchanged by this slice: no step is added, removed
or reordered, so ADR-0006's call-order spy test should still pass untouched. That is itself a
success criterion below.

## Success criteria

1. `resolve_required_current` takes and returns a `datetime | None`, and no boolean urgency state
   survives anywhere in `custom_components/`.
2. A missed-deadline hold is nowhere a stored field — it is `pursued is not None and pursued <= now`
   at every site that needs it.
3. The backstop releases the pursued occurrence per `resolution-rules.md`'s bound, including on an
   installation where the following occurrence never resolves (R14 lets any day resolve to "no
   deadline") — the 24-hour arm is what makes the release always reachable.
4. The escalated maximum permitted rate is computed from the smoothed household baseline; the R3
   clamp and the `peak_headroom` readout still compute from the raw (debounced) one, and a test
   pins that the two can differ.
5. ADR-0006's call-order spy test passes unchanged.
6. Mutation check: each new test is shown to fail against a deliberately broken implementation
   before the slice is called done — the standard this strand has been held to since #1101.

## No ADR is opened by this slice

Against `CLAUDE.md`'s calibration test: the state-shape change swaps one parameter's type on one
Engine entry point and one Coordinator field. It reaches no second module's contract — M1 already
owns and threads that state by `system-design.md` §3's two-kind split, and ADR-0010's Decision is
about package placement, which does not move. The rules driving it — which occurrence is pursued,
when it is released, which baseline the forecast reads — are **domain rules**, which `CLAUDE.md`'s
second carve-out places in `requirements.md`/`resolution-rules.md`, where they already are, and
explicitly not in an ADR. Adding a field to `CycleContext` is within ADR-0012's existing shape.

Three existing ADRs are *honoured* rather than changed: **ADR-0006** (two clamp call sites, cycle
order), **ADR-0009** (test tiers, named per task), **ADR-0024** (`DeadlineUnreachableCleared`
pairing — unchanged, and D-6 explains why it needs no new arm).

## Concrete decisions

### D-1 — the urgency parameter becomes the pursued occurrence

`resolve_required_current`'s `urgency_latched: bool` becomes `pursued_occurrence: datetime | None`,
and `RequiredCurrentResult` gains `pursued_occurrence: datetime | None` as the successor value the
Manager threads back in.

`urgent` stays on the result. Every downstream consumer already reads it — the effective peak
limit's `urgent` parameter, `Auto`'s escalation row, the notification edge — and re-deriving it at
each of those sites would spread R5's precedence rule across the coordinator.

The relation between the two is fixed and stated once, in the engine: `urgent == (pursued_occurrence
is not None)`. A test asserts that invariant on every branch, which is what stops the two drifting.

### D-2 — the hold is a comparison, not a field

`self._urgency_latched: bool` becomes `self._pursued_occurrence: datetime | None`. The
missed-deadline hold gets no field, no setter and no clear path of its own: it is
`pursued is not None and pursued <= now`, evaluated where it is needed. Two sites need it —

- the engine, to short-circuit the two R5 tests and pin `urgent`/`unreachable` on;
- R9's reserve-cap precondition, which reads it **as it stood entering the cycle**
  (`resolution-rules.md`; `system-design.md` §5.1's opening note) — that is, against the value
  threaded in, before the urgency call updates it.

That ordering is the reason the value is read near the top of the cycle and written near the end,
and a test pins that the two readings can differ within one cycle.

### D-3 — the forecast reads `smoothed net import − charger power`, undeferred

The one thing #1154 says this spec must resolve rather than assume. **Resolved from the analysis
text**, as follows, rather than chosen:

- The glossary names two different things: *"the [household baseline]"* — net import minus charger
  power — and *"the **accepted** baseline R3 solves from"*, which is the first after R3's two
  deferral cases have been applied (`system-overview.md`, `household baseline`).
- R3's own acceptance criterion scopes the deferrals to its clamp: *"The household baseline **this
  check** solves around is this control cycle's own reading, except in exactly two cases"*
  (`requirements.md` R3).
- R10's exemption criterion likewise attributes them to R3 and separates them from the smoothing
  window: *"R3 applies **its own** deferrals to the household baseline it solves around, stated in
  R3 and authoritative there; they are not this window … and neither is ever substituted for this
  window in either direction."*
- The `escalated maximum permitted rate` entry contrasts exactly one axis — *"fitted to a raw
  reading"* for the delivered rate against *"fitted to a smoothed household baseline"* for the
  forecast. It does not contrast deferral.

So the forecast's operand is `smoothed_net_w − charger_w`, with **no** R3 deferral applied.

Both of R3's deferrals exist to suppress a one- to three-cycle artifact in a per-instant clamp;
R10's window suppresses the same artifact over its own length, and `coordinator.py`'s `surplus_w`
comment already records that reasoning for the other smoothed consumer. Applying both to a forecast
would defer twice over, against a bound — *"never … more than one control cycle"* — written for the
clamp's safety and meaningless for a forecast.

Because this had to be *derived* rather than read off a sentence, issue #1164 is filed
asking R5 or the glossary entry to state it in one line, so that no future
implementer re-derives it. That issue does not block this slice: the derivation above is the
analysis layer's own text, not a new rule. If it is ever contradicted, the source wins and this
decision changes with it.

**Where it lands.** `_run_cycle` already computes `smoothed_net_w`. A named local
`smoothed_baseline_w = smoothed_net_w - charger_w` is added beside it and carried on `CycleContext`
as its own field. Deliberately *not* reused from `ctx.surplus_w`, which is its exact negation:
solar surplus is a different domain term with a floor of its own and a different consumer set
(glossary), and one refactor of either would silently change the other.

### D-4 — the backstop needs the occurrence following the pursued one

`resolution-rules.md`'s release condition needs two operands the engine does not have today: the
occurrence *following* the pursued one, and 24 hours since the pursued one. The second is arithmetic
on a value the engine already holds. The first is resolved by the Coordinator, where the other
occurrence resolution already lives (`coordinator_cycle.py`'s `resolve_next_occurrence` call), and
passed in as `following_occurrence: datetime | None`.

`None` is a normal value here, not an error: R14 lets any day resolve to "no deadline". That is
precisely why the 24-hour arm exists, and the test for it is the one that would have caught the
earlier hole.

### D-5 — the fault-cycle rule is unchanged, and must be shown to be

Both fault early-returns sit upstream of the assignment, so a fault cycle holds the occurrence it
entered with rather than releasing it — the same reasoning `_role_readings_at` and
`_unreachable_edge` already carry (ADR-0024). Swapping the field's type must not move that line; the
existing fault tests are re-pointed at the new field rather than rewritten.

### D-6 — `unreachable` while held, and why ADR-0024 needs no new arm

While the hold is in effect no required current is computed (`UC05`), so `unreachable` cannot come
from the comparison. The engine sets it directly: a pursued occurrence in the past is unreachable by
definition, time having run out on it.

`_unreachable_edge` then keeps working untouched, because every release of the pursued occurrence
flips `unreachable` back to False through the same flag it already reads — which is exactly
ADR-0024's argument for keying the edge on the flag rather than on any one upstream guard.

## Structure

| Piece | File | `system-design.md` service |
| --- | --- | --- |
| `resolve_required_current` signature and return | `custom_components/smart_charging/engines/deadline.py` | **E4** Deadline Engine |
| The hold comparison and the backstop | same | **E4** |
| `self._pursued_occurrence`, threaded in and out | `custom_components/smart_charging/coordinator.py` | **M1** Coordinator |
| `smoothed_baseline_w` local + `CycleContext` field | `coordinator.py`, `coordinator_cycle.py` | **M1** |
| `_escalated_maximum_permitted_rate_a` reads it | `coordinator.py` | **M1** calling **E5** |
| `following_occurrence` resolution and pass-through | `coordinator_cycle.py` | **M1** calling **E4** |
| R9's reserve precondition reads the entering value | `coordinator.py` | **M1** |

Signatures after the slice:

```python
def resolve_required_current(
    deadline_at: datetime | None,
    following_occurrence: datetime | None,
    now: datetime,
    soc: float,
    active_soc_limit: float,
    ev_battery_capacity_kwh: float,
    voltage: float,
    baseline_desired_a: float,
    escalated_maximum_permitted_rate_a: float,
    pursued_occurrence: datetime | None,
) -> RequiredCurrentResult: ...


@dataclass(frozen=True)
class RequiredCurrentResult:
    required_a: float | None
    urgent: bool
    unreachable: bool
    pursued_occurrence: datetime | None  # the successor M1 threads back in
```

## Testing approach (ADR-0009)

`engines/deadline.py` is pure — **plain pytest**, in `tests/engines/test_deadline.py`, no HA
harness. The coordinator threading, the `CycleContext` field and the two-baseline split are
HA-coupled — **HA harness**, in `tests/test_coordinator*.py`, run under WSL, which is where this
project's HA environment lives. Each task below names its tier.

## Deliberate deferrals

- **The `following_occurrence` resolution lag.** Like the escalated rate's own mode-lag caveat
  already recorded in `coordinator.py`, the following occurrence is resolved once per cycle, before
  dispatch. No case is known where that matters within a single cycle; recorded here rather than
  left silent.
- **No entity surfaces the pursued occurrence.** `entity-catalog.md` lists none, and adding one is a
  `requirement` change, not this slice's.
- **No safety behaviour is deferred.** Every clamp, the fault path and the notification gating are
  untouched, which is what D-5 and D-6 exist to pin.
