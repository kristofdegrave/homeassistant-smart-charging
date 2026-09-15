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

- The test files under review and the code they exercise — the trees the stack overlay names.
- The authorities the bar's items 1 and 2 rest on — the stack overlay names them under its
  **Review** section, and says which of them is conditional on what the change touches.
- The behaviour the tests claim to verify, in `docs/analysis/`: `requirements.md`, the relevant
  use-case, `control-cycle.md`, `resolution-rules.md`.

Read conditionally: what the stack overlays' **Review** sections name, on the condition each
states.

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

It also needs no route to it, and the reason is an assumption worth stating rather than
leaving to be rediscovered: that overlap is triggered by an adapter change, adapters are
product code under the tree the path map routes to the `development` checklist, and the path
half of that routing can never be skipped or steered. So the overlap cannot fire on a review
that reached this file alone. Move adapters out of that tree and the assumption goes with
them — this file would then need the route it does without today.

## Overlays

**Apply the overlays** the profile's declared stacks provide for this work type: one file per
stack at `overlays/<stack>.md` beside this one, its **Review** section read with this file as
part of the same checklist. An overlay adds the stack's material to the list or check that
names it and never restates one of this file; one that reads `none` is the stack saying it has
nothing to add here. The shape, and the rule that no stack material lives in this file, are
this tree's `README.md`'s.
