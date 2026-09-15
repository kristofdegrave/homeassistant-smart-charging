---
layer: method
---

# Work type: `development` — how the work is done

Turn one task from an approved implementation plan (`docs/plans/<slice>.md`) into working,
test-covered code under `custom_components/smart_charging/`, **test-first**. The plan owns *what*
to build and *in what order*; this file is *how* one task gets built.

This file is the `development` row's work file in `CLAUDE.md`'s **Model selection** table. It
carries **how a development task is built** and nothing else.

*What must be true of the finished tests* is the **`testing` row's** completion bar, not this
row's — `done.md`'s preamble states that split and why; the loop below is where you reach it.

## Before you start

- The task must come from an **approved** implementation plan — never write
  `custom_components/` code without that plan in place. The plan is produced by the `specs`
  work type, which `CLAUDE.md`'s **Model selection** table routes to.
- Work the tasks in the plan's order; a task can be built only once every task it depends on
  exists or is stubbed (the plan states its `Depends on`).

## Building the task

**The implement step (do the work)**: read, in this order, before writing anything —

- the task's own section of the plan, the **ADR it cites**, and the **analysis behaviour** it
  realises (`docs/analysis/control-cycle.md`, `resolution-rules.md`, `requirements.md`, the
  relevant use-case). The plan's formulas and thresholds are **test anchors** attributed to
  those documents: reproduce them, don't reinvent them;
- the **`ha-integration-knowledge` skill** — the Home Assistant platform reference (entity
  platforms, config-flow conventions, quality scale, thin-wrapper rule) — before writing
  anything that touches HA APIs.

Then TDD **one behaviour at a time** (use the `test-driven-development` skill):

- **Write the failing test** against the files `CLAUDE.md`'s **Model selection** table names in
  the `testing` row — its work file for how the test is chosen, named and structured, and its
  completion bar for what the finished tests have to satisfy. This is not a second standard:
  the reviewer applies that same bar to the tests this loop writes.
- **Run it** and confirm it **fails for the right reason** (red).
- **Write the minimal implementation** to pass (green). Match the surrounding code's idioms.
- **Refactor while green.** Commit.

**Honour the structural ADRs as you code.** The bar's item 2, *Structural ADR compliance*,
enumerates them and judges them, two of them at Critical. What that means while writing: the
engine/adapter boundary, the two clamp call sites and the fault path are decided *before* the
first line, not repaired after a review — a design that puts HA state inside an engine or folds
the two clamps into one conditional is rewritten rather than adjusted.

**Pre-commit self-check**, before each commit: run the **Quick review checklist** at the end of
the `python-anti-patterns` skill over the diff, and — where the change touches async code —
the checklist in `async-python-patterns` (that skill's **When this file applies** section is
the single statement of which files those are). The bar's item 5, *The general-Python and async
bar*, is where a miss is judged; running it here is what keeps it out of the review.

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

## Common mistakes

Mistakes in how the work is done. The defects themselves are enumerated once, in the two bars,
so none of them is restated here:

- Writing implementation before the red test, or a test that passes without the code.
- Starting from the plan's task text alone, without the ADR it cites and the analysis behaviour
  it realises — which is how a formula gets reinvented instead of reproduced.
- Deciding the layer after writing the code: a piece that turns out to need `homeassistant.*`
  inside `modes/`/`engines/` is a design signal, and moving the import is not the fix.
- Treating the `testing` row's files as optional because the tests were written here rather than
  under a `testing` issue — they are the same artifact.
- Claiming "done" without running the linter and the suite, and without driving the runtime
  behaviour the change makes observable.
- Writing against this file alone and never opening `done.md` — the bar is where most of what a
  review will say already is.
