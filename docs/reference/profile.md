---
layer: project
---

# Project profile

The facts about *this* project that a person has to know to act on the method, each with its
why. `.claude/profile.yml` is the other half: every value a script or a command reads verbatim
— repository, board and field ids, the label set, enabled work types, the review cap and its
ceiling, dependency pins. Nothing here repeats a value the YAML holds; a section names the key
instead. Between them the two files own these facts: the repository and tracker, the board and
its ids, the label set, the enabled work types, the review cap and its ceiling, the dependency
pins, the research sources, the trees a `Source:` line may name, git identity, merge strategy and
flow deviations. A method document that spells one of *those* facts is the defect — it states the rule and routes
here. Stack-specific content (Home Assistant, Python) is a different axis and is not this
file's: it lives in the stack skills and in the per-stack overlays of the work-type files
(`docs/reference/work-types/<label>/overlays/<stack>.md`). What the profile holds about a stack
is `profile.yml`'s `stacks`: the declared stacks, each with the tokens the method check keeps
out of the core work-type files.

## Repository and git identity

A pull request has two sides, and each runs as its own account, interactive or unattended:
- **The author side runs as the bot**, `profile.yml`'s `identity.bot_login`, a collaborator
  with the `write` role: every commit and push, opening the pull request, and the fix step's
  thread replies, summary and note comments and thread resolves.
- **The reviewer side runs as the owner**, `profile.yml`'s `repo.owner`: the review passes, the
  exit labels, the escalation and self-grant comments, the merge, and the human's approval — and board
  moves, labels and every comment on an issue, whichever step posts them.

"The session's login" and "the login the session posts under", where a method file reads
one, are the owner's: every such site reads an issue or a reviewer-side post. The abstraction
stays in the method, and this is its mapping.

**How each side reaches its account.** `gh`'s active account stays the owner's, so a plain
`gh` call is the reviewer side. The author side's calls go through `.github/gh-as-bot.sh`,
which runs a closed list of them with the bot's stored token. Git reaches the bot through this
repository's local config, which every worktree shares, and no global config is relied on:
- `user.name` and `user.email` are the bot's login and noreply address;
- `credential.https://github.com.helper` is set twice — first to the empty string, which
  clears the helper list, since the global `gh auth git-credential` answers first and serves
  only `gh`'s active account; then to a helper returning `gh auth token --user <bot>`.

The bot's `gh` login carries the `repo` and `workflow` scopes, not `project`, which is why the
board stays the owner's.

**Why:** an author cannot approve their own pull request, so only one the bot opened is one the
owner can give the code-owner review; and with the sides on separate logins, a pull request's
author and reviewer are told apart by login. Older squash merges carry either account's author
line. **Why it matters:** both logins pass the author test, so `CLAUDE.md`'s **Contribution
workflow** topic's **Rounds and the cap** tells the session's posts from a human item by the
session's markers, never by author. Whether a session merges is **Merge strategy** below.

The repository is `profile.yml`'s `repo`; the tracker is GitHub issues, pull requests, review
threads and labels on it, driven with the recipes in
[tracker-mechanics.md](method/tracker-mechanics.md).

## Merge strategy

Every PR is **squash-merged**. Whose merge it is depends on its trees: a PR whose changed
files all sit under the auto-merge trees `profile.yml`'s `autopilot.auto_merge_trees` lists
may be merged by a Claude session, as the maintainer's own account, under the conditions
[contribution-workflow.md](method/contribution-workflow.md)'s **Commit & push authorization**
states; every other PR is merged by the maintainer by hand — `CODEOWNERS` covers every tree and
branch protection on `main` requires that approval, which a session's `--admin` merge
bypasses. **Why those trees:** they are read by a human later, at the epic-body
read and at verify live; the analysis, the records and the rules a run works under are the spec
and stay at the human's gate. **The known limit:** the rule is enforced locally, by the
`PreToolUse` guard in a Claude session of this repository — not by the platform, which has no
rule keyed on labels and files; the guard is an accident guard and not a sandbox. That is the
trade for merging as the owner rather than having a second account approve. **Why the
squash matters:** it rewrites the merged branch into one commit, which orphans any branch
stacked on it. That is the reason [contribution-workflow.md](method/contribution-workflow.md)'s **Base `main` and stacking** has every
PR base `main` directly, however the work was branched locally.

## Autopilot loop

The loop is started from the repository root with the loop-only settings file
`profile.yml`'s `autopilot.loop_settings` names:

