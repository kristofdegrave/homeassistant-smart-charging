# ADR-0037: Scenario/timeline test tier — a third tier alongside ADR-0009's two (extends ADR-0009)

Date: 2026-09-10
Status: Proposed

## Context

[ADR-0009](0009-testing-strategy.md) names exactly two test tiers and justifies the split
between them: plain pytest for the HA-free domain logic (`modes/`, `profiles/`, `engines/`),
and `pytest-homeassistant-custom-component` for adapters, the coordinator pipeline, and
entities. The specific reading this record narrows is the placement rule in ADR-0009's Decision
and Consequences, which treats the choice as binary — a module either can or cannot import
`homeassistant.*`, and that answers which harness its tests use. There is no third answer to
"where does this test go".

The suite has since grown three end-to-end suites that drive real control cycles —
`hass.config_entries.async_setup` plus `coordinator.async_refresh()`, not a mode's `step`
function: `tests/test_solar_end_to_end.py` (UC01/UC02), `tests/test_captar_end_to_end.py`, and
`tests/test_deadline_soc_management_end_to_end.py`, 1108 lines in total. (A fourth suite,
`tests/test_notifications_end_to_end.py`, also drives the full stack but drives no control
cycles of its own and asserts nothing about the control path — it advances the real
`async_track_time_interval` tick with `freezer` and `async_fire_time_changed` to exercise M3's
dispatch, so none of what follows describes it.) The three cycle-driving suites live in
ADR-0009's HA-harness tier and they do their job. But three properties are common to all three,
and each is deliberate rather than an oversight:

- **One engine at a time.** All three pre-seed the tracked monthly peak
  (`seed_ample_peak_headroom`) so R3's headroom is non-binding on the commanded current — the
  clamp still runs every cycle, it just never bites, so the mode under test is the only thing
  shaping the result. That single-engine focus is what makes a failure in
  `test_solar_end_to_end.py` name Solar rather than name the system.
- **A handful of cycles, not a timeline.** No single test in any of the three exceeds six
  cycles: the deepest is `test_solar_end_to_end.py`'s
  `test_uc01_2b_restart_debounce_gates_a_later_idle_crossing` at 6, with three further solar
  tests at 5, and a maximum of 4 in each of the CapTar and deadline/SOC suites.
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
the clamp whose own coordinator step method is documented as "never skippable, no opt-out of any
kind". That second instance was identified by a reader of the first one's diff, not by any test.
That is the cost being weighed: not that the current tiers cannot catch this class, but that
they catch one instance per live observation, and nothing re-checks the remaining call sites,
modes, or use-cases for the same class once it is known.

**Where a contributor would put such a test today.** A test that needs every engine live over
many consecutive cycles against readings that lag has no home in the taxonomy. It lands in
whichever existing suite is nearest, where it either breaks that suite's single-engine focus or
gets its lag model hand-rolled locally — `_cycle_from_feedback` again, once per suite.

**Any oracle for such a test has to be more than a re-run of the code under test.**
`engines/cycle_invariant.py` (E8, `apply_floor_cap`) is a production clamp applied on the write
path of every cycle: it guarantees C1 — the commanded current is 0 A or within `[min, max]`. A
scenario that re-derives C1 from the same value E8 just produced passes because E8 ran, and
learns nothing. The distinction that matters is not *whether production enforces the property*
but *whether the assertion is computed by the same code path that produced the value* — because
"E8 is still applied on every path that writes a current" is a real and checkable property that
a future refactor could break, while "the number E8 returned satisfies E8" is not.

## Considered options

### Option A — A third scenario/timeline tier, judged by per-cycle invariants

Multi-cycle runs with every engine live and binding, driven by a test-only plant
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
  fuzzy exactly where the three existing cycle-driving end-to-end suites sit.
- Con: a test-only simulator is itself code that can be wrong, and a wrong simulator produces
  confident failures against correct product code (or, worse, confident passes), which costs
  more triage than having no test.
- Con: runtime grows multiplicatively — many cycles × all engines live × eventually one scenario
  per use-case — so the suite may need its own marker or CI job rather than riding along.

### Option B — Grow the existing HA-harness end-to-end suites; no new tier

Extend the three cycle-driving `test_*_end_to_end.py` suites to run longer, keep every engine
live, and model lag inline, leaving ADR-0009's two-tier taxonomy untouched.

- Pro: nothing new for a contributor to learn — no third placement rule, no new taxonomy. The
  mechanism is demonstrably expressible in the current harness already:
  `_cycle_from_feedback` closes the commanded-current → `charger_w` → `net_w` → surplus loop
  today. And this option is not merely adequate on paper: R3's `baseline_w` defect was diagnosed
  and its fix regression-tested entirely within these two tiers, so the status quo plus
  incremental growth has a real track record. Cheapest option by a wide margin.
