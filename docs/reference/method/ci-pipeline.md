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
is the consistency obligation: the same vocabulary is baked in wherever a worker, a script or
an instruction to a future run names a label, and all of those must move together. Three rules
find them, and **no rule's scope is a list**: two read the whole repository, and the third is
narrowed by an argument rather than an enumeration — stated where it is given, so it can be
checked. That matters because a scope enumerated by hand is the same defect these rules exist
to catch, and was: `.github/create-uc-issues.sh` applies a context label with
`gh issue create --label uc` and sat outside an earlier scope list for as long as that list
was maintained by hand.

**The name rule** finds the prose and the values a *rename* makes wrong, and it reads the whole
repository:

```sh
git ls-files -z | xargs -0 grep -nE '\buc\b'
```

— run once per label being renamed, with that label in place of `uc`. Nothing is excluded, and
nothing needs to be: a label word is a candidate wherever it appears, and the trees a list
would have left out are exactly the ones that bit. The price is volume, which differs by label
rather than being uniform, and is the honest cost of a scope that cannot miss.

Every hit is a **candidate**, not an obligation. Most of the labels are also ordinary English
words — `workflow` and `requirement` above all — so the rule over-includes on purpose and the
reader decides per hit whether it is the label or the word. What it turns up, by way of
illustration and never as the set: a worker's `context_labels` variable or `case` block, a
reason string a human reads, a guard's own `case`, an issue form's `labels:` key that stamps
the label on every issue filed through it, the profile's `labels` section that
`.github/setup-labels.sh` writes to the repository, a one-off script that applies the label
when it files issues, a skill that names the labels it applies, `CLAUDE.md`'s **Model
selection** table, and the method documents that name a label in prose or in a heading. A hit
inside `.claude/skills/`, `.claude/agents/` or a worker prompt is the expensive kind: it is
read at run time, and a skill's **frontmatter `description`** is loaded on every run, so a
stale label there is both wrong and costly.

**The directory rule** exists because `docs/reference/work-types/<label>/` spells the label as
a **directory name** — so renaming a label means moving a directory, not editing a line, for
each label that has one. Every reference naming that directory breaks with the move, and
references reach it from outside the tree as well as within it, so this rule also reads the
whole repository:

```sh
git ls-files -z | xargs -0 grep -nE 'work-types/uc/'
```

Outside-the-tree hits written as a repo-rooted path — `docs/reference/work-types/uc/done.md`,
or the directory with its trailing slash — are gated: `check-method.py`'s check 2 resolves
link and path targets in every live file it walks, so that reference goes red on the rename
rather than dangling. What this grep is still for is the residue that check states it cannot
resolve, and the files it never opens. The residue in full: the snapshot trees it skips
(`docs/adl/**`, `docs/plans/**` and the two frozen ones); a bare path written without its root
segment (`work-types/uc/done.md`) that the check has no base to resolve; the directory written
without its trailing slash (`docs/reference/work-types/uc`), which the check skips because one
bare word cannot be told from a fragment of prose; a path named in prose with no backticks at
all, which nothing marks as a path; a reference written as an absolute
`github.com/<owner>/<repo>/blob/<ref>/…` URL, the shape `.github/ISSUE_TEMPLATE/adr.yml` uses;
every file outside the trees check 1 walks — the rest of `.github/`, `README.md`, `tests/**`,
`custom_components/**` — since this grep is `git ls-files`-wide and the check is not; and any
reference inside a fenced code block, which the check skips by design and which the two `sh`
fences in this very section are.

**The in-tree rule** covers what the directory rule cannot see: inside
`docs/reference/work-types/`, a label's directory is named without the `work-types/` prefix —
`../uc/done.md` from a sibling label, or plain `uc/done.md` from the tree's own `README.md`.
Both shapes:

```sh
grep -rnE '(\.\./)?uc/' docs/reference/work-types/
```

This is the one rule not read over the whole repository, and the argument for the narrowing —
rather than a list — is that the prefix-less spelling is only writable from inside the tree:
a path reaching a label's directory from anywhere else has to traverse `work-types`, so it
spells it and is the directory rule's already. The two together therefore still exclude no
file.

