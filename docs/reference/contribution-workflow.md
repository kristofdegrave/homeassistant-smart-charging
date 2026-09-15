# Contribution workflow

Universal lifecycle for **every** unit of work in this repo — a doc, an ADR, a design, or
code. Six steps, each naming the skill an interactive session runs it through; the rules the
steps rest on follow the chain. Artifact-specific sections in `CLAUDE.md` (analysis docs,
ADRs) layer their own template/quality-check steps on top of this; they never replace it. The
same lifecycle run by CI, with `github-actions[bot]` as the actor, is
[ci-pipeline.md](ci-pipeline.md).

Two related references cover the phases just outside this lifecycle: the stages either side of
it ([idea-to-issues.md](idea-to-issues.md) — idea, routing, spec, slicing into issues, and
verifying a shipped slice on the real installation) and the **Definition of Done** an author
checks inside step 1, before the PR ([definition-of-done.md](definition-of-done.md), also
covering commit message conventions) — the project-wide floor, distinct from a row's per-type
*completion bar*, which that document routes to.

## The chain

0. **Every unit of work has an issue before work starts.** If none exists yet, file one first
   (`file-task-issue`) — no exception for small or typo-level changes. Correct context label +
   Size/Estimate fields (see **Issue conventions** below). Board **Status** defaults to
   `Backlog`.
1. **Implement** (`implement`). Isolated `git worktree`, always, even for a one-line fix —
   it removes the shared-checkout risk of a concurrent session switching branches underneath
   you. Branch `<context-label>/<issue-number>` (see **Issue conventions** below) from an
   up-to-date `origin/main`, never a stale local `main`. Board **Status** → `In progress` when
   writing actually starts, not at filing time. Self-check against the
   [Definition of Done](definition-of-done.md), then push and open a PR against `main` — never
   another branch — referencing the issue with `Closes #N` or `Part of #N` (see **Base `main`
   and stacking** and **`Closes` and `Part of`** below). Board **Status** → `In review`.
2. **Review** (`review`). Count the rounds first (**Rounds and the cap** below), then run
   the pass against current `origin/main`. Fresh reviewer agents, never inline (**Rule A**
   below), one per checklist `CLAUDE.md`'s **Model selection** table resolves for the
   change. All findings go to the PR as one native review before anything is fixed.
3. **Fix, then re-review** (`fix`, then `review` again). Every finding gets a fix and a reply
   on its thread, or a reply saying why not, and its thread is closed out per **Thread
   discipline** below. Human PR comments, at any
   point, are findings like any other. Loop until a pass is clean, up to the cap (**Rounds
   and the cap** below). Still Critical or Major open at the cap → stop and escalate to
   the human partner.
4. **Approval** (`finalize-pr-review`). A clean pass → `needs-approval` (**Exit labels**
   below). Board **Status** stays `In review`. Merge is the human's, always.
5. **Clean up** (`cleanup`, invoked by the human after the merge). Verify the change is on
   `origin/main`, remove the task's worktree, board **Status** → `Done`. A merged `specs` PR:
   file its task issues (**Merge and issue closing** below).

## Rule A — author/reviewer separation

A change is judged by a **spawned reviewer agent**, never by the session that holds the
author's context. What corrupts a review is the *reviewer* carrying that context, not the
session: the session that wrote the work may run step 2, because it only dispatches to agents
that cannot see what it saw and relays what they return. The moment it judges the work itself
— screening findings before posting, or "checking the reviewer missed nothing" — the separation
is gone. A fresh **agent**, not a fresh session.

## Rule B — stop-and-report, per issue

The chain runs **unattended** from the step it is entered at: implement → review → fix →
review … → approval or escalation, with no check-in between steps. The session stops at exactly
two points — a clean pass (step 4) or the cap, found by step 2's count and ending step 3's
loop — and reports.
It never starts the next issue off the back of the one that just finished; that is the control
on autonomous artifact-chaining, and it is per issue, not per step.

**Invoking a step skill enters the chain there.** `/implement #N` runs through to approval or
escalation; "only this step" is something the human says explicitly. Step 5 is the one
exception: `cleanup` is invoked by the human, since the session does not watch for the merge.

## Rounds and the cap

- **One pass posts one review**, however many reviewer agents it ran. The first review pass is
  round 1.
- **The cap is 2 review passes**, counted from the most recent reset event (see below). This
  line is the **only** statement of the interactive cap — everything that needs the number
  routes here instead of repeating it.
- **A clean pass** has nothing Critical or Major open; a pass whose remaining findings are all
  Minor/Nit counts as clean once they are fixed — the same bar CI applies to its own verdict —
  so the final round needs no further pass to confirm it.
