# ADR-0052: An autopilot's controls — three human gates replace Rule B's chaining stop, auto-merge by tree behind a local guard, milestones as ordered priority (narrows ADR-0043 and ADR-0048)

Date: 2026-09-26
Status: Accepted

## Summary

In the context of a chain whose only control on unattended work is a human
gesture per issue, facing an autopilot that would start issues and merge pull requests
unwatched, we decided on three gates plus a lane cap, merging by tree, a local guard and milestones
as ordered slices, to spend the human's attention only on judgment, accepting that the guard
is an accident guard, not a sandbox.

## Context

- **The control today is a human per issue.** **Rule B** runs the chain unattended and never
  starts the next issue; every merge is manual, by `CODEOWNERS` and branch protection, and
  `cleanup` starts from the human.
- **An autopilot is wanted**: each tick its picker starts the next startable issue and parks
  what needs a human — a loop the human starts and stops, not
  the CI pipeline [ADR-0048](0048-retire-the-ai-label-pipeline.md) retired, nor
  [ADR-0043](0043-scheduled-upstream-drift-watcher.md)'s case, a clock-fired job with no
  human in its trigger.
- **What each tree is to the flow.** Analysis and records are the spec; a design derives
  from merged analysis, an epic body from one approved slice of it, read by a human
  ([ADR-0044](0044-implementation-spec-lives-in-the-epic-body.md)).
  `.github/`, `.claude/`, `docs/reference/` and `CLAUDE.md` are the run's rules.
- **Merges run as the human's account.** An author cannot approve their own pull request, so
  the session merges with `gh pr merge --admin`, bypassing code-owner review and required
  checks; the platform has no rule keyed on label and files. Only commits carry a bot
  identity, used for nothing else.
- **Nothing orders the backlog**; `Ready` has no role.

## Considered options

### Where the human's control sits

#### Option A1 — Keep Rule B: the human starts every issue

- Pro: a human sees every issue.
- Con: the per-issue gesture is the ceiling.

#### Option A2 — Three gates plus a lane cap

Any open issue filed by a collaborator, with a context label whose row names a work file and
no open blocked-by edge, is startable; the human acts at three gates — a manual-merge tree's
merge, the epic-body read, verify live. The human starts and stops the loop, so a human is in its
trigger; at most two lanes, one issue's chain each, run at once on disjoint trees.

- Pro: attention goes to the spec, the slice and the installation, and only a collaborator's
  issue starts a run.
- Con: the per-issue veto goes; what is worked next is then set only by edges and order.
- Con: a machine starts ill-formed issues; a pre-flight catches only mechanical faults.

### What the autopilot may merge

#### Option B1 — Nothing: every merge stays manual

- Pro: the merge gate is untouched.
- Con: every pull request still waits: the ceiling.

#### Option B2 — By tree

All files under `custom_components/`, `tests/` or `docs/design/`, the head a branch of this
repository, `needs-approval` without `needs-decision`, CI green; any other tree waits.

- Pro: decided from diff, labels and head alone, over trees a human reads again later;
  outside work stays at the human's gate.
- Con: a design change reaches the flow's *approved* state without a human merge.
- Con: a fork's pull request never auto-merges.

### How the merge class is enforced

#### Option C1 — A second account: the bot approves and merges

- Pro: branch protection stays real.
- Con: a second account whose rubber stamp empties the code-owner rule.

#### Option C2 — A local guard: the PreToolUse hook refuses `gh pr merge` outside the class

The destructive-git guard refuses `gh pr merge` outside B2's conditions or without a squash;
merges run as the human, `--admin`.

- Pro: one rule in one script with tests, beside the guard it extends; one account,
  once the bot's last use, commit authorship, goes.
- Con: an accident guard, not a sandbox: it sees `gh pr merge` typed as such, not a wrapped
  shell or a raw API call.
- Con: commits stop carrying a bot author, which the chain never used.

### In what order issues are picked

#### Option D1 — Board order, tie-break smallest Size

- Pro: no new field.
- Con: insertion order says nothing about what ships first.

#### Option D2 — Milestones as ordered slices

One milestone per slice — of `project-plan.md`, or a method epic — ordered by a
numeric prefix in its title; an epic carries it, a child inherits it.

- Pro: native to issues and `gh`, assigned once per epic.
- Con: GitHub has no milestone order; the prefix is a hand-held convention, like branch
  names.
- Con: four stale milestones need ordering first, one roadmap session.

## Decision

**Options A2, B2, C2 and D2.**

A2 over A1, which keeps the gesture that is the ceiling; its second Con is accepted.

B2 over B1, which leaves the ceiling in place; its first Con is accepted on its Pro, its
second as that gate's price.

C2 over C1 because C1's account would rubber-stamp the rule C2 states once; its Cons are
the known limit and the bot's last use.

D2 over D1 because a picker needs an order somebody meant; its Cons are accepted.

One record, not four: A2 removes the per-issue gesture, so B2 must say what the run
finishes alone, C2 must hold B2, and D2 keeps the human's say on what is worked next; with D1
instead, A2's first Con is unbounded.

