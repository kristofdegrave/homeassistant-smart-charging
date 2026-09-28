# Contribution workflow

Universal lifecycle for **every** unit of work in this repo. Five steps, each naming the
skill an interactive session runs it through. The artifact-specific additions for analysis documents and ADRs
(`CLAUDE.md`'s **Review protocol for analysis documents** and **Architecture Decision Records
(ADRs)** topics) layer their own template and quality-check steps on top of this, never
replacing it.

Beside this lifecycle: the stages either side of it are
[idea-to-product.md](idea-to-product.md)'s, and the **Definition of Done** an author checks before
the PR is [definition-of-done.md](definition-of-done.md)'s.

## The chain

0. **File the issue** (`file-task-issue`).
   - Every unit of work has an issue before work starts — no exception for small or
     typo-level changes.
   - If none exists yet, file one first, per **Issue conventions** below (context label, board
     fields). Board **Status** starts in the *backlog* column (**Project board** below).
1. **Implement** (`implement`).
   - Isolated `git worktree`, always, even for a one-line fix. A row whose work file makes no branch or PR skips the
     worktree, push and PR — the `implement` skill's exception — and keeps *in progress* and
     *done*.
   - Branch per **Branch naming** (under **Issue conventions** below), cut from an up-to-date
     `origin/main` (**Base `main` and stacking** below).
   - Board **Status** → the *in progress* column when writing actually starts, not at filing
     time. The issue's epic, if it has one, moves there with it unless it already is
     (**Project board** below; the parent read is [tracker-mechanics.md](tracker-mechanics.md)'s
     **Parent/sub-issue and blocked-by edges**).
   - Self-check against the [Definition of Done](definition-of-done.md); then push and open
     the PR against `main`, referencing the issue (**Base `main` and stacking** and **`Closes`
     and `Part of`** below).
   - Board **Status** → the *in review* column.
2. **Review** (`review`).
   - Count the rounds first (**Rounds and the cap** below).
   - Run the pass against current `origin/main`.
   - Fresh reviewer agents, never inline (**Rule A** below), one per checklist `CLAUDE.md`'s
     **Model selection** table resolves for the change.
   - All findings go to the PR as one native review before anything is fixed.
   - Then the pass's exit, this step's alone (**Exit labels** below): a clean pass →
     `needs-approval`, with the PR confirmed to be based on `main`; Critical or Major still
     open on the last pass the cap allows, no round self-granted → both exit labels and one
     escalation comment; Critical or Major open
     with passes left, or a round self-granted → no label, the findings are the fix step's.
   - Board **Status** stays *in review*. Whose the merge is: **Merge and issue closing**
     below.
3. **Fix** (`fix`, then `review` again).
   - Every finding gets a fix and a reply on its thread, or a reply saying why not; threads
     close per **Thread discipline** below.
   - Human PR comments, at any point, are findings like any other.
   - Then the review step again, until a pass is clean or the cap ends the loop (**Rounds and
     the cap** below).
4. **Clean up** (`cleanup`, triggered by the human stating that the merge happened).
   - Verify the change is on `origin/main`; remove the task's worktree; board **Status** →
     the *done* column.
   - Then the issue's epic, if it has one: report its open-children count
     (**Merge and issue closing** below).

## Rule A — author/reviewer separation

A change is judged by a **spawned reviewer agent**, never by the session that holds the
author's context. What corrupts a review is the *reviewer* carrying that context, not the
session: the session that wrote the work may run step 2, because it only dispatches to agents
that cannot see what it saw and relays what they return. The moment it judges the work itself
— screening findings before posting, or checking the reviewer missed nothing — the separation
is gone.

## Rule B — stop-and-report, per issue

The chain **runs through** from the step it is entered at, with no check-in between steps:
implement → review → fix → review … → a clean pass or the cap. The session stops at two
points — a clean pass, or the cap with Critical or Major findings still open and no round
self-granted — both found by step 2 at the end of its pass, and reports; a run whose work file
opens no PR stops where that work file ends instead, and a run its dispatch says is unattended
has a third stop, the park `clarify` makes (**Rule C**).
It never starts the next issue off the back of the one just finished.

**Invoking a step skill enters the chain there.** `/implement #N` runs through to a clean pass
or the cap; "only this step" is something the human says explicitly. Step 4 is the one
exception (**The chain** above).

## Rule C — decisions go through `clarify`

