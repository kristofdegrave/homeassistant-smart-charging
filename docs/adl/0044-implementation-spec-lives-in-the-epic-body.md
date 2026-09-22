# ADR-0044: The implementation spec lives in its epic's body, and each task carries the sources it was cut from

Date: 2026-09-22
Status: Accepted

## Context

An implementation spec today is a pair of files under `docs/plans/` per slice — a `-design.md`
stating scope, decisions and test strategy, and a TDD plan listing the tasks. Each task issue
pins itself to its task with an anchored `Plan:` line, which a format check enforces and the
CI drafter parses to find the heading it must build the task prompt from. `specs` is a work
type with a label, a drafter case, a review checklist and a path-map entry.

Three forces bear on that shape.

**A plan is derived and ephemeral, but the tree keeps it forever.** The method already states
that a plan is never a source of truth: it restates what the ADRs, use-cases and requirements
decided, in the order one slice will build them. It is dead the day its last task merges. Yet
it merges into `main` and stays, and the tree is now the project's largest artifact class —
57 files. Being in the tree makes it behave like a source whether or not anyone intends it to:
one ADR's Blast radius table carries ten plan-file rows it has to reconcile, and five other
ADRs carry "plan-doc follow-up" items whose content is an accepted record telling a shipped
plan that it is now wrong. That bill is paid on every new ADR, forever, for files nobody will
read again. Two files per slice doubles it.

**The spec is reviewed as a diff, which is the wrong instrument.** A spec merges through the
same PR loop as everything else: reviewer, findings, fix, re-review, up to the review cap. But
the errors a per-file diff review is good at — a wrong restatement, a bad heading — are also
the errors the `development` reviewer catches later anyway, because it reads the task, the
analysis documents and the ADRs. What no per-task reviewer can ever see is what lives *between*
tasks: an in-scope requirement that no task implements, slicing by layer instead of by
behaviour, an order that cannot be built, a scope boundary drawn in the wrong place,
conventions that disagree across tasks. The loop costs rounds and catches the cheap half.

**The task end pulls the other way.** Today a worker is responsible for finding its own
sources. That makes a thin or wrong issue body harmless to correctness — the worker goes to the
documents regardless — at the price of re-deriving, on every task, a reading the decomposer
already did in full when it wrote the spec. Whether that cost should keep being paid is the
same question seen from the task's end, and the answer constrains where the spec lives: a spec
that is not a file has to reach the worker somehow.

## Considered options

Two option sets, because the decision has two ends: where the spec lives, and how a task learns
what to read. The second only has a live answer once the first is settled.

### Where the spec lives

#### Option A — Keep the file pair under `docs/plans/`

- Pro: no migration; the drafter's heading parser, the `Plan:` check, the `specs` label and its
  checklist all keep working; a spec is diffable and reviewable with the tools already built.
- Pro: a spec's engineering decisions that outlive the slice have somewhere obvious to sit.
- Con: pays the plan-rot bill in full and forever — every new ADR's Blast radius searches a tree
  of dead derived files, and accepted records accumulate follow-up items against them.
- Con: keeps reviewing decomposition with an instrument that cannot see between tasks, at the
  cost of a full round loop per spec.
- Con: two artifacts per slice where one would do, each able to drift from the other.

#### Option B — Keep the design file, move the task list into the children

- Pro: halves the tree; the task text stops being duplicated between a plan heading and an
  issue body, and the `Plan:` line and its parser go away.
- Pro: the durable half of a spec — scope, decisions, test strategy — keeps a reviewable home.
- Con: keeps the tree, so the blast-radius and follow-up bill is reduced rather than removed;
  a half-retired tree is still a tree that ADRs must search and reconcile.
- Con: splits one spec across two media, so the scope boundary lives in a file and the tasks
  that must respect it live in the tracker, with nothing keeping them in step.
- Con: leaves the review question unanswered — the surviving file is still diff-reviewed.

#### Option C — Move both into the tracker: the epic body is the spec, the children are the tasks

- Pro: removes the tree, and with it the standing blast-radius and follow-up bill on every
  future ADR.
- Pro: the spec and its tasks are one artifact in one medium, and the tracker already carries
  the edges — native sub-issues and blocked-by — that a build order needs.
- Pro: the drafter already receives the issue body, so a task reaches CI with no plan file, no
  anchored line, no format check and no heading parser.
- Pro: a body is not a diff, which forces the review question to be answered rather than
  inherited: one fresh-agent pass with a decomposition checklist, before the children are filed
  and while the decomposition is still cheap to change.
- Con: the spec is no longer versioned with the code, so how it changed is a tracker edit
  history rather than a commit.
- Con: `specs` stops being a work type, which costs a Model-selection row, a drafter case, a
  path-map entry and a checklist — a migration across every place the pipeline enumerates them.
- Con: a spec's engineering decisions that outlive its slice lose their default home, and must
  be pushed up into an ADR or accepted as living in a closed epic.
