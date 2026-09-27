# Work type: `decompose` — the review checklist

**Who reads this.** A reviewer dispatched against this row. Every enabled work type holds
this role file (`work-types/README.md`'s **The three roles**); this one states where the review of this work
type happens, and names no criteria of its own.

**The pass is the review.** A `decompose` run changes no file, so there is no pull request, no
diff and nothing the path map of `CLAUDE.md`'s **Model selection** section selects. Its review
is the decomposition-checklist pass that `implement.md`'s entry 1 runs over the epic body: one
fresh `reviewer` agent, applying the checklist `CLAUDE.md`'s **Decomposition checklist** topic
routes to, to the body handed over as a file. It runs inside the implement step, before the
park, because the human's read follows it and nothing else does — the closing step of the flow
`CLAUDE.md`'s **Idea-to-product flow** topic routes to fixes that order. What the pass checks,
at what severity, and which two of the reviewer's defaults do not apply are that checklist's.
The bar, `done.md`, scores what the pass cannot: that it ran once, and what the run left on
the tracker; the author applies it, and the human's read is the second reader.

**A reviewer reached by a dispatch against this row** was misrouted, since the pass above is
the review and it has already run: say so, then apply `done.md`'s bar — and no checklist
beyond it — to the parked epic body and what the run left on the tracker, which is what the
dispatch can still see. The verdict is the bar's; a diff handed over with the dispatch is
outside this row and is reported, not reviewed.
