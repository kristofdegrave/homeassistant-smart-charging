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
any safety caveat stated out loud), testing approach, and packaging. The testing approach
names the **testing seam(s)** the tasks' failing tests drive through — one that exists over
one the slice adds, one for the whole slice where one reaches every task; a testing approach
naming no seam is **Minor**, since each task then finds its own and the suite grows a seam per
task. The TDD plan carries the task entries, each in the shape `implement.md`'s *The task
entry* fixes: vertical, its exact files and its failing test, its **Blocked by** line and its
**Verify live** list. Content outside those lists is judged by
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
requires, a fault path that guesses a value instead of forcing 0 A). An engine reaching Home
Assistant directly, against ADR-0003, is **Major**.

The records a slice is ordinarily gated on, and the list to read the spec against rather than
the whole log: adapters (0003), package layout (0002/0010), config split (0005),
coordinator/two-clamps (0006), fault-on-`None` (0007), testing split (0009), native naming
(0004). This is the enumeration, for both the author and the reviewer; `implement.md`'s
*Honor the ADRs* rule points here rather than keeping a second copy. It is the usual set, not
a closed one — an ADR outside it that the slice touches is judged by the same item.

**(5) TDD plan quality.** Tasks are bite-sized (a failing test → minimal impl → green →
commit), each naming **exact file paths** and a concrete failing test — a task missing either
is **Major**, since the `development` work file consumes it literally. Each task names its **test boundary
per ADR-0009**: plain pytest for `modes/`/`engines/` (no HA import), HA harness
(`pytest-homeassistant-custom-component` + `MockConfigEntry`) for adapters, coordinator,
entities, and the config flow. A missing boundary, a pure-logic task routed through the HA
harness, or an HA-coupled task tested with plain pytest is **Major**. Integration checkpoints
are named where a task is wired to its callers — missing ones are **Minor**.

Two more, because the task entries are what the task issues are filed from and the entries
must let that filing invent nothing:

- **Each task is a vertical slice** — the shape the **Ticket** stage of
  [idea-to-product.md](../../idea-to-product.md) gives an epic's children, since each entry
  becomes one. The decidable test: something about the task is observable on the real
  installation the day it merges, with no later task landed first. A task that fails it is
  layer-shaped — an adapter alone, an entity alone, waiting for its counterpart — and is
  **Major**: it files a child nothing can demo and hands the flow's verify-live gate a list
  with nothing on it. A task with nothing newly observable — a pure refactor — passes this
  item, and says `none` in its Verify-live list the way item 7 asks.
- **Each task declares `Blocked by`**: the ids of the tasks in this plan it cannot start
  before, or `none`. An entry with no such line is **Major** — the filer cannot tell an
  omission from an empty set, and the edge it would have set is the one the flow orders the
  work by. A line naming an id the plan has no task for, or an issue number, or one that makes
  a cycle, is **Major** for the same reason. The line agrees with item 1's build order or the
  finding is item 1's.

**(6) Scope honesty.** Deferrals are explicit, and nothing in scope silently pulls in an
out-of-scope service (**Major**). A safety-relevant omission — a mandated clamp or fault
behavior dropped for an MVP — is called out in the spec as a known deviation; a silent one is
**Critical**.

**(7) Every task carries a usable Verify-live list.** This is the only home for the
per-type completion rule it states: **every task entry defines the list for its own task**,
fixed before the code is written — `definition-of-done.md`'s **Verify live** pass is run
against it after the task is deployed and has no other source, and the first task's list is
the one that pass drives before the second task starts. An absent list on a task that changes
observable runtime behaviour is **Major**: without it the pass is run from memory, which is
exactly what that pass exists to prevent. A task with nothing observable says `none` and why in
one line; an entry with neither a list nor that line is **Major** too, since the pass cannot
tell it from a forgotten one. An item naming no concrete entity id, or an expected value
carried without its unit, is **Minor** — a bare number hides the unit and precision defects the
pass is looking for.

**(8) Terminology and identifiers match.** Every domain term is already in the
`docs/analysis/system-overview.md` glossary, and entity ids match `docs/analysis/entity-catalog.md`
and ADR-0004 native naming — **Minor**.
