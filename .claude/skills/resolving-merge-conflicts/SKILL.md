---
name: resolving-merge-conflicts
description: Use when a merge or rebase in this repo is already conflicted — `git status` reports unmerged paths, or a file carries conflict markers — most often after merging `origin/main` into a task branch before a review pass. Not for a merge that applied cleanly, not for deciding whether to merge, and not for a test that fails for reasons unrelated to the conflict.
---

# Resolving merge conflicts

Merging `origin/main` into the task branch before **every** review pass is a standing step of
this project's contribution workflow (defined in `CLAUDE.md`, **Contribution workflow**), so
conflicts here are routine rather than exceptional. Resolving one wrongly silently reverts work
that is already merged, and no later check catches that — which is why the procedure is written
down.

**Always resolve. Never abort the merge, and never re-run it hoping the conflict disappears.**

## Step 0 — know which commands you have

A `PreToolUse` hook (`.claude/hooks/block-destructive-git.sh`) denies the destructive git
commands that fall outside the standing commit/push authorization. Three of its rules bite
during a conflict, so plan around them instead of discovering them mid-merge:

- **Rebase is denied on a branch that has an upstream** — i.e. any branch already pushed, which
  a branch under review always is. Integrate with `git merge origin/main`; the workflow step
  that sends you here permits exactly that.
- **Whole-tree discards are denied** — `checkout .`, `restore .`, a hard reset, a forced clean.
  To take one side of a conflicted file wholesale, name the path:
  `git checkout --ours -- <path>` or `--theirs -- <path>`. Never "start over" by throwing the
  working tree away.
- **Force-push and forced branch deletion are denied.** No resolution needs either; if you
  believe yours does, you are rewriting published history — stop and ask the human partner.

Aborting the merge is not blocked by the hook. It is blocked by this skill.

## Step 1 — see the state

`git status` for the unmerged paths, and `git log --oneline --left-right HEAD...MERGE_HEAD` for
what each side actually contributed. Read every conflicted file whole, not just the marked
hunks: a conflict usually means the surrounding code moved too.

## Step 2 — find the primary sources for each side

Reconstruct *intent* before touching a marker. Each side of a conflict here has a paper trail,
in this order of usefulness:

1. **The commit message** — its prefix (`T<n>:`, `UC<nn>:`, `docs:`) names the kind of work.
2. **The anchored `Plan:` line** on the issue that commit's PR closes: it points at the exact
   task in a `docs/plans/` implementation plan, which states what that task was allowed to
   change.
3. **The PR body's `Closes #<n>` / `Part of #<n>`** — follow both; `Part of` leads to the epic,
   whose other children are often the other side of the conflict.
4. **The owning analysis or design doc** cited by that plan task.

A side whose intent you cannot state in one sentence is a side you cannot resolve. Keep reading.

## Step 3 — resolve each hunk

Preserve **both** intents wherever they compose. Where they genuinely do not, keep the side that
matches the stated goal of *this* merge — bringing a branch up to date with `main` means
`main`'s merged behaviour survives unless this branch's own issue exists to change it — and say
so in the PR thread. **Never invent a third behaviour that neither side wrote.**

Three cases are not ordinary hunk-merging:

- **The two sides disagree about what the system should do.** In `custom_components/`, that is
  not a merge decision. `docs/analysis/` owns behaviour and specs derive from it rather than
  design it (`write-impl-spec`'s *derive, don't design*). Resolve the mechanical part, then stop
  and escalate the disagreement to the owning analysis doc through its own issue-first cycle.
  Picking a winner inside a merge commit writes an undocumented behavioural decision into the
  code.
- **Generated or index-like content** — an epic body listing its children, `docs/adl/`
  numbering, a catalog or coverage table, a use-case inventory. Re-derive it from its source
  after taking both sides' underlying changes; hand-merging the rows yields a table matching
  neither side's reality. ADR numbers are never renumbered: if both sides claimed the same
  number, the later ADR moves to a free one (`CLAUDE.md`, **Architecture Decision Records**) and
  every reference to it moves with it.
- **A conflict that is really a stacked branch.** A PR based on `main` while the local branch
  sits on an unmerged prior branch shows the combined stack in its diff; that shrinks by itself
  once the lower branch merges. It is not a conflict to resolve, and never a reason to rewrite
  or re-point the lower branch — the contribution workflow's branching rule covers this case.

Leave no markers behind: grep the tree for `<<<<<<<`, `=======` and `>>>>>>>` before moving on.

## Step 4 — run the checks

A merge breaks things neither side broke alone. Run the full completion bar for what the merged
tree now touches — the paired lint and format checks, and the suite in the harness matched to
the change — as defined by the doc that `CLAUDE.md`'s **Contribution workflow** section names as
the completion bar, with the harness split per
[ADR-0009](../../../docs/adl/0009-testing-strategy.md). Do not shortcut to "the tests near my
conflict": the ones that catch a bad resolution are usually elsewhere.

Fix what the merge broke, in the merge, before committing.

## Step 5 — finish

Stage everything and commit. Keep git's default merge message, adding one line per hunk where a
side had to be dropped, naming which and why.

Then report to the human partner, before resuming the workflow step that sent you here: the
hunks where the two intents were incompatible and what you dropped, plus any behaviour
disagreement escalated in step 3 — that one is an open issue, not a resolved conflict.
