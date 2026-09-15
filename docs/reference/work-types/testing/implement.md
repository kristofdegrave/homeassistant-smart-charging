# Work type: `testing` — how the work is done

Author tests that verify this integration's behaviour in the **correct harness** and cover the
cases the project requires, per
[ADR-0009](../../../adl/0009-testing-strategy.md) — the authoritative plain-pytest vs
HA-harness split — and the extension of its mandated coverage in
[ADR-0040](../../../adl/0040-fifth-mandated-adapter-case-unit-set.md). Tests mirror the package
1:1 (`tests/` matches `custom_components/smart_charging/`).

This file is the `testing` row's work file in `CLAUDE.md`'s **Model selection** table. It
carries **how a test suite is written** and nothing else; the completion bar beside it,
`done.md`, carries what must be true of the finished suite.

It is also what the `development` work file routes its TDD loop to when that loop reaches the test it is
about to write, and the bar goes with it: a test written inside a development task is the same
artifact as one written under a `testing` issue, and is judged against the same bar.

## Choose the harness first (ADR-0009)

The directory-to-harness mapping is the bar's item 1, *Harness split*, which states it and
judges it — read it there rather than from a summary. What that means before the first line:
settle which layer the unit is in, because a test written in the wrong harness is rewritten
rather than adjusted.

Before writing an HA-harness test, read the **Testing Requirements** section of the
`ha-integration-knowledge` skill — in particular its rule that tests exercise the integration
through its public surface (config entry, entity state, services) rather than mocking internal
integration details. Plain-pytest tests under `tests/modes/` and `tests/engines/` don't need it.

If you cannot test a piece with plain pytest without importing `homeassistant`, it belongs in an
adapter/coordinator/entity — that is a design signal, not a reason to reach for the harness in a
`modes/`/`engines/` test.

## Writing the tests

**The implement step (do the work)**: identify the unit and its layer — pure logic vs HA-coupled — pick the
harness above, then:

- **Name and structure each test as a behaviour spec.** The bar's item 3, *Traceability and
  structure*, defines both and judges them. What that means while writing:
  - **Name** in **Should-When-Then** form — `test_should_<expected behaviour>_when_<condition>`
    — so the name reads as a spec sentence and still traces to the requirement / UC / ADR
    criterion it verifies (e.g.
    `test_should_clamp_to_remaining_headroom_when_target_exceeds_grid_limit`,
    `test_should_force_zero_and_fault_when_status_is_none`). Write the name before the body;
    a name chosen after the fact describes the mechanics you just wrote rather than the
    behaviour you meant to pin.
  - **Structure the body** in three blocks — **Arrange / Act / Assert** — with `# Arrange`,
    `# Act`, `# Assert` comments: `# Arrange` sets up state, `# Act` performs the single action
    under test, `# Assert` checks the outcome.
- **Cover the mandated cases.** The bar's item 2, *Mandated coverage*, enumerates them and
  judges them; work from it rather than from memory, and read ADR-0040 before writing the unit
  cases rather than working from a summary — it is the authority on which roles its clause
  reaches, how it is discharged per adapter class, and the docstring a case pinning "used
  as-is" must carry.
- **Run red first** — confirm each test fails without the implementation. The bar's item 4,
  *Test honesty*, judges the result; what that means while writing is that the red run happens
  **before** the implementation exists, not as a retrospective check, because a test written
  against working code is the one that most easily passes for the wrong reason.

## Rules

- **One behaviour per test** — the bar's item 3, *Traceability and structure*, states it and
  judges it. What that means while writing: if you're tempted to test a second behaviour (a
  second `# Act`, or asserts about an unrelated outcome), split it into another test rather than
  widening this one.
- **Mock at the boundary** — the bar's item 4, *Test honesty*, states it and judges it. What
  that means while writing: mock the HA boundary the unit talks to, not the collaborator whose
  wiring the test is supposed to prove.

## Common mistakes

Mistakes in how the work is done. The defects themselves are enumerated once, in the bar, so
none of them is restated here:

- Reaching for the HA harness to dodge a design signal. A piece that cannot be tested with plain
  pytest belongs in an adapter/coordinator/entity — moving the test is not the fix.
- Writing the mandated cases from memory instead of from the bar's item 2 and ADR-0040. The unit
  case in particular has a trigger, a per-class discharge and exclusions that a summary loses.
- Naming the test after the body you just wrote rather than the behaviour you meant to pin —
  which is why the name comes first.
- Running red only after the implementation exists, so "it fails without the code" is inferred
  rather than observed.
- Writing against this file alone and never opening `done.md` — the bar is where most of what a
  review will say already is.
