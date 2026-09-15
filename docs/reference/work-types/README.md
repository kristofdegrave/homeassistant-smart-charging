---
layer: method
---

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

Not every label has a directory, and a label that has one need not hold all three roles. A
label gets a directory when its work type has content worth writing down, and each role file
appears when that role has content of its own: a label may have a work file without a
completion bar or vice versa. `workflow` is the extreme case and a deliberate one — it is never
drafted from an issue, so it has **no work file and no completion bar**, and its directory holds
`review.md` alone. Do not manufacture the other two for symmetry: the document `CLAUDE.md`'s
**Model selection** section routes to argues why that label has no drafted work, and a
placeholder work file would contradict it. The row is what says which files exist, so an absent file is a fact about the
row, not a gap in this tree.

## The three roles

`CLAUDE.md`'s row is what names a file; this table says what each name holds. The names are
`implement.md`, `done.md` and `review.md`, each appearing when the role it carries has content —
which of them a given directory holds is **The shape** above. They are this tree's own
convention, not something the cell grammar states: that names the three *roles* and leaves each
row to name its paths literally. So if a row ever names a different filename, the row governs
and this line is the copy that shrinks.

| File | What it holds | Who reads it |
|---|---|---|
| `implement.md` | How the artifact is written — the drafting order, the template, the rules, the mistakes. | The author, and a CI drafting run. |
| `done.md` | The **completion bar**: what must be true of the finished artifact, each item carrying the severity a miss lands at. | The author, as the self-check before requesting review, **and** the reviewer, as the bulk of the review criteria — the document `CLAUDE.md`'s **Model selection** section routes to says why one file serves both. |
| `review.md` | Reviewer-only material: how to read the change, and the checks about the *change* rather than the artifact. | The reviewer. |

`review.md` **exists for the labels whose reviewer has been made generic** — `adr`, `uc`,
`requirement`, `specs`, `development`, `testing`, `documentation` and `workflow` — every label
that has a directory, `requirement/review.md` being a pointer to `uc/`'s the way its `done.md`
is. A label whose directory holds `review.md` and nothing else is migrated, not half-built —
see the paragraph above. What a generic reviewer holds instead — the output contract, the anchoring rules and how
a checklist is resolved — sits with whoever applies the checklist: `.claude/agents/reviewer.md`
locally, and CI's own review-workflow prompt, which has no agent to spawn and self-applies the
file instead.

## When a label branches

A work type may cover more than one artifact, written differently and judged differently. Such
a label keeps the ordinary role files at its **own level** — that is what its row names, exactly
like an unbranched label — and those files route onward to one subdirectory per branch, named
for the branch:

```text
docs/reference/work-types/<label>/<branch>/<role>.md
```

`documentation` is the case: `system-design/` and `project-plan/`, for the two documents under
`docs/design/`.

The level a file sits at is what says who it binds:

- a file at the **label's own level** applies to every branch — and, for a role that is split,
  it is where the routes to each branch's file live;
- a file **inside a branch directory** applies to that branch only.

Where the split needs spelling out — which artifact sends a change down which branch, and why
the role is split at all — that belongs at the label's own level too, stated in **one** of those
files with the others routing to it rather than repeating it. `documentation` states it in its
`done.md`, the file both the author and the reviewer read.

That distinction is the reason for the nesting, and it is load-bearing rather than cosmetic: one
role can be shared across a label's branches while another is split, and the level a file sits
at is the whole of how that is expressed. A shared role is simply one file at the label's own
level with no branch copies beneath it — which is what `review.md` is for `documentation`,
whose reviewer covers both branches. **Which** of a label's roles are split is that label's own
question, settled in its files rather than here; this document says only where a file of each
kind goes.

The row is unaffected by any of this: it names the label's own `implement.md` and `done.md`, and
a run that follows them reaches the branch without the row ever mentioning one.

Because the role names never change with the depth, every leaf reads the same as every
unbranched label's directory.

## When two labels share a bar

Two labels may point at **one** `done.md` rather than each having their own. **Whether a given
pair may is decided by the rule *Two rows may share one bar*** — in the document `CLAUDE.md`'s
**Model selection** section routes to — and this document does not repeat that rule: a rule
restated here, however carefully attributed, is a second copy that drifts.

What the shape looks like where it applies: each label still has its own directory with its own
`done.md` in it, and one of those files is a route to the other rather than a copy of it. Only
the contents are shared — no label loses its directory, and nothing moves out of one.

Two branches of one label are a different case, not this one — see **When a label branches**
above.

## What a file in this tree may say

**A file in a label's directory** does not travel between repositories the way a skill or an
agent definition does, so `ai-authoring.md`'s routing rules bind it only in part: it may name
this project's paths, its documents and its tracker commands directly. That reference states
exactly which of its checklist items still apply to such a file and which are carved out — read
it there rather than inferring the line from examples here, and note that the carve-out it
grants is scoped to those directories. This README is not one of them: it is an ordinary
reference document under `docs/reference/`, outside that rule's subject matter altogether.

Two rules bind every file in this tree, in full, this README included:

- **One source of truth per fact.** A rule stated in the bar is not restated in the work file;
  the work file points at the bar's item by number and title and says what it means while
  drafting. The same goes the other way, and for anything `CLAUDE.md` already owns.
- **The content is instructions to future runs**, CI runs included. Write it as instruction,
  with completion criteria a run can decide, not as commentary about the work type.
