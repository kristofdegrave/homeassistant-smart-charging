---
name: finalize-pr-review
description: Use after a review pass on any Smart Charging PR (CI's _ai-review.yml verdict, or a local fresh-agent review via submit-pr-review) comes back clean — confirms nothing Critical/Major remains, applies needs-approval, and checks the PR isn't a stranded stacked branch before handing it to the human partner for merge.
---

# Finalize a PR review

A review pass that finds nothing left to fix isn't done until the PR itself reflects that —
otherwise it still looks like it has outstanding remarks, and the human partner has to
re-derive what's actually settled.

Threads are closed out per finding during step 5, by `resolve-review-thread` — this skill
does not repeat that mechanic. If a thread is still open for a finding that was fixed, run
that skill before this one.

## The checklist

1. **Confirm nothing Critical/Major remains unresolved.** If the review (CI verdict or local
   agent) found no remaining Critical/Major findings requiring a fix, this PR is ready for a
   human decision. If something Critical/Major is still open, stop here — don't apply
   `needs-approval` yet.
2. **Apply `needs-approval`**: `gh pr edit <PR> --add-label needs-approval`. This signals "no
   more automated review/fix work is pending, a human must now decide" — it does not replace
   manual merge approval (CODEOWNERS + branch protection still gate the actual merge). The
   linked issue's board Status should already be "In review" (moved when the PR was opened);
   this step doesn't move it further.
3. **Verify the PR isn't a stranded stack** before treating any of the above as final:
   - Confirm the PR's base is `main`, not another work branch:
     `gh pr view <PR> --json baseRefName`. If it's based on an unmerged branch, retarget now:
     `gh pr edit <PR> --base main`.
   - If the base branch already reached `main` via its own squash-merge, this PR's diff may
     be showing stale content — check before approving further.
   - Don't just trust "merged" status on a related PR; verify the artifact is actually on
     `origin/main` with `git ls-tree origin/main <path>` before relying on it.

## Common mistakes

- Applying `needs-approval` while a Critical/Major finding is still open.
- Treating `needs-approval` as itself sufficient to merge — it's a signal for the human
  partner's decision, never a self-approval.
- Leaving a PR based on another work branch instead of `main`, which strands the change
  the moment the base branch squash-merges (the commits' SHAs stop existing on `main`).
