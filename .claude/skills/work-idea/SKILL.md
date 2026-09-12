---
name: work-idea
description: Use when picking up a GitHub issue labeled `idea` in the Smart Charging project — brainstorm it interactively until it can be decomposed into one or more properly context-labeled follow-up issues, rather than drafting an artifact directly.
---

# Work an idea

An `idea` issue can be small or very large, and rarely maps 1:1 to a single artifact. This
skill turns it into one or more scoped, context-labeled issues that the labeled pipeline can
then draft — it never drafts an artifact or opens a PR itself.

This is a manual/interactive skill, not a CI-wired one: grilling is a genuine dialogue with a
human, so it stays a session task rather than a non-interactive drafter.

The stages this skill walks — the two tracks, the verification gate, the spec gate, what a
child issue is, and when the idea issue closes — are defined once in the flow document that
`CLAUDE.md`'s **Contribution workflow** section names as covering the stages either side of
the lifecycle. Read that first; this skill only sequences those stages and says which skill
performs each. Cite it, never restate it.

## The cycle

1. **Read the idea issue** — title, body, and anything it links to (docs, related issues). An
   idea raised in conversation gets filed as an `idea` issue first, so there is something to
   record decisions against.
2. **Grill it** — the `grilling` skill owns the technique. Two outputs, two homes: a **decision**
   is written to the idea issue as it settles, and a **question of fact** goes to the `research`
   skill, which records its finding as a comment on the issue that needed it. Stop at "the idea
   is scoped enough to split," not at "the work is designed in detail" — that detail belongs to
   each child issue's own downstream skill.
3. **Route it down one track** — new behaviour, or a defect/improvement against behaviour that
   already ships. The flow document owns the rule and what each track must produce. Write the
   chosen track on the issue, so the next step is not re-argued.
4. **On the shipped-behaviour track, verify the claim before anything is designed** — the
   `diagnosing-bugs` skill performs this step and owns what counts as a reproduction. A claim it
   cannot reproduce is not a defect yet: say so on the issue and stop the cycle there. On the
   new-behaviour track this step does not apply.
5. **Decompose.** A single-artifact idea is one issue filed with `file-task-issue`, and keeps the
   grilled decisions on its own body. A multi-artifact strand gets the epic filed first, with the
   decisions from step 2 moved into its body under a *Decisions so far* heading, then each child
   filed with `file-task-issue`. Children are vertical, demoable slices filed in dependency
   order and attached as **native sub-issues of the epic with blocked-by edges** — never a
   markdown checklist in the epic body; `CLAUDE.md`'s **Tracker mechanics** section routes to the
   `gh` commands. A part still too fuzzy to scope keeps the `idea` label and gets worked later —
   recursion is expected, not an error.
6. **Cross-link** — every child/epic issue body notes "Split from #NNN"; the original idea issue
   gets one comment listing everything it was split into.
7. **Close the idea issue** once it is fully captured — either directly in child issues
   (single-artifact case) or via the new epic (multi-artifact case). Closing it means the idea is
   decomposed, not that the children are *done* — the epic stays open tracking those until they
   all finish. If some part is not covered, say so explicitly in the closing comment instead of
   closing over the gap.
8. **Stop here** — do not draft artifacts, open PRs, or write code in this cycle. That is each
   child issue's own next step, per `CLAUDE.md`'s **Contribution workflow** section.

## Rules

- One context label per child issue — the pipeline's draft job already refuses to draft an issue
  with zero or multiple context labels; don't hand it one. A child on the shipped-behaviour track
  may legitimately carry only its kind label until the fixing artifact is known.
- Don't skip the `grilling` step to save a round-trip — an idea decomposed without the user's
  buy-in just relocates the ambiguity into the child issues.
- Don't draft content for a child issue beyond what's needed to scope it (a clear title and a
  body stating the problem/intent) — the artifact itself is the downstream skill's job.

## Common mistakes

- Closing the parent idea issue when only part of it was decomposed.
- Relabeling/reusing the idea issue itself as the epic instead of filing a new, separate epic
  issue — the epic must stay open tracking children long after the idea issue is closed.
- Leaving grilled decisions in chat scrollback, or leaving them on the idea issue after an epic
  was filed instead of moving them into the epic body.
- Designing a fix on the shipped-behaviour track before the claim has been reproduced.
- Slicing children by layer ("the adapter ticket", "the entity ticket") rather than vertically —
  a layer-shaped child cannot be demoed and cannot be verified live.
- Filing `development`/`testing` child issues before an approved plan exists for them to cite
  in their `Plan:` line.
- Giving a child issue two context labels (e.g. both `uc` and `requirement`) because the
  idea touches both — split it into two children instead.
- Treating this as a green light to start implementing once issues exist — each child still
  needs its own drafting (or manual work) and review cycle.
