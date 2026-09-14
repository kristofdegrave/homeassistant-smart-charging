# Work type: `adr` — how the work is done

Capture an architectural decision as a numbered, immutable Architecture Decision Record
(`docs/adl/NNNN-kebab-case-title.md`), per
[ADR-0001](../../../adl/0001-use-architecture-decision-records.md) — the decision to use ADRs
at all, and why the template looks the way it does.

This file is the `adr` row's work file in `CLAUDE.md`'s **Model selection** table. It carries
**how an ADR is written** and nothing else. Two things deliberately sit elsewhere:

- The lifecycle around the draft — issue, worktree, PR, review, fix, merge — belongs to the
  contribution workflow and is not re-derived here.
- *What must be true of a finished ADR* is the completion bar, `done.md`, named alongside this
  file in the same row and again in that row's review column. The author checks it before
  requesting review and the reviewer applies it, so it is written once for both. That includes
  the worthiness test — whether this decision should be an ADR at all is answered when the issue
  is filed and re-answered by the reviewer, not while drafting.

## Drafting an ADR

- **Numbering** (part of step 1, before drafting): next sequential integer after the highest
  existing `docs/adl/NNNN-*`, zero-padded to 4 digits. Never reuse or renumber; a superseded
  ADR keeps its number.
- **Branch naming exception** (the general rule this overrides is in the contribution workflow,
  which lets a context label's own work file override the number segment when that file states
  the exception and its reason — this is that statement): an ADR
  branches as `adr/<adr-number>` — its own zero-padded sequential number from the step above,
  not the issue number. Since that number comes from what's merged on `main` rather than a
  unique issue number, it isn't collision-free across concurrent ADRs: **only one ADR may be in
  flight (drafted but not yet merged) at a time.** Resolve the number before creating the
  worktree/branch, not after; CI does the equivalent in `_ai-draft.yml` right after checkout,
  and refuses (clears `needs-draft`, comments why) rather than clobbering if that branch
  already exists upstream.
- **Step 1 (draft)**: against `docs/adl/template.md` — Status, Context, **Considered options**
  (every option seriously evaluated, each with Pro/Con — not just the chosen one), Decision,
  Consequences.
- **Step 2 (PR)**: one PR per ADR — see **Rules** below.
- **Cross-check against existing ADRs and design docs**, before step 3: does this decision
  contradict an existing `Accepted` ADR? If so, this record supersedes it: set the new ADR's
  Status normally, and edit the *old* ADR's Status line only, to `Superseded by ADR-NNNN` —
  never rewrite the old ADR's Context/Decision/Consequences.

## Rules

- **One problem, one decision per ADR** — the bar's item 7 states it and judges it. What that
  means while drafting: a design doc that bundles several architectural choices produces
  several ADRs, not one ADR carrying several decisions.
- **One PR per ADR.** No PR contains more than one ADR, or an ADR plus unrelated non-ADR work,
  even if they're closely related — file a separate issue and open a separate PR per ADR so
  each decision gets its own review. This doesn't cap an ADR at one PR outright: a genuine
  follow-up on the same ADR still follows the workflow doc's multi-PR convention for that
  issue. The ADL row (the bar's item 2) and any supersession Status-line edit
  belong to the same ADR's PR, not a separate one.
- **Immutable once Accepted.** Never edit an Accepted ADR's Context/Decision/Consequences to
  reflect a change of mind — write a new ADR that supersedes it. This file is the only home
  for the **author and fix side** of the rule; a fix run reaches it through the `adr` row, so
  it never needs restating in a skill. The reviewer's side of it lives with the reviewer — in
  the files the `adr` row's review column names and in CI's review prompt — and is not a
  duplicate of this.
  Two guards, because the rule is easy to over-apply:
  - **Read "Accepted" from the base branch, not the working tree** — `git show <base>:<path>`,
    where `<base>` is the base commit the caller gives you (CI's prompt supplies it; locally,
    resolve the PR's base). A bare branch name may not resolve in a fresh checkout.
    Every ADR is drafted with `Status: Accepted` in its own PR, so a working-tree read makes an
    ADR still being drafted look immutable. If the file doesn't exist on the base, or its
    Status there isn't already `Accepted`, normal fixes apply. If the base **cannot be read at
    all** — no base ref fetched, the command unavailable — do not fall back to the working
    tree: treat the record as Accepted, which by the next guard means only a finding arguing
    the *decision* is wrong becomes **Skipped** — write-up findings are still fixed normally.
    Say in the summary that the base read failed. That is the loud failure of the two; a wrong
    Skipped entry is one a human reads and reverses, where a wrong edit rewrites an accepted
    decision with nothing to notice it.
  - **Only the *decision* is immutable, not the write-up.** A finding about a missing Con, a
    Decision that doesn't reference its options, or a Consequence that doesn't follow is fixed
    normally. Only a finding arguing an already-Accepted *decision* is wrong becomes a
    **Skipped** entry, recorded as a candidate for a superseding ADR.
- **List the rejected options for real** — the bar's item 4 states it and judges it. What that
  means while drafting: if you reach the Considered options section with only the option you
  chose, stop and name what else was on the table, even if it is just "do nothing" / "keep the
  status quo".
- **Reference, don't restate.** If a decision depends on a requirement or use-case, cite it
  (`R7`, `UC03`) rather than re-deriving it.

## Common mistakes

- Skipping the issue-first step for a decision nobody has discussed yet.
- Editing an old ADR's Decision text instead of writing a new ADR that supersedes it.
- Bundling two ADRs, or an ADR plus unrelated work, into one PR.
- Drafting against this file alone and never opening `done.md` — the bar is where most of what
  a review will say already is.
