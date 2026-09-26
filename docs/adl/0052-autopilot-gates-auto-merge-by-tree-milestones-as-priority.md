# ADR-0052: An autopilot's controls — three human gates replace Rule B's chaining stop, auto-merge by tree behind a local guard, milestones as ordered priority (narrows ADR-0048)

Date: 2026-09-26
Status: Accepted

## Summary

In the context of a contribution chain whose only control on unattended work is a human
gesture per issue, facing an autopilot that would start issues and merge pull requests
unwatched, we decided on gates plus a cap, auto-merge by tree, a local guard and milestones
as ordered slices, to spend the human's attention only on judgment, accepting that the guard
is an accident guard in Claude sessions of this repository, not a sandbox.

## Context

- **The control today is a human per issue.** **Rule B** of the contribution workflow runs
  the chain unattended to a clean pass or the cap, and never starts the next issue off the
  back of the last: the control on autonomous artifact-chaining. Every merge is manual, by
  `CODEOWNERS` and branch protection, and `cleanup` starts from the human saying it happened.
- **An autopilot is wanted**: each tick it reads tracker state, picks the next startable
  issue, runs its chain in isolation, and parks what needs a human — a local session,
  not the CI pipeline [ADR-0048](0048-retire-the-ai-label-pipeline.md) retired.
- **What each tree is to the flow.** Analysis and records are the spec. A design document is
  derived from merged analysis; an epic body is derived from one approved slice of it, then
  read by a human ([ADR-0044](0044-implementation-spec-lives-in-the-epic-body.md)). Code,
  tests and design each have a review checklist. `.github/`, `.claude/`, `docs/reference/` and `CLAUDE.md` are the rules a run operates
  under. Verify live is an observation on the installation.
- **Merges run as the human's account.** An author cannot approve their own pull request, so
  a merge by the session is `gh pr merge --admin`, bypassing code-owner review and the
  required checks; the platform has no rule keyed on a label and a file set. Only commits
  carry a bot identity, kept for nothing else.
- **Two chains on one tree conflict**, and a squash merge orphans a stacked branch.
- **Nothing orders the backlog.** The board has no priority field, its `Ready` column plays
  no role, and the flow records milestone and priority as not yet standardized.

## Considered options

### Where the human's control sits

#### Option A1 — Keep Rule B: the human starts every issue

- Pro: a human looks at every issue before work begins.
- Con: one gesture per issue is the ceiling the autopilot exists to remove.

#### Option A2 — A curated queue: the human fills `Ready`, the autopilot drains it

- Pro: a per-issue veto survives.
- Con: a gesture per issue; an unfilled queue stalls the run and records no reason.

#### Option A3 — Three gates plus a cap

Any open issue with a context label and no open blocked-by edge is startable; the human acts
at three gates — the merge of a document children are cut from, the epic-body read, verify
live. At most two tree-disjoint lanes: a candidate overlapping an in-flight pull request's
files is skipped that tick, a parked one counting as in flight.

- Pro: attention goes to the spec, the slice and the installation.
- Con: the per-issue veto goes; what is worked next is then set only by edges and order.
- Con: an ill-formed issue is started by a machine; a pre-flight (one context label, a
  deliverable, resolving sources) catches only the mechanical.

### What the autopilot may merge

#### Option B1 — Nothing: every merge stays manual

- Pro: the merge gate is untouched.
- Con: every pull request still waits; the merge stays the ceiling.

#### Option B2 — By tree

All files under `custom_components/`, `tests/` or `docs/design/`, `needs-approval` without
`needs-decision`, CI green; every other tree, and a mixed-tree pull request, waits.

- Pro: decided from the diff and labels alone, over trees a human reads again at the
  epic-body gate or verify live.
- Con: a design change reaches the flow's *approved* state without a human merge; a
  mixed-tree pull request waits.
- Con: a wrong merge lands on `main` unread, caught by a filed bug, not prevented.

### How the merge class is enforced

#### Option C1 — A second account: the bot approves and merges

- Pro: branch protection stays real; no `--admin`.
- Con: a second account to keep, whose rubber stamp empties the code-owner rule.

#### Option C2 — A local guard: the PreToolUse hook refuses `gh pr merge` outside the class

