# Tracker mechanics

The concrete commands for driving this project's tracker — GitHub issues, pull requests,
review threads, labels, and the project board — in one place, so no artifact has to
re-derive them and no agent has to rediscover the failure modes below the hard way.

**Mechanics only: the how, never the when or the why.** Which work gets an issue, what a
label means, when a PR is opened, when `needs-approval` goes on — all of that belongs to
[contribution-workflow.md](contribution-workflow.md) (the lifecycle),
[idea-to-issues.md](idea-to-issues.md) (the stages either side of it) and
[ci-pipeline.md](ci-pipeline.md) (the label-driven automation). This file assumes the
decision is already made and answers only "what do I type".

Throughout, the project's own values — repository, board, field and option ids — are **never
spelled here**. They are `.claude/profile.yml`'s (`repo`, `board`), and the recipes name them
as shell variables; set those once per shell with

```sh
eval "$(bash .github/profile-env.sh)"
```

which prints `OWNER`, `REPO_NAME`, `REPO` (`owner/name`), `BOARD`, `PROJECT_ID`,
`SIZE_FIELD`, `ESTIMATE_FIELD`, `STATUS_FIELD`, one `SIZE_<tier>` per Size option and one
`STATUS_<Column>` per Status column (`STATUS_In_progress`), every value read from the
profile. Then `echo "$REPO"` — the helper prints nothing when it fails, `eval` of nothing
succeeds, and the first recipe pasted with an unset `$REPO` misfires silently
(`gh issue create --repo --title …` reads the title as the repo). An empty echo means fix the
helper first. What those values mean on this project is [profile.md](profile.md).

Every recipe below was run against this project on `gh` 2.95 rather than transcribed from
memory: the reads in the variable form written here, the writes with the same values spelled
out literally before the variables replaced them — the substitution is textual, so a recipe
that ran with the value runs with the variable — **except where a recipe says otherwise about
itself**. Re-run one before trusting it if `gh` has moved on.

## The one rule: read the state back

`gh` reaches GitHub over **two transports**, and they fail independently:

| Transport | Used by |
|---|---|
| **GraphQL** | `gh issue create/edit/view/list`, `gh pr create/edit/view/comment`, `gh issue comment`, every `gh project *` subcommand, all review-thread resolution |
| **REST** | everything reached through `gh api <path>` without the `graphql` endpoint |

GitHub's **secondary (abuse) rate limiter** trips on a burst of GraphQL mutations — a couple
of review rounds' worth of thread replies and resolutions is enough — and then blocks the
whole GraphQL column **while REST keeps working**. `gh api rate_limit` does not surface the
secondary limiter: it happily reports 5000/5000 remaining on every bucket while `gh project`
and `gh pr edit` refuse. **The check is to retry the call you actually need and read its
result back, not to consult any meter.** A cheap GraphQL *read* such as
`gh api graphql -f query='{viewer{login}}'` is only a second meter: it can pass while the
mutation path is still refused, so a green probe is evidence of nothing. Use it to tell a
network failure from a refusal, never to decide a write is safe.

Worse, some of these fail *quietly enough to look like success*. `gh pr edit --add-label`
has reported success while applying nothing, repeatedly. So:

> **Never trust a write command's exit status. Read the resulting state back — and prefer a
> REST read for the read-back, so a blocked GraphQL path cannot make a failed write look
> confirmed.**

Every recipe below therefore comes with its read-back, and with a REST fallback where one
exists. Two operations have **no** REST equivalent and can only be waited out:
`gh project item-add` / `item-edit` (board fields) and `resolveReviewThread`.

**Recovering from a refusal.** Two behaviours seen on 2026-09-08 with the limiter tripped.
Unlike every other recipe in this file they are **reported, not re-executed**: deliberately
re-tripping the limiter would block whatever else is running against this repo, so neither
was re-verified when it was written down.

- *The wait is minutes.* The block lifted after roughly **nine minutes**. Retry the call you
  actually need on a 60-second loop rather than parking the work for an hour.
- *A write can land while its read-back is still refused.* A `gh project item-edit` returned
  success and the `item-list` meant to confirm it was refused in the same minute — the board
  pair above, where neither half has a REST fallback to drop to, so the refusal caught the
  read rather than the write. That is the one state the read-back rule leaves open.
  **Retry the read; do not retry the write.** A board-field edit is idempotent and a blind
  retry of it is merely wasted, but the same middle state reaches writes that are not — a
  comment, a review reply, a sub-issue edge — where the retry posts a duplicate. One rule
  covers both: establish what landed before writing again.

