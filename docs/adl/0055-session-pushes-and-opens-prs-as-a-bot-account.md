# ADR-0055: The session commits, pushes and opens pull requests as a bot account; the owner's account keeps approval and merge (narrows ADR-0052)

Date: 2026-09-29
Status: Accepted

## Summary

In the context of one GitHub account shared by the session and the human partner, facing a
code-owner review nobody can give to a pull request its own author opened, we decided on
Option C, the bot reached only to commit, push and open a pull request, to make the human's
approval a real review, accepting that the owner's account can now approve the session's pull
requests, so an approval is one more rule of an accident guard.

## Context

- **One account today.** [ADR-0052](0052-autopilot-gates-auto-merge-by-tree-milestones-as-priority.md)'s
  Option C2 runs merges as the owner with `--admin`, and so left commits, pushes, pull requests,
  comments and labels on the owner's login too; the bot account it stopped using still exists.
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
  `gh` that could run it, a token prefix included, and the loop's `dontAsk` allow-list matches commands by how
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

### Option C — The owner's account stays the default; the bot is reached only to commit, push and open a pull request

Commits carry the bot's name and noreply email through the repository-local git config;
pushes use a repository-local credential helper returning the bot's stored token; a pull
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
first Con is accepted because no step needs the session to approve: approval stays the
human's alone, and the autopilot merges under ADR-0052's rule as the owner with `--admin`.

## Consequences

- **The profile names the bot.** `profile.yml` gains the bot's login; `profile.md`'s
  **Repository and git identity** states the split, the bot's `write` role on the repository,
  and the repository-local `user.name`, `user.email` and `credential.https://github.com.helper`
  it relies on: an empty helper entry first, since the global `gh auth git-credential` answers
  first and serves only `gh`'s active account, which stays the owner's.
- **A wrapper opens the pull request.** One script under `.github/` sets `GH_TOKEN` from the
  profile's bot login and runs `gh pr create`, or its REST fallback on the pulls collection,
  and refuses any other call; `tracker-mechanics.md`'s **Opening a change request** and the
  allow-list name it in place of plain `gh pr create`.
- **The guard refuses an approval**: `gh pr review --approve`, and an `APPROVE` event sent to
  a pull request's reviews, read from the `--input` payload file every review is posted with
  and refused when that file cannot be read, with tests. `submit-pr-review`'s author reason
  no longer holds: never approving becomes that rule, and never requesting changes stays its
  own prose rule, since a request changes nothing a merge reads.
- **The human's merge of a manual tree can be an approved one**, with no bypass; and with the
  bot's `write` role, branch protection refuses a push to `main` the session makes.
- **ADR-0052 is narrowed**, not superseded: its C2 Pro and Con about one account and the
  bot's last use no longer describe commits and pull requests; its guard and merge rule stand.
- One `workflow` issue carries every row below.

**Blast radius.** One search, run from the repository root:

```sh
rg -n --hidden --glob '!.git/' --glob '!docs/adl/**' --glob '!docs/postmortems/**' \
  --glob '!docs/archive/**' --glob '!docs/plans/**' --glob '!CHANGELOG.md' \
  -e 'self-approv|cannot approve|can.t approve|approve or request changes|\bapproves\b' \
  -e '\b(login|account)s?\b|owner.s login|same login|under the owner|as the owner' \
  -e 'as the maintainer|as the human' \
  -e 'kristofdegrave-bot|bot (account|identity|author|login)|[Oo]nly commits carry' \
  -e 'gh pr create|gh pr review|APPROVE' -e '/pulls(\*|[^/a-z]|$)|/pulls/<[a-z]+>/reviews' \
  -e 'commit identity|git config user|credential\.' \
  -e 'gh pr merge. outside|merge outside the auto-merge|goes to the merge rule' \
  -e '^# The merge rule|same hook mechanizes|Table-driven test for block-destructive' .
```

