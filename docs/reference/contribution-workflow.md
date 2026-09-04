# Contribution workflow

Universal lifecycle for **every** unit of work in this repo — a doc, an ADR, a design, or
code. Artifact-specific sections in `CLAUDE.md` (analysis docs, ADRs) layer their own
template/quality-check steps on top of this; they never replace it.

Two related references cover the phases just outside this lifecycle: what happens *before* an
issue exists ([idea-to-issues.md](idea-to-issues.md), epic decomposition) and the completion
bar an author checks *before* step 2 below ([definition-of-done.md](definition-of-done.md),
also covering commit message conventions).

0. **Open a GitHub issue first.** Every task gets an issue before work starts — no exception
   for small or typo-level changes. Correct context label + Size/Estimate fields (see
   **Issue conventions** below). Board **Status** defaults to `Backlog`.
1. **Do the work in an isolated `git worktree`, always.** No exceptions, even a one-line fix —
   removes the shared-checkout risk of a concurrent session switching branches underneath you.
   Branch name: `<context-label>/<issue-number>` (see **Issue conventions** below for the
   full scheme, including the multi-PR suffix). Create the worktree from an up-to-date `main`
   — `git fetch origin && git worktree add -b <branch> <path> origin/main` (not a stale local
   `main`) — so the new branch starts from the latest merged work rather than whatever `main`
   happened to be at the last fetch; the one exception is deliberately stacking on a
   not-yet-merged prior task's branch per step 2, in which case fetch first and branch off that
   instead. As soon as you actually start
   writing/developing (not at issue-filing time), move the issue's board **Status** to
   `In progress`. Work can be interactive, with intermediate commits. Before step 2, self-check
   against the [Definition of Done](definition-of-done.md).
2. **Push and open a PR against `main`.** Always base `main` directly — never another
   `<context-label>/*` branch, even if logically stacked on a not-yet-merged prior task
   (squash merges orphan stacked branches). Branching off a prior task's branch locally is
   fine; the PR itself is `--base main` from the start. GitHub's diff for a dependent PR
   temporarily shows the combined stack until the branch below merges — expected, shrinks
   automatically. PR description references the linked issue with `Closes #<issue-number>` so
   merging auto-closes it; if the issue needs more than one PR, use `Part of #<issue-number>`
   on every PR except the one that finishes the issue. Move the issue's board **Status** to
   `In review`.
