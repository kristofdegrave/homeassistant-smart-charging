# Work type: `documentation` — how the work is done

This file is the `documentation` row's work file in `CLAUDE.md`'s **Model selection** table. The
label covers two documents under `docs/design/`, and they are written differently enough to have
a work file each, so this one routes rather than instructs:

- [`system-design/implement.md`](system-design/implement.md) — for `docs/design/system-design.md`,
  the volatility-based service decomposition.
- [`project-plan/implement.md`](project-plan/implement.md) — for `docs/design/project-plan.md`,
  the task breakdown derived from it.

**Which branch a change is in is stated once, in the completion bar** — [`done.md`](done.md),
beside this file — together with why the label splits at all. Read the condition there, not
here: the bar is the one per-type file the author and the reviewer both read, so stating it
there costs neither of them a read, while stating it here would put the reviewer inside the
author's recipe to find out which bar applies.

Everything about how either document is written is in the branch file. Nothing is duplicated
here, and a change that touches both documents follows both.
