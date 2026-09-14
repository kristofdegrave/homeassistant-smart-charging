# ADR-0041: The CI reviewer reads its instructions from the base branch and its subject from the PR

Date: 2026-09-14
Status: Accepted

## Context

The AI review worker (`.github/workflows/_ai-review.yml`) no longer carries its own copy of
the path→agent routing. It resolves both halves of the routing rule — and, through it, every
checklist it applies — from `CLAUDE.md`'s **Model selection** section, and from whatever files
that section's columns name (`.claude/agents/*.md`, `.claude/skills/*/SKILL.md`, work-type
documents under `docs/reference/work-types/`).

On a `pull_request` run those files come from the PR's own merge ref. So does everything they
route onward to. That makes the review's *standard* and the review's *subject* the same tree,
and a pull request that edits one of those files edits the rule that is about to be applied to
it. The concrete shapes: a row rewritten to name a permissive file, a checklist rewritten to
drop the check the change would fail, a work-type document rewritten to redefine what "done"
means. None of these requires the model to misbehave — a reviewer that follows its instructions
faithfully is exactly what makes the rewrite effective.

Three forces pull against each other here.

- **Anything read from the merge ref is PR-controlled.** This is a property of the ref, not of
  any particular file, so a fix keyed on one file's name is a fix for one instance of the
  problem.
- **The subject has to come from the merge ref.** A review of the base branch reviews nothing.
  Whatever is done about the standard must leave the reviewed files alone.
- **Whether a protection held cannot be something the protected party reports.** The reviewer
  is a model given a prompt; a model that is truncated, distracted, or steered by content in
  the diff produces a report indistinguishable from a compliant one. Any invariant whose only
  evidence is the reviewer saying it held is not an invariant.

There is also a scoping force: the instruction sources are not a closed set. A checklist may
name further reading, and that further reading may sit anywhere in the repository. Whatever
boundary is drawn has to be enumerable by the workflow before the model runs, which means it
has to be drawn in terms of paths rather than of "everything the reviewer ends up reading".

`CLAUDE.md`'s **Architecture Decision Records** section keeps this inside the ADR bar: its
test/CI/dev-tooling carve-out explicitly does not reach the CI pipeline's own structure —
trust boundaries, job topology, review-loop caps.

## Considered options

### Option A — Leave it prompt-only

State in the reviewer's prompt that when the diff changes the routing or a checklist, it must
review against the base-branch version, and let the reviewer determine both that the condition
applies and that it complied. This is the shape the change that introduced the guard iterated
on for several review rounds before abandoning it.

- Pro: nothing to build and nothing to maintain. One file changes, the rule reads as a plain
  English sentence, and it adapts to cases a path list cannot express — the model can tell an
  unrelated hook edit from a rewritten checklist, which a path trigger cannot.
