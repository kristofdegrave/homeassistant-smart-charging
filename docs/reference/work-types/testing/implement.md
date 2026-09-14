# Work type: `testing` — how the work is done

Author tests that verify this integration's behaviour in the **correct harness** and cover the
cases the project requires, per
[ADR-0009](../../../adl/0009-testing-strategy.md) — the authoritative plain-pytest vs
HA-harness split — and the extension of its mandated coverage in
[ADR-0040](../../../adl/0040-fifth-mandated-adapter-case-unit-set.md). Tests mirror the package
1:1 (`tests/` matches `custom_components/smart_charging/`).

This file is the `testing` row's work file in `CLAUDE.md`'s **Model selection** table. It
carries **how a test suite is written** and nothing else. Two things deliberately sit
elsewhere:

- The lifecycle around the work — issue, worktree, PR, review, fix, merge — belongs to the
  contribution workflow and is not re-derived here.
- *What must be true of a finished test suite* is the completion bar, `done.md`, named
  alongside this file in the same row and again in that row's review column. The author checks
  it before requesting review and the reviewer applies it, so it is written once for both.

It is also what `develop-task`'s TDD loop follows when that loop reaches the test it is about
to write: the `development` row names no test work file of its own, and a test written there is
the same artifact judged against the same bar.

## Choose the harness first (ADR-0009)

- **Plain pytest** — `tests/modes/`, `tests/engines/`: pure logic that imports **no**
  `homeassistant.*`. Fast, no runtime. This is where mode/engine behaviour, clamp math, and the
  resolution rules are verified.
- **HA harness** (`pytest-homeassistant-custom-component` + `MockConfigEntry`) —
  `tests/adapters/`, `tests/test_coordinator.py`, entity/platform tests,
  `tests/test_config_flow.py`, `tests/test_init.py`: anything HA-coupled (entity state,
  config-entry lifecycle, registration, services).

Before writing an HA-harness test, read the **Testing Requirements** section of the
`ha-integration-knowledge` skill — in particular its rule that tests exercise the integration
through its public surface (config entry, entity state, services) rather than mocking internal
integration details. Plain-pytest tests under `tests/modes/` and `tests/engines/` don't need it.

If you cannot test a piece with plain pytest without importing `homeassistant`, it belongs in an
adapter/coordinator/entity — that is a design signal, not a reason to reach for the harness in a
`modes/`/`engines/` test.

## Writing the tests

**Step 1 (do the work)**: identify the unit and its layer — pure logic vs HA-coupled — pick the
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

- **Harness by layer, no exceptions.** Pure logic → plain pytest (no HA import); HA-coupled → HA
  harness. A pure-logic test that imports `homeassistant` defeats the package boundary that
  makes the logic HA-free.
- **One behaviour per test.** A test verifies exactly one behaviour: one action in `# Act`, and
  every assertion under `# Assert` checks that same behaviour. If you're tempted to test a
  second behaviour (a second `# Act`, or asserts about an unrelated outcome), split it into
  another test. This keeps each Should-When-Then name honest and a failure pointing at a single
  cause.
- **Mock at the boundary.** Don't mock so deep the wiring the test claims to cover is bypassed,
  and don't let a fixture silently pin a value that makes the assertion trivially true.

## Common mistakes

- A `modes/`/`engines/` test that imports `homeassistant.*` (wrong harness).
- Missing one of an adapter role's mandated cases.
- Clamp-math tests with no worked example (just "it returns a number").
- Vacuous asserts or asserting on a mock's return value — green against no implementation.
- Test names that describe mechanics (`test_function_returns`) instead of the behaviour they
  trace to — use Should-When-Then, not the function's name.
- A test body with no Arrange / Act / Assert structure, or with more than one action in `# Act`
  (asserting several behaviours at once) so a failure no longer points at a single scenario.
- Writing against this file alone and never opening `done.md` — the bar is where most of what a
  review will say already is.
