# ADR-0043: The upstream-drift watcher — a scheduled, issue-writing job over the profile's pin manifest

Date: 2026-09-16
Status: Accepted

## Context

This project does not write every skill it runs. Several under `.claude/skills/` were ported
from other repositories, and the stack packages were installed from a marketplace.
`.claude/profile.yml`'s `dependencies` is the provenance manifest for all of them: one row per
copy, carrying the source repository, the path inside it, and a `pin` recording the upstream
state the copy was last reconciled with.

Nothing holds that pin to the truth. A vendored copy whose upstream is revised keeps working
here unchanged, and the pin keeps asserting a reconciliation that stopped being true — the
silent-drift shape where a source moves, the local reading stays, and no gate notices. A pin
with no expiry is worse than no pin at all, because it reads as verified.

Five forces pull on whatever answers that.

- **There is no local change to hang a check on.** Every other agreement in this repository is
  held by a check that runs on the change itself. Here the change happens in someone else's
  repository, at a time nothing here causes.
- **An upstream commit is a question, not a patch.** These copies are adaptations rather than
  mirrors — several deliberately drop or invert upstream behaviour — so nothing that watches
  them may act on what it finds. Adopting an upstream change, or deciding it does not apply, is
  a judgement with a reason worth recording.
- **The label vocabulary drives an autonomous pipeline.** `needs-draft`, `needs-review` and
  `needs-work` start drafting, review and fix runs. A job able to apply one of them would be
  able to start work nobody asked for, and a job that fires on a clock would do it from a cron
  expression.
- **Not every pin can be answered.** Four of the sixteen rows carry a `sha256:` content hash
  recorded by the marketplace installer rather than a commit. That hash is not reproducible
  here — a locally computed sha256 of the same bytes does not match a lockfile hash even for a
  copy that never diverged — so those rows can be neither confirmed nor refuted by any
  comparison this repository can run.
- **A write grant that fires on a clock is a new trust boundary.** Every write-capable *job
  this repository authors* fires on an event a named human caused: a label a maintainer
  applied, a merge to `main`, a tag. A scheduled job has no human anywhere in its trigger, so
  its grant is the first this repository issues that is exercised without one. Dependabot is
  configured here and does run weekly, but it is the boundary's other side rather than a
  counter-example: its ability to write is GitHub's own service grant, not a token this
  repository hands to steps it wrote, and there is no job definition here whose permissions
  anyone could get wrong.

That last force is why this is a record rather than a PR description. The test/CI/dev-tooling
carve-out in `CLAUDE.md`'s **Architecture Decision Records (ADRs)** topic explicitly does not
reach the CI/automation pipeline's own structure — trust boundaries and job topology — and this
is both.

## Considered options

### Option A — Do nothing; reconcile when someone remembers

Keep the manifest as a record and check it by hand when a port is next touched.

- Pro: no new workflow, no new grant, no weekly run to keep green. The manifest still holds the
  provenance, which is most of its value: a human who goes looking can answer the question
  unaided.
- Con: nobody goes looking. This is precisely the silent-drift shape the manifest was written
  against, and leaving it unwatched turns every row into a claim with no expiry — which, as the
  Context says, is the failure mode that reads as success.

### Option B — Off-the-shelf dependency tooling (Dependabot)

Let an existing updater track the sources.

- Pro: maintained by someone else, nothing of ours to keep correct, and it already knows how to
  open and update one pull request per moved dependency.
- Con: it tracks package ecosystems and whole repositories, not an arbitrary path inside an
  unrelated repository — and a path is exactly the unit pinned here. Its output is also a
  patch, which is the shape the second force rules out. This is not a guess about an unadopted
  tool: Dependabot is already configured here for two ecosystems, and neither of them can be
  made to address a skill's directory in a repository this project does not depend on.

### Option C — Vendor upstream unmodified (submodule or subtree) and adapt in a layer on top

Track the upstream tree itself, so drift becomes a pointer comparison.

- Pro: no manifest and no comparison logic of our own; `git` answers the question, and the
  answer is exact rather than inferred from a commit listing.
- Con: there is no unmodified copy to track. These skills are forked in the file itself, not
  decorated from outside, so the vendored tree would be one nothing reads and the adaptation
  layer would have to restate each file whole. It buys an exact answer about a tree that is not
  the one running.

### Option D — A second manifest of its own, `.claude/skills/UPSTREAM.md`

Give the check a dedicated file, in prose, next to the skills it describes.

- Pro: provenance sits beside the artifacts it is about, readable without the profile's schema,
  and a machine-read file stays out of a file humans edit by hand.
