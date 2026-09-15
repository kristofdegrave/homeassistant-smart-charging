# Work type: `testing` — the completion bar

This file states *what must be true of a finished test suite*. How the tests are written —
choosing the harness, naming, structuring, the order the work happens in — is `implement.md`.
How a review is conducted — what to read first, how to anchor findings, the output format —
belongs with the reviewer.

**Which change dispatched the review does not change which bar applies.** Tests written inside a
`development` task's TDD loop are the same artifact as tests written under a `testing` issue,
and this is the bar for both.

## The bar

**(1) Harness split.** The directory-to-harness mapping is stated once, in the stack overlay
under this item, and both sides read it from there — together with the severity a test written
in the wrong harness carries, and why.

**(2) Mandated coverage.** Each miss is **Major**; name the role, branch or path missed. The
cases, and the authorities that mandate them, are enumerated in the stack overlay under this
item.

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
have. Mocking is at the boundary — the stack overlay names it — not so deep it hides the wiring
the test claims to cover — **Major** where the bypassed wiring is what the test's own name
claims to verify, **Minor** where the over-deep mock merely makes the test brittle.

## Overlays

**Apply the overlays** the profile's declared stacks provide for this work type: one file per
stack at `overlays/<stack>.md` beside this one, its **Done** section read with this file as part
of the same bar — by the author self-checking and by the reviewer applying it. An overlay adds
the stack's material to the item that names it and never restates an item of this file; one
that reads `none` is the stack saying it has nothing to add here. The shape, and the rule that
no stack material lives in this file, are this tree's `README.md`'s.
