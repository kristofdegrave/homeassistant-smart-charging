---
name: work-idea
description: Use when picking up a GitHub issue labeled `idea` in the Smart Charging project — brainstorm it interactively until it can be decomposed into one or more properly context-labeled follow-up issues, rather than drafting an artifact directly.
---

# Work an idea

An `idea` issue can be small or very large, and rarely maps 1:1 to a single artifact. This
skill turns it into one or more scoped, context-labeled issues that the labeled pipeline
(`ai-pipeline.yml`) can then draft — it never drafts an artifact or opens a PR itself.

This is a manual/interactive skill, not a CI-wired one: brainstorming is a genuine dialogue,
so it stays a session task for now rather than a non-interactive drafter.

The single-vs-multi-artifact filing decision, epic mechanics, and deferral rules are defined
once in `docs/reference/idea-to-issues.md` — read that first. This skill adds only the
brainstorming gate that has to happen before any of that filing.

## The cycle

1. **Read the idea issue** — title, body, and anything it links to (docs, related issues).
2. **Brainstorm it** — follow the `brainstorming` skill's dialogue style: one question at a
   time, propose 2-3 approaches with a recommendation, get explicit buy-in on the resulting
   shape before decomposing. Stop at "the idea is scoped enough to split," not at "the work
   is designed in detail" — that detail belongs to each child issue's own downstream skill
   (`write-use-case`, `write-adr`, `write-requirement`, `write-impl-spec`, `develop-task`,
   `write-tests`, or whatever `workflow` resolves to).
3. **Decompose**, following the `docs/reference/idea-to-issues.md` cycle (single-artifact vs.
   multi-artifact epic filing, what to file now vs. defer). A part that's
   still too fuzzy to scope keeps the `idea` label itself and gets worked later — recursion is
   expected, not an error.
4. **Cross-link** — every child/epic issue body notes "Split from #NNN"; the original idea
   issue gets one comment listing everything it was split into.
5. **Close the idea issue** once it's fully captured — either directly in child issues (single-
   artifact case) or via the new epic (multi-artifact case). Closing the idea issue is about
   the idea being decomposed, not about the resulting epic's children being *done* — the epic
   itself stays open tracking those until they all finish. If some part isn't covered yet, say
   so explicitly in the closing/summary comment instead of closing over the gap.
6. **Stop here** — do not draft artifacts, open PRs, or write code in this cycle. That is each
   child issue's own next step, per CLAUDE.md's issue-first workflow.

## Rules

- One context label per child issue — the pipeline's draft job (`_ai-draft.yml`) already
  refuses to draft an issue with zero or multiple context labels; don't hand it one.
- Don't skip the brainstorming dialogue to save a round-trip — an idea decomposed without
  the user's buy-in just relocates the ambiguity into the child issues.
- Don't draft content for a child issue beyond what's needed to scope it (a clear title and a
  body stating the problem/intent) — the artifact itself is the downstream skill's job.

## Common mistakes

- Closing the parent idea issue when only part of it was decomposed.
- Relabeling/reusing the idea issue itself as the epic instead of filing a new, separate epic
  issue — the epic must stay open tracking children long after the idea issue is closed.
- Filing `development`/`testing` child issues before an approved plan exists for them to cite
  in their `Plan:` line.
- Giving a child issue two context labels (e.g. both `uc` and `requirement`) because the
  idea touches both — split it into two children instead.
- Treating this as a green light to start implementing once issues exist — each child still
  needs its own `needs-draft` cycle (or manual work) and review, per CLAUDE.md.