## Filing a work item

`gh issue create` cannot set project-board fields. It is always two steps: create, then add
the item to the board and edit its fields by raw node id.

```sh
# 1. create (see the Windows note below for why the body is a file)
gh issue create --repo $REPO \
  --title "<title>" --body-file <path> --label <context-label>

# 2. put it on the board; item-add prints the item id you then edit
gh project item-add $BOARD --owner $OWNER --url <issue-url> --format json
```

```sh
# 3. set the fields, one call each, by node id
gh project item-edit --project-id $PROJECT_ID --id <item-id> \
  --field-id $SIZE_FIELD --single-select-option-id $SIZE_M                # Size = M
gh project item-edit --project-id $PROJECT_ID --id <item-id> \
  --field-id $ESTIMATE_FIELD --number 3                                  # Estimate = 3
gh project item-edit --project-id $PROJECT_ID --id <item-id> \
  --field-id $STATUS_FIELD --single-select-option-id $STATUS_<Column>    # Status = <Column>
```

`--number` is right for Estimate and `--single-select-option-id` for Size and Status: Estimate
is a plain number field, not a single-select.

The project id, the three field ids and every option id are `profile.yml`'s `board` section —
`board.project_id`, `board.fields.<size|estimate|status>.id`, and
`board.fields.<size|status>.options`, which is where `$SIZE_M` and `$STATUS_<Column>` above
come from (`profile-env.sh` emits one variable per option, spaces in a column name becoming
underscores; which column the chain wants at each step is the contribution workflow's
**Project board**). Re-derive them with
`gh project field-list $BOARD --owner $OWNER --format json` if an edit is rejected — they are
stable in practice but not guaranteed — and fix them in the profile, the only place they are
spelled.

**Read-back — and the `--limit` trap.** `gh project item-list` defaults to **30** items, and
the board is far past that. A lookup under the default limit returns *empty rather than
erroring*, so a missing id reads as "the issue is not on the board" when it simply was not in
the page. Always pass an explicit high limit:

```sh
gh project item-list $BOARD --owner $OWNER --format json --limit 1000 \
  --jq '.items[] | select(.content.number==<n>) | {id, size, estimate, status}'
```

**REST fallback for the creation step** (the board steps have none):

```sh
gh api -X POST repos/$REPO/issues --input <payload.json>
```

with `{"title": …, "body": …, "labels": [ … ]}`. Using `--input` also keeps the body's UTF-8
intact.

## Rewriting a work item's body

`gh issue edit --body-file` is GraphQL and inherits the silent-failure warning above, so the
REST form is the one to reach for:

```sh
gh api -X PATCH repos/$REPO/issues/<n> \
  -F body=@<path> --jq '.body'
```

The body goes in a file, not inline, for the reason *Windows and Git Bash* below gives — and
`-F body=@<path>` reads the markdown as-is, where `--input <payload.json>` would mean
hand-escaping it into JSON first. Reach for `--input` here only when the same call is also
setting `title`, `state` or `labels`. `--jq '.body'` on the PATCH prints the stored body, so
the call is its own read-back; the independent one is
`gh api repos/$REPO/issues/<n> --jq '.body'`.

## Finding a work item by its body text

`gh search issues` **rejects `--state all`** — `invalid argument "all" for "--state" flag:
valid values are {open|closed}`. To search across both states, search from the list command
instead, which accepts `all` and takes the same query qualifiers:

```sh
gh issue list --repo $REPO --state all \
  --search "<query> in:body" --limit 100 --json number,state,title
```

`--limit` is not optional, for the reason *Filing a work item*'s `--limit` trap above gives:
the default is 30 and the overflow is silent.

`gh issue list` is GraphQL, so it is refusable. The REST fallback is the search API itself,
where the state is a query qualifier rather than a flag and so is not constrained the way
`gh search issues` is:

```sh
gh api -X GET search/issues -f per_page=100 --paginate \
  -f q="repo:$REPO <query> in:body" \
  --jq '.items[] | "\(.number) \(.state) \(.title)"'
```

`per_page` and `--paginate` are as mandatory here as `--limit` is above, and less obviously so:
without them this repo's `workflow in:title` search returned 30 items against a `total_count`
of 89, and a body-text lookup is exactly where a short page reads as "no such issue exists".

