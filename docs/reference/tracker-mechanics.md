# Tracker mechanics

The concrete commands for driving this project's tracker — GitHub issues, pull requests,
review threads, labels, and the EMS project board — in one place, so no artifact has to
re-derive them and no agent has to rediscover the failure modes below the hard way.

**Mechanics only: the how, never the when or the why.** Which work gets an issue, what a
label means, when a PR is opened, when `needs-approval` goes on — all of that belongs to
[contribution-workflow.md](contribution-workflow.md) (the lifecycle),
[idea-to-issues.md](idea-to-issues.md) (the stages either side of it) and
[ci-pipeline.md](ci-pipeline.md) (the label-driven automation). This file assumes the
decision is already made and answers only "what do I type".

Throughout: the repo is `kristofdegrave/homeassistant-smart-charging`, the board is project
`1` under owner `kristofdegrave` (**EMS**). Every recipe below was run against them on
`gh` 2.95 — in the exact form written here, not a form it was later edited away from — rather
than transcribed from memory. Re-run one before trusting it if `gh` has moved on.

## The one rule: read the state back

`gh` reaches GitHub over **two transports**, and they fail independently:

| Transport | Used by |
|---|---|
| **GraphQL** | `gh issue create/edit/view`, `gh pr create/edit/view/comment`, `gh issue comment`, every `gh project *` subcommand, all review-thread resolution |
| **REST** | everything reached through `gh api <path>` without the `graphql` endpoint |

GitHub's **secondary (abuse) rate limiter** trips on a burst of GraphQL mutations — a couple
of review rounds' worth of thread replies and resolutions is enough — and then blocks the
whole GraphQL column for up to an hour **while REST keeps working**. `gh api rate_limit` does
not surface the secondary limiter: it happily reports 5000/5000 remaining on every bucket
while `gh project` and `gh pr edit` refuse. **The check is to retry the call you actually
need and read its result back, not to consult any meter.** A cheap GraphQL *read* such as
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

## Filing a work item

`gh issue create` cannot set project-board fields. It is always two steps: create, then add
the item to the board and edit its fields by raw node id.

```sh
# 1. create (see the Windows note below for why the body is a file)
gh issue create --repo kristofdegrave/homeassistant-smart-charging \
  --title "<title>" --body-file <path> --label <context-label>

# 2. put it on the board; item-add prints the item id you then edit
gh project item-add 1 --owner kristofdegrave --url <issue-url> --format json
```

```sh
# 3. set the fields, one call each, by node id
gh project item-edit --project-id PVT_kwHOABQtm84Bd8mI --id <item-id> \
  --field-id PVTSSF_lAHOABQtm84Bd8mIzhYaY9g --single-select-option-id 9728cbdc   # Size = M
gh project item-edit --project-id PVT_kwHOABQtm84Bd8mI --id <item-id> \
  --field-id PVTF_lAHOABQtm84Bd8mIzhYaY9k --number 3                             # Estimate = 3
gh project item-edit --project-id PVT_kwHOABQtm84Bd8mI --id <item-id> \
  --field-id PVTSSF_lAHOABQtm84Bd8mIzhYaYzw --single-select-option-id 47fc9ee4    # Status = In progress
```

`--number` is right for Estimate and `--single-select-option-id` for Size and Status: Estimate
is a plain number field, not a single-select.

Project id: `PVT_kwHOABQtm84Bd8mI`.

| Field | Field id | Option ids |
|---|---|---|
| Size | `PVTSSF_lAHOABQtm84Bd8mIzhYaY9g` | XS `eff732af` · S `9592a5a3` · M `9728cbdc` · L `c53df028` · XL `7b141a16` |
| Estimate | `PVTF_lAHOABQtm84Bd8mIzhYaY9k` | number field |
| Status | `PVTSSF_lAHOABQtm84Bd8mIzhYaYzw` | Backlog `f75ad846` · Ready `08afe404` · In progress `47fc9ee4` · In review `4cc61d42` · Done `98236657` |

