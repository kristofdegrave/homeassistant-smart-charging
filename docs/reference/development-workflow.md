# Development workflow

Universal lifecycle for **every** unit of work in this repo — a doc, an ADR, a design, or
code. Artifact-specific sections in `CLAUDE.md` (analysis docs, ADRs) layer their own
template/quality-check steps on top of this; they never replace it.

0. **Open a GitHub issue first.** Every task gets an issue before work starts — no exception
   for small or typo-level changes. Correct context label + Size/Estimate fields (see
   **Issue conventions** below). Board **Status** defaults to `Backlog`.
1. **Do the work in an isolated `git worktree`, always.** No exceptions, even a one-line fix —
   removes the shared-checkout risk of a concurrent session switching branches underneath you.
   Branch name: `<context-label>/<issue-number>` (see **Issue conventions** below for the
   full scheme, including the multi-PR suffix). As soon as you actually start
   writing/developing (not at issue-filing time), move the issue's board **Status** to
   `In progress`. Work can be interactive, with intermediate commits. Before step 2, self-check
   against the **Definition of Done** below.
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
   branch is behind `main`; if so, merge/rebase `main` in and resolve conflicts before
   reviewing, so review always runs against current `main`.
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

## Definition of Done (self-check before step 2)

Before pushing and opening the PR, self-check against a baseline Definition of Done — this is
the author's own review, distinct from step 3's fresh external reviewer:

- **Scope**: built what the issue actually asked, no more and no less (see the forward-
  dependency contract-first rule below for anything intentionally deferred to a later task).
- **Builds/lints clean**: no syntax errors; linter passes (`ruff check .` and `ruff format
  --check .` for `custom_components/`/`tests/` changes — pair both, not just the first).
- **Tests green**: the relevant suite passes, in the harness matched to what changed
  (ADR-0009: plain pytest for pure logic, HA harness for adapters/coordinator/entities/config
  flow).
- **Test coverage matches the change**: new behavior has a new test that proves it, not just
  reliance on existing tests happening to still pass; edge cases the issue implies are
  covered, not only the happy path.
- **Runtime-verified, not just test-verified**, for anything with observable runtime
  behavior — drive it, don't claim it works on unit tests alone.

