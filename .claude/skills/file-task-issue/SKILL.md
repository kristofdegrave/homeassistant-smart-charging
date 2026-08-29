---
name: file-task-issue
description: Use when creating any GitHub issue in this repo — sets the correct context label, populates the project-board Size/Estimate fields, and (for development/testing issues pinned to a plan) writes the anchored `Plan:` line correctly the first time.
---

# File a task issue

Filing an issue correctly the first time avoids a wasted `needs-draft` cycle later. This skill
is the checklist to run through before running `gh issue create`, not a replacement for
deciding *what* the issue is about.

Context labels, project-board Size/Estimate fields, the anchored `Plan:` line, and epic-checklist
membership are all defined once in `CLAUDE.md`'s **Issue conventions** section — read that
first. This skill adds only the pre-flight order to run through so nothing gets filed
half-scoped.

## The checklist

1. **Is it scoped enough to file yet?** If the work is still fuzzy (spans multiple artifacts,
   unclear boundaries), use the `work-idea` skill instead and give it the `idea` label — don't
   force a premature context label onto something that isn't scoped.
2. **Pick the one context label**, set Size/Estimate, and — for `development`/`testing` — write
   the anchored `Plan:` line, per **Issue conventions** above. A code-quality/bug finding
   against already-shipped code (not pinned to a `docs/plans` task) uses `bug`/`enhancement`
   instead of a drafter-facing context label — the pattern the coordinator-cleanup epic (#608)
   and its children use.
3. **File it**, then move on — the drafter/review cycle is a separate, later step.
4. **If the issue belongs to an existing epic** (e.g. a code-review finding that fits an
   already-open cleanup epic), append it to that epic's checklist body
   (`- [ ] #NNN — <short title>`) rather than leaving it untracked. Don't check off boxes for
   *other* items while doing this unless you've verified and been asked to — status ticks are
   a call for whoever owns the epic, not a side effect of filing an unrelated issue.

## Common mistakes

- Two context labels on one issue (e.g. both `uc` and `requirement`) because the work touches
  both — split into two issues instead.
- A `Plan:` line with extra text on it ("Plan: docs/plans/foo.md#T3 (blocked on #120)") — the
  drafter's regex won't resolve it to one task and the run fails.
- Leaving Size/Estimate unset — `_ai-draft.yml` falls back to the M tier and posts a warning
  rather than failing, but that's a safety net, not a substitute.
- Setting Estimate on an epic in addition to Size.
