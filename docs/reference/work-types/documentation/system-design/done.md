# Work type: `documentation` — the completion bar for `system-design.md`

This file states *what must be true of a finished system design*. How it is written — the drafting
order, the classifications, the diagrams — is [`implement.md`](implement.md).
How a review is conducted — what to read first, how to anchor findings, the output format, and
the checks about the *change* rather than the document — belongs with the reviewer.

**This bar is for `docs/design/system-design.md` only.** The other branch,
`docs/design/project-plan.md`, has [its own bar](../project-plan/done.md). Why this work type has
a bar per document, and which one a change falls under, is stated once in the label's own
[`done.md`](../done.md) — the file that routed you here.

There is no 6Cs pass here. That check is for behavioural requirements and use-cases; a service
decomposition's correctness is judged by whether each cut encapsulates a real volatility and the
call directions hold, not by Clarity/Concision/etc.

**What the design is judged against, beyond itself.** In `docs/analysis/`:
`system-overview.md` (the authoritative Ubiquitous Language glossary and the control-loop /
adapter-role orientation), `requirements.md` (the requirement IDs the document may reference),
`control-cycle.md`, `resolution-rules.md` and `entity-catalog.md` (the mechanism docs a
service's responsibility may overlap with), and the use-cases under `use-cases/`, which are what
item 3 validates against.

## The bar

**(1) Volatility, not function, drives the decomposition.**
- Every service names the **volatility** it encapsulates explicitly — what varies, along what
  axis, and why — not just what it does. A service whose only justification is "it does step N
  of use case X" is a functional slice wearing the Method's vocabulary: **Major**, and name the
  service.
- No two services encapsulate the same volatility, and no single service bundles two
  independent volatilities — the second should split. Either is **Major**.
- Services are named for the *thing that varies* (e.g. "Tariff Policy Engine"), not for a use
  case or a verb phrase copied from a use-case step. Where the volatility rationale is present
  and only the name records the verb phrase, this is **Minor**; where the name is the whole
  justification, it is the first bullet's **Major**.

**(2) Layering and call directions.**
- Every service is classified as exactly one of Client, Manager, Engine, Resource Access,
  Resource, and the classification matches its actual responsibility — a Manager that contains
  reusable business rules should be an Engine, an Engine that reaches an external resource
  directly should delegate to Resource Access. A missing or mismatched classification is
  **Major**.
- Call directions only go Client → Manager → {Engine, Resource Access} → Resource. An **upward
  call** — a Resource Access calling back into an Engine, an Engine calling a Manager — is
  **Critical**: the one-way rule is the invariant the whole decomposition rests on, and a
  design that breaks it cannot be built as drawn.
- Managers call other Managers only through the one allowed orchestration pattern the document
  itself states. An undocumented peer-to-peer Manager-to-Manager web is **Major**.
- Engines do not orchestrate a multi-step flow (a Manager's job); Resource Access holds no
  business or policy logic (an Engine's job). Either leak is **Major**.

**(3) Use-case validation, not use-case-driven design.**
- Every use case under `docs/analysis/use-cases/`, and `control-cycle.md`'s loop, is reachable
  end-to-end through the service map by walking its Given/When/Then or flowchart steps against
  the static diagram. One that is not is **Major** — name the use case and the step that dead-ends.
- A single use case mapping cleanly one-to-one onto a single service is the signature of
  function-based decomposition, the opposite of what this method is for. It is not necessarily
  wrong, but it is always **called out**: **Minor**, named as a design smell, with the service
  and the use case. A healthy decomposition has most use cases crossing several services.
- The dynamic (sequence) diagrams' Manager orchestration matches the corresponding use case's
  actual flow steps. A diagram that adds a step the use case does not have, or drops one it
  does, is **Major**; a difference only in the order of two steps that commute is **Minor**.

**(4) Cross-document consistency.**
- Every domain term used is defined in the `system-overview.md` glossary — **Minor**, and the
  fix is to add the term to the glossary first, not to reword the design around it.
- Every requirement ID referenced exists in `requirements.md` — a reference to an ID that does
  not exist is **Major**, since the design is claiming coverage it cannot have.
- The service map does not contradict `control-cycle.md`'s own loop or the existing
  "adapter role" concept in `system-overview.md`. Where the design changes one of those
  concepts it says so explicitly; a **silent** divergence is **Major**, an explicit one is a
  finding only if the document it changes is not updated in the same change.

**(5) The two diagrams are present and in the required form.** A static architecture diagram
(Mermaid `flowchart TD`) carrying the service map and the allowed call directions, and a dynamic
diagram (Mermaid `sequenceDiagram`) per major use case. A missing static diagram is **Major** —
item 2 and item 3 are both decided against it. A major use case with no dynamic diagram is
**Minor** per occurrence, **Major** where the document has none at all.

**(6) No clutter.** Content another document owns — a mechanism, a requirement, an ADR's
rationale — or that states no fact, is judged by the *Clutter* entry in
[`ai-authoring.md`'s Vocabulary](../../../method/ai-authoring.md#vocabulary), at the severities
and in the scope it states.