Re-derive these with `gh project field-list 1 --owner kristofdegrave --format json` if an edit
is rejected — they are stable in practice but not guaranteed.

**Read-back — and the `--limit` trap.** `gh project item-list` defaults to **30** items, and
the board is far past that. A lookup under the default limit returns *empty rather than
erroring*, so a missing id reads as "the issue is not on the board" when it simply was not in
the page. Always pass an explicit high limit:

```sh
gh project item-list 1 --owner kristofdegrave --format json --limit 1000 \
  --jq '.items[] | select(.content.number==<n>) | {id, size, estimate, status}'
```

**REST fallback for the creation step** (the board steps have none):

```sh
gh api -X POST repos/kristofdegrave/homeassistant-smart-charging/issues --input <payload.json>
```

with `{"title": …, "body": …, "labels": [ … ]}`. Using `--input` also keeps the body's UTF-8
intact.

## Parent/sub-issue and blocked-by edges

That an epic's membership and ordering use these relationships rather than body text is
[contribution-workflow.md](contribution-workflow.md)'s **Issue conventions**. `gh` supports
both directly. At filing time:

```sh
gh issue create --repo kristofdegrave/homeassistant-smart-charging … \
  --parent <epic-number> --blocked-by <issue-number>
```

Afterwards:

```sh
gh issue edit <epic>  --repo kristofdegrave/homeassistant-smart-charging --add-sub-issue <child>
gh issue edit <child> --repo kristofdegrave/homeassistant-smart-charging --add-blocked-by <issue>
```

Read-back. `gh issue view --json parent,blockedBy` nests the dependency list one level deeper
than the flag name suggests — it is `.blockedBy.nodes[]`, not `.blockedBy[]`, and a `jq`
expression written the obvious way fails with *expected an object but got: array*:

```sh
gh issue view <n> --repo kristofdegrave/homeassistant-smart-charging \
  --json parent,blockedBy --jq '{parent: .parent.number, blockedBy: [.blockedBy.nodes[].number]}'
```

REST fallbacks — and their read-backs are the better read-back for the `gh issue edit` path
above too, since a GraphQL read cannot confirm a GraphQL write that the limiter may have
swallowed. Both writes take the sub-issue's / blocker's **database id**, not its issue
number:

```sh
sid=$(gh api repos/kristofdegrave/homeassistant-smart-charging/issues/<child> --jq .id)
gh api -X POST repos/kristofdegrave/homeassistant-smart-charging/issues/<epic>/sub_issues -F sub_issue_id=$sid
gh api repos/kristofdegrave/homeassistant-smart-charging/issues/<epic>/sub_issues --jq '[.[].number]'

bid=$(gh api repos/kristofdegrave/homeassistant-smart-charging/issues/<blocker> --jq .id)
gh api -X POST repos/kristofdegrave/homeassistant-smart-charging/issues/<n>/dependencies/blocked_by -F issue_id=$bid
gh api repos/kristofdegrave/homeassistant-smart-charging/issues/<n>/dependencies/blocked_by --jq '[.[].number]'
```

## Commenting on a work item

```sh
gh issue comment <n> --repo kristofdegrave/homeassistant-smart-charging --body-file <path>
gh pr comment    <n> --repo kristofdegrave/homeassistant-smart-charging --body-file <path>
```

One REST fallback serves both — for the comments API a PR *is* an issue, so the `issues` path
is correct for a PR number too:

```sh
gh api -X POST repos/kristofdegrave/homeassistant-smart-charging/issues/<n>/comments -f body='<markdown>'
```

Read back with:

```sh
gh api repos/kristofdegrave/homeassistant-smart-charging/issues/<n>/comments \
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
gh issue edit <n> --repo kristofdegrave/homeassistant-smart-charging --add-label <label>
gh pr edit   <n> --repo kristofdegrave/homeassistant-smart-charging --add-label <label>
```

