# Adopting Löwy's Method for System Design — Smart Charging

*Date: 2026-07-07*

## Context

The project's analysis-first pipeline (system-overview → requirements → use-cases/flows → ADRs
→ code) has no step that produces an overall service architecture before individual structural
decisions get ADRs one at a time. Juval Löwy's IDesign Method ("the Method") fills that gap: it
decomposes a system by **volatility** (what's likely to change and why) rather than by function,
and derives a project/task plan mechanically from the resulting architecture ("project design").

Use-cases in this method are **validation input, not the decomposition driver** — a use case is
allowed (expected) to cut across several services; that crossing is what proves the services were
sliced correctly. This is a deliberate contrast with the existing UC-first flow docs, not a
replacement of them.

---

## Where this fits in the existing pipeline

```text
system-overview.md → requirements.md → flows/ + use-cases/  →  design/  →  ADRs  →  code
                                                                  ^^^^^^
                                                              new phase
```

`design/` runs once the relevant use-cases/flows are stable enough to validate against, and
*before* individual ADRs, because a service boundary is itself a structural decision that an ADR
should capture — the design step surfaces which decisions need one.

---

## Document structure (new)

```text
docs/design/
  system-design.md   — volatility-based service decomposition (static + dynamic architecture)
  project-plan.md     — implementation task breakdown derived from system-design.md
```

Both are singular, living documents (not one-per-decision like ADRs) — revised in place as the
architecture evolves, each revision going through the same review cycle. Branch naming falls back
to CLAUDE.md's `docs/<issue-number>` rule, since neither artifact has a sequential number of its
own.

### `system-design.md` — the Method

1. **Enumerate use cases** already drafted under `docs/analysis/use-cases/` and `flows/` — listed
   as validation input, not walked through directly.
2. **Identify volatilities** — for each area of behavior, ask what varies, along what axis, and
   why (e.g. charger hardware/protocol, tariff and captar rules, deadline-urgency policy, SOC
   data source).
3. **Encapsulate each volatility in a service**, categorized as one of:
   - **Client** — a consumer of the system (HA automations/UI).
   - **Manager** — orchestrates one use case's flow in a specific order; the "how" of a use case.
   - **Engine** — reusable business/policy logic, volatility-scoped, no orchestration.
   - **Resource Access** — encapsulates *how* a specific resource is reached; isolates that
     volatility from everything above it.
   - **Resource** — the external thing itself (charger, HA entity state, tariff/captar source).
4. **Static architecture diagram** — the service map and allowed call directions: Client → Manager
   → {Engine, Resource Access} → Resource. No calls go upward. A Manager may call another Manager
   only via the one allowed orchestration pattern (never a peer-to-peer web).
5. **Dynamic (behavioral) diagrams** — one sequence diagram per major use case, showing how its
   Manager orchestrates Engines/Resource Access to realize that use case's flow.
6. **Self-check against structural rules** (see the `system-design-reviewer` agent's checklist).
7. Review, address, manual approval, commit — same cycle as every other analysis document.

### `project-plan.md` — project design

Consumes an approved `system-design.md` and produces the mechanical translation Löwy calls
"project design": build order (Resource Access → Engines → Managers → Clients), which services
surface a structural decision that needs its own ADR before being built, integration/testing
checkpoints between services, and a task list that feeds `writing-plans` / `custom_components/`
work. On a solo project this replaces "team assignment" with a sequenced, independently-testable
task list — the mechanical derivation is the point, not who does the work.

---

## New agent: `system-design-reviewer`

Fresh, separate Opus agent (read-only), following the `analysis-reviewer`/`adr-reviewer` pattern.
Checks, in addition to the standard cross-document consistency / glossary checks:

- Every service traces to a genuine volatility, stated explicitly — not a disguised functional
  slice (the tell: a service named after a use case rather than a thing that varies).
- Layering rules aren't violated: no upward calls, Managers don't call Managers outside the one
  allowed orchestration pattern, Engines don't orchestrate.
- Every use case in `docs/analysis/use-cases/` and `flows/` is reachable end-to-end through the
  service map (validates the decomposition without letting use cases drive it).
- `project-plan.md`'s build order is consistent with the static diagram's call directions.

---

## CLAUDE.md changes

- Add `docs/design/` to the "Document structure" tree, with its two files.
- Insert a step in "Writing order": once relevant use-cases/flows are stable, `design/system-design.md`
  then `design/project-plan.md`, before ADRs get opened for the structural decisions the design
  surfaces.
