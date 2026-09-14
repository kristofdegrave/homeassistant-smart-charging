# Work type: `testing` — the completion bar

This file states *what must be true of a finished test suite*. How the tests are written —
choosing the harness, naming, structuring, the order the work happens in — is `implement.md`.
How a review is conducted — what to read first, how to anchor findings, the output format —
belongs with the reviewer.

**Which change dispatched the review does not change which bar applies.** Tests written inside a
`development` task's TDD loop are the same artifact as tests written under a `testing` issue,
and this is the bar for both.

## The bar

**(1) Harness split (ADR-0009).** The directory-to-harness mapping is stated here, once, and
both sides read it from here:
- **Plain pytest** — `tests/modes/`, `tests/engines/`: pure logic, importing no
  `homeassistant.*`. Fast, no runtime; this is where mode/engine behaviour, clamp math and the
  resolution rules are verified. A test in these directories that pulls in the HA harness is
  **Major** — it defeats the package boundary that makes the logic HA-free.
- **HA harness** (`pytest-homeassistant-custom-component` + `MockConfigEntry`) —
  `tests/adapters/`, `tests/test_coordinator.py`, entity/platform tests,
  `tests/test_config_flow.py`, `tests/test_init.py`: anything HA-coupled (entity state,
  config-entry lifecycle, registration, services). One of these tested with plain pytest where it
  needs a real (mocked) HA runtime is **Major** — the test either bypasses the wiring it claims
  to cover or re-implements it.

**(2) Mandated coverage.** Each miss below is **Major**; name the role, branch or path missed.
- **Every adapter role:** present, absent, unavailable, and — for the status/enum role — an
  unmapped raw state. ADR-0009 requires all four.
- **Every numeric role whose catalogued unit column names a unit:** the fifth mandated case —
  the role states its expected unit set, and the adapter class that defines its read carries a
  foreign-unit case and an absent-unit case. ADR-0040, which extends ADR-0009, is the authority
  on the trigger, the per-class discharge and the exclusions — read it before judging a role in
  or out, and before judging a pinned behaviour adequate. It also requires a docstring on a case
  pinning "used as-is", and is the authority on what that docstring must say.
- **Engines:** each behavioural row / branch, plus **worked examples** for the clamp math
  (grid-safety, floor/cap) and the NF4 voltage fallback. A clamp test asserting only that a
  number came back is a missing worked example, not a present one.
- **Coordinator:** happy path, status-gating-to-zero, clamp applied, and the fault path
  (required adapter `None` → 0 A + `Fault`; grid voltage `None` → not a fault).
- **Config flow:** a full flow creates a valid entry; validation rejects a bad mapping.

**(3) Traceability and structure.** Coverage is checkable from the test names alone, and a
failure points at a single scenario. Severity is decided against **the changed tests**, which
are all a reviewer sees: a miss that is an exception among them is **Minor per occurrence**; a
miss that is the *pattern* of them — so that following the change's own example reproduces it —
is **Major**. The split is there because a bar that only ever says Minor routes a suite-wide
miss through as clean, and a suite-wide miss defeats this item's purpose rather than blemishing
it.
- Each name is in **Should-When-Then** form — `test_should_<expected behaviour>_when_<condition>`
  — and traces to the requirement / UC / ADR criterion it verifies. A name describing mechanics
  rather than behaviour (`test_function_returns`) is a miss: coverage is no longer readable from
  the names, which disables the half of the review that reads it there.
- Each body is blocked into **Arrange / Act / Assert** with those comments.
- Exactly one behaviour per test: one action in `# Act`, every assertion under `# Assert`
  checking that same behaviour. A test bundling two behaviours can no longer be honest, in its
  name, about what failed.

**(4) Test honesty.** Each test genuinely **fails without the implementation** — no vacuous
asserts, no asserting on a mock's own return value, no fixture silently pinning a value that
makes the assertion trivially true. A test that would pass against an empty implementation is
**Major**: it isn't testing anything, and a suite containing it reports a coverage it does not
have. Mocking is at the HA boundary, not so deep it hides the wiring the test claims to cover —
**Major** where the bypassed wiring is what the test's own name claims to verify, **Minor**
where the over-deep mock merely makes the test brittle.
