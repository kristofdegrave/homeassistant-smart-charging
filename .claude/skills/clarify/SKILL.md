---
name: clarify
description: Use whenever the session needs a decision that belongs to the human partner, or a fact only they hold — merge or grant at an escalation or a hold, an open design choice. In an interactive session it asks; where no human can answer (a headless run, `AskUserQuestion` denied or absent) it parks the question on the issue being worked and ends the run. Never for what the session can look up itself in the code, the docs or via research.
---

# Clarify

How this project puts a decision to the human partner. That every such decision comes here is
the decisions rule under `CLAUDE.md`'s **Contribution workflow**; this skill is the how.

Unless a stage names `brainstorming` (below), the method is `grilling`'s — call the Skill tool
with "grilling" and follow it: the design tree, the frontier, and facts found by the agent
rather than asked. Three deviations win where they differ:

1. **One question per turn**, not the whole frontier in one round. Take one question from the
   frontier, give its context and your recommended answer, and wait for the reply before
   recomputing the frontier and asking the next:

   ```
   **<question title>**

   <context: what is being decided, why it matters now, the options>

   Recommendation: <your recommended answer, and why>
   ```

   A single decision is settled by its reply; `grilling`'s closing confirmation of a shared
   understanding is for a tree of several.
2. **The recommendation is never the human partner's answer.** Only their reply settles a
   question; no reply leaves it open, and a question `grilling`'s no-human fallback defaults is
   recorded open, never settled.
3. **A merge or a grant is never defaulted.** With no human able to answer, that question stays
   open and the session stops there. This overrides `grilling`'s no-human fallback, as **No
   human can answer** below does for every other question.

A skill or stage that names `grilling` for a dialogue with the human partner gets it through
this skill; a user who invokes `grill-me` asked for `grilling` itself, and gets it unwrapped.
Where a stage names `brainstorming` instead — `CLAUDE.md`'s **Idea-to-product flow** does, for
a narrow idea — that skill runs the dialogue, still entered here and still under deviations 2
and 3.

## No human can answer

No human can answer when the run is headless, or when the `AskUserQuestion` tool is absent or
its first call is denied. Then the question is **parked** rather than asked, and the run ends
on the park — the interactive path above is for a session with a human in it. Deviations 2
and 3 hold unchanged: nothing is defaulted, and a merge or a grant is never inferred from
anything but a human's reply.

1. **Compose the question** in deviation 1's shape — title, context with the options,
   recommendation — for the one question at the head of the frontier. One park carries one
   question; the tree resumes from its answer in a later run.
2. **Post it as a comment on the issue being worked** — the issue the run was dispatched for
   — with the marker `<!-- autopilot-parked -->` as the comment's last line. The commands, and
   the read-back that proves the comment landed, are `CLAUDE.md`'s **Tracker mechanics**.
   The question's comment is the one carrying the marker; a comment on that issue newer than
   it is the human's answer, which is what a later run reads and what this one never
   infers. A run with no issue to park on ends with the question in its report instead — it
   invents no home for it.
3. **Apply `needs-decision` to that issue**, per `CLAUDE.md`'s **Tracker mechanics**, and
   read the label set back.
4. **End the run with a report** naming the parked issue, the question's title, and what the
   run leaves undone until it is answered. Done means the comment and the label are both
   read back on the issue and the report names it.

The marker's format is fixed here, beside the session's other markers — the family
`CLAUDE.md`'s **Contribution workflow** names under Rounds and the cap; who reads it, and
how, is the reader's to state.
