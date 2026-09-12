---
name: file-task-issue
description: Use when creating any GitHub issue in this repo — sets the correct context label, populates the project-board Size/Estimate fields, and (for development/testing issues pinned to a plan) writes the anchored `Plan:` line correctly the first time.
---

# File a task issue

Filing an issue correctly the first time avoids a wasted `needs-draft` cycle later. This skill
is the checklist to run through before running `gh issue create`, not a replacement for
deciding *what* the issue is about.

Context labels, project-board Size/Estimate fields, the anchored `Plan:` line, and epic
membership (native sub-issues) are all defined once, and `CLAUDE.md`'s **Issue conventions**
section routes to wherever that is — start there. This skill adds only the pre-flight order to
run through so nothing gets filed half-scoped.

## The checklist

1. **Is it scoped enough to file yet?** If the work is still fuzzy (spans multiple artifacts,
   unclear boundaries), use the `work-idea` skill instead and give it the `idea` label — don't
   force a premature context label onto something that isn't scoped.
2. **Pick the one context label**, set Size/Estimate, and — for `development`/`testing` — write
   the anchored `Plan:` line, per **Issue conventions** above. A finding against
   already-shipped behaviour also takes a **kind label** (`bug`/`enhancement`); which labels
   that issue ends up with, and when, is the two-axis rule in that same section.
3. **File it**, then move on — the drafter/review cycle is a separate, later step.
4. **If the issue belongs to an existing epic** (e.g. a code-review finding that fits an
   already-open cleanup epic), attach it as a **native sub-issue** of that epic rather than
   leaving it untracked — `gh` commands in **Issue conventions** above. Don't touch the
   epic's other children while doing this: their state is a call for whoever owns the epic,
   not a side effect of filing an unrelated issue.

## Common mistakes

- Two context labels on one issue (e.g. both `uc` and `requirement`) because the work touches
  both — split into two issues instead.
- A `Plan:` line with extra text on it ("Plan: docs/plans/foo.md#T3 (blocked on #120)") — the
  drafter's regex won't resolve it to one task and the run fails.
- Leaving Size/Estimate unset — `_ai-draft.yml` falls back to the M tier and posts a warning
  rather than failing, but that's a safety net, not a substitute.
- Setting Estimate on an epic in addition to Size.
