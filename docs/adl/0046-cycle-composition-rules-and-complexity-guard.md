# ADR-0046: The control cycle's composition rules, held by a complexity guard (supersedes ADR-0023)

Date: 2026-09-22
Status: Accepted

## Summary

In the context of a `_run_cycle` that regrew past the size ADR-0023 decomposed, facing a rule
that said how to extract a block but nothing that stopped the next one landing inline, we
decided on named-step composition with a stated body rule and a complexity guard, to keep the
cycle a short literal sequence that fails the build when it regrows, accepting a threshold
that a large new concern meets only by adding a step, never by growing one.

## Context

[ADR-0023](0023-decompose-run-cycle-into-named-steps.md) decomposed a ~360-line `_run_cycle`
into named units of two kinds — plain coordinator methods for I/O-bound blocks, small pure
units in `coordinator_cycle.py` for gating logic with its own state — and rejected a uniform
`apply(ctx) -> ctx` pipeline (its Option B). `_run_cycle` in `coordinator.py` is ~390 lines
today, 68 statements with a cyclomatic complexity of 11; every function beside it in
`coordinator.py` and `coordinator_cycle.py` is at most 34 statements and complexity 9.

Forces:

- **ADR-0006's auditability and clamp separation.** A reviewer reads `_run_cycle` top to bottom
  against [ADR-0006](0006-coordinator-and-data-flow.md)'s ten steps; the R3 and C4 clamps stay
  two distinct calls, only R3's gated by the R17 opt-out.
- **ADR-0023 kept some of the shape on purpose.** It left in `_run_cycle`'s body the provisional
  and final `resolve_effective_peak_limit` calls, both `_reset_mode_state_if_changed` calls,
  `CycleContext` fields assigned in place with no reordering, and the final write,
  fault-recovery and `CycleResult` block. Some of that is where the regrowth sits: values are
  held both as locals and as `ctx` fields, and a new concern lands as a block beside them.
- **No mechanical check.** Nothing in the lint configuration fails on a function's size or
  branching, so ADR-0023's "short, literal sequence" was a goal no build enforced.
- **Fault cycles hold state.** Both fault exits sit upstream of state a successful cycle
  advances — the last-successful-cycle timestamp (ADR-0021), the deadline-unreachable edge
  (ADR-0024), the urgency latch — and ADR-0007 requires one fault-handling code path. A step
  moved across a fault exit changes behaviour.
- **The two resets are two points of change.** A `Manual` mode change is final before the
  cycle starts, and the baseline dry run reads per-mode state before `Auto`'s own mode is
  resolved; `Auto`'s change is known only after that resolution.
- **Comments are most of the length.** 68 statements take ~390 lines; a statement count alone
  does not see a block's reasoning growing inline.

## Considered options

### Option A — Keep ADR-0023 as it stands

- Pro: No new record, no migration beyond the extraction ADR-0023 already set out.
- Con: The regrowth happened under it: it says how to extract a block, not what may stay in
  the body, and nothing fails when a fix lands inline.

### Option B — A uniform `CycleStep` pipeline (ADR-0023's Option B)

- Pro: Every step one shape; adding or reordering a step is a one-line change to a list.
- Con: ADR-0006's order becomes a consequence of a list's construction, not literal code.
- Con: A step that recurs (the reset) and two early fault exits do not fit one
  `apply(ctx) -> ctx` shape without making an early-exit signal part of every step's return,
  and the shared signature stops saying which fields a step reads and writes — ADR-0023's
  reasons, none of which the cycle's current shape has changed.

### Option C — The complexity guard alone, over ADR-0023's shape

Enable ruff's complexity rules on the cycle's files and leave ADR-0023's choices as they are.

- Pro: The smallest change that fails the build on regrowth; no rule to interpret.
- Con: A statement count is met by moving arbitrary chunks into helpers, so the guard alone
  says nothing about where a value lives or what may stay in the body: the local-and-`ctx`
  copies and the provisional limit remain, and comments keep growing unseen.

