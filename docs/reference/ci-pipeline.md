# CI pipeline (`.github/workflows/ai-pipeline.yml` + `_ai-*.yml`)

The automated, label-driven equivalent of
[contribution-workflow.md](contribution-workflow.md)'s chain — the same lifecycle, a different
actor. Commits here are made as `github-actions[bot]`, not the interactive session's own
identity (see that doc's **Git identity** section).

## Labels are CI-only triggers

`needs-draft`, `needs-review`, and `needs-work` exist to invoke these jobs — nothing else. A
**Claude session must never self-apply one on its own initiative** to hand its own review/fix
work to CI instead of doing it in-session; interactive review and fix always happen locally,
per [contribution-workflow.md](contribution-workflow.md) review and fix steps: a fresh reviewer
subagent posts findings via `submit-pr-review`, then `resolve-review-thread` closes out each
thread that got fixed. This does *not* forbid the pipeline's actual, intended human triggers
below — a maintainer applying `needs-draft` to start the pipeline, or manually re-adding
`needs-work` after the loop cap, is the go-signal these labels exist for. What's disallowed is
a session adding one unprompted as a shortcut, which can also collide with the loop-cap
accounting below (e.g. forcing an extra automated review pass eats into the 2-cycle cap a
human never intended to spend).

## Each job does exactly one task

**Draft** only drafts, **review** only reviews and posts findings, **fix** only addresses
posted findings. No job does more than the one task its trigger label names — a review run
never commits a fix, and a fix run never re-reviews its own output (that's the write/review
separation the `workflow` review checklist's non-negotiables enforce).

## Label vocabulary sync

The context-label vocabulary itself (values and meanings) is documented once, in
[contribution-workflow.md](contribution-workflow.md)'s **Issue conventions**. What lives here
is the CI-side consistency obligation: the same vocabulary is baked into six pipeline
places that must all move together — `ai-pipeline.yml`'s header comment; `_ai-draft.yml`'s
`context_labels` variable, its "No context label found" reason string, and its `case` block;
`.claude/profile.yml`'s `labels` section, which `.github/setup-labels.sh` writes to the
repository; and `close-guard.yml`'s `case` block, which
names `development` and `testing` (see **The docs-only close guard** below) — and, for the
three labels that have an issue form, that form's `.github/ISSUE_TEMPLATE/*.yml` `labels:` key
too (`adr.yml` → `adr`, `requirement.yml` → `requirement`, `use-case.yml` → `uc`), which stamps
that label on every issue filed through the form. Two more places carry the same vocabulary
without being part of the pipeline's own configuration — though both are read by the workers at
run time, which is what makes *renaming* a label expensive here rather than merely tedious:
`CLAUDE.md`'s **Model selection** table, one row per context label,
and `docs/reference/work-types/<label>/`, where the label is a **directory name** — so renaming
a label means moving a directory, not editing a line, for each label that has one (today,
`adr`, `development`, `documentation`, `requirement`, `specs`, `testing`, `uc` and `workflow`),
and then
fixing every cross-directory reference the move breaks. **Find them by rule, not from a
list**: every **relative-path** reference that leaves a label's own directory for another
label's — `../<label>/…`, whether it is a markdown link or a bare path in prose, and in
**either** direction, since a label's directory is referred to as often as it refers out.
`grep -rn '\.\./' docs/reference/work-types/` enumerates the candidates in one command;
renaming a label means fixing every hit naming it, on both sides.

No count is stated here on purpose. This sentence is a sync obligation — it exists for the
case where someone forgets to update a list — so a hand-maintained list inside it is the
defect it is meant to prevent, and it has drifted every time one has been tried. The rule
also survives the labels still to migrate, each of which adds more such references.

Three things the rule deliberately excludes, so a rename executor does not chase them.
A reference that leaves the tree entirely (`../../../adl/…`) does not name a label and
survives the move. A reference that stays **inside** one label's own directory — between
`documentation/`'s two per-branch subdirectories, or from one of them back up to the file that
routed there — moves with the directory it sits in. And a route
by **label name** through the *Model selection* table rather than by path — `development`'s
bar sending the `tests/**` half to the `testing` row, and the work files that name a row —
carries no `../` at all: the table named just above is where a rename fixes those.

The shape of that tree — the roles a label's
directory holds, and the per-branch subdirectories a label whose work covers more than one
artifact gets — is [work-types/README.md](work-types/README.md)'s; what belongs here is only
that the label is the directory name, so a rename moves a directory. Adding a label means
updating those eight — the work-types directory only where the new label gets a file of its
own, which is not a given and need not be a work file (`workflow`'s directory holds only a
review checklist); renaming one additionally means updating any form that stamps it. A
rename that misses `close-guard.yml` fails open silently — its `case` simply stops matching —
so that one is checked, not assumed.

All three workers read the table rather than carrying their own copy of the work-file and
checklist mappings — the drafter and the fix worker for the *How the work is done* column, the
reviewer for *How it is reviewed* — so the row is the selection itself rather than a mirror of
one kept in sync by hand. That is what makes changing what a label routes *to* cheap — one
cell in either *How* column — and changing the table's own shape expensive, since it now
reaches every worker at once.
Adding or renaming a label is a third thing again, and not cheap: see the eight places above.

The row is not the whole routing, though. `ai-pipeline.yml`'s path filter decides whether a job
runs at all, and `_ai-review.yml`'s diff enumeration decides which files a checklist can see.
`.claude/profile.yml`'s `review.path_map` holds the same set a fourth time, for the workers
that will read it there instead of here. Adding a tree means editing all four. `docs/design/**` was the standing proof of what happens
otherwise: it sat in the *no context label* row and in neither of the other two, so a
`docs/design`-only PR spawned no job — which takes out the **label** half as well as the path
half, since a job that never runs cannot add a reviewer either. All three now carry it.
`file-task-issue/SKILL.md` doesn't hold its own copy — it points at `CLAUDE.md`'s Issue
conventions, which forwards to [contribution-workflow.md](contribution-workflow.md).

The **action/state labels** (`needs-draft`, `needs-review`, `needs-work`, `needs-approval`,
`needs-decision`) are not context labels either. They are defined in exactly one of those
eight places — `.claude/profile.yml`'s `labels`; where another of the eight mentions one (an issue
form's guidance text, `_ai-draft.yml`'s reason string, `ai-pipeline.yml`'s Action/state line)
it is prose telling a human which trigger to add next, never a value a worker matches on, so a
rename there is a wording fix rather than a sync obligation. What binds instead is the set of
places that *match* or *apply* them: `ai-pipeline.yml`'s three `if:` guards, which compare
`github.event.label.name` against a trigger label by string and — like `close-guard.yml`'s
`case` block above — fail open silently on a rename, every job simply never firing; `_ai-review.yml`'s
verdict routing (and `_ai-draft.yml`/`_ai-fix.yml` for the two trigger hand-offs); and, for
the two exit labels, the interactive lifecycle's two exits — reached through `CLAUDE.md`'s
**Contribution workflow** section, whose doc names in its **Exit labels** section the one step
that applies them — so a rename is checked there rather than assumed from here. On the CI side, `_ai-review.yml`'s verdict routing is the only place that applies
either. Adding or renaming one means updating that set, and the **Pipeline steps** below where
the label's meaning is stated.

The **kind-of-work labels** (`bug`, `enhancement`) are deliberately in exactly one of those
places — `.claude/profile.yml`'s `labels` — and in none of the other seven, including
`docs/reference/work-types/<label>/`, which a kind label never gets. They are not context labels
([contribution-workflow.md](contribution-workflow.md)'s **Issue conventions**), so adding or
renaming one never touches `ai-pipeline.yml`'s header, `_ai-draft.yml`'s
`context_labels`/reason string/`case` block, `close-guard.yml`'s `case` block, an issue form,
or `CLAUDE.md`'s **Model selection** table. `_ai-draft.yml` consequently cannot see them, which
is the intended behaviour on all three shapes: a `bug` issue with no context label is refused
with *No context label found*; a `bug` issue that also carries one routes on that one, exactly
as if the kind label were absent (so `count` is still 1 and the single-context-label refusal is
unaffected); and a `bug`+`development` issue must still resolve an anchored `Plan:` line, so
unpinned fix work fails closed rather than being drafted from free-text issue content. What a
kind label *does* reach is the doc side: [contribution-workflow.md](contribution-workflow.md)'s
**Issue conventions** owns the two-axis rule and every other document points at it, so renaming
one means updating the profile's `labels` (and re-running `setup-labels.sh`) and that section —
and then checking the handful of
documents that name the label in passing.

## The docs-only close guard

`.github/workflows/close-guard.yml` fails a PR whose changed files are all under `docs/` and
which closes a `development`/`testing` issue: a documentation-only diff cannot implement code,
so closing a code task with one marks the work done while it is still outstanding. It is the
one **hard** gate on the documentation-to-code link; the two prompt-level checks that back it
up sit in the `requirement` work type's propagate step and the Code-backing item of the
completion bar its row names.

It is deliberately not part of the AI pipeline this document otherwise describes. A checklist
item in `_ai-review.yml` would be a model's judgement on a PR that reached `needs-review` and
would gate no merge, and a check in `ai-pipeline.yml` would run only when someone applies a
label. It is equally deliberately not a job in `ci.yml`, where the project's other required
status checks live: it needs the `edited` trigger, since the state it refuses is created by
editing a PR body, and putting `edited` on `ci.yml` would re-run the whole build matrix on
every body or title edit and cancel in-flight test runs through that file's concurrency group.

It detects closing references through GitHub's own resolution of them, so a keyword in the
body, an `owner/repo#n` reference, a full issue URL and a link made in the PR's Development
sidebar all count. It is evaluated as of the last push or edit, though: a sidebar link emits no
`pull_request` event, so one added after the last event is caught only by the next one.

It reports a status on every PR, but only blocks a merge once `docs-only-close-guard` is listed
in branch protection's required checks on `main`.

## Pipeline steps

- **Trigger**: a maintainer labels an issue `needs-draft` plus exactly one context label — a
  context label alone never triggers anything; only an *action* label (`needs-draft` on an
  issue; `needs-review`/`needs-work` on a PR) spawns an AI job. `workflow` and `documentation`
  are never auto-drafted — neither is in `_ai-draft.yml`'s label set (`workflow` because a
  drafted label is contained by an allow-list of the trees its drafts actually write — one tree
  for each doc label — and that list never reaches the files instructing future drafts. A
  `workflow` change **is** those instructing files — `.github/`, `.claude/`, `CLAUDE.md` — so
  no allow-list can contain one; `documentation` simply isn't wired in yet). A human authors
  both drafts by hand. The review step is still automated
  for `workflow` and for `documentation`, since
  routing reaches both through the changed paths and not only through the issue's context label.
  `docs/design/**` is in `ai-pipeline.yml`'s path filter and `_ai-review.yml`'s diff enumeration,
  so a PR touching only that tree reaches the `documentation` checklist. Being outside the
  drafter and being outside review are separate facts: `documentation` is still never
  auto-drafted, for the reason above.
- **Outside the pipeline by design**: `docs/postmortems/**` is in neither `ai-pipeline.yml`'s
  path filter nor `_ai-review.yml`'s diff enumeration, so a PR touching only that directory
  spawns no AI job and a PR touching it alongside other trees has its post-mortem invisible to
  the CI reviewer. That is deliberate — every one of the reviewer checklists is written against
  an artifact that asserts behaviour, and none fits a narrative document whose review is about
  quotation accuracy (see `CLAUDE.md`'s **Post-mortems** topic). Review is a fresh-agent
  pass run interactively instead. If a checklist for it is ever written, add the directory to
  both places and this bullet becomes the record of why it was absent.
- **Draft** (`_ai-draft.yml`, ≈ the **File the issue** and implement steps): resolves the model and branch
  (`<context-label>/<issue-number>`, [contribution-workflow.md](contribution-workflow.md)'s own
  scheme, or a label's own override per its **Branch naming** note) from the label. Its
  `max_turns` tier is driven by the issue's project-board **Size** field (set per
  [contribution-workflow.md](contribution-workflow.md)'s **Issue conventions**) — Estimate is
  planning-only and isn't read by any workflow. `development`/`testing` additionally require a
  resolved `Plan:` line — the exact,
  anchored format (`Plan: docs/plans/<file>.md#T<task-number>`, nothing else on that line: no
  backticks, no trailing `(PR #NNN)`, no surrounding sentence) is the sole scope-pinning
  mechanism letting this job act on untrusted issue-body text, so it must resolve to exactly
  one plan file and task id (`<task-number>` matching the plan's own numbering, e.g. `T3.1`,
  `T5`) or the run fails. **The file describing the artifact is not named in the workflow**: the
  worker reads `CLAUDE.md`'s **Model selection** table row for the label and follows whatever
  its *How the work is done* column names. That is what lets a work type move out of
  `.claude/`, and change how many files it is split into, without this workflow changing; a
  missing row, or a named file that does not exist, stops the run rather than drafting from
  memory. Runs that file's *content* steps only (draft, self-checks) —
  never its review/commit/report steps, since the workflow owns those. Opens the PR with
  `Closes #<issue-number>` and its own, coarser commit-prefix mapping (`_ai-draft.yml`'s
  `commit_prefix`: `docs` for `uc`/`requirement`/`adr`/`specs`, `feat` for `development`,
  `test` for `testing`) — deliberately simpler than the
  [commit message conventions](definition-of-done.md) table, since a single draft commit has
  no per-UC/per-task number to interpolate yet; that granularity is added by later human/CI
  commits on the branch, which do follow that table. Then adds `needs-review`.
- **Review** (`_ai-review.yml`, ≈ the review step): `needs-review` resolves its checklists from
  `CLAUDE.md`'s **Model selection** table — the routing rule, both halves of it, lives there
  rather than in the workflow —
  and self-applies each against the files it covers, posting findings via `submit-pr-review`'s
  CI mode and ending in a `clean`/`remarks` verdict marker. Because that table comes from the
  PR's own merge ref, a diff touching `CLAUDE.md`, `.claude/`, `docs/reference/` or the label
  script — computed from the changed paths by the workflow, not judged from the diff's content
  — has its **instructions** read from base-branch copies staged into the runner's temp
  directory, and the review body opens with a note recording that the instructions were taken
  from the base branch and that the new version needs a human read. That note is never a
  finding and never makes the verdict `remarks`: there is nothing for a fix worker to do about
  it, and a clean verdict routes the PR to `needs-approval`, which is the human read it asks
  for. What it does not claim is that the routing was rewritten — the trigger is a path
  trigger and cannot establish that. The protection is the base copies, not the note: a PR must
  not be able to apply its own rewritten routing to itself. Only the instructions move: the files under review are still the
  PR's, read from the checkout. The staging step verifies every base copy it wrote is present
  and the right size and fails the job otherwise, so whether the guard held is never the
  worker's judgement, and a failure to enumerate the changed paths turns the guard **on**, not
  off. The staged set is a superset of the paths that arm it, so base routing can never name a
  file that has no base copy. A file the PR *adds* under a watched tree arms the guard and has
  no base copy, which is correct: it is not something the base standard can route to. As with the drafter, the table
  column may name one or more of an agent definition, a work-type review document and a
  completion bar; the worker follows what it says, so a checklist can move, or split, without
  this workflow changing. Unacknowledged human inline
  comments (no `ai-fix-ack` reply) count as
  remarks too — the CI equivalent of the fix step's rule that human PR comments are findings.
- **Fix** (`_ai-fix.yml`, ≈ the fix step): a `remarks` verdict on a **docs-only** diff adds
  `needs-work`, which runs `address-review-remarks`, commits as `github-actions[bot]`
  (`docs: address AI review remarks (#<pr>)`), and re-adds `needs-review`. It can only commit
  under `docs/`, and not `docs/reference/work-types/**` — the tree it reads as its own
  instructions, excluded from its commit step so one fix run cannot rewrite what the next one
  obeys. So a diff touching **anything** outside that set (`.github/`, `.claude/`,
  `custom_components/`, `tests/`, or a work file) never reaches it automatically:
  `_ai-review.yml`'s `non_docs_changed` guard routes that PR straight to the two exit labels
  (**Clean / cap-out** below) with a comment saying why, rather than spending fix cycles that could not
  commit anything. A human applies those changes by hand — or re-adds `needs-work` manually
  to get one fix pass over the `docs/` part of a mixed diff, which is the only way the fix
  job ever sees a non-docs PR. That bound no longer means "documents only", though: the
  work-type tree puts files that *instruct* a drafter under `docs/`, which is why the per-type
  allow-list is pulled ahead of the rest of the CI change.
- **Loop cap** (docs-only diffs — the only ones that reach the fix job automatically): **2**
  automatic fix cycles, because CI runs fully unsupervised with no human watching in real time.
  A 3rd `remarks` verdict goes straight to `needs-approval` **plus `needs-decision`**, with a
  comment giving the human the two decisions: merge as is, or re-add `needs-work` manually to
  grant one more cycle. The interactive session caps its own loop
  separately ([contribution-workflow.md](contribution-workflow.md)'s **Rounds and the cap**): the two count
  different populations and never interact, so neither is the other's bound. Which labels the
  interactive cap applies is that doc's **Exit labels** section's own business, not this file's.
- **Clean / cap-out** (≈ the review step's exit): a `clean` verdict, hitting the 2-cycle cap, or a `remarks`
  verdict on a non-docs diff all add `needs-approval` — same label, same meaning as the
  interactive flow: no automated work pending, human approval to merge still required. The
  two `remarks` exits — the cap and the non-docs hand-off — also add `needs-decision`; the
  clean verdict never does. `needs-approval` answers *does this need a human*,
  `needs-decision` answers *did the review leave findings open* — the two states a maintainer
  scanning the PR list most needs to tell apart, and indistinguishable from the first label
  alone. Every run that reaches the routing step clears a stale `needs-approval` before any
  verdict is applied — the removal there is unconditional; a stale
  `needs-decision` is cleared only by a `clean` verdict, so a granted extra cycle that comes
  back clean drops it, while a run that produced no verdict at all leaves the findings-open
  signal standing.
- **Merge** (the **Clean up** step's precondition, unchanged): always a manual human action regardless of which path
  drafted or reviewed the PR.
