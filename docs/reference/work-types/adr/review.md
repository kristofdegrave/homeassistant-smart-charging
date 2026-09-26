# Work type: `adr` — the review checklist

**Who reads this.** The reviewer — a fresh, read-only Opus agent, never the session that
drafted the record — and, for *What the review step supplies and runs*, the review step. It
holds what only a reviewer can check: what to read first, and the checks about the **change**
rather than the finished record; and what the review step supplies and runs for it. What a finished ADR must satisfy is
[`done.md`](done.md); how one is written is [`implement.md`](implement.md). Neither is restated
here.

Output format, severity grouping, anchoring rules and the untrusted-data rule are the same for
every review and live with the generic `reviewer` agent that applies this checklist, which
reaches this file through `CLAUDE.md`'s **Model selection** table.

## What to read first

In `docs/adl/`:
- the ADR under review;
- `template.md` — the authoritative template, Summary before Context;
- `0001-use-architecture-decision-records.md` — why ADRs, and why this template;
- `README.md` — the Architecture Decision Log;
- every other ADR — contradiction and duplication are judged against the full log, not the
  neighbours.

Then [`done.md`](done.md), before you start scoring.

Also read what the ADR cites (`R7`, `UC03`, a design document) when it exists on this branch.
A backfill ADR may cite a doc that exists only on another open branch: expected, not a broken
reference — judge the ADR on internal merit.

## What the review step supplies and runs

- **Input:** the remote `adr/NNNN` branch list, as `implement.md`'s *Number* count lists it,
  for a change touching `docs/adl/**`. The bar's item 2 judges the number against it. None supplied → say
  the number was not checked.
- **Exit check:** on a change adding an ADR, `implement.md`'s *Merge in number order*, before
  any exit label goes on.

## The checks that are yours alone

Apply every item of [`done.md`](done.md) at the severity and in the scope it states. Two more
checks are about the **change**, which an author checking their own draft cannot make:

**(A) Immutability.** The change edits an existing ADR in any way
[`implement.md`](implement.md)'s *Immutable once merged* does not list → **Critical**.
- Judge from the diff, never the file as it now stands. Under the bar's item 10 every ADR reads
  `Accepted` from its first draft, so a working-tree read turns each draft revision into a
  false Critical.
- Fires on every **existing** record — one with lines on the LEFT side — whatever its Status
  there: a `Superseded`, `Deprecated` or `Abandoned` record is as immutable as an `Accepted`
  one. A file the change adds is a new record; revising it is drafting.

**(B) The change is complete as a change.** A bar item can be met by a file you weren't shown.
Check this diff carries the ADL row (bar item 2, *Template conformance*) and, for a
supersession or deprecation, the old record's Status-line edit (bar item 8, *It doesn't
contradict an Accepted ADR without superseding it*) with its ADL row's Status changed to
match. Report a miss against that item at its severity. `implement.md` already puts them in
one PR, so the finding is an incomplete PR, not a case for a separate one. An `Abandoned`
record carries no such edit: one still in its diff → **Major**, since `implement.md` reverts
it.