- Con: one review pass with no cap means a decomposition error that survives it is caught only
  by the human read that follows, or not at all.

### How a task learns what to read

#### Option D — The worker keeps hunting its own sources

- Pro: the standing rule, and the safe one: an issue body cannot damage correctness, because
  the worker consults the documents whatever the body says.
- Pro: nothing to maintain, and no judgement for the decomposer to get wrong.
- Con: saves nothing — the re-derivation the decomposer already performed is paid again on
  every task, which is the whole cost the move was meant to remove.
- Con: each worker's hunt is independent, so two tasks of one slice can read different
  documents and reach different conclusions with nothing to reconcile them.

#### Option E — The drafter fetches the epic body at draft time

- Pro: no per-child authoring; the parent is the single copy, so it cannot drift from the tasks.
- Con: widens the drafter's untrusted-data boundary from one issue's body to a second,
  separately-editable one, which is the boundary an accepted record deliberately drew narrow.
- Con: hands every task an entire spec to save it three lines, so each task's prompt carries
  the scope, decisions and test strategy of tasks it is not building.
- Con: reintroduces a fetch-and-parse step of exactly the kind retiring the `Plan:` line
  removed.

#### Option F — Each child carries the anchored sources it was cut from

- Pro: the decomposer has the reading in hand at the moment it writes the task, so recording it
  is free then and a full re-derivation later.
- Pro: a pointer, not the content: nothing is copied, so nothing can go stale except the anchor
  itself, which a check can resolve.
- Pro: the drafter's prompt stays the issue title and body, boundary unwidened, and no task is
  handed a spec.
- Con: issue bodies become load-bearing for correctness, inverting the rule that made a thin
  body harmless.
- Con: the decomposer owns a per-task completeness judgement whose misses fail silently — an
  under-pointed task yields an under-informed implementation, and nothing in the task itself
  shows the pointer set was short.
- Con: granularity is a judgement a check cannot make; an over-precise anchor looks tidier than
  the right one while being worse.

## Decision

**Option C and Option F.** The spec is the epic's body and each child's body is one task; each
child carries anchored `Source:` lines naming the documents it was cut from; the decomposition
is reviewed once, by a fresh agent with a decomposition checklist, before the children are
filed. `docs/plans/**` and the `specs` work type are retired.

C over A because A's decisive Con is not a one-off migration cost but a recurring one: the
blast-radius and follow-up bill A pays is charged to every future ADR, and it buys files that
the method itself says are never a source of truth. C over B because B reduces that bill
without removing it — a half-retired tree is still searched and still reconciled — and because
B's own Con, one spec split across two media with nothing keeping the halves in step, is a new
defect A did not have. C's Cons are accepted on their terms: losing commit-versioning is the
price of an artifact that was never meant to be durable, and the migration is finite where A's
bill is not. The engineering-decision Con is the one genuinely unresolved trade — such a
decision goes to an ADR when it meets that bar, and otherwise stays in the epic body, which is
no worse than the plan file it sits in today.

The review shape follows from C's fourth Pro rather than being chosen separately: once the spec
is a body, the diff loop is not available, and the loop was in any case aimed at errors the
`development` reviewer catches downstream. What replaces it is aimed at the errors nothing else
can see — the between-task class named in the Context. The uncapped single pass is C's last
Con, accepted because the pass is followed by a human read and because a capped loop over a
body would recreate the cost it removes.

F over D because D's second Con is the one that decides it: D saves nothing, and the saving was
the point. F over E because E's first Con crosses a boundary an accepted record drew on
purpose, and its second gives every task the whole spec to avoid writing three lines. F's own
Cons are taken as the terms of the trade rather than as objections: the inversion is real and
is what makes the decomposer's judgement load-bearing, which is precisely why the decomposition
gets its own review pass, and why that pass's checklist must judge anchor granularity — the
Con a check cannot cover. The silent-miss Con is bounded by an escape rather than removed: a
worker whose anchors do not answer what its task requires goes and finds the rest, and reports
in its PR that it did, so a decomposer's misses surface instead of being absorbed.

Two ends of one decision, one record. Splitting them would produce two ADRs each citing the
other at every turn, and each appearing in the other's Blast radius.

## Consequences

**The sources rule, stated for the worker.** A child of a decomposition carries `Source:` lines
— anchored at line start, one per line, nothing else on the line, the retired `Plan:` line's
proven shape — naming the documents it was cut from. Those lines replace the worker's own
source-hunt. They are provenance, never a discovery result: they never satisfy a work file's
own search obligation, and a `Source:` line is not a hit of an ADR's Blast radius search, which
stays a from-scratch re-runnable search. Targets are documentation paths only — not issues,
which have native edges, and not code paths. The anchor is optional under a smallest
self-contained-unit rule. The rule binds every child of a decomposition and no issue filed
outside one, where nobody determined the sources in advance and the work file's instruction to
go and find them is correct.