- Con: the three properties above are constitutive of what those suites are *for*, not
  accidental limits. Each is scoped to one use-case and keeps the other engines non-binding
  deliberately so that a failure names one mode; taking that away makes every failure in them
  ambiguous and destroys the diagnostic value they currently have. The shared invariant set
  also has nowhere to live — it would be re-asserted in three (eventually twelve) places or, in
  practice, not at all — and with no named tier the lag model gets re-hand-rolled per suite,
  the `_cycle_from_feedback` duplication multiplied by the number of use-cases.

### Option C — No scenario testing; status quo of review plus per-engine tests

Leave the taxonomy and the suites exactly as they are, and keep relying on code review, the
per-engine plain-pytest suites, and observation of live installs to surface this bug class.

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

Option A, as an **extension** of ADR-0009 rather than a supersession: this record narrows
ADR-0009's placement rule — the reading that a test's home follows from whether its subject can
import `homeassistant.*` — and leaves the rest of that decision intact. ADR-0009's reasoning for
why mode/profile/engine logic is plain-pytest, and why adapters and the coordinator need the HA
harness, holds unchanged, and both existing tiers keep their contracts. Supersession is reserved
for a decision that no longer holds, which is not the case here; this follows the same pattern as
ADR-0023 extending ADR-0012 and ADR-0034 extending ADR-0021.

**Placement rule.** Three answers, in order of what the test needs:

1. **Plain pytest** — HA-free pure logic in `modes/`, `profiles/`, `engines/`. Unchanged from
   ADR-0009.
2. **HA harness (existing tier)** — adapters, the coordinator pipeline, entities, config flow,
   and per-use-case end-to-end runs: one use-case or one engine under test, the others held
   non-binding, a few cycles, asserting the commanded current against a named requirement or UC
   criterion. A test whose question is *"does this mode do the right thing through the real
   wiring"* belongs here.
3. **Scenario/timeline tier** — every engine live and binding, a timeline of many consecutive
   cycles, the *world* scripted (solar curve, tariff windows, departure time, scheduled
   exogenous events) with readings derived by the plant simulator including its configured lag,
   judged by the shared invariant set plus a few scenario-intent assertions. A test whose
   question is *"does the whole stack stay correct over time as the engines interact and readings
   lag"* belongs here.

Tier 3 runs in the **same** `pytest-homeassistant-custom-component` harness as tier 2 — it drives
the real config entry and real coordinator cycles, so it could not run anywhere else. What
separates the two is scope (which engines are binding, over how many cycles, against readings
derived rather than seeded) and oracle (invariants versus per-criterion assertions), not the
harness. The tier boundary is therefore a placement and review convention, not a technical one,
which is exactly why it needs writing down.

**The three existing cycle-driving `test_*_end_to_end.py` suites stay exactly as they are** —
not migrated, not superseded, not retrofitted onto the simulator. Their single-engine focus is the
property that makes their failures diagnostic, and answering "which mode is wrong" is a
different and still-needed job from answering "did the system stay correct". A scenario failure
says the system misbehaved; a Solar end-to-end failure says Solar misbehaved. Accordingly,
`_cycle_from_feedback` is left in place and is not extracted into the simulator: this decision
adds a tier, it does not refactor the existing one. Option B's Pro (nothing new to learn) is
paid for here in the placement rule above being explicit rather than in avoiding the tier.

