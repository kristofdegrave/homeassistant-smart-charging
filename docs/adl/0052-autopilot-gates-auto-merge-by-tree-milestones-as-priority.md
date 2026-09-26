# ADR-0052: An autopilot's controls — three human gates replace Rule B's chaining stop, auto-merge by tree behind a local guard, milestones as ordered priority

Date: 2026-09-26
Status: Accepted

## Summary

In the context of a contribution chain whose only control on unattended work is a human
gesture per issue, facing an autopilot that would start issues and merge pull requests
unwatched, we decided on gates plus a cap, auto-merge by tree, a local guard and milestones
as ordered slices, to put the human's attention only where judgment is needed, accepting that the merge class is enforced only in Claude sessions of this repository, not by
the platform.

## Context

- **The control today is a human per issue.** **Rule B** of the contribution workflow runs
  the chain unattended to a clean pass or the cap, and never starts the next issue off the
  back of the last: the control on autonomous artifact-chaining. Every merge is manual, by
  `CODEOWNERS` and branch protection.
- **An autopilot is wanted.** Each tick it reads tracker state, picks the next startable
  issue, runs the chain for it in isolation, and parks what needs a human. It is a local
  session — a `/loop` session first, `claude -p` per issue later — not the CI pipeline
  [ADR-0048](0048-retire-the-ai-label-pipeline.md) retired.
- **Three points still need a human.** Merging the documents later children are cut from
  (analysis, records) and the rules the run operates under (`.github/`, `.claude/`,
  `docs/reference/`, `CLAUDE.md`); the epic-body read, a human read under
  [ADR-0044](0044-implementation-spec-lives-in-the-epic-body.md); and verify live, an
  observation on the installation. `custom_components/`, `tests/` and `docs/design/` are
  downstream of the spec, each reviewed and checked.
- **Merges run as the human's account.** An author cannot approve their own pull request, so
  a merge by the session is `gh pr merge --admin`, bypassing code-owner review and the
  required checks; the platform has no rule keyed on a label and a file set. Commits alone
  carry a bot identity.
- **Two chains on one tree conflict**, and a squash merge orphans a stacked branch.
- **Nothing orders the backlog.** The board has no priority field, its `Ready` column plays
  no role, and the flow records milestone and priority as not yet standardized.

## Considered options

### Where the human's control sits

#### Option A1 — Keep Rule B: the human starts every issue

- Pro: a human looks at every issue before work begins.
- Con: one gesture per issue is the ceiling the autopilot exists to remove.

#### Option A2 — A curated queue: the human fills `Ready`, the autopilot drains it

- Pro: a per-issue veto survives, at one drag per issue.
- Con: a gesture per issue; an unfilled queue stalls the run, and a column records no reason.

#### Option A3 — Three gates plus a cap

Any open issue with a context label and no open blocked-by edge is startable; the autopilot
parks at the gates. At most two tree-disjoint lanes: a candidate overlapping an in-flight
pull request's files is skipped that tick, and a parked pull request counts as in flight.

- Pro: attention goes to the spec, the slice and the installation, at gates the flow already
  has.
- Con: an ill-formed issue is started by a machine; a pre-flight (one context label, a
  deliverable, resolving sources) catches only the mechanical part.
- Con: on a busy tree the overlap rule leaves a lane empty.

### What the autopilot may merge

#### Option B1 — Nothing: every merge stays manual

- Pro: the merge gate is untouched.
- Con: every pull request still waits for the human; the merge stays the ceiling.

#### Option B2 — By tree

All files under `custom_components/`, `tests/` or `docs/design/`, `needs-approval` without
`needs-decision`, CI green; every other tree, and a mixed-tree pull request, waits.

- Pro: decided from the diff and the labels alone, over trees downstream of the spec.
- Con: a mixed-tree pull request waits, however small its out-of-class part.
- Con: a wrong merge lands on `main` unread, caught by a filed bug, not prevented.

#### Option B3 — By context label (`development`, `testing`, `documentation`)

- Pro: reads the Model selection row directly.
- Con: a label bounds no file: a `development` pull request may edit `.claude/`.

### How the merge class is enforced

