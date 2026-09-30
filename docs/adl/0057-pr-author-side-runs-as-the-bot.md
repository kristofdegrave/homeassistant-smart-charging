# ADR-0057: A pull request's author side runs as the bot account, its reviewer side as the owner (narrows ADR-0055)

Date: 2026-09-30
Status: Accepted

## Summary

In the context of a pull request the bot opens while the session replies on it as the owner,
facing one author split across two logins, we decided on Option C, the author side's posts
as the bot too, to tell a pull request's author and reviewer apart by login, accepting that the
wrapper grows from one call to four, each an allow-list entry and a refusal to test.

## Context

- **ADR-0055's line.** [ADR-0055](0055-session-pushes-and-opens-prs-as-a-bot-account.md)'s
  Option C puts commits, pushes and opening a pull request on the bot and leaves every other
  post on the owner's login, accepting that "the session's comments and labels still share the
  owner's login, told apart by markers alone".
- **Two sides of one pull request.** The author side — the implement and fix steps — opens it,
  commits and pushes, replies in each review thread, posts the fix summary and notes, and
  resolves the threads it fixed. The reviewer side — the review step — posts the review passes,
  the exit labels, the escalation and self-grant comments, and the human approves and merges.
  Board moves are both sides' bookkeeping.
- **What reads a post's author.** The round count and `fix`'s collector take a *human item* to
  be a login not ending in `[bot]` whose body carries none of the session's markers, and every
  session post carries one. The bot is a user login with `write` access, so
  [ADR-0054](0054-autopilot-runs-dontask-and-trusts-only-write-access-authors.md)'s author test
  admits it. `clarify`'s park, the self-grant count, the tick log and the `decompose` go read
  "the session's login", on issues and on the reviewer side's comments.
- **The calls.** A reply is REST; a comment is GraphQL through `gh pr comment`, with a REST
  fallback whose path is the same for a pull request as for an issue; a thread resolve is
  GraphQL only, and a round's replies and resolves are the burst that trips the secondary
  limiter on the account sending them. The board needs the `project` scope, which the bot's
  token lacks, and the merge rule reads the labels.

## Considered options

### Option A — Keep ADR-0055's line

- Pro: the wrapper stays one call; nothing else changes.
- Con: one pull request's author shows as two logins, and the fixer's and the reviewer's posts
  share one, told apart by markers alone.

### Option B — The author steps run wholly as the bot, board moves and labels included

- Pro: every write the implement and fix steps make carries one login.
- Con: the bot's token needs the `project` scope and access to the owner's board.
- Con: the exit labels the merge rule reads, and `fix`'s removal of stale ones, would carry the
  author's login where the reviewer side sets the same labels.

### Option C — The author side's posts on the pull request run as the bot; bookkeeping and the reviewer side stay the owner's

The wrapper ADR-0055 decides runs, with the bot's token, a closed list: opening a pull request,
a reply in one of its review threads, a comment on it, and resolving one of its threads —
refusing an issue that is not a pull request and any other call. Board moves, labels, the
review passes and the reviewer side's comments stay plain `gh`, as the owner.

- Pro: a pull request's author and reviewer are told apart by login as well as by markers.
- Pro: thread resolves spend the bot's side of the secondary limiter, not the owner's.
- Con: the wrapper grows from one call to four, each an allow-list entry and a refusal to
  test.
- Con: the fix step still writes as the owner when it takes stale exit labels off, so the step
  holds both logins.

## Decision

**Option C**, over A because A's pull request splits its author across two logins, and over B
because B's Cons put the author's login on the labels the reviewer side and the merge rule
own. Its first Con is accepted because each added call is the same shape as ADR-0055's one;
its second because the labels then stay on the one login that sets them and the merge rule
reads.

## Consequences

- **"The session's login" names a side.** On issues and on the reviewer side's comments it is
  the owner's: `clarify`'s park, the self-grant count, the tick log and the `decompose` go
  read that one, and say so.
- **The round count and the collector need no new rule.** The bot's posts carry the session's
  markers, which is what excludes them, and pass the author test on its `write` access.
- **The wrapper and the allow-list** gain the three calls; the owner's forms of a reply and a
  resolve go, and the owner's comment stays for the reviewer side.
- **ADR-0055 is narrowed**, not superseded: its Option C's scope — the bot reached only to
  commit, push and open a pull request — the wrapper's single call, and its comment Con no
  longer describe the author side; its identity split, its approval rule and its guard stand.
