# Work type: `documentation` — how the work is done

This file is the `documentation` row's work file in `CLAUDE.md`'s **Model selection** table. The
label covers two documents under `docs/design/`, and they are written differently enough to have
a work file each, so this one routes rather than instructs:

- [`system-design/implement.md`](system-design/implement.md) — for `docs/design/system-design.md`,
  the volatility-based service decomposition.
- [`project-plan/implement.md`](project-plan/implement.md) — for `docs/design/project-plan.md`,
  the task breakdown derived from it.

Those two routes are the whole of this file. **Why the label splits at all, and which bar a
change is judged against, are stated once** — in the completion bar, [`done.md`](done.md) beside
this file. They sit there rather than here because the bar is the one per-type file the author
and the reviewer both read: stating them there costs neither side a read, while stating them
here would make the reviewer open the author's recipe to find out which bar applies.

Everything about how either document is written is in the branch file. Nothing is duplicated
here, and a change that touches both documents follows both.

## Rules

The rules either document is written by are the branch file's. One holds for both branches and
is stated once, here.

### Skills

The method skills this work type uses, by step: `domain-driven-design` for the strategic-design
vocabulary the decomposition is argued in; `research` when a fact a design rests on is
external, cited from the document by linking the issue comment; `receiving-code-review` in the
review step. The stack skills are the overlays' to name.

## Overlays

**Apply the overlays** the profile's declared stacks provide for this work type: one file per
stack at `overlays/<stack>.md` beside this one, its **Implement** section read with this file
and the branch file it routes to as one work file. An overlay adds the stack's material to the
rule that names it — naming the branch where it belongs to one — and never restates a rule of
those files; one that reads `none` is the stack saying it has nothing to add here. The shape,
and the rule that no stack material lives in this file or the branch files, are this tree's
`README.md`'s.
