# ADR-0010: Package home for the cross-cutting engines

Date: 2026-07-17
Status: Accepted

## Context

ADR-0002 fixed the package layout for `custom_components/smart_charging/`: the
subpackages `adapters/`, `modes/`, `profiles/`, the platform files and `entity.py` at the
package root, and `coordinator.py` driving the control cycle. That layout gave a home to
the Resource-Access layer (`adapters/`), the Charging-Mode Engines (`modes/`), and the
Profile Engines (`profiles/`) — but to no other engine.

The volatility-based decomposition in `docs/design/system-design.md` surfaced **eight
further engines** that ADR-0002 left homeless: SOC-Target, Deadline, Billing-Protection,
Grid-Safety, Signal-Conditioning, Cycle-Invariant, Capability-Gate, and the Peak-Demand
Tracker (system-design §3, §8 follow-up). `docs/design/project-plan.md` §3 records this as
gate **G-ADR-0010**, which blocks build tasks E3–E9. This ADR extends ADR-0002 to place
those eight; it does not change where `adapters/`, `modes/`, or `profiles/` live.

Three forces constrain the choice:

- **The engine-purity boundary must stay structural, not conventional.** system-design §4
  rule 4 requires that no engine performs Home Assistant / adapter I/O and no engine calls
  another engine; ADR-0006 states the same for mode modules ("pure functions/classes …
  no direct HA or adapter access"), and ADR-0009 relies on exactly that boundary to
  unit-test engine logic with plain pytest, no HA harness. Wherever the eight engines
  live, a test importing one must not be able to pull in `homeassistant.*` — the same
  guarantee `modes/` and `profiles/` already give.
- **Three of the eight are stateful.** Signal-Conditioning (the R10 smoothing window),
  Cycle-Invariant (the R11 cooldown/hold timers), and the Peak-Demand Tracker (the running
  monthly peak) operate over cross-cycle state. Per system-design §3, that state is
  **owned and threaded in/out by the Manager** — it is a function parameter, never
  HA-held inside the engine. The layout must accommodate stateful and pure engines side by
  side without either becoming a place where HA state could hide.
- **`tests/` mirrors the package 1:1** (ADR-0002, ADR-0009). Where the engines live
  dictates where their plain-pytest test modules live, so the layout must make that
  mapping obvious.

## Considered options

### Option A — A single `engines/` subpackage, one module per engine

A new `engines/` subpackage, sibling to `adapters/`, `modes/`, and `profiles/`, with one
module per engine: `soc_target.py`, `deadline.py`, `billing_protection.py`,
`peak_demand_tracker.py`, `grid_safety.py`, `signal_conditioning.py`, `cycle_invariant.py`,
`capability_gate.py`. `tests/engines/` mirrors it 1:1.

- Pro: Mirrors ADR-0002's existing pattern exactly — `modes/` and `profiles/` are already
  subpackages of pure, HA-free logic with one self-contained module per unit; a reader who
  knows those immediately knows where a third such family lives, and `tests/engines/`
  follows the same mirror rule. The directory boundary is the purity guard: a module under
  `engines/` sits with no HA-coupled sibling, so a test importing `engines.soc_target`
  structurally cannot import `homeassistant.*`, the same guarantee `modes/`/`profiles/`
  give. Eight sibling modules are directly scannable.
- Con: The flat listing does not itself show which three engines are stateful — a reader
  must open the module (or its signature) to learn Signal-Conditioning threads a smoothing
  window. It also groups nothing: Billing-Protection and the Peak-Demand Tracker, both the
  V6 billing concern, are siblings with no marker that they pair.

### Option B — Group by concern/volatility inside `engines/` (e.g. `billing/`, `safety/`, `conditioning/`)

A nested `engines/` whose immediate children are concern groups
(`engines/billing/{billing_protection,peak_demand_tracker}.py`,
`engines/safety/grid_safety.py`, `engines/conditioning/signal_conditioning.py`, …), each
grouping the engines of one volatility.

- Pro: Expresses the volatility grouping structurally, and co-locates the one genuine pair
  — Billing-Protection and the Peak-Demand Tracker (both V6), which project-plan §5 bundles
  into task E5 — in a single `billing/` directory.
- Con: Six of the eight engines map to exactly one volatility each (SOC-Target = V4,
  Deadline = V5, Grid-Safety = V7, Signal-Conditioning = V8, Cycle-Invariant = V9,
  Capability-Gate = V10), so most "groups" would be a directory holding a single module —
  nesting with no grouping payoff, for the sake of one real pair. It over-structures ahead
  of need, deepens import paths, is harder to scan, and breaks the flat
  one-module-per-unit parity ADR-0002 set for `modes/` and `profiles/`.

### Option C — Top-level modules alongside `coordinator.py`, no new package

Place the eight engines as top-level modules in the package root
(`custom_components/smart_charging/soc_target.py`, `deadline.py`, …), next to
`coordinator.py`, `entity.py`, and the platform files.

- Pro: Fewer directories; the engines sit directly beside the Coordinator that composes
  them, so a reader tracing the control cycle finds them without descending into a
  subpackage.
- Con: It puts pure, HA-free engine logic in the **same namespace** as the most HA-coupled
  code in the package — `coordinator.py` (a `DataUpdateCoordinator`), `entity.py`, and the
  platform files (`select.py`, `number.py`, …). That is precisely the leak ADR-0002
  rejected in its own Option A: nothing structurally stops `soc_target.py` from importing
  `homeassistant.*` when its neighbors already do, so the ADR-0006/0009 purity boundary
  degrades from structural to conventional. It also breaks parity — two smaller families of
  pure logic (`modes/`, `profiles/`) get a subpackage while a larger third does not — and
  makes `tests/` placement ambiguous (engine tests would sit in the `tests/` root beside
  the HA-harness `test_coordinator.py`, blurring ADR-0009's plain-pytest vs. HA-harness
  split).

### Option D — A single `engines/` subpackage split by state (`engines/pure/`, `engines/stateful/`)

A new `engines/` subpackage whose two children partition the engines by kind:
`engines/pure/` (SOC-Target, Deadline, Billing-Protection, Grid-Safety, Capability-Gate)
and `engines/stateful/` (Signal-Conditioning, Cycle-Invariant, Peak-Demand Tracker).

- Pro: Makes the pure/stateful distinction — a real axis in system-design §3 — visible in
  the directory tree, so a reader sees at a glance which engines carry threaded state.
- Con: The distinction is already carried where it matters — in each engine's signature
  (a stateful engine takes state in and returns it out; a pure one does not). Encoding it
  in the tree adds a second source of truth that can drift if an engine gains or sheds
  state, forcing a file move for what is really a signature change. It also splits the
  billing pair (Billing-Protection pure, Peak-Demand Tracker stateful) across two
  directories, and deepens import paths for a fact the type signatures already state.

## Decision

Option A. Add a single `engines/` subpackage under `custom_components/smart_charging/`,
sibling to `adapters/`, `modes/`, and `profiles/`, with **one module per engine**:
`soc_target.py`, `deadline.py`, `billing_protection.py`, `peak_demand_tracker.py`,
`grid_safety.py`, `signal_conditioning.py`, `cycle_invariant.py`, `capability_gate.py`.
`tests/engines/` mirrors it 1:1, following ADR-0002's mirror rule and ADR-0009's
plain-pytest boundary.

Option A is chosen because it reuses the exact structural device ADR-0002 already proved
for `modes/` and `profiles/`: a subpackage of pure logic whose directory boundary *is* the
purity guard, keeping the ADR-0006/0009 "no HA I/O in an engine" boundary structural rather
than conventional — the payoff Option C forfeits by mixing engines into the HA-coupled root
namespace. The stateful engines need no special home because their state is a threaded
parameter, not HA-held state (system-design §3): a stateful engine is just another module
in `engines/`, its state visible in its signature — which is why the state-based split of
Option D adds a second, drift-prone source of truth for a fact the signatures already
carry. Option B's concern grouping is rejected as premature: only one volatility (V6) owns
more than one engine, so grouping would produce mostly single-module directories, trading
ADR-0002's flat one-module-per-unit parity for nesting that buys nothing today. The V6 pair
(Billing-Protection + Peak-Demand Tracker) stays two sibling modules in `engines/`; their
relationship is recorded by project-plan task E5 bundling them, not by a directory.

## Consequences

- The integration package gains a fourth logic/access subpackage, `engines/`, joining
  `adapters/`, `modes/`, and `profiles/`; `coordinator.py`, `entity.py`, and the platform
  files stay at the package root, unchanged. ADR-0002 is **extended, not superseded** — it
  named `adapters/`/`modes/`/`profiles/` and left the other engines open; this ADR fills
  that gap without altering any of its decisions.
- Every future cross-cutting engine gets its own module in `engines/` and a mirrored
  `tests/engines/test_<engine>.py` (ADR-0009), one self-contained unit per engine — the
  same rule ADR-0002 set for a new mode or profile.
- The purity boundary the ADR-0006/0009 test strategy depends on is preserved
  structurally: engine modules live with no HA-coupled sibling, so their plain-pytest tests
  cannot import `homeassistant.*`. A stateful engine takes its cross-cycle state as a
  parameter threaded by the Manager (system-design §3); it holds no HA state itself.
- This unblocks gate **G-ADR-0010** in `docs/design/project-plan.md` §3, releasing build
  tasks **E3–E9** (the eight cross-cutting engines; E5 bundles Billing-Protection with the
  Peak-Demand Tracker). Tasks E1 (`modes/`) and E2 (`profiles/`) were never blocked, having
  ADR-0002 homes.
- If `engines/` later grows large enough that concern grouping earns its keep (a second
  volatility acquiring multiple engines, say a home-battery capability adding several),
  regrouping toward Option B becomes worth revisiting — this decision does not foreclose
  it, it just isn't justified by a single pair today.
- This ADR closes the G-ADR-0010 gate. The remaining system-design §8 follow-up,
  candidate ADR-0011 (cross-Manager domain events), is a separate decision and is
  untouched here.
