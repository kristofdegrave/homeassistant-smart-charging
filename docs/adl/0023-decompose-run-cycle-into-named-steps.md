# ADR-0023: Decompose `_run_cycle` into named per-step methods (extends ADR-0012)

Date: 2026-08-10
Status: Proposed

## Context

[ADR-0006](0006-coordinator-and-data-flow.md) fixes the control cycle's step order — ten
steps, explicit and literal in `coordinator.py`, auditable by reading `_run_cycle` top to
bottom against the ADR's own numbered list — and requires the R3 peak clamp (step 7,
skippable only via `Power` mode's R17 opt-out) and the C4 grid-ceiling clamp (step 8, never
skippable) to stay two separate method calls. Its Option A (one combined clamp routine) was
rejected specifically because it would let the R17 opt-out reach C4 by construction.

[ADR-0012](0012-coordinator-internal-decomposition.md) named three concrete Single
Responsibility / Open-Closed violations inside `_run_cycle` — the mode-dispatch `if/elif`
chain, three loose monthly-peak-tracking fields, and inlined SOC-limit resolution — and
extracted exactly those three into small, independently pytest-testable units
(`ModeHandler`, `PeakDemandState`, `SocGateResolver`), threading a `CycleContext` dataclass
between them. It explicitly considered and rejected a fully generic `CycleStep` pipeline
(its Option B: a list of `apply(ctx) -> ctx` objects iterated in a loop) because it would
make ADR-0006's step order an implicit consequence of a list's construction rather than a
literal, readable sequence of named calls — and it left the door open for later work:
"If a future addition reveals a similarly-shaped SRP/OCP violation elsewhere in `_run_cycle`
not covered by these four units, that is a new decision to make at that time, not something
this ADR forecloses or pre-answers."

That time has come. `_run_cycle` is still a single ~360-line method. Everything ADR-0012
did not name remains inlined directly in it: the initial adapter reads and voltage
resolution, the R8 solar step-up resolution, the R9 solar-reserve-cap and R14
departure-deadline read-and-resolve block (shared by today's urgency and tomorrow's
reserve-cap precondition), the disconnect/`Off`/`Power`/SOC-gated-stop dispatch branches
that surround the `ModeHandler` lookup, and the two clamp calls plus the floor/cap
invariant. None of this is a defect ADR-0012 missed — none of it was one of the three named
violations — but the accumulated inline volume is itself now the problem: every new
cross-cutting concern this integration has added (deadline urgency, solar reserve, step-up)
has landed as more lines inside the same method rather than as a new, independently testable
unit, and `_run_cycle` is difficult to read, extend, or unit-test as a whole.

The forces at play:

- ADR-0006's auditability requirement (a reviewer reads `_run_cycle` top to bottom and
  checks it against the ADR's numbered steps) must not be weakened.
- ADR-0006's R3/C4 clamp separation (two call sites, only one has an opt-out) must not be
  weakened.
- Several of the still-inlined blocks perform real adapter I/O (`await
  self._adapters[...].read()`) interleaved with computation — per ADR-0009/0010, only the
  coordinator side may touch HA/adapter I/O, so a block that reads an adapter cannot become
  a pure object the way `PeakDemandState`/`SocGateResolver` did; at best its I/O and its
  decision logic can be separated, with the I/O staying coordinator-side.
- The cycle's actual control flow is not a uniform linear pipeline: `_reset_mode_state_if_changed`
  is called twice (once catching a `Manual` mode change early, again after `Auto`'s own mode
  resolves later in the same cycle), and two fault checks return `CycleResult` early,
  skipping every remaining step for that cycle.
- Growth pressure is real and ongoing — R12/R13 (notifications) and further deadline/urgency
  refinements are active or upcoming work, and each has so far meant editing `_run_cycle`
  directly.

## Considered options

### Option A — Extract every remaining block into a named unit, `_run_cycle` stays an explicit sequence of calls