Every hit is a candidate, whether it is a markdown link or a bare path in prose, and in
**either** direction, since a label's directory is referred to as often as it refers out —
`uc/` and `requirement/` point at each other today, and `README.md` names three labels'
directories without a `../` anywhere. Renaming a label means fixing every hit naming it, on
every side.

**Two per-label sites are already checked rather than grepped for**, both by
`.github/check-method.py` against the profile's `work_types.enabled`: check 4, that each
enabled label's `docs/reference/work-types/<label>/` directory exists and is complete — which
is also what says which labels have a directory for the rule above to move — and check 3, that
the commit-prefix table of the document `CLAUDE.md`'s **Definition of Done** topic routes to
carries a row for it, one row per context label, with no directory moving for it. A label
added or renamed owes both, and the PR goes red rather than the obligation resting on someone
remembering to run a grep. They are the shape the rest of this section is reaching for, and
check 2's target resolution is the directory rule's half of it — mechanical because a path
either resolves or it does not. What stays a rule stated well is what needs judgment: the
name rule, which has to tell the label `workflow` from the English word, and the in-tree
rule, whose bare prefix-less `uc/done.md` names no tree the check can root it at (written as
a markdown link, `../uc/done.md` resolves against its own directory and is caught).

No count is stated in any of the three on purpose. A rule like these is a sync obligation — it
exists for the case where someone forgets to update a list — so a hand-maintained list inside
it is the defect it is meant to prevent, and it has drifted every time one has been tried,
in the scope of the rule as readily as in its results. The rules also survive the labels still
to migrate, each of which adds more such references.

What each is for: the name rule finds the prose and values a *rename* makes wrong, which no
path check can see; the directory and in-tree rules find the references a *directory
move* breaks, which is mechanical.

Two things the path rules deliberately over-report, so a rename executor does not chase them.
A reference that leaves the tree entirely (`../../../adl/…`) is unaffected by the move, even
where the path happens to contain a label word — `testing/overlays/home-assistant.md` links
`../../../../adl/0009-testing-strategy.md`, which the name rule hits on `testing` and which no
rename touches. And a reference that stays **inside** one label's own directory — between
`documentation/`'s two per-branch subdirectories, or from one of them back up to the file that
routed there — moves with the directory it sits in.

The shape of that tree — the roles a label's
directory holds, and the per-branch subdirectories a label whose work covers more than one
artifact gets — is [work-types/README.md](../work-types/README.md)'s; what belongs here is only
that the label is the directory name, so a rename moves a directory. Adding a label means
updating every place the three rules above turn up — **and** giving it a directory, which is
not optional: check 3 refuses a profile whose `labels.context` and `work_types.enabled` name
different sets, so a new context label is a new enabled work type, and check 4 then requires
its directory. What varies is only what the directory holds — a review checklist is the one
file always required, and `workflow`'s holds nothing else. Renaming a label additionally means
updating any form that stamps it. A
rename that misses `close-guard.yml` fails open silently — its `case` simply stops matching —
so that one is checked, not assumed.

All three workers read the table rather than carrying their own copy of the work-file and
checklist mappings — the drafter and the fix worker for the *How the work is done* column, the
reviewer for *How it is reviewed* — so the row is the selection itself rather than a mirror of
one kept in sync by hand. That is what makes changing what a label routes *to* cheap — one
cell in either *How* column — and changing the table's own shape expensive, since it now
reaches every worker at once.
Adding or renaming a label is a third thing again, and not cheap: run the three rules above.

The row is not the whole routing, though: the path map it carries is one of four enumerations
of one set, and adding a tree means editing all four. Which four, which of them is the source,
and how each omission would fail, are stated once — in the document `CLAUDE.md`'s **Model
selection** topic routes to, under **The path map is one of four enumerations of one set** —
and are not restated here; the check that holds the other three to the source is **The
watched-path check** below. What belongs here is only the two
that are this pipeline's own: `ai-pipeline.yml`'s path filter decides whether a job runs at
all, and `_ai-review.yml`'s diff enumeration decides which files a checklist can see.
`file-task-issue/SKILL.md` doesn't hold its own copy — it points at `CLAUDE.md`'s Issue
conventions, which forwards to [contribution-workflow.md](contribution-workflow.md).

