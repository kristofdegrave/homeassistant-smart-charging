# Contribution workflow

Universal lifecycle for **every** unit of work in this repo — a doc, an ADR, a design, or
code. Five steps, each naming the skill an interactive session runs it through; the rules the
steps rest on follow the chain. The artifact-specific additions for analysis documents and ADRs
(`CLAUDE.md`'s **Review protocol for analysis documents** and **Architecture Decision Records
(ADRs)** topics) layer their own template/quality-check steps on top of this; they never
replace it.

Two related references cover the phases just outside this lifecycle: the stages either side of
it ([idea-to-product.md](idea-to-product.md) — the default flow from a captured idea, through
the artifact chain, to a slice verified on the real installation) and the **Definition of
Done** an author checks inside step 1, before the PR
([definition-of-done.md](definition-of-done.md), also covering commit message conventions) —
the project-wide floor, distinct from a row's per-type *completion bar*, which that document
routes to.

## The chain

0. **File the issue** (`file-task-issue`).
   - Every unit of work has an issue before work starts — no exception for small or
     typo-level changes.
   - If none exists yet, file one first, per **Issue conventions** below (context label, board
     fields). Board **Status** starts in the *backlog* column (**Project board** below).
1. **Implement** (`implement`).
   - Isolated `git worktree`, always, even for a one-line fix — a concurrent session switching
     branches underneath you is the risk it removes.
   - Branch per **Branch naming** (under **Issue conventions** below), cut from an up-to-date
     `origin/main` (**Base `main` and stacking** below).
   - Board **Status** → the *in progress* column when writing actually starts, not at filing
     time. The issue's epic, if it has one, moves there with it unless it already is — the
     child's start is the epic's start (**Project board** below; the parent read is
     [tracker-mechanics.md](tracker-mechanics.md)'s **Parent/sub-issue and blocked-by edges**).
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
     escalation comment handing the disagreement to the human partner; Critical or Major open
     with passes left, or a round self-granted → no label, the findings are the fix step's.
   - Board **Status** stays *in review*. Merge is the human's, always (**Merge and issue
     closing** below).
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
— screening findings before posting, or "checking the reviewer missed nothing" — the separation
is gone. A fresh **agent**, not a fresh session.

## Rule B — stop-and-report, per issue

The chain runs **unattended** from the step it is entered at: implement → review → fix →
review … → a clean pass or the cap, with no check-in between steps. The session stops at exactly
two points — a clean pass, or the cap with Critical or Major findings still open and no round
self-granted — both found by step 2 at the end of its pass, and reports.
It never starts the next issue off the back of the one that just finished; that is the control
on autonomous artifact-chaining, and it is per issue, not per step.

**Invoking a step skill enters the chain there.** `/implement #N` runs through to a clean pass
or the cap; "only this step" is something the human says explicitly. Step 4 is the one
exception: `cleanup` is triggered by the human stating that the merge happened, since the
session does not watch for the merge — no step dispatches it, and the skill itself guards
against a statement that turns out to be premature.

## Rounds and the cap

- **The cap exists because the chain runs unattended** (**Rule B**): a finding no fix
  resolves would otherwise loop without end.
- **One pass posts one review**, however many reviewer agents it ran. The first review pass is
  round 1.
- **The cap starts at `.claude/profile.yml`'s `review.interactive_cap`** review passes, counted
  from the most recent reset event. That key is the **only** statement of that number and this
  line the only statement of what it counts — everything that needs either routes here.
- **A clean pass** has nothing Critical or Major open; a pass whose remaining findings are all
  Minor/Nit counts as clean once they are fixed,
  so the final round needs no further pass to confirm it.
- **At the cap** — the last pass the count allows still has a Critical or Major finding open —
  the session **grants itself one more round** only when all three hold:
  - (i) the author agrees with every open Critical or Major finding;
  - (ii) no fix needs a decision that is the human partner's — a product choice, or a
    trade-off the spec does not settle;
  - (iii) each such finding comes from the original work, not from the previous round's own
    fix.

  The review step posts the grant as a PR comment giving why each condition holds, ending in
  the self-grant marker `<!-- local-review-self-granted -->`. Each such comment since the
  reset event raises the cap by one pass, never past `.claude/profile.yml`'s
  `review.interactive_ceiling` passes — that key is the ceiling's only statement.
- **Otherwise** — a condition fails, or the ceiling is reached — the loop stops instead of
  fixing again: the review step, at the end of that pass, puts the exit labels on (**Exit
  labels** below) and posts one escalation comment handing the disagreement to the human,
  who has **two decisions**: merge as is, accepting the open findings, or **grant another
  round** — a fresh count, since the escalation comment is itself the reset event. In-session
  they are asked through `grilling`. A grant is an instruction given to the session, never
  inferred from a thread or a default answer.
