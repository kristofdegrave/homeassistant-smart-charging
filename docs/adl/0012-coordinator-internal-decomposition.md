# ADR-0012: Coordinator internal decomposition (Strategy + extracted state owners)

Date: 2026-07-23
Status: Proposed

## Context

ADR-0006 fixes the control cycle's *step order* and requires that order to stay visible
as an explicit sequence in `coordinator.py`, with the R3 peak-clamp and C4
grid-ceiling-clamp remaining two distinct call sites. It says nothing about how each
step's *own* logic is organized inside `coordinator.py` — that was out of scope for that
decision.

Today, `SmartChargingCoordinator._run_cycle` implements all ten of ADR-0006's steps
inline in one ~220-line method (`coordinator.py:162-382`), with all cross-step data held
in local variables and instance fields. Three specific spots have grown Single
Responsibility / Open-Closed problems as the integration has added modes and engines:

- **Mode dispatch** (`coordinator.py:278-334`) is an `if/elif` chain matched on
  `active_mode` string constants, one branch per mode module (`off`, `power`, `solar`,
  `solar_only`, `captar`), plus the disconnect/SOC-gate stop-charging branches that share
  the same chain. Adding a fifth mode means editing this chain, even though each mode
  module (`modes/*.py`) is already a self-contained pure function per ADR-0006's own "no
  direct HA or adapter access" rule — the per-mode branches are the piece not yet
  decoupled into a lookup; the disconnect/stop-charging branches are coordinator
  orchestration and are out of scope for this decision.
- **Monthly-peak-demand tracking state** (`_peak_window`, `_peak_tracked_kw`,
  `_peak_tracked_month`) is three loose instance fields, mutated by hand inline in
  `_run_cycle`, even though the tracking *logic* already lives in
  `engines/peak_demand_tracker.py` as pure functions. The coordinator owns the state but
  not as a single cohesive object with its own update operation. This is a distinct
  concern from `_peak_tracker` (a `PeakBreachTracker` from `engines/billing_protection.py`)
  — that field is the R3 peak-clamp's own breach-timer state, consumed only by the step-7
  clamp, and is left untouched by this decision; it is not part of the monthly-peak
  bookkeeping this ADR extracts.
- **SOC-gate resolution** (`coordinator.py:244-275`) — resolving the active SOC limit and
  detecting whether it changed since the last cycle — is inlined in `_run_cycle` alongside
  unrelated steps, even though it is a single, separable, pure responsibility (resolve,
  then report whether it changed). Firing the resulting `ActiveSocLimitChanged` event is
  HA I/O and stays the coordinator's job, per ADR-0009/0010's rule that only the
  coordinator side does HA I/O — extracting it into the same object as the pure
  resolution would blur that boundary.

As more modes, engines, and cross-cutting concerns (deadline/SOC management, Captar,
notifications) land, each addition currently means editing `_run_cycle` itself rather
than registering a new unit of behavior — the coordinator accretes edits proportional to
every new capability instead of just the capabilities that are genuinely
control-cycle-sequencing changes.

This decision is scoped strictly to *internal organization*: which object owns which
step's code and state. It does not touch, and must not be read as reopening, ADR-0006's
ten-step order or its requirement that the R3 and C4 clamps remain separate,
independently-skippable call sites.

## Considered options

### Option A — Leave `_run_cycle` as-is (status quo)

- Pro: Zero migration cost or risk; the ten steps already read top-to-bottom in the order
  ADR-0006 mandates, which has real value for a reviewer checking that order against the
  ADR.
- Con: The mode-dispatch `if/elif` chain, the three loose monthly-peak-tracking fields,
  and the inlined SOC-limit resolution are Open-Closed and Single-Responsibility
  violations that get
  strictly worse with every future mode or cross-cutting concern added to the cycle —
  each one is another edit to an already-220-line method rather than a new, independently
  testable unit.

### Option B — Full Chain-of-Responsibility pipeline of generic `CycleStep` objects

Replace all ten steps with a list of objects implementing one `CycleStep` interface
(`apply(context) -> context`), iterated in a loop; `_run_cycle` becomes a fixed
`for step in self._steps: context = step.apply(context)`.

- Pro: Maximum uniformity — every step, not just the three pain points, becomes an
  independently testable, independently registered object.
- Con: ADR-0006's step order stops being a directly readable sequence of named calls in
  `coordinator.py` and becomes an implicit consequence of a list's construction order
  elsewhere — exactly the failure mode ADR-0006's Option A rejected for the R3/C4 clamps
  (a single generic mechanism hiding a distinction that must stay visible). It is also a
  much larger diff than the three concrete pain points justify: steps like voltage
  resolution or the floor/cap invariant have no OCP/SRP problem today and gain only
  indirection from being wrapped in the same generic interface.

### Option C — Mode dispatch only (Strategy), leave peak-tracking and SOC-gate inline

Extract just the `ModeHandler` Strategy for mode dispatch; leave monthly-peak-tracking
fields and the SOC-gate block inline as they are today.

- Pro: Smallest possible diff; addresses the one violation most likely to recur (new
  modes are more probable near-term than new peak-tracking variants).
