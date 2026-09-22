---
name: file-task-issue
description: Use when creating any GitHub issue in this repo — sets the correct context label, populates the project-board Size/Estimate fields, and (for a child of a decomposition) writes the anchored `Source:` lines correctly the first time. Also holds the mechanics of a decomposition's closing step — running its review pass, and filing its children.
---

# File a task issue

Filing an issue correctly the first time avoids a wasted `needs-draft` cycle later. This skill
is the checklist to run through before running `gh issue create`, not a replacement for
deciding *what* the issue is about.

Context labels, project-board Size/Estimate fields, the anchored `Source:` lines, and epic
membership (native sub-issues and blocked-by edges) are all defined once, and `CLAUDE.md`'s
**Issue conventions** section routes to wherever that is — start there for what each means and
when it applies. *Which* issues a strand gets and in what order — the epic whose body is the
spec, and the children cut from it — is the closing step of the flow `CLAUDE.md`'s
**Idea-to-product flow** topic routes to. The `gh` commands that write them, and the
read-backs that confirm they took, are routed by `CLAUDE.md`'s **Tracker mechanics**
section. This skill adds only the pre-flight order to run through so nothing gets filed
half-scoped.

## The checklist

1. **Is it scoped enough to file yet?** If the work is still fuzzy (spans multiple artifacts,
   unclear boundaries), use the `work-idea` skill instead and give it the `idea` label — don't
   force a premature context label onto something that isn't scoped.
2. **Pick the one context label**, set Size/Estimate, and — for a child of a decomposition —
   write the anchored `Source:` lines, per **Issue conventions** above. A finding against
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

## Filing the children of a decomposition

The closing step's four steps, their order and what the epic body must contain are the flow's,
per **Idea-to-product flow** above — don't re-derive them here. This section holds the mechanics
of the two steps that have any; the checklist the pass applies is `CLAUDE.md`'s **Decomposition
checklist**.

- **Running the pass** (the flow's step 2). Write the body to a scratch file — the `reviewer`
  agent reads files and reaches no tracker — and spawn that agent once, naming the scratch
  file's absolute path and that checklist. Fix what it finds in the epic body itself: there is
  no PR here, so there is no review payload to post and no thread to resolve. Read the body back
  from the tracker afterwards, so the fix is confirmed rather than assumed.
- **Filing the children** (the flow's step 4). Each goes through the checklist at the top of
  this file: its own task text as the body, its `Source:` lines, its native sub-issue edge to
  the epic, and a blocked-by edge to each child it cannot start before.

Done when every task in the epic body has an issue carrying its label, Size/Estimate, `Source:`
lines and edges, and no task in that body is left without one.

## Common mistakes

The conventions are `CLAUDE.md`'s **Issue conventions**, not this list; the ones this skill's
users trip on most are the context label, the `Source:` lines, Size and Estimate, and epic
edges.
What a drafter run does when one of them is wrong is the CI side of `CLAUDE.md`'s
**Contribution workflow**. The mistakes that are this skill's own:

- Forcing a context label onto work that is still fuzzy instead of filing it as an `idea`
  (item 1).
- Stopping after the create call — Size/Estimate are a second step (item 2), and an edge not
  passed as a flag is a second step too (item 4); an issue missing them reads as filed and is
  not.
- Filing a decomposition's children before the agent pass and the human read above. The pass is
  there to catch what lives between tasks, and a task already filed is one it can no longer
  cheaply change.