The **action/state labels** (`needs-draft`, `needs-review`, `needs-work`, `needs-approval`,
`needs-decision`) are not context labels either. They are defined in exactly one place
the name rule above turns up — `.claude/profile.yml`'s `labels`. The same grep returns many more
hits, in retry comments and guidance text across the workers; those are prose telling a human
which trigger to add next, never a value a worker matches on, so a rename there is a wording
fix rather than a sync obligation. What binds instead is the set of
places that *match* or *apply* them: `ai-pipeline.yml`'s `if:` guards, which compare
`github.event.label.name` against a trigger label by string and — like `close-guard.yml`'s
`case` block above — fail open silently on a rename, every job simply never firing; `_ai-review.yml`'s
verdict routing (and `_ai-draft.yml`/`_ai-fix.yml` for the two trigger hand-offs); and, for
the two exit labels, the interactive lifecycle's two exits — reached through `CLAUDE.md`'s
**Contribution workflow** section, whose doc names in its **Exit labels** section the one step
that applies them — so a rename is checked there rather than assumed from here. On the CI side, `_ai-review.yml`'s verdict routing is the only place that applies
either. Adding or renaming one means updating that set, and the **Pipeline steps** below where
the label's meaning is stated.

The **kind-of-work labels** (`bug`, `enhancement`) are defined in `.claude/profile.yml`'s
`labels` and get no `docs/reference/work-types/<label>/` directory, which a kind label never
gets. They are not context labels
([contribution-workflow.md](contribution-workflow.md)'s **Issue conventions**), and no worker
matches on them — but "the profile and nowhere else" would be wrong, and was: run the same
greps for `bug` or `enhancement` and they turn up a skill naming the labels it applies, which
is a real hit and the expensive kind, since a skill's text is read at run time. What renaming
one does *not* touch is anything a worker branches on. `_ai-draft.yml` cannot see them, which
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

## The watched-path check

`.github/check-path-map.py` asks one question: do the three consumers of the watched-path set
still carry exactly the set the profile declares? `.claude/profile.yml`'s `review.path_map` is
the **source** — the only copy that says what a tree is *for*, and the only one a script can
read without parsing prose. It is the source of the *set*; routing still resolves from
`CLAUDE.md`'s Model selection table, which is what the review worker reads. The three consumers
are `ai-pipeline.yml`'s `on.pull_request.paths`, which
decides whether any job runs; `_ai-review.yml`'s `git diff … -- <paths>` enumeration, which
decides what a checklist can see; and `CLAUDE.md`'s no-label row, the human-readable authority.
`ci.yml`'s `method` job runs it, blocking, with its fixtures first;
`.github/hooks/pre-commit` runs it locally as a warning, for the same reason it warns rather
than blocks on the method check.

**It exists because a careful author was not enough.** The set was spelled four times by hand,
and a tree left out of one of them is invisible in exactly the way a tree nobody thought about
is — the review simply never looks there, and nothing goes red. A finding therefore names the
file, the enumeration inside it and the tree: "they disagree" is not something an author can
act on, and an author who has to re-derive which of four files is short is back where the check
found them.

**Verified, not generated — decided per consumer.** Deriving a consumer from the source is the
stronger shape in general, and it is not the shape any of these three take.

- `ai-pipeline.yml`'s path filter **cannot** be derived at run time: GitHub reads it to decide
  whether to start a job at all, so there is no run to generate it in. The alternative is a
  generated file checked in — which still needs this check, because a checked-in generated file
  can be hand-edited or left stale. Generation would therefore remove no failure mode, only add
  a generator and a did-you-run-it obligation.
- `_ai-review.yml`'s diff enumeration **could** be derived: a step could read the profile and
  emit the pathspec into the prompt. It is not, for a reason that is about trust rather than
  effort. The enumeration decides what the reviewer can see, and a PR that shrank the profile
  would then shrink its own review — the self-routing guard's concern, one file over. Deriving
  it safely means deriving it from the *base* commit's profile, which is a decision about that
  trust boundary and belongs with the ADR that records it, not with this check. Until then the
  hardcoded list is verified, and a PR that shrinks the profile fails here instead.
- `CLAUDE.md`'s row is prose. It interleaves the trees with the checklist each routes to and
  with the paragraph's own argument; generating it would trade the document people actually
  read for a block nobody may edit. It is verified, and that is the right shape for the only
  copy a human is meant to read.

**The translation is the check's, and it is why all three need parsing rather than comparing.**
Each consumer spells the same tree in its own grammar: an Actions path filter takes the
source's globs verbatim, a git pathspec names the directory (`docs/reference`, not
`docs/reference/**`), and `CLAUDE.md` pairs each tree with a work type. A consumer that spells
a tree in another consumer's grammar reports twice — once as the tree it is missing, once as
the one it carries — because "missing `src`" alone would read as a tree nobody has.