- **At the cap** with a Critical or Major finding still open, the loop stops instead of
  reviewing again: the exit labels go on (**Exit labels** below) and one escalation comment
  hands the disagreement to the human, who has **two decisions**: merge as is, accepting the
  open findings, or **grant another round**. A grant is an instruction given to the session,
  never inferred from a thread.
- **Rounds are counted from the most recent reset event**: the escalation comment posted
  at the cap, or a human review posted after an exit label. No reset event
  means counting from the PR's first review. A granted round or a human review therefore never
  gets refused by a cap it did not ask for.

## Exit labels

`needs-approval` and `needs-decision` both mean **no automated review/fix work is pending, a
human decides**. A clean pass applies `needs-approval` alone; the cap applies `needs-decision`
**alongside** `needs-approval`, so a capped PR is distinguishable from a clean one in any list
view while `needs-approval` keeps its single meaning. Neither replaces manual merge approval
(**Merge and issue closing** below).

A human review or PR comment posted **after** either label makes it false: the label comes off
(in step 3, before the fix), and the next pass's exit re-applies whichever is then correct.

`needs-draft`, `needs-review` and `needs-work` are CI's triggers and the human partner's
go-signal — an interactive session never self-applies them ([ci-pipeline.md](ci-pipeline.md)).

## Thread discipline

- **Reply always.** Every finding addressed gets a reply on its thread describing what was done,
  or why not.
- **Resolve only what was actually fixed.** A disputed, deferred or partially addressed thread
  stays open, with the reply saying why.
- **Resolve after the push, never before.** A failed push would otherwise leave threads closed
  over work that is not on the branch.
- **Outdated is not resolved.** A thread the diff no longer shows is still open until it is
  resolved explicitly.

These four are the rule; `resolve-review-thread` applies them per thread, and
[tracker-mechanics.md](tracker-mechanics.md) holds the commands.

## Base `main` and stacking

The PR always bases `main` directly — never another work branch, even if logically stacked on
a not-yet-merged prior task, because squash merges orphan stacked branches. Branching off a
prior task's branch locally is fine; the PR itself is `--base main` from the start, and the
new branch is still cut from a fetched `origin/main` — or, when deliberately stacking, from
the freshly fetched prior branch — never from a stale local `main`.

## `Closes` and `Part of`

The PR description references the linked issue with `Closes #<issue-number>` so merging
auto-closes it; if the issue needs more than one PR, use `Part of #<issue-number>` on every PR
except the one that finishes the issue. A task PR normally carries both — `Closes` for its own
task issue and `Part of` for the epic — and where anything needs to resolve a PR to one issue,
the `Closes` reference is the one that names it.

## Merge and issue closing

**Merge is always manual** (`CODEOWNERS` + branch protection) — never auto-merged or
self-approved; `needs-approval` only signals that no automated work is pending. Merging
auto-closes the linked issue via the PR's `Closes #N` reference, or leaves it open if the PR
only used `Part of #N`. Never close the linked issue directly (`gh issue close`), even on a
fully clean verification-only task — closing is left to that reference, which fires on merge.

**A merged `specs` issue produces task issues, not code.** Its approved plan doesn't implement
itself — file the `development`/`testing` task issues per [idea-to-issues.md](idea-to-issues.md)'s
**Ticket** stage (one per task, each with the anchored `Plan:` line) so the work actually gets
picked up. Filing them is part of finishing the spec issue, inside step 5; implementing them is
a new issue and a new chain.

Once merged, the task's worktree is removed as part of step 5 — the reason the step exists is
that a worktree left behind is a stale checkout waiting for a bulk sweep nobody schedules.

## Commit & push authorization

Commit and push freely, at any point during the work — no per-commit or per-push approval
needed. This is a standing authorization the project makes in this document; it does not
extend to anything destructive or hard to reverse (force-push, rewriting published history,
`git reset --hard`, etc.), which still follow the general ask-before-acting default. A
`PreToolUse` hook (`.claude/settings.json` → `.claude/hooks/block-destructive-git.sh`) refuses
the most common of those before they run — a backstop for this text, not a replacement for
it.

## Project board

Status field on the EMS project board (`gh project view 1 --owner kristofdegrave`) has 5
options: `Backlog`, `Ready`, `In progress`, `In review`, `Done`. `Ready` is unused today (not
part of this workflow) — the chain above only moves Backlog → In progress → In review → Done. If
`Ready` gets a defined meaning later (e.g. dependencies/contract resolved and pickable),
insert it explicitly into step 0/1 here rather than leaving it implicit.

## Parallel work and forward dependencies

