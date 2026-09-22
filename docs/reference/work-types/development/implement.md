# Work type: `development` — how the work is done

Turn one task into working, test-covered product code, **test-first**. The task is the issue
body; the spec it was cut from is the body of that issue's parent epic, which owns *what* to
build and *in what order*. This file is *how* one task gets built. Where the product code lives, and the platform and
language it is written in, are the stack overlays' (**Overlays**, below).

This file is the `development` row's work file in `CLAUDE.md`'s **Model selection** table. It
carries **how a development task is built** and nothing else.

*What must be true of the finished tests* is the **`testing` row's** completion bar, not this
row's — `done.md`'s preamble states that split and why; the loop below is where you reach it.

## Before you start

- The task must come from an **approved** spec — never write product code without one in
  place. The spec is the parent epic's body, and the issue you are building is one of its
  children; how that decomposition is made and reviewed is `CLAUDE.md`'s **Idea-to-product
  flow**.
- Work the tasks in the epic's order; a task can be built only once every task it depends on
  exists or is stubbed (the plan states its `Depends on`).

## Building the task

**The implement step (do the work)**: read, in this order, before writing anything —

- the task's own section of the plan, the **ADR it cites**, and the **analysis behaviour** it
  realises (`docs/analysis/control-cycle.md`, `resolution-rules.md`, `requirements.md`, the
  relevant use-case). The plan's formulas and thresholds are **test anchors** attributed to
  those documents: reproduce them, don't reinvent them;
- the **platform reference** the stack overlay names, before writing anything that touches the
  platform's APIs.

Then TDD **one behaviour at a time** (use the `test-driven-development` skill):

- **Write the failing test** against the files `CLAUDE.md`'s **Model selection** table names in
  the `testing` row — its work file for how the test is chosen, named and structured, and its
  completion bar for what the finished tests have to satisfy. This is not a second standard:
  the reviewer applies that same bar to the tests this loop writes.
- **Run it** and confirm it **fails for the right reason** (red).
- **Write the minimal implementation** to pass (green). Match the surrounding code's idioms.
- **Refactor while green.** Commit.

**Honour the structural boundaries as you code.** The bar's item 2, *Structural ADR
compliance*, judges them, and the stack overlay enumerates them — and says, under its
**Implement** section, what honouring them means while writing: which designs are rewritten
rather than adjusted, because the boundaries are decided *before* the first line, not repaired
after a review.

**Pre-commit self-check**, before each commit: run the language checklists the stack overlay
names over the diff. The bar's item 5, *The language bar*, is where a miss is judged; running
it here is what keeps it out of the review.

**Before opening the PR**, self-check against the bar and against the Definition of Done the
contribution workflow names (use the `verification-before-completion` skill). The bar's item 6,
*Runtime check recorded*, is the one most often skipped: the observation is made while the
behaviour is in front of you, not reconstructed afterwards.

**The review step**: receive the reviewer's findings with the `receiving-code-review` skill —
verify, don't perform.

## Rules

- **Test-first, always.** No implementation line before a failing test that demands it. The
  `testing` row's bar judges the result; what that means here is that the red run happens before
  the implementation exists.
- **Minimal + DRY + YAGNI.** Build only what the task needs; reuse existing helpers; match
  surrounding style. The bar's item 3, *Code health*, states it and judges it.
- **Cite behaviour, don't restate it.** The analysis documents own the rules; reproduce them as
  test anchors attributed to their source.
- **Never regress a safety invariant.** The bar's item 4, *Safety not weakened*, states it and
  judges it. What that means while writing: clamps, floor/cap and the fault path stay intact and
  un-merged — a task that seems to need one loosened is a task whose plan is wrong, so surface
  it rather than weakening the invariant.
- **No magic strings or numbers, written that way the first time.** The bar's item 3 states the
  rule and its one exception. What that means while writing: reach for an enum or a named
  constant the *first* time a literal is compared or assigned more than once — don't wait for
  the review to flag it.
- **Plan inconsistency → truthful, task-scoped implementation, surfaced.** If a task's literal
  instruction conflicts with the plan's own ordering, or would require an untruthful declaration
  (advertising a capability a later task hasn't built yet), or would creep into another task's
  files, don't silently follow the literal text and don't paper over it. Implement the minimal
  truthful version scoped to this task, record which later task owns the deferred piece, and
  flag the deviation instead of deciding silently.
- **Frequent commits**, one behaviour each.

### Skills

The method skills this work file uses, by step: `test-driven-development` for the loop above;
`systematic-debugging` when a red test stays red, or a green one passes, for a reason you cannot
explain; `research` when a step is blocked on an external fact; `verification-before-completion`
before the PR; `receiving-code-review` in the review step. The stack skills — the platform
reference, the language checklists — are the overlays' to name.

## Common mistakes

Mistakes in how the work is done. The defects themselves are enumerated once, in the two bars,
so none of them is restated here:

- Writing implementation before the red test, or a test that passes without the code.
- Starting from the plan's task text alone, without the ADR it cites and the analysis behaviour
  it realises — which is how a formula gets reinvented instead of reproduced.
- Treating the `testing` row's files as optional because the tests were written here rather than
  under a `testing` issue — they are the same artifact.
- Claiming "done" without running the linter and the suite, and without driving the runtime
  behaviour the change makes observable.
- Writing against this file alone and never opening `done.md` — the bar is where most of what a
  review will say already is.

## Overlays

**Apply the overlays** the profile's declared stacks provide for this work type:
`overlays/<stack>.md` beside this file, its **Implement** section read with this file as part of
the same work file. What an overlay is, what a file reading `none` means and what may not live in
this file are this tree's `README.md`'s **Stack overlays**.
