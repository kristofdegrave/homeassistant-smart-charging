# Definition of Done & commit message conventions

## Definition of Done (self-check before opening the PR)

Before pushing and opening the PR ([contribution-workflow.md](contribution-workflow.md) step
2), self-check against a baseline Definition of Done — this is the author's own review,
distinct from step 3's fresh external reviewer:

- **Scope**: built what the issue actually asked, no more and no less (see
  [contribution-workflow.md](contribution-workflow.md)'s **Parallel work and forward
  dependencies** for anything intentionally deferred to a later task).
- **Builds/lints clean**: no syntax errors; linter passes (`ruff check .` and `ruff format
  --check .` for `custom_components/`/`tests/` changes — pair both, not just the first).
- **Tests green**: the relevant suite passes, in the harness matched to what changed
  (ADR-0009: plain pytest for pure logic, HA harness for adapters/coordinator/entities/config
  flow).
- **Test coverage matches the change**: new behavior has a new test that proves it, not just
  reliance on existing tests happening to still pass; edge cases the issue implies are
  covered, not only the happy path.
- **Runtime-verified, not just test-verified**, for anything with observable runtime
  behaviour — drive it, don't claim it works on unit tests alone, and record what you drove
  and what you saw in the PR description's **Runtime check** section (next).

Doc/ADR/design artifacts satisfy this with their own self-check instead (6Cs pass, template
conformance, cross-document consistency) — each artifact's own skill defines what "done"
means there (`write-adr`, `write-requirement`, `write-use-case`, `write-impl-spec`,
`write-system-design`, `write-project-design`; the analysis-doc and ADR versions are also
mirrored in `CLAUDE.md`'s artifact-specific sections). The checklist above is the floor for
anything touching `custom_components/`/`tests/`.

### Runtime check (in the PR description)

A PR that changes **observable runtime behaviour** carries a **Runtime check** section in its
description (any heading level — the level is not load-bearing, the heading text is).
Observable runtime behaviour is what someone can see from the *running* integration rather
than from its source or its test output, and a diff changes it when it changes any of:

- an **owned entity's state value**, or the computation that produces it;
- an owned entity's **unit of measurement**, **display precision**, **device class** or
  **state class**;
- the **dashboard** — which tiles or cards appear, their order, titles, or how a value is
  formatted;
- a **notification** the integration raises — its text, its trigger condition, or when it
  clears;
- the **current commanded to the charger**;
- whether an owned entity **appears at all** — registry enablement and capability gating —
  whether it goes **unavailable**, and the **name it displays** (`strings.json`,
  `translations/`).

A diff changes none of these, and needs no section, when no input exists for which any item on
that list would come out differently — the usual cases being an internal refactor, a rename
with no surfaced effect, tests, and documentation.

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
they carry the entity ids into the slice's **Verify live** checklist below. Approving without
doing one of the two is the thing this bar exists to make visible.

This is not a CI gate, deliberately: a mechanical presence check is satisfied by an empty
heading, and no automated check can tell whether a pasted reading is the one the diff changed.
The check is `code-reviewer` reading the section against the diff — a diff that touches
anything in the list above with no Runtime check section is a **Major** finding there.

## Verify live (per slice, after deployment)

The Definition of Done above, its Runtime check included, is an author self-check on **one PR,
before merge** — the author's own claim, about whichever behaviours the author chose to drive,
on a branch. Every vertical slice therefore also gets a **verify-live** pass once it is
deployed, run by the author of the merged slice ([idea-to-issues.md](idea-to-issues.md)'s
**Verify live** stage places it in the wider flow):

- **The checklist comes from the spec, not from memory** — the entity ids to observe and the
  values, with units, expected of them, fixed before the slice was built. Every spec defines
  this list, one per slice; producing it is part of writing the spec (`write-impl-spec`).
- **The result is a comment on the epic**: the observed value for each item on that list, plus
  a log excerpt or dashboard screenshot. Where the work has no epic — a single-artifact idea,
  or a one-slice fix — the comment goes on the task issue instead.
- **The first slice of a strand is verified live before slice two starts.**

The Runtime check above and this pass do not substitute for each other, and a PR that satisfies
one has not satisfied the other:

| | Runtime check (above) | Verify live |
|---|---|---|
| Unit | One PR | One deployed slice |
| Moment | Before merge | After deployment |
| Judged against | The diff | A checklist written before the code |
| Recorded in | The PR's **Runtime check** section | A comment on the epic (or the task issue) |
| Checked by | `code-reviewer`, on the open PR | The author of the merged slice, against the spec's list |

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
| anything else (a fix, refactor, chore not tied to a plan task) — including an issue carrying only a `bug`/`enhancement` kind label, which has no context label to infer from | conventional-commit type (`fix:`, `refactor:`, `feat:`, `chore:`) | `fix: revert the unconsumed prompt_timeout_h config-flow field` |

CI's `_ai-draft.yml` uses its own coarser commit-prefix mapping for the initial draft commit
only — see [ci-pipeline.md](ci-pipeline.md).