- **Rounds are counted from the most recent reset event**, of which there are exactly two
  kinds: an escalation comment — the one posted at the cap, or the one that puts a PR on hold
  (**Exit labels** below) — and a **human item** — a review, PR comment or review-thread reply
  by an author whose login does not end in `[bot]`, whose body carries none of the session's
  own markers (the local round marker, an `ai-fix-` marker, the escalation marker, the
  self-grant marker — a marked item is the session's footprint under the developer's own
  account, **Git identity** below), posted while an exit label was on: after its `labeled`
  event and before any later `unlabeled` one. Nothing else resets the count, a self-grant
  comment included; no reset event means counting from the PR's first review. This is the
  rule's only statement — the `review` skill's *Count the rounds* item is its one procedure.
  A round the human grants, or a human review, therefore never gets refused by a cap it did
  not ask for.

## Exit labels

`needs-approval` and `needs-decision` both mean **no automated review/fix work is pending, a
human decides**. `needs-approval` adds that a human may merge the PR **as it stands**, which is
why a hold takes it off; `needs-decision` adds that a reason not to merge is still open. Both exits have one actor: the **review step**, at the end of the pass it
just posted. After a clean pass it applies `needs-approval` alone, removing a stale
`needs-decision` if one is present. After the last pass the cap allows, with Critical or Major
still open and no round self-granted, it applies `needs-decision` **alongside**
`needs-approval` and posts the one escalation comment **Rounds and the cap** describes. So a capped PR is distinguishable from a
clean one in any list view while `needs-approval` keeps its single meaning. No other step or
skill applies either label; the one exception is the session putting a PR on hold (below).
Neither label replaces manual merge approval (**Merge and issue closing** below).

A human item (**Rounds and the cap** above) posted **while** either label is on makes it
false, and so does a round the human grants: both labels come off no later than the review step's
next pass — the `fix` skill's first step removes them when a human item precedes it, and the
review step's first act removes them whenever a reset event of either kind precedes its pass
and a label is still on (a grant given in-session posts nothing, so only the review step sees
it; a human item may reach the review step directly) — and that pass's exit re-applies
whichever is then correct.

**A blocking reason found after the exit puts the PR on hold.** When the session learns, before
the merge, that a PR carrying `needs-approval` should not merge as it stands:

- It takes `needs-approval` off, and puts `needs-decision` on alone. `needs-decision` alone
  means the PR is **on hold**: no automated work is running on it, and a human decides.
- It posts the reason on the PR as an escalation comment ending in the escalation marker. That
  comment is a reset event (**Rounds and the cap** above), so a round the human partner grants
  starts a fresh count. The label operations and the comment follow
  [tracker-mechanics.md](tracker-mechanics.md), as the review step's own exit does.
- It does no further work on the PR. The human partner either merges as is, or grants a round.
- On a granted round, the session's first act posts the hold reason as a PR review of its own:
  a `COMMENT` review whose body is the reason, carrying no marker. It is posted directly per
  [tracker-mechanics.md](tracker-mechanics.md), not through `submit-pr-review`, which
  adds the round marker. The round enters at **Fix** whichever step skill carried the grant,
  since the review step never reads human review bodies as findings. The fix step then reads it
  as it reads any human review body, and the chain runs on from **Fix**. Without a marker it
  also counts as a human item (**Rounds and the cap** above), which changes nothing: the grant
  has already started a fresh count. The session's reason
  is never the verdict (**Rule A**): the review step's next pass decides the exit.
- A concern that does not block the merge is filed as a follow-up instead, and the PR keeps
  `needs-approval`.

The session applies the hold itself, rather than asking the human partner to hold a PR that
still carries `needs-approval`.

## Thread discipline

- **Reply always.** Every finding addressed gets a reply on its thread describing what was done,
  or why not.
- **Resolve only what was actually fixed.** A disputed, deferred or partially addressed thread
  stays open, with the reply saying why.
- **Resolve after the push, never before.** A failed push would otherwise leave threads closed
  over work that is not on the branch.
- **Outdated is not resolved.** A thread the diff no longer shows is still open until it is
  resolved explicitly.
- **Out of scope is filed, not fixed.** A comment asking for something outside the PR's scope
  gets an issue instead (`file-task-issue`, context label per the artifact it belongs to,
  linked to the PR); the reply names the issue, and the thread is then resolved.

These five are the rule; `resolve-review-thread` applies them per thread, and
[tracker-mechanics.md](tracker-mechanics.md) holds the commands.

## Base `main` and stacking

