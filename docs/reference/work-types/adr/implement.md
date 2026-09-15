# Work type: `adr` — how the work is done

Capture an architectural decision as a numbered, immutable Architecture Decision Record under
`docs/adl/`, per
[ADR-0001](../../../adl/0001-use-architecture-decision-records.md) — the decision to use ADRs
at all, and why the template looks the way it does.

This file is the `adr` row's work file in `CLAUDE.md`'s **Model selection** table. It carries
**how an ADR is written** and nothing else.

The worthiness test is not part of how an ADR is written: whether this decision should be an
ADR at all is answered when the issue is filed, and re-answered by the reviewer against the
completion bar's item 1, not while drafting.

## Drafting an ADR

- **Numbering** (part of the implement step, before drafting): the bar's item 2, *Template conformance*,
  defines the number and the filename and judges them. What that means while drafting: resolve
  the number *before* the branch exists, since the branch is named after it — and never reuse
  or renumber one. A superseded ADR keeps its number, which is why the highest existing number
  is the only safe thing to count from.
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
- **The implement step (draft)**: against `docs/adl/template.md` — Status, Context, **Considered options**
  (every option seriously evaluated, each with Pro/Con — not just the chosen one), Decision,
  Consequences.
- **The PR (closing the implement step)**: one PR per ADR — see **Rules** below.
- **Cross-check against existing ADRs and design docs**, before the review step: does this decision
  contradict an existing `Accepted` ADR? The bar's item 8, *It doesn't contradict an Accepted ADR without superseding it*, defines what the finished pair has to
  look like and judges it. What that means while drafting: go and look, before you have written
  a Decision that assumes nothing conflicts — the check is cheap then and expensive afterwards,
  and it is the step most often skipped.

## Rules

- **One problem, one decision per ADR** — the bar's item 7, *One problem, one decision*, states it and judges it. What that
  means while drafting: a design doc that bundles several architectural choices produces
  several ADRs, not one ADR carrying several decisions.
- **One PR per ADR.** No PR contains more than one ADR, or an ADR plus unrelated non-ADR work,
  even if they're closely related — file a separate issue and open a separate PR per ADR so
  each decision gets its own review. This doesn't cap an ADR at one PR outright: a genuine
  follow-up on the same ADR still follows the workflow doc's multi-PR convention for that
  issue. The ADL row (the bar's item 2, *Template conformance*) and any supersession Status-line edit
  belong to the same ADR's PR, not a separate one. The bar's item 2, *Template conformance*,
  is where the ADL row itself is judged.
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
    The reason is the drafting convention stated in the bar's item 10, *Status is `Accepted`
    before `needs-approval`*: under it, a working-tree read makes an ADR still being drafted
    look immutable. If the file doesn't exist on the base, or its
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
- **List the rejected options for real** — the bar's item 4, *The considered options are real*, states it and judges it. What that
  means while drafting: if you reach the Considered options section with only the option you
  chose, stop and name what else was on the table, even if it is just "do nothing" / "keep the
  status quo".
- **Reference, don't restate.** If a decision depends on a requirement or use-case, cite it
  (`R7`, `UC03`) rather than re-deriving it.

### Skills

The method skills this work file uses, by step: `research` for the facts an ADR's Context rests
on, cited from the record by linking the issue comment; `receiving-code-review` in the review
step. The stack skills are the overlays' to name.

## Common mistakes

- Skipping the issue-first step for a decision nobody has discussed yet.
- Editing an old ADR's Decision text instead of writing a new ADR that supersedes it.
- Bundling two ADRs, or an ADR plus unrelated work, into one PR.
- Drafting against this file alone and never opening `done.md` — the bar is where most of what
  a review will say already is.

## Overlays

**Apply the overlays** the profile's declared stacks provide for this work type:
`overlays/<stack>.md` beside this file, its **Implement** section read with this file as part of
the same work file. What an overlay is, what a file reading `none` means and what may not live in
this file are this tree's `README.md`'s **Stack overlays**.
