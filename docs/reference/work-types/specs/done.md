# Work type: `specs` — the completion bar

This file states *what must be true of a finished spec* — the design doc and its paired TDD plan
together, since a plan inconsistent with its own design fails item 3 whichever of the two is
wrong. How a spec is written — the drafting order, the scoping step, the cut test — is
`implement.md`. How a review is conducted — what to read first, how to anchor findings, the
output format, and the checks that are about the *change* rather than the documents — belongs
with the reviewer.

There is no 6Cs pass here. That check is for the behavioural requirements and use-cases a spec
**cites**; a spec's own correctness is judged by whether it derives faithfully and anchors its
tests, not by Clarity/Concision/etc.

## The bar

**(1) Derivation, not invention.** Every task maps to a service already named in
`docs/design/system-design.md` §3 and a task in `docs/design/project-plan.md` §5. A service,
call direction, or volatility the spec introduces that is not already in the design is
**Major** — the derivation must be mechanical, and the fix is an issue against the design doc,
not a paragraph here. The build order matches `project-plan.md`'s (Resource Access / Engines
before the Managers / Clients that depend on them), and no task depends on a caller of its
own — a departure from that order is **Major**.

**(2) Behavior is cited, not restated.** Behavioral rules (formulas, thresholds, resolution
order, R-numbers) are attributed to their owning analysis doc as **test anchors**, not
re-derived as if the spec owned them. A restatement that could drift from `control-cycle.md` /
`resolution-rules.md` / `requirements.md` is **Major**.

Before reporting a restatement, read the owning doc and check it says the same thing. Two
cases are not restatements at all:

- **It says something different** — **Critical**. The spec cannot resolve the conflict and the
  owning doc must.
- **No analysis doc says it** — the plan holds the only copy, so this is a **gap in that doc
  (Major)**, reported against it. Never a recommendation to delete the text here, and never a
  finding the author resolves by cutting it. A `D-n` decision, a file layout, a signature or a
  test boundary appears only in the plan by construction; that is the plan doing its job, not a
  gap.

**(3) Each plan document carries only what it alone can say.** The design doc is capped at:
the slice's scope and success criteria, install-time config, the **concrete decisions** (`D-n`)
this slice makes and the concrete structure they land in (files, classes, signatures), a table
**mapping every piece to its named service** in `system-design.md`, deliberate deferrals (with
any safety caveat stated out loud), testing approach, packaging, and the Verify-live checklist
of item 7. The TDD plan carries the task entries. Content outside those lists is judged by
item 2 where another doc owns it; where no doc does, it is **Minor** — a cut candidate the
author has to place, not yet a defect.

Two named cases, because they are the common ones: **restated ADR rationale** (the *why*
belongs in the ADR the spec cites) is **Minor**, and **per-task narrative that states no fact
the task entry already carries** — in the TDD plan, where those entries live — is **Minor**.

**Length is not itself a finding.** A slice whose decisions and tasks genuinely run long is a
correct plan at its natural length. Report a line because another doc already says it, never
because the document is big.

**(4) ADR compliance and gates.** The spec honors every accepted ADR it touches, and identifies
the ADR gate for each gated task (e.g. engines package home, cross-Manager events) before the
task that depends on it — a gate opened after the task it blocks, or not identified at all, is
**Major**. A task that contradicts an accepted ADR is **Major**, and **Critical** where the
contradicted rule is a safety behaviour (a single merged clamp instead of the two ADR-0006
requires, a fault path that guesses a value instead of forcing 0 A). The stack overlay adds,
under this item, the boundary crossings that are this stack's.

The records a slice is ordinarily gated on — the list to read the spec against rather than the
whole log — are enumerated in the stack overlay under this item, for both the author and the
reviewer; `implement.md`'s *Honor the ADRs* rule points there rather than keeping a second
copy. It is the usual set, not a closed one — an ADR outside it that the slice touches is
judged by the same item.

**(5) TDD plan quality.** Tasks are bite-sized (a failing test → minimal impl → green →
commit), each naming **exact file paths** and a concrete failing test — a task missing either
is **Major**, since the `development` work file consumes it literally. Each task names its
**test boundary** — the boundaries, which kind of task falls under each, and the severity of a
boundary missing or wrongly chosen are the stack overlay's under this item. Integration
checkpoints are named where a task is wired to its callers — missing ones are **Minor**.

**(6) Scope honesty.** Deferrals are explicit, and nothing in scope silently pulls in an
out-of-scope service (**Major**). A safety-relevant omission — a mandated clamp or fault
behavior dropped for an MVP — is called out in the spec as a known deviation; a silent one is
**Critical**.

**(7) The slice's Verify-live checklist is present and usable.** This is the only home for the
per-type completion rule it states: **every spec defines the checklist for its own slice**, in
the design doc, fixed before the code is written — `definition-of-done.md`'s **Verify live**
stage is run against it after deployment and has no other source. An absent checklist is
**Major**: without it the pass is run from memory, which is exactly what that stage exists to
prevent. An item naming no concrete entity id, or an expected value carried without its unit,
is **Minor** — a bare number hides the unit and precision defects the pass is looking for.

**(8) Terminology and identifiers match.** Every domain term is already in the
`docs/analysis/system-overview.md` glossary, and entity ids match `docs/analysis/entity-catalog.md`
and ADR-0004 native naming — **Minor**.

## Overlays

**Apply the overlays** the profile's declared stacks provide for this work type:
`overlays/<stack>.md` beside this file, its **Done** section read with this file as part of the
same bar. What an overlay is, what a file reading `none` means and what may not live in this file
are this tree's `README.md`'s **Stack overlays**.