Multiple tasks can proceed in parallel. When one task needs something a not-yet-built task
will produce (an entity, an event, a function signature), don't block and don't
invent/implement the missing piece. Pin down the **contract** instead — exact name/id, value
semantics/unit, a shared constant both sides code against — in the relevant
spec/`const.py`/ADR, and mark the producing side as a dependency for its own later task. The
producing task implements the real thing; the consuming task only adds the signature and
tests against a simulated/stubbed instance of the contract — never a private reimplementation
of the producer's logic.

## Git identity

Claude commits, comments, and opens PRs as the developer's own GitHub account — there is no
separate bot account for the interactive session.

## Issue conventions

- **Context label** matches the artifact type: `adr`, `uc`, `requirement`, `specs`
  (implementation spec: design + TDD plan, `docs/plans/**`), `development`/`testing`
  (implementation tasks against an approved plan), `workflow` (CI/skill/agent-authoring
  changes), `documentation` (design-doc changes, `docs/design/**` — reviewed, but not yet
  wired into automated drafting). Adding or renaming a label: see
  [ci-pipeline.md](ci-pipeline.md) for every place this vocabulary must stay in sync.
- **Kind-of-work labels** (`bug`, `enhancement`) are a **second, orthogonal axis**, not context
  labels. The context label says *which artifact* the work produces; the kind label says *why*
  the work exists — a defect in, or an improvement to, already-shipped behaviour. They are
  orthogonal because the fix for a defect is not always code: an entity-catalog row that claims
  a Read-by it does not earn is a `bug` whose fix lands in `docs/analysis/**`, and a stale
  minimum-HA declaration is a `bug` whose fix is neither. So an issue carries the kind label
  **alone** at the shipped-behaviour track's entry point, where the claim has not been verified
  and the fixing artifact is not yet known, and gains a context label once it is —
  [idea-to-issues.md](idea-to-issues.md)'s **Route** owns that track and its verify-first
  gate. Neither label substitutes for the other, and neither triggers anything on its own —
  only an action label does. A kind label adds no Model-selection row and no drafter `case`
  entry; see [ci-pipeline.md](ci-pipeline.md).
- **Project-board fields**: always set **Size** (XS/S/M/L/XL) and **Estimate** (points) when
  filing an issue. Size a sweep/audit-shaped task (cross-file invariant check, full-suite run,
  cross-check an ADR) up at least one tier from raw effort — it takes more reading than the
  raw effort suggests. **Epics get Size only, never Estimate** — an epic's cost is the sum of
  its children's estimates.
- **Epic-first for multi-artifact strands**: see [idea-to-issues.md](idea-to-issues.md) for
  the full cycle (when to file the epic, what to file immediately vs. defer). The epic is the
  **parent issue** and each child is a **native sub-issue** of it; a child that cannot start
  until another finishes carries a **native blocked-by relationship**. Neither is body text —
  `gh` supports both directly, so nobody needs to re-derive them — the commands, and the
  read-backs that confirm an edge actually landed, are in
  [tracker-mechanics.md](tracker-mechanics.md).
  Child issue bodies still say "Part of #N" for the epic, never
  "Closes #N" (would auto-close the epic).
- **One extra condition on `needs-approval`**: a `requirement`/`uc` change that touches
  shipped behaviour also needs a `specs` issue to exist for it — see
  [idea-to-issues.md](idea-to-issues.md)'s **Spec** stage, which owns that gate and explains
  why the automatic label cannot enforce it.
- **Task issues** (`development`/`testing` label) filed against an approved
  `docs/plans/<slice>.md` TDD plan must include an exact, anchored `Plan:` line identifying the
  plan file and task id (nothing else on that line) — see [ci-pipeline.md](ci-pipeline.md) for
  the required format and why it must be anchored. Get it right at filing time.

**Branch naming**: `<context-label>/<issue-number>` — label is the issue's context label
(`adr`, `uc`, `requirement`, `specs`, `development`, `testing`, `workflow`, `documentation`),
number is the GitHub issue number. **An issue carrying only a kind label** (`bug`,
`enhancement`) has no context label to name the branch, so the kind label itself is the
segment: `bug/<issue-number>` or `enhancement/<issue-number>` — the shipped-behaviour track's
defined segment, matching the `bug/<n>` branches such work already uses. Earlier branches for
*this* kind of work also used `dev/` and `fix/`; those two spellings are historical, not
alternatives (`development/<n>` keeps its own meaning above — a plan-pinned task). When both
axes are present the **context label wins**, so the branch matches what `_ai-draft.yml` would
compute from the same issue. If extra work on the same issue needs a second, separate
PR, suffix a third segment describing the split: `<context-label>/<issue-number>/<slug>`
(e.g. `development/142/followup`).

A context label's own work file — whatever `CLAUDE.md`'s **Model selection** table names in
its row — may override the number segment when there's a concrete reason to key the branch off
the artifact's own identity instead of the issue's. State the exception and its reason in that
file, don't leave it implicit here.