#### Option C1 — A second account: the bot approves and merges

- Pro: branch protection stays real; no `--admin`.
- Con: a second account to keep, whose rubber-stamp approval empties the code-owner rule
  while the class rule still needs a home.

#### Option C2 — A local guard: the PreToolUse hook refuses `gh pr merge` outside the class

The destructive-git guard refuses `gh pr merge` unless it squashes and B2's conditions hold,
auto-merge trees from the profile, every required check green. Merges run as the
human via `--admin --squash`; the bot identity is retired.

- Pro: one rule in one script with its own tests, beside the guard it extends; one account.
- Con: local enforcement only — it binds Claude sessions of this repository, not any other
  client, and `--admin` bypasses the checks the hook re-checks itself.

### In what order issues are picked

#### Option D1 — Board order, tie-break smallest Size

- Pro: no new field.
- Con: insertion order nobody curates says nothing about what ships first.

#### Option D2 — A board priority field

- Pro: expressive per issue.
- Con: one more field per issue, invisible to `gh issue`, not inherited; priority is per
  slice.

#### Option D3 — Milestones as ordered slices

One milestone per roadmap slice, ordered by a numeric prefix in its title, no due dates; an
epic carries it, a child inherits it at filing. Lowest open milestone first, then children of
an epic in progress, then board order; unmilestoned issues last.

- Pro: native to issues and to `gh`, assigned once per epic, visible in every list.
- Con: GitHub has no milestone order, so the prefix is a convention held by hand.
- Con: the four stale open milestones must be closed or ordered first.

## Decision

**Options A3, B2, C2 and D3.**

A3 over A1 and A2 because both keep the gesture that is the ceiling, and A2 adds a queue that
stalls. A3's first Con is bounded by the pre-flight; its second is the price of never stacking
on an unmerged branch.

B2 over B1 because B1 leaves the ceiling in place, and over B3 because B3's label bounds no
file. B2's second Con is accepted on its Pro.

C2 over C1 because C1's account would rubber-stamp the rule C2 states once, with tests. C2's
Con is the known limit this record writes down: the trade for one account.

D3 over D1 because a picker needs an order somebody meant, and over D2 because the slice is
the unit of priority. D3's first Con is a convention, like branch names.

One record, not four: gates mean nothing without a class the autopilot may merge, the class
nothing without its enforcement, and a picker at an uncurated queue needs an order.

## Consequences

- **Rule B is rewritten.** The stop-and-report stays for an interactive session; the chaining
  sentence goes, the gates and the cap in its place.
- **Merge is manual for the manual-merge trees only**; `needs-approval` is the merge
  condition for the auto-merge class.
- **Parking reuses the exit labels on issues.** `needs-approval` on an epic: read the parking
  comment and say go. `needs-decision` on any issue: a question in `clarify`'s shape.
  Removing the label is go; commenting with it on is an answer the next tick reads; leaving
  both is not yet. The parking comment carries a marker, and an item whose last human
  comment is newer than it is never re-parked. The labels' descriptions and the exit-labels
  rule widen to issues; `clarify` parks instead of blocking when no human can answer.
- **The guard gains the merge rule**, with tests, and the profile lists the auto-merge trees.
  A non-required check such as `authoring` reaches the rule or is promoted.
- **The bot identity is retired.** Commits carry the human partner's account; the profile's
  git-identity prose then holds as written.
- **Milestones become the method's priority.** The flow's *not yet standardized* sentence is
  replaced by the rule in **Issue conventions**; filing copies the epic's milestone to the
  child; working an idea or routing a bug ends on a milestone.
- **The epic-body read becomes a work type.** A `decompose` context label with its own Model
  selection row: one child per epic, blocked by every artifact-stage issue; its work file
  drafts the body, runs the checklist pass, fixes, and parks the epic with an executive
  summary; on go, the next tick files the children. Epics carry an `epic` label, outside the
  per-task rules.
- **Limits throttle, failures park.** A usage-limit error dispatches nothing new, probes every
  thirty minutes and resumes on success; a `paused` label on the tracking issue is the
  remote stop. A crash is retried once, then parked. A daily digest comment reports.
