---
name: finalize-pr-review
description: Use after a review pass on any Smart Charging PR (CI's _ai-review.yml verdict, or a local fresh-agent review via submit-pr-review) comes back clean — resolves the inline threads that were actually fixed, applies needs-approval, moves the linked board issue to "In review", and checks the PR isn't a stranded stacked branch before handing it to the human partner for merge.
---

# Finalize a PR review

A review pass that finds nothing left to fix isn't done until the PR itself reflects that —
otherwise it still looks like it has outstanding remarks, and the human partner has to
re-derive what's actually settled.

## The checklist

1. **Resolve only the threads you actually fixed.** After committing and pushing fixes, walk
   the PR's review threads and resolve each one whose finding was addressed — by default,
   without being asked. Leave open any thread that was deferred, disputed, or only partially
   addressed, and say which and why in a summary comment.
   - GitHub review threads resolve via GraphQL only (no REST endpoint):
     ```
     gh api graphql -f query='query { repository(owner:"kristofdegrave", name:"homeassistant-smart-charging") { pullRequest(number:N) { reviewThreads(first:50){ nodes{ id isResolved comments(first:1){nodes{path line body}} } } } } }'
     ```
     then per thread: `mutation($tid:ID!){ resolveReviewThread(input:{threadId:$tid}){ thread{ id isResolved } } }`.
   - `isOutdated: true` (line moved by a later commit) is **not** the same as resolved —
     resolve explicitly.
2. **Confirm nothing Critical/Major remains unresolved.** If the review (CI verdict or local
   agent) found no remaining Critical/Major findings requiring a fix, this PR is ready for a
   human decision. If something Critical/Major is still open, stop here — don't apply
   `needs-approval` yet.
3. **Apply `needs-approval`**: `gh pr edit <PR> --add-label needs-approval`. This signals "no
   more automated review/fix work is pending, a human must now decide" — it does not replace
   manual merge approval (CODEOWNERS + branch protection still gate the actual merge).
4. **Move the linked issue to "In review"** on the project board — applying `needs-approval`
   to the PR is also the trigger for this board-status move.
5. **Verify the PR isn't a stranded stack** before treating any of the above as final:
   - Confirm the PR's base is `main`, not another `dev/*` branch: `gh pr view <PR> --json baseRefName`.
     If it's based on an unmerged branch, retarget now: `gh pr edit <PR> --base main`.
   - If the base branch already reached `main` via its own squash-merge, this PR's diff may
     be showing stale content — check before resolving/approving further.
   - Don't just trust "merged" status on a related PR; verify the artifact is actually on
     `origin/main` with `git ls-tree origin/main <path>` before relying on it.

## Common mistakes

- Resolving a thread whose finding was only partially fixed, or disputed rather than agreed —
  resolve fixes, not disagreements.
- Applying `needs-approval` while a Critical/Major finding is still open.
- Treating `needs-approval` as itself sufficient to merge — it's a signal for the human
  partner's decision, never a self-approval.
- Leaving a PR based on a `dev/*` branch instead of `main`, which strands the change the
  moment the base branch squash-merges (the commits' SHAs stop existing on `main`).
