# ADR-0054: The autopilot's security model — what an unattended run may run, write and trust

Date: 2026-09-29
Status: Accepted

## Summary

In the context of an unattended `/loop` that dispatches writing agents under the human's
credentials, facing outsiders' tracker text and a permissive session reaching commits, we
decided on Options A1–A6 — `dontAsk`, a harness deny, one author test, tick-log state,
bounded agents and titled parks — to keep every unattended write inside rules the human
committed, accepting that a step needing an unlisted grant parks instead of running.

## Context

- **The loop acts as the human.** [ADR-0052](0052-autopilot-gates-auto-merge-by-tree-milestones-as-priority.md)
  lets a human-started loop start issues; its dispatched agents commit, push and comment under
  the owner's login, and its guard is an accident guard, not a sandbox.
- **Claude Code's permission modes** ([permissions](https://code.claude.com/docs/en/permissions)
  and [subagents](https://code.claude.com/docs/en/sub-agents) documentation) include `auto`,
  `dontAsk` and `bypassPermissions`. `dontAsk` refuses anything outside `permissions.allow`
  without prompting; `auto` still prompts when unsure. A subagent inherits
  `bypassPermissions`, `acceptEdits` and `auto`, and otherwise runs its own definition's
  `permissionMode`.
  `permissions.deny` path rules bind every mode and every subagent, before any allow, but
  only the file tools, the shell's recognised file commands and redirects, not a subprocess.
  `/loop` cannot run a skill with `disable-model-invocation: true`.
- **An unattended prompt hangs**: nobody answers it, and the lane stays held.
- **A same-repository branch's workflow runs with repository secrets**, so a commit under
  `.github/**` or `.claude/**` changes what runs next, with the owner's reach.
- **Whose text steers a run** is tested in three drifted copies — `clarify`'s, `decompose`'s,
  and the not-a-`[bot]`-login test `fix`'s collector and the round count's *human item* share —
  so a stranger's review comment on an autopilot pull request becomes an unattended commit.
- **A tick is a fresh read.** What the next tick needs — lane holder, retries, throttle,
  pending merges — survives only where it is written; a log that quotes tracker text or an
  agent's return hands that text the session's trust.
- **A dispatched agent can hang or overrun**, and a second dispatch onto its branch makes two
  writers.
- **Two parks share one label**: ADR-0052's verify-live park and the `decompose` park both put
  `needs-approval` on the epic, and the `decompose` entry rule reads any such removal as its go.

## Considered options

One option set per force; A is chosen in each.

### 1. Permission mode

- **A1 — `dontAsk` with a committed allow-list; the loop refuses any other mode; each agent
  definition carries the mode.** Pro: a missing grant is refused at the tool, so a step fails
  fast; the list is reviewed like code. Con: every command a step needs, `research`'s web
  access included, must be listed first, or the step parks.
- **B1 — `auto`.** Pro: no list to keep. Con: it still prompts when unsure, and an unattended
  prompt hangs.
- **C1 — `bypassPermissions`.** Pro: nothing ever blocks. Con: nothing is refused beyond the
  accident guard, and every agent inherits it.

### 2. Harness paths

- **A2 — the loop's own settings file, layered over the shared one and its guard, denies edits
  and writes to `.claude/**`, `.github/**` and `CLAUDE.md`**; a step that tries is refused and
  its chain parks. Pro: refused before the write, in every subagent; interactive sessions keep
  the shared file alone. Con: a harness change never runs unattended, even a trivial one; and
  the deny misses a subprocess's write, such as an allowed `git checkout <ref> -- .github/…`.
- **B2 — the tick declines to dispatch or continue a chain whose pull request touches them.**
  Pro: no settings file. Con: the write has already happened when the tick sees it.
- **C2 — allowed on `workflow` issues the human starts.** Pro: harness work could be delegated.
  Con: the autopilot never picks a `workflow` issue, so it widens nothing used.

### 3. Whose input steers a run

- **A3 — one author test at every tracker read that decides an action**, `fix`'s finding
  collector included: an author the tracker reports as having write access (`OWNER`,
  `COLLABORATOR`, or `MEMBER` on an organisation's repository), never a `[bot]` login; forks
  excluded outright. Stated once, beside the tracker recipe that reads the association. A
  failing item is logged as an attempted steer, never acted on. Pro: one owner closes the
  stranger's-comment hole everywhere. Con: `clarify`, `decompose`, `fix`, the round count and
  the autopilot each lose their own wording and point there.
- **B3 — the test at the tick only.** Pro: one site. Con: the hole inside the chain stays open.
- **C3 — only the session's login and the human's.** Pro: the tightest set here. Con: breaks
  on a team repository.

### 4. The loop's own state

- **A4 — every tick log carries the whole state forward** — lane holder and its start time,
  retry count, throttle and probe times, pending merges — so the newest log alone decides the
  next tick; logs and parks name items by number or link only, never quoting tracker text or
  an agent's return, which is data like tracker content. Pro: survives a restart or another
  machine, visible on the tracker. Con: each log repeats state that did not change.
- **B4 — state in a repository or scratch file.** Pro: private. Con: lost on a machine or
  session change, invisible on the tracker.
- **C4 — state in the session, logs for humans only.** Pro: nothing to serialize. Con: a
  restart loses the lane and pending checks.

### 5. Agent lifecycle

- **A5 — after a stated timeout the tick stops the agent and confirms it stopped, then retries
  once from a clean worktree; an unconfirmed stop parks the chain.** Every dispatch says "this
  step only", and the tick never self-grants a review round, since judging whether the author
  agrees is judging the work (Rule A). Pro: never two writers on one branch. Con: a hung stop
  costs a human gesture.
- **B5 — no timeout.** Pro: nothing killed mid-write. Con: a hung agent holds the lane forever.
- **C5 — timeout and re-dispatch without stopping.** Pro: fastest recovery. Con: two agents can
  push to one branch.

### 6. Verify live

- **A6 — implement ADR-0052's Consequence as written**: an epic's first child closing parks the
  epic with `needs-approval` and a comment opening `verify live: #<epic>` carrying the
  verify-live list; no other child starts before the label's removal. The `decompose` park
  carries its own fixed title; each rule reads only its own titled park, and a removal is the
  go only for the newest titled park on the epic. Pro: a parked item for the human, and
  neither removal reads as the other's go. Con: every park writer and reader must keep its
  title exact.
- **B6 — skip instead of park in phase 1.** Pro: no park to distinguish. Con: narrows ADR-0052,
  and leaves the human nothing parked to act on.
- **C6 — a separate `needs-verify` label.** Pro: the label alone disambiguates. Con: a label to
  sync, narrowing ADR-0052's choice of `needs-approval`.

## Decision

**Options A1, A2, A3, A4, A5 and A6**, each for the Cons its rivals carry above; each A's Con
is accepted.

One record, not six: each answers what an unattended run may run, write or trust, and each
leans on another — a mode without a harness deny still writes the harness, a deny without the
author test still obeys a stranger, a test without A4's rule is undone by quoting; A5's retry
count and lane holder are A4's state, and A6's titled park is a tracker read A3's test gates.

## Consequences

- **The autopilot skill is rewritten against this record** before it merges: it loses
  `disable-model-invocation: true`, which `/loop` cannot run; checks the session's mode at its
  first step; applies A3's test at every read; carries A4's state in every tick log; bounds
  agents per A5; and writes and reads A6's titled `verify live: #<epic>` park.
- **A committed allow-list and a loop-only settings file** are added; the loop starts with the
  latter, and every agent type it dispatches gets a definition carrying
  `permissionMode: dontAsk`.
- **No commit or push around the harness deny — derived from A2, not separately decided.**
  In the loop only, the `PreToolUse` guard also refuses a commit or push touching the harness
  paths. A `gh api` contents or git-data write passes both, an accepted gap.
- **The author test gets one home** in **Tracker mechanics**; the three drifted copies point
  there.
- **The `decompose` park gains a fixed title**, and its entry rule reads only that park.
- **Label gestures — derived from A1 and A3, not separately decided.** A label event carries an
  actor, no association, and the session acts under the human's login; so removing an epic's
  `needs-approval`, the human's go, stays the human's. The allow-list draws the line by
  command: `gh pr edit --remove-label` admitted, `gh issue edit --remove-label needs-approval`
  and the REST label `DELETE` not, so a pull request's removal on the REST fallback parks.
- **Harder**: a new command in any step is an allow-list change first, human-reviewed. The
  mode in the shared `reviewer` definition reaches interactive dispatches too, so the
  allow-list must cover the worktree and scratch reads they are handed.
- **ADR-0052 is not narrowed**: A6 is its Consequence, and its guard stays an accident guard.

**Blast radius.** One search, run from the repository root:

```sh
rg -n --hidden --glob '!.git/' --glob '!docs/postmortems/**' --glob '!docs/archive/**' \
  -e 'author_association|[Aa]uthor test|[Aa]uthor with write access|in `\[bot\]`' \
  -e 'permissionMode|[Pp]ermission mode|"permissions"|^tools:' \
  -e 'verified live before|verify-live gate|verify live: #' \
  -e 'A park counts|The park\*\* is|parking marker|autopilot-parked' \
  -e 'block-destructive-git' \
  -e 'only this step|grants itself|self-grant condition' .
```

Wide enough: every login test is written ``in `[bot]` `` and every association read names
`author_association`; every agent definition has a `tools:` line; every settings file a
`"permissions"` key; the verify-live gate names itself, and every park writer, reader and bar
item names the park or its marker; the guard is named by its file; A5's step scope and
self-grant by their rule's words. Tick logs and timeouts have no site on `main`, their skill
being unmerged. **68** hits.

| Site | Today | Follow-up |
|---|---|---|
| `.claude/settings.json:2` | An empty allow-list, no loop file | The committed allow-list; the harness deny in the loop's own file |
| `.claude/agents/reviewer.md:4` | No mode | Gains `permissionMode: dontAsk` |
| `docs/reference/method/tracker-mechanics.md:301` | Explains the association; the test is each reader's | States the one author test, forks included |
| `.claude/skills/clarify/SKILL.md:75`, `:77`; `docs/reference/work-types/decompose/implement.md:19` | Own copies of the test | Point at the one test |
| `.claude/skills/fix/SKILL.md:27`; `docs/reference/method/contribution-workflow.md:119` | Any login not ending in `[bot]` | The one author test |
| `docs/reference/work-types/decompose/implement.md:25`, `:40` | Any parking-marker comment is its park; a removal after it is its go | Only its titled park, and only when newest |
| `docs/reference/work-types/decompose/implement.md:77`, `:121` | Posts the park with the marker alone | Opens it with the fixed title |
| `docs/reference/work-types/decompose/done.md:33` | Scores the park by its marker, passing an untitled one | Scores the title too |
| `docs/reference/method/definition-of-done.md:93`; `docs/reference/method/idea-to-product.md:498` | The gate names no park | Held by the `verify live: #<epic>` park |
| `docs/reference/method/contribution-workflow.md:78` | "Only this step" is the human's to say | A tick's dispatch counts as saying it |
| `docs/reference/method/contribution-workflow.md:100`; `.claude/skills/review/SKILL.md:107` | Self-grants at the cap, unattended too | Never in an unattended run |
| `.claude/hooks/block-destructive-git.sh:190`; `.claude/hooks/test-block-destructive-git.sh:2` | Refuses destructive git and out-of-class merges | In the loop, also refuses a commit or push touching the harness paths; tested |

**44** hits conform: `tracker-mechanics.md:298`, `:306`, `:440`; `clarify/SKILL.md:57`, `:71`,
its park under `needs-decision` on its issue, not an epic; `contribution-workflow.md:121`,
`decompose/implement.md:140`, `decompose/done.md:34`, `cleanup/SKILL.md:76`,
`decomposition-checklist.md:66`, ADR-0052's `:136`; nine that only name or run the guard —
`CLAUDE.md:21`, `settings.json:12`, `profile.yml:192`, `contribution-workflow.md:240`, the
guard's `:125`, `:170` and its tests' `:5`, `:12`, `:618`; and **24** in this record. Out of
scope: ADR-0052's `:166`, `:194` stay a merged record's blast radius; `testing/implement.md:3`
is prose about writing tests; `test-check-method.sh:143` keeps feeding the method check a
synthetic agent.
