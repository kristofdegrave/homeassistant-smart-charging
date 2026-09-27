# ADR-0052: An autopilot's controls — three human gates replace Rule B's chaining stop, auto-merge by tree behind a local guard, milestones as ordered priority (narrows ADR-0043 and ADR-0048)

Date: 2026-09-26
Status: Accepted

## Summary

In the context of a contribution chain whose only control on unattended work is a human
gesture per issue, facing an autopilot that would start issues and merge pull requests
unwatched, we decided on gates plus a cap, auto-merge by tree, a local guard and milestones
as ordered slices, to spend the human's attention only on judgment, accepting that the guard
is an accident guard, not a sandbox.

## Context

- **The control today is a human per issue.** **Rule B** of the contribution workflow runs
  the chain unattended to a clean pass or the cap, and never starts the next issue off the
  back of the last. Every merge is manual, by
  `CODEOWNERS` and branch protection, and `cleanup` starts from the human.
- **An autopilot is wanted**: each tick it starts the next startable issue in isolation and
  parks what needs a human — a loop the human starts and stops under their own account, not
  the CI pipeline [ADR-0048](0048-retire-the-ai-label-pipeline.md) retired, nor
  [ADR-0043](0043-scheduled-upstream-drift-watcher.md)'s case, a clock-fired job with no
  human anywhere in its trigger.
- **What each tree is to the flow.** Analysis and records are the spec. A design document is
  derived from merged analysis; an epic body is derived from one approved slice of it, then
  read by a human ([ADR-0044](0044-implementation-spec-lives-in-the-epic-body.md)).
  `.github/`, `.claude/`, `docs/reference/` and `CLAUDE.md` are the rules a run operates
  under.
- **Merges run as the human's account.** An author cannot approve their own pull request, so
  a merge by the session is `gh pr merge --admin`, bypassing code-owner review and required
  checks; the platform has no rule keyed on a label and a file set. Only commits
  carry a bot identity, which nothing else uses.
- **Nothing orders the backlog.** The board has no priority field, its `Ready` column plays
  no role, and the flow leaves priority unstandardized.

## Considered options

### Where the human's control sits

#### Option A1 — Keep Rule B: the human starts every issue

- Pro: a human looks at every issue.
- Con: the gesture per issue is the ceiling.

#### Option A2 — Three gates plus a cap

Any open issue with a context label whose row names a work file, and no open blocked-by
edge, is startable; the human acts at three gates — the merge of a document children are cut
from, the epic-body read, verify live. The human starts and stops the loop, so a human is in
its trigger. At most two tree-disjoint lanes in flight.

- Pro: attention goes to the spec, the slice and the installation.
- Con: the per-issue veto goes; what is worked next is then set only by edges and order.
- Con: an ill-formed issue is started by a machine; a pre-flight (one context label, a body
  the work file can act on, resolving sources) catches only the mechanical.

### What the autopilot may merge

#### Option B1 — Nothing: every merge stays manual

- Pro: the merge gate is untouched.
- Con: every pull request still waits: the ceiling.

#### Option B2 — By tree

All files under `custom_components/`, `tests/` or `docs/design/`, `needs-approval` without
`needs-decision`, CI green; any other tree waits.

- Pro: decided from the diff and labels alone, over trees a human reads again at the
  epic-body gate or verify live.
- Con: a design change reaches the flow's *approved* state without a human merge.

### How the merge class is enforced

#### Option C1 — A second account: the bot approves and merges

- Pro: branch protection stays real.
- Con: a second account, whose rubber stamp empties the code-owner rule.

#### Option C2 — A local guard: the PreToolUse hook refuses `gh pr merge` outside the class

The destructive-git guard refuses `gh pr merge` unless it squashes and B2's conditions hold;
merges run as the human via `--admin --squash`.

- Pro: one rule in one script with its own tests, beside the guard it extends; one account,
  once the bot's last use, commit authorship, goes.
- Con: an accident guard, not a sandbox: it sees `gh pr merge` typed as such here, not a
  wrapped shell, a raw API call or another client.
- Con: commits stop carrying a bot author, which the chain never used to tell items apart.

### In what order issues are picked

#### Option D1 — Board order, tie-break smallest Size

- Pro: no new field.
- Con: insertion order nobody curates says nothing about what ships first.

#### Option D2 — Milestones as ordered slices

One milestone per slice — of `project-plan.md`, or a method epic — ordered by a
numeric prefix in its title; an epic carries it, a child inherits it at filing; unmilestoned
issues are picked last.

- Pro: native to issues and `gh`, assigned once per epic.
- Con: GitHub has no milestone order, so the prefix is a convention held by hand.
- Con: four stale milestones must be ordered first.