The destructive-git guard refuses `gh pr merge` unless it squashes and B2's conditions hold;
merges run as the human via `--admin --squash`.

- Pro: one rule in one script with its own tests, beside the guard it extends; one account.
- Con: an accident guard, not a sandbox: it sees `gh pr merge` typed as such in a Claude
  session here, not a wrapped shell, a raw API call or another client, and `--admin`
  bypasses the checks it re-checks.

### In what order issues are picked

#### Option D1 — Board order, tie-break smallest Size

- Pro: no new field.
- Con: insertion order nobody curates says nothing about what ships first.

#### Option D3 — Milestones as ordered slices

One milestone per slice — of `project-plan.md`, or an epic of the method's own — ordered by a
numeric prefix in its title, no due dates. Lowest open milestone first, then children of an
epic in progress, then board order; unmilestoned issues last.

- Pro: native to issues and to `gh`, assigned once per epic, visible in every list.
- Con: GitHub has no milestone order, so the prefix is a convention held by hand.
- Con: four stale open milestones must be ordered or closed first.

## Decision

**Options A3, B2, C2 and D3.**

A3 over A1 and A2 because both keep the gesture that is the ceiling, and A2 adds a queue that
stalls. A3's second Con is bounded by the pre-flight.

B2 over B1 because B1 leaves the ceiling in place. B2's Cons are accepted on its Pro: nothing
is cut from a design before a human reads the body derived from it.

C2 over C1 because C1's account would rubber-stamp the rule C2 states once, with tests; C2's
Con is the known limit this record writes down, the accident guard it extends.
C1 needs the bot; C2 leaves it no role, so it goes.

D3 over D1 because a picker needs an order somebody meant; D3's first Con is a convention.

One record, not four. A3 removes the per-issue gesture, so B2 has to say what the run may
finish alone, C2 has to hold B2, and D3 is where the human's say on what is worked next
survives: with D1 in D3's place, A3's first Con is unbounded.

## Consequences

- **Rule B is rewritten.** The stop-and-report stays for an interactive session; the chaining
  sentence goes, gates and cap in its place.
- **Merge is manual for the manual-merge trees only**; `needs-approval` is the auto-merge
  class's merge condition, and the Design gate's *approved* is met by it.
- **`cleanup` after an auto-merge runs from the autopilot's own merge**; the human's
  statement stays the trigger after a manual one.
- **Parking reuses the exit labels on issues.** `needs-approval` on an epic asks for a go;
  `needs-decision` on any issue asks a question in `clarify`'s shape. Removing the label is
  go; a comment with it on is read by the next tick. The parking
  comment carries a marker, and an item whose last human comment is newer than it is never
  re-parked. `clarify` parks instead of blocking when no human can answer.
- **The guard gains the merge rule**, with tests, and the profile lists the auto-merge trees.
  A non-required check such as `authoring` reaches the rule or is promoted.
- **The bot identity is retired**; commits carry the human partner's account.
- **Milestones become the method's priority**, stated in **Issue conventions** in place of
  the flow's *not yet standardized* sentence; filing copies the epic's milestone to the
  child, and working an idea or routing a bug ends on one.
- **The epic-body read becomes a work type.** A3 starts only an issue with a context label,
  so the parked read has to be one: a `decompose` label with its own row, one child per
  epic, blocked by every artifact-stage issue, parking the epic with an executive summary;
  on go, the children are filed. Epics carry an `epic` label the picker excludes.
- **Limits throttle, failures park:** a usage-limit error pauses dispatch rather than failing
  an issue, a `paused` label on the tracking issue is the remote stop, a failed run is
  retried once, then parked.
- **ADR-0048 is narrowed** in two consequences it kept: who applies the exit labels, and
  `CODEOWNERS` justified by the manual merge gate alone. Its decision and Status stand.
- **`docs/design/system-design.md` §8.3** gets a process row for this record.

**Blast radius.** One search, run from the repository root:

```sh
rg -n --hidden --glob '!.git/' \
  --glob '!docs/adl/**' --glob '!docs/postmortems/**' --glob '!docs/archive/**' \
  --glob '!docs/plans/**' --glob '!CHANGELOG.md' \
  -e 'Rule B\b' -e 'next issue' -e 'artifact-chaining' \
  -e '[Mm]erge is always manual|[Mm]anual merge|merged, manually|manually, by the maintainer|no Claude session can merge|never auto-merged' \
  -e '[Mm]erge is the human|human may merge|human.s merge|watch for the merge|merge happened|human stating' \
  -e 'not yet standardized' -e '[Mm]ilestone' -e '`Ready`' -e 'approved (slice of )?`project-plan' \
  -e 'gh pr merge|block list is the one' -e 'bot account|kristofdegrave-bot' \
  -e '"PR: ' -e 'one actor' \
  -e '[Ii]nteractive (session|lifecycle)|non-interactive|[Ii]nteractive(-| )only|[Ii]nteractive sessions only' .
```

Wide enough because each part replaces a rule that names itself, in every phrasing used: Rule
B, the manual merge and the `cleanup` trigger that assumes it, the Design gate's *approved*,
the milestone sentence, the unused column, the guard's block list, the bot identity, the
labels' `PR:` scope and one actor, and the interactive qualifier on the chain and its skills.
`--hidden` keeps `.claude/` and `.github/` in. **54** hits.

| Site | Today | Follow-up |
|---|---|---|
| `docs/reference/method/contribution-workflow.md:69`, `:75`, `:76`; `.claude/skills/implement/SKILL.md:60` | Rule B forbids starting the next issue | The sentence goes |
| `docs/reference/method/contribution-workflow.md:4`, `:86`, `:275`; `CLAUDE.md:112`; `.claude/profile.yml:170`; `.claude/skills/implement/SKILL.md:8`; `.claude/skills/review/SKILL.md:8`; `.claude/skills/fix/SKILL.md:8` | Say interactive | Hold unattended too |
| `docs/reference/method/contribution-workflow.md:46`, `:215`, `:216`; `docs/reference/profile.md:34`, `:35`, `:55`; `.github/CODEOWNERS:5` | Every merge is the human's | Narrowed to the manual-merge trees |
| `docs/reference/method/contribution-workflow.md:54`, `:80`, `:81`; `.claude/skills/cleanup/SKILL.md:3`, `:9`, `:14` | `cleanup` waits for the human's statement | Triggered by the autopilot's own merge |
| `docs/reference/method/contribution-workflow.md:145` | Neither label replaces manual merge approval | The auto-merge class's merge condition |
| `docs/reference/method/contribution-workflow.md:136`, `:137`; `.claude/profile.yml:71`, `:74` | Describe a pull request, with one actor | Widened to issues and the autopilot |
| `docs/reference/method/idea-to-product.md:215`, `:416` | *Approved* means merged by the human | Met by the auto-merge condition |
| `.github/workflows/ci.yml:91` | A red `authoring` needs the manual gate | Reaches the merge rule, or is promoted |
| `.claude/hooks/block-destructive-git.sh:30` | The block list is the workflow doc's | Gains the `gh pr merge` rule and its tests |
| `docs/reference/profile.md:23` | Names one account; commits carry the bot's | Holds once the bot identity goes |
| `docs/reference/method/idea-to-product.md:195` | Milestone and priority are not yet standardized | Replaced by the milestone rule |
| `.claude/skills/implement/SKILL.md:3`, `:13`; `.claude/skills/review/SKILL.md:3`, `:14`; `.claude/skills/fix/SKILL.md:3`; `.claude/skills/resolve-review-thread/SKILL.md:3` | Interactive-only, with why | Widened to the unattended dispatch |
| `.claude/skills/clarify/SKILL.md:3` | Never in a non-interactive run, since it blocks | Parks the question instead |
| `.claude/skills/research/SKILL.md:3`, `:17` | Refuses a non-interactive run for want of grants | The autopilot's dispatch states what it grants |

6 hits conform: `contribution-workflow.md:91`, `handoff/SKILL.md:11`, `:12`,
`check-authoring-rules.sh:26`, `check-method.py:100` and `profile.md:49` keep the cap's
reason, the stop, two manual-merge trees, a column name and `Ready`'s no role. Out of scope:
3 hits in `grilling/SKILL.md` and `diagnosing-bugs/SKILL.md`, which keep refusing to run
without a human. The excluded trees, this record among them, keep their dated text.
