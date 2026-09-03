---
name: write-adr
description: Use when making or changing any architectural decision in the Smart Charging project — a new ADR under docs/adl/, or superseding an existing one.
---

# Write an ADR

Capture an architectural decision as a numbered, immutable Architecture Decision Record
(`docs/adl/NNNN-kebab-case-title.md`), per `docs/adl/0001-use-architecture-decision-records.md`
(the decision to use ADRs at all, and why the template looks the way it does).

Follows this project's contribution workflow, defined in `CLAUDE.md` (issue → worktree → PR →
review → fix/resolve → merge). This skill covers only what's specific to an ADR — don't
re-derive the universal steps here.

## Is this decision ADR-worthy?

See `CLAUDE.md`'s "Architecture Decision Records (ADRs)" section for the worthiness test
(structure that's expensive to reverse or materially constrains future options — vs. a
variable name or log message with no lasting structural consequence), its calibration
test for borderline cases, and its two carve-outs (test/CI/dev-tooling choices;
domain/business rules) — check those before drafting, not just the headline definition.

## ADR-specific additions to the workflow

- **Numbering** (part of step 1, before drafting): next sequential integer after the
  highest existing `docs/adl/NNNN-*`, zero-padded to 4 digits. Never reuse or renumber; a
  superseded ADR keeps its number.
- **Branch naming exception** (see `CLAUDE.md`'s Contribution workflow section for the
  general branch-naming rule this overrides): an ADR branches as `adr/<adr-number>` — its
  own zero-padded sequential number from the step above, not the issue number. Since that
  number comes from what's merged on `main` rather than a unique issue number, it isn't
  collision-free across concurrent ADRs: **only one ADR may be in flight (drafted but not
  yet merged) at a time.** Resolve the number before creating the worktree/branch, not
  after; CI does the equivalent in `_ai-draft.yml` right after checkout, and refuses
  (clears `needs-draft`, comments why) rather than clobbering if that branch already
  exists upstream.
- **Step 1 (draft)**: against `docs/adl/template.md` — Status, Context, **Considered
  options** (every option seriously evaluated, each with Pro/Con — not just the chosen
  one), Decision, Consequences.
- **Step 2 (PR)**: one PR per ADR — see **Rules** below.
- **Self-check**, before step 3's review (no 6Cs pass — that check is for behavioral
  requirements/use-cases; an ADR's correctness is judged by whether its options and
  trade-offs are real, not by Clarity/Concision/etc.):
  - Context states the forces at play without presupposing the answer.
  - Every considered option has at least one genuine Pro and one genuine Con — an
    option with no real Con is a sign it wasn't seriously considered, or a real Con is
    being hidden.
  - Decision references the options' trade-offs rather than restating them.
  - Consequences names concrete follow-up (issues to open, docs to update), not just
    restating the decision.
  - `docs/adl/README.md` (the ADL) has a new row for this ADR, and the number matches
    the numbering step above — the reviewer checks both and will raise a finding if
    either is missing.
- **Cross-check against existing ADRs and design docs**, before step 3: does this
  decision contradict an existing `Accepted` ADR? If so, this record supersedes it: set
  the new ADR's Status normally, and edit the *old* ADR's Status line only, to
  `Superseded by ADR-NNNN` — never rewrite the old ADR's Context/Decision/Consequences.
- **Step 3's reviewer**: `adr-reviewer`. It checks template conformance, that every
  option has a genuine Pro and Con, that the Decision references those trade-offs, that
  Consequences actually follow, and cross-ADR consistency (including the immutability
  rule). Don't use `analysis-reviewer` — that agent is scoped to `docs/analysis/**` and
  doesn't cover `docs/adl/**`.

## Rules

- **One problem, one decision per ADR.** Each ADR addresses exactly one problem and
  records exactly one decision. If a design doc bundles several architectural choices,
  split them into separate ADRs rather than one ADR with multiple unrelated decisions.
- **One PR per ADR.** No PR contains more than one ADR, or an ADR plus unrelated non-ADR
  work, even if they're closely related — file a separate issue and open a separate PR
  per ADR so each decision gets its own review. This doesn't cap an ADR at one PR
  outright: a genuine follow-up on the same ADR still follows the workflow doc's
  multi-PR convention for that issue. The ADL row (see the Self-check bullet above) and
  any supersession Status-line edit belong to the same ADR's PR, not a separate one.
- **Immutable once Accepted.** Never edit an Accepted ADR's Context/Decision/Consequences
  to reflect a change of mind — write a new ADR that supersedes it.
- **List the rejected options for real.** An ADR whose only "considered option" is the
  one that was chosen isn't using the template — go back and name what else was on the
  table, even if it's just "do nothing" / "keep the status quo".
- **Reference, don't restate.** If a decision depends on a requirement or use-case,
  cite it (`R7`, `UC03`) rather than re-deriving it.

## Common mistakes

- Skipping the issue-first step for a decision nobody has discussed yet.
- An option with no genuine Con (usually means the alternative wasn't actually explored).
- Editing an old ADR's Decision text instead of writing a new ADR that supersedes it.
- Bundling two independent structural choices into one ADR.
- Bundling two ADRs, or an ADR plus unrelated work, into one PR.

