# Architecture Decision Log (ADL)

The Architecture Decision Log is the index of every Architecture Decision Record (ADR)
in this project. Each row is one immutable decision; see `template.md` for the format
and `0001-use-architecture-decision-records.md` for why this project uses ADRs and this
template.

| ADR | Title | Status |
| --- | --- | --- |
| [0001](0001-use-architecture-decision-records.md) | Use Architecture Decision Records, with a Nygard+options template | Accepted |
| [0002](0002-domain-and-package-layout.md) | Domain slug and package layout for the `smart_charging` integration | Accepted |
| [0003](0003-hardware-abstraction-adapters.md) | Hardware abstraction via config-flow entity mapping and Python adapters | Accepted |
| [0004](0004-owned-vs-mapped-entities.md) | Owned control/diagnostic entities vs. mapped hardware entities | Accepted |
| [0005](0005-config-entry-structure-and-interval.md) | Config entry structure and control interval | Accepted |
| [0006](0006-coordinator-and-data-flow.md) | Coordinator and data flow | Accepted |
| [0007](0007-fault-handling.md) | Fault handling for adapter reads, translation failures, and uncaught exceptions | Accepted |
| [0008](0008-reconfigure-reload-behavior.md) | Config-entry reload on reconfigure and options changes | Accepted |
| [0009](0009-testing-strategy.md) | Testing strategy | Accepted |

Add a row here in the same commit as every new or superseded ADR.
