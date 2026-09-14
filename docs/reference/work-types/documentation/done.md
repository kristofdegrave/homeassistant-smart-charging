# Work type: `documentation` — the completion bar

This file is the `documentation` row's completion bar in `CLAUDE.md`'s **Model selection**
table. Like this label's work file it routes rather than instructs, because the label's two
documents are judged against disjoint criteria.

## Which bar applies

By which of the documents under `docs/design/` the change touches. **This is the label's branch
condition, and this file is its only home** — the work file beside this one routes here for it,
and so does anything else that needs it:

- `system-design.md` → [`system-design/done.md`](system-design/done.md)
- `project-plan.md` → [`project-plan/done.md`](project-plan/done.md)

A change touching both documents is judged against both bars, each against its own document.
Neither bar is a default for a document the other names.

## Why there are two

The two documents are judged on criteria with nothing in common: one is judged on whether each
service cut encapsulates a real volatility and the call directions hold, the other on whether a
task breakdown follows the architecture it derives from. A single bar covering both would carry
an "if" in every item, and an item that applies to half its artifact is one a reviewer learns to
skim.

That rests on `docs/design/` holding exactly one document per branch. **A third document there
means a third branch and a third bar** — otherwise it is silently covered by neither, matched by
neither route above and judged by nothing.
