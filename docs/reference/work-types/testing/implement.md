# Work type: `testing` — how the work is done

Author tests that verify the system's behaviour in the **correct harness** and cover the cases
the project requires. Which harnesses exist and which code belongs in each, the mandated cases,
the authorities behind both and the layout the tests mirror are the stack overlay's
(**Overlays**, below).

This file is the `testing` row's work file in `CLAUDE.md`'s **Model selection** table. It
carries **how a test suite is written** and nothing else; the completion bar beside it,
`done.md`, carries what must be true of the finished suite.

It is also what the `development` work file routes its TDD loop to when that loop reaches the test it is
about to write, and the bar goes with it: a test written inside a development task is the same
artifact as one written under a `testing` issue, and is judged against the same bar.

## Choose the harness first

The directory-to-harness mapping is the bar's item 1, *Harness split*, which states it and
judges it — read it there rather than from a summary. What that means before the first line:
settle which layer the unit is in, because a test written in the wrong harness is rewritten
rather than adjusted. What to read before writing a test in each harness, and the design signal
a piece that fits neither sends, are the stack overlay's.

## Writing the tests

**The implement step (do the work)**: identify the unit and its layer — the stack overlay names
the layers — pick the harness above, then:

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
  judges them; work from it rather than from memory, and read the authority it names for the
  unit cases before writing them rather than working from a summary — it is the authority on
  which roles its clause reaches, how it is discharged per adapter class, and the docstring a
  case pinning "used as-is" must carry.
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
  that means while writing: mock the boundary the unit talks to — the stack overlay names it —
  not the collaborator whose wiring the test is supposed to prove.

### Skills

The method skills this work file uses, by step: `test-driven-development` for the red run
before the implementation; `systematic-debugging` when a test fails, or passes, for a reason
you cannot explain; `verification-before-completion` before the PR; `receiving-code-review` in
the review step. The stack skills — the platform's testing reference — are the overlays' to
name.

## Common mistakes

Mistakes in how the work is done. The defects themselves are enumerated once, in the bar, so
none of them is restated here:

- Writing the mandated cases from memory instead of from the bar's item 2 and the authority it
  names. The unit case in particular has a trigger, a per-class discharge and exclusions that a
  summary loses.
- Naming the test after the body you just wrote rather than the behaviour you meant to pin —
  which is why the name comes first.
- Running red only after the implementation exists, so "it fails without the code" is inferred
  rather than observed.
- Writing against this file alone and never opening `done.md` — the bar is where most of what a
  review will say already is.
- The stack overlays add the mistakes that belong to the platform's harness.

## Overlays

**Apply the overlays** the profile's declared stacks provide for this work type: one file per
stack at `overlays/<stack>.md` beside this one, its **Implement** section read with this file as
part of the same work file. An overlay adds the stack's material to the rule that names it and
never restates a rule of this file; one that reads `none` is the stack saying it has nothing to
add here. The shape, and the rule that no stack material lives in this file, are this tree's
`README.md`'s.
