---
name: grilling
description: Use in an interactive session whenever the session needs a decision from the human partner — a design choice, merge or grant at a review cap or hold, a fact only they can supply — and when the user asks to be "grilled", "grill me", or to stress-test a plan, decision or idea. Requires a human respondent — never self-invoke this in a non-interactive context since it blocks on answers nothing will provide.
---

# Grilling

Interview the user relentlessly until you reach a shared understanding. Map this as a **design
tree**: every decision branches into the decisions that hang off it. A single decision is a tree
of one node, asked the same way.

In an interactive session every decision the session needs from the user comes here, per the
decisions rule under `CLAUDE.md`'s **Contribution workflow**: merge or grant at a review cap or on
a hold, an open design choice, a fact only the user holds.

The **frontier** is every decision whose prerequisites are already settled: the questions you can
ask _now_ without guessing at answers you haven't heard yet. Ask **one frontier question per
turn**, carrying the context the user needs to answer it and your recommended answer. Then wait
for the answer before asking the next.

Format a question like so:

```
**<question title>**

<context: what is being decided, why it matters now, the options — as many paragraphs as it takes>

Recommendation: <your recommended answer, and why>
```

Each answer reshapes the tree: a settled decision pushes the frontier outward and unblocks the
questions that depended on it. Recompute the frontier before every question and take the next
one from it. A question whose answer depends on another still open is not on the frontier yet.

Finding _facts_ is your job, never the user's. When a frontier question needs a fact, dispatch a
subagent (in parallel, if several are independent) to find it: from inside the working directory
(filesystem, tools, prior docs) by exploring it, or from outside it (how Home Assistant behaves,
what a library does, what a device API returns) via the `research` skill. Don't ask the user for
anything you could look up yourself; a fact only the user holds is a frontier question like any
decision. Don't block on a lookup: it is an unsettled prerequisite, so only the questions
downstream of it wait for the subagent to report; keep asking from the rest of the frontier. The
_decisions_ are the user's: put each to them and wait.

The session is done when the frontier is empty: every branch of the design tree visited, nothing
left silently assumed. Do not act on a tree of several decisions until the user confirms you
have reached a shared understanding; a single decision is settled by its answer.

Where the skill or stage that sent you here picks the built-in `brainstorming` skill for the
dialogue at hand instead — `CLAUDE.md`'s **Idea-to-product flow** does, for a narrow idea — use
that one.

This is interactive-only: if you find yourself invoked with no human able to answer, do not
block — make the recommended answer the default for every open question, record them as open
questions in your output, and proceed.