## Consequences

- **Rule B loses its chaining sentence**, keeping its stop.
- **`cleanup` runs from the autopilot's merge**.
- **Parking reuses the exit labels on issues**: `needs-approval` on an epic asks for a go,
  `needs-decision` asks a question; a marker in the parking comment stops a tick re-parking
  what the human answered.
- **The merge rule lives in the workflow's *Commit & push authorization***, which the guard
  mechanizes: the rule, head condition included, with tests; the profile lists the
  auto-merge trees and lane limit; a non-required check reaches the rule or is promoted.
- **The bot identity is retired.**
- **The picker holds the verify-live gate**: an epic's first child closing parks the epic
  with `needs-approval` and the verify-live list; no other child starts before its removal.
- **Milestones become the method's priority**, in **Issue conventions**; filing
  copies the epic's to the child, and an idea or routed bug ends on one.
- **The epic-body read becomes a work type.** A2 starts only an issue with a context label,
  so the parked read has to be one: a `decompose` label with its own row, one child per
  epic blocked by its artifact issues, keeping ADR-0044's single uncapped pass and parking
  the epic; on go, the children are filed. Epics carry an `epic` label the picker excludes.
- **ADR-0048 is narrowed** in two kept consequences: who applies the exit labels, and
  `CODEOWNERS`' justification by the manual gate alone; **ADR-0043** in its may-not-dispatch
  rule and its scheduled-automation constraint, which bind a job with no human in its
  trigger, not a human-started loop; narrowed, not superseded, as its decision stands for its
  own job.

**Blast radius.** One search, run from the repository root:

```sh
rg -n --hidden --glob '!.git/' \
  --glob '!docs/adl/**' --glob '!docs/postmortems/**' --glob '!docs/archive/**' \
  --glob '!docs/plans/**' --glob '!CHANGELOG.md' \
  -e 'Rule B\b' -e 'next issue' -e 'artifact-chaining' \
  -e '[Mm]erge is always manual|[Mm]anual merge|merged, manually|manually, by the maintainer|no Claude session can merge|never auto-merged|manual approval|auto-approve|auto-merge' \
  -e '[Mm]erge is the human|human may merge|human.s merge|watch for the merge|merge happened|human stating' \
  -e 'not yet standardized' -e '[Mm]ilestone' -e '`Ready`' -e 'approved (slice of )?`project-plan' \
  -e 'gh pr merge|block list is the one|[Dd]estructive git|Commit & push|commit/push authorization|first word|Table-driven test for block' \
  -e '[Bb]ranch protection|required (status )?checks?|hard\*\* gate|interactive_(cap|ceiling)' \
  -e 'bot account|kristofdegrave-bot' -e '"PR: ' -e 'one actor|one step that applies' \
  -e 'human-authored|names none|Narrowed by ADR-0050|through ADR-0051|\| 0043 \|' \
  -e 'manual-approval-before-merge|maintainer is the sole|never a self-approval|No other step or|says to go on|Size/Estimate, `Source:`' \
  -e '^  context:|^  enabled:|[Oo]ne row per (enabled )?(context label|entry)|one row each|`adr`, `uc`, `requirement`|`uc`, `requirement`, `adr`|`documentation` and `workflow`|^## Labels' \
  -e 'filed here|filed first|filed now|fresh-agent pass over|Running the pass|verified live before|next slice' \
  -e 'running its review pass|holds the mechanics|mechanics of running|closing step runs|runs before any child|run by the author|author of the merged slice' \
  -e '[Ii]nteractive (session|lifecycle)|non-interactive|[Ii]nteractive(-| )only|[Ii]nteractive sessions only' .
