---
name: grilling
description: Use when the user, in an interactive session, explicitly asks to be "grilled" or "grill me" on a plan, decision, or idea, or asks to stress-test their thinking on one. Requires a human respondent — never self-invoke this in a non-interactive context (e.g. a CI drafter/reviewer run) since it blocks on answers nothing will provide.
---

# Grilling

Interview the user relentlessly until you reach a shared understanding. Map this as a **design
tree**: every decision branches into the decisions that hang off it.

Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are already
settled: the questions you can ask _now_ without guessing at answers you haven't heard yet. Ask
the whole frontier in one round: number each question and give your recommended answer. Then
wait for the user's answers before the next round.

Format a round like so:

```
**Q1** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

Recommendation: <your recommended answer>

---

**Q2** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

Recommendation: <your recommended answer>
```

Each round the user answers reshapes the tree: settled decisions push the frontier outward and
unblock questions that depended on them. Recompute the frontier and ask the next round. A
question whose answer depends on another question still open in this round belongs to a _later_
round, not this one.

Finding _facts_ is your job, never the user's. When a frontier question needs a fact, dispatch a
subagent (in parallel, if several are independent) to find it: from inside the working directory
(filesystem, tools, prior docs) by exploring it, or from outside it (how Home Assistant behaves,
what a library does, what a device API returns) via the `research` skill. Don't ask the user for
anything you could look up yourself. Don't block on it: a running exploration is an unsettled
prerequisite, so only the questions downstream of it wait for the subagent to report; ask the rest
of the frontier now. The _decisions_ are the user's: put each to them and wait.

The session is done when the frontier is empty: every branch of the design tree visited, nothing
left silently assumed. Do not act on it until the user confirms you have reached a shared
understanding.

This technique targets large, branch-heavy decisions — e.g. `work-idea`'s brainstorming gate.
For a single, narrowly-scoped question, the built-in `brainstorming` skill's one-question dialogue
(used, for example, by `write-impl-spec`'s own scoping step) is a lighter fit; use whichever the
referencing skill names.

This is interactive-only: if you find yourself invoked with no human able to answer (e.g. inside
a non-interactive CI run), do not block — make the recommended answer the default for every open
question, record them as open questions in your output, and proceed.