- **ADR-0048 stands**: the lifecycle still runs in local sessions; its kept exit labels gain
  a meaning on issues.
- **`docs/design/system-design.md` §8.3** gives this record a process row.
- **Easier:** the repository moves unattended. **Harder:** an auto-merge is read by a human
  only afterwards, and the merge rule is only as good as the machine running it.

**Blast radius.** One search, run from the repository root:

```sh
rg -n --hidden --glob '!.git/' \
  --glob '!docs/adl/**' --glob '!docs/postmortems/**' --glob '!docs/archive/**' \
  --glob '!docs/plans/**' --glob '!CHANGELOG.md' \
  -e 'Rule B\b' -e 'next issue' -e 'artifact-chaining' \
  -e '[Mm]erge is always manual|[Mm]anual merge|merged, manually|manually, by the maintainer|no Claude session can merge|never auto-merged' \
  -e 'not yet standardized' -e '[Mm]ilestone' -e '`Ready`' \
  -e 'gh pr merge|block list is the one' -e 'bot account|kristofdegrave-bot' \
  -e '"PR: ' -e 'one actor' \
  -e 'interactive session|non-interactive|[Ii]nteractive only|interactive-only' .
```

Wide enough because each part replaces a rule that names itself: Rule B, the manual-merge
statements, the unstandardized milestone, the unused column, the guard's block list, the bot
identity, the labels' `PR:` scope and one actor, and the interactive qualifier on the chain
and its skills. `--hidden` keeps `.claude/` and `.github/` in. **40** hits on `origin/main`.

| Site | Today | Follow-up |
|---|---|---|
| `docs/reference/method/contribution-workflow.md:69`, `:75`, `:76`; `.claude/skills/implement/SKILL.md:60` | Rule B forbids starting the next issue | The sentence goes; gates and cap in its place |
| `docs/reference/method/contribution-workflow.md:4`, `:86`, `:275`; `CLAUDE.md:112`; `.claude/profile.yml:170` | Name an interactive session | Hold unattended too |
| `docs/reference/method/contribution-workflow.md:215`, `:216`; `docs/reference/profile.md:34`, `:35`; `.github/CODEOWNERS:5` | Every merge is manual | Narrowed to the manual-merge trees |
| `docs/reference/method/contribution-workflow.md:145` | Neither label replaces manual merge approval | For the auto-merge class `needs-approval` is the merge condition |
| `docs/reference/method/contribution-workflow.md:137`; `.claude/profile.yml:71`, `:74` | The exit labels have one actor and describe a pull request | Widened to issues and the autopilot's park |
| `.github/workflows/ci.yml:91` | A red `authoring` surfaces at the manual gate | Reaches the merge rule, or is promoted |
| `.claude/hooks/block-destructive-git.sh:30` | The block list is the workflow doc's | Gains the `gh pr merge` rule and its tests |
| `docs/reference/profile.md:23` | Names one account; commits carry the bot's | The bot identity goes; the section then holds |
| `docs/reference/method/idea-to-product.md:195` | Milestone and priority are not yet standardized | Replaced by the milestone rule |
| `.claude/skills/implement/SKILL.md:3`, `:13`; `.claude/skills/review/SKILL.md:3`, `:14`; `.claude/skills/fix/SKILL.md:3`; `.claude/skills/resolve-review-thread/SKILL.md:3` | Use in an interactive session, and why | Widened to the unattended dispatch |
| `.claude/skills/clarify/SKILL.md:3` | Never in a non-interactive run, since it blocks | Parks the question on the issue instead |

6 hits conform: `contribution-workflow.md:91` (the cap's reason), `handoff/SKILL.md:11` and
`:12` (the stop that stays), `check-authoring-rules.sh:26` (two manual-merge trees),
`check-method.py:100` (a column name) and `profile.md:49` (`Ready` keeps no role). Out of
scope: the 5 hits in `grilling/SKILL.md`, `diagnosing-bugs/SKILL.md` and `research/SKILL.md`
keep refusing to self-invoke without a human. The excluded trees keep their dated text; this
record and its ADL row fall in that exclusion.