These are the GraphQL commands that **fail silently** under the secondary limiter, so the
read-back is not optional:

```sh
gh api repos/kristofdegrave/homeassistant-smart-charging/issues/<n> --jq '[.labels[].name]'
```

(An issue path serves a PR too — a PR is an issue for the labels API.) REST fallback, which
returns the resulting label set directly, so it is its own read-back:

```sh
gh api -X POST   repos/kristofdegrave/homeassistant-smart-charging/issues/<n>/labels -f "labels[]=<label>" --jq '[.[].name]'
gh api -X DELETE repos/kristofdegrave/homeassistant-smart-charging/issues/<n>/labels/<label>               --jq '[.[].name]'
```

These recipes apply an existing label; they never create or rename one. Which labels exist
and what they mean is [contribution-workflow.md](contribution-workflow.md)'s **Issue
conventions**, and the places that vocabulary is baked into are
[ci-pipeline.md](ci-pipeline.md)'s **Label vocabulary sync**.

## Opening a change request

```sh
gh pr create --repo kristofdegrave/homeassistant-smart-charging \
  --base main --head <branch> --title "<title>" --body-file <path>
```

`gh pr create` is itself GraphQL and can be refused while REST is fine. The fallback creates
the same PR:

```sh
gh api -X POST repos/kristofdegrave/homeassistant-smart-charging/pulls \
  -f title='<title>' -f head='<branch>' -f base=main -F body=@<path> --jq '.html_url'
```

Read back with:

```sh
gh api repos/kristofdegrave/homeassistant-smart-charging/pulls/<n> \
  --jq '{state, base: .base.ref, head: .head.ref}'
```

## Posting a review with inline anchors

The review **payload** — what goes in the body, how findings are grouped, the anchoring rules
and the CI verdict marker — is owned by the `submit-pr-review` skill and is not restated here.
The transport is:

```sh
gh api repos/kristofdegrave/homeassistant-smart-charging/pulls/<n>/reviews --input <payload.json>
```

`--input` is mandatory rather than convenient: the payload is JSON with markdown inside it,
and building it inline mangles exactly the characters review findings are full of. Read back
with:

```sh
gh api repos/kristofdegrave/homeassistant-smart-charging/pulls/<n>/reviews \
  --paginate --jq '.[] | {id, state}' | tail -1
```

## Replying to and resolving a thread

Replying is REST and takes the **inline comment's** id, which this lists (with `--paginate`,
for the reason given under *Commenting* above — a review round easily exceeds one page):

```sh
gh api repos/kristofdegrave/homeassistant-smart-charging/pulls/<n>/comments \
  --paginate --jq '.[] | {id, path, line}'
```

```sh
gh api -X POST repos/kristofdegrave/homeassistant-smart-charging/pulls/<n>/comments/<comment-id>/replies \
  -f body='<markdown>'
```

Resolving has **no REST endpoint at all** — GraphQL only, in two steps. List the threads with
their ids and current state:

```sh
gh api graphql -f query='query { repository(owner:"kristofdegrave", name:"homeassistant-smart-charging") {
  pullRequest(number:<n>) { reviewThreads(first:100) {
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
- **Git Bash rewrites a leading-slash argument into a Windows path.** `gh api /repos/…` fails
  with *invalid API endpoint: "C:/Program Files/Git/repos/…"*. Either omit the leading slash —
  `gh api repos/…`, which is what every recipe above does — or prefix the command with
  `MSYS_NO_PATHCONV=1`. The same rewriting hits `git` arguments of the form `<rev>:<path>` when
  the path part starts with a slash.

## Relationship to the review-mechanics skills

`submit-pr-review`, `finalize-pr-review` and `address-review-remarks` exist to drive the
tracker — that is their whole subject, so they legitimately carry tracker commands of their
own. Where they define *what a review says* (payload shape, severity grouping, verdict
marker, which threads may be resolved), they remain the source of truth and this file defers
to them. Where they merely need to reach the tracker, this file is the mechanics reference.
