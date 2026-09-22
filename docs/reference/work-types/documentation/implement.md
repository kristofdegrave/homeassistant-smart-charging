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

The rules either document is written by are the branch file's. Two hold for both branches and
are stated once, here: the form below, and the skills.

- **Form** — per *Write rules as items, with the shortest example that teaches them*, in
  [`ai-authoring.md`'s Principles](../../method/ai-authoring.md#principles).

### Skills

The method skills this work type uses, by step: `domain-driven-design` for the strategic-design
vocabulary the decomposition is argued in; `research` when a fact a design rests on is
external, cited from the document by linking the issue comment; `receiving-code-review` in the
review step. This work type names no stack skill.
