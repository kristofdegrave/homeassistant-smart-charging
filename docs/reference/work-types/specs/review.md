# Work type: `specs` — the review checklist

**Who reads this.** The reviewer only — a fresh, read-only Opus agent, never the session that
drafted the spec. It holds what only a reviewer can check: what to read first, and the checks
that are about the **change** rather than the finished documents. What must be true of a
finished spec is [`done.md`](done.md) beside this file, and how one is written is
[`implement.md`](implement.md); neither is restated here.

The output format, the severity grouping, the anchoring rules and the untrusted-data rule are
not here either. They are the same for every review and live with whoever applies this
checklist — the generic `reviewer` agent definition locally, the review workflow's own prompt
in CI, which has no agent to spawn and self-applies instead. Both reach this file the same
way, through `CLAUDE.md`'s **Model selection** table.

An implementation spec translates an approved slice of the system design into a concrete,
test-driven build sequence. It **derives** from the architecture — it never re-decomposes it
or invents new behaviour. Review it on that footing.

## What to read first

Always read:

- The file(s) under review in `docs/plans/` — read both the `-design.md` and the paired TDD
  plan if both exist, since the plan must stay consistent with the design.

Then the documents the spec derives from, which is what makes the bar decidable. The
`CLAUDE.md` sections that own each topic name them: **Document structure**, for the analysis
documents this project's behaviour lives in (the requirements, the glossary, the control cycle,
the resolution rules, the entity catalog and the use-cases) and for the design documents that
own the service catalog and the build order; and **Architecture Decision Records (ADRs)**, for
the accepted records the spec is gated on. Read the ones the spec touches, not the trees whole.

Then [`done.md`](done.md), the completion bar, before you start scoring rather than while you
write up. It also enumerates the records a slice is ordinarily gated on, which is what turns
"the ones the spec touches" into a list rather than a judgement call.

## The checks that are yours alone

[`done.md`](done.md) is the bulk of the checklist: apply every item in it as a review
criterion, at the severity that item states. Two checks are not in it, because they are about
the **change** rather than about the finished documents, and an author checking their own draft
cannot make them. Everything else — including the scope each bar item states for itself — comes
from the bar, not from here.

**(A) The pair is complete as a change.** A design doc naming a paired TDD plan this diff does
not add, or a TDD plan whose design doc is neither in the change nor already on the base
branch, leaves the bar's item 3 judged against half an artifact. Say which half is missing and
report it against that item at the severity it states, rather than reviewing the present half
as though it were the whole.

**(B) Where a finding belongs to another document, say so and stop there.** Several bar items
resolve to a defect in a document this spec only cites — a behavioural rule no analysis doc
states, a conflict between the spec and its source, a service the design doc does not carry.
Name the owning document and what it would have to say. Do not propose wording for the spec
that papers over it, and never recommend deleting text the plan holds the only copy of.