Wide enough: whose login a step runs under is keyed on the words `login` and `account`
themselves, not on phrasings of them; who may approve on the approval phrasings, the
`needs-approval` label excluded; opening or reviewing a pull request on the command and the
`pulls` endpoint; and what the guard refuses on each statement of the merge rule, beside which
the approval rule goes. **103** hits.

| Site | Today | Follow-up |
|---|---|---|
| `docs/reference/profile.md:23`, `:26`, `:28` | One account for every step, the bot retired | The split, its local git config, and the session's comments on the owner's login |
| `docs/reference/profile.md:51` | Merges as one account instead of a bot's | The bot opens; the owner still merges |
| `docs/reference/profile.md:145` | Only the guard closes the push gaps, branch protection not binding the owner | Branch protection binds the bot's pushes; the guard still closes the rest |
| `docs/reference/method/contribution-workflow.md:279` | The cap relies on one account | Relies on the session's comments being the owner's |
| `.claude/skills/submit-pr-review/SKILL.md:14` | The PR's opener cannot approve or request changes anyway | The guard refuses an approval; never requesting changes stays a prose rule |
| `docs/reference/method/tracker-mechanics.md:360`, `:364`, `:368` | `gh pr create` and its REST fallback as the owner | Through the bot wrapper |
| `docs/reference/method/tracker-mechanics.md:442` | A bot's login ends in `[bot]` | An app's does; the bot account is a user login |
| `.claude/hooks/block-destructive-git.sh:5`, `:26`, `:49` | The header states a merge rule only | Gains the approval rule |
| `.claude/hooks/test-block-destructive-git.sh:2` | Tests the git and merge rules | Gains the approval cases |
| `CLAUDE.md:18`; `docs/reference/method/contribution-workflow.md:247` | The guard refuses destructive git and a merge | And an approval |
| `.claude/settings.json:30`, `:38` | Allow the owner to open a pull request, by command or by a POST on the `pulls` collection | The wrapper opens one; the owner's POST on the bare collection goes |
| `.claude/settings.json:34` | Allows any un-verbed call on `pulls`, reads included | Keeps reads and `pulls/<n>/reviews` and `comments`; a POST on the bare collection goes |

50 hits conform, since comments, reviews, labels, the board, the guard's reads and the merge
stay on the owner's login, which is the login the session posts under that these read:
`block-destructive-git.sh:121`, `:234`, `:236`; `test-block-destructive-git.sh:159`;
`settings.json:42`; `autopilot/SKILL.md:18`, `:33`, `:145`; `clarify/SKILL.md:71`, `:76`;
`fix/SKILL.md:26`, `:27`, `:30`, `:34`, `:35`; `review/SKILL.md:29`, `:105`;
`submit-pr-review/SKILL.md:12`, `:57`, `:58`, `:63`; `CODEOWNERS:1`, `:6`;
`contribution-workflow.md:120`, `:217`, `:278`; `idea-to-product.md:403`;
`tracker-mechanics.md:39`, `:48`, `:249`, `:300`, `:305`, `:308`, `:419`, `:423`, `:431`,
`:432`, `:434`, `:436`, `:452`, `:460`; `profile.md:30`, `:42`, `:105`;
`decompose/done.md:41`; `decompose/implement.md:41`, `:44`, `:57`, `:70`, `:72`.

Out of scope, 33 hits, each keeping what it says:
- `account` in another sense — a domain example or "account for": 11 in
  `.claude/skills/domain-driven-design/`, 2 in `.claude/vendor/`, 1 in `custom_components/`,
  4 in `tests/`, 3 in `docs/analysis/`, 4 in `docs/design/`, and `fix/SKILL.md:93`.
- Another actor's login: the 2 in `.github/workflows/upstream-drift.yml` and
  `ci-pipeline.md:260`, the CI job's app; `setup-labels.sh:13`, the human running it;
  `profile.yml:27`, the board's owner; `test-check-authoring-rules.sh:23`, a throwaway
  repository's identity.
- `ai-authoring.md:281`, a recipe named as an authoring example.