**What becomes easier.** A new ADR's Blast radius no longer searches a tree of dead derived
files, and no accepted record acquires a follow-up item against a shipped plan. A slice is one
artifact instead of three. A task reaches CI with no anchored line to check, no plan file to
fetch and no heading to parse. A worker starts from a named reading rather than from a hunt.

**What becomes harder.** A decomposition's quality now rests on one pass and a human read, with
no rounds to recover in. An issue body is load-bearing, so a thin one is a correctness defect
rather than an inconvenience. A spec's history is a tracker edit log, not a diff. A spec's
durable engineering decisions need a deliberate home — an ADR when they meet its bar — or they
close with the epic.

**Follow-up.** The `specs` work type is retired from the Model-selection table, the profile's
work types, labels and path map, the drafter's cases and the review and pipeline path filters;
its work-type directory is deleted. The method documents merge the Spec and Ticket stages into
one closing step and drop the `docs/plans/` tree from the document structure. The decomposition
checklist is written, reachable from the routing table, and carries an item for anchor
granularity. The skills that name a plan file or the `Plan:` line move to the epic body and the
decomposition pass. Durable documents that cite a plan file have that citation folded inward.
Plans of shipped slices are deleted; a plan whose epic is still open stays until that epic
closes, and is deleted then.

**Blast radius.** Search:

```
rg -n "docs/plans|\bspecs\b|^Plan:" CLAUDE.md .claude .github docs
```

Wide enough because the decision retires three separately-named things and no one name reaches
the others: keying only on `docs/plans` drops the label, the work type, the Model-selection row
and the drafter case, none of which mention the tree; keying only on `specs` drops the tree and
the anchored line; `^Plan:` is the line's own proven shape, and matching it unanchored would
sweep every prose sentence containing the word. The unquoted word alternative is deliberate
over a backtick-quoted one: the method documents discuss the work type in plain prose as often
as in code spans, and narrowing to the span form would drop those. It catches generic English
"specs" as well, accounted for below rather than excluded by narrowing.

70 files match today. Every one of them either restates the retired shape or lives in the
retired tree, so the table has no conforming rows; they are grouped by what has to happen to
them.

| Sites | What they do today | Verdict |
|---|---|---|
| **Pipeline enumerations** (9): `CLAUDE.md`, `.claude/profile.yml`, `.github/workflows/_ai-draft.yml`, `.github/workflows/_ai-review.yml`, `.github/workflows/ai-pipeline.yml`, `.github/check-method.py`, `.github/test-check-method.sh`, `.github/ISSUE_TEMPLATE/idea.yml`, `.github/CODEOWNERS` | Carry the `specs` row, label, drafter case, `docs/plans/**` path entry, `Plan:` checks and heading parser, and the tree's code owner | Does not conform |
| **Method documents** (19), all under `docs/reference/`: `method/idea-to-product.md`, `method/contribution-workflow.md`, `method/definition-of-done.md`, `method/ci-pipeline.md`, `method/model-selection.md`, `method/ai-authoring.md`, `profile.md`, `work-types/README.md`, `work-types/specs/implement.md`, `work-types/specs/done.md`, `work-types/specs/review.md`, `work-types/uc/implement.md`, `work-types/uc/done.md`, `work-types/uc/review.md`, `work-types/development/implement.md`, `work-types/development/review.md`, `work-types/adr/review.md`, `work-types/documentation/project-plan/implement.md`, `work-types/documentation/system-design/implement.md` | Describe the spec as a file pair under `docs/plans/`, send an author to "the plan task", or file gaps as `specs` issues | Does not conform |
| **Skills** (4): `.claude/skills/cleanup/SKILL.md`, `.claude/skills/work-idea/SKILL.md`, `.claude/skills/grilling/SKILL.md`, `.claude/skills/resolving-merge-conflicts/SKILL.md` | Name the `specs` label, the `specs` work file, or a plan file as the artifact a step produces or resolves | Does not conform |
| **Durable documents citing a plan file** (14): `docs/adl/0012`, `0015`, `0020`, `0022`, `0023`, `0024`, `0027`, `0028`, `0029`, `0041`, `0042`, `docs/analysis/entity-catalog.md`, `docs/design/project-plan.md`, `docs/design/system-design.md` | Lean on a plan file for a rationale, carry a "plan-doc follow-up" item against one, or list `docs/plans/**` among the reviewed trees | Does not conform |
| **The retired tree** (22 of the 57 files under `docs/plans/`) | Are the spec files themselves, or cross-reference each other | Does not conform |

Out of scope (2):

- `docs/postmortems/2026-09-11-four-live-behaviour-defects.md` — a post-mortem is a dated
  snapshot of reasoning and never a source of truth, so it keeps its text unchanged, plan-file
  names and all, exactly as it keeps every other fact that was true on its date.
- `.claude/skills/domain-driven-design/references/strategic-design.md` — a vendored reference
  whose single hit is the English word "specs" in an outsourcing-decision table, unrelated to
  the work type. It keeps saying what it says.

This record is itself the 71st hit of the search once it lands, and conforms by construction:
it names the retired shape only to retire it.