- Con: both halves are unverifiable. The condition has to be phrased against content ("if this
  diff modifies `CLAUDE.md`'s **Model selection** section"), and a heading is something a PR
  can rename, after which the honest reading is "no such section was modified" — the bypass the
  rule exists to prevent. And the compliance claim is the reviewer's own, so a run that read
  the checkout anyway reports exactly what a compliant run reports. A prompt-only rule also has
  nothing to point at: with no base copies on disk, "review against the base version" is an
  instruction the runner cannot carry out.

### Option B — Stage base copies of a declared path set; arm and verify the guard in the workflow

Before the model runs, a workflow step materialises the base-branch blobs of a declared set of
roots into the runner's temp directory, checks every copy it wrote against the base blob's own
size, computes from the changed paths whether the diff touches that set, and passes the answer
into the prompt as a fixed ON/OFF value. The prompt then routes every instruction read through
the staged directory when it is ON, and leaves the reviewed files coming from the checkout in
both cases.

- Pro: the trigger and the staging are facts the workflow computes and checks rather than
  claims the model makes, so the reviewer is never the party deciding whether its own guard
  held. An enumeration failure or a truncated copy fails the job; an unresolvable changed-path
  list fails towards ON. Declaring the set once and expanding it into both the staging loop and
  the trigger keeps staged a superset of watched by construction, which is what makes the ON
  branch's promise satisfiable at all.
- Con: it introduces a second boundary that has to be maintained — the watched set — and the
  prose copy of that set in `ci-pipeline.md` cannot interpolate the array, so it can drift. The
  trigger is coarser than the hazard: it fires on any change under the watched trees, so
  ordinary workflow PRs pay for a protection aimed at a narrow case. And it is explicitly
  partial — the workflow's own prompt, the action's unconditional load of the checkout's
  `CLAUDE.md`, and any standard a checklist names outside the watched roots all stay outside it.

### Option C — Always read instructions from the base branch, with no trigger

Stage the same copies, and have the reviewer read every instruction from them on every run.

- Pro: no trigger to get wrong, and no ON/OFF branch in the prompt for a model to mis-resolve.
  One provenance rule, stated once, holding for every PR — and since the staging step runs
  unconditionally under Option B anyway, it costs nothing extra per run.
- Con: it applies the base standard to PRs that have nothing to do with the boundary, which is
  the large majority. A checklist improvement merged today would not govern any PR until a
  second PR is opened against it, and a checklist correction could never be exercised by the
  change that makes it. It also removes the one signal that says a self-routing change happened
  at all: with no trigger, there is no note, and nothing tells the maintainer which PRs need
  the extra read.

### Option D — Human-only review of self-routing changes

When the diff touches the trees the review's instructions come from, skip the AI review and
route straight to `needs-approval`.

- Pro: no trust question remains, because no model reads PR-controlled instructions. It needs
  no staging, no verification, and no prompt branch — and the manual merge gate that stands
  behind every PR here already provides the human read.
- Con: the changes most in need of a checklist are the ones that would get none. Pipeline and
  authoring work in this repository almost always touches `.claude/`, `docs/reference/` or
  `CLAUDE.md`, so this withdraws automated review from a large and security-relevant slice of
  the traffic and replaces it with a maintainer reading a diff unaided — the condition the AI
  review loop exists to improve on.

## Decision

**Option B.** The reviewer's instructions come from base-branch copies, its subject comes from
the PR's checkout, and which of those applies is computed by the workflow from the changed
paths.

Option A fails on the third force in the Context: both its condition and its compliance are the
reviewer's own claims, and its condition is additionally anchored to a heading the PR can
rename. Option B's cost — a declared path set and a prose copy that can drift — is a
maintenance burden, which is a smaller category of failure than a guard that reports success
while not holding.

Option C's single rule is genuinely simpler, and its staging-cost argument is correct, but the
price it pays is that a merged instruction change cannot govern the PR that makes it, and that
nothing marks a self-routing PR for the maintainer. Option B keeps both by accepting a trigger.
Option D's "no trust question at all" is bought by withdrawing review from exactly the class of
change this project most wants reviewed.

Three properties follow from the reasoning above rather than being separate choices, and are
recorded here because each was reached by discarding a working alternative:

- **The trigger is path-computed, not content-judged.** Option A's phrasing problem is not
  fixed by phrasing it better — any condition expressed against document structure is a
  condition a PR can edit out. Paths cannot be renamed out of a diff.
- **The invariant is a checked workflow step, not a promise in the prompt.** Telling the
  reviewer to report a missing base copy as a finding makes the reviewer the judge of whether
  the guard held. The staging step compares each copy against the base blob's size and fails
  the job instead.
- **The note the reviewer opens with never decides the verdict.** A guard-ON run prefaces its
  summary with a note saying the instructions were taken from the base branch and the new
  version needs a human read. It is not a finding: it is not a defect, and there is nothing for
  the fix worker to do about it, so counting it would send every such PR through two no-op fix
  cycles before capping out. It also claims only what the workflow knows — a path trigger fired
  — and not that any routing or checklist was actually rewritten. The protection is the base
  copies; the note is a hand-off marker, and the `needs-approval` a clean verdict produces *is*
  the human read it asks for.

## Consequences

**The standing constraint this places on future checklists and work-type documents.** A
reviewer instruction is protected only if it lives under one of the watched roots —
`CLAUDE.md`, `.claude/`, `docs/reference/`, plus `.github/setup-labels.sh`, which is staged for
the superset invariant and is deliberately *not* an instruction source. An author who moves a
checklist, or points one at a standard, outside those roots silently leaves the boundary, and
nothing in CI will say so. So:

- A new checklist, work-type review document, or anything a checklist routes to *for how to
  review* belongs under a watched root. Putting it elsewhere is a decision about this boundary
  and needs a superseding record, not a file move.
- Changing the watched set means updating `ci-pipeline.md`'s **Review** bullet in the same
  change. A document cannot interpolate the array, so that copy is the one place the set can
  still drift.

**A property of the pair of workers, recorded because it is load-bearing and written nowhere
else.** The fix worker has no base-staging guard of its own, and does not need one: the set of
instruction sources it trusts is exactly the set a fix-reachable PR cannot modify. `CLAUDE.md`
and `.claude/**` are outside `docs/`, so a diff touching them routes to `needs-approval` rather
than `needs-work`; `docs/reference/work-types/**` routes there too, via the review worker's
`uncommittable_docs` check. A change to either of those routing rules re-opens this question
for the fix worker, and would need this record revisited.

**Follow-up this creates:**

- `docs/reference/ai-authoring.md`'s CI-worker checklist gains a line for the general rule: a
  worker prompt whose instructions are resolved from the PR's own merge ref must read them from
  base-branch copies when the diff touches the trees they come from, with the arming decided by
  the workflow from changed paths rather than by the model. The rule generalises past this one
  workflow and currently exists only inside it.
- The two standards a checklist routes to outside the watched roots — `docs/adl/template.md`
  and `docs/adl/0009-testing-strategy.md` — are read from the checkout, and the staging step's
  comment defers the question of widening the boundary to cover them to this record. This ADR
  does not widen it: `docs/adl/template.md` is the sharpest case precisely because a
  template-only PR routes to `adr-reviewer` and never arms the guard at all, so covering it is
  a different decision — arming on the tree a standard lives in, rather than on the trees the
  instructions themselves come from — and belongs in its own record. Until then, they are a
  known gap, not an oversight.
- `_ai-review.yml`'s staging comment can drop its forward reference to "the ADR that records
  this trust boundary" now that this record exists.

**What becomes harder.** Every review run pays a full base-tree enumeration and blob write for
the watched roots, and every change to the watched set is a two-file change. A PR touching any
watched tree carries a note in its review body whether or not it went near the routing.

**What this does not close**, stated so the boundary's edges are a limit rather than a
surprise:

- This workflow's own prompt is read from the merge ref, so a PR editing `_ai-review.yml`
  reviews itself with its own rewritten prompt. Only CODEOWNERS and the manual merge gate stand
  behind that.
- `claude-code-action` loads the checkout's `CLAUDE.md` in full on every run, so on a guard-ON
  PR the rewritten **Model selection** section is in the model's context regardless. The staged
  base copy mitigates the vector — the prompt names the base path as the one to resolve routing
  from — but does not close it.

**Blast radius** — every site this decision governs today, and whether each conforms.

The search: `grep -rnE 'anthropics/claude-code-action|base-checklists|_ai-\*\.yml'
.github/workflows/ docs/reference/ CLAUDE.md`. The first alternative is the action that runs a
model against a prompt, which is what makes a workflow an instruction consumer at all — keying
on `_ai-review.yml`, or on the word "guard", would name only the file that already implements
the boundary and would miss both sibling workers and any future one under a different name. The
second and third catch the places that describe the boundary, or the worker class as a class,
in prose — the copies that can drift away from the implementation. It returns six files.

| Site | What it does today | Conforms? |
|---|---|---|
| `.github/workflows/_ai-review.yml` | Stages base copies of the watched roots, verifies each against the base blob size, computes the ON/OFF trigger from changed paths, and routes instruction reads through the staged directory while reading the subject from the checkout | **Yes** — this is the implementation |
| `.github/workflows/_ai-draft.yml` | Runs from an issue against a checkout of the default branch; resolves its work file from `CLAUDE.md`'s table, which on that checkout is the merged copy | **Yes**, trivially — no PR ref is in play, so instruction and subject cannot be the same PR-controlled tree |
| `.github/workflows/_ai-fix.yml` | Checks out the PR head and resolves its instructions from `CLAUDE.md`, `.claude/**` and the work-type tree — all PR-controlled — with no base staging | **Yes**, by routing rather than by staging: a PR that can edit any of those never reaches this worker, per the property recorded above |
| `docs/reference/ci-pipeline.md` (**Review** bullet) | Prose copy of the watched set, the path-computed trigger, the staging verification, the fail-toward-ON behaviour, and the note's non-verdict status | **Yes** — and it is the copy this decision obliges a future change to the set to update |
| `docs/reference/ai-authoring.md` (**Checklist — authoring a CI worker prompt/config**) | Covers checklist selection, tool grants, turn ceilings, loop caps, untrusted PR content and third-party report containment; says nothing about where a worker's own instructions are read from | **No** — the checklist line is named as follow-up above |
| `CLAUDE.md` (**Authoring AI artifacts**) | Routes CI worker prompts to `ai-authoring.md` and states no provenance rule of its own | **Yes** — the routing is correct; the rule belongs in the file it routes to |

**Out of scope.** `.github/workflows/ai-pipeline.yml` is matched by none of the three patterns
and is not governed here: it triggers the workers and passes SHAs, and reads no instruction of
its own — it keeps doing exactly that. The two `docs/adl/` standards and the two structural
gaps named under *What this does not close* are likewise matched by no pattern; they keep
being read from the checkout and from the merge ref respectively, and are named above as a
known gap and as limits so that their absence from this table is stated rather than silent.