- The `workflow` issue carrying ADR-0055's rows carries these too.

**Blast radius.** One search, run from the repository root:

```sh
rg -n --hidden --glob '!.git/' --glob '!docs/adl/**' --glob '!docs/postmortems/**' \
  --glob '!docs/archive/**' --glob '!docs/plans/**' --glob '!CHANGELOG.md' \
  -e '\b(login|account)s?\b|owner.s login|same login|under the owner|as the owner' \
  -e 'as the maintainer|as the human' \
  -e 'kristofdegrave-bot|bot (account|identity|author|login)' \
  -e '[/]replies|resolveReviewThread|gh pr comment|issues/<n>/comments' \
  -e 'smart-charging/(pulls|issues)\*' \
  -e 'ai-fix-(summary|ack|note)' .
```

Wide enough: whose login a post carries is keyed on the words `login` and `account`
themselves; the posts this record moves on the calls that make them, their allow-list entries
and the markers they carry. **100** hits.

| Site | Today | Follow-up |
|---|---|---|
| `docs/reference/method/tracker-mechanics.md:264`, `:271` | A comment on a pull request or issue, as the owner | The fix step's comment on a pull request through the wrapper |
| `docs/reference/method/tracker-mechanics.md:475`, `:495` | A reply and a thread resolve, as the owner | Through the wrapper |
| `docs/reference/method/tracker-mechanics.md:308` | The session's comments are the owner's | Under either login, each passing the author test |
| `.claude/settings.json:34` | Allows any un-verbed call on `pulls`, a reply included once `-F` makes it a POST | Keeps reads and `pulls/<n>/reviews`; the owner's reply goes |
| `.claude/settings.json:38`, `:43` | Allow the owner's POSTs on `pulls` and the resolve mutation | The reply and the resolve through the wrapper |
| `docs/reference/profile.md:23`, `:26`, `:28` | One account for every step | The author and reviewer sides and their logins |
| `docs/reference/profile.md:30` | The session's footprint on the owner's login | Split by side |
| `docs/reference/profile.md:109` | The resolve mutation as an allow-list prefix, in a sentence granting `POST` on the pulls | The wrapper's entry; the `POST` on the pulls goes |
| `docs/reference/method/contribution-workflow.md:279` | The cap relies on one account | Relies on the session's markers |
| `.claude/skills/review/SKILL.md:29`; `.claude/skills/clarify/SKILL.md:71`; `.claude/skills/autopilot/SKILL.md:145`; `docs/reference/work-types/decompose/implement.md:44`, `:70` | Read "the session's login" | Name the owner's |

51 hits conform. Four are ADR-0055's rows, which carries them: `block-destructive-git.sh:26`,
`submit-pr-review/SKILL.md:14`, `profile.md:51`, `tracker-mechanics.md:442`. The other 47:
`block-destructive-git.sh:121`; `test-block-destructive-git.sh:118`, `:167`, `:346`;
`settings.json:32`, `:33`, `:36`, `:37`, `:42`; `autopilot/SKILL.md:18`, `:33`;
`clarify/SKILL.md:76`; `fix/SKILL.md:26`, `:27`, `:30`, `:32`, `:35`, `:36`, `:92`, `:95`,
`:110`; `research/SKILL.md:50`; `submit-pr-review/SKILL.md:57`, `:58`; `CODEOWNERS:6`;
`contribution-workflow.md:120`, `:278`; `tracker-mechanics.md:48`, `:61`, `:249`, `:278`,
`:299`, `:300`, `:305`, `:419`, `:423`, `:432`, `:433`, `:434`, `:436`, `:517`;
`profile.md:42`, `:150`; `decompose/done.md:41`; `decompose/implement.md:41`, `:57`, `:72`.

Out of scope, 30 hits, each keeping what it says:
- `account` in another sense — a domain example or "account for": 10 in
  `.claude/skills/domain-driven-design/`, 2 in `.claude/vendor/`, 1 in `custom_components/`,
  4 in `tests/`, 3 in `docs/analysis/`, 4 in `docs/design/`, and `fix/SKILL.md:93`.
- Another actor's login: the 2 in `.github/workflows/upstream-drift.yml` and
  `ci-pipeline.md:260`, the CI job's app; `setup-labels.sh:13`, the human running it;
  `profile.yml:27`, the board's owner.
