---
name: clarify
description: Use in an interactive session whenever the session needs a decision that belongs to the human partner, or a fact only they hold — merge or grant at an escalation or a hold, an open design choice. Never for what the session can look up itself in the code, the docs or via research, and never in a non-interactive run, since it blocks on answers nothing will provide.
---

# Clarify

How this project puts a decision to the human partner. That every such decision comes here is
the decisions rule under `CLAUDE.md`'s **Contribution workflow**; this skill is the how.

The method is `grilling`'s — call the Skill tool with "grilling" and follow it: the design tree,
the frontier, and facts found by the agent rather than asked. Three deviations win where they
differ:

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
   open and the session stops there. This overrides `grilling`'s no-human fallback, which still
   governs every other question.

A skill or stage that names `grilling` for a dialogue with the human partner gets it through
this skill; a user who invokes `grill-me` asked for `grilling` itself, and gets it unwrapped.
Where a stage names `brainstorming` instead — `CLAUDE.md`'s **Idea-to-product flow** does, for
a narrow idea — that skill runs the dialogue, still entered here and still under deviations 2
and 3.
