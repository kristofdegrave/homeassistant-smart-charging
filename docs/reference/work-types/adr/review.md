# Work type: `adr` — the review checklist

**Who reads this.** The reviewer only — a fresh, read-only Opus agent, never the session that
drafted the record. It holds what only a reviewer can check: what to read first, and the
checks that are about the **change** rather than the finished record. What must be true of a
finished ADR is [`done.md`](done.md) beside this file, and how one is written is
[`implement.md`](implement.md); neither is restated here.

The output format, the severity grouping, the anchoring rules and the untrusted-data rule are
not here either. They are the same for every review and live with whoever applies this
checklist — the generic `reviewer` agent definition locally, the review workflow's own prompt
in CI, which has no agent to spawn and self-applies instead. Both reach this file the same
way, through `CLAUDE.md`'s **Model selection** table.

## What to read first

Always read, in `docs/adl/`:

- The ADR under review.
- `template.md` — the authoritative template (Status, Context, Considered options with
  Pro/Con per option, Decision, Consequences).
- `0001-use-architecture-decision-records.md` — why this project uses ADRs and why the
  template looks the way it does.
- `README.md` — the Architecture Decision Log index.
- Every other file in `docs/adl/` — an ADR can only be judged for contradiction and
  duplication against the full log, not just its immediate neighbours.

Then [`done.md`](done.md), the completion bar, before you start scoring rather than while you
write up.

If the ADR references a requirement, use-case, or design doc (`R7`, `UC03`, `docs/plans/*.md`),
read that too, when available on this branch — a backfill ADR may cite a doc that only exists
on a different, still-open branch; treat that as expected, not a broken reference, and judge
the ADR on internal merit instead.

## The checks that are yours alone

[`done.md`](done.md) is the bulk of the checklist: apply every item in it as a review
criterion, at the severity that item states. Two checks are not in it, because they are about
the **change** rather than about the finished record, and an author checking their own draft
cannot make them. Everything else — including the scope each bar item states for itself —
comes from the bar, not from here.

**(A) Immutability.** If this change *edits* an existing ADR's Context / Decision /
Consequences — as opposed to adding a Status supersession line, or fixing a typo — that is a
**Critical** finding. A change of mind must be a new ADR that supersedes the old one, never a
rewrite of an accepted one.

Judge it from the diff, never from the file as it now stands. The bar's item 10 states the
drafting convention that makes a working-tree read wrong: under it, every ADR reads `Accepted` from
its first draft, so a working-tree read makes a record still being drafted look immutable and
turns every legitimate draft revision into a false Critical.

So: this check fires only where the diff shows an **existing** record — one with lines on the
LEFT side — whose Status there was already `Accepted`. A file the change adds outright is a new
record, and revising it is drafting, not rewriting.

**(B) Whether the change is complete as a change.** A bar item can be satisfied by a file you
were not shown. Check that everything this ADR needs is actually in *this* diff: the ADL row
(bar item 2, *Template conformance*) and, where the ADR supersedes another, that record's
Status-line edit (bar item 8). Report a miss against the bar item, at the severity it
states — `implement.md` already rules that they belong to one PR, so the finding is that the
PR is incomplete, not that a separate PR would be wrong.

## Overlays

**Apply the overlays** the profile's declared stacks provide for this work type: one file per
stack at `overlays/<stack>.md` beside this one, its **Review** section read with this file as
part of the same checklist. An overlay adds the stack's material to the list or check that
names it and never restates one of this file; one that reads `none` is the stack saying it has
nothing to add here. The shape, and the rule that no stack material lives in this file, are
this tree's `README.md`'s.