A decision put to the human partner goes through `clarify`, which asks it or parks it — never
as a loose question in a status report. The one report form admitted is `clarify`'s: a
question with no issue to park on, in its shape.

## Rounds and the cap

- **One pass posts one review**, however many reviewer agents it ran. The first review pass is
  round 1.
- **The cap starts at `.claude/profile.yml`'s `review.interactive_cap`** review passes, counted
  from the most recent reset event. That key is the **only** statement of that number and this
  line of what it counts; everything that needs either routes here.
- **A clean pass** has nothing Critical or Major open; a pass whose remaining findings are all
  Minor/Nit counts as clean once they are fixed,
  so the final round needs no further pass to confirm it.
- **At the cap** — the last pass the count allows still has a Critical or Major finding open —
  the session **grants itself one more round** only when all three hold:
  - (i) the author agrees with every open Critical or Major finding;
  - (ii) no fix needs a decision that is the human partner's — a product choice, or a
    trade-off the spec does not settle;
  - (iii) each such finding comes from the original work, not the previous round's own fix.

  The review step posts the grant as a PR comment giving why each condition holds, ending in
  the self-grant marker `<!-- local-review-self-granted -->`. Each such comment since the
  reset event raises the cap by one pass, never past `.claude/profile.yml`'s
  `review.interactive_ceiling` passes — that key is the ceiling's only statement.
- **Otherwise** — a condition fails, or the ceiling is reached — the loop stops instead of
  fixing again: the review step, at the end of that pass, puts the exit labels on (**Exit
  labels** below) and posts one escalation comment handing the disagreement to the human,
  who has **two decisions**: merge as is, accepting the open findings, or **grant another
  round** — a fresh count, since the escalation comment is itself the reset event. A grant
  is an instruction to the session, never inferred from a thread or a default answer.
- **Rounds are counted from the most recent reset event**, of which there are exactly two
  kinds: an escalation comment — the one posted at the cap, or the one that puts a PR on hold
  (**Exit labels** below) — and a **human item** — a review, PR comment or review-thread reply
  by an author whose login does not end in `[bot]`, whose body carries none of the session's
  own markers (the local round, `ai-fix-`, escalation, self-grant and `clarify`'s
  `autopilot-parked` markers; [profile.md](../profile.md)'s **Repository and git identity**),
  posted while an exit label was on: after its `labeled` event and before any later
  `unlabeled` one. **Marker rule:** every session post carries one — a review's inline comments via its body,
  else `fix`'s note marker — bar the hold-reason review (**Exit labels** below); every
  comment the session posts on an issue carries one, `fix`'s note marker where no other
  fits, so a parked question's reader can tell the human's answer. Nothing else
  resets the count, a self-grant comment included; no reset event means counting from the
  PR's first review. This is the rule's only statement — the `review` skill's *Count the
  rounds* item is its one procedure.

## Exit labels

`needs-approval` and `needs-decision` both mean **no automated review/fix work is pending**.
On a PR, `needs-approval` adds that it may be merged **as it stands**, by a human or under the
merge rule; `needs-decision` adds that a reason not to merge is still open, for a human to
decide. Both PR exits have one actor: the **review step**, at the end of its pass. After a
clean pass it applies `needs-approval` alone, removing a stale `needs-decision`.
After the last pass the cap allows, with Critical or Major still open and no round
self-granted, it applies `needs-decision` **alongside** `needs-approval` and posts the one
escalation comment **Rounds and the cap** describes, so a capped PR is told from a clean one
and `needs-approval` keeps one meaning. No other step or skill applies either label to a PR,
bar the session putting one on hold (below), which a checklist's exit check can also do at the
exit.
Neither label is a merge (**Merge and issue closing** below).

On a PR, a human item (**Rounds and the cap** above) posted **while** either label is on makes it
false, and so does a round the human grants: both labels come off no later than the review step's
next pass — the `fix` skill's first step removes them when a human item precedes it, and the
review step's first act removes them whenever a reset event of either kind precedes its pass
and a label is still on (a grant given in-session posts nothing, so only the review step sees
it; a human item may reach the review step directly) — and that pass's exit re-applies
whichever is then correct.

On an **issue** the same two labels park work for the human, as ADR-0052 decided:
`needs-decision` is applied by `clarify`'s parking rule, in an unattended run,
and means a question waits for the human's answer; `needs-approval` on an epic asks for a go,
applied by the `decompose` row's work file.
The human takes an issue's label off; a run removes `needs-decision`, on an answer
that settles `clarify`'s park, and never an epic's `needs-approval`, whose removal is the human's
go. An issue's label says nothing about any PR.

**A blocking reason found after the exit puts the PR on hold.** When the session learns, before
the merge, that a PR carrying `needs-approval` should not merge as it stands:

- It takes `needs-approval` off, and puts `needs-decision` on alone. `needs-decision` alone
  means the PR is **on hold**: no automated work is running on it, and a human decides.
- It posts the reason on the PR as an escalation comment ending in the escalation marker. That
  comment is a reset event (**Rounds and the cap** above). The label operations and the comment follow
  [tracker-mechanics.md](tracker-mechanics.md).
- It does no further work on the PR; the human partner merges as is or grants a round.
- On a granted round, the session's first act posts the hold reason as a PR review of its own:
  a `COMMENT` review whose body is the reason, carrying no marker. It is posted directly per
  [tracker-mechanics.md](tracker-mechanics.md), not through `submit-pr-review`, which
  adds the round marker. The round enters at **Fix** whichever step skill carried the grant,
  since the review step never reads human review bodies as findings; the fix step reads it as
  any human review body, and the chain runs on. The session's reason
  is never the verdict (**Rule A**): the review step's next pass decides the exit.
- A concern that does not block the merge is filed as a follow-up instead, and the PR keeps
  `needs-approval`.

The session applies the hold itself rather than asking the human partner to.

## Thread discipline

- **Reply always.** Every finding gets a reply on its thread: what was done, or why not.
- **Resolve only what was actually fixed.** A disputed, deferred or partially addressed thread
  stays open, with the reply saying why.
- **Resolve after the push, never before.** A failed push would otherwise leave threads closed
  over work not on the branch.
- **Outdated is not resolved.** A thread the diff no longer shows stays open until resolved
  explicitly.
- **Out of scope is filed, not fixed.** A comment asking for something outside the PR's scope
  gets an issue instead (`file-task-issue`, context label per the artifact it belongs to,
  linked to the PR); the reply names the issue, and the thread is resolved.

These five are the rule; `resolve-review-thread` applies them per thread, and
[tracker-mechanics.md](tracker-mechanics.md) holds the commands.

## Base `main` and stacking

The PR always bases `main` directly — never another work branch, even one it is logically
stacked on, because this project's merge strategy ([profile.md](../profile.md)'s **Merge
strategy**) orphans stacked branches. Branching off a prior task's branch locally is fine; the
new branch is cut from a fetched `origin/main` — or, when deliberately stacking, from the
freshly fetched prior branch — never a stale local `main`.

