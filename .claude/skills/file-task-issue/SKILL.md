---
name: file-task-issue
description: Use when creating any GitHub issue in this repo — sets the correct context label, populates the project-board Size/Estimate fields, and (for development/testing issues pinned to a plan) writes the anchored `Plan:` line correctly the first time.
---

# File a task issue

Filing an issue correctly the first time avoids a wasted `needs-draft` cycle later. This skill
is the checklist to run through before running `gh issue create`, not a replacement for
deciding *what* the issue is about.

Context labels, project-board Size/Estimate fields, the anchored `Plan:` line, and epic
membership (native sub-issues and blocked-by edges) are all defined once, and `CLAUDE.md`'s
**Issue conventions** section routes to wherever that is — start there for what each means and
when it applies. The `gh` commands that write them, and the read-backs that confirm they took,
are routed by `CLAUDE.md`'s **Tracker mechanics** section. This skill adds only the pre-flight
order to run through so nothing gets filed half-scoped.

## The checklist

1. **Is it scoped enough to file yet?** If the work is still fuzzy (spans multiple artifacts,
   unclear boundaries), use the `work-idea` skill instead and give it the `idea` label — don't
   force a premature context label onto something that isn't scoped.
2. **Pick the one context label**, set Size/Estimate, and — for `development`/`testing` — write
   the anchored `Plan:` line, per **Issue conventions** above. A finding against
   already-shipped behaviour also takes a **kind label** (`bug`/`enhancement`); which labels
   that issue ends up with, and when, is the two-axis rule in that same section. Size/Estimate
   are board fields, not labels: setting them is its own step after the issue is on the board,
   per **Tracker mechanics** above.
3. **File it** — setting whichever of step 4's edges are already known as flags on the create
   call rather than as a second pass — then move on; the drafter/review cycle is a separate,
   later step.
4. **If the issue belongs to an epic** — one being decomposed now, or an already-open one a
   later finding fits — attach it as a **native sub-issue** of that epic, and add a
   **blocked-by edge** to each already-filed issue it cannot start before, rather than leaving
   it untracked or its order implied by body text. Both edges can be set while creating the
   issue or added afterwards; **Tracker mechanics** above routes to the commands and to the
   read-back that confirms each edge exists. Don't touch the epic's other children while doing
   this: their state is a call for whoever owns the epic, not a side effect of filing one issue.

## Common mistakes

- Two context labels on one issue (e.g. both `uc` and `requirement`) because the work touches
  both — split into two issues instead.
- A `Plan:` line with extra text on it ("Plan: docs/plans/foo.md#T3 (blocked on #120)") — the
  drafter's regex won't resolve it to one task and the run fails.
- Leaving Size/Estimate unset — `_ai-draft.yml` falls back to the M tier and posts a warning
  rather than failing, but that's a safety net, not a substitute.
- Setting Estimate on an epic in addition to Size.
- Recording epic membership or ordering as body text — a checklist line, or "after #NNN" in
  prose — instead of the native sub-issue and blocked-by edges.
