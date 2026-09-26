# ADR-0048: Retire the AI label pipeline — the lifecycle runs in local sessions only (deprecates ADR-0041 and ADR-0020)

Date: 2026-09-26
Status: Accepted

## Summary

In the context of a CI pipeline that drafts, reviews and fixes pull requests on three labels and
is not used, facing the rules, copies and review surface it adds to every process change, we
decided to retire it, keeping an abstract description of the CI lifecycle, to keep the
method's cost in line with what is actually run, accepting that adopting CI again means
rebuilding it from that description rather than applying a label.

## Context

- **The pipeline.** Three labels trigger it — one to draft an issue into a PR, one to review a PR,
  one to fix it — through four workflows and two composite actions that only those workflows use.
  Around it sit a path map held in four copies with a check that keeps them in step, a verdict
  marker, and a CI branch in 13 skills and some 35 other files.
- **It is not used, and is not expected to be.** All work runs in local interactive sessions
  instead: issue → implement → review → fix → `needs-approval` → human merge → cleanup, with
  `needs-decision` as the other exit.
- **Its cost falls on local work too.** Some rules exist only so the CI workers can run: the
  drafter's containment, the verdict markers, the path map's copies. The fix worker's tool grant
  cannot count words, so a fix summary reports net lines. Every `workflow` change is reviewed
  against its CI half as well.
- **Regular CI does not depend on it.** Lint, tests, hassfest, HACS, the method and authoring
  checks, the close guard, the upstream-drift watcher and the release workflows each run without
  the pipeline.
- **The pipeline's structure is architectural.** The ADR bar's test/CI carve-out does not reach
  the CI pipeline's own structure. Two Accepted records decide parts of it:
  [ADR-0041](0041-ci-reviewer-instruction-subject-trust-boundary.md), the review worker's trust
  boundary, and [ADR-0020](0020-skillspector-advisory-pr-scan.md), the SkillSpector scan that
  runs only as a job inside the review workflow.
- **The method travels between repositories.** Another project adopting it may want to run the
  lifecycle in CI, so the shape of CI's part is worth keeping, even where this project's
  implementation is not.

## Considered options

### Option A — Keep the pipeline (status quo)

- Pro: nothing to migrate; CI work resumes the moment a label is applied.
- Con: pays every cost in the Context for a capability no one runs, and keeps two descriptions of
  one lifecycle — the local steps and their CI branches — that each process change must keep in
  step.

### Option B — Keep the files, disable the triggers

- Pro: a one-line change per workflow, reversed just as cheaply; the documentation stays intact.
- Con: dormant code still binds. The documents, path map and checklists still describe the
  pipeline and must still be kept in step, so most of the cost stays.
- Con: a workflow that never runs is never tested, so turning it back on means debugging drift
  that no run was there to reveal.

### Option C — Retire it, keeping an abstract description of the CI lifecycle

The workflows, composite actions, labels, path map and every CI branch in the method go. The
local lifecycle is unchanged. The method keeps a short description of how the lifecycle *would*
run in CI: that each step can be triggered by a label of its own, that each job does one task,
that review and fix loop to a cap, and that `needs-approval` hands over to the human. It names no
label, workflow or tool grant.

- Pro: removes the rules, copies and review surface that exist only for the pipeline, while
  regular CI is untouched.
- Pro: the method still says how its steps split into jobs, which is what a project adopting it
  with CI would start from.
- Con: adopting CI again means rebuilding it from that description and from history, not
  applying a label. ADR-0041's trust boundary and ADR-0020's scan go with it, so a future
  pipeline has to decide its own.
- Con: a one-time migration across nearly sixty files, which has to be ordered so that no live
  pointer names a file that has already been deleted.

### Option D — Retire it with no description at all

- Pro: the smallest method; nothing about CI left to maintain.
- Con: the method loses the one statement that its steps are separable jobs. That statement also
  explains why each step skill does one task and why the review loop has a cap.

## Decision

**Option C.** A's and B's Cons are the costs this record exists to remove, and B removes the least
of them for its trouble. D's smaller method is bought with what C's second Pro keeps. C's
first Con is accepted because the pipeline is not expected to return in this project, and the
abstract description is what a return would start from. Its second is a one-off cost, where A's
is paid on every change.