```sh
claude --setting-sources project --settings .claude/autopilot.settings.json
```

then `/loop <interval> /autopilot` in that session. **Why `--setting-sources project`:** it
drops the user and local settings, whose broad allows would otherwise reach the loop, so the
committed `.claude/settings.json` allow-list and the loop file are the only grants in force;
the shared file's `PreToolUse` guards still run. **Why the loop file:**
[ADR-0054](../adl/0054-autopilot-runs-dontask-and-trusts-only-write-access-authors.md)'s
Options A1 and A2 — it sets `defaultMode: dontAsk`, denies edits and writes to `.claude/**`,
`.github/**` and `CLAUDE.md` in any checkout, allows edits only in a task worktree and the
session scratchpad, and sets the `env` variable `autopilot.loop_marker` names to `1`, which the
`autopilot` skill's first step checks and the destructive-git guard keys on: with it set, the
guard refuses a commit or a push whose change touches `.claude/`, `.github/` or a `CLAUDE.md`
or `CLAUDE.local.md`,
a change written by a subprocess as well as by Edit — the shell's way round the Edit deny. Its
header states the rule and what it concedes.

**What the rules assume.** A task worktree sits beside the main checkout, named `sc-<…>`
(`<parent>/sc-wf-<n>` for `workflow/<n>`); the `Read` and `Edit` rules for worktrees match
`//**/sc-*/**`, and those for scratch files `//**/scratchpad/**`. The shared allow-list's
`Read` rules exist because the `reviewer` definition's `permissionMode: dontAsk` reaches
interactive dispatches too. A worktree placed elsewhere is refused in the loop. Seven shapes
the harness itself decides, observed in a `dontAsk` session:

- **No `$` in a command.** `gh api repos/$REPO/…` is refused where the same call with the
  repository spelled out passes, and so is a GraphQL document declaring a variable, even
  quoted; shell state does not survive between calls either. So a recipe's shell variables are
  resolved with `bash .github/profile-env.sh` and their values spelled into the command, and the allow-list names this repository literally; with the marker in the
  loop file, the only `profile.yml` values spelled under `.claude/**`, since a settings file
  cannot read the profile.
- **Git in a worktree is `git -C <worktree> …`**: `cd <worktree> && git …` is refused
  whatever the allow-list says. `Bash(git -C *)` is in the loop file only, so an interactive
  session still prompts for it.
- **Scratch paths are written long**: a Windows short name (`KRISTO~1`) is refused where its
  long form passes.
- **The marker is read with `printenv <marker>`**, the one form the loop file admits.
- **A command is one line**: a line break inside a quoted argument makes it match no rule, so
  a multi-line GraphQL document is written on one line.
- **A rule's text holds no parenthesis**: a `Bash(…)` rule with one inside matches nothing,
  so each rule here stops before the first `(` of the command it admits.
- **A commit message goes in a file** (`git -C <worktree> commit -F <scratch file>`): the
  loop's text denies read an inline `-m` too, so a message naming `-c` or a push to `main`
  is refused.

**`gh api` is admitted by recipe shape**, not whole: reads on this repository's issues and
pulls, an un-verbed `POST` under `pulls/<n>/` (the review post, `--input` to its reviews), `POST`/`PATCH` on its issues, `POST` on its milestones, any `-X GET`, `rate_limit`,
and the two GraphQL recipes' opening words (`query{ repository`, `{viewer{login}}`), each a
prefix. The author side's calls are admitted as `bash .github/gh-as-bot.sh`, whose closed
list is the script's own; an owner's reply in a thread, and a call on the bare `pulls`
collection, are `ask` rules, and the resolve mutation is not admitted as the owner. `ask` rules close
what a prefix leaves open: a method after the path or a second method flag, `--method`, `..`
in a path, a second `query=`, a GraphQL field or `--input` read from a file, a GraphQL
`mutation` after `-F`, an `operationName`, a second `input:` in one document, and a body
`PATCH` from a file. So a write outside those shapes is refused; a plain `-X GET` still reads
any endpoint. The REST comment fallback (`-F body=@<file>`) is admitted.

**Label gestures.** `.claude/settings.json`'s `ask` rules match
`gh issue edit … --remove-label … needs-approval`, a `gh api` label `DELETE`, `PUT` or
`PATCH`, an issue `PATCH` from `--input` or `=@`, and the GraphQL `…LabelsFromLabelable` and
`updateIssue` mutations, with or without a leading assignment: an interactive session prompts,
a `dontAsk` one is refused. `gh pr edit --remove-label` is allowed. A single command removing
another label while naming `needs-approval` is refused too, and parks. The same `ask` rules
hold the GraphQL `mergeBranch`, `…Ref…`, commit, repository-settings, branch-protection and
`…PullRequest…` mutations.