**An enumeration it cannot find exits 2, never 0.** A check that passes because it read nothing
is the failure this one exists to remove, so a missing path filter, a missing (or doubled)
`git diff` line, a `CLAUDE.md` without the map paragraph and an unparseable profile each fail
as an environment error rather than as agreement. The fixtures
(`.github/test-check-path-map.sh`) cover both verdicts and that one: a complete layout that
passes, one case per finding the check can report, and the exit-2 cases. They run before the
check itself in `ci.yml`, as every other check's here do.

The set's own agreement was the method check's until this check existed, for the two of the
four copies it could see. It is now one check's, whole — `.github/check-method.py` holds no
part of it, and says so at the line where it used to.

## The upstream-pin drift check

`.github/workflows/upstream-drift.yml` runs weekly and asks one question: does every
dependency the profile pins still match the upstream state it was pinned to? The pins are
`.claude/profile.yml`'s `dependencies` — the provenance manifest, one row per skill this
project did not write itself, each carrying the source repository, the path inside it, and a
`pin` recording the upstream state the copy was last reconciled with. The comparison is
`.github/check-upstream-drift.py`'s; the workflow only carries the answer to a human.

**It exists because nothing else fails.** A vendored skill whose upstream is revised keeps
working here, and the pin keeps asserting a reconciliation that is no longer true — the silent
drift class where a source moves, the local reading stays, and no gate notices. Every other
agreement in this repository is held by a check that runs on the change itself; this one has
no change to run on, because the change happens in someone else's repository.

**It never edits a skill and never edits the manifest.** These copies are adaptations, not
mirrors — several deliberately drop or invert upstream behaviour — so an upstream commit is a
question, not a patch. The workflow's token grants no write beyond opening and editing one
issue, so the property is enforced by what it *can* do rather than only by what its steps say.
It applies `workflow` and no other label: a scheduled job able to apply `needs-draft`,
`needs-review` or `needs-work` would spawn drafting or review work nobody asked for.

**One open report, updated in place.** The report is found by two conditions, each doing a
different job. A marker in the body — not the title and not the label, either of which a
maintainer may change while triaging it, and each of which would otherwise hide the open report
and open a second one. And the issue's **author**, because that marker is published: it sits in
this public repository, in the script and in every report, so without an author condition
anyone able to open an issue could paste it into one and become the report, and the job would
splice into a stranger's issue and never open the real one. A maintainer cannot change who
opened an issue, so constraining the author costs nothing the marker match was defending.

Only the region between the marker and its closing pair is the workflow's: a note a maintainer
adds around it survives the next run, which a wholesale body replacement would both destroy and
then read as a change every week afterwards. A body whose markers are missing, doubled or
reversed is **refused** rather than merged optimistically — each of those shapes destroys text
if it is guessed at, and refusing fails the run loudly instead. The body is rewritten only when
its content actually changed, compared on content rather than bytes — that is a weaker claim
than "when the set of rows changed", and deliberately so: a row already listed whose upstream
head has moved again is a real change to the report, though the set of rows did not move.
When it does rewrite, it also posts one short comment, because an edited body notifies nobody
— that comment is the whole of how a maintainer learns the report moved, which is why the
rewrite condition being right matters more than it looks. The workflow never closes it: the report ends when a human acts on it, and
the act is the same either way — **adopt the upstream change, or decide it does not apply, and
bump the pin in the PR that records the decision**. That PR closes the report through its own
`Closes` reference, which is what stops the row reappearing. A report closed without a pin
bump comes straight back on the next run, correctly.