The PR always bases `main` directly — never another work branch, even if logically stacked on
a not-yet-merged prior task, because this project's merge strategy — [profile.md](../profile.md)'s **Merge strategy** — orphans
stacked branches. Branching off a
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

**Merge is always manual** (how this project enforces that is [profile.md](../profile.md)'s
**Merge strategy**) — never auto-merged or self-approved. Merging auto-closes the linked issue
via the PR's `Closes #N` reference, or leaves it open if the PR only used `Part of #N`. Never close the linked issue directly (`gh issue close`), even on a
fully clean verification-only task — closing is left to that reference, which fires on merge.

**An epic's body is the spec, and its children are the tasks.** The spec doesn't implement
itself — the `development`/`testing` children are filed as part of the decomposition that wrote
the epic body — the closing step of the flow `CLAUDE.md`'s **Idea-to-product flow** topic
routes to — so the work actually gets picked up. Implementing each child is its own issue and its own chain.

**An epic is closed by the human partner, never by a PR or by `cleanup`.** Its gate is
[idea-to-product.md](idea-to-product.md)'s **Close** stage's, stated there and not here; of its
two conditions, step 4 establishes the first — every child closed — and never the second,
which is an observation on the real installation and the human's: `cleanup` reads the
epic's open-children count once the linked issue is *done*, and reports it; what the report says at zero is the skill's own step. It never
closes. Nothing watches for the moment otherwise: GitHub does not close a parent whose
sub-issues are all closed, and a child PR carries `Part of` for its epic precisely so a merge
cannot.

Step 4 removes the task's worktree because one left behind is a stale checkout nobody sweeps.

## Commit & push authorization

Commit and push freely, at any point during the work — no per-commit or per-push approval
needed. This is a standing authorization the project makes in this document; it does not
extend to anything destructive or hard to reverse (force-push, rewriting published history,
`git reset --hard`, etc.), which still follow the general ask-before-acting default. A
`PreToolUse` hook (`.claude/settings.json` → `.claude/hooks/block-destructive-git.sh`) refuses
the most common of those before they run.

## Project board

The chain above names four column **roles** — *backlog*, *in progress*, *in review*, *done* —
and never a column by its name on the board: the board's Status vocabulary and option ids are
`.claude/profile.yml`'s `board.fields.status`, and which column plays which role on this
project — including any column that plays none — is [profile.md](../profile.md)'s **Project
board**. The rule here is only that the chain moves an item **backlog → in progress → in
review → done** and through no other column: a column that later gains a defined meaning is
inserted explicitly into step 0/1 here rather than left implicit.

**An epic's Status follows its children** and takes the shorter path **backlog → in progress
→ done**: the session running step 1 moves it to *in progress* when its first child goes
there, it is never *in review* — nothing of its own is reviewed — and the human partner moves
it to *done* with the same hand that closes it, which step 4's open-children report is there
to prompt (**Merge and issue closing** above). A child starting under an epic already *in
progress* changes nothing.

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

Whose account the interactive session acts under is [profile.md](../profile.md)'s **Repository
and git identity**. What this chain relies on is only that it is **one account, shared with the
human partner** — which is why **Rounds and the cap** above tells a human item from the
session's own footprint by the session's markers, never by author.

## Issue conventions

- **Context label** matches the artifact type: `adr`, `uc`, `requirement`,
  `development`/`testing` (implementation tasks, **Task issues** below), `workflow` (CI/skill/agent-authoring
  changes), `documentation` (design-doc changes, `docs/design/**`). The label set itself — every name, colour and description,
  and which context labels this project enables — is `.claude/profile.yml`'s `labels` and
  `work_types`, and `.github/setup-labels.sh` writes it to the repository from there. Adding or
  renaming a label: see [ci-pipeline.md](ci-pipeline.md) for every place this vocabulary must
  stay in sync.
- **Kind-of-work labels** (`bug`, `enhancement`) are a **second, orthogonal axis**, not context
  labels. The context label says *which artifact* the work produces; the kind label says *why*
  the work exists — a defect in, or an improvement to, already-shipped behaviour. They are
  orthogonal because the fix for a defect is not always code: an entity-catalog row that claims
  a Read-by it does not earn is a `bug` whose fix lands in `docs/analysis/**`, and a stale
  minimum-HA declaration is a `bug` whose fix is neither. So an issue carries the kind label
  **alone** at the shipped-behaviour track's entry point, where the claim has not been verified
  and the fixing artifact is not yet known, and gains a context label once it is —
  [idea-to-product.md](idea-to-product.md)'s **Route** owns that track and its verify-first
  gate. Neither label substitutes for the other, and a kind label adds no Model-selection
  row.
