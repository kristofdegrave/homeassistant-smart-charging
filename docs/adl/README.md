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
| [0010](0010-engines-package-home.md) | Package home for the cross-cutting engines | Accepted |
| [0011](0011-cross-manager-coordination-via-domain-events.md) | Cross-Manager coordination via domain events | Accepted |
| [0012](0012-coordinator-internal-decomposition.md) | Coordinator internal decomposition (Strategy + extracted state owners) | Accepted |
| [0013](0013-stable-owned-entity-object-ids.md) | Stable, locale-independent object_ids for owned entities | Proposed |
| [0014](0014-state-mutation-encapsulation.md) | Setter-method encapsulation for the coordinator's externally-writable fields | Superseded by ADR-0016 |
| [0015](0015-managers-package-home.md) | Package home for the Managers beyond the Coordinator | Accepted |
| [0016](0016-entity-to-coordinator-writes-via-ha-events.md) | Entity-to-coordinator writes via Home Assistant events | Superseded by ADR-0018 |
| [0017](0017-profile-as-composed-mode-selection-policy.md) | Mode-selection policy Protocol and registry for `profiles/` | Accepted |
| [0018](0018-entity-to-coordinator-access-via-ra3-store.md) | Entity-to-coordinator access via RA3's Store (pull-based read, Manager-initiated write) | Accepted |
| [0019](0019-store-package-home.md) | Package home for the RA3 Config/State Store | Accepted |
| [0020](0020-skillspector-advisory-pr-scan.md) | Advisory SkillSpector scan feeding the workflow-reviewer AI review | Accepted |
| [0021](0021-adapter-readings-diagnostic-sensor.md) | Adapter-role readings surfaced via a single diagnostic sensor's attributes | Accepted |
| [0022](0022-runtime-dashboard-delivery-mechanism.md) | Runtime-dashboard delivery mechanism | Accepted |
| [0023](0023-decompose-run-cycle-into-named-steps.md) | Decompose `_run_cycle` into named per-step methods (extends ADR-0012) | Accepted |
| [0024](0024-deadline-unreachable-cleared-event.md) | Paired clear event to re-arm the deadline-unreachable notice per occasion | Accepted |
| [0025](0025-config-flow-branching-structure.md) | Table-driven linear step sequence for the capability-gated config flow | Accepted |
| [0026](0026-psutil-for-perf-test-cpu-rss-measurement.md) | `psutil` for CPU-time/RSS measurement in perf tests | Accepted |

Add a row here in the same commit as every new or superseded ADR.
