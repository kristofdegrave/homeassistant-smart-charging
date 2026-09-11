# Type-agnostic lifecycle skills driven by a work-types table — Smart Charging

*Date: 2026-09-11*

## Context

The contribution workflow (`docs/reference/contribution-workflow.md`) is one lifecycle for
every unit of work: issue → worktree → PR → review → fix/reply/resolve → loop → `needs-approval`
→ manual merge. It is deliberately agnostic to the *type* of work. What differs per type is
already captured in two kinds of file:

- **How the work is done** — one skill per artifact type: `write-adr`, `write-use-case`,
  `write-requirement`, `write-impl-spec`, `write-system-design`, `write-project-design`,
  `develop-task`, `write-tests`. Each opens with "follows this project's contribution workflow
  … this skill covers only what's specific" and then gives the type's template, self-check and
  rules.
- **How it is reviewed** — one agent per artifact type: `adr-reviewer`, `analysis-reviewer`,
  `impl-spec-reviewer`, `system-design-reviewer`, `code-reviewer`, `test-reviewer`,
  `workflow-reviewer`. Each is a fresh, read-only Opus reviewer with a type-specific checklist.

CI already treats these as reference files behind a generic runner: `_ai-draft.yml` maps the
issue's context label to a skill and tells the worker to "follow the `<skill>` skill";
`_ai-review.yml` maps changed paths to a reviewer agent and tells the worker to "apply the
checklist in `<agent>.md`"; `_ai-fix.yml` invokes `address-review-remarks`.

Locally there is no such runner. An interactive session has to remember the lifecycle steps,
pick the matching skill and reviewer by hand, drive the review loop, count rounds, and
remember the `needs-approval` step. The mapping from label to files exists only inside CI's
workflow files, where a local session never reads it.

Model: mattpocock/skills `engineering/implement` — a five-line skill that delegates to `/tdd`
and `/code-review` and otherwise says nothing the delegated skills already say. The
`engineering/triage` skill from the same repo was considered as well; its state machine,
`needs-info` round-trips and out-of-scope knowledge base solve a pre-work problem for a
multi-reporter project, which `work-idea` and the project board already cover here. It is not
adopted.

---

## Decision summary

1. **A work-types table in `CLAUDE.md`**, keyed by context label, pointing at the work file and
   the review file for each type, plus the model the work runs on.
2. **Thin, type-agnostic lifecycle skills**, one per step range of the contribution workflow,
   that look the label up in that table and delegate. They cite the workflow doc and the table
   and restate neither.
3. **The per-type files stay exactly what they are**: work files remain skills, review files
   remain agents. No per-type `implement`/`review` skills are created.
4. **The loop (step 6) stays with the human partner.** Each skill ends by naming the next one;
   nothing chains autonomously.
5. **CI keeps its own copies of the mapping for now.** Making CI read the table is a deferred
   follow-up, recorded so the duplication is explicit rather than accidental.

---

## The work-types table

Lives in `CLAUDE.md`. One row per context label. It absorbs the current *Model selection*
section, whose content is already per-type, so `CLAUDE.md` barely grows.

| Context label | How the work is done | How it is reviewed | Model for the work |
|---|---|---|---|
| `adr` | `.claude/skills/write-adr/SKILL.md` | `.claude/agents/adr-reviewer.md` | opus |
| `uc` | `.claude/skills/write-use-case/SKILL.md` | `.claude/agents/analysis-reviewer.md` | opus |
| `requirement` | `.claude/skills/write-requirement/SKILL.md` | `.claude/agents/analysis-reviewer.md` | opus |
| `specs` | `.claude/skills/write-impl-spec/SKILL.md` | `.claude/agents/impl-spec-reviewer.md` | opus |
| `documentation` | `.claude/skills/write-system-design/SKILL.md` or `write-project-design/SKILL.md`, by which file the issue names | `.claude/agents/system-design-reviewer.md` | opus |
| `development` | `.claude/skills/develop-task/SKILL.md` | `.claude/agents/code-reviewer.md` | sonnet |
| `testing` | `.claude/skills/write-tests/SKILL.md` | `.claude/agents/test-reviewer.md` | sonnet |
| `workflow` | `docs/reference/ai-authoring-token-efficiency.md` (human-authored; no drafting skill) | `.claude/agents/workflow-reviewer.md` | opus |

Reviewers always run on Opus regardless of row, per the existing model-selection rule; the
table's model column is for the *work*. A row is meant to be complete on its own: a lifecycle
skill needs nothing outside the row to know what to delegate to.

Once the table exists, the "Step 3's reviewer is X" line in each work skill is a duplicate and
is removed; the table is the single source of that fact, per
`docs/reference/ai-authoring-token-efficiency.md`.

---

## The lifecycle skills

Boundaries follow the workflow doc's own step numbering, which is also the boundary CI draws
between its draft, review and fix workers.