## `Closes` and `Part of`

The PR description references the linked issue with `Closes #<issue-number>` so merging
auto-closes it; if the issue needs more than one PR, use `Part of #<issue-number>` on every PR
except the one that finishes the issue. A task PR normally carries both — `Closes` for its own
task issue and `Part of` for the epic — and `Closes` is the reference that resolves a PR to
one issue.

## Merge and issue closing

**Merge is the human's, except under the merge rule** (**Commit & push authorization** below;
its enforcement is [profile.md](../profile.md)'s **Merge strategy**) — never self-approved.
Merging auto-closes the linked issue via `Closes #N` (not via `Part of #N`); never close it
directly (`gh issue close`), even on a verification-only task. Only a `decompose` issue or an
idea, having no PR, is closed by the work file or skill that ran it, once its filings exist,
with a closing comment listing them ([tracker-mechanics.md](tracker-mechanics.md)'s **Closing
a work item**).

**An epic with a spec carries it in its body, and its children are the tasks**, filed by the
decomposition that wrote the body — the closing step of the flow `CLAUDE.md`'s
**Idea-to-product flow** topic routes to, which also says which epics have one. Each child is
its own issue, implemented in its own chain.

**An epic is closed by the human partner, never by a PR or by `cleanup`.** Its gate is
[idea-to-product.md](idea-to-product.md)'s **Close** stage's; of its two conditions, step 4
establishes the first — every child closed — and never the second, an observation on the real
installation, the human's: `cleanup` reads the epic's open-children count once the linked issue
is *done* and reports it; what the report says at zero is the skill's own step. It never closes.

## Commit & push authorization

Commit and push freely, at any point — a standing authorization this document makes, with no
per-commit or per-push approval. It does not extend to anything destructive or hard to reverse
(force-push, rewriting published history, `git reset --hard`, etc.), which keeps the
ask-before-acting default; a `PreToolUse` hook (`.claude/settings.json` →
`.claude/hooks/block-destructive-git.sh`) refuses the most common of those before they run.