```

Wide enough because each part replaces a rule that names itself: Rule B, the manual merge and
`cleanup`'s trigger, the Design gate, milestones, `Ready`, the guard's scope and
authorization, branch protection, rows without a work file, the label vocabulary, the exit
labels' actor, the bot identity, the epic's filing and pass, verify live's holder and
author, the interactive qualifier, the cap's keys. **133** hits.

| Site | Today | Follow-up |
|---|---|---|
| `docs/reference/method/contribution-workflow.md:75`, `:76`; `.claude/skills/implement/SKILL.md:60` | Rule B forbids starting the next issue | The sentence goes |
| `docs/reference/method/contribution-workflow.md:4`, `:275`; `.claude/profile.yml:171`; `.claude/skills/implement/SKILL.md:8`; `.claude/skills/review/SKILL.md:8`; `.claude/skills/fix/SKILL.md:8` | Say interactive | Hold unattended |
| `CLAUDE.md:113` | Says interactive; `cleanup` starts from the human | Holds unattended; the autopilot's merge triggers it |
| `docs/reference/method/contribution-workflow.md:46`, `:215`, `:216`; `docs/reference/profile.md:34`, `:35`, `:55`; `.github/CODEOWNERS:2`, `:5` | Every merge is the human's, by branch protection | Narrowed |
| `docs/reference/method/contribution-workflow.md:54`, `:80`, `:81`; `.claude/skills/cleanup/SKILL.md:3`, `:9`, `:14` | Waits for the human's statement | Triggered by the autopilot's merge |
| `docs/reference/method/contribution-workflow.md:145` | Neither label replaces manual approval | The auto-merge class's merge condition |
| `docs/reference/method/contribution-workflow.md:136`, `:137`, `:142`; `docs/reference/method/ci-pipeline.md:142`; `.claude/profile.yml:71`, `:74` | A pull request's, with one actor | Widened to issues and the autopilot |
| `.claude/profile.yml:78`, `:114`, `:123`; `CLAUDE.md:30`; `docs/reference/method/ci-pipeline.md:93`; `docs/reference/method/contribution-workflow.md:282`, `:327`; `docs/reference/method/definition-of-done.md:123`; `docs/reference/profile.md:65`, `:73`; `docs/reference/work-types/README.md:52`; `.github/ISSUE_TEMPLATE/idea.yml:13` | Enumerate the context labels and rows | Gain `decompose`; `epic` joins the labels |
| `docs/reference/work-types/workflow/review.md:177`; `.claude/skills/submit-pr-review/SKILL.md:12`; `.claude/skills/review/SKILL.md:107` | Sole, non-negotiable manual gate | Narrowed |
| `docs/reference/method/ai-authoring.md:523`, `:524`; `.github/dependabot.yml:5` | Never auto-merge; Dependabot like any PR | Narrowed; Dependabot's stay manual |
| `docs/reference/method/idea-to-product.md:215`, `:416` | *Approved* gates the spec | Met by the auto-merge condition |
| `docs/reference/method/idea-to-product.md:156`, `:168`, `:183`, `:207`, `:210`; `.claude/skills/file-task-issue/SKILL.md:54`, `:63` | File the epic and its issues, run the pass, no milestone | Gain the `decompose` child, `epic` label and milestone |
| `docs/reference/method/definition-of-done.md:78`, `:92`, `:104`; `docs/reference/method/idea-to-product.md:480`, `:488`, `:490`, `:498` | Slice two waits for slice one's verify live by the merged slice's author | The picker parks the epic after its first child for the human |
| `.claude/skills/file-task-issue/SKILL.md:3`, `:50`; `docs/reference/method/idea-to-product.md:202`; `CLAUDE.md:115`; `docs/reference/method/decomposition-checklist.md:5`, `:101` | Hold the pass's mechanics, run by the closing step | Move to the `decompose` work file |
| `.github/workflows/ci.yml:90`, `:91`, `:133`; `docs/reference/method/ci-pipeline.md:163`, `:180` | Block only as branch protection's required checks | Reach the merge rule, or are promoted |
| `.claude/hooks/block-destructive-git.sh:2`, `:3`, `:4`, `:30`, `:38`, `:100`, `:294`; `.claude/hooks/test-block-destructive-git.sh:2` | Refuse and test destructive git on `git` segments | Gain the `gh pr merge` rule and its cases |
| `docs/reference/method/contribution-workflow.md:236`; `CLAUDE.md:18` | Frame the guard as destructive-git only | State the merge rule too |
| `docs/design/system-design.md:832`, `:891`, `:894` | Records through 0051; the 0043 and 0048 rows | Gain this record and its narrowings |
| `docs/reference/profile.md:23` | No separate bot account, for the interactive session | True once the identity goes; holds unattended |
| `docs/reference/method/idea-to-product.md:195` | Not yet standardized | Replaced by the milestone rule |
| `.claude/skills/implement/SKILL.md:3`, `:13`; `.claude/skills/review/SKILL.md:3`, `:14`; `.claude/skills/fix/SKILL.md:3`; `.claude/skills/resolve-review-thread/SKILL.md:3` | Interactive-only, with why | Widened to the unattended dispatch |
| `.claude/skills/clarify/SKILL.md:3`; `docs/reference/method/contribution-workflow.md:86` | Rule C sends decisions there; it blocks | Parks the question instead |
| `.claude/skills/research/SKILL.md:3`, `:17` | Refuses a run without grants | The dispatch states its grants |

24 hits conform: `use-case.yml:13`, `contribution-workflow.md:69`, `:91`, `:95`, `:112`, `.claude/profile.yml:175`,
`:177`, `:179`, `handoff/SKILL.md:11`, `:12`, `check-authoring-rules.sh:26`,
`check-method.py:103`, `ci.yml:6`, `:7`, `:12`, `:16`, `profile.md:49`, `CLAUDE.md:44`,
`work-types/README.md:134`, `model-selection.md:81`, `definition-of-done.md:34`,
`implement/SKILL.md:23`, `workflow/review.md:53`, `resolving-merge-conflicts/SKILL.md:20`.
Out of scope: 4 hits in `grilling/SKILL.md`, `diagnosing-bugs/SKILL.md` and
`improve-architecture/SKILL.md` keep refusing to run unattended; four `test-check-method.sh`
fixtures (`:40`, `:82`, `:90`, `:99`) keep feeding the method check a synthetic profile.