**The invariant-oracle rule.** An invariant earns a place in the shared set only if it is *not*
computed by the same code path that produced the value it judges. E8's C1 floor/cap is the
reference counter-example in its narrow form: re-deriving C1 from the current `apply_floor_cap`
just returned passes because E8 ran, so it tests the assertion rather than the system. The rule
is deliberately about the assertion's provenance rather than about whether production enforces
the property at all, because the wider version of that same C1 question — *is E8 still applied on
every path that writes a current* — is a genuine invariant that a future refactor could break (a
new write site, a fault branch that returns early, a reordering that clamps before E8), and one
this tier is unusually well placed to catch. The invariants that qualify are therefore properties
of a *sequence*, or comparisons against ground truth the production code structurally cannot see:
headroom measured against the simulator's *true* charger draw rather than the lagged reading (the
#990/#992 class), a cooldown surviving a mode switch (#974), a latch resetting per occasion
rather than per reload (#546), bounded oscillation. The first is the clearest case — true
instantaneous draw is exactly what the coordinator does not have, which is what lets the tier be
an oracle rather than a mirror of the code under test.

**The plant simulator is test-only; product code takes no dependency on it.** That places its
internals — its structure, its numeric model, any library it calls — squarely inside CLAUDE.md's
test/CI/dev-tooling carve-out, i.e. outside ADR scope and inside the tier's implementation spec.
What is ADR-scoped is only what this record settles: that the tier exists, where a contributor
puts a test, and what a passing scenario is allowed to mean.

That distinction — a test-tier *taxonomy* is architectural, the *tooling* a tier calls is not —
is not one CLAUDE.md's carve-out draws today. Read literally, the carve-out excludes anything
test-only unless product code depends on it, which would exclude this record too (and would
equally have excluded ADR-0009, whose grandfathered status is not authorisation for a successor).
The distinction is nonetheless the right one, for the same reason the carve-out already exempts
the CI/automation pipeline's *own structure* while excluding which tool a pipeline script calls:
both are about who is bound by a rule rather than which library implements it. A tier taxonomy
binds where every future test goes and what a green suite is allowed to mean; a measurement
library (ADR-0026/ADR-0029) binds nothing beyond the file that imports it. Making the carve-out
say so is a prerequisite this decision creates rather than a licence it assumes — see
Consequences.

Option D is rejected on its Con: an oracle the fix pipeline can regenerate is not an oracle
under `_ai-fix.yml`. Its Pro is genuinely forfeited — behavior changes outside the invariant set
go uncaught — and the accepted mitigation is that each newly understood bug class becomes a
candidate invariant, growing the set over time, rather than adding a snapshot layer later.
Option C is rejected because the second `baseline_w` instance being caught by a reader rather
than by a test shows the status quo's cost is already being paid. Option B is rejected because
its Con is structural: the single-engine focus it would have to give up is the same focus that
gives the existing suites their diagnostic value.

## Consequences

- **CLAUDE.md's test/CI/dev-tooling carve-out has to be amended to name test-suite taxonomy as
  ADR-worthy**, the way it already exempts the CI/automation pipeline's own structure. Until it
  is, this record sits outside the carve-out's literal wording (see the Decision's third
  paragraph), and the next contributor faces the same ambiguity. That amendment is a separate
  `workflow` change, not part of this ADR — this decision creates it as a prerequisite.
- **The tier's simulator and invariant runner are designed, not decided, here.** The paired
  implementation spec owns both, and must settle three questions this ADR deliberately leaves
  open: how simulated time relates to the coordinator's update interval; whether the simulator's
  outputs reach HA state through `tests/helpers.py`'s existing `seed_charger_states` path or
  replace it; and where a scenario file physically lives. That last one needs an answer because
  ADR-0002's `tests/`-mirrors-the-package layout — restated as a live rule in ADR-0010, ADR-0015
  and ADR-0019 — has no slot for a tier that mirrors no package. It is not a contradiction (the
  existing `test_*_end_to_end.py` suites already sit outside the mirror), but a placement rule
  whose whole purpose is answering "where does this test go" should not leave the literal
  directory unstated.
- **Two contributor-facing documents become stale the moment the tier lands** and need updating
  in the same strand: `.claude/skills/write-tests/SKILL.md` (its frontmatter description and its
  "Choose the harness first (ADR-0009)" section both state the split as two-way) and
  `docs/reference/definition-of-done.md`'s "Tests green" bullet (same two-way phrasing). A
  `workflow` issue for that pair is follow-up work this decision creates.
- **The first scenario targets C4's exposure, not R3's.** R3's clamp reads a debounced
  `baseline_w` (`debounce_baseline_w`, threaded through `CycleContext.baseline_w`) while C4's
  `clamp_to_ceiling` still re-derives its own, so the first scenario's value is the *invariant*
  that holds across both clamp call sites — and that would fail for a third if one appears —
  rather than a reproduction of the instance R3 already handles. This narrows the epic's
  bug-first framing, which assumed the harness would exist before either clamp was fixed.
- **Snapshot/approval testing is foreclosed for this tier.** Introducing one later contradicts
  this record and needs a superseding ADR, not an addition.
- **The ADL index carries a back-pointer on ADR-0009's row.** Extending ADRs have not done this
  before (ADR-0012's row has no pointer to ADR-0023, ADR-0021's none to ADR-0034) while
  narrowing ones have; this record adopts the narrowing convention deliberately, because a
  contributor looking up the testing strategy needs to find the third tier from ADR-0009's row
  rather than by reading to the end of the log. Extending ADRs should follow suit going forward.
- **Suite runtime becomes a budget question.** Many cycles × all engines live × eventually one
  scenario per use-case may warrant a pytest marker or a separate CI job; that is a
  dev-tooling choice for the spec, but it is a cost this decision knowingly incurs.
- **A wrong simulator is a new failure mode** with no analogue in the existing tiers: a false
  failure indicts correct product code. The mitigation this decision relies on is the bug-first
  sequencing — the simulator's lag model is validated by reproducing an already-diagnosed real
  defect before any speculative scenario is written.
- **Status flips to Accepted** once *both* the CLAUDE.md carve-out amendment and the first
  scenario have landed — the amendment because until it does this record is outside the rule it
  is judged by (bullet 1), and the scenario because until then the tier does not exist. It is
  Proposed until both hold. If the amendment is rejected rather than made, this record should be
  withdrawn or superseded rather than left Proposed indefinitely.
