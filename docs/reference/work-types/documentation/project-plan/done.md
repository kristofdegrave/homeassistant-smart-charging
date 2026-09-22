# Work type: `documentation` — the completion bar for `project-plan.md`

This file states *what must be true of a finished project plan*. How it is written — the derivation
order, the ADR flagging step, the task-list shape — is
[`implement.md`](implement.md). How a review is conducted — what to
read first, how to anchor findings, the output format, and the checks about the *change* rather
than the document — belongs with the reviewer.

**This bar is for `docs/design/project-plan.md` only.** The other branch,
`docs/design/system-design.md`, has [its own bar](../system-design/done.md). Why this work type
has a bar per document, and which one a change falls under, is stated once in the label's own
[`done.md`](../done.md) — the file that routed you here.

There is no 6Cs pass here. That check is for behavioural requirements and use-cases; a task
breakdown's correctness is judged by whether it follows the architecture it derives from, not by
Clarity/Concision/etc. Clutter is still checked, as item 5 below.

**The plan is never judged alone.** Every item below is decided against
`docs/design/system-design.md` — the version in the same change if the change touches it, the
one on the base branch otherwise. Both sides read that document alongside this one, even when
only the plan changed; a plan judged without it can only be checked for internal tidiness,
which is not what any item here asks. Domain terms are additionally judged against the
`system-overview.md` glossary, as in every document in this project — a term the plan uses and
that glossary does not define is **Minor**, and the fix is to add it there first rather than to
reword the plan around it.

## The bar

**(1) Derived, not designed.** The plan introduces no service that `system-design.md` does not
carry, and changes no call direction it states. A plan that invents a service, renames one into
a different responsibility, or works around an architecture gap locally is **Major**: the gap
belongs in `system-design.md`, and the finding names which service or direction the plan added
and what the design would have to say instead.

**(2) Build order follows the call directions.** Resource Access and Engines are sequenced
before the Managers and Clients that depend on them — a service is built only once every
service it calls exists or is stubbed. An order that contradicts the static diagram's call
directions is **Major**; name the pair of tasks and the direction they violate.

**(3) Tasks are complete and independently testable.**
- Every service in `system-design.md` appears in **exactly one** task, or one natural sub-slice
  of a large one. A service dropped from the plan, or carried by two tasks, is **Major** — name
  it.
- Each task is verifiable on its own before the next depends on it. A task whose completion
  can only be observed once a later task lands is **Major**: it is what makes the derivation a
  guess rather than a sequence.
- Each task names what it depends on and the **integration checkpoint** that proves it is wired
  correctly with its callers. A missing dependency list or checkpoint is **Minor per task**,
  **Major** where it is the pattern of the plan rather than an exception — a plan with no
  checkpoints anywhere cannot show its own order was followed.

**(4) ADR flags are real and come before the build.** A service boundary, protocol choice, or
schema decision that would be expensive to reverse carries a line item to open an ADR, and that
line item sits **before** the task that depends on it.
- A structural decision of that kind with no flag is **Major**; name the service and which
  clause of `CLAUDE.md`'s **Architecture Decision Records (ADRs)** worthiness test it meets.
- A flag on something that fails that test — including anything its two carve-outs exclude — is
  **Minor**: it is busywork, not a missing gate.
- A flag positioned after the task that depends on it is **Major**: the ADR would then be
  retrofitted to a built service, which is the thing the flag exists to prevent.

**(5) No clutter**, as the *Clutter* entry in
[`ai-authoring.md`'s Vocabulary](../../../method/ai-authoring.md#vocabulary) defines it, at its
severities and in its scope.
