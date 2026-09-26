# CI: the lifecycle as jobs, and the repository's own checks

Two things live here. First, how [contribution-workflow.md](contribution-workflow.md)'s
lifecycle runs when CI, not an interactive session, is the actor: a shape, with no
implementation. A project may run the whole lifecycle in interactive sessions and no CI job at
all. Second, the regular CI checks whose reasons this document owns: label vocabulary sync, the
docs-only close guard, the watched-path check and the upstream-pin drift check.

## The lifecycle as CI jobs

The lifecycle's steps are the same ones in CI. Only who takes each step changes, and so does
how a step is started.

**One trigger label per step.** A label starts each job:
- a **drafting** label, on an issue, starts the job that drafts it into a PR;
- a **review** label, on a PR, starts the job that reviews it;
- a **fix** label, on a PR, starts the job that addresses the posted findings.

A context label alone starts nothing. It selects the row of `CLAUDE.md`'s **Model selection**
table that the job follows, and a job reads that row rather than keeping its own copy of it.
A trigger label is applied by a human, as the go-signal, or by the job before it, as the
hand-off to the next step. A session that takes a step itself has no reason to apply the step's
trigger, and doing so would start a second actor on the same work.

**Each job does one task.**
- Drafting drafts the artifact, opens the PR and hands it to review.
- Review applies the checklists the row and the changed paths select, posts its findings and
  ends in a verdict: clean, or remarks.
- Fix addresses the posted findings, commits, and hands the PR back to review.

A review never commits a fix, and a fix never reviews its own output. That is the author/reviewer
separation of [contribution-workflow.md](contribution-workflow.md)'s **Rule A**, kept across
jobs: the job that wrote a change is never the one that judges it.

**Review and fix loop to a cap.** A remarks verdict starts fix, and fix starts review again. The
loop stops at a clean verdict or at a cap on automatic fix cycles. The cap is needed because no
one watches the loop run, so a finding the fix job cannot resolve would otherwise spend cycles
without end. It counts CI's own cycles only.
[contribution-workflow.md](contribution-workflow.md)'s **Rounds and the cap** counts the
interactive session's rounds, and neither count bounds the other.

**`needs-approval` hands the PR to the human.** Both ways out of the loop end the same way:
- a clean verdict applies `needs-approval`;
- reaching the cap applies `needs-approval` and `needs-decision`.

Both labels keep the meanings [contribution-workflow.md](contribution-workflow.md)'s **Exit
labels** gives them. From there a human merges the PR as it stands, or grants CI one more cycle
by applying the fix label again. The merge is always a human act, whichever actor drafted or
reviewed the PR.

**What the shape leaves to the project running it.** It sets no bot identity, no permission a
job holds, and nothing about what a job may commit or trust. A job acts on issue and PR text
that anyone can write, so these are decisions, and the project that adopts CI records them for
itself.

## Label vocabulary sync

The context-label vocabulary itself (values and meanings) is documented once, in
[contribution-workflow.md](contribution-workflow.md)'s **Issue conventions**. What lives here
is the consistency obligation: the same vocabulary is baked in wherever a script, a form or an
instruction to a future run names a label, and all of those must move together. Three rules
find them, and **no rule's scope is a list**: two read the whole repository, and the third is
narrowed by an argument rather than an enumeration — stated where it is given, so it can be
checked. That matters because a scope enumerated by hand is the same defect these rules exist
to catch: a file that applies a label sits outside a hand-kept list for as long as nobody
remembers to add it.

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
illustration and never as the set: a reason string a human reads, a guard's own `case`, an
issue form's `labels:` key that stamps the label on every issue filed through it, the profile's
`labels` section that `.github/setup-labels.sh` writes to the repository, a skill that names
the labels it applies, `CLAUDE.md`'s **Model selection** table, and the method documents that
name a label in prose or in a heading. A hit inside `.claude/skills/` or `.claude/agents/` is
the expensive kind: it is read at run time, and a skill's **frontmatter `description`** is
loaded on every run, so a stale label there is both wrong and costly.

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

`file-task-issue/SKILL.md` doesn't hold its own copy of the vocabulary — it points at
`CLAUDE.md`'s Issue conventions, which forwards to
[contribution-workflow.md](contribution-workflow.md).

The **exit labels** (`needs-approval`, `needs-decision`) are not context labels either. They
are defined in exactly one place the name rule above turns up — `.claude/profile.yml`'s
`labels`. The same grep returns more hits, in guidance text telling a human what a label means;
a rename there is a wording fix rather than a sync obligation. What binds instead is the place
that *applies* them: the lifecycle's two exits, reached through `CLAUDE.md`'s **Contribution
workflow** section, whose doc names in its **Exit labels** section the one step that applies
them — so a rename is checked there rather than assumed from here.

The **kind-of-work labels** (`bug`, `enhancement`) are defined in `.claude/profile.yml`'s
`labels` and get no `docs/reference/work-types/<label>/` directory, which a kind label never
gets. They are not context labels
([contribution-workflow.md](contribution-workflow.md)'s **Issue conventions**) — but "the
profile and nowhere else" would be wrong, and was: run the same greps for `bug` or
`enhancement` and they turn up a skill naming the labels it applies, which is a real hit and
the expensive kind, since a skill's text is read at run time. What a kind label *does* reach
is the doc side: [contribution-workflow.md](contribution-workflow.md)'s
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

It is deliberately a status check rather than a review checklist item: a checklist item is a
reviewer's judgement on the PR, and gates no merge. It is equally deliberately not a job in
`ci.yml`, where the project's other required
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
It applies `workflow` and no other label: a scheduled job that applied a label able to start
work would start work nobody asked for.

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