### Option D — Named-step composition with a stated body rule, and a complexity guard

ADR-0023's two unit kinds, carried forward, plus a rule for what the body may hold, three
answers ADR-0023 gave differently or left open, and the guard of Option C to hold the result:

- **`CycleContext` is built once, right after the required-role read succeeds**, from the
  required reads and what derives from them alone (the debounced baseline). Every value a later
  step reads is a field on it, written by the step that resolves it — never also a local.
- **The provisional peak limit moves into the fault exit.** Its only consumer is the
  state-of-charge fault's result, so that exit resolves the non-urgent limit itself; the body
  resolves the effective peak limit once, after urgency, and assigns it once.
- **Both resets stay**, as two calls: each is a distinct point where the active mode can
  change, and dropping the first would give a `Manual` switch's dry run stale per-mode state.

- Pro: Every force above has an answer: the body stays auditable against ADR-0006, the fault
  exits keep holding what they hold, a value has one home, and the build fails on regrowth.
- Pro: The body rule gives the guard's number a meaning — it measures a body whose permitted
  contents are stated, not an arbitrary cut.
- Con: A threshold is a blunt limit: a large new concern must arrive as a new step even where
  inline code would read more directly, and a contributor near the limit extracts rather than
  grows.
- Con: More coordinator methods to navigate, and the step-kind judgment ADR-0023 left to each
  extraction remains.

## Decision

Option D, superseding ADR-0023: Option A leaves the regrowth unanswered, Option B trades
ADR-0006's literal order for a shape the cycle does not have, and Option C holds a size without
saying what the size is of. ADR-0023's two unit kinds, its rejection of the pipeline, and
[ADR-0012](0012-coordinator-internal-decomposition.md)'s `ModeHandler` registry lookup stand.

**`_run_cycle`'s body holds only:**

1. Calls to named steps, one statement each, whose result is written onto `ctx` or is the
   sentinel a fault test reads.
2. The two fault exits: a test of that sentinel and a literal `return` of the result a single
   fault-exit step builds — the return stays in the body, ADR-0007's one path.
3. The two `_reset_mode_state_if_changed` calls.
4. Mode dispatch, the R3 clamp, the C4 clamp and the floor/cap invariant, as four distinct calls
   in ADR-0006's order.
5. The charger write, then the return of the result a named step builds — that step also records
   the last-successful-cycle timestamp and the fault recovery, so nothing precedes the write that
   ADR-0021 requires after it.

Nothing else: no inline arithmetic or predicate, no branch other than the two fault tests, no
event fired from the body — a Home Assistant event is fired by the coordinator method that
resolves what it reports, which keeps the I/O coordinator-side (ADR-0009, ADR-0010). A comment
in the body is at most a one-line pointer; a step's reasoning is its docstring.

**No step moves across a fault exit.** What a fault cycle leaves untouched today, it leaves
untouched after any change under this record.

**The guard.** Ruff's `C901` at `max-complexity = 10` and `PLR0915` at `max-statements = 35`,
over `custom_components/smart_charging/coordinator.py` and
`custom_components/smart_charging/coordinator_cycle.py`. Ten is McCabe's own bound and ruff's
default; 35 is the smallest round figure every other function in the two files meets today,
and a body of the shape above is about 25 statements, so it fails well before it doubles. The
`development` completion bar states the gate and is where it is read; tightening either number
or adding a file is the bar's call, while loosening either or dropping one of these files
contradicts this record.

## Consequences

- Easier: reading the cycle against ADR-0006, and seeing a regrowth — it fails the lint job
  instead of reaching review. Harder: a fix that would be three inline lines becomes a named
  step, and a step near its own limit is split rather than extended.
