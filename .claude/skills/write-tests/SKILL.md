---
name: write-tests
description: Use when authoring or expanding a test suite for the Smart Charging integration — choosing the right harness per ADR-0009 (plain pytest for pure logic, HA harness for adapters/coordinator/entities), covering the mandated edge cases, and naming tests for requirement/UC traceability.
---

# Write tests (ADR-0009 harness split)

Author tests that verify Smart Charging behavior in the **correct harness** and cover the cases the
project requires. Tests mirror the package 1:1 (`tests/` matches
`custom_components/smart_charging/`). This skill is usually used *inside* `develop-task`'s TDD loop,
but also stands alone when back-filling or expanding coverage.

## Choose the harness first (ADR-0009)

- **Plain pytest** — `tests/modes/`, `tests/engines/`: pure logic that imports **no**
  `homeassistant.*`. Fast, no runtime. This is where mode/engine behavior, clamp math, and the
  resolution rules are verified.
- **HA harness** (`pytest-homeassistant-custom-component` + `MockConfigEntry`) —
  `tests/adapters/`, `tests/test_coordinator.py`, entity/platform tests, `tests/test_config_flow.py`,
  `tests/test_init.py`: anything HA-coupled (entity state, config-entry lifecycle, registration,
  services).

If you cannot test a piece with plain pytest without importing `homeassistant`, it belongs in an
adapter/coordinator/entity — that is a design signal, not a reason to reach for the harness in a
`modes/`/`engines/` test.

## The cycle (do every step, in order)

0. **Open (or link) the issue / task** the tests belong to; work on its feature branch.
1. **Identify the unit and its layer** — pure logic vs HA-coupled — and pick the harness above.
2. **Name and structure each test as a behavior spec:**
   - **Name** in **Should-When-Then** form — `test_should_<expected behavior>_when_<condition>` — so
     the name reads as a spec sentence and still traces to the requirement / UC / ADR criterion it
     verifies (e.g. `test_should_clamp_to_remaining_headroom_when_target_exceeds_grid_limit`,
     `test_should_force_zero_and_fault_when_status_is_none`). Coverage stays checkable by name.
   - **Structure the body** in three blocks — **Arrange / Act / Assert** — with `# Arrange`,
     `# Act`, `# Assert` comments: `# Arrange` sets up state, `# Act` performs the single action
     under test, `# Assert` checks the outcome. One behavior per test — exactly one action in `# Act`,
     and assertions only under `# Assert`.
3. **Cover the mandated cases:**
   - **Every adapter role:** present, absent, unavailable, and — for the status/enum role — an
     unmapped raw state (all four; ADR-0009).
   - **Engines:** each behavioral row/branch, plus **worked examples** for clamp math (grid-safety,
     floor/cap) and the NF4 voltage fallback.
   - **Coordinator:** happy path, status-gating-to-zero, clamp applied, fault path (required adapter
     `None` → 0 A + `Fault`; grid voltage `None` → not a fault).
   - **Config flow:** a full flow creates a valid entry; validation rejects a bad mapping.
4. **Run red first** — confirm each test fails without the implementation (no vacuous asserts, no
   asserting on a mock's own return). Mock only at the HA boundary.
5. **Review** — launch the `test-reviewer` agent (fresh, separate Opus); post findings via the
   `submit-pr-review` skill in **local mode**.
6. **Address**, then **manual review**, then **commit** referencing the issue.

## Rules

- **Harness by layer, no exceptions.** Pure logic → plain pytest (no HA import); HA-coupled → HA
  harness. A pure-logic test that imports `homeassistant` defeats the package boundary.
- **Name for traceability, structure for behavior.** Should-When-Then names — a reviewer reads
  coverage from names alone — with Arrange / Act / Assert bodies.
- **One behavior per test.** A test verifies exactly one behavior: one action in `# Act`, and every
  assertion under `# Assert` checks that same behavior. If you're tempted to test a second behavior
  (a second `# Act`, or asserts about an unrelated outcome), split it into another test. This keeps
  each Should-When-Then name honest and a failure pointing at a single cause.
- **All four adapter cases, every role.** Present / absent / unavailable / unmapped-raw.
- **Tests must fail without the code.** If a test passes against an empty implementation, it isn't
  testing anything.
- **Mock at the boundary.** Don't mock so deep the wiring the test claims to cover is bypassed.

## Common mistakes

- A `modes/`/`engines/` test that imports `homeassistant.*` (wrong harness).
- Missing one of an adapter role's four state cases.
- Clamp-math tests with no worked example (just "it returns a number").
- Vacuous asserts or asserting on a mock's return value — green against no implementation.
- Test names that describe mechanics (`test_function_returns`) instead of the behavior they trace
  to — use Should-When-Then, not the function's name.
- A test body with no Arrange / Act / Assert structure, or with more than one action in `# Act`
  (asserting several behaviors at once) so a failure no longer points at a single scenario.