Give every still-inlined block in `_run_cycle` the same treatment ADR-0012 already gave
three of them: where a block is genuinely pure decision logic with its own state (mirroring
`SocGateResolver`), extract it into a small object in `coordinator_cycle.py`; where a block
is I/O-bound orchestration (adapter reads, or reads mixed with a call into an already-pure
engine function) with no independent state of its own, extract it into a plain private
`async def _stepN_...` method on `SmartChargingCoordinator`. Either way, `_run_cycle` itself
shrinks to a literal, top-to-bottom sequence of named calls — still directly checkable
against ADR-0006's ten steps, still with the R3/C4 clamps as two distinct calls exactly as
ADR-0006 requires, still using the `ModeHandler` registry lookup ADR-0012 already
established for mode dispatch.

- Pro: Preserves ADR-0006's auditability in full — the sequence is still literal code, not
  data a loop consumes. A step's own signature documents which `CycleContext` fields it
  touches, rather than every step sharing one `apply(ctx) -> ctx` shape.
- Pro: Naturally represents this cycle's actual (non-uniform) control flow — a step calling
  `_reset_mode_state_if_changed()` twice, or a fault check returning early, is just two
  ordinary method calls / an ordinary early `return`, not a special case bolted onto a
  generic mechanism.
- Pro: Every extracted unit — pure object or coordinator method — becomes independently
  testable at a finer grain than "run the whole coordinator," continuing the testability
  gain ADR-0012 started.
- Con: More classes/methods to navigate than one method, and two different kinds of unit
  (stateful `coordinator_cycle.py` objects vs. plain coordinator methods) to choose between
  when adding a new step — a judgment call each time, not a single uniform recipe.

### Option B — Full generic `CycleStep` pipeline (ADR-0012's Option B, revisited)

Replace the remaining inline blocks — and, for uniformity, the three ADR-0012 already
extracted — with a single list of objects sharing one `apply(ctx) -> ctx` interface,
iterated by `_run_cycle` in a loop.

- Pro: Maximum uniformity — every step has the same shape, and adding, removing, or
  reordering a step becomes a one-line change to the list rather than a code edit at a
  specific point in a function body.
- Con: ADR-0006's step order becomes an implicit consequence of the list's construction,
  not literal, readable code — the same objection ADR-0012 already raised, still
  unaddressed by anything new in this cycle's shape.
- Con: This cycle does not fit a uniform linear pipeline. `_reset_mode_state_if_changed`
  runs twice at two different points for two different reasons; a flat list of unique step
  objects cannot represent a step recurring mid-sequence without either duplicating an
  entry (confusing — is it the same step twice, or two different steps that happen to do
  the same thing?) or splitting it into two distinguishable steps that exist only to be
  runnable twice. Two fault paths return early, which a generic `apply(ctx) -> ctx` loop
  cannot express without an added abort/short-circuit signal — the moment the interface
  needs that, it is no longer the uniform interface Option B was chosen for.
- Con: `apply(ctx) -> ctx` is identical for every step by construction, so a step's own type
  signature no longer documents which `CycleContext` fields it actually reads or writes —
  a real loss of self-documentation for a control loop that commands physical charging
  current, where "what does this step depend on" is a question worth answering from the
  signature alone.
- Con: Forces steps with no history of independent variation (voltage resolution, the
  floor/cap invariant) into the same interface as steps that do vary — pure ceremony for
  those steps, the same cost ADR-0012 already declined to pay.
- Con: A stack trace through a generic loop names `apply()` on some object, one more hop
  than a stack trace through a named method that already identifies the failing step.

### Option C — Status quo: leave `_run_cycle` as one method

- Pro: Zero migration cost or risk.
- Con: Does not address the stated problem — a ~360-line method that every new
  cross-cutting concern (notifications, further deadline/urgency work) continues to grow,
  is hard to read as a whole, and leaves several genuinely testable decisions (R8 step-up
  gating, R9 reserve-cap gating, the deadline-table read-and-resolve block) untestable
  except by driving the full coordinator through an HA test harness.

## Decision

