# Work type: `testing` — the review checklist

**Who reads this.** The reviewer only — a fresh, read-only Opus agent, never the session that
wrote the tests. It holds what only a reviewer can check: what to read first, and the checks
that are about the **change** rather than the finished suite. What must be true of a finished
test suite is [`done.md`](done.md) beside this file, and how one is written is
[`implement.md`](implement.md); neither is restated here.

The output format, the severity grouping, the anchoring rules and the untrusted-data rule are
not here either. They are the same for every review and live with whoever applies this
checklist — the generic `reviewer` agent definition locally, the review workflow's own prompt
in CI, which has no agent to spawn and self-applies instead. Both reach this file the same
way, through `CLAUDE.md`'s **Model selection** table.

**This is the checklist for `tests/**` whichever row dispatched the review.** The `development`
row names it for that tree as well as this row naming it, for the reason [`done.md`](done.md)
gives for itself: tests written inside a `development` task's TDD loop are the same artifact as
tests written under a `testing` issue, and the criteria belong to the artifact rather than to
the label. Which row reached these files tells you nothing about which checklist they get.

## What to read first

Always read:

- The test files under review in `tests/` and the code under
  `custom_components/smart_charging/` they exercise.
- `docs/adl/0009-testing-strategy.md` — the authoritative plain-pytest vs HA-harness split.
- ADR-0040, which extends ADR-0009's mandated coverage with the fifth, unit case — where the
  change touches or wires an adapter that reads a numeric role. Locate it by number per
  `CLAUDE.md`'s **Architecture Decision Records (ADRs)** section.
- The behaviour the tests claim to verify, in `docs/analysis/`: `requirements.md`, the relevant
  use-case, `control-cycle.md`, `resolution-rules.md`.

Read conditionally:

- The **Testing Requirements** section of the `ha-integration-knowledge` skill — where the
  change includes HA-harness tests (`tests/adapters/`, `tests/test_coordinator.py`, entity/
  platform, config-flow, `tests/test_init.py`). Skip it for a change confined to
  `tests/modes/` or `tests/engines/`.

Then [`done.md`](done.md), the completion bar, before you start scoring rather than while you
write up.

## The checks that are yours alone

There are none, and that is a statement rather than a gap. [`done.md`](done.md) is the whole of
the checklist: apply every item in it as a review criterion, at the severity that item states,
including the scope each item states for itself. A test suite is judged entirely on what a
finished suite has to be, and every one of those items is as decidable by a reviewer reading
the changed tests as by the author who wrote them — item 3 says so of its own severity split,
and item 4 is a reading of the test against the implementation rather than a run of it.

Where a `development` change is under review alongside this one, the single place the two bars
meet is stated once, in that row's own completion bar, and is decided in the review that holds
both. This file adds nothing to it and must not restate it.