`<query>` is the one piece of free text in either recipe, and it goes through the shell in
both. Pick a distinctive substring that has no apostrophe or em-dash in it rather than pasting
a phrase out of an issue — see *Windows and Git Bash* below for what the shell does to those.

## Parent/sub-issue and blocked-by edges

That an epic's membership and ordering use these relationships rather than body text is
[contribution-workflow.md](contribution-workflow.md)'s **Issue conventions**. `gh` supports
both directly. At filing time:

```sh
gh issue create --repo $REPO … \
  --parent <epic-number> --blocked-by <issue-number>
```

Afterwards:

```sh
gh issue edit <epic>  --repo $REPO --add-sub-issue <child>
gh issue edit <child> --repo $REPO --add-blocked-by <issue>
```

Read-back. `gh issue view --json parent,blockedBy` nests the dependency list one level deeper
than the flag name suggests — it is `.blockedBy.nodes[]`, not `.blockedBy[]`, and a `jq`
expression written the obvious way fails with *expected an object but got: array*:

```sh
gh issue view <n> --repo $REPO \
  --json parent,blockedBy --jq '{parent: .parent.number, blockedBy: [.blockedBy.nodes[].number]}'
```

REST fallbacks — and their read-backs are the better read-back for the `gh issue edit` path
above too, since a GraphQL read cannot confirm a GraphQL write that the limiter may have
swallowed. Both writes take the sub-issue's / blocker's **database id**, not its issue
number:

```sh
sid=$(gh api repos/$REPO/issues/<child> --jq .id)
gh api -X POST repos/$REPO/issues/<epic>/sub_issues -F sub_issue_id=$sid
gh api repos/$REPO/issues/<epic>/sub_issues --jq '[.[].number]'

bid=$(gh api repos/$REPO/issues/<blocker> --jq .id)
gh api -X POST repos/$REPO/issues/<n>/dependencies/blocked_by -F issue_id=$bid
gh api repos/$REPO/issues/<n>/dependencies/blocked_by --jq '[.[].number]'
```

## Commenting on a work item

```sh
gh issue comment <n> --repo $REPO --body-file <path>
gh pr comment    <n> --repo $REPO --body-file <path>
```

One REST fallback serves both — for the comments API a PR *is* an issue, so the `issues` path
is correct for a PR number too:

```sh
gh api -X POST repos/$REPO/issues/<n>/comments \
  -F body=@<path>
```

Read back with:

```sh
gh api repos/$REPO/issues/<n>/comments \
  --paginate --jq '.[].body' | tail -1
```

`--paginate` is not optional here. A bare `--jq '.[-1].body'` returns the last item of the
**first 30-item page**, which on any busy issue or PR is not the newest comment — the same
trap as `item-list`'s default limit above, and just as silent. The same applies to every
listing read-back in this file.

Two `gh api` traps that bite on these read-backs: **`-f` makes the request a POST**, so a
query parameter on a GET needs `-X GET -f per_page=100` or a literal `?per_page=100` in the
path — plain `-f` turns the read into a write attempt and comes back `422 "body" wasn't
supplied`. And `--paginate` applies `--jq` per page, so the filter must emit a stream
(`.[].body`) rather than index into one page.

## Applying a label

```sh
gh issue edit <n> --repo $REPO --add-label <label>
gh pr edit   <n> --repo $REPO --add-label <label>
```

These are the GraphQL commands that **fail silently** under the secondary limiter, so the
read-back is not optional:

```sh
gh api repos/$REPO/issues/<n> --jq '[.labels[].name]'
```

Removing one is the same command with `--remove-label <label>`. It exits 0 and prints the PR
URL whether or not the label was present, so it is safe on the common path where it is
absent — and, like every `gh pr edit`, it needs the read-back above to prove anything.

(An issue path serves a PR too — a PR is an issue for the labels API.) REST fallback, which
returns the resulting label set directly, so it is its own read-back — except that the
`DELETE` returns **404 `Label does not exist`** when the label is absent, so a caller that
does not know whether it is on must treat 404 as success:

```sh
gh api -X POST   repos/$REPO/issues/<n>/labels -f "labels[]=<label>" --jq '[.[].name]'
gh api -X DELETE repos/$REPO/issues/<n>/labels/<label>               --jq '[.[].name]'
```

