---
name: file-task-issue
description: Use when creating any GitHub issue in this repo — sets the correct context label, populates the project-board Size/Estimate fields, and (for development/testing issues pinned to a plan) writes the anchored `Plan:` line correctly the first time.
---

# File a task issue

Filing an issue correctly the first time avoids a wasted `needs-draft` cycle later. This skill
is the checklist to run through before running `gh issue create`, not a replacement for
deciding *what* the issue is about.

## The checklist

1. **Is it scoped enough to file yet?** If the work is still fuzzy (spans multiple artifacts,
   unclear boundaries), use the `work-idea` skill instead and give it the `idea` label — don't
   force a premature context label onto something that isn't scoped.
2. **Exactly one context label**, matching the artifact type:
   - `uc` — use-case
   - `requirement` — requirement / constraint / glossary change
   - `adr` — Architecture Decision Record
   - `specs` — implementation spec (design + TDD plan)
   - `development` — implementation task (code + tests), pinned to a plan
   - `testing` — test-authoring task, pinned to a plan
   - `workflow` — CI/skill/agent-authoring change (review only, no auto-drafter)
   - `documentation` — design-doc change (`docs/design/**`); not yet wired into the CI
     drafter's label set

   Context labels are safe to add freely — they don't trigger CI. Only an *action* label
   (`needs-draft`, `needs-review`, `needs-work`) fires a job, and that's a separate, later step.

   A code-quality/bug finding against already-shipped code (not pinned to a `docs/plans` task)
   uses `bug` or `enhancement` instead — this is the pattern the existing coordinator-cleanup
   epic (#608) and its children use, not the drafter-facing context labels above.
3. **For `development`/`testing` issues**: include the exact-form anchored line in the body:
   ```
   Plan: docs/plans/<file>.md#T<task-number>
   ```
   Nothing else on that line — no backticks, no trailing `(PR #NNN)`, no surrounding sentence.
   `.github/workflows/_ai-draft.yml` parses this line as its sole containment mechanism for
   untrusted issue-body text; get it right when filing, not after a failed drafter run.
4. **Set the project-board fields** (EMS project board, `kristofdegrave/projects/1`):
   - **Size** (XS/S/M/L/XL) — always.
   - **Estimate** (numeric points) — always, *except* epics (issues that group child issues
     via a checklist body), which get Size only. An epic's cost is the sum of its children's
     estimates; setting Estimate on it double-counts effort already on the children.
   - For a `development`/`testing` issue shaped like an audit or sweep (verify invariants
     across multiple files, run the full suite, cross-check an ADR — not just one unit's
     test+impl), size it up at least one tier from what raw effort suggests — the CI drafter
     reads without Bash access and a "small" human task can still be read-heavy for it.
5. **File it**, then move on — the drafter/review cycle is a separate, later step.
6. **If the issue belongs to an existing epic** (e.g. a code-review finding that fits an
   already-open cleanup epic), append it to that epic's checklist body
   (`- [ ] #NNN — <short title>`) rather than leaving it untracked. Don't check off boxes for
   *other* items while doing this unless you've verified and been asked to — status ticks are
   a call for whoever owns the epic, not a side effect of filing an unrelated issue.

## Common mistakes

- Two context labels on one issue (e.g. both `uc` and `requirement`) because the work touches
  both — split into two issues instead.
- A `Plan:` line with extra text on it ("Plan: docs/plans/foo.md#T3 (blocked on #120)") — the
  drafter's regex won't resolve it to one task and the run fails.
- Leaving Size/Estimate unset — `_ai-draft.yml` falls back to the M tier and posts a warning
  rather than failing, but that's a safety net, not a substitute.
- Setting Estimate on an epic in addition to Size.