## Consequences

**ADR-0041 and ADR-0020 are deprecated, not superseded.** Each decided the structure of a
workflow that no longer exists, and no new decision replaces either. A future CI pipeline decides
its own trust boundary in a record of its own. ADR-0020's rule that a static scanner over the
instruction tree is advisory by default lapses with it.

**Four records that cite the pipeline stand as written.** ADR-0037, ADR-0043, ADR-0044 and
ADR-0045 mention it in their reasoning or their conformance tables, but none of their decisions
depends on it.

**What stays.** The local lifecycle and its step skills. `needs-approval`, `needs-decision` and
the rules on who applies them. The `workflow` row's *none — human-authored*, though its reason,
the CI drafter's containment, lapses with the drafter. `CLAUDE.md`'s no-label path-map
paragraph, which becomes the path map's only copy.

**What goes with the labels.** The rule against self-applying the three trigger labels. The path
map's other copies and the check that holds them together. The CI branch of every skill and
document. `address-review-remarks` folds into `fix`, whose summary reports net words again, and
`submit-pr-review` keeps only its local mode.

**Outside the repository.** Once the pipeline's files are deleted, the human partner deletes the
three trigger labels, the `ai` environment and the `ANTHROPIC_API_KEY` and `WORKFLOW_PAT` secrets
on GitHub; `setup-labels.sh` never deletes a label.

**Easier:** a process change is written and reviewed once, for the case that runs. **Harder:**
nothing drafts, reviews or fixes unattended, so every step needs a session.

**Blast radius.** Two searches, both run from the repository root over the same excluded trees:

```sh
rg -n -i --hidden --glob '!.git/' \
  --glob '!docs/adl/**' --glob '!docs/postmortems/**' --glob '!docs/archive/**' \
  --glob '!docs/plans/**' --glob '!CHANGELOG.md' --glob '!.github/test-check-authoring-rules.sh' \
  -e '_ai-(draft|review|fix)' -e 'ai-pipeline' -e 'ai-review-verdict' -e 'needs-(draft|review|work|\*)' \
  -e 'drafter' -e '(CI|review|fix) worker' -e 'CI mode' -e 'self-appl' -e 'address-review-remarks' \
  -e 'path_map|check-path-map' -e 'create-uc-issues' -e 'ai-cost-summary|anthropic-smoke-test' \
  -e 'WORKFLOW_PAT|ANTHROPIC_API_KEY' .
```

```sh
rg -n -i --hidden --glob '!.git/' \
  --glob '!docs/adl/**' --glob '!docs/postmortems/**' --glob '!docs/archive/**' \
  --glob '!docs/plans/**' --glob '!CHANGELOG.md' --glob '!.github/test-check-authoring-rules.sh' \
  -e 'github-actions\[bot\]|claude-code-action|documentation pipeline|CI-drafted|CI lifecycle|CI pipeline' \
  -e 'AI review|review pipeline|SkillSpector|ADR-00(20|41)\b|\| 00(20|41) \|' .
```

Wide enough because the first keys on every name the pipeline's parts have — its workflows,
actions, labels, marker, roles, secrets, fix-entry skill and the rules that exist only for it —
and the second on how prose names the pipeline as a whole — its bot account, the action it
runs, the phrases the documents use for it — and on the two records this one deprecates, since
a citation of either describes a decision that no longer holds. `--hidden` is load-bearing,
since most sites sit under `.claude/` and `.github/`, which `rg` otherwise skips. On
`origin/main` the first returns **398** hits in 50 files and the second **64**, 53 of them in
files the first already hits.

