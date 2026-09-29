# ADR-0055: The session pushes and opens pull requests as a bot account; the owner's account keeps approval and merge (narrows ADR-0052)

Date: 2026-09-29
Status: Accepted

## Summary

In the context of one GitHub account shared by the session and the human partner, facing a
code-owner review nobody can give to a pull request its own author opened, we decided on
Option C, the bot reached only to push and to open a pull request, to make the human's
approval a real review, accepting that the owner's account can now approve the session's pull
requests, so an approval is one more rule of an accident guard.

## Context

- **One account today.** [ADR-0052](0052-autopilot-gates-auto-merge-by-tree-milestones-as-priority.md)'s
  Option C2 runs merges as the owner with `--admin`, and so left commits, pushes, pull requests,
  comments and labels on the owner's login too; the bot account it retired is usable again.
- **An author cannot approve their own pull request** (GitHub answers 422). A pull request the
  session opens is the owner's, so the code-owner review branch protection on `main` requires
  is one nobody can give: every merge bypasses it.
- **What reads the owner's login.** [ADR-0054](0054-autopilot-runs-dontask-and-trusts-only-write-access-authors.md)'s
  author test, the round count's markers and the `decompose` go read the association or login
  of comments the session and the human both post; the board is a Projects board of the
  owner's personal account, which the bot's token cannot reach without the `project` scope.
- **How a command picks an account.** `gh` takes `GH_TOKEN` over its stored logins, and
  `gh auth token --user <login>` reads one stored login's token; git pushes with whatever its
  credential helper returns. The merge guard refuses a `gh pr merge` behind any first word but
  `gh`, a token prefix included, and the loop's `dontAsk` allow-list matches commands by how
  they start.
- **The merge decision is ADR-0052's**: the auto-merge class, its guard and the human's gate
  over every other tree. Only who runs each step is open here.

## Considered options

### Option A — Keep one account

- Pro: one credential; nothing in the harness changes.
- Con: the code-owner review stays one nobody can give, and commits never say who wrote them.

### Option B — The bot is the session's default; the owner's token is reached only to merge

The session starts with the bot's token in its environment, and the merge step reaches the
owner's through a committed wrapper the guard trusts as a second first word.

- Pro: every write the session makes carries the bot's login, so author alone tells the
  session's items from the human's.
- Con: no committed setting can carry the token, so every session needs a launch convention
  the loop's `--setting-sources project` start does not supply.
- Con: the author test, the round count, the `decompose` go and every board write read or need
  the owner's login, and each would change.
- Con: the guard gains a second word it lets reach a merge.

### Option C — The owner's account stays the default; the bot is reached only to push and to open a pull request

Pushes use a repository-local credential helper returning the bot's stored token; a pull
request is opened through one committed wrapper that sets `GH_TOKEN` to it and runs only that
call. Approval and merge stay plain `gh`, as the owner.

- Pro: the human approves a pull request the session opened, so the code-owner review is one
  somebody can give.
- Pro: the guard's merge rule, the author test, the round count and the board keep reading
  the owner's login unchanged.
- Con: the owner's account can now approve the session's pull requests, so the guard must
  refuse an approval to the session: an accident guard, not a sandbox.
- Con: the session's comments and labels still share the owner's login, told apart by markers
  alone.
- Con: two credentials sit on the machine, both reachable by the session.

## Decision

**Option C**, over A because A's code-owner review stays empty, and over B because B's Cons
change every reader of the owner's login for an attribution the markers already give. Its
first Con is accepted as ADR-0052 accepts its guard's limit.

Approval stays the human's alone: the autopilot merges under ADR-0052's rule as the owner
with `--admin`, and never approves.

## Consequences

- **The profile names the bot.** `profile.yml` gains the bot's login; `profile.md`'s
  **Repository and git identity** states the split, the repository-local `user.name`,
  `user.email` and `credential.https://github.com.helper` it relies on, and that the global
  helper, `gh auth git-credential`, serves only `gh`'s active account, which stays the owner's.
- **A wrapper opens the pull request.** One script under `.github/` sets `GH_TOKEN` from the
  profile's bot login and runs `gh pr create`, or its REST fallback on the pulls collection,
  and refuses any other call; `tracker-mechanics.md`'s **Opening a change request** and the
  allow-list name it in place of plain `gh pr create`.
- **The guard refuses an approval**: `gh pr review --approve`, and an `APPROVE` event sent to
  a pull request's reviews, read from the `--input` payload file every review is posted with
  and refused when that file cannot be read, with tests; `submit-pr-review`'s reason for never approving
  becomes that rule, since its author reason no longer holds.
- **The human's merge of a manual tree can be an approved one**, with no bypass.
- **ADR-0052 is narrowed**, not superseded: its C2 Pro and Con about one account and the
  bot's last use no longer describe commits and pull requests; its guard and merge rule stand.
- One `workflow` issue carries every row below.

**Blast radius.** One search, run from the repository root:

```sh
rg -n --hidden --glob '!.git/' --glob '!docs/adl/**' --glob '!docs/postmortems/**' \
  --glob '!docs/archive/**' --glob '!docs/plans/**' --glob '!CHANGELOG.md' \
  -e 'self-approv|cannot approve|can.t approve|approve or request changes' \
  -e 'one account|own GitHub account|owner.s login|human.s login|same login|under the owner|as the owner|as the maintainer|as the human' \
  -e 'kristofdegrave-bot|bot (account|identity|author|login)|[Oo]nly commits carry' \
  -e 'gh pr create|gh pr review|APPROVE' -e '/pulls(\*|[^/a-z]|$)|/pulls/<[a-z]+>/reviews' \
  -e 'commit identity|git config user|credential\.' .
```

Wide enough: the decision governs whose login each step runs under and who may approve, and
every site stating either names the account, the bot, the approval, or the command or the
`pulls` endpoint that opens or reviews a pull request. **32** hits.

| Site | Today | Follow-up |
|---|---|---|
| `docs/reference/profile.md:23`, `:26`, `:28` | One account for every step, the bot retired | The split and its local git config |
| `docs/reference/profile.md:51` | Merges as one account instead of a bot's | The bot opens; the owner still merges |
| `docs/reference/method/contribution-workflow.md:279` | The cap relies on one account | Relies on the session's comments being the owner's |
| `.claude/skills/submit-pr-review/SKILL.md:14` | The PR's opener cannot approve anyway | The guard refuses an approval |
| `docs/reference/method/tracker-mechanics.md:360`, `:364`, `:368` | `gh pr create` and its REST fallback as the owner | Through the bot wrapper |
| `.claude/settings.json:30`, `:34`, `:38` | Allow the owner to open a pull request, by command or over REST | The wrapper opens one; the owner's calls on the `pulls` collection narrowed to reviews and comments |

16 hits conform: `profile.md:30`, `:42`, `contribution-workflow.md:217`,
`tracker-mechanics.md:39`, `:308`, `:431`, `:452`, `:460`, `CODEOWNERS:6`,
`review/SKILL.md:105`, `submit-pr-review/SKILL.md:12`, `:63`, `fix/SKILL.md:34`,
`autopilot/SKILL.md:33`, `decompose/implement.md:57`, `test-block-destructive-git.sh:159`.
Out of scope: `profile.yml:27` names the board's owner, `test-check-authoring-rules.sh:23` a
throwaway repository's identity, `ci-pipeline.md:260` the retired job's app login, and
`ai-authoring.md:281` a recipe named as an authoring example; each keeps saying so.