**What the loop file refuses beyond the harness paths:** edits to any `.git` or `HEAD` file,
so no repository can be made by hand; git's `-c` and `--config-env` overrides,
`git -C … config`, `--git-dir`, `--work-tree`, `--upload-pack`,
`--receive-pack`, `--exec`, `--output`, `--extcmd`, `grep -O`/`--open-files-in-pager`; the
subcommands the chain never runs — `rebase`, `bisect`, `submodule`, `difftool`,
`filter-branch`, `clone`, `init`, `cherry-pick`, `switch`, and a fetch of a pull request's
`pull/<n>/…` ref — and those that write the tree or the object store around the
Edit deny — `mv`, `restore`, `apply`, `am`, `checkout … -- <path>`, `hash-object`,
`update-index`, `read-tree`, `commit-tree`, `update-ref`, `mktree`, `fast-import`; a push
naming `main`; and `pytest`, which runs any `conftest.py` a writer has written.

**Known gaps.** A Bash rule matches the text typed, not the program run — Claude Code's own
permissions documentation says it is not a security boundary around the program — so each
list above holds the forms named, and a form it does not name passes. Behind it, the
destructive-git guard's loop mode reads each word as sh passes it on (quotes and
backslashes removed; case ignored where gh ignores it), refuses a git or gh command carrying
`$` anywhere, a prefix assignment included, or one bash would expand (a brace list, a glob outside quotes), rather than guess
what the shell builds from it, and its header states the rules: the label gesture and the
named GraphQL mutations in any such spelling or spacing, a push of HEAD while `main` is
checked out, git's global overrides and their `GIT_*` environment forms, the
program-running options its header names, the subcommands this file denies, a `checkout` of
a path, a target outside this repository's checkout and worktrees, and a fetch with an
option it does not read, from another source, of a pull-request ref or an object id, or into
a named destination. Still open: what neither layer names — a GraphQL
mutation outside the guard's list, a git subcommand outside both lists, and the indirection
the guard's header concedes (a word built by the shell, a command run by another); and any
branch on `origin` — one anyone with write access pushed, reviewed or not — whose
`.github/hooks` a `git -C <wt> merge` or `checkout <ref>` brings in, and git runs on that
checkout or merge or the next commit: the guard refuses a commit only while a hook's change
is uncommitted and not staged by a merge in progress, not once a merge has committed it.
One layer sits outside both: a push runs as the bot, whose `write` role branch protection
binds, so the platform itself refuses a push to `main` the session makes.

**Not in the list.** Tests: `pytest` is denied in the loop, and the WSL test runner is this
machine's, not the repository's; a step that needs a local test run is refused in the loop
and leaves the tests to CI. Merge conflicts: taking one side with `checkout --ours`/`--theirs
<path>` is refused, so a conflict is resolved by editing the file, and one in a harness file
parks. Web access: neither `WebFetch` nor `WebSearch` is listed, so a
`research` step parks.

## Project board

The board is `profile.yml`'s `board` (its name, number and node id are there). Its Status
column vocabulary and option ids are `board.fields.status`. The contribution workflow's chain
names columns by **role** only — *backlog*, *in progress*, *in review*, *done* — and this list
is what maps each role to a column here; a method document that spelled a column name would
be stating a profile value, which the method check refuses:

- `Backlog` — the *backlog* role: filed, not started. Every issue starts here.
- `Ready` — **plays no role**. It exists on the board but has no defined meaning in this
  workflow, so nothing moves an item into it. If it gains one later (say, dependencies resolved
  and pickable), the contribution workflow's chain is where it gets inserted, explicitly.
- `In progress` — the *in progress* role: writing has actually started, in a worktree on the
  issue's branch — or, for an issue with no worktree (an epic, a `decompose` issue), its work
  has.
- `In review` — the *in review* role: a PR is open; it stays here through every review/fix
  round and the merge decision (the human's, or a session's under the merge rule).
- `Done` — the *done* role: merged and cleaned up — or, for an issue with no PR, closed by
  its owner's hand.

