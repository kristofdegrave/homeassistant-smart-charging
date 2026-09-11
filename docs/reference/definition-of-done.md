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
  behavior — drive it, don't claim it works on unit tests alone.

Doc/ADR/design artifacts satisfy this with their own self-check instead (6Cs pass, template
conformance, cross-document consistency) — each artifact's own skill defines what "done"
means there (`write-adr`, `write-requirement`, `write-use-case`, `write-impl-spec`,
`write-system-design`, `write-project-design`; the analysis-doc and ADR versions are also
mirrored in `CLAUDE.md`'s artifact-specific sections). The checklist above is the floor for
anything touching `custom_components/`/`tests/`.

## Verify live (per slice, after deployment)

The checklist above is an author self-check on **one PR, before merge** — the author's own
claim, about whichever behaviours the author chose to drive, on a branch. Every vertical slice
therefore also gets a **verify-live** pass once it is deployed, run by the author of the
merged slice ([idea-to-issues.md](idea-to-issues.md)'s **Verify live** stage places it in the
wider flow):

- **The checklist comes from the spec, not from memory** — the entity ids to observe and the
  values, with units, expected of them, fixed before the slice was built. Every spec defines
  this list, one per slice; producing it is part of writing the spec (`write-impl-spec`).
- **The result is a comment on the epic**: the observed value for each item on that list, plus
  a log excerpt or dashboard screenshot. Where the work has no epic — a single-artifact idea,
  or a one-slice fix — the comment goes on the task issue instead.
- **The first slice of a strand is verified live before slice two starts.**

The runtime-verified self-check above and this pass do not substitute for each other, and a PR
that satisfies one has not satisfied the other:

| | Runtime-verified (above) | Verify live |
|---|---|---|
| Unit | One PR | One deployed slice |
| Moment | Before merge | After deployment |
| Judged against | The diff | A checklist written before the code |
| Recorded in | The PR | A comment on the epic (or the task issue) |

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
| anything else — including an issue carrying only a `bug`/`enhancement` kind label, which has no context label to infer from (a fix, refactor, chore not tied to a plan task) | conventional-commit type (`fix:`, `refactor:`, `feat:`, `chore:`) | `fix: revert the unconsumed prompt_timeout_h config-flow field` |

CI's `_ai-draft.yml` uses its own coarser commit-prefix mapping for the initial draft commit
only — see [ci-pipeline.md](ci-pipeline.md).
