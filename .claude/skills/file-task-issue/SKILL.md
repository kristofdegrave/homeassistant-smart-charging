---
name: file-task-issue
description: Use when creating any GitHub issue in this repo — sets the correct context label, populates the project-board Size/Estimate fields, places it on its milestone where the rule requires one (a child copies its epic's), and (for a child of a decomposition) writes the anchored `Source:` lines correctly the first time. Also holds the mechanics of filing an epic's opening issues, any `decompose` child last, and a decomposition's children.
---

# File a task issue

Filing an issue correctly the first time avoids a wasted implement step later. This skill
is the checklist to run through before running `gh issue create`, not a replacement for
deciding *what* the issue is about.

Context labels, project-board Size/Estimate fields, milestones and epic
membership (native sub-issues and blocked-by edges) are all defined once, and `CLAUDE.md`'s
**Issue conventions** section routes to wherever that is — start there for what each means and
when it applies. *Which* issues a strand gets and in what order — the epic, the issues its
opening pass files, and its children — is owned by the flow `CLAUDE.md`'s **Idea-to-product
flow** topic routes to. The `gh` commands that write them, and the
read-backs that confirm they took, are routed by `CLAUDE.md`'s **Tracker mechanics**
section. This skill adds only the pre-flight order to run through so nothing gets filed
half-scoped.

## The checklist

1. **Is it scoped enough to file yet?** If the work is still fuzzy (spans multiple artifacts,
   unclear boundaries), use the `work-idea` skill instead and give it the `idea` label — don't
   force a premature context label onto something that isn't scoped.
2. **Pick the one context label** (an epic's labels are **Issue conventions**'), set
   Size/Estimate, and — for a child of a decomposition — write the anchored `Source:` lines.
   What each entry's sources name, and how finely, is the closing step's, under `CLAUDE.md`'s
   **Idea-to-product flow**; the line's own format belongs to **Issue conventions** and is not
   stated there yet, so follow the shape the epic body's **Sources** key already uses. **Issue
   conventions** covers the other fields. A finding against already-shipped behaviour also
   takes a **kind label** (`bug`/`enhancement`); which labels that issue ends up with, and
   when, is the two-axis rule in that same section. Size/Estimate are board fields, not
   labels: setting them is its own step after the issue is on the board, per **Tracker
   mechanics** above.
3. **Pick the milestone** — a filing field, set on every issue the milestone rule under
   **Issue conventions** above says carries one, chosen and ranked as that section says and
   never by this skill's own choice. What a milestone is, and how an issue
   routed to work that lacks one is picked, are that section's too; the flag that sets it, the
   call that creates one and the read-back that confirms the name resolved are **Tracker
   mechanics**'.
4. **File it** — setting the milestone and whichever of step 5's edges are already known as
   flags on the create call rather than as a second pass — then move on; implementing it is a
   separate, later step.
5. **If the issue belongs to an epic** — one being decomposed now, or an already-open one a
   later finding fits — attach it as a **native sub-issue** of that epic, and add a
   **blocked-by edge** to each already-filed issue it cannot start before, rather than leaving
   it untracked or its order implied by body text; the epic takes a blocked-by edge to it too,
   per **Issue conventions**. What an issue filed after the opening pass does to the epic's
   `decompose` child, blocking an open one or getting a new one filed, is the flow's opening
   pass's, under **Idea-to-product flow** above. These edges can be set while creating the
   issue or added afterwards; **Tracker mechanics** above routes to the commands and to the
   read-back that confirms each edge exists. Beyond those edges, don't touch the epic's other
   children: their state is a call for whoever owns the epic, not a side effect of filing one
   issue.

## Filing an epic's opening issues

Which issues an epic gets at the flow's opening pass, their order and their edges, a
`decompose` child included or not, are the flow's, per **Idea-to-product flow** above. Filed in
that order, a `decompose` child's blocked-by edges each name an issue that already exists, so
they go on as flags of its create call. Each goes through the
checklist at the top of this file. Done when every edge the flow names for them reads back, and
the epic's blocked-by edge to each of them.

## Filing the children of a decomposition

The closing step's four steps, their order and what the epic body must contain are the flow's,
per **Idea-to-product flow** above — don't re-derive them here. Drafting the body, running its
review pass and parking the epic are the work file of the `decompose` row in `CLAUDE.md`'s
**Model selection**, which reaches this section for the flow's step 4 once the human has said
go. Each child goes through the checklist at the top of this file: its own task text as the
body, its `Source:` lines, the epic's milestone, its native sub-issue edge to the epic, the
epic's blocked-by edge to it, and a blocked-by edge to each child it cannot start before.

Done when every task in the epic body has an issue carrying its label, Size/Estimate, the
epic's milestone, `Source:` lines and edges, the epic's to it included, and no task in that
body is left without one.

## Common mistakes

The conventions are `CLAUDE.md`'s **Issue conventions**, not this list — except the `Source:`
lines, whose owner is item 2 above; the ones this skill's users trip on most are the context
label, the `epic` label, those lines, Size and Estimate, the milestone, and epic edges. The
mistakes that are this skill's own:

- Forcing a context label onto work that is still fuzzy instead of filing it as an `idea`
  (item 1).
- Stopping after the create call — Size/Estimate are a second step (item 2), and an edge not
  passed as a flag is a second step too (item 5); an issue missing them reads as filed and is
  not.
- Filing a child without its epic's milestone (item 3).
- Leaving an epic the flow's opening pass gives a `decompose` child without one, or that child
  short of an edge to an artifact-stage issue the pass filed: the closing step then never
  starts, or starts before what it derives from has merged.
- Filing a decomposition's children before the pass and the human read that the `decompose`
  row of `CLAUDE.md`'s **Model selection** runs. The pass is there to catch what lives between
  tasks, and a task already filed is one it can no longer cheaply change.
