# ADR-0037: Scenario/timeline test tier — a third harness alongside ADR-0009's two (extends ADR-0009)

Date: 2026-09-10
Status: Proposed

## Context

[ADR-0009](0009-testing-strategy.md) names exactly two test tiers and justifies the split
between them: plain pytest for the HA-free domain logic (`modes/`, `profiles/`, `engines/`),
and `pytest-homeassistant-custom-component` for adapters, the coordinator pipeline, and
entities. Its Consequences frame placement as a binary choice — a module either can or cannot
import `homeassistant.*`, and that answers which harness its tests use. There is no third
answer.

The suite has since grown four end-to-end suites that drive the real stack —
`hass.config_entries.async_setup` plus `coordinator.async_refresh()`, not a mode's `step`
function: `tests/test_solar_end_to_end.py` (UC01/UC02), `tests/test_captar_end_to_end.py`,
`tests/test_deadline_soc_management_end_to_end.py`, and
`tests/test_notifications_end_to_end.py`, ~1340 lines in total. They live in ADR-0009's
HA-harness tier and they do their job. But three properties are common to all four, and each
is deliberate rather than an oversight:

- **One engine at a time.** Three of the four call `seed_ample_peak_headroom(coordinator)` to
  pre-seed a large historical peak, which switches R3's peak clamp off so the mode under test
  is the only thing shaping the commanded current. That isolation is what makes a failure in
  `test_solar_end_to_end.py` name Solar rather than name the system.
- **A handful of cycles, not a timeline.** The deepest suite
  (`test_deadline_soc_management_end_to_end.py`) reaches 20 `async_refresh()` calls across all
  of its tests; the solar and CapTar suites run two apiece per test.
- **Instantaneously self-consistent readings.** Each cycle seeds `net_w` and `charger_w`
  together, at values that already agree. `test_solar_end_to_end.py::_cycle_from_feedback`
  hand-rolls the one exception — `charger_w = last_commanded * voltage`,
  `net_w = charger_w - solar_w` — closing the loop for a single mode, with zero sensor lag, in
  one suite.

Three forces bear on whether that is enough.