## Decision

**Options A2, B2, C2 and D2.**

A2 over A1, which keeps the gesture that is the ceiling; A2's second Con is accepted.

B2 over B1, which leaves the ceiling in place; B2's Cons are accepted on its Pro.

C2 over C1 because C1's account would rubber-stamp the rule C2 states once; its
first Con is the known limit written down here, its second the bot's last use.

D2 over D1 because a picker needs an order somebody meant; its first Con is a convention like
branch names, its second one roadmap session.

One record, not four: A2 removes the per-issue gesture, so B2 must say what the run may
finish alone, C2 must hold B2, and D2 keeps the human's say on what is worked next — with D1
in its place, A2's first Con is unbounded.

## Consequences

- **Rule B loses its chaining sentence**; the stop-and-report stays for an interactive
  session.
- **Merge is manual for the manual-merge trees only**; `needs-approval` is the auto-merge
  class's merge condition, which meets the Design gate's *approved*.
- **`cleanup` after an auto-merge runs from the autopilot's own merge**; a manual one still
  needs the human's statement.
- **Parking reuses the exit labels on issues.** `needs-approval` on an epic asks for a go;
  `needs-decision` asks a question in `clarify`'s shape. A marker in the parking comment
  keeps a tick from re-parking what the human answered.
- **The merge rule lives in the workflow's *Commit & push authorization***, which the guard
  mechanizes: the rule with tests and a wider header; the profile lists the auto-merge
  trees; a non-required check such as `authoring` reaches the rule or is promoted.
- **The bot identity is retired**; commits carry the human partner's account.
- **Milestones become the method's priority**, stated in **Issue conventions** in place of
  the flow's sentence; filing copies the epic's milestone to the child, and an idea or a
  routed bug ends on one.
- **The epic-body read becomes a work type.** A2 starts only an issue with a context label,
  so the parked read has to be one: a `decompose` label with its own row, one child per
  epic blocked by its artifact issues, parking the epic; on go, the children are filed. Epics carry an `epic` label the picker excludes.
- **Limits throttle, failures park:** a usage-limit error pauses dispatch, a `paused` label
  is the remote stop, a failed run is retried once then parked.
- **ADR-0048 is narrowed** in two kept consequences: who applies the exit labels, and
  `CODEOWNERS`' justification by the manual gate alone; **ADR-0043** in its may-not-dispatch
  rule and its scheduled-automation constraint, which bind a job with no human in its
  trigger, not a loop the human starts. Both stand.

**Blast radius.** One search, run from the repository root:

```sh
rg -n --hidden --glob '!.git/' \
  --glob '!docs/adl/**' --glob '!docs/postmortems/**' --glob '!docs/archive/**' \
  --glob '!docs/plans/**' --glob '!CHANGELOG.md' \
  -e 'Rule B\b' -e 'next issue' -e 'artifact-chaining' \
  -e '[Mm]erge is always manual|[Mm]anual merge|merged, manually|manually, by the maintainer|no Claude session can merge|never auto-merged' \
  -e '[Mm]erge is the human|human may merge|human.s merge|watch for the merge|merge happened|human stating' \
  -e 'not yet standardized' -e '[Mm]ilestone' -e '`Ready`' -e 'approved (slice of )?`project-plan' \
  -e 'gh pr merge|block list is the one|[Dd]estructive git|Commit & push|commit/push authorization|first word' \
  -e 'bot account|kristofdegrave-bot' -e '"PR: ' -e 'one actor|one step that applies' \
  -e 'human-authored|names none|Narrowed by ADR-0050|through ADR-0051|\| 0043 \|' \
  -e 'manual-approval-before-merge|maintainer is the sole|never a self-approval|No other step or|says to go on|Size/Estimate, `Source:`' \
  -e '^  context:|^  enabled:|[Oo]ne row per (enabled )?(context label|entry)|one row each|`adr`, `uc`, `requirement`|^## Labels' \
  -e '[Ii]nteractive (session|lifecycle)|non-interactive|[Ii]nteractive(-| )only|[Ii]nteractive sessions only' .
