# Work type: `adr` — the review checklist

**Who reads this.** The reviewer only — a fresh, read-only Opus agent, never the session that
drafted the record. It holds what only a reviewer can check: what to read first, and the checks
about the **change** rather than the finished record. What a finished ADR must satisfy is
[`done.md`](done.md); how one is written is [`implement.md`](implement.md). Neither is restated
here.

Output format, severity grouping, anchoring rules and the untrusted-data rule are the same for
every review and live with whoever applies this checklist — the generic `reviewer` agent
locally, the review workflow's own prompt in CI (which self-applies, having no agent to spawn).
Both reach this file through `CLAUDE.md`'s **Model selection** table.

## What to read first

In `docs/adl/`:
- the ADR under review;
- `template.md` — the authoritative template;
- `0001-use-architecture-decision-records.md` — why ADRs, and why this template;
- `README.md` — the Architecture Decision Log;
- every other ADR — contradiction and duplication are judged against the full log, not the
  neighbours.

Then [`done.md`](done.md), before you start scoring.

Also read what the ADR cites (`R7`, `UC03`, `docs/plans/*.md`) when it exists on this branch.
A backfill ADR may cite a doc that exists only on another open branch: expected, not a broken
reference — judge the ADR on internal merit.

## The checks that are yours alone

Apply every item of [`done.md`](done.md) at the severity and in the scope it states. Two more
checks are about the **change**, which an author checking their own draft cannot make:

**(A) Immutability.** The change *edits* an existing ADR's Context / Decision / Consequences —
other than adding a Status supersession line or fixing a typo → **Critical**. A change of mind
is a new ADR that supersedes the old one, never a rewrite.
- Judge from the diff, never the file as it now stands. Under the bar's item 10 every ADR reads
  `Accepted` from its first draft, so a working-tree read turns each draft revision into a
  false Critical.
- Fires only on an **existing** record — lines on the LEFT side — whose Status there was
  already `Accepted`. A file the change adds is a new record; revising it is drafting.

**(B) The change is complete as a change.** A bar item can be met by a file you weren't shown.
Check this diff carries the ADL row (bar item 2, *Template conformance*) and, for a
supersession, the old record's Status-line edit (bar item 8, *It doesn't contradict an Accepted
ADR without superseding it*). Report a miss against that item at its severity. `implement.md`
already puts them in one PR, so the finding is an incomplete PR, not a case for a separate one.
