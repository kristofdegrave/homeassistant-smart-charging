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

**Always resolve.** Never re-run the merge hoping the conflict disappears, and never `--abort`
on your own judgement — if the operation itself was the mistake (started against the wrong ref,
say), ask the human partner rather than deciding it here.

## Step 0 — know which commands you have

Some destructive git commands fall outside the standing commit/push authorization and are
refused mechanically by a `PreToolUse` guard. `CLAUDE.md`, **Contribution workflow**, names both
the authorization and the guard script, and that script is the authority on exactly what it
refuses and when — read it if a command comes back refused. Two of its decisions shape this
procedure:

- **Integrate with `git merge origin/main`, not a rebase.** Starting a rebase is denied on a
  branch that has an upstream — the guard's proxy for "already published", which a branch under
  review normally is. The workflow step that sends you here accepts either, so merge. Flags that
  only steer a rebase *already* in progress stay available, so a rebase legitimately started on
  an unpublished branch can always be finished.
- **Name paths; never discard the tree.** Take one side of a conflicted file with
  `git checkout --ours -- <path>` or `--theirs -- <path>`. In a **merge**, `--ours` is the branch
  you are on and `--theirs` is what you are merging in; in a **rebase** the two invert, `--ours`
  becoming the upstream you are replaying onto and `--theirs` your own commit. Confirm which
  operation you are in before trusting either — taking the wrong side here is exactly the silent
  revert this skill exists to prevent. Discarding the whole working tree is denied, as are
  force-push and forced branch deletion — no resolution needs any of them, and if yours seems to,
  you are rewriting published history: stop and ask the human partner.

`--abort` is not blocked by the guard. It is blocked by this skill, absent the human partner's
say-so.

## Step 1 — see the state

`git status` for the unmerged paths, and `git log --oneline --left-right HEAD...MERGE_HEAD` for
what each side contributed. In a rebase the incoming commit is `REBASE_HEAD` and `HEAD` already
carries whatever replayed cleanly before it, so read that pair as "what is landing now", not as
a two-side split. Either way, read every conflicted file whole rather than only the marked
hunks: a conflict usually means the surrounding code moved too.

## Step 2 — find the primary sources for each side

Reconstruct *intent* before touching a marker. Each side of a conflict here has a paper trail,
in this order of usefulness:

1. **The commit message** — its prefix names the kind of work the commit did; the prefix
   vocabulary is in the completion-bar doc's commit-message conventions, reached from
   `CLAUDE.md`, **Contribution workflow**.
2. **The anchored `Plan:` line**, where the issue that commit's PR closes carries one — only
   implementation-track issues do. It points at the exact task in an implementation plan, which
   states what that task was allowed to change. `CLAUDE.md`, **Issue conventions**, gives that
   line's required format and which issues must carry it.
3. **The PR body's `Closes #<n>` / `Part of #<n>`** — follow both; `Part of` leads to the epic,
   whose other children are often the other side of the conflict.
4. **The owning specification document** — the analysis and design documents that `CLAUDE.md`'s
   **Document structure** section lists, reached from the plan task or from the changed file
   itself.

A side whose intent you cannot state in one sentence is a side you cannot resolve. Keep reading.

## Step 3 — resolve each hunk

Preserve **both** intents wherever they compose. Where they genuinely do not, keep the side that
matches the stated goal of *this* merge — bringing a branch up to date with `main` means
`main`'s merged behaviour survives unless this branch's own issue exists to change it — and say
so in the PR thread. **Never invent a third behaviour that neither side wrote.**

Three cases are not ordinary hunk-merging:

- **The two sides disagree about what the system should do.** In product code, that is not a
  merge decision. Behaviour is owned by the analysis documents that `CLAUDE.md`'s **Document
  structure** section lists, and specs derive from them rather than design it
  (`write-impl-spec`'s *derive, don't design*). Resolve the mechanical part, then stop and
  escalate the disagreement to the owning analysis doc through its own issue-first cycle.
  Picking a winner inside a merge commit writes an undocumented behavioural decision into the
  code.
- **Generated or index-like content** — an epic body listing its children, ADR numbering, a
  catalog or coverage table, a use-case inventory. Re-derive it from its source after taking
  both sides' underlying changes; hand-merging the rows yields a table matching neither side's
  reality. The ADR log needs one extra rule of its own, for the case where both sides claimed the
  same number — a case `write-adr`'s one-ADR-in-flight rule is meant to prevent, so reaching it
  means something already went wrong upstream. `CLAUDE.md`, **Architecture Decision Records**,
  forbids renumbering outright; applied to a collision, that puts the side already on `main`
  out of reach, so the *unmerged* side is the one that moves. Renumber it by `write-adr`'s
  numbering rule against a freshly fetched `origin/main`, and bring everything that skill keys
  off the number with it — cross-references and the ADL index row in the same commit; the branch
  name only if it has not been pushed, otherwise leave it and say so in the PR.
- **A conflict that is really a stacked branch.** A PR based on `main` while the local branch
  sits on an unmerged prior branch shows the combined stack in its diff; that shrinks by itself
  once the lower branch merges. It is not a conflict to resolve, and never a reason to rewrite
  or re-point the lower branch — the branching rule reached from `CLAUDE.md`, **Contribution
  workflow**, covers this case.

Leave no markers behind: grep the tree for `<<<<<<<`, `=======` and `>>>>>>>` before moving on.

## Step 4 — run the checks

A merge breaks things neither side broke alone. Run the full completion bar for what the merged
tree now touches — the paired lint and format checks, and the suite in the harness matched to
the change — as defined by the doc that `CLAUDE.md`'s **Contribution workflow** section names as
the completion bar; that doc also states which harness covers what, so match the suite to the
merged tree rather than guessing. Do not shortcut to "the tests near my conflict": the ones that
catch a bad resolution are usually elsewhere.

Fix what the merge broke, in the merge, before committing.

## Step 5 — finish

Stage everything, then finish the operation you are in: commit the merge, or `git rebase
--continue` and repeat steps 1-4 for each further commit that conflicts, until the rebase is
done. A merge commit is an exception to the default commit-message shape the completion-bar doc
gives — keep git's generated message, adding one line per hunk where a side had to be dropped,
naming which and why. A rebase has no such commit: put those lines in the report below instead,
since `--continue` reuses the replayed commit's own message.

Then report to the human partner, before resuming the workflow step that sent you here: the
hunks where the two intents were incompatible and what you dropped, plus any behaviour
disagreement escalated in step 3 — that one is an open issue, not a resolved conflict.