Doc/ADR/design artifacts satisfy this with their own self-check instead (6Cs pass, template
conformance, cross-document consistency) — each artifact's own skill defines what "done"
means there (`write-adr`, `write-requirement`, `write-use-case`, `write-impl-spec`,
`write-system-design`, `write-project-design`; the analysis-doc and ADR versions are also
mirrored in `CLAUDE.md`'s artifact-specific sections). The checklist above is the floor for
anything touching `custom_components/`/`tests/`.

## Commit & push authorization

Commit and push freely, at any point during the work — no per-commit or per-push approval
needed. This is a standing authorization the project makes in this document; it does not
extend to anything destructive or hard to reverse (force-push, rewriting published history,
`git reset --hard`, etc.), which still follow the general ask-before-acting default.

## Commit message conventions

The human partner's own choice of message always wins; the shape below is only the
**default** when nothing more specific is asked for, so a skill doesn't need to invent one.
Default shape is `<prefix>: <description>`, with `<prefix>` inferred from context label,
matching current practice (`git log`):

| Context label | Default prefix | Example |
|---|---|---|
| `adr` | `docs:` (mention `ADR-NNNN` in the description) | `docs: add ADR-0029 process-time for perf-test CPU measurement` |
| `uc` | `UC<NN>:` | `UC12: rewrite the Requirements-satisfied section to match current R20/R18` |
| `requirement` | `docs:` | `docs: correct ADR-0028's departure-time restore-state claim` |
| `specs` (implementation spec: design + TDD plan, `docs/plans/**`) | `specs:` for a new plan, `docs:` for a revision/review pass | `specs: nine-step topic-grouped config-flow implementation design + TDD plan` |
| `documentation` (design docs, `docs/design/**`) | `docs:` | `docs: revise the volatility-based service decomposition` (illustrative) |
| `development` / `testing` | `T<task-number>:` matching the issue's `Plan:` line | `T3: config flow accepts a low-tariff state-translation table` |
| anything else (a fix, refactor, chore not tied to a plan task) | conventional-commit type (`fix:`, `refactor:`, `feat:`, `chore:`) | `fix: revert the unconsumed prompt_timeout_h config-flow field` |

## Project board

Status field on the EMS project board (`gh project view 1 --owner kristofdegrave`) has 5
options: `Backlog`, `Ready`, `In progress`, `In review`, `Done`. `Ready` is unused today (not
part of this workflow) — steps above only move Backlog → In progress → In review → Done. If
`Ready` gets a defined meaning later (e.g. dependencies/contract resolved and pickable),
insert it explicitly into step 0/1 here rather than leaving it implicit.

## From idea to issues (epic decomposition)

Entry point is an in-conversation idea or an existing `idea`-labeled issue (`work-idea` runs
the brainstorm dialogue either way). Once scoped enough to act on:

1. **Single-artifact idea** — file that one issue directly (`file-task-issue`); no epic needed.
2. **Multi-artifact strand** (ADR + spec + implementation, or similar) — file a **new epic
   issue** first, Size only, unchecked checklist placeholder. If the idea started as an issue,
   link it in the epic body ("Split from #NNN") and close the idea issue once it's fully
   captured — the epic is a separate issue that stays open; don't relabel/reuse the idea issue
   as the epic, since an epic must stay open tracking children long after the idea itself is
   "decomposed."
3. **File what's already decidable now**, each appended to the epic's checklist as created:
   ADR issue if a structural decision surfaced; spec issue (`specs`) — needed for nearly every
   multi-artifact strand, skip only when the epic is pure non-code doc work; any other
   already-scoped issue (`uc`, `requirement`, `workflow`).
4. **Don't file `development`/`testing` task issues yet.** They require an approved plan's
   anchored `Plan:` line (`write-impl-spec`'s output), which doesn't exist until step 3's spec
   issue is drafted and reviewed. File them once that plan lands, one per task in the plan's
   build order, each appended to the epic checklist as filed.
5. **Keep the epic current.** Anything that surfaces later and belongs to this strand — a bug
   found mid-implementation, a follow-up task — gets appended to the epic's checklist too
   (`bug`/`enhancement` labels are fine; a child doesn't need a drafter context label to belong
   to an epic).
6. **Size + Estimate on every issue** except the epic itself (Size only — see **Issue
   conventions** below).
7. **Milestone / priority**: not yet standardized — `[TBD]`. Note urgency in the epic body
   until this is resolved rather than inventing a scheme ad hoc.

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

Claude commits, comments, and opens PRs as the human partner's own GitHub account,
`kristofdegrave` — there is no separate bot account (a prior `kristofdegrave-bot` account was
banned and is no longer used). This applies to the interactive session only — the CI flow
below commits as `github-actions[bot]`, a separate, unrelated identity.

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
  `.github/setup-labels.sh`'s label definitions, and `file-task-issue/SKILL.md`. Adding or
  renaming a label means updating all five, not just one.
- **Project-board fields**: always set **Size** (XS/S/M/L/XL) and **Estimate** (points) — they
  drive `_ai-draft.yml`'s `max_turns` tier, not labels. Size a sweep/audit-shaped task
  (cross-file invariant check, full-suite run, cross-check an ADR) up at least one tier from
  raw effort — it's read-heavy for the CI drafter even when small for a human. **Epics get
  Size only, never Estimate** — an epic's cost is the sum of its children's estimates.
- **Epic-first for multi-artifact strands**: see **From idea to issues** above for the full
  cycle (when to file the epic, what to file immediately vs. defer). Child issues use "Part of
  #N" for the epic, never "Closes #N" (would auto-close the epic).
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
number is the GitHub issue number (not the artifact's own sequential number — an ADR's
0001/0002/... numbering is document content, unrelated to its branch name). If extra work on
the same issue needs a second, separate PR, suffix a third segment describing the split:
`<context-label>/<issue-number>/<slug>` (e.g. `development/142/followup`).

## CI flow (`.github/workflows/_ai-*.yml`)

The automated, label-driven equivalent of steps 0–9 above — same lifecycle, different actor.
Commits here are made as `github-actions[bot]`, not the interactive session's `kristofdegrave`
identity.

- **Trigger**: a maintainer labels an issue `needs-draft` plus exactly one context label.
  `workflow` is never auto-drafted — no safe path containment exists for untrusted issue
  content outside `docs/**`/`custom_components/**`/`tests/**` — a human authors that draft by
  hand; only its review step is automated.
- **Draft** (`_ai-draft.yml`, ≈ steps 0–2): resolves the skill, model, and branch
  (`<context-label>/<issue-number>`, this doc's own scheme) from the label; `development`/
  `testing` additionally require a resolved `Plan:` line. Runs the skill's *content* steps only
  (draft, self-checks) — never its review/commit/report steps, since the workflow owns those.
  Opens the PR with `Closes #<issue-number>` and its own, coarser commit-prefix mapping
  (`_ai-draft.yml`'s `commit_prefix`: `docs` for `uc`/`requirement`/`adr`/`specs`, `feat` for
  `development`, `test` for `testing`) — deliberately simpler than the **Commit message
  conventions** table above, since a single draft commit has no per-UC/per-task number to
  interpolate yet; that granularity is added by later human/CI commits on the branch, which do
  follow the table above. Then adds `needs-review`.
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
