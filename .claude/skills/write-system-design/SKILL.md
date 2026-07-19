---
name: write-system-design
description: Use when authoring or changing docs/design/system-design.md in the Smart Charging project — applying Juval Löwy's IDesign Method (volatility-based decomposition) to derive the service architecture from the drafted use-cases/flows.
---

# Write the system design (Löwy's Method)

Author `docs/design/system-design.md`: a volatility-based service decomposition, static +
dynamic architecture, derived from the use-cases/flows already drafted under
`docs/analysis/use-cases/` and `docs/analysis/flows/`. Full rationale for why this phase exists
and where it sits in the pipeline: `docs/plans/2026-07-07-lowy-system-design-method.md`.

**The core discipline of the Method: use cases validate the decomposition, they never drive it.**
If you catch yourself creating one service per use case, or naming a service after a UC verb
phrase, stop — that is functional decomposition wearing this method's vocabulary.

## The cycle (do every step, in order)

0. **Open (or link) a GitHub issue** describing the intent and scope. Skip only for a pure-wording
   edit that doesn't change a service boundary or a call direction. Branch as `docs/<issue-number>`
   (this artifact has no sequential number of its own), per CLAUDE.md's branch-naming convention.
1. **Enumerate the use cases and flows** already drafted (`use-cases/UCnn-*.md`, `flows/*.md`).
   List them; do not start decomposing from them yet — this list is what you validate against in
   step 6, not the input to step 2.
2. **Identify volatilities.** For each area of behavior across the enumerated use cases, ask: what
   here is likely to change, along what axis, and why? (Examples in this domain: charger hardware
   protocol, tariff/captar rule source, deadline-urgency policy, SOC data source, solar-capability
   presence.) Write each volatility down explicitly with its rationale — this rationale is what the
   reviewer checks for.
3. **Encapsulate each volatility in exactly one service**, classified as one of:
   - **Client** — a consumer of the system (HA automations/UI/entities).
   - **Manager** — orchestrates one use case's flow, in a specific order; the "how".
   - **Engine** — reusable business/policy logic scoped to one volatility; never orchestrates.
   - **Resource Access** — encapsulates *how* one specific resource is reached; isolates that
     access volatility from everything above it.
   - **Resource** — the external thing itself (charger, HA entity state, tariff/captar source).
4. **Static architecture diagram** (Mermaid `flowchart TD`): the service map with allowed call
   directions only — Client → Manager → {Engine, Resource Access} → Resource. State explicitly
   the one allowed pattern (if any) for Manager-to-Manager orchestration; state that Engines don't
   orchestrate and Resource Access doesn't hold policy.
5. **Dynamic diagrams** (Mermaid `sequenceDiagram`, one per major use case): show the Manager
   orchestrating Engines/Resource Access to realize that use case's actual flow steps, in order.
6. **Validate against the use-case list from step 1** — walk each use case's Given/When/Then or
   flowchart steps against the static diagram; confirm each is reachable end-to-end. A use case
   that maps one-to-one onto a single service is a warning sign, not a pass — revisit step 2/3.
7. **Self-check**: every service's volatility rationale is explicit; no upward calls; no service
   named after a use-case verb phrase; every domain term already exists in the
   `system-overview.md` glossary (add it there first if not).
8. **Review** — launch the `system-design-reviewer` agent (fresh, separate Opus; never review
   inline).
9. **Address** the review feedback.
10. **Commit and push** (`docs: add system design` or `docs: revise system design`), referencing
    the issue from step 0 — commit and push freely; there is no pre-commit approval gate.
11. **Manual approval gates the merge** — the human partner's explicit approval is required before
    the PR is **merged** (enforced by `CODEOWNERS` + branch protection), not before each commit.
12. **Stop and report** status. Once `system-design.md` is approved, the `write-project-design`
    skill consumes it to produce the implementation task breakdown.

## Rules

- **Volatility drives the cut, not function.** Every service must answer "what varies here, and
  why" — not just "what does this do".
- **Use cases are validation, not decomposition input.** Expect (and want) most use cases to cross
  several services.
- **No upward calls, ever.** Client → Manager → {Engine, Resource Access} → Resource is one-way.
- **Managers orchestrate, Engines decide, Resource Access reaches, Resources are reached.** Don't
  let policy logic leak into a Manager or a Resource Access; don't let a multi-step orchestration
  leak into an Engine.
- **Reference, don't restate.** Cite `control-cycle.md`, `resolution-rules.md`, and the
  `system-overview.md` "adapter role" concept rather than re-deriving them; if this design changes
  or supersedes one of those concepts, say so explicitly.

## Common mistakes

- One service per use case (functional decomposition in disguise).
- A service named after a UC verb phrase instead of the volatility it encapsulates.
- An Engine that reaches a Resource directly instead of delegating to Resource Access.
- A Resource Access that contains business rules instead of just access mechanics.
- Skipping the "walk every use case against the static diagram" validation step.
