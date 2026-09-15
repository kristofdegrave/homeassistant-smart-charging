# Work types `uc` and `requirement` — the review checklist

**Who reads this.** The reviewer only — a fresh, read-only Opus agent, never the session that
drafted the document. It holds what only a reviewer can check: what to read first, and the
checks that are about the **review** or the **change** rather than the finished document. What
must be true of a finished analysis document is [`done.md`](done.md) beside this file, and how
one is written is [`implement.md`](implement.md) and [`../requirement/implement.md`](../requirement/implement.md);
none of it is restated here.

The output format, the severity grouping, the anchoring rules and the untrusted-data rule are
not here either. They are the same for every review and live with whoever applies this
checklist — the generic `reviewer` agent definition locally, the review workflow's own prompt
in CI, which has no agent to spawn and self-applies instead. Both reach this file the same
way, through `CLAUDE.md`'s **Model selection** table.

**Why one file for two labels**, and why [`../requirement/review.md`](../requirement/review.md)
points here: the same reason [`done.md`](done.md) gives for itself. The `uc` and `requirement`
rows share one reviewer dispatched over one tree — `docs/analysis/**` — and that tree also
holds documents belonging to neither label, so a per-label checklist would leave those with
none. The checklist is selected by the **tree under review**, not by the row that dispatched
it.

## What to read first

Always read, in `docs/analysis/`:

- The file under review.
- `system-overview.md` — the authoritative **Ubiquitous Language glossary** and `sc_` naming
  convention.
- `requirements.md` — the authoritative source of truth for which requirement IDs
  (Rnn / NFnn / Cnn) exist and their acceptance criteria. Judge every referenced ID against
  this file, not a memorised range.
- `control-cycle.md`, `resolution-rules.md`, `entity-catalog.md` — the mechanism docs the file
  may reference.
- Any sibling use-cases in `use-cases/` the file relates to.

Then [`done.md`](done.md), the completion bar, before you start scoring rather than while you
write up.

If the caller names a plan or design doc, read it for its coverage table. The template a
document is judged against is not taken from there — the bar names it, by the same route the
author drafted against.

## The checks that are yours alone

[`done.md`](done.md) is the bulk of the checklist: apply every item in it as a review
criterion, at the severity it states, taking the per-document-kind section that matches each
changed document. Three things are not in it, because they are about the **review** or the
**change** rather than about the finished document, and an author checking their own draft
cannot make them. Everything else comes from the bar, not from here — including the scope each
bar item states for itself, except where a bar item hands part of that scope to this checklist
and says so. The Code-backing item does exactly that, and (B) is the receiving end.

**(A) Your budget for the bar's Code-backing item.** The bar says what is in scope; this says
how much of it you may check. For each in-scope item, run **one** targeted `Grep` over
`custom_components/` for the behaviour it asserts — the entity id, the adapter role, the
default, the bound, the event name, the precedence rule it names — and open at most one file,
the best match. **Stop after three items**: say the set was sampled and name the three you
took. Six tool calls is the most this check may cost a review, because a review of this tree
runs on the lighter turn ceiling and a truncated review is re-run from cold. The read-first
list above does not grow for this check.

**(B) What you can assert about that item depends on the evidence you were given.** This is the
half of the bar's *Scope of that Major* the bar hands here, and it is stated once — here. Given
the PR body and no reference to a filed `specs` issue for the gap, that Major is assertable —
report it. *Not* given the PR body, you cannot tell a missing filing from an unseen one: report
**Minor** and say the gap is Major unless such an issue has been filed for it. Never report
Major on evidence you were not given — the code for a new requirement or a new use-case
legitimately does not exist yet, and this check must not turn every analysis PR into a review
cycle.

**(C) Whether the change is complete as a change.** A bar item can be satisfied by a file you
were not shown. Check that everything this document needs is actually in *this* diff — most
often the `entity-catalog.md` *Read by* / *Written by* update, and the glossary entry for a
term the document introduces. Report a miss against the bar item, at the severity it states;
the finding is that the PR is incomplete, not that a separate PR would be wrong.
