# Flow documents

This directory originally planned nine per-behaviour flow documents (`00-control-cycle.md`
through `08-profile-selection.md`). In practice the analysis converged on a smaller set of
documents that cover the same ground without restating shared mechanism across nine files:

| Originally planned          | Covers                                                                 | Now lives in                                                                                                             |
| --------------------------- | ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `00-control-cycle.md`       | The coordinator loop: read → smooth → dispatch → clamp → set           | [`control-cycle.md`](../control-cycle.md)                                                                                |
| `01-solar-flow.md`          | `Solar` mode, including grid fallback (R1)                             | [UC01](../use-cases/UC01-charge-from-solar-surplus.md)                                                                   |
| `02-solar-only-flow.md`     | `SolarOnly` mode (R2)                                                  | [UC02](../use-cases/UC02-charge-from-solar-only.md)                                                                      |
| `03-captar-flow.md`         | `Captar` mode (R4)                                                     | [UC03](../use-cases/UC03-charge-from-grid-within-captar-limit.md)                                                        |
| `04-power-flow.md`          | `Power` mode, incl. configurable peak-breach option (R17)              | [UC04](../use-cases/UC04-charge-at-a-user-set-current.md)                                                                |
| `05-soc-management.md`      | Active SOC limit resolution & lifecycle and solar step-up (R6, R7, R8) | Active SOC limit lookup in [`resolution-rules.md`](../resolution-rules.md) (R7); step-up lifecycle in UC06 (planned)     |
| `06-deadline-override.md`   | Deadline urgency as a cross-cutting override (R5)                      | Departure-deadline lookup in [`resolution-rules.md`](../resolution-rules.md) (R14); urgency escalation in UC05 (planned) |
| `07-solar-reserve-logic.md` | Solar-reserve overnight cap and the home-day flag (R9, R13)            | Solar-reserve row of the active SOC limit table in [`resolution-rules.md`](../resolution-rules.md); UC07/UC08 (planned)  |
| `08-profile-selection.md`   | Profiles select modes; the `Auto` profile (R16, NF1)                   | Auto mode-selection table in [`resolution-rules.md`](../resolution-rules.md)                                             |

Rationale for the pivot: the per-mode flows (01–04) turned out to be goal-oriented behaviours
with a primary actor and success/exception scenarios — a better fit for the use-case template
than a flow document. The remaining flows (05–08) turned out to be shared, priority-ordered
lookups consumed by several use-cases and the coordinator, rather than independent
sequences — collecting them once in `resolution-rules.md` avoids restating the same table in
every use-case that reads it.

This directory is kept only for the mapping above; no further flow documents are planned. New
analysis work happens in [`control-cycle.md`](../control-cycle.md), [`resolution-rules.md`](../resolution-rules.md),
[`entity-catalog.md`](../entity-catalog.md), and [`use-cases/`](../use-cases/).