These recipes apply an existing label; they never create or rename one. Which labels exist
and what they mean is [contribution-workflow.md](contribution-workflow.md)'s **Issue
conventions**, and the places that vocabulary is baked into are
[ci-pipeline.md](ci-pipeline.md)'s **Label vocabulary sync**.

## Opening a change request

```sh
gh pr create --repo $REPO \
  --base main --head <branch> --title "<title>" --body-file <path>
```

`gh pr create` is itself GraphQL and can be refused while REST is fine. The fallback creates
the same PR:

```sh
gh api -X POST repos/$REPO/pulls \
  -f title='<title>' -f head='<branch>' -f base=main -F body=@<path> --jq '.html_url'
```

Read back with:

```sh
gh api repos/$REPO/pulls/<n> \
  --jq '{state, base: .base.ref, head: .head.ref}'
```

## Reading a change request's merge state

`state` cannot tell a merged PR from one closed without merging — REST reports `closed` for
both. The fields that decide it are `merged` and `merged_at`:

```sh
gh api repos/$REPO/pulls/<n> \
  --jq '{state, merged, merged_at}'
```

A merged PR reads `{"state":"closed","merged":true,"merged_at":"<timestamp>"}`; anything else
is not merged, whatever its `state`. This is a REST read, so it is not refusable by the
GraphQL limiter; `gh pr view <n> --json state,mergedAt` is the GraphQL form of the same read
and offers nothing over it.

The paths a change request touched — what a landed-check has to verify one by one — come from
the same API, not from a local diff, since the worktree that made the change may be gone by
the time anyone asks:

```sh
gh api repos/$REPO/pulls/<n>/files \
  --paginate --jq '.[].filename'
```

`--paginate` is not optional, for the reason *Commenting* above gives: a bare read returns the
first 30 files, and a large change is exactly where a short page reads as "every path
verified". Like the merge-state read above it is REST, so the GraphQL limiter cannot refuse
it. A deleted path is listed like any other; the read says nothing about *how* a path changed,
only that it did — `.[].status` carries `added`/`removed`/`modified` if a caller needs to tell
them apart.

## Reading a change request's label events and its review/comment timeline

The contribution workflow's round count and its exit-label rules both turn on one question —
was a human's review or comment posted while an exit label was on? — and neither the reviews
listing nor the comments listing can answer it: they carry no label state. The label timeline
does. It is REST, so the GraphQL limiter cannot refuse it, and an issue path serves a PR too:

```sh
gh api repos/$REPO/issues/<n>/events \
  --paginate --jq '.[] | select(.event=="labeled" or .event=="unlabeled") | {event, label: .label.name, at: .created_at, by: .actor.login}'
```

Each line is one label change, oldest first:
`{"event":"labeled","label":"needs-approval","at":"<timestamp>","by":"<login>"}`. A label was
**on** at a given moment when its most recent event before that moment is `labeled`.

The other side of the comparison is every review, every issue comment and every review-thread
reply, with author and time — as a stream, not the post read-backs elsewhere in this file,
which keep only the latest item by design:

```sh
gh api repos/$REPO/pulls/<n>/reviews \
  --paginate --jq '.[] | {id, user: .user.login, at: .submitted_at, body}'
gh api repos/$REPO/issues/<n>/comments \
  --paginate --jq '.[] | {id, user: .user.login, at: .created_at, body}'
gh api repos/$REPO/pulls/<n>/comments \
  --paginate --jq '.[] | {id, user: .user.login, at: .created_at, body}'
```

The third stream is the inline review-thread replies — where a maintainer most often disputes
mid-loop, and where the session's own `ai-fix-ack` replies live, so the marker test applies to
it as to the other two. `--paginate` is mandatory for the reason *Commenting* above gives, and the filter must stream
(`.[] | …`) rather than index into one page. A bot's login ends in `[bot]`; timestamps are
ISO 8601 in UTC and compare correctly as strings.

## Posting a review with inline anchors

The review **payload** — what goes in the body, how findings are grouped, the anchoring rules
and the CI verdict marker — is owned by the `submit-pr-review` skill and is not restated here.
The transport is:

```sh
gh api repos/$REPO/pulls/<n>/reviews --input <payload.json>
```

`--input` is mandatory rather than convenient: the payload is JSON with markdown inside it,
and building it inline mangles exactly the characters review findings are full of. Read back
with:

```sh
gh api repos/$REPO/pulls/<n>/reviews \
  --paginate --jq '.[] | {id, state}' | tail -1
```

