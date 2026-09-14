# Work-type documents

This tree holds the per-work-type instructions that used to live inside the skills and reviewer
agents: how each artifact is written, and what must be true of a finished one. It describes the
**shape** of the tree and nothing about any particular work type — the per-label content is in
the files themselves, and the authoritative mapping from a work type to its files is the
matching row of `CLAUDE.md`'s **Model selection** table.

Read this when you are adding a work type, adding a role file to one, or working out which file
a row means. Read `CLAUDE.md`'s **Model selection** section when you need to know which files a
given change is governed by — that row is the source of truth, and this document never
overrides it.

## The shape

One directory per **context label**, named exactly for the label:

```text
docs/reference/work-types/<label>/<role>.md
```

So `adr/implement.md`, `uc/done.md`. The label is the directory name, which is what makes
renaming a label a directory move rather than an edit — `ci-pipeline.md`'s **Label vocabulary
sync** owns that obligation and the rest of what a rename touches.

Not every label has a directory. A label gets one when its work type has content worth writing
down; `workflow` deliberately has none (no automated drafting, human-authored), and a label may
have a work file without a completion bar or vice versa. The row is what says which files
exist, so an absent file is a fact about the row, not a gap in this tree.

## The three roles

| File | What it holds | Who reads it |
|---|---|---|
| `implement.md` | How the artifact is written — the drafting order, the template, the rules, the mistakes. | The author, and a CI drafting run. |
| `done.md` | The **completion bar**: what must be true of the finished artifact, each item carrying the severity a miss lands at. | The author, as the self-check before requesting review, **and** the reviewer, as the bulk of the review criteria — `CLAUDE.md`'s **Model selection** section says why one file serves both. |
| `review.md` | Reviewer-only material: how to read the change, and the checks about the *change* rather than the artifact. | The reviewer. |

`review.md` **does not exist for any label yet.** That material still sits in the reviewer agent
definitions under `.claude/agents/`; the pass that moves it is the one that makes the reviewer
agents generic, and it is that pass which adds these files.

## When a label branches

A row may split on **which file the change touches** rather than on the label alone. Such a
label gets one subdirectory per branch, named for the branch:

```text
docs/reference/work-types/<label>/<branch>/<role>.md
```

`documentation` is the case: `system-design/` and `project-plan/`, for the two documents under
`docs/design/`.

The level a file sits at is what says who it binds:

- a file **inside a branch directory** applies to that branch only;
- a file at the **label's own level**, beside the branch directories, applies to every branch.

That distinction is the reason for the nesting, and it is load-bearing rather than cosmetic:
one role can be shared across a label's branches while another is split, and the level a file
sits at is the whole of how that is expressed. **Which** of a branching label's roles are shared
and which are split is that label's own question, not this document's: its row decides it, under
the rules `CLAUDE.md`'s **Model selection** section states. This document says only where a file
of each kind goes once that is settled.

Because the role names never change with the depth, every leaf reads the same as every
unbranched label's directory.

## When two labels share a bar

Two labels may point at **one** `done.md` rather than each having their own. **Whether a given
pair may is `CLAUDE.md`'s Model selection section to decide** — it states the rule that earns
it, and this document does not repeat it: a rule restated here, however carefully attributed,
is a second copy that drifts.

What the shape looks like where it applies: the worked case is `requirement/done.md`, which is
a route to `uc/done.md` and restates nothing of it. Each label still keeps its own directory
and its row still names a path inside that directory, so the row stays self-contained; only
the file's contents are shared.

Two branches of one label are a different case, not this one — see **When a label branches**
above.

## What a file in this tree may say

These documents do not travel between repositories the way a skill or an agent definition does,
so `ai-authoring.md`'s routing rules bind them only in part: they may name this project's paths,
its documents and its tracker commands directly. That reference states exactly which of its
checklist items still apply and which are carved out — read it there rather than inferring the
line from examples here.

Two rules do apply, in full:

- **One source of truth per fact.** A rule stated in the bar is not restated in the work file;
  the work file points at the bar's item by number and title and says what it means while
  drafting. The same goes the other way, and for anything `CLAUDE.md` already owns.
- **The content is instructions to future runs**, CI runs included. Write it as instruction,
  with completion criteria a run can decide, not as commentary about the work type.
