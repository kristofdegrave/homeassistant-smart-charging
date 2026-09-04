# CI pipeline (`.github/workflows/ai-pipeline.yml` + `_ai-*.yml`)

The automated, label-driven equivalent of
[contribution-workflow.md](contribution-workflow.md)'s steps 0–9 — same lifecycle, a different
actor. Commits here are made as `github-actions[bot]`, not the interactive session's own
identity (see that doc's **Git identity** section).

## Labels are CI-only triggers

`needs-draft`, `needs-review`, and `needs-work` exist to invoke these jobs — nothing else. A
**Claude session must never self-apply one on its own initiative** to hand its own review/fix
work to CI instead of doing it in-session; interactive review and fix always happen locally,
per [contribution-workflow.md](contribution-workflow.md) steps 3–6: a fresh `*-reviewer`
subagent posts findings via `submit-pr-review`, then `finalize-pr-review` resolves what got
fixed. This does *not* forbid the pipeline's actual, intended human triggers below — a
maintainer applying `needs-draft` to start the pipeline, or manually re-adding `needs-work`
after the loop cap, is the go-signal these labels exist for. What's disallowed is a session
adding one unprompted as a shortcut, which can also collide with the loop-cap accounting below
(e.g. forcing an extra automated review pass eats into the 2-cycle cap a human never intended
to spend).

## Each job does exactly one task

**Draft** only drafts, **review** only reviews and posts findings, **fix** only addresses
posted findings. No job does more than the one task its trigger label names — a review run
never commits a fix, and a fix run never re-reviews its own output (that's the write/review
separation `workflow-reviewer`'s non-negotiables checklist enforces).

## Pipeline steps

- **Trigger**: a maintainer labels an issue `needs-draft` plus exactly one context label.
  `workflow` is never auto-drafted — no safe path containment exists for untrusted issue
  content outside `docs/**`/`custom_components/**`/`tests/**` — a human authors that draft by
  hand; only its review step is automated.
- **Draft** (`_ai-draft.yml`, ≈ steps 0–2): resolves the skill, model, and branch
  (`<context-label>/<issue-number>`, [contribution-workflow.md](contribution-workflow.md)'s own
  scheme, or a label's own override per its **Branch naming** note) from the label;
  `development`/`testing` additionally require a resolved `Plan:` line. Runs the skill's
  *content* steps only (draft, self-checks) — never its review/commit/report steps, since the
  workflow owns those. Opens the PR with `Closes #<issue-number>` and its own, coarser
  commit-prefix mapping (`_ai-draft.yml`'s `commit_prefix`: `docs` for
  `uc`/`requirement`/`adr`/`specs`, `feat` for `development`, `test` for `testing`) —
  deliberately simpler than the [commit message conventions](definition-of-done.md) table,
  since a single draft commit has no per-UC/per-task number to interpolate yet; that
  granularity is added by later human/CI commits on the branch, which do follow that table.
  Then adds `needs-review`.
- **Review** (`_ai-review.yml`, ≈ steps 3–4): `needs-review` runs the matching `*-reviewer`
  agent and posts findings via `submit-pr-review`'s CI mode, ending in a `clean`/`remarks`
  verdict marker. Unacknowledged human inline comments (no `ai-fix-ack` reply) count as
  remarks too — the CI equivalent of step 8.
- **Fix** (`_ai-fix.yml`, ≈ step 5): a `remarks` verdict adds `needs-work`, which runs
  `address-review-remarks`, commits as `github-actions[bot]` (`docs: address AI review
  remarks (#<pr>)`), and re-adds `needs-review`. It can only commit under `docs/` (its
  commit step is `git add docs`-only) — for a `workflow`-labeled PR, findings outside
  `docs/**` (e.g. in `.github/workflows/`, `.claude/`) still burn a fix cycle but land in the
  PR body as patches for a human to apply, not as a commit.
- **Loop cap**: **2** automatic fix cycles, tighter than the interactive session's 3-round cap
  ([contribution-workflow.md](contribution-workflow.md) step 6) — deliberately, since CI runs
  fully unsupervised with no human watching in real time, unlike an interactive session. A 3rd
  `remarks` verdict goes straight to `needs-approval` with a comment asking a human to re-add
  `needs-work` manually for one more cycle.
- **Clean / cap-out** (≈ step 7): a `clean` verdict or hitting the 2-cycle cap both add
  `needs-approval` — same label, same meaning as the interactive flow: no automated work
  pending, human approval to merge still required.
- **Merge** (step 9, unchanged): always a manual human action regardless of which path
  drafted or reviewed the PR.