- ADR-0023's Status reads `Superseded by ADR-0046`, and its ADL row matches, in this change.
- Follow-up:
  - The `development` completion bar gains the gate at this threshold over these files, landing
    just before the restructure.
  - `_run_cycle` is restructured to this rule, and ruff's `C901` and `PLR0915` are enabled for
    these two files in the same change, so the method cannot regrow between them.
  - `system-design.md` gains a cycle-composition account beside §5.1's account of the cycle's
    order.
- A step that fits neither unit kind, or a concern that cannot be one statement in the body,
  is a new decision, as ADR-0012 and ADR-0023 left it.

**Blast radius.** Three searches, run from the repository root:

1. `rg -n 'async def _run_cycle|CycleContext\(|resolve_effective_peak_limit\(|_reset_mode_state_if_changed\(' custom_components/`
   — the body this record governs, every construction of the carrier, every peak-limit
   resolution and every reset (13 hits). Keyed on the call forms, and run over the whole
   package, so a construction or resolution outside the coordinator is found too.
2. `rg -n '^\s*(async )?def ' custom_components/smart_charging/coordinator.py custom_components/smart_charging/coordinator_cycle.py`
   — every function the guard measures (70 hits).
3. `rg -n 'ADR-0023|0023-decompose' docs/ custom_components/ tests/ .claude/ .github/ CLAUDE.md`
   — every citation of the record this one supersedes; the dot-directories are named, since a
   root sweep skips them.

| Site | Today | Verdict |
|---|---|---|
| `coordinator.py:445` `_run_cycle` (search 1, 2) | 68 statements, complexity 11: inline blocks, events, arithmetic and the final result block in the body | Does not conform: follow-up restructure |
| `coordinator.py:511` provisional `resolve_effective_peak_limit` | Resolved in the body for the state-of-charge fault's result | Does not conform: moves into the fault exit |
| `coordinator.py:740` final `resolve_effective_peak_limit` | The one assignment to `ctx.effective_peak_limit_kw`, also kept as a local | Does not conform: the local goes |
| `coordinator.py:523`, `:784` `_reset_mode_state_if_changed()` | The two resets | Conform |
| `coordinator.py:579` `CycleContext(` | Built after smoothing, mid-cycle; values held both as locals and fields | Does not conform: built after the required-role read |
| `coordinator.py:1382` `CycleContext(` in `_mode_desired_current` | The baseline dry run's own throwaway carrier, never passed to a clamp | Conforms: not the cycle's carrier |
| `coordinator.py:1234` `resolve_effective_peak_limit(` in `_escalated_maximum_permitted_rate_a` | The escalated limit a named step resolves for urgency | Conforms: inside a step |
| `coordinator.py:1271` `def _reset_mode_state_if_changed` | The reset's definition | Conforms |
| `engines/billing_protection.py:40` `def resolve_effective_peak_limit` | The pure engine function | Conforms |
| `coordinator.py:744`, `:909`; `sensor.py:211` | A comment or docstring naming the resolution or the reset | Conform: prose, not a call |
| Every other function in search 2 (69 hits) | At most 34 statements and complexity 9 | Conform |
| `coordinator.py`, `coordinator_cycle.py`, `tests/test_coordinator.py`, `tests/test_coordinator_cycle.py` (search 3: 16 hits) | Cite ADR-0023 for an extraction this record carries forward | Conform: the citation resolves and the extraction stands |
| `docs/design/project-plan.md:298, 322, 468, 473` (search 3) | Cite ADR-0023 as the cycle's decomposition | Conform: the record resolves; re-pointing is the follow-up design change's call |
| `docs/adl/README.md` (search 3: 2 hits) | ADR-0023's ADL row, and this record's | Both written in this change |

Out of scope:

- **`docs/adl/0023-decompose-run-cycle-into-named-steps.md`, `0036-*`, `0037-*`** (search 3):
  Accepted records; ADR-0023 changes only its Status line, the others keep citing it.
- **This record** (search 3): it states the supersession.
- **`docs/plans/**`** (search 3): a retired tree (ADR-0044); its files keep their text.
