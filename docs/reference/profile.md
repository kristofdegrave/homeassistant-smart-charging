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
pins, the research sources, git identity, merge strategy and flow deviations. A method document that spells one of *those* facts is the defect — it states the rule and routes
here. Stack-specific content (Home Assistant, Python) is a different axis and is not this
file's: it lives in the stack skills and in the per-stack overlays of the work-type files
(`docs/reference/work-types/<label>/overlays/<stack>.md`). What the profile holds about a stack
is `profile.yml`'s `stacks`: the declared stacks, each with the tokens the method check keeps
out of the core work-type files.

## Repository and git identity

Claude commits, comments and opens PRs as the developer's own GitHub account — one account,
shared with the human partner, whether the session is interactive or unattended. The local
`user.name` and `user.email` of this repository, which every worktree of it shares, are the
human's public commit identity; no global git config is relied on. **Why one account:**
[ADR-0052](../adl/0052-autopilot-gates-auto-merge-by-tree-milestones-as-priority.md)'s Option
C2 decides it; older squash merges still carry the retired `kristofdegrave-bot` author line. Whether
a session merges is **Merge strategy** below. **Why it matters:** a
human item and the session's own footprint are posted under the same login, so
[contribution-workflow.md](method/contribution-workflow.md)'s **Rounds and the cap** tells them apart
by the session's markers, never by author.

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
trade for running merges as one account instead of a bot's. **Why the
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
`autopilot` skill's first step checks and the guard can key on.

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
pulls, `POST`/`PATCH` on its issues, `POST` on its pulls and milestones, any `-X GET`,
`rate_limit`, and the three GraphQL recipes' opening words (`query{ repository`,
`mutation{ resolveReviewThread`, `{viewer{login}}`), each a prefix. `ask` rules close
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
list above holds the forms named, and a form it does not name passes. Known ones: a label or
mutation name in another letter case (gh matches label names case-insensitively, the rules do
not) or split by quotes (`needs-appro''val`), which passes every substring rule, the label
gesture included; spacing a GraphQL document the rules do not expect; a bare
`git -C <main checkout> push` while on `main`, which names no refspec; and what git reads from
disk rather than from the command — a `git -C` into a directory that is not a task worktree, or
a hook the repository runs on commit (its `core.hooksPath` is under `.github/`), reached by a
write this list does not name; a `-C` into a directory a writer laid out as a repository by
some path other than a `HEAD` edit; and any ref on `origin` — a branch anyone with write access
pushed, merged or reviewed or not — whose `.github/hooks` a `git -C <wt> merge` or
`checkout <ref>` brings in, and git runs on the next checkout or commit. Branch protection does
not enforce on the owner's account, so only the `PreToolUse` guard, which parses what it
reads, can close these, and it does not yet.

**Not in the list.** Tests: `pytest` is denied in the loop, and the WSL test runner is this
machine's, not the repository's; a step that needs a local test run is refused in the loop
and leaves the tests to CI. Merge conflicts: taking one side with `checkout --ours`/`--theirs
-- <path>` is refused, so a conflict is resolved by editing the file, and one in a harness file
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