| Sites | Today | Follow-up |
|---|---|---|
| **The pipeline's own files** (7): `.github/workflows/ai-pipeline.yml`, `_ai-draft.yml`, `_ai-review.yml`, `_ai-fix.yml`; `.github/actions/ai-cost-summary/`, `.github/actions/anthropic-smoke-test/`; `.github/create-uc-issues.sh` — 146 + 35 hits | Route the three labels to the drafting, review and fix jobs, and run them | Removed with the pipeline's workflows |
| **The path-map check** (3): `.github/check-path-map.py`, `check-path-map.sh`, `test-check-path-map.sh` — 61 + 2 | Hold the path map's four copies in step | Removed with the path map |
| **Retained checks, hooks and scripts** (7): `.github/workflows/ci.yml`, `.github/hooks/pre-commit`, `.github/check-method.py`, `.github/test-check-method.sh`, `.github/check-word-budget.sh`, `.github/setup-labels.sh`, `.gitignore` — 12 + 2 | Run or cite the path-map check, name the CI worker, describe the labels as the pipeline's, or justify an ignore rule by the action the pipeline runs | Path-map steps and citations removed with the path map; the comments reworded for regular CI |
| **The CI lifecycle document and a workflow pointing into it** (2): `docs/reference/method/ci-pipeline.md`, `.github/workflows/upstream-drift.yml` — 53 + 5 | Describe the pipeline in full; point at "the CI lifecycle" and keep a `needs-*` invariant | Rewritten as the abstract description plus its three regular-CI sections; the watched-path section removed with the path map; the pointer and invariant reworded |
| **Skills** (13) under `.claude/skills/`: `address-review-remarks`, `cleanup`, `diagnosing-bugs`, `file-task-issue`, `fix`, `grilling`, `handoff`, `implement`, `research`, `resolve-review-thread`, `review`, `submit-pr-review`, `work-idea` — 33 + 2 | Carry a CI branch, the self-apply rule or CI's fix entry | CI branches removed; `address-review-remarks` folded into `fix` |
| **Routing and profile** (6): `CLAUDE.md`, `.claude/profile.yml`, `docs/reference/method/model-selection.md`, `docs/reference/work-types/workflow/review.md`, `docs/reference/profile.md`, `.github/CODEOWNERS` — 42 + 4 | State the self-apply rule, the path map's copies, the three labels, the `workflow` row's CI reason and the checklist's CI-worker checks, or justify code-owner review by bot-opened PRs | Rewritten for the local case; the labels and `path_map` removed from the profile; the secrets checks reworded for any workflow that holds secrets; `CODEOWNERS` keeps covering every tree, justified by the manual merge gate alone |
| **Other method and work-type documents, and the issue forms** (18): under `docs/reference/method/`, `ai-authoring.md`, `contribution-workflow.md`, `decomposition-checklist.md`, `definition-of-done.md`, `idea-to-product.md`, `tracker-mechanics.md`; under `docs/reference/work-types/`, `README.md`, `adr/implement.md`, `adr/review.md`, `development/review.md`, `development/done.md`, `documentation/review.md`, `testing/review.md`, `uc/done.md`, `uc/review.md`; `.github/ISSUE_TEMPLATE/adr.yml`, `requirement.yml`, `use-case.yml` — 51 + 9 | Carry an "in CI…" branch, the review prompt's self-apply sentence, the bot-PR exception to the Runtime check, or a form's prompt to trigger the drafter | "In CI" branches removed or rewritten for the local case |
| **The design document's ADR index** (1): `docs/design/system-design.md` — 0 + 3 | Lists ADR-0020 and ADR-0041 as standing, and counts the records after ADR-0019 without this one | Both rows marked deprecated by this record, and this record given its row |

No hit conforms: 398 + 62 hits are in the rows above.

Neither search keys on a bare "CI", which the documents also use for the pipeline as an actor
("CI therefore refuses to draft…"). Over the same scope, `rg -n -e '\bCI\b'` returns 171 hits:
155 in files the rows above already hold, and 16 in seven other files, all of them regular CI —
the release workflow, the benchmarks, the authoring and drift checks, and the ADR bar's own
carve-out — which keep describing it. The pipeline lines among the 155 are removed or rewritten
by a final sweep, once the pipeline's files are gone.

Out of scope: `.github/workflows/upstream-drift.yml:112` and `:114`, two of the second search's
hits, name `github-actions[bot]` for regular CI's own issue lookup and keep doing so. The
excluded trees are never edited for this: Accepted ADRs keep their text apart from the
deprecation Status lines, post-mortems, archived documents, plans and the changelog stay dated
records, and `test-check-authoring-rules.sh` keeps its synthetic `_ai-*` fixture names, which
test pattern matching rather than the pipeline. This record and its ADL row fall in that
exclusion, so neither is a hit.