- Con: Leaves the other two already-identified SRP violations (monthly-peak-tracking
  state as three loose fields; SOC-limit resolution inlined with unrelated steps)
  unaddressed with no plan to revisit them, when both are already causing the same "edit
  `_run_cycle` by hand" pattern this ADR exists to stop.

### Option D — Extract four targeted units: `CycleContext`, `ModeHandler` Strategy, `PeakDemandState`, `SocGateResolver`

Introduce a `CycleContext` dataclass carrying raw/smoothed readings, voltage, and `now`
between steps (replacing ad hoc local variables); a `ModeHandler` Strategy interface with
one thin adapter per existing mode module (wrapping, not changing, `modes/*.py`'s pure
functions), looked up from a `dict[str, ModeHandler]` instead of the `if/elif` chain; a
`PeakDemandState` object owning the three monthly-peak-tracking fields (`_peak_window`,
`_peak_tracked_kw`, `_peak_tracked_month`) behind one
`update(net_w, now_dt) -> monthly_peak_kw` method, wrapping the existing
`engines/peak_demand_tracker.py` functions; and a `SocGateResolver` — a pure object, no HA
I/O — owning only SOC-limit resolution and change-detection (`resolve(...) -> (limit,
changed)`), wrapping the existing `engines/soc_target.py` functions. The coordinator
itself still fires `ActiveSocLimitChanged` when `SocGateResolver` reports a change — that
HA I/O stays on the coordinator side, per ADR-0009/0010's boundary that only the
coordinator, never a pure/engine-style unit, touches `hass.bus`. `_peak_tracker` (the R3
clamp's own breach-timer state) is untouched by this decision; it remains threaded through
the step-7 clamp call exactly as today. `_run_cycle` keeps ADR-0006's ten steps as ten
explicit calls, in order, but each call's body is now a short delegation to one of these
objects instead of inline logic.

- Pro: Directly targets the three concrete violations in Context without touching steps
  that have no such problem; ADR-0006's step order remains a literal, readable sequence
  of named calls in `_run_cycle` — nothing about the ordering becomes implicit.
- Con: Four new small classes/interfaces to learn instead of one uniform mechanism;
  a sixth or seventh similarly-shaped violation elsewhere in `_run_cycle` (should one
  emerge later) would need its own follow-up decision rather than being already covered
  by a general-purpose pipeline.

## Decision

Option D. It resolves the three violations named in Context — mode dispatch,
monthly-peak-demand state, and SOC-limit resolution — without Option B's cost of making
ADR-0006's step order implicit, and without Option A's or Option C's gap of leaving known
SRP violations unaddressed. `_run_cycle` remains, in code, the ten-step sequence ADR-0006
requires; what changes is that steps 4 (SOC-limit resolution), 6 (mode dispatch), and the
monthly-peak-demand bookkeeping folded into step 1/9 now delegate to `SocGateResolver`,
`ModeHandler` lookup, and `PeakDemandState` respectively, threading a `CycleContext`
between them instead of loose local variables. Steps 7 and 8 (the R3 peak clamp and C4
ceiling clamp) remain exactly as ADR-0006 Option B fixed them: two separate method calls,
only the first gated by the R17 opt-out, and `_peak_tracker` — the R3 clamp's own
breach-timer state, a different concern from `PeakDemandState`'s monthly bookkeeping —
stays threaded through that clamp call untouched.

`ModeHandler` implementations wrap the existing `modes/*.py` pure functions unchanged —
this decision does not touch mode-module internals, only how the coordinator looks one
up.

## Consequences

- `coordinator.py` still contains, and must continue to contain, ADR-0006's ten-step
  order as an explicit sequence of calls in `_run_cycle` — this decision changes what
  each call delegates to, not the sequence itself. A future change that collapses these
  delegations back into inline logic, or that hides the step order inside a generic loop
  (Option B), would contradict this decision as much as it would ADR-0006.
- Adding a fifth mode becomes: implement `modes/<mode>.py` (unchanged process) plus one
  `ModeHandler` adapter registered in the coordinator's dispatch dict — no edit to the
  dispatch chain itself.
- `PeakDemandState` and `SocGateResolver` are both pure, HA-free objects — no `hass.bus`
  or other HA I/O — so each is independently unit-testable with plain pytest, without
  constructing a full coordinator or an HA test harness, the same testability benefit
  ADR-0006/ADR-0009 already claim for the mode modules and the `engines/` package
  (ADR-0010). Firing `ActiveSocLimitChanged` itself remains the coordinator's job, per
  ADR-0009/0010's boundary that HA I/O lives only on the coordinator side.
- The R3/C4 clamp separation from ADR-0006 is unchanged and unaffected by this decision.
- Follow-up: a docs/plans implementation spec and TDD task plan for this refactor, once
  this ADR is accepted — the four new units, the `CycleContext` shape, and the
  before/after diff are implementation-spec-level detail, not part of this decision.
- If a future addition reveals a similarly-shaped SRP/OCP violation elsewhere in
  `_run_cycle` not covered by these four units, that is a new decision to make at that
  time, not something this ADR forecloses or pre-answers.