- Con: `.claude/profile.yml`'s `dependencies` already is that manifest, and covers more — the
  stack packages, and the `installed: user` rows that are not under `.claude/skills/` at all. A
  second file is a second source of truth for the same fact with nothing holding the two in
  step, so the decision would create an in-repo instance of the very drift it is built to
  catch.

### Option E — A PR-time check rather than a scheduled job

Add the comparison to the checks `ci.yml` already runs.

- Pro: no new trigger class and no new grant — it would run under `contents: read` like its
  neighbours and report by failing a pull request a human is already reading.
- Con: it has nothing to run on. The event being watched for happens elsewhere, so a PR-time
  check fires only when this repository happens to change: it reddens an unrelated pull request
  over a state its author did not cause, checks the same pins twenty times on a busy day, and
  checks them not at all in a quiet month.
- What is rejected here is a PR-time check as *the watcher*, and only that. A PR-time check over
  something a pull request does change — whether the manifest still parses and every pin carries
  a known scheme — has a local change to run on and is not this option; the chosen option
  includes exactly that half, and the Decision says why it has to.

### Option F — Require a resolvable `commit:` pin for every row first

Convert or drop the four `sha256:` rows as a precondition, so every row is answerable.

- Pro: three verdicts instead of four, no row that repeats every week, and no verdict whose
  whole content is "this cannot be checked".
- Con: converting a `sha256:` row means finding the upstream commit that produced the installed
  bytes and recording a decision, per row — which is the reconciliation work the report exists
  to prompt. Making it a precondition blocks the check on the work the check was built to
  surface. Dropping the rows instead hides them: an unverifiable pin that is not listed is
  indistinguishable from a current one.

### Option G — A weekly scheduled job over the profile's manifest, reporting as one issue

A cron-triggered workflow reads `dependencies`, compares each pin with upstream, and opens or
updates a single issue. Its only write grant is `issues: write`; it applies `workflow` and no
other label; rows it cannot answer get a verdict of their own.

- Pro: the trigger matches what is watched — a clock, because nothing local causes the event.
  The write surface is one issue, so "never edits a skill, never edits the manifest" is
  enforced by what the token can do rather than only by what the steps say. One report, found
  by a marker in its body and by its author, updated in place, keeps a stale upstream from
  producing a weekly pile. And a row that cannot be answered says so instead of being called
  drifted.
- Con: it introduces the trigger class the fifth force describes, and a scheduled job nobody
  watches is exactly where a broken check rots unnoticed. It adds a comparison that has to stay
  correct against another repository's API, including one decision — which issue *is* the
  report — that lives in the job rather than in the tested script, because answering it means
  querying GitHub.

## Decision

**Option G.**

Option A is rejected on the Context's opening claim rather than on effort: an unwatched pin is
not a neutral record but a false one, and the manifest already existed by the time this was
decided. Options B and C both fail on the unit: Dependabot cannot address a path inside an
unrelated repository, and a submodule can address only a tree this project does not run,
because the second force's adaptations are in the files themselves. Option D's placement
argument is real, but it pays for it with a second source of truth for one fact — and the
profile's manifest covers rows a skills-directory file could not.

Option E is the one that would have cost nothing new, and it is rejected on the first force
alone: a check with no change to run on does not become one by being attached to an unrelated
change. Option F's tidier verdict set is rejected on its own Con — it makes the check wait for
the work the check exists to request.

Option G's cost is accepted as the price of watching the one thing here that nothing else can
watch, and it is paid down where it can be — by taking the half of Option E that Option E's own
Con does not reject. The check's fixtures are offline and run both at PR time and inside the
scheduled job, and the check's parse-only `--validate` mode runs on every pull request. Both
have a local change to run on, which is the whole of what Option E lacked: the fixtures answer
to the check's own source, and `--validate` to the manifest, and a pull request changes each of
those. `--validate` earns its place because one unreadable row aborts the comparison and takes
every other row's verdict with it, so a malformed row must not be able to ship green and
surface a week later in the job the Con above says nobody watches.

Three properties follow from the reasoning above rather than being separate choices, and are
recorded because each was reached by discarding a working alternative.

- **The write surface is how the second force is enforced, not how it is described.** The job
  is granted `issues: write` and nothing else — no `contents: write`, no
  `pull-requests: write`. A steps-only promise not to edit a skill is a promise a future step
  can break silently; a grant that does not exist cannot be used by a step nobody reviewed.
- **It applies `workflow` and no other label.** The third force makes `needs-draft`,
  `needs-review` and `needs-work` unavailable to anything on a schedule, and the general rule
  is the narrower one: a clock-fired job may report, and may not dispatch.