**The merge rule.** A session runs `gh pr merge` only when all hold: `--squash`; the head a
branch of this repository, not a fork's; `needs-approval` on and `needs-decision` off; every
changed file under a tree in `.claude/profile.yml`'s `autopilot.auto_merge_trees`; every
check green, required or not. A push landing on `main` is a merge by another name, and
refused. The same hook mechanizes it and fails closed — its header is the authority on the
exact conditions — and any other PR is the human's.

## Project board

The chain above names four column **roles** — *backlog*, *in progress*, *in review*, *done* —
and never a column by its name on the board: the board's Status vocabulary and option ids are
`.claude/profile.yml`'s `board.fields.status`, and which column plays which role — including
any that plays none — is [profile.md](../profile.md)'s **Project board**. The rule here is
only that the chain moves an item **backlog → in progress → in review → done** and through
no other column; a column gaining a meaning is inserted into
step 0/1 here.

**An epic's Status follows its children** and takes the shorter path **backlog → in progress
→ done**: the session running step 1 moves it to *in progress* when its first child goes
there, it is never *in review*, and the human partner moves it to *done* with the same hand
that closes it, which step 4's open-children report prompts (**Merge and issue closing**
above). A `decompose` issue, having no PR, takes the same shorter path.

## Parallel work and forward dependencies

Tasks may proceed in parallel. When one needs something a not-yet-built task will produce,
neither block nor invent the missing piece: pin down the **contract** — exact name/id, value
semantics/unit, a shared constant both sides code against — in the relevant
spec/`const.py`/ADR, and mark the producing side as a dependency for its own later task.
The producer implements the real thing; the consumer adds only the signature and tests
against a stubbed instance of the contract, never a private reimplementation of the
producer's logic.

## Git identity

Whose account the interactive session acts under is [profile.md](../profile.md)'s **Repository
and git identity**. **Rounds and the cap** above relies only on its being **one account,
shared with the human partner**.

## Issue conventions