3. **Review.** Fresh, separate reviewer agent for the artifact type, always **Opus** (per
   CLAUDE.md's model-selection rule) — never inline in the main session. Before this, and
   before every later pass in the loop: check if the
   branch is behind `origin/main`; if so, merge/rebase `origin/main` in and resolve conflicts
   before reviewing, so review always runs against current `main`.
4. **Post findings to the PR before fixing.** Native GitHub PR review with inline comments
   (`submit-pr-review`, local mode) — never skip straight to "fixed it, see PR body." Applies
   once the PR exists, which step 2 guarantees is always before review.
5. **Fix, comment, resolve.** Per finding addressed: fix it, reply on that thread describing
   what was done, then resolve the thread (`finalize-pr-review` has the GraphQL mechanic — no
   REST endpoint exists for this). Resolve only what was actually fixed; leave
   deferred/disputed/partial threads open and say why.
6. **Loop steps 3–5**, capped at **3 rounds**, until a pass finds no remaining Critical/Major
   findings. Still unresolved at round 3 → stop and escalate to the human partner with the
   disagreement instead of continuing; that usually needs a judgment call the loop can't make.
7. **Label `needs-approval`** once a review pass (CI or local) comes back clean. Board
   **Status** stays `In review` — this only signals no automated review/fix work is pending,
   it doesn't replace manual merge approval.
8. **Manual PR comments**, at any point, are handled like step 5: fix, reply, resolve. Don't
   close the linked issue directly (`gh issue close`) even on a fully clean verification-only
   task — closing is left to the `Closes #N` reference from step 2, which fires on merge.
9. **Merge is always manual** (`CODEOWNERS` + branch protection) — never auto-merged or
   self-approved, including by CI-drafted PRs. Merging auto-closes the linked issue via step
   2's `Closes #N` reference (or leaves it open if the PR only used `Part of #N`) — move its
   board **Status** to `Done` once that happens. Once merged: verify the change landed on
   `origin/main` (`git ls-tree origin/main <path>`), then remove the task's worktree
   (`git worktree remove <path>`) right away if clean — don't wait for a bulk sweep.

**Stop and report, interactive session only.** After each artifact/task is committed (step 1
onward), report status and wait for the human partner before starting the next one — this is a
control on autonomous artifact-chaining, not boilerplate: don't draft/commit a second document
or task off the back of one that just landed without a check-in. Doesn't apply to the CI flow
below, which runs its labeled steps to completion by design.

## Commit & push authorization

Commit and push freely, at any point during the work — no per-commit or per-push approval
needed. This is a standing authorization the project makes in this document; it does not
extend to anything destructive or hard to reverse (force-push, rewriting published history,
`git reset --hard`, etc.), which still follow the general ask-before-acting default.

## Project board

Status field on the EMS project board (`gh project view 1 --owner kristofdegrave`) has 5
options: `Backlog`, `Ready`, `In progress`, `In review`, `Done`. `Ready` is unused today (not
part of this workflow) — steps above only move Backlog → In progress → In review → Done. If
`Ready` gets a defined meaning later (e.g. dependencies/contract resolved and pickable),
insert it explicitly into step 0/1 here rather than leaving it implicit.

## Parallel work and forward dependencies

Multiple tasks can proceed in parallel. When one task needs something a not-yet-built task
will produce (an entity, an event, a function signature), don't block and don't
invent/implement the missing piece. Pin down the **contract** instead — exact name/id, value
semantics/unit, a shared constant both sides code against — in the relevant
spec/`const.py`/ADR, and mark the producing side as a dependency for its own later task. The
producing task implements the real thing; the consuming task only adds the signature and
tests against a simulated/stubbed instance of the contract — never a private reimplementation
of the producer's logic.

## Git identity

Claude commits, comments, and opens PRs as the developer's own GitHub account — there is no
separate bot account for the interactive session. This applies to the interactive session
only — the CI flow below commits as `github-actions[bot]`, a separate, unrelated identity.

## Issue conventions

- **Context label** matches the artifact type: `adr`, `uc`, `requirement`, `specs`
  (implementation spec: design + TDD plan, `docs/plans/**`), `development`/`testing`
  (implementation tasks against an approved plan), `workflow` (CI/skill/agent-authoring
  changes — see CI flow below, never auto-drafted), `documentation` (design-doc changes,
  `docs/design/**` — review only, not yet wired into the CI drafter's label set). A context
  label alone never triggers CI — only an *action* label (`needs-draft` on an issue;
  `needs-review`/`needs-work` on a PR) spawns an AI job.

  This vocabulary is listed in five places that must all move together: this doc,
  `ai-pipeline.yml`'s header comment, `_ai-draft.yml`'s `context_labels` variable/case block,
  `.github/setup-labels.sh`'s label definitions, and each `.github/ISSUE_TEMPLATE/*.yml`'s
  `labels:` key (`adr.yml` → `adr`, `requirement.yml` → `requirement`, `use-case.yml` → `uc`),
  which stamps that label on every issue filed through the form. Adding or renaming a label
  means updating all five, not just one — `file-task-issue/SKILL.md` only points here, it
  doesn't hold its own copy.
- **Project-board fields**: always set **Size** (XS/S/M/L/XL) and **Estimate** (points) — they
  drive `_ai-draft.yml`'s `max_turns` tier, not labels. Size a sweep/audit-shaped task
  (cross-file invariant check, full-suite run, cross-check an ADR) up at least one tier from
  raw effort — it's read-heavy for the CI drafter even when small for a human. **Epics get
  Size only, never Estimate** — an epic's cost is the sum of its children's estimates.
- **Epic-first for multi-artifact strands**: see [idea-to-issues.md](idea-to-issues.md) for
  the full cycle (when to file the epic, what to file immediately vs. defer). Child issues use
  "Part of #N" for the epic, never "Closes #N" (would auto-close the epic).
- **Task issues** (`development`/`testing` label) filed against an approved
  `docs/plans/<slice>.md` TDD plan must include this exact anchored line:

  ```text
  Plan: docs/plans/<file>.md#T<task-number>
  ```

  Parsed by `.github/workflows/_ai-draft.yml` as the sole containment mechanism letting the
  automated drafter act on untrusted issue-body text — the line must be anchored (nothing
  else on it: no backticks, no trailing `(PR #NNN)`, no surrounding sentence) so it resolves
  to exactly one plan file and task id. `<task-number>` matches the plan's own numbering
  (`T3.1`, `T5`). Everything else — rationale, blockers, PR back-refs — goes in surrounding
  prose. Get it right at filing time; retrofitting after a failed `needs-draft` run wastes a
  cycle.

**Branch naming**: `<context-label>/<issue-number>` — label is the issue's context label
(`adr`, `uc`, `requirement`, `specs`, `development`, `testing`, `workflow`, `documentation`),
number is the GitHub issue number. If extra work on the same issue needs a second, separate
PR, suffix a third segment describing the split: `<context-label>/<issue-number>/<slug>`
(e.g. `development/142/followup`).

A context label's own skill may override the number segment when there's a concrete reason
to key the branch off the artifact's own identity instead of the issue's — state the
exception and its reason in that skill, don't leave it implicit here.

## CI flow (`.github/workflows/_ai-*.yml`)

The automated, label-driven equivalent of steps 0–9 above — same lifecycle, different actor.
Commits here are made as `github-actions[bot]`, not the interactive session's own identity.

- **Trigger**: a maintainer labels an issue `needs-draft` plus exactly one context label.
  `workflow` is never auto-drafted — no safe path containment exists for untrusted issue
  content outside `docs/**`/`custom_components/**`/`tests/**` — a human authors that draft by
  hand; only its review step is automated.
- **Draft** (`_ai-draft.yml`, ≈ steps 0–2): resolves the skill, model, and branch
  (`<context-label>/<issue-number>`, this doc's own scheme, or a label's own override per
  the **Branch naming** note above) from the label; `development`/`testing` additionally
  require a resolved `Plan:` line. Runs the skill's *content* steps only
  (draft, self-checks) — never its review/commit/report steps, since the workflow owns those.
  Opens the PR with `Closes #<issue-number>` and its own, coarser commit-prefix mapping
  (`_ai-draft.yml`'s `commit_prefix`: `docs` for `uc`/`requirement`/`adr`/`specs`, `feat` for
  `development`, `test` for `testing`) — deliberately simpler than the
  [commit message conventions](definition-of-done.md) table, since a single draft commit has
  no per-UC/per-task number to interpolate yet; that granularity is added by later human/CI
  commits on the branch, which do follow that table. Then adds `needs-review`.
- **Review** (`_ai-review.yml`, ≈ steps 3–4): `needs-review` runs the matching `*-reviewer`
  agent and posts findings via `submit-pr-review`'s CI mode, ending in a `clean`/`remarks`
  verdict marker. Unacknowledged human inline comments (no `ai-fix-ack` reply) count as
  remarks too — the CI equivalent of step 8.
- **Fix** (`_ai-fix.yml`, ≈ step 5): a `remarks` verdict adds `needs-work`, which runs
  `address-review-remarks`, commits as `github-actions[bot]` (`docs: address AI review
  remarks (#<pr>)`), and re-adds `needs-review`.
- **Loop cap**: **2** automatic fix cycles, tighter than the interactive session's 3-round cap
  (step 6) — deliberately, since CI runs fully unsupervised with no human watching in real
  time, unlike an interactive session. A 3rd `remarks` verdict goes straight to
  `needs-approval` with a comment asking a human to re-add `needs-work` manually for one more
  cycle.
- **Clean / cap-out** (≈ step 7): a `clean` verdict or hitting the 2-cycle cap both add
  `needs-approval` — same label, same meaning as the interactive flow: no automated work
  pending, human approval to merge still required.
- **Merge** (step 9, unchanged): always a manual human action regardless of which path
  drafted or reviewed the PR.
