---
name: write-adr
description: Use when making or changing any architectural decision in the Smart Charging project — a new ADR under docs/adr/, or superseding an existing one.
---

# Write an ADR

Capture an architectural decision as a numbered, immutable Architecture Decision Record
(`docs/adr/NNNN-kebab-case-title.md`), per `docs/adr/0001-use-architecture-decision-records.md`
(the decision to use ADRs at all, and why the template looks the way it does).

## Is this decision ADR-worthy?

Write an ADR when the choice is about **structure that would be expensive to reverse or
that materially constrains future options** — e.g. how integration entities map to
hardware, where a boundary/abstraction layer sits, a config-entry schema shape, a
library/protocol dependency, a change to the coordinator/control-loop structure.

Skip it for a variable name, a log message, or any implementation detail with no lasting
structural consequence. When in doubt: would a future contributor benefit from knowing
*why*, not just *what*? If yes, write the ADR.

## The cycle (do every step, in order)

0. **Open (or link) a GitHub issue** describing the decision to be made, before drafting.
   Skip this step only when the ADR merely documents a decision already approved in an
   issue/PR that exists (link it instead). Reference the issue in the eventual
   commit/PR (`Closes #N`). Branch as `adr/<issue-number>`, per CLAUDE.md's branch-naming
   convention.
1. **Number it** — next sequential integer after the highest existing `docs/adr/NNNN-*`,
   zero-padded to 4 digits. Never reuse or renumber; a superseded ADR keeps its number.
2. **Draft** against `docs/adr/template.md`: Status, Context, **Considered options**
   (every option seriously evaluated, each with Pro/Con — not just the chosen one),
   Decision, Consequences.
3. **Self-check** (no 6Cs pass — that check is for behavioral requirements/use-cases;
   an ADR's correctness is judged by whether its options and trade-offs are real, not by
   Clarity/Concision/etc.):
   - Context states the forces at play without presupposing the answer.
   - Every considered option has at least one genuine Pro and one genuine Con — an
     option with no real Con is a sign it wasn't seriously considered, or a real Con is
     being hidden.
   - Decision references the options' trade-offs rather than restating them.
   - Consequences names concrete follow-up (issues to open, docs to update), not just
     restating the decision.
4. **Cross-check against existing ADRs and design docs** — does this decision contradict
   an existing `Accepted` ADR? If so, this record supersedes it: set the new ADR's
   Status normally, and edit the *old* ADR's Status line only, to
   `Superseded by ADR-NNNN` — never rewrite the old ADR's Context/Decision/Consequences.
5. **Review** — spin up a dedicated, separate **Opus** agent (never review inline) to
   check: internal consistency of the ADR itself (do the stated Consequences actually
   follow from the Decision?), consistency with other ADRs and with `docs/analysis/**` /
   `docs/plans/**` docs it touches, and that no option was rejected without a stated Con
   that justifies it. Use a general-purpose agent, not `analysis-reviewer` — that agent
   is scoped to `docs/analysis/**` and doesn't cover `docs/adr/**`.
6. **Address** the review feedback.
7. **Manual review** — present the addressed draft to the human partner and get explicit
   approval before committing.
8. **Commit** (`docs: add ADR-NNNN <slug>`, or `docs: supersede ADR-000X with ADR-NNNN`),
   referencing the issue from step 0.
9. **Stop and report** status before starting the next document.

## Rules

- **One decision per ADR.** If a design doc bundles several architectural choices,
  split them into separate ADRs rather than one ADR with multiple unrelated decisions.
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