```

Wide enough because each part replaces a rule that names itself, in every wording: Rule B, the manual merge and `cleanup`'s trigger, the
Design gate's *approved*, the milestone sentence and filing's list, `Ready`, the guard's
block list, scope and authorization, rows without a work file, the label vocabulary and row
set, the exit labels' scope and actor, the bot identity, the closing step's go, the design
index, the interactive qualifier. **92** hits.

| Site | Today | Follow-up |
|---|---|---|
| `docs/reference/method/contribution-workflow.md:69`, `:75`, `:76`; `.claude/skills/implement/SKILL.md:60` | Rule B forbids starting the next issue | The sentence goes |
| `docs/reference/method/contribution-workflow.md:4`, `:275`; `.claude/profile.yml:170`; `.claude/skills/implement/SKILL.md:8`; `.claude/skills/review/SKILL.md:8`; `.claude/skills/fix/SKILL.md:8` | Say interactive | Hold unattended too |
| `CLAUDE.md:112` | Says interactive; `cleanup` starts from the human | Holds unattended; the autopilot's merge triggers it too |
| `docs/reference/method/contribution-workflow.md:46`, `:215`, `:216`; `docs/reference/profile.md:34`, `:35`, `:55`; `.github/CODEOWNERS:5` | Every merge is the human's | Narrowed to the manual-merge trees |
| `docs/reference/method/contribution-workflow.md:54`, `:80`, `:81`; `.claude/skills/cleanup/SKILL.md:3`, `:9`, `:14` | `cleanup` waits for the human's statement | Triggered by the autopilot's own merge |
| `docs/reference/method/contribution-workflow.md:145` | Neither label replaces manual merge approval | The auto-merge class's merge condition |
| `docs/reference/method/contribution-workflow.md:136`, `:137`, `:142`; `docs/reference/method/ci-pipeline.md:142`; `.claude/profile.yml:71`, `:74` | A pull request's, with one actor | Widened to issues and the autopilot |
| `.claude/profile.yml:78`, `:114`, `:122`; `CLAUDE.md:30`; `docs/reference/method/ci-pipeline.md:93`; `docs/reference/method/contribution-workflow.md:282`, `:327`; `docs/reference/method/definition-of-done.md:123`; `docs/reference/profile.md:65`, `:73` | Enumerate the context labels and rows | Gain `decompose`; `epic` and `paused` join the labels |
| `docs/reference/work-types/workflow/review.md:177`; `.claude/skills/submit-pr-review/SKILL.md:12`; `.claude/skills/review/SKILL.md:107` | The manual gate is sole and non-negotiable | Narrowed to the manual-merge trees |
| `docs/reference/method/idea-to-product.md:215`, `:416` | *Approved*, meaning merged, gates the spec | Met by the auto-merge condition |
| `docs/reference/method/idea-to-product.md:210` | The human says go on | The `decompose` park; go is the label's removal |
| `.claude/skills/file-task-issue/SKILL.md:63` | Filing's done-when list has no milestone | Gains the epic's milestone |
| `.github/workflows/ci.yml:91` | A red `authoring` needs the manual gate | Reaches the merge rule, or is promoted |
| `.claude/hooks/block-destructive-git.sh:2`, `:3`, `:4`, `:30`, `:38`, `:100`, `:294` | Refuses destructive git, on `git` segments | Gains the `gh pr merge` rule, tests, and a wider header |
| `docs/reference/method/contribution-workflow.md:236`; `CLAUDE.md:18` | Frame the guard as destructive-git only | The section states the merge rule too |
| `docs/design/system-design.md:832`, `:891`, `:894` | Count the records through 0051; the 0043 and 0048 rows | Gain this record and both narrowings |
| `docs/reference/profile.md:23` | Says there is no separate bot account | True once the commit identity goes |
| `docs/reference/method/idea-to-product.md:195` | Milestone and priority are not yet standardized | Replaced by the milestone rule |
| `.claude/skills/implement/SKILL.md:3`, `:13`; `.claude/skills/review/SKILL.md:3`, `:14`; `.claude/skills/fix/SKILL.md:3`; `.claude/skills/resolve-review-thread/SKILL.md:3` | Interactive-only, with why | Widened to the unattended dispatch |
| `.claude/skills/clarify/SKILL.md:3`; `docs/reference/method/contribution-workflow.md:86` | Blocks on a human; Rule C sends decisions there | Parks the question instead |
| `.claude/skills/research/SKILL.md:3`, `:17` | Refuses a non-interactive run for want of grants | The autopilot's dispatch states what it grants |

13 hits conform: `contribution-workflow.md:91`, `handoff/SKILL.md:11`, `:12`,
`check-authoring-rules.sh:26`, `check-method.py:100`, `profile.md:49`, `CLAUDE.md:44`,
`work-types/README.md:134`, `model-selection.md:81`, `definition-of-done.md:34`,
`implement/SKILL.md:23`, `workflow/review.md:53`, `resolving-merge-conflicts/SKILL.md:20`. Out of scope: the 3 hits in `grilling/SKILL.md` and
`diagnosing-bugs/SKILL.md`, which keep refusing to run unattended, and
`test-check-method.sh:40`, `:82`, `:90`, fixtures. Excluded trees keep their dated text.