- **Project-board fields**: always set **Size** (XS/S/M/L/XL) and **Estimate** (points) when
  filing an issue. Size a sweep/audit-shaped task (cross-file invariant check, full-suite run,
  cross-check an ADR) up at least one tier from raw effort — it takes more reading than the
  raw effort suggests. **Epics get Size only, never Estimate** — an epic's cost is the sum of
  its children's estimates.
- **Epic-first for multi-artifact strands**: see [idea-to-product.md](idea-to-product.md)'s
  **Decompose** stage for the full cycle (when to file the epic, what to file immediately vs.
  defer). The epic is the **parent issue** and each child is a **native sub-issue** of it; a
  child that cannot start until another finishes carries a **native blocked-by
  relationship**. Neither is body text —
  `gh` supports both directly, so nobody needs to re-derive them — the commands, and the
  read-backs that confirm an edge actually landed, are in
  [tracker-mechanics.md](tracker-mechanics.md).
  Child issue bodies still say "Part of #N" for the epic, never
  "Closes #N" (would auto-close the epic).
- **One extra condition on `needs-approval`**: a `requirement`/`uc` change that touches
  shipped behaviour also needs an epic whose body carries the spec to exist for it — see
  [idea-to-product.md](idea-to-product.md)'s **Analysis** stage, whose gate owns that
  condition and explains why the automatic label cannot enforce it.
- **Task issues** (`development`/`testing` label) are **children of the epic whose body
  carries the implementation spec**, and each one's body is its task — ADR-0044. So such an
  issue is filed as a native sub-issue of that epic, never standing alone: the parent edge is
  what says the body was cut from a decomposition somebody reviewed rather than typed straight
  into an issue. Get the edge on at filing time; adding it afterwards works
  (**Epic-first for multi-artifact strands** above has both forms).

**Branch naming**: `<context-label>/<issue-number>` — label is the issue's context label
(`adr`, `uc`, `requirement`, `development`, `testing`, `workflow`, `documentation`),
number is the GitHub issue number. **An issue carrying only a kind label** (`bug`,
`enhancement`) has no context label to name the branch, so the kind label itself is the
segment: `bug/<issue-number>` or `enhancement/<issue-number>` — the shipped-behaviour track's
defined segment. Earlier branches for *this* kind of work also used `dev/` and `fix/`; those
two spellings are historical, not alternatives (`development/<n>` keeps its own meaning above — a task cut from an epic). When both
axes are present the **context label wins**. If extra work on the same issue needs a second, separate
PR, suffix a third segment describing the split: `<context-label>/<issue-number>/<slug>`
(e.g. `development/142/followup`).

A context label's own work file — whatever `CLAUDE.md`'s **Model selection** table names in
its row — may override the number segment when there's a concrete reason to key the branch off
the artifact's own identity instead of the issue's. State the exception and its reason in that
file, don't leave it implicit here.

## Post-mortems

One dated analysis per shipped failure, at `docs/postmortems/YYYY-MM-DD-<slug>.md` — the tree
is listed under `CLAUDE.md`'s **Document structure** topic. What a post-mortem is, which rules
do not reach it, and how it is reviewed are this topic's.

### A snapshot of reasoning at a date

A post-mortem is a **snapshot of reasoning at a date**, not a source of truth for behaviour. It
is never kept current, never cited as the reason a rule exists (the rule's own reference doc
says that), and never consulted to answer "what does the system do" — the analysis docs own
that. Its job is to explain how a specific failure got past a specific process, so the changes
it recommends can be argued from evidence. Once those changes land, it stays as the record of
why and is not revised.

### Two rules that apply elsewhere do not apply here

- **Tracking refs are required, not forbidden.** `CLAUDE.md`'s *Review protocol for analysis
  documents* topic forbids PR numbers and issue statuses in analysis-doc and ADR bodies, because
  they rot. That rule does not reach this directory: a post-mortem's entire evidentiary value
  is the specific PRs, issues, commits and review comments it cites, at the dates it cites
  them — don't "fix" these.
- **It is not an analysis document.** The 6Cs/glossary-first protocol and the analysis
  tree's own review checklist do not govern it; it quotes the analysis docs as evidence
  rather than asserting behaviour.

### How it is reviewed

By a fresh-agent review run interactively, weighted toward **quotation
accuracy** — a post-mortem is an argument built entirely from quotes, so a quote that is
inaccurate, truncated in a way that changes its meaning, or mined out of a context that would
undercut the point is the defect class that matters. Pick the reviewer from what the PR
actually touches (the `workflow` checklist when it also edits `CLAUDE.md`).
No reviewer checklist is applied to the post-mortem itself: the checklists are all written
against artifacts that assert behaviour, and none fits a narrative document.
