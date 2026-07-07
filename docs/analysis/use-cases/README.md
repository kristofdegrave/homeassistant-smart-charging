# Use-cases

Goal-oriented behaviours of the smart-charging system, one per document. Each use-case follows
the **use-case template** in the design doc
([2026-06-25-use-cases-design.md](../../plans/2026-06-25-use-cases-design.md#use-case-template-use-casesucnn-md)):
Primary actor → Stakeholders → Scope/level → Preconditions → Trigger → Main success scenario →
Alternate flows → Exception flows → Postconditions → State model → Domain events → Diagram →
Requirements satisfied → Relationships. Scenario bodies are written in **Given / When / Then**
(BDD), which suits an event-driven control loop and doubles as a testable spec.

Every domain term used in a use-case must already be defined in the
[Ubiquitous Language glossary](../system-overview.md#ubiquitous-language). Use-cases speak in
domain language ("the active SOC limit", "charger status"); the `sc_` entity binding lives only in
[`entity-catalog.md`](../entity-catalog.md), keyed by its *Read by* / *Written by* columns.

Use-cases plug into two shared mechanism documents rather than restating them:

- [`control-cycle.md`](../control-cycle.md) — the coordinator spine every mode runs on (read →
  smooth → dispatch → clamp → set), including the peak-protection and grid-supply-ceiling clamps
  and the rapid-cycling invariant.
- [`resolution-rules.md`](../resolution-rules.md) — the shared priority-ordered lookups (active SOC
  limit, departure deadline, effective peak limit, Auto mode-selection).

---

## Inventory

| UC | Goal | Primary actor | Requirements | Status |
| --- | --- | --- | --- | --- |
| [UC01](UC01-charge-from-solar-surplus.md) | Charge from solar surplus (incl. grid fallback) | Household energy manager | R1 | Planned |
| [UC02](UC02-charge-from-solar-only.md) | Charge from solar only | Household energy manager | R2 | Planned |
| [UC03](UC03-charge-from-grid-within-captar-limit.md) | Charge from the grid in Captar mode | Household energy manager | R4 | Planned |
| [UC04](UC04-charge-at-a-user-set-current.md) | Charge at a user-set current | EV driver | R17 | Planned |
| [UC05](UC05-guarantee-ready-by-departure.md) | Guarantee the car is ready by departure | EV driver | R5 | Planned |
| [UC06](UC06-store-abundant-solar.md) | Store abundant solar by stepping up the limit | Household energy manager | R8 | Planned |
| [UC07](UC07-reserve-capacity-for-tomorrow.md) | Reserve capacity for tomorrow's solar | Household energy manager | R9 | Planned |
| [UC08](UC08-plan-tomorrow-home-day.md) | Plan tomorrow's home day (evening prompt) | EV driver | R13 | Planned |
| [UC09](UC09-sync-charge-limit-with-car.md) | Keep the charge limit in sync with the car | EV driver | R6 | Planned |
| [UC10](UC10-remind-to-plug-in.md) | Remind me to plug in | EV driver | R12 | Planned |

---

## Notes

- **UC05 is a cross-cutting goal, realized by the coordinator, not by extending a mode.** The
  charging use-cases (UC01–UC04) stay pure — each computes only its own set-point, never modified
  by deadline logic (NF2). Deadline urgency is instead a profile-keyed rule in
  [`resolution-rules.md`](../resolution-rules.md) (the Deadline-urgency response), applied by the
  coordinator (`control-cycle.md`, step 5) to whichever mode is currently dispatched, so the
  urgency-escalation logic is never duplicated per mode. (For `Power`, the response can raise the
  requested current above the configured Power target current — up to the maximum charging
  current — regardless of the peak-protection option; it additionally widens the peak headroom
  only while that option is enabled, since `Power` is otherwise already unconstrained by the
  effective peak limit.)
- **The `Auto` profile is not a use-case.** Choosing which mode is active is a priority-ordered
  decision with no human pursuing a goal, so it lives as the Auto mode-selection table in
  [`resolution-rules.md`](../resolution-rules.md). The `Manual` profile needs no document — the
  user or an external source sets the active mode directly.
- **`Off` mode is not a use-case.** It is the null behaviour (the coordinator sets 0 A); there is
  no goal to document.