- **The report is identified by a marker in its body *and* by its author.** The marker, not the
  title or the label, because a maintainer triaging the report may change either and each
  change would otherwise hide it and open a second. The author as well, because the marker is
  published in a public repository: without an author condition, anyone able to open an issue
  could paste it in and become the report, and the job would splice into a stranger's issue
  while never opening the real one. Who opened an issue is the one property a maintainer cannot
  change.

What the job does with the answer, verdict by verdict — including how a report is closed and
why the rewrite condition is content-based — is
`docs/reference/method/ci-pipeline.md`'s **The upstream-pin drift check**, which this record
does not restate.

## Consequences

**Easier.** A pin now carries an expiry: a row that stops matching upstream becomes a question
addressed to a human within a week, rather than a claim nobody re-reads. Bumping a pin becomes
the act that closes a report, which gives every adoption or non-adoption decision a place to be
written down — the pull request that bumps it.

**Harder.** Vendoring anything new now carries an obligation: a copy with no manifest row is
watched by nothing. That obligation is written down — `docs/reference/method/ai-authoring.md`'s
**Vendored skills are forked on purpose** states it, and states that answering a report means
bumping the pin either way — but nothing mechanical refuses an undeclared copy, so the
obligation is met by an author who knows it or not at all. A row whose pin scheme cannot be
parsed aborts the comparison for every other row, which is why the parse-only mode runs at PR
time. And the weekly job itself is now a thing that can break quietly — the cost the Decision's
last paragraph pays down rather than removes.

**Forecloses.** An automatic re-sync of a vendored copy. This record makes adoption a human
decision recorded in the pull request that bumps the pin, so a later change that wants the
watcher to open a pull request instead of an issue is re-opening this decision, not
implementing it.

**Standing constraint on future scheduled automation.** A later job that needs a write grant on
a schedule inherits this record's shape — a token scoped to the one artifact it writes, no
`needs-*` label, one artifact updated in place rather than a stream of new ones — or supersedes
this record to say why its case differs.

**Follow-up this creates.** The four `sha256:` rows each want reconciling to a `commit:` pin,
one decision per row; the report asks for exactly that every run until they get it. That work
is deliberately not a precondition here, per Option F.

**Blast radius.**

1. **Search.**

   ```
   rg -n -e 'schedule:' \
         -e '^[[:space:]]*(contents|issues|pull-requests|actions|checks|packages|statuses|deployments|discussions|security-events|id-token):[[:space:]]*write' \
         -e 'WORKFLOW_PAT' \
         .github
   ```

   …plus eight sites listed explicitly in the table below. This is a **hybrid** of the
   template's two forms, for the reason the template's width test demands: neither form alone
   reaches everything this decision governs.

   The pattern is three arms, and each is load-bearing. **`schedule:`** finds the trigger class
   this decision introduces — but on its own it returns two files, the new job and Dependabot's
   configuration, which says nothing about the write grants the decision has to be weighed
   against. **The permission keys** find every write grant, not only
   `issues: write`: a pattern on the new job's own grant would drop precisely the neighbours
   this decision has to be weighed against. **`WORKFLOW_PAT`** is the arm a permissions-only
   pattern would miss entirely — a reusable workflow declares no `permissions:` of its own,
   inheriting the caller's, and a personal access token is a write-capable credential expressed
   as no permission key at all. Without that arm the three `_ai-*.yml` workers — where most of
   this repository's automated writing actually happens — do not appear at all.

   The path is `.github` rather than `.github/workflows`, and the difference is one file:
   `.github/dependabot.yml`, which the first arm returns and which is weekly clock-triggered
   automation that opens pull requests here. Narrowing to the workflows directory would have
   dropped the one configured automation this decision's own Option B is about — width failure
   arrived at by path rather than by pattern.

   What no widening of *either* reaches is a site the decision governs without being
   clock-triggered or write-capable itself, because those are the only two things the pattern
   knows how to recognise. Four categories fall there, eight files in all, and they are listed
   rather than searched for:

   - **A workflow that merely invokes the check**, under read-only permissions and on no
     schedule — `ci.yml`. It is inside the search path and returns nothing, which is exactly the
     miss: a pattern keyed on triggers, permission keys and a PAT name cannot see a `run:` line.
   - **The check's own scripts and fixtures**, which carry every verdict but no workflow syntax.
   - **The manifest the check reads**, which is YAML of an unrelated shape.
   - **The prose that states what this decision obliges** — three documents, none of which
     names a permission key or a cron expression.

   One consequence worth stating: `docs/adl/` is outside the path, so this record is not a hit of
   its own search and needs no self-row.

   The search returns **8 files**; with the eight listed sites, **16** are enumerated — **13** in
   the table below and **3** out of scope under 3.

   Two workflows are genuine non-sites rather than misses: `close-guard.yml` and `coverage.yml`
   return nothing for the pattern *and* invoke nothing of this decision's — they declare
   `contents: read` with read-only job scopes, hold no PAT, run on no schedule, and neither
   mentions the drift check. `ci.yml` looks like a third of them and is not one, which is why it
   is listed above rather than dismissed here.

