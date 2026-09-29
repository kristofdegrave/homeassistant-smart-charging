# ADR-0054: The autopilot's security model — `dontAsk` on a committed allow-list, harness paths denied, one author test, state in the tick log, bounded agents, titled parks

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
- **Claude Code's permission modes** are `default`, `acceptEdits`, `plan`, `auto`, `dontAsk`
  and `bypassPermissions`. `dontAsk` refuses anything outside `permissions.allow` without
  prompting; `auto` still prompts when unsure. A subagent inherits `bypassPermissions`,
  `acceptEdits` and `auto`, and otherwise runs its own definition's `permissionMode`.
  `permissions.deny` path rules bind every mode and every subagent, before any allow.
  `/loop` cannot run a skill with `disable-model-invocation: true`.
- **An unattended prompt hangs**: nobody answers it, and the lane stays held.
- **A same-repository branch's workflow runs with repository secrets**, so a commit under
  `.github/**` or `.claude/**` changes what runs next, with the owner's reach.
- **Whose text steers a run** is tested in three drifted copies — the `clarify` and `decompose`
  work files, the round count's *human item* — and `fix` collects findings from any login not
  ending in `[bot]`, so a stranger's review comment on an autopilot pull request becomes an
  unattended commit.
- **A tick is a fresh read.** What the next tick needs — lane holder, retries, throttle,
  pending merges — survives only where it is written; a log that quotes tracker text or an
  agent's return hands that text the session's trust.
- **A dispatched agent can hang or overrun**, and a second dispatch onto its branch makes two
  writers.
- **Two parks share one label**: ADR-0052's verify-live park and the `decompose` park both put
  `needs-approval` on the epic, and the `decompose` entry rule reads any such removal as its go.

## Considered options

One option set per force; A is the chosen option in each.

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

- **A2 — the loop's own settings file denies edits and writes to `.claude/**`, `.github/**`
  and `CLAUDE.md`**; a step that tries is refused and its chain parks. Pro: enforced at the tool,
  before the write, in every subagent; interactive sessions keep the shared file. Con: a
  harness change never runs unattended, even a trivial one.
- **B2 — the tick declines to dispatch or continue a chain whose pull request touches them.**
  Pro: no settings file. Con: the write has already happened when the tick sees it.
- **C2 — allowed on `workflow` issues the human starts.** Pro: harness work could be delegated.
  Con: the autopilot never picks a `workflow` issue anyway, so it widens nothing it uses.

### 3. Whose input steers a run

- **A3 — one author test at every tracker read that decides an action**, `fix`'s finding
  collector included: an author the tracker reports as having write access (`OWNER`,
  `COLLABORATOR`, or `MEMBER` on an organisation's repository), never a `[bot]` login; forks
  excluded outright. A label gesture carries an actor but no association, and only an account
  the platform lets triage the repository can label, so its test is the actor, never a `[bot]`.
  Stated once, beside the tracker recipe that reads the association. A failing item is logged
  as an attempted steer, never acted on. Pro: one owner closes the
  stranger's-comment hole everywhere. Con: `clarify`, `decompose`, `fix` and the round count
  each lose their own wording and point there.
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

**Options A1, A2, A3, A4, A5 and A6**, each for the Con its rivals carry: B1 hangs, C1 refuses
nothing; B2 sees the write too late, C2 widens nothing used; B3 leaves the chain open, C3 breaks
on a team; B4 and C4 lose state on a restart; B5 holds the lane, C5 makes two writers; B6 and C6
narrow ADR-0052. Each A's Con is accepted.

One record, not six: each answers what an unattended run may run, write or trust, and each
leaves the next open — a mode without a harness deny still writes the harness, a deny without
the author test still obeys a stranger, and a test without A4's rule is undone by quoting.

## Consequences

- **The autopilot skill is rewritten against this record** before it merges: it loses
  `disable-model-invocation: true`, which `/loop` cannot run; checks the session's mode at its
  first step; carries A4's state in every tick log; and bounds agents per A5.
- **A committed allow-list and a loop-only settings file** are added; the loop starts with that
  file, and every agent definition gains `permissionMode: dontAsk`.
- **The author test gets one home** beside the association recipe in **Tracker mechanics**;
  the three drifted copies and `fix`'s collector point there, closing the stranger's-comment
  hole.
- **The `decompose` park gains a fixed title**, and its entry rule reads only that park.
- **Harder**: a new command in any step is an allow-list change first, human-reviewed.
- **ADR-0052 is not narrowed**: A6 is its Consequence, and its guard stays an accident guard.

**Blast radius.** One search, run from the repository root:

```sh
rg -n --hidden --glob '!.git/' --glob '!docs/postmortems/**' --glob '!docs/archive/**' \
  -e 'author_association|[Aa]uthor test|[Aa]uthor with write access|in `\[bot\]`' \
  -e 'permissionMode|[Pp]ermission mode|"permissions"|^tools:' \
  -e 'verified live before|verify-live gate|verify live: #' \
  -e 'A park counts|The park\*\* is' .
```

Wide enough: every login test is written ``in `[bot]` `` and every association read names
`author_association`; every agent definition has a `tools:` line; every settings file a
`"permissions"` key; the verify-live gate and each park reader name themselves. Tick logs and
agent lifecycle have no site on `main`: the skill that holds them is unmerged. **47** hits.

| Site | Today | Follow-up |
|---|---|---|
| `.claude/settings.json:2` | An empty allow-list, no loop file | The committed allow-list; the harness deny in the loop's own file |
| `.claude/agents/reviewer.md:4` | No mode | Gains `permissionMode: dontAsk` |
| `docs/reference/method/tracker-mechanics.md:301` | Explains the association; the test is each reader's | States the one author test, forks and label gestures included |
| `.claude/skills/clarify/SKILL.md:75`, `:77`; `docs/reference/work-types/decompose/implement.md:19` | Own copies of the test | Point at the one test |
| `.claude/skills/fix/SKILL.md:27`; `docs/reference/method/contribution-workflow.md:119` | Any login not ending in `[bot]` | The one author test |
| `docs/reference/work-types/decompose/implement.md:25`, `:40` | Any parking-marker comment is its park; a removal after it is its go | Only its titled park, and only when newest |
| `docs/reference/method/definition-of-done.md:93`; `docs/reference/method/idea-to-product.md:498` | The gate names no park | Held by the `verify live: #<epic>` park |

**32** hits conform: `tracker-mechanics.md:298`, `:306`, `:440`, `clarify/SKILL.md:71`,
`decompose/implement.md:140`, `decompose/done.md:34`, `cleanup/SKILL.md:76`,
`decomposition-checklist.md:66`, ADR-0052's `:136`, this record's ADL row, and **22** in this
record. Out of scope:
ADR-0052's `:166`, a merged record's search; `testing/implement.md:3`, authoring tests;
`test-check-method.sh:143`, a fixture's agent.
