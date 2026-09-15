# Work type: `documentation` — the review checklist

**Who reads this.** The reviewer only — a fresh, read-only Opus agent, never the session that
drafted the document. It holds what only a reviewer can check: what to read first, and the
checks that are about the **change** rather than the finished documents. What must be true of a
finished system design or project plan is [`done.md`](done.md) beside this file, and how either
is written is [`implement.md`](implement.md); both route onward per document, and neither is
restated here.

The output format, the severity grouping, the anchoring rules and the untrusted-data rule are
not here either. They are the same for every review and live with whoever applies this
checklist — the generic `reviewer` agent definition locally, the review workflow's own prompt
in CI, which has no agent to spawn and self-applies instead. Both reach this file the same
way, through `CLAUDE.md`'s **Model selection** table.

**Why this file sits at the label's own level with no per-branch copies.** One reviewer covers
both of the label's documents, and everything only a reviewer can check is the same for both:
the reading order below holds whichever document changed, and each of the two change-level
checks is *about* the pair. What genuinely differs per document is criteria, and all of it is in
the bar — which is also where the label's branch condition is stated, once. So this file never
routes by document; [`done.md`](done.md) does, and this file sends you there.

These documents apply Juval Löwy's IDesign Method: volatility-based service decomposition, not
functional decomposition, and a task breakdown derived mechanically from it. Review them on
that footing.

## What to read first

Always read:

- The file(s) under review in `docs/design/` — read both the system design and the project plan
  if both exist, even when only one changed, since the plan's bar judges it against the design.

Then the documents the design is judged against, which is what makes the bar decidable.
`CLAUDE.md`'s **Document structure** section owns them, and each bar item names the ones that
item needs — read those, not the trees whole.

Then [`done.md`](done.md), the completion bar, before you start scoring rather than while you
write up. It routes to the per-document bar for each file you were handed.

## The checks that are yours alone

The bar [`done.md`](done.md) routes to is the bulk of the checklist: follow it to the bar for
each file you were handed and apply **that** bar's every item as a review criterion, at the
severity the item states. Two checks are not in it, because they are about the **change** rather
than about the finished documents, and an author checking their own draft cannot make them.
Everything else — including the scope each bar item states for itself — comes from the bar, not
from here.

**(A) Whether the change is complete as a change.** A bar item can be satisfied by a file you
were not shown. A design that adds or renames a service without the project plan's task list
following it, or a plan whose system design is neither in this change nor already on the base
branch, leaves the bar judged against half an artifact. Say which half is missing and report it
against the bar item at the severity it states, rather than reviewing the present half as
though it were the whole. A glossary term the design introduces is the same case: the
`system-overview.md` entry belongs in *this* diff.

**(B) Where a finding belongs to the counterpart document, say so and stop there.** Several bar
items resolve to a defect in the counterpart of the document under review — a plan that cannot
be ordered because the design's call directions are ambiguous, a design gap the plan worked
around. Name the owning document and what it would have to say. Do not propose wording that
papers over it in the document you were handed.

## Overlays

**Apply the overlays** the profile's declared stacks provide for this work type: one file per
stack at `overlays/<stack>.md` beside this one, its **Review** section read with this file as
part of the same checklist. An overlay adds the stack's material to the list or check that
names it and never restates one of this file; one that reads `none` is the stack saying it has
nothing to add here. The shape, and the rule that no stack material lives in this file, are
this tree's `README.md`'s.