**The observed bug shape.** One defect class (issue #990) is a transient, artificially
negative `baseline_w` (`net_w - charger_w`) for one cycle after a charger current step-down,
inflating R3's peak headroom and producing a phantom positive solar surplus after dark. It was
diagnosed by a human overlaying two sensors' history on a live install, and its fix
(`debounce_baseline_w`, threaded through `CycleContext.baseline_w`) was verified by a targeted
engine test plus a coordinator-cycle regression test — entirely inside ADR-0009's existing two
tiers. The same class then turned out to have a second instance (issue #992): C4's
`clamp_to_ceiling` re-derives `net_w - charger_w` itself and carries the identical exposure, in
the clamp whose own docstring says it is "never skippable, no opt-out of any kind". That second
instance was identified by a reviewer reading the first one's diff — not by any test. That is
the cost being weighed: not that the current tiers cannot catch this class, but that they catch
one instance per live observation, and nothing re-checks the remaining call sites, modes, or
use-cases for the same class once it is known.

**Where a contributor would put such a test today.** A test that needs every engine live over
many consecutive cycles against readings that lag has no home in the taxonomy. It lands in
whichever existing suite is nearest, where it either breaks that suite's single-engine
isolation or gets its lag model hand-rolled locally — `_cycle_from_feedback` again, once per
suite.

**Any oracle for such a test has to be something production does not already enforce.**
`engines/cycle_invariant.py` (E8, `apply_floor_cap`) is a production clamp applied inside every
cycle: it guarantees C1 — the commanded current is 0 A or within `[min, max]`. A test asserting
C1 over a scenario's cycles would pass because E8 ran, telling us nothing about whether E8 was
called at the right point or whether anything upstream was wrong.

## Considered options

### Option A — A third scenario/timeline tier, judged by per-cycle invariants

Multi-cycle runs with every engine live and none neutralized, driven by a test-only plant
simulator (charger obeys a commanded current after a lag, meter derives `net_w` from true draw
against a solar/house-load curve, SOC integrates delivered energy, exogenous events scheduled
on the same timeline), judged by a shared invariant set checked on every cycle plus a few
per-scenario intent assertions.

- Pro: gives the temporal/whole-stack bug class a standing oracle instead of a per-instance
  live observation. Because the invariant set runs against *every* scenario, a newly understood
  class is re-checked everywhere at once — the #992 shape (same defect, second call site,
  found only because someone read the diff) becomes a test failure rather than a review catch.
  The lag and feedback model exists in exactly one place rather than being hand-rolled per
  suite, and scenarios script the *world* (solar curve, tariff windows, departure) rather than
  the readings, so a scenario author reproduces a lag-driven bug without having to know that
  bug exists.
- Con: ADR-0009's own accepted Con — a contributor must know which idiom applies to a given
  module — gets strictly worse: three answers instead of two, and the boundary is genuinely
  fuzzy exactly where the four existing end-to-end suites sit. A test-only simulator is itself
  code that can be wrong, and a wrong simulator produces confident failures against correct
  product code (or, worse, confident passes), which costs more triage than having no test.
  Runtime grows multiplicatively — many cycles × all engines live × eventually one scenario per
  use-case — so the suite may need its own marker or CI job rather than riding along.

### Option B — Grow the existing HA-harness end-to-end suites; no new tier

Extend the four `test_*_end_to_end.py` suites to run longer, keep every engine live, and model
lag inline, leaving ADR-0009's two-tier taxonomy untouched.

- Pro: nothing new for a contributor to learn — no third placement rule, no new taxonomy, no
  new harness. The mechanism is demonstrably expressible in the current harness already:
  `_cycle_from_feedback` closes the commanded-current → `charger_w` → `net_w` → surplus loop
  today. And this option is not merely adequate on paper — #990 was in fact found and fixed
  within these tiers, so the status quo plus incremental growth has a real track record.
  Cheapest option by a wide margin.
- Con: the three properties above are constitutive of what those suites are *for*, not
  accidental limits. Each is scoped to one use-case and neutralizes the other engines
  deliberately so that a failure names one mode; taking that away makes every failure in them
  ambiguous and destroys the diagnostic value they currently have. The shared invariant set
  also has nowhere to live — it would be re-asserted in four (eventually twelve) places or, in
  practice, not at all — and with no named tier the lag model gets re-hand-rolled per suite,
  the `_cycle_from_feedback` duplication multiplied by the number of use-cases.

### Option C — No scenario testing; status quo of review plus per-engine tests

- Pro: zero new code, and therefore zero new code that can be wrong. The existing tiers plus
  review are catching real defects, and the single highest-yield oracle to date has been a
  human reading a live install's history graphs — something no test tier replaces.
- Con: the demonstrated cost is the two-instance `baseline_w` shape above. A defect class
  reaches a live install, gets fixed at the one call site that was observed, and its twin at a
  second call site — in the more safety-critical of the two clamps — surfaces only because a
  reviewer happened to look. Every further instance costs another live-install observation, and
  there is no artifact that would fail if a third call site has the same shape.

### Option D — A scenario tier judged by golden/approval snapshot files

Same simulator as Option A, but the oracle is a recorded cycle-by-cycle trace per scenario,
compared on each run.

- Pro: the cheapest oracle to author, and the broadest — record once and *any* behavior change
  shows up as a diff, including changes nobody thought to assert in advance, which a fixed
  invariant set by definition misses.
- Con: `_ai-fix.yml` can reach green by regenerating the snapshot — a one-command path that
  lets the fix pipeline silently bless a regression, with no equivalent escape hatch for an
  invariant. Compounding that, a legitimate behavior change produces a large multi-cycle diff
  that a reviewer is structurally likely to rubber-stamp, so the broad coverage the Pro claims
  degrades precisely when it is being exercised.

## Decision

Option A, as an **extension** of ADR-0009 rather than a supersession. Nothing in ADR-0009 has
stopped being true: its reasoning for why mode/profile/engine logic is plain-pytest, and why
adapters and the coordinator need the HA harness, holds unchanged, and both tiers keep their
existing contracts. What changes is only that placement is no longer binary. This follows the
same pattern as ADR-0023 extending ADR-0012 and ADR-0034 extending ADR-0021; supersession is
reserved for a decision that no longer holds, which is not the case here.

**Placement rule.** Three answers, in order of what the test needs:

1. **Plain pytest** — HA-free pure logic in `modes/`, `profiles/`, `engines/`. Unchanged from
   ADR-0009.
2. **HA harness (existing tier)** — adapters, the coordinator pipeline, entities, config flow,
   and per-use-case end-to-end runs: one use-case or one engine under test, the others
   deliberately neutralized, a few cycles, asserting the commanded current against a named
   requirement or UC criterion. A test whose question is *"does this mode do the right thing
   through the real wiring"* belongs here.
3. **Scenario/timeline tier** — every engine live and none neutralized, a timeline of many
   consecutive cycles, the *world* scripted (solar curve, tariff windows, departure time,
   scheduled exogenous events) with readings derived by the plant simulator including its
   configured lag, judged by the shared invariant set plus a few scenario-intent assertions. A
   test whose question is *"does the whole stack stay correct over time as the engines interact
   and readings lag"* belongs here.

**The four existing `test_*_end_to_end.py` suites stay exactly as they are** — not migrated,
not superseded, not retrofitted onto the simulator. Their single-engine isolation is the
property that makes their failures diagnostic, and answering "which mode is wrong" is a
different and still-needed job from answering "did the system stay correct". A scenario failure
says the system misbehaved; a Solar end-to-end failure says Solar misbehaved. Accordingly,
`_cycle_from_feedback` is left in place and is not extracted into the simulator: this decision
adds a tier, it does not refactor the existing one. Option B's Pro (nothing new to learn) is
paid for here in the placement rule above being explicit rather than in avoiding the tier.

**The invariant-oracle rule.** An invariant earns a place in the shared set only if nothing in
production enforces it. E8's C1 floor/cap is the reference counter-example: asserting it in a
scenario would pass because E8 ran, so it tests the assertion rather than the system. The
invariants that qualify are properties of a *sequence*, or comparisons against ground truth the
production code structurally cannot see — headroom measured against the simulator's *true*
charger draw rather than the lagged reading (the #990/#992 class), a cooldown surviving a mode
switch (#974), a latch resetting per occasion rather than per reload (#546), bounded
oscillation. The first of those is the clearest case: true instantaneous draw is exactly what
the coordinator does not have, which is what lets the tier be an oracle rather than a mirror of
the code under test.

**The plant simulator is test-only; product code takes no dependency on it.** That is what
places its internals — its structure, its numeric model, any library it calls — under
CLAUDE.md's test/CI/dev-tooling carve-out, i.e. outside ADR scope and inside the tier's
implementation spec. What is ADR-scoped is only what this record settles: that the tier exists,
where a contributor puts a test, and what a passing scenario is allowed to mean. That split is
the same one ADR-0009 itself draws: a test-tier taxonomy is architectural because it binds where
all future test code goes and what a green suite means, while the tooling a given tier happens
to call is not (compare ADR-0026/ADR-0029, which record a measurement dependency the perf tests
take, not a taxonomy).

Option D is rejected on its Con: an oracle the fix pipeline can regenerate is not an oracle
under `_ai-fix.yml`. Its Pro is genuinely forfeited — behavior changes outside the invariant set
go uncaught — and the accepted mitigation is that each newly understood bug class becomes a
candidate invariant, growing the set over time, rather than adding a snapshot layer later.
Option C is rejected because the second `baseline_w` instance being caught by a reader rather
than by a test shows the status quo's cost is already being paid. Option B is rejected because its Con is structural: the isolation it would have to give up
is the same isolation that gives the existing suites their diagnostic value.

## Consequences

- **The tier's harness is designed, not decided, here.** The paired implementation spec owns
  the simulator and invariant-runner design, and must settle two questions this ADR
  deliberately leaves open: how simulated time relates to the coordinator's update interval,
  and whether the simulator's outputs reach HA state through `tests/helpers.py`'s existing
  `seed_charger_states` path or replace it.
- **Two contributor-facing documents become stale the moment the tier lands** and need updating
  in the same strand: `.claude/skills/write-tests/SKILL.md` (its frontmatter description and its
  "Choose the harness first (ADR-0009)" section both state the split as two-way) and
  `docs/reference/definition-of-done.md`'s "Tests green" bullet (same two-way phrasing). A
  `workflow` issue for that pair is follow-up work this decision creates.
- **The first scenario targets C4's exposure, not R3's.** R3's clamp already reads a debounced
  `baseline_w` while C4's `clamp_to_ceiling` still re-derives its own, so the first scenario's
  value is the *invariant* that holds for both clamp call sites — and that would fail for a
  third if one appears — rather than a reproduction of the already-fixed R3 instance. This
  narrows the original bug-first framing, which assumed the harness would be built before
  either fix existed.
- **Snapshot/approval testing is foreclosed for this tier.** Introducing one later contradicts
  this record and needs a superseding ADR, not an addition.
- **Suite runtime becomes a budget question.** Many cycles × all engines live × eventually one
  scenario per use-case may warrant a pytest marker or a separate CI job; that is a
  dev-tooling choice for the spec, but it is a cost this decision knowingly incurs.
- **A wrong simulator is a new failure mode** with no analogue in the existing tiers: a false
  failure indicts correct product code. The mitigation this decision relies on is the bug-first
  sequencing — the simulator's lag model is validated by reproducing an already-diagnosed real
  defect before any speculative scenario is written.
- **Status flips to Accepted** once the harness and first scenario land; it is Proposed while
  the tier does not yet exist.