Option A. `_run_cycle` is decomposed into named units of two kinds, matching whether a
block does HA/adapter I/O (per ADR-0009/0010, I/O must stay coordinator-side) or is pure
decision logic with its own state (per ADR-0012's existing pattern):

- **Plain private coordinator methods** (`async def _step_...` on `SmartChargingCoordinator`,
  in `coordinator.py`) for I/O-bound orchestration blocks that read adapters and/or delegate
  to an already-pure engine function, with no state of their own beyond what they read this
  cycle:
  - Initial adapter reads (status/net/charger power) and voltage resolution.
  - The R14 departure-deadline read-and-resolve block shared by today's urgency and
    tomorrow's R9 precondition (external departure adapter, sun reading, low-tariff
    reading, weekday computation, and the `resolve_deadline_for` closure) — this block
    already calls the pure `resolve_departure_deadline` engine function; the method's job
    is only to gather the adapter readings and call it, matching the rationale already used
    for `resolve_deadline_urgency`'s extraction ("the adapter/HA reads... stay here;
    everything else moves to `coordinator_cycle.py`").
  - The R5/R14/R15 deadline-urgency call site's own adapter reads (today's deadline, the
    sensed battery capacity) that must stay coordinator-side even though
    `resolve_deadline_urgency` itself is already a pure `coordinator_cycle.py` function.
  - The disconnect/`Off`/`Power`/SOC-gated-stop dispatch branches that surround the
    `ModeHandler` registry lookup (the lookup itself, per ADR-0012, is untouched).
  - The two clamp calls (R3, C4) and the floor/cap invariant — each becomes its own named
    call at its existing call site, still two distinct calls per ADR-0006, still with only
    the R3 call gated by the R17 opt-out; this decision does not touch clamp behavior,
    only gives each call site a name.

- **New small stateful objects in `coordinator_cycle.py`**, mirroring `SocGateResolver`, for
  blocks that are genuinely pure decision logic once their few required inputs are supplied:
  - R8 solar step-up gating (`is_solar_mode_charging` plus the call into
    `resolve_solar_step_up`, threading `self._step_up_state`) — the coordinator method
    supplies the current mode/status/profile; the object owns the gating decision and the
    state.
  - R9 solar-reserve-cap gating (the call into `resolve_solar_reserve_active`) — the
    coordinator method supplies the read values (forecast, deadline-tomorrow result); the
    object owns the gating decision.

`CycleContext` remains the shared data carrier ADR-0012 established; each new unit reads
from and writes to it exactly as `SocGateResolver`/`PeakDemandState` already do, at the same
points in the sequence where the corresponding field is assigned today (no reordering).
Mode dispatch continues to route through the `ModeHandler` registry ADR-0012 established;
this decision does not reopen how modes are looked up, only names the surrounding branches
that decide *whether* to look up a handler at all. The R3/C4 clamp separation from ADR-0006
is unchanged and unaffected.

This choice is made over Option B because this cycle's actual control flow — a step that
recurs mid-sequence, two early-return fault paths, an opt-out that must never reach a
second clamp — does not fit a uniform linear pipeline without either hiding that shape
inside added special-case machinery or forcing every step through an interface that erases
which data it depends on. It is made over Option C because the stated problem (a
360-line method, untestable-except-through-the-full-coordinator decision blocks, growing
edit surface) is real and worsening.

## Consequences

- `_run_cycle` becomes a short, literal sequence of named calls — still checkable line by
  line against ADR-0006's ten steps, still with two distinct clamp calls, still dispatching
  through the `ModeHandler` registry.
- Two new stateful units are added to `coordinator_cycle.py` (R8 step-up gating, R9
  reserve-cap gating), independently pytest-testable the same way `SocGateResolver` already
  is — no HA harness required for either.
- Several new plain private methods are added to `coordinator.py`; being I/O-bound, they
  are tested the same way the rest of `coordinator.py` is today — via the existing HA-harness
  regression suite (`tests/test_coordinator.py`), not new pure-unit tests. Adding a pure-unit
  test at the coordinator-method level is possible only for whatever pure decision each
  method delegates to, not the method itself.
- Choosing between the two unit kinds is a judgment call at extraction time, not a fixed
  recipe — a future contributor adding a new step still has to ask "does this touch an
  adapter" the way this ADR's own Decision section had to.
- Follow-up: a `docs/plans` implementation spec and TDD task plan, the same pattern
  ADR-0012 used, is the next step — this ADR does not itself implement any code change, and
  the exact method names, boundaries, and test list are implementation-spec-level detail,
  not part of this decision.
- If a future addition reveals a step whose extraction doesn't fit either unit kind cleanly,
  that is a new decision to make at that time, the same escape hatch ADR-0012 left open and
  this ADR does not close.