Four verdicts, and the distinctions are the point. `current` and `drifted` are the ordinary
pair. `missing` — no commit upstream touches the path at all — is reported rather than passed,
under a heading of its own: a renamed or deleted path is the loudest kind of drift and
precisely what a naive sha comparison reads as "nothing changed", so it does not share a
section with the rows that are permanently unverifiable. `unresolvable` covers the rows pinned to a `sha256:`
content hash recorded by the marketplace installer: that hash is not reproducible here — a
locally computed sha256 of the same bytes does not match a lockfile hash even for a copy that
never diverged — so those rows can be neither confirmed nor refuted, and calling them
"drifted" would be a claim the check cannot support. They are reported as needing
reconciliation to a `commit:` pin, and repeat every run until they get one. A lookup that
*errors* is not a verdict at all: the run fails and writes nothing, rather than opening a
report whose rows are silently incomplete.

Decisions live in the script, and the workflow calls it and carries the answer to GitHub. That
is why: the splice and the did-anything-change comparison were inline shell in the job until a
review observed that the one piece of logic able to destroy a maintainer's writing was also the
one piece no fixture could reach. Logic in the job is logic no test covers, in a job nobody
watches.

One decision necessarily stays in the job — which issue *is* the report, since finding it means
querying GitHub — and it is the untested remainder the rule above would otherwise hide. It has
already been wrong once: the author condition was first written with the REST spelling of the
bot login against a call served from GraphQL, where the same actor is rendered differently, and
a condition that matches nothing does not fail but opens a fresh issue every week. The value
now in the file is the one `gh` actually returns for this repository's own bot-authored items,
read off a real query rather than reasoned from a doc.

The check's fixtures (`.github/test-check-upstream-drift.sh`) are offline by construction and
run twice: in `ci.yml`, so a PR that breaks the check fails on that PR, and again inside the
scheduled job, since a weekly job nobody watches is exactly where a broken check would rot.
`ci.yml` also runs the check itself in its `--validate` mode — parse the manifest, check every
pin's scheme, touch no network. That mode exists because one unreadable row aborts the whole
comparison and so takes every *other* row's verdict down with it; without a PR-time check, a
malformed row would ship green and surface only as a red scheduled run, in the job that
argument says nobody watches.

## Pipeline steps

- **Trigger**: a maintainer labels an issue `needs-draft` plus exactly one context label — a
  context label alone never triggers anything; only an *action* label (`needs-draft` on an
  issue; `needs-review`/`needs-work` on a PR) spawns an AI job. `workflow` and `documentation`
  are never auto-drafted, but they reach that outcome by different mechanisms and a maintainer
  sees the difference. `workflow` **is** in `_ai-draft.yml`'s `context_labels`, and its `case`
  arm refuses with a reason of its own: a drafted label is contained by an allow-list of the
  trees its drafts actually write — one tree for each doc label — and that list never reaches
  the files instructing future drafts, while a `workflow` change **is** those instructing files
  (`.github/`, `.claude/`, `CLAUDE.md`), so no allow-list can contain one. `documentation` is
  absent from that variable entirely, so it never reaches a `case` arm: a `documentation` issue
  is refused with *No context label found*, which is the wrong explanation and is why the label
  counts as not wired in yet rather than deliberately refused. Being in the variable also means
  `workflow` participates in the multiple-context-labels refusal, which `documentation` does
  not. A human authors both drafts by hand. The review step is still automated
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
  pass run interactively instead. If a checklist for it is ever written, the directory is added
  to `.claude/profile.yml`'s `review.path_map` and followed out into all three consumers — the
  watched-path check refuses any other order — and this bullet becomes the record of why it was
  absent.
- **Draft** (`_ai-draft.yml`, ≈ the **File the issue** and implement steps): resolves the model and branch
  (`<context-label>/<issue-number>`, [contribution-workflow.md](contribution-workflow.md)'s own
  scheme, or a label's own override per its **Branch naming** note) from the label. Its
  `max_turns` tier is driven by the issue's project-board **Size** field (set per
  [contribution-workflow.md](contribution-workflow.md)'s **Issue conventions**); a Size that is
  unset, unreadable or not one of the five tiers falls back to the M tier with a workflow
  warning rather than failing the run — Estimate is planning-only and isn't read by any
  workflow. `development`/`testing` additionally require a
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