- **Context label** matches the artifact type: `adr`, `uc`, `requirement`,
  `development`/`testing` (implementation tasks, **Task issues** below), `workflow`
  (CI/skill/agent-authoring changes), `documentation` (design-doc changes, `docs/design/**`),
  `decompose` (an epic's body read, one per epic with a spec, none otherwise). The label set
  itself — every name, colour and description, and which context labels this project enables
  — is `.claude/profile.yml`'s `labels` and `work_types`, and `.github/setup-labels.sh` writes
  it to the repository. Adding or renaming a label: [ci-pipeline.md](ci-pipeline.md) lists
  every place this vocabulary must stay in sync.
- **Kind-of-work labels** (`bug`, `enhancement`) are a **second, orthogonal axis**, not context
  labels. The context label says *which artifact* the work produces; the kind label says *why*
  the work exists — a defect in, or an improvement to, already-shipped behaviour. An issue
  carries the kind label
  **alone** at the shipped-behaviour track's entry point, where the claim has not been verified
  and the fixing artifact is not yet known, and gains a context label once it is —
  [idea-to-product.md](idea-to-product.md)'s **Route** owns that track and its verify-first
  gate. Neither label substitutes for the other, and a kind label adds no Model-selection
  row.
- **The `epic` label** marks an epic — a parent tracking its children, not a unit of work — so
  an epic carries no context label and is never picked as a task. A kind label naming the
  epic's own work stays beside it (a bug-track epic keeps `bug`); `epic` adds no
  Model-selection row and makes no branch.
- **Project-board fields**: always set **Size** (XS/S/M/L/XL) and **Estimate** (points) when
  filing an issue. Size a sweep/audit-shaped task (cross-file invariant check, full-suite run,
  cross-check an ADR) up at least one tier from raw effort. **Epics get Size only, never Estimate.**
- **Epic-first for multi-artifact strands**: see [idea-to-product.md](idea-to-product.md)'s
  **Decompose** stage for the full cycle (when to file the epic, what to file immediately vs.
  defer). The epic is the **parent issue** and each child is a **native sub-issue** of it; a
  child that cannot start until another finishes carries a **native blocked-by
  relationship**, and the epic a blocked-by edge to each child — a convention for the UI,
  which lists its open work; nothing gates on it. Neither is body text; the commands and the
  read-backs that confirm an edge landed are in [tracker-mechanics.md](tracker-mechanics.md).
  Child issue bodies still say "Part of #N" for the epic, never
  "Closes #N".
- **Milestone** is the method's priority (ADR-0052): an ordered roadmap slice ranked by a
  numeric title prefix — lower first, unprefixed after every prefixed one — never a due date.
  Unprefixed milestones do not rank against each other: a picker facing a tie puts the choice
  to the human partner through `clarify` (**Rule C**). Within one milestone, between milestones
  sharing a prefix, or among unmilestoned issues, it takes the lowest-numbered (oldest)
  unblocked issue not labelled `epic`. The roadmap session is one the human partner holds to
  prefix every milestone; a new milestone stays unprefixed until then, and only the human
  partner reorders. An epic carries its milestone and filing copies it to each child routed to
  work. Every issue routed to work carries one; an `idea` issue and an unreproduced claim are
  not work yet ([idea-to-product.md](idea-to-product.md)'s **Decompose** and **Route** stages say
  when the work they become is placed). Whoever picks the next issue takes an unmilestoned
  issue routed to work last, never skips it. The `gh` flags are
  [tracker-mechanics.md](tracker-mechanics.md)'s **Filing a work item**.
- **One extra condition on `needs-approval`**: a `requirement`/`uc` change that touches
  shipped behaviour also needs an epic whose body carries the spec to exist for it — see
  [idea-to-product.md](idea-to-product.md)'s **Analysis** stage, whose gate owns that
  condition.
- **Task issues** (`development`/`testing` label) cut from a spec are **children of the epic
  whose body carries it**, each one's body its task — ADR-0044; a bug fix's are cut from none.
  Such an issue is a native sub-issue of that epic, its edge set at filing time or after
  (**Epic-first for multi-artifact strands** above has both forms).

**Branch naming**: `<context-label>/<issue-number>` — label is the issue's context label,
number is the GitHub issue number; a `decompose` issue makes no branch. **An issue carrying
only a kind label** (`bug`, `enhancement`) has no context label to name the branch, so the
kind label itself is the segment: `bug/<issue-number>` or `enhancement/<issue-number>` — the
shipped-behaviour track's defined segment. Earlier branches used `dev/` and `fix/`; both
spellings are historical, not alternatives (`development/<n>` keeps its meaning above). When
both axes are present the **context label wins**. If extra work on the same issue needs a
second PR, suffix a third segment describing the split: `<context-label>/<issue-number>/<slug>`.

A context label's own work file — whatever `CLAUDE.md`'s **Model selection** table names in
its row — may override the number segment for a concrete reason to key the branch off the
artifact's own identity rather than the issue's; state the exception and its reason in that
file.

## Post-mortems

One dated analysis per shipped failure, at `docs/postmortems/YYYY-MM-DD-<slug>.md` — the tree
is listed under `CLAUDE.md`'s **Document structure** topic. What a post-mortem is, which rules
do not reach it, and how it is reviewed are this topic's.

### A snapshot of reasoning at a date

A post-mortem is a **snapshot of reasoning at a date**, not a source of truth for behaviour. It
is never kept current, never cited as the reason a rule exists (the rule's own reference doc
says that), and never consulted to answer "what does the system do" — the analysis docs own
that. It explains how a specific failure got past a specific process; once its changes land, it
stays as the record of why.

### Two rules that apply elsewhere do not apply here

- **Tracking refs are required, not forbidden.** `CLAUDE.md`'s *Review protocol for analysis
  documents* topic forbids PR numbers and issue statuses in analysis-doc and ADR bodies. That
  rule does not reach this directory: a post-mortem's entire evidentiary value
  is the specific PRs, issues, commits and review comments it cites, at the dates it cites
  them.
- **It is not an analysis document.** The 6Cs/glossary-first protocol and the analysis
  tree's own review checklist do not govern it; it quotes the analysis docs as evidence
  rather than asserting behaviour.

### How it is reviewed

By a fresh-agent review run interactively, weighted toward **quotation
accuracy** — a post-mortem is an argument built entirely from quotes, so a quote that is
inaccurate, truncated so its meaning changes, or mined from a context that would undercut the
point is the defect class that matters. Pick the reviewer from what the PR
actually touches (the `workflow` checklist when it also edits `CLAUDE.md`).
No reviewer checklist applies to the post-mortem itself: all are written against artifacts
that assert behaviour, and none fits a narrative document.