| Steps | Skill | Status | Responsibility |
|---|---|---|---|
| 1–2 | `implement` | new | `/implement #N`. Read the issue; look its context label up in the table; if there is no context label (or the label is `idea`), stop and point at `work-idea` / `file-task-issue`. Create the worktree per the workflow doc, delegate the actual work to the row's work file, run the Definition of Done self-check, push, open the PR against `main` with `Closes #N`, move the board Status. End by naming `review` as the next step. |
| 3–4 | `review` | new | `/review #N` on a PR. Look the linked issue's label up; do the behind-`origin/main` check; spawn the row's reviewer agent fresh (never inline); post findings via `submit-pr-review`. Owns the **round cap**: count prior review passes on the PR by the verdict marker and, at the cap of 3, stop and escalate the disagreement instead of reviewing again. On a clean pass, hand to `finalize-pr-review`; on remarks, name `address-review-remarks` as the next step. |
| 5 | `address-review-remarks` | widened | Already locates findings, applies the severity-based fix policy, acknowledges human comments and posts the per-finding summary. Its "fix with the author's context" section, which today knows only use-cases, ADRs and analysis docs, becomes "apply the work file from the table row", so it covers code, tests, specs and design docs too. Per finding it calls `resolve-review-thread`. |
| 5 (mechanic) | `resolve-review-thread` | new, small | Reply in the finding's thread with what was done or why not, then resolve the thread **only if actually fixed**; disputed or partial threads stay open. Owns the REST reply call, the `ai-fix-ack` marker, the GraphQL resolve mutation and the "outdated is not resolved" rule. Extracted from `finalize-pr-review`. |
| 7 | `finalize-pr-review` | trimmed | Keeps `needs-approval` and the stranded-stack check; points to `resolve-review-thread` for the mechanic it used to carry. |

Step 0 (file the issue) stays with `file-task-issue`. Step 6 (the loop) and steps 8–9 (manual
comments, merge, worktree cleanup) stay with the human partner and the workflow doc.

Who decides whether a finding must be addressed is unchanged: the reviewer agent assigns
severity (step 3); the fix skill applies the policy — every Critical/Major fixed, Minor/Nit
when trivial, disagreements recorded as Skipped (step 5); `finalize-pr-review` refuses
`needs-approval` while a Critical/Major stays open (step 7).

---

## Why reference files, not per-type skills

Per-type `implement-adr`, `implement-uc`, … skills were considered and rejected:

- They would be eight near-identical copies of the lifecycle with one line changed — exactly
  the duplication `ai-authoring-token-efficiency.md` forbids, and they would drift.
- Dispatch by context label is deterministic. Dispatch by skill-description matching is fuzzy,
  and a skill firing on the wrong artifact costs a whole run's context.
- CI would end up with one generic runner per side plus eight local runners to keep aligned.

Converting the work skills into plain `docs/reference/` files was also considered and
rejected: a skill *is* a reference file plus a trigger description, so keeping them as skills
costs nothing, keeps `/write-adr` usable on its own when a draft is wanted without the full
lifecycle, and avoids touching CI's drafter, which names them by skill name.

The review files must stay agents, not checklists: the workflow requires a fresh, separate
reviewer that never runs inline, and only an agent definition carries the tool grant, the
read-only restriction and the `model: opus` pin. The seven agents share a preamble and an
output format; folding that into one generic reviewer agent that reads a per-type checklist
would mirror CI's self-applied prompt more closely and is a possible later cleanup, not part
of this change.

---

## Consequences

- `CLAUDE.md`: gains the work-types table (replacing *Model selection*) and one line in the
  *Contribution workflow* section mapping the step ranges to the four lifecycle skills.
- Each work skill loses its "Step 3's reviewer" line. Their one-line "follows the contribution
  workflow" pointer stays.
- `address-review-remarks` keeps its name — CI's fix worker invokes it by name and CI is out of
  scope — but its scope widens to every type. Because that means a fix pass may now edit
  `custom_components/` and `tests/`, the skill states explicitly that per-type path containment
  in CI continues to come from the workflow's own `add_paths`, not from the skill.
- `finalize-pr-review` shrinks; `resolve-review-thread` is the new home of the reply/resolve
  mechanic.
- **Deferred follow-up**: `_ai-draft.yml`'s label `case` (skill, model, paths, commit prefix)
  and `_ai-review.yml`'s path-to-reviewer mapping are now the second and third copies of what
  the table owns. Making CI read the table, and updating `ci-pipeline.md`'s "every place this
  vocabulary must stay in sync" list, is filed separately and not started until the local
  skills have stabilised.

## Non-goals

- No change to CI behaviour in this strand, other than the deferred follow-up above.
- No autonomous chaining of skills; the stop-and-report rule in the workflow doc is unchanged.
- No second state machine. Readiness and progress remain the project board's Status field plus
  `needs-approval`.