## Replying to and resolving a thread

Replying is REST and takes the **inline comment's** id, which this lists (with `--paginate`,
for the reason given under *Commenting* above — a review round easily exceeds one page):

```sh
gh api repos/$REPO/pulls/<n>/comments \
  --paginate --jq '.[] | {id, path, line}'
```

```sh
gh api -X POST repos/$REPO/pulls/<n>/comments/<comment-id>/replies \
  -F body=@<path> --jq '.id'
```

The POST returns the created comment, so `--jq '.id'` is its read-back.

Resolving has **no REST endpoint at all** — GraphQL only, in two steps. List the threads with
their ids and current state:

```sh
gh api graphql -F owner="$OWNER" -F name="$REPO_NAME" -F number=<n> \
  -f query='query($owner:String!, $name:String!, $number:Int!) { repository(owner:$owner, name:$name) {
  pullRequest(number:$number) { reviewThreads(first:100) {
    pageInfo { hasNextPage endCursor }
    nodes { id isResolved isOutdated
      comments(first:1){ nodes { databaseId path line body } } } } } } }'
```

`first:` is a hard cap, not a default that grows — the same trap as `item-list`'s limit. Check
`hasNextPage` and fetch the next page with `after:` rather than assuming 100 covered it.

then resolve one by its thread id:

```sh
gh api graphql -f query='mutation($tid:ID!){ resolveReviewThread(input:{threadId:$tid}){ thread { id isResolved } } }' \
  -f tid=<thread-id>
```

`isOutdated: true` only means a later commit moved the line; it is **not** resolved. The
mutation returns `isResolved`, which is the read-back — and since a burst of these is the
classic way to trip the secondary limiter, re-run the listing query afterwards rather than
assuming a batch all landed.

## Windows and Git Bash

- **Pass bodies as files, never as a heredoc into `--body`.** Issue and PR bodies written as
  `--body "$(cat <<'EOF' … EOF)"` have come out of this setup with mojibake in place of
  em-dashes and stray backslashes before backticks, and a long quoted heredoc containing many
  apostrophes can abort the whole command with *unexpected EOF*. Write the body with the Write
  tool and use `--body-file` (or `--input` for a JSON payload); it costs nothing and removes
  the failure mode.
- **A `gh api` body is a body too — `-F body=@<path>`, not inline `-f body='…'`.** The inline
  form is the one place left where the shell still gets at the text, and an apostrophe in it
  has aborted the call with *unexpected end of JSON input*. `-F body=@<path>` reads the file
  itself and round-trips apostrophes, em-dashes and backticks byte for byte:

  ```sh
  gh api -X POST repos/$REPO/issues/<n>/comments \
    -F body=@<path> --jq '.body'
  ```

  Which is why every recipe above that passes a body as a `gh api` field — comments, review
  replies, PR creation, a body rewrite — is written that way. The two that pass a whole JSON
  document instead (issue creation, a review payload) use `--input <file>` for the same
  reason: the text never reaches the shell.
- **`jq` is not on PATH here; `gh --jq` is.** `gh`'s own `--jq` flag is built in and every
  recipe above relies on it, but a standalone `jq` in a pipe fails with *jq: command not
  found*. So a JSON payload for `--input` cannot be assembled with the obvious
  `jq -Rs '{body: .}' file` — write the payload file directly with the Write tool instead.
- **Git Bash rewrites a leading-slash argument into a Windows path.** `gh api /repos/…` fails
  with *invalid API endpoint: "C:/Program Files/Git/repos/…"*. Either omit the leading slash —
  `gh api repos/…`, which is what every recipe above does — or prefix the command with
  `MSYS_NO_PATHCONV=1`. The same rewriting hits `git` arguments of the form `<rev>:<path>` when
  the path part starts with a slash.

## Relationship to the review-mechanics skills

`submit-pr-review` and `address-review-remarks` carry tracker commands
of their own. Which of their commands may be written out rather than routed, and which file
wins where both spell the same one out, is
settled by [ai-authoring.md](ai-authoring.md)'s **Tracker-dependent mechanics route through
`CLAUDE.md`** and is not re-argued here. What this file never covers is *what a review says* —
payload shape, severity grouping, verdict marker, and — `resolve-review-thread`'s alone —
which threads may be resolved. Those four stay with the skills, and this file defers to them
on each.