2. **Per-hit verdict** (every hit appears here or in 3; the eight explicitly listed sites are
   marked *listed*).

| Site | What it does today | Verdict |
| --- | --- | --- |
| `.github/workflows/upstream-drift.yml` | Weekly cron plus `workflow_dispatch`; `contents: read` at the top, re-declared on its one job, which adds `issues: write` and nothing else; opens or splices a single report and applies `workflow` | Conforms — the site this record decides |
| `.github/workflows/ci.yml` *(listed)* | Runs the check's fixtures and its parse-only `--validate` mode at PR time, under `contents: read`, on no schedule | Conforms — it is where the Decision's "paid down where it can be" half actually runs; a `run:` line is invisible to the pattern, which is why it is listed |
| `.github/check-upstream-drift.py`, `.github/check-upstream-drift.sh` *(listed)* | Hold the comparison, the four verdicts, the marker pair and the splice; the workflow calls them and carries the answer to GitHub | Conform — keeping the logic that can destroy a maintainer's writing where fixtures reach it is this decision's own shape |
| `.github/test-check-upstream-drift.sh` *(listed)* | The check's fixtures; offline by construction, run at PR time and again inside the scheduled job | Conforms |
| `.claude/profile.yml` *(listed)* | Carries `dependencies`, now machine-read: 12 `commit:` rows and 4 `sha256:` rows | **Does not conform in those four rows** — each is reported `unresolvable` every run until reconciled to a `commit:` pin, which is the follow-up above; the manifest and its 12 other rows conform |
| `docs/reference/method/ci-pipeline.md` *(listed)* | States why the job exists, what it may not do, the four verdicts, and how a report is closed | Conforms — it is where the operational detail lives, which is why this record cites rather than repeats it |
| `docs/reference/method/ai-authoring.md`, **Vendored skills are forked on purpose** *(listed)* | States the two standing obligations this decision creates: a copy brought in from outside gets its `dependencies` row in the same PR or it is left out of the check, and a drift report is answered by bumping the pin whichever way the decision went | Conforms — and it routes to the CI document for the watcher itself rather than restating it |
| `docs/reference/profile.md`, **Dependencies** *(listed)* | Describes `dependencies` as the provenance manifest and states that a pin moves only by a decision recorded in the PR that moves it | Conforms — the same rule this record's Consequences reach from the watcher's side |
| `.github/workflows/ai-pipeline.yml` | The autonomous pipeline's entry: `contents`/`issues`/`pull-requests: write` per calling job, every job gated on a `labeled` event whose sender is a named maintainer | Conforms — a human is in its trigger, the property the scheduled job cannot have and compensates for by writing no label that dispatches |
| `.github/workflows/_ai-draft.yml`, `_ai-fix.yml`, `_ai-review.yml` | Reusable workers. None declares a write grant of its own: the first two declare no `permissions:` at all and inherit the caller's, and `_ai-review.yml` declares only `contents: read` on its `skill-scan` job. All three use `WORKFLOW_PAT` where a label must trigger the next job and for Projects reads | Conform — same trigger property as their caller; named here because the PAT is a write surface no permission key shows |

3. **Out of scope** (3 files):

   `.github/dependabot.yml` — weekly ecosystem updates for GitHub Actions and pip, opened as
   pull requests and merged only by the manual approval every PR here needs. It is on the other
   side of this decision's boundary rather than governed by it: nothing in this repository
   issues it a token or writes its steps, so the standing constraint above — a token scoped to
   the one artifact written, no `needs-*` label, one artifact updated in place — has nothing
   here to bind. It keeps doing exactly that, and this record neither extends to it nor argues
   its stream of pull requests should become one issue.

   `.github/workflows/release-please.yml` and `.github/workflows/release.yml` — release
   automation, whose `contents: write` (and `pull-requests: write`) exists to publish this
   repository's own artifacts on a merge to `main` and on a tag. They watch nothing external,
   touch none of the label vocabulary, and fire on an event a human caused; they keep doing
   exactly that, and this decision changes nothing about them.
