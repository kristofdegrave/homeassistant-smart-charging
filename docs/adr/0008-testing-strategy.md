# ADR-0008: Testing strategy

Date: 2026-07-04
Status: Accepted

## Context

Before any test scaffolding is written, the integration needs a decided testing
strategy: what gets tested with what harness, and why. This is backfilled from
Decision 7 of `docs/plans/2026-07-04-integration-architecture-design.md` (PR #30, still
open — see ADR-0001's plan to give each of that doc's decisions its own ADR before #30
merges), tracked from [issue #41](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/41).

ADR-0002 already decided the package layout — `modes/`, `profiles/`, and the peak
protection/SOC/deadline logic they call are self-contained, HA-free pure logic, with all
HA-entity I/O isolated behind an `Adapter` protocol in `adapters/`. That structural
boundary is what makes a testing strategy split by layer possible at all: without it,
"unit-test the pure logic without HA" would just be an aspiration, not something the
package layout actually enforces.

ADR-0006 (coordinator and data flow, backfilling Decision 5 — issue #38, not yet drafted
at the time of writing) decides the coordinator's pipeline: a single
`DataUpdateCoordinator` subclass that reads through adapters, resolves SOC limit and
mode, dispatches to mode modules, applies the peak/grid-ceiling clamps, and writes back.
That pipeline is HA-coupled by construction (`DataUpdateCoordinator`, config-entry
lifecycle, entity registry) — it cannot be exercised with plain pytest alone, and its
correctness depends on wiring that only exists inside a running (or mocked) HA instance.

The forces at play: pure mode/profile/protection logic is the highest-churn, most
behaviorally-critical code (it is what `requirements.md`'s acceptance criteria and the
UC docs actually describe), and the project wants fast, HA-independent tests for it with
direct traceability to those requirements. Adapters and the coordinator are thinner but
still need coverage for entity-state edge cases (missing/unavailable/unmapped) and for
the pipeline wiring itself (config flow, coordinator setup, entity registration) — those
can only be verified against something that behaves like real HA.

## Considered options

### Option A — Unit-test pure logic directly with plain pytest; test adapters and the coordinator pipeline through the HA test harness

- Pro: Mode/profile/protection logic (the highest-value, most requirement-dense code) is
  tested with no HA dependency at all — fast, no test-harness setup, runs anywhere plain
  Python runs. This is the direct payoff of ADR-0002's layout: because that logic cannot
  import `homeassistant.*`, its tests structurally cannot either. Test names can map
  1:1 to requirement/UC acceptance criteria for traceability
  (e.g. `test_r1_solar_first_holds_at_minimum_during_grid_fallback`).
- Con: Two different testing idioms exist side by side in the same test suite (plain
  pytest for logic, `pytest-homeassistant-custom-component` + `MockConfigEntry` for
  adapters/coordinator) — a contributor has to know which one applies to a given module,
  and plain-pytest tests for mode logic cannot catch entity-registration or
  platform-wiring bugs (a mode module can be perfectly correct in isolation while the
  coordinator still wires it to the wrong entity) — that class of bug is only caught by
  the HA-harness tests this option still keeps for adapters and the coordinator.

### Option B — Test everything uniformly through the HA test harness (`pytest-homeassistant-custom-component` + `MockConfigEntry`), including mode/profile/protection logic

- Pro: One testing idiom for the whole suite — no split between "plain pytest" and
  "HA-harness" test files, so there's no ambiguity about which applies to a new module.
- Con: HA-harness tests are slower to set up and run than plain pytest, and depend on
  `pytest-homeassistant-custom-component` being installed and a (mocked) HA runtime being
  spun up even to test logic that never touches HA — running mode/profile logic through
  that harness anyway would undermine the actual point of ADR-0002's package boundary:
  if the pure-logic modules need the HA test harness to be tested, the boundary that was
  supposed to make them HA-independent isn't buying anything in practice.

## Decision

Option A. Mode modules, profile modules, peak protection, SOC management, and deadline
escalation are unit-tested directly with plain pytest — a direct consequence of ADR-0002
making that logic HA-free by construction. Test names reference the requirement or UC
acceptance criterion they verify (e.g.
`test_r1_solar_first_holds_at_minimum_during_grid_fallback`) for traceability back to
`requirements.md` and the UC docs.

Adapter classes are tested against mocked HA state objects covering entity present,
absent, unavailable, and — for enum roles — an unmapped raw state (the same case the
error-handling decision — backfilled separately, not yet drafted at the time of writing —
treats as equivalent to a missing entity). The coordinator's
pipeline (ADR-0006) is tested at the integration level: `pytest-homeassistant-custom-component`
provides the HA test harness, and `MockConfigEntry` drives config-flow and coordinator
integration tests. Option A's Con is accepted deliberately — plain-pytest tests for mode
logic cannot catch entity-registration or platform-wiring bugs, which is exactly why
adapters and the coordinator keep their HA-harness integration tests rather than also
being tested in isolation only.

CI enforcement of this strategy (running pytest, ruff, hassfest, HACS validation in
GitHub Actions) is scoped to a separate dev-tooling follow-up design, not to this
document.

## Consequences

- `tests/` mirrors `custom_components/smart_charging/` per ADR-0002's layout decision;
  within that mirrored structure, `tests/modes/`, `tests/profiles/`, and the
  protection/SOC/deadline test modules use plain pytest, while `tests/adapters/` and
  `tests/test_coordinator.py` (or equivalent) depend on
  `pytest-homeassistant-custom-component` and `MockConfigEntry`.
- Every new mode, profile, or protection rule needs a plain-pytest test file named for
  the requirement/UC criterion it verifies — reviewers can check requirement coverage by
  test name alone, without reading the test body.
- Every new adapter role needs its four HA-state cases (present, absent, unavailable,
  unmapped-raw-state for enum roles) covered before it's considered done.
- `pytest-homeassistant-custom-component` becomes a test-only dependency (not a runtime
  dependency of the integration itself) — this needs to be declared in the dev-tooling
  follow-up design's dependency/CI setup (tracked separately, not by this ADR).
- This ADR does not decide CI wiring (when pytest/ruff/hassfest/HACS validation run, on
  what triggers) — that remains open for the dev-tooling follow-up design.
