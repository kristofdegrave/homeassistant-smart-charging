# Work type: `documentation` — how `system-design.md` is written

Author `docs/design/system-design.md`: a volatility-based service decomposition — static and
dynamic architecture — derived from the behaviour already drafted under `docs/analysis/`, per
Juval Löwy's IDesign Method. Full rationale for why this phase exists and where it sits in the
pipeline: `docs/plans/2026-07-07-lowy-system-design-method.md`.

This file is the `documentation` work type's work file for a change touching
`docs/design/system-design.md`, reached from the label's own `implement.md` one level up, which
is what the row names. Why the label splits at all, where a change touching
`docs/design/project-plan.md` goes instead, and which bar a change falls under are stated once
in the label's own [`done.md`](../done.md).
It carries **how the system design is written** and nothing else; the completion bar beside
it, `done.md`, carries what must be true of the finished design.

**The core discipline of the Method: use cases validate the decomposition, they never drive
it.** The bar's item 1, *Volatility, not function, drives the decomposition*, states it and
judges it. What that means while drafting: if you catch yourself creating one service per use
case, or naming a service after a use-case verb phrase, stop — that is functional decomposition
wearing this method's vocabulary.

## Drafting the system design

**The implement step (do the work)**, in order:

1. **Enumerate the behaviour already drafted** — the use cases under
   `docs/analysis/use-cases/`, and `control-cycle.md`. List them; do not start
   decomposing from them yet — this list is what you validate against in step 6, not the input
   to step 2.
2. **Identify volatilities.** For each area of behaviour across the enumerated use cases, ask:
   what here is likely to change, along what axis, and why? (Examples in this domain: charger
   hardware protocol, tariff/captar rule source, deadline-urgency policy, SOC data source,
   solar-capability presence.) Write each volatility down explicitly with its rationale — the
   bar's item 1 judges that rationale, so an unwritten one is a finding rather than an
   omission.
3. **Encapsulate each volatility in exactly one service**, classified as one of:
   - **Client** — a consumer of the system: an automation, a UI, an entity.
   - **Manager** — orchestrates one use case's flow, in a specific order; the "how".
   - **Engine** — reusable business/policy logic scoped to one volatility; never orchestrates.
   - **Resource Access** — encapsulates *how* one specific resource is reached; isolates that
     access volatility from everything above it.
   - **Resource** — the external thing itself: the charger, a platform entity's state, the
     tariff/captar source.
4. **Static architecture diagram** (Mermaid `flowchart TD`): the service map with allowed call
   directions only — Client → Manager → {Engine, Resource Access} → Resource. State explicitly
   the one allowed pattern (if any) for Manager-to-Manager orchestration; state that Engines
   don't orchestrate and Resource Access doesn't hold policy.
5. **Dynamic diagrams** (Mermaid `sequenceDiagram`, one per major use case): show the Manager
   orchestrating Engines/Resource Access to realize that use case's actual flow steps, in
   order.
6. **Validate against the list from step 1** — walk each use case's Given/When/Then or
   flowchart steps against the static diagram; confirm each is reachable end-to-end. The bar's
   item 3, *Use-case validation, not use-case-driven design*, judges the result, including the
   one-to-one design smell. What that means while drafting: a use case that maps cleanly onto a
   single service sends you back to steps 2–3 rather than forward.

Once `system-design.md` is approved and merged, the project plan is derived from it — the other
branch of this work type, and [its own work file](../project-plan/implement.md).

## Rules

- **Volatility drives the cut, not function** — the bar's item 1 states it and judges it. What
  that means while drafting: every service must answer "what varies here, and why", not just
  "what does this do".
- **Use cases are validation, not decomposition input** — the bar's item 3 states it and judges
  it. What that means while drafting: expect, and want, most use cases to cross several
  services.
- **No upward calls, ever** — the bar's item 2, *Layering and call directions*, states it and
  judges it. What that means while drafting: Client → Manager → {Engine, Resource Access} →
  Resource is one-way, and a diagram is the place the violation becomes visible, so draw the
  arrows before you argue about them.
- **Managers orchestrate, Engines decide, Resource Access reaches, Resources are reached** —
  the bar's item 2 states it and judges it. What that means while drafting: don't let policy
  logic leak into a Manager or a Resource Access, and don't let a multi-step orchestration leak
  into an Engine.
- **Reference, don't restate.** Cite `control-cycle.md`, `resolution-rules.md`, and the
  `system-overview.md` "adapter role" concept rather than re-deriving them; if this design
  changes or supersedes one of those concepts, say so explicitly — the bar's item 4,
  *Cross-document consistency*, judges a silent divergence.

## Common mistakes

Mistakes in how the work is done. The defects themselves are enumerated once, in the bar, so
none of them is restated here:

- Starting from the use-case list as the input to the decomposition instead of as the
  validation set — which is what produces one service per use case.
- Naming a service after a use-case verb phrase, so the name records what it does rather than
  what varies inside it.
- Writing a service down without its volatility rationale, intending to add it later.
- Skipping step 6's walk of every use case against the static diagram, so the design is never
  tested against the behaviour it exists to serve.
- Drafting against this file alone and never opening `done.md` — the bar is where
  most of what a review will say already is.