**Size** (`board.fields.size`) is a five-tier T-shirt estimate of reading-plus-writing effort;
**Estimate** (`board.fields.estimate`) is story points in a plain number field. Both are board
fields, not labels, so filing an issue is always two steps
([tracker-mechanics.md](method/tracker-mechanics.md)'s **Filing a work item**). The rules for setting
them — sizing sweeps up a tier, epics carrying Size only — are
[contribution-workflow.md](method/contribution-workflow.md)'s **Issue conventions**.

## Labels

The label set — names, colours, descriptions — is `profile.yml`'s `labels`, in five groups
(pre-triage, action, context, kind, structure), and `.github/setup-labels.sh` writes exactly
that set to the repository. What a group means and when an issue carries a label from it is
[contribution-workflow.md](method/contribution-workflow.md)'s **Issue conventions**; the other places
the context vocabulary is baked into are [ci-pipeline.md](method/ci-pipeline.md)'s **Label
vocabulary sync**. The enabled context labels are also the enabled work types
(`work_types.enabled`) — one directory each under `docs/reference/work-types/` and one row each
in `CLAUDE.md`'s **Model selection** table.

## Source lines

What a `Source:` line may name, and how finely, is the method's rule
(`CLAUDE.md`'s **Source lines**); the two lists it leaves to the project are `profile.yml`'s
`source_lines`, which `.github/check-source-lines.py` reads.

- **`trees`** — the analysis, design and decision-record trees: the documents a spec is
  derived from, and so the only ones a task can be cut from. The method tree is left out
  because a decomposition never cuts a task from it; post-mortems because they are dated
  snapshots, never a source of truth; code and tests because they are what a task changes.
- **`whole_file`** — use-cases and ADRs. Both are argued as wholes: a use-case's exception and
  alternate flows qualify its main flow, and an ADR's decision is only as narrow as its options
  and consequences say. A partial read drops exactly the part that makes the behaviour
  correct, so a bare path is the default for both.

## Research sources

When an external fact blocks a decision — what Home Assistant does in some case, how a
dependency behaves, what a device's API returns — these are this project's primary sources,
highest trust first. The `research` skill carries the generic procedure and reaches this list
through `CLAUDE.md`'s **Research sources** section.

1. **Home Assistant** — `developers.home-assistant.io` for the documented contract, and the
   `homeassistant` package source at the version pinned in `requirements-test.txt` for what
   the code actually does.
2. **Library source** — a dependency's published source at the version the file that pins it
   names (`requirements-test.txt` for test and dev dependencies; the integration manifest's
   `requirements` array for anything the shipped integration depends on), not its README. A
   changelog entry counts only as a pointer to the commit that made the change.
3. **Device / vendor API docs** — the manufacturer's own specification for a charger,
   inverter, meter or tariff provider this project integrates with (the hardware is listed in
   `docs/analysis/system-overview.md`); a captured response from the real device outranks the
   specification.

## Dependencies

The method skills this project's work files name, the skills ported into `.claude/skills/`,
and the two stack packages (Home Assistant, Python) are declared in `profile.yml`'s
`dependencies`, each with its upstream source and the pin it was last reconciled with. That
section is the provenance manifest: a pin moves only by a decision recorded in the PR that
moves it, because several of these skills are deliberate adaptations of their upstream
([ai-authoring.md](method/ai-authoring.md)'s **Vendored skills are forked on purpose**). Which of them
are method and which are stack follows the three-layer split this file exists for — method
(travels everywhere), profile (this project), stack packages (Home Assistant, Python) — so the
stack skills are declared here and are not part of the method.

## Flow

The method's default idea-to-product flow is [idea-to-product.md](method/idea-to-product.md), and
its first rule is to apply what this section states over the stages it names. This section is
the **deviation contract**, and it has exactly two shapes. Either it says **Default** — the
flow as written, no stage removed, added or reordered, no gate changed — and carries no `###`
at all. Or it carries one `###` per deviation, each heading naming, in backticks, the context
label of the work type whose stage it changes — ``### The `documentation` stage is skipped on the bug
track``, say — with the why beneath it, and never a copy of the flow, which would drift from
the method's. **Every backticked span in a deviation heading is read as a work type**, so
nothing else in the heading is backticked: a kind label, a file or a status goes in plain
words, or in the why beneath. The method check refuses a deviation heading that names no work
type, or one this project does not enable — a stage whose work type is not enabled is skipped
by the flow's own rule and needs no deviation to say so — and it refuses a profile document
with no `## Flow` section, or no profile document at all, since either has stated neither
shape.

**Default.** This project follows the flow as written.
