# Definition of Done & commit message conventions

## Definition of Done (self-check before opening the PR)

Before pushing and opening the PR (the close of [contribution-workflow.md](contribution-workflow.md)'s
implement step), self-check against a baseline Definition of Done — this is the author's own review,
distinct from the review step's fresh external reviewer:

- **Scope**: built what the issue actually asked, no more and no less (see
  [contribution-workflow.md](contribution-workflow.md)'s **Parallel work and forward
  dependencies** for anything intentionally deferred to a later task).
- **Builds/lints clean**: no syntax errors; the linter passes — the command, and the pairing
  rule that goes with it, are the `development` work type's stack overlays' (the row in
  `CLAUDE.md`'s **Model selection** table names the work file; its **Overlays** section
  routes on).
- **Tests green**: the relevant suite passes, in the harness matched to what changed — the
  `testing` bar's item 1, *Harness split*, and the stack overlay it routes to, state the
  split.
- **Test coverage matches the change**: new behavior has a new test that proves it, not just
  reliance on existing tests happening to still pass; edge cases the issue implies are
  covered, not only the happy path.
- **Runtime-verified, not just test-verified**, for anything with observable runtime
  behaviour — drive it, don't claim it works on unit tests alone, and record what you drove
  and what you saw in the PR description's **Runtime check** section (next).

Doc/ADR/design artifacts satisfy this with their own self-check instead (6Cs pass, template
conformance, cross-document consistency) — the artifact's row in `CLAUDE.md`'s **Model
selection** table defines what "done" means there. The analysis-doc version is also mirrored in
`CLAUDE.md`'s **Review protocol for analysis documents** topic. The checklist above is the
floor for anything touching the product-code and test trees.

**A row's completion bar applies wherever the row names one** — not only to those artifacts.
Where a row names a **completion bar**, that file is what the author self-checks against and
what the reviewer applies; where it names none, the row's work file carries what "done"
means. What differs between classes is how the bar meets the checklist above, and a work-type
file may rely on this: for a doc artifact the bar **stands in for** that checklist, there being
nothing to build or run; for a change touching the product-code or test trees the bar **adds
to** it, because the checklist is the floor for exactly those trees.

### Runtime check (in the PR description)

A PR that changes **observable runtime behaviour** carries a **Runtime check** section in its
description (any heading level — the level is not load-bearing, the heading text is).
Observable runtime behaviour is what someone can see from the *running* system rather than
from its source or its test output. What that is in this stack — the list a diff is judged
against — is the `development` work type's stack overlay's, under its bar's item 6, *Runtime
check recorded when the change is observable at runtime*; this document owns the definition
and the section's shape, the overlay owns the enumeration. A diff changes none of it, and needs no section, when no input exists for
which any item on that list would come out differently — the usual cases being an internal
refactor, a rename with no surfaced effect, tests, and documentation.

The section states two things, in as few lines as they take:

- **What was driven** — the conditions the running integration was put into: the mode, whether
  a car was connected, and the readings that were present or seeded.
- **What was observed** — the **pasted entity state including its unit** for every entity the
  diff affects, or a **dashboard screenshot** where the change is one of layout, formatting or
  legibility. A bare number does not satisfy this: unit and precision defects are exactly what a
  value pasted without its unit hides.

Where the behaviour genuinely cannot be driven before merge, the section still exists and says
so, naming what was substituted (a log excerpt, a seeded harness run) and what is left for the
**Verify live** pass below. An absent section and an honest one are different states, and only
the second is reviewable.

**A PR opened by the CI pipeline's bot account is the one exception, and it is not the bot's
finding.** That body is written by the pipeline, and no worker there has a running installation
to drive, so such a PR carries no Runtime check section and its absence is not a review finding
— a reviewer says what the check would have to record and stops there, rather than spending a
fix cycle on something no fix worker can produce. The observation is still owed, by the human
partner who approves the merge: either they add the section to the PR body before approving, or
they carry the entity ids into the task's **Verify live** list below. Approving without
doing one of the two is the thing this bar exists to make visible.

This is not a CI gate, deliberately: a mechanical presence check is satisfied by an empty
heading, and no automated check can tell whether a pasted reading is the one the diff changed.
The check is the review of the PR's product-code half reading the section against
the diff — a diff that touches anything in the overlay's list with no Runtime check section is a
**Major** finding there. That review's checklist and the completion bar it applies are named in
the `development` row of `CLAUDE.md`'s **Model selection** table.

## Verify live (per vertical slice, after deployment)

The Definition of Done above, its Runtime check included, is an author self-check **before
merge** — the author's own claim, about whichever behaviours the author chose to drive, on a
branch. Every vertical slice therefore also gets a **verify-live** pass once it is
deployed, run by the author of the merged slice ([idea-to-product.md](idea-to-product.md)'s
**Verify live** stage places it in the wider flow). A vertical slice is what the flow's
**Ticket** stage cuts a child issue to, so on the plan track it is one task entry, one issue
and one PR — the same unit this page's self-check ran on, observed again in a different place
and against a different standard:

- **The list comes from the spec, not from memory** — fixed before the slice was built. That
  the spec carries one per task, and what each item has to name, is an item of the `specs`
  completion bar ([work-types/specs/done.md](../work-types/specs/done.md), named in that row of
  `CLAUDE.md`'s **Model selection** table) — so a missing or unusable list is a finding
  against the spec, caught when the spec is reviewed rather than when this pass is run.
- **The result is a comment on the epic**: the observed value for each item on that list, plus
  a log excerpt or dashboard screenshot. Where the work has no epic — a single-artifact idea,
  or a one-slice fix — the comment goes on the task issue instead.
- **The first slice of a strand is verified live before slice two starts.**

The Runtime check above and this pass do not substitute for each other, and a PR that satisfies
one has not satisfied the other. Sharing a unit is exactly why: two claims about the same
slice, and only the second is made where the code actually runs, against a standard fixed
before it was written.

| | Runtime check (above) | Verify live |
|---|---|---|
| Moment | Before merge | After deployment |
| Judged against | The diff | A list written before the code |
| Recorded in | The PR's **Runtime check** section | A comment on the epic (or the task issue) |
| Checked by | The `development` review, on the open PR | The author of the merged slice, against the spec's list |

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
| `workflow` (CI/skill/agent-authoring changes) | `workflow:` | `workflow: a weekly drift check reads the profile's dependency pins and reports what moved` |
| anything else (a fix, refactor, chore not tied to a plan task) — including an issue carrying only a `bug`/`enhancement` kind label, which has no context label to infer from | conventional-commit type (`fix:`, `refactor:`, `feat:`, `chore:`) | `fix: revert the unconsumed prompt_timeout_h config-flow field` |

One row per context label, and `.github/check-method.py`'s check 3 fails when an enabled one
has none — so a label added to the profile is a row owed here.

CI's `_ai-draft.yml` uses its own coarser commit-prefix mapping for the initial draft commit
only — see [ci-pipeline.md](ci-pipeline.md).
