# Project plan — implementation task breakdown

This document is the **project-design** step of the Method: it translates the approved
[`system-design.md`](system-design.md) into an ordered, dependency-aware, independently-testable
task list for the implementation under `custom_components/smart_charging/`. It **derives** that
sequence mechanically from the architecture — it does not decompose services, introduce new ones,
or change any call direction. Every service named here comes from `system-design.md`'s
[§3 service catalog](system-design.md#3-service-catalog); every ordering constraint comes from its
[§4 allowed call directions](system-design.md#4-static-architecture).

Löwy's project-design step normally also assigns services to teams. This is a solo project, so
that step collapses into a single sequenced task list — the value is the mechanical derivation from
the architecture, not who does each task.

---

## 1. Scope and authority

- **`system-design.md` is authoritative for shape** (which services exist, what each encapsulates,
  the one-way call directions). This plan is authoritative for **sequence** (build order,
  dependency edges, integration checkpoints) and for **which structural decisions must be settled
  by an ADR before a given task starts**.
- Behavior stays owned by the analysis docs: `control-cycle.md` for the order of operations in one
  cycle, `resolution-rules.md` for the priority-ordered lookups, `entity-catalog.md` for
  entity/role bindings, `requirements.md`/UC01–UC11 for acceptance criteria. This plan cites those
  documents as the source of truth and does not re-derive their behavior. Where a task names a
  specific formula, threshold, or rule (e.g. the surplus formula, the clamp baseline, an R-number),
  it does so as a **test anchor** — the concrete thing that task's test must reproduce, attributed
  to its owning doc — not as a restatement that this plan owns. If an anchor and its source doc ever
  disagree, the source doc wins.
- If executing this plan reveals a gap in `system-design.md`, the gap is fixed **there first**
  (re-running the `write-system-design` review cycle), then this plan resumes — the derivation must
  stay mechanical.
- **This is a planning artifact — no `custom_components/` code is written as part of it.** Approved
  tasks feed `writing-plans`/`test-driven-development` for the actual implementation.
- **Status markers are a record, not a change to the derivation.** Every task below carries a
  **Status** line saying whether that service has shipped under `custom_components/smart_charging/`
  and where. The build order, dependency edges, and gates are unaffected by them — the plan remains
  the mechanical translation of the architecture, and the markers only record how far reality has
  come along it. Where an ADR accepted *after* a task was first written settled that task's
  structure differently from what the task anticipated, the task text is corrected to the shipped
  shape and cites the deciding ADR; the ordering it sits in is not renegotiated.

---

## 2. Derivation rule (why the order is what it is)

A service can be built only once every service it *calls* already exists or is stubbed. Reading
`system-design.md` §4's one-way edges bottom-up yields the build order below (a partial order —
Resource Access and Engines are parallel-buildable, per the refinements that follow):

```text
Resources (external — not built)
  └─ Resource Access  (adapters, notification access, config/state store)  ── call only Resources
       └─ Engines     (pure + stateful)                                    ── call nothing below them
            └─ Managers (Coordinator, Vehicle-Limit, Notification)         ── call Engines + Resource Access
                 └─ Clients (timer, owned entities, config flow, dashboard, external events) ── call Managers / Store
```

Two refinements the diagram forces, not preferences:

- **Engines call nothing below them** (§4 rule 4), so they have no runtime dependency on Resource
  Access — a Manager feeds them. They are therefore buildable in parallel with Resource Access. The
  build order lists Resource Access first only because the Coordinator (the first Manager) needs
  *both* layers present, and Resource Access is the thinner of the two.
- **Managers never call each other** (§4 rule 5); cross-Manager coordination is publish/subscribe on
  domain events. So the three Managers have no ordering dependency *on each other* — only on the
  Engines and Resource Access they compose, plus the ADR-0011 gate ([§3](#3-structural-decision-gate-adrs-before-build)).

The order below is **not** renegotiable by convenience. Where a later service is convenient to
smoke-test earlier (e.g. the config flow), that is called out as a checkpoint, not a reordering.

---

## 3. Structural-decision gate (ADRs before build)

Six structural decisions bear on build order — three surfaced by `system-design.md` when this plan
was first derived (G-ADR-0010, G-ADR-0011, G-NAMING), three more surfaced by the layers this plan
sequences as they were actually built (a package home for the Managers beyond the Coordinator, a
package home *and* an access shape for RA3's Store, and the dashboard's delivery mechanism). All
six are now **resolved**, each by an Accepted ADR. No structural-decision gate blocks any task
below; the table is kept as a record of which tasks passed through which gate.

| Gate | Decision | Blocked (until resolved) |
| --- | --- | --- |
| **G-ADR-0010** *(resolved — ADR-0010, Accepted)* | *Package home for the eight cross-cutting Engines* — an `engines/` subpackage vs top-level modules. ADR-0002 gave `adapters/`, `modes/`, `profiles/` homes but no home for SOC-Target, Deadline, Billing-Protection, Grid-Safety, Signal-Conditioning, Cycle-Invariant, Capability-Gate, Peak-Demand Tracker (system-design §8 follow-up). Decided: a single `engines/` subpackage, one module per engine (Option A). | Tasks **E3–E9** (the cross-cutting Engines; the eight engines map to E3–E9 because E5 bundles Billing-Protection + the Peak-Demand Tracker) — released. Never blocked E1 (`modes/`) or E2 (`profiles/`) — those already had ADR-0002 homes. |
| **G-ADR-0011** *(resolved — ADR-0011, Accepted)* | *Cross-Manager coordination via domain events* — fixes the publish/subscribe pattern (no direct Manager→Manager calls) and the per-trigger event-vs-rederive decision (system-design §4 rule 5). ADR-0024 later refines it on the Coordinator → Notification Manager edge (a level signal must also publish its clearing edge), without reopening it. | Tasks **M2** (Vehicle-Limit Manager) and **M3** (Notification Manager), and the event-publish step of **M1** (Coordinator) — released. |
| **G-ADR-0015** *(resolved — ADR-0015, Accepted)* | *Package home for the Managers beyond the Coordinator* — the same question ADR-0010 answered for the Engines, unanswered by ADR-0002/-0010 for M2/M3. Decided: a `managers/` subpackage (`vehicle_limit.py`, `notification_manager.py`), with `coordinator.py`/`coordinator_cycle.py` staying at the package root as the single, explicitly grandfathered exception, and `tests/managers/` mirroring 1:1. | Tasks **M2** and **M3** — released. Did not block **M1**, which ADR-0002 already homed at `coordinator.py`. |
| **G-ADR-0018/0019** *(resolved — ADR-0018 and ADR-0019, both Accepted)* | *RA3's access direction and package home.* ADR-0018 fixes the shape: the Coordinator **pulls** owned-entity values through the Store each cycle rather than entities pushing into it (superseding ADR-0014's held-reference setters and ADR-0016's per-field HA event, both of which had solved on the wrong axis). ADR-0019 fixes the home: `adapters/store.py`, joining V1/V11/V13 as one Resource-Access package, rather than a new subpackage or a root module. | Task **RA3**, and the owned-entity read path of **M1** that depends on its shape — released. |
| **G-NAMING** *(resolved — ADR-0004 + ADR-0013, both Accepted)* | *Owned-entity naming.* ADR-0004 makes owned entities **native platform entities** under the `smart_charging_` prefix (`select.smart_charging_profile`, `number.smart_charging_soc_limit_override`, `select.smart_charging_mode`, `sensor.smart_charging_monthly_peak_kw`, …), and `entity-catalog.md` was conformed to those native names via the analysis review cycle, so ADR-0004 stands unchanged. That left a second half open, which **ADR-0013** then settled: under `has_entity_name = True`, HA derives an owned entity's `object_id` from its *translated display name*, so the shipped `entity_id`s neither matched the catalog nor were stable across locales. Decided: pin an explicit, locale-independent object_id suffix per owned entity, equal to its catalog suffix. The tasks below cite the catalog's native names, which is what ships. (The install-time/tuning `sc_`-prefixed *helper* rows are a separate concern — not owned control/diagnostic entities, out of scope for this gate.) | **C2** (owned control entities), **C3** (diagnostic output entities), and RA3's owned-entity write path — released. |
| **G-ADR-0022** *(resolved — ADR-0022, Accepted)* | *Runtime-dashboard delivery mechanism* — how UC11's surface reaches an install at all, given system-design classifies it as a Client with no service of its own. Decided: programmatic registration as a locked, YAML-mode dashboard, regenerated and re-registered idempotently on every `async_setup_entry`. The classification is unchanged — the dashboard still touches only the Store and adapter read-backs. | Task **C5** — released. |

---

## 4. Build order overview

| Phase | Services (system-design §3) | Gate | Tasks | Status |
| --- | --- | --- | --- | --- |
| **0 — Gate** | — | see [§3](#3-structural-decision-gate-adrs-before-build) | G-ADR-0010, G-ADR-0011, G-ADR-0015, G-ADR-0018/0019, G-NAMING, G-ADR-0022 | All six resolved |
| **1 — Resource Access** (V1, V11, V13) | Adapter roles; Notification access; Config/State Store | — (G-ADR-0018/0019, G-NAMING resolved) | RA1, RA2, RA3, RA4 | Shipped (`adapters/`) |
| **2 — Engines** (V2–V10) | 5 Charging-Mode; 2 Profile; SOC-Target; Deadline; Billing-Protection; Peak-Demand Tracker; Grid-Safety; Signal-Conditioning; Cycle-Invariant; Capability-Gate | — (G-ADR-0010 resolved) | E1, E2, E3, E4, E5, E6, E7, E8, E9 | Shipped (`modes/`, `profiles/`, `engines/`) |
| **3 — Managers** | Charging Coordinator; Vehicle-Limit Manager; Notification Manager | — (G-ADR-0011, G-ADR-0015 resolved) | M1, M2, M3 | Shipped (`coordinator.py`, `coordinator_cycle.py`, `managers/`) |
| **4 — Clients** (V14 + triggers) | Control-interval timer; Owned control entities; Diagnostic outputs; Config/options flow; Dashboard (UC11); External-event wiring | — (G-NAMING, G-ADR-0022 resolved) | C1, C2, C3, C4, C5, C6 | Shipped (platform files, `config_flow.py`, `dashboard.py`, `__init__.py` wiring) |

Each phase ends with an **integration checkpoint** (⎔) proving the phase is wired to its callers
before the next phase depends on it.

The phases record the *dependency* order, not the chronology the work followed. Implementation ran
as vertical slices (a behaviour plus the Resource Access, Engines, and Client surface it needed),
each with its own spec and TDD plan under `docs/plans/`. What the phase order guarantees, and what
held throughout, is that no service was built before the services it calls existed.

---

## 5. Task list

Each task states: **Service** (system-design §3 role + volatility) · **Status** (whether it has
shipped, and where) · **Builds** · **Depends on** (what must exist/be stubbed first) · **ADR gate** ·
**Testable on its own** (the unit boundary, per ADR-0009) · **Integration checkpoint** (what proves
it is wired to its callers).

### Phase 0 — Structural-decision gate *(all six resolved)*

- **G-ADR-0010 — Engines package home (resolved).** `docs/adl/0010-engines-package-home.md`
  (Accepted) — a single `engines/` subpackage, one module per engine, extending ADR-0002. *Was
  blocking E3–E9; released.*
- **G-ADR-0011 — Cross-Manager domain events (resolved).**
  `docs/adl/0011-cross-manager-coordination-via-domain-events.md` (Accepted) — fixes the pub/sub
  pattern and the per-trigger event-vs-rederive decision; `docs/adl/0024-...` (Accepted) later
  refines the Coordinator → Notification Manager edge with a paired clear event. *Was blocking M1
  (publish step), M2, M3; released.*
- **G-ADR-0015 — Managers package home (resolved).** `docs/adl/0015-managers-package-home.md`
  (Accepted) — a `managers/` subpackage for every Manager module beyond the Coordinator, with
  `coordinator.py`/`coordinator_cycle.py` grandfathered at the package root. *Was blocking M2 and
  M3; released.*
- **G-ADR-0018/0019 — RA3's access shape and package home (resolved).**
  `docs/adl/0018-entity-to-coordinator-access-via-ra3-store.md` (Accepted) fixes the Coordinator's
  pull-based read of owned entities through the Store — superseding ADR-0016 (itself superseding
  ADR-0014), both of which had chosen a push mechanism; `docs/adl/0019-store-package-home.md`
  (Accepted) puts the Store at `adapters/store.py`. *Was blocking RA3 and M1's owned-entity read
  path; released.*
- **G-NAMING — Owned-entity naming (resolved).** Two ADRs, not one: `entity-catalog.md` was
  conformed to ADR-0004's native-entity names via the analysis review cycle, so ADR-0004 stands
  unchanged; and `docs/adl/0013-stable-owned-entity-object-ids.md` (Accepted) then pinned an
  explicit, locale-independent `object_id` suffix per owned entity, because HA's
  `has_entity_name = True` derivation was otherwise producing `entity_id`s from the *translated*
  display name — matching neither the catalog nor each other across locales. C2, C3, and RA3's
  owned-write path build against the catalog's names, which is what now ships. *Released.*
- **G-ADR-0022 — Runtime-dashboard delivery (resolved).**
  `docs/adl/0022-runtime-dashboard-delivery-mechanism.md` (Accepted) — programmatic registration of
  a locked, YAML-mode dashboard, regenerated idempotently on every setup. *Was blocking C5;
  released.*

### Phase 1 — Resource Access

**RA1 — Adapter protocol + config-driven adapter factory + control-cycle read/write adapters**
- **Service:** Resource Access, V1 (adapter roles) — the core of ADR-0003.
- **Status:** shipped — `adapters/base.py` (the `Adapter` protocol), `adapters/factory.py`, and the
  per-role modules (`numeric.py`, `status.py`, `presence.py`, `boolean.py`, `sun.py`, `tariff.py`,
  `time_read.py`, `_read_only.py`); tests under `tests/adapters/`.
- **Builds:** the shared `Adapter` protocol (`async read()` / `async write(value)`, ADR-0003) in
  `adapters/`; the factory that instantiates one adapter per role from config-entry **data** role
  mappings; and the control-cycle roles: `charger_current` (r/w), `charger_power`, `charger_status`
  (with the raw→canonical translation table), `ev_soc`, `ev_battery_capacity`, `net_power`,
  `grid_voltage`, `solar_power`. A role returning `None` is the ADR-0007 fault signal (grid voltage
  excepted, NF4) — the adapter surfaces `None`, it does not decide policy.
- **Depends on:** config-entry data shape (ADR-0003/0005) — provided as fixtures for now; RA3's
  full Store not required (role mappings can be passed in).
- **ADR gate:** none new (ADR-0003 already accepted).
- **Testable on its own:** HA test harness (ADR-0009 — adapters are HA-coupled): entity-state edge
  cases (missing / unavailable / unmapped), and the `charger_status` translation table
  (raw→canonical) in both directions.
- **Integration checkpoint:** ⎔ factory produces the full control-cycle adapter set from a sample
  config entry; each `read()` returns a canonical value or `None` against a mocked HA state.

**RA2 — Policy-input read adapters**
- **Service:** Resource Access, V1 (continuation of the same adapter layer).
- **Status:** shipped — the roles are registered by `adapters/factory.py` and keyed by the `ROLE_*`
  constants in `const.py`.
- **Builds:** `solar_forecast`, `low_tariff`, `sun`, `car_home`, `departure_external`,
  `home_day_external` — the roles consumed by the Deadline, Profile, and Notification services
  rather than the raw set-point path.
- **Depends on:** RA1 (protocol + factory).
- **ADR gate:** none.
- **Testable on its own:** HA harness; same edge-case matrix as RA1.
- **Integration checkpoint:** ⎔ all non-vehicle-limit roles resolve through the factory. (The role
  set has since grown past the count this plan was first derived against — `notification_target`
  for RA4 and the optional `monthly_peak_external` of ADR-0030 are the additions; the factory
  remains the single place a role is instantiated.)

**RA3 — Config/State Store access**
- **Service:** Resource Access, V13 (Config/State Store).
- **Status:** shipped — `adapters/store.py` (`Store.resolve_entity_id` / `read` / `write`, resolving
  an owned entity by its ADR-0013 `object_id` suffix through the entity registry), with the
  config-entry data/options half in `config.py`; tests in `tests/adapters/test_store.py`.
- **Builds:** reads of config-entry **data** (role mappings, translation tables, capabilities) and
  **options** (tunable thresholds, control interval, ADR-0005); reads **and writes** of owned-entity
  state via HA's entity/restore-state registry (ADR-0004). No custom persistence layer.
- **Depends on:** RA1 (data shape). The owned-entity read/write path targets the native names
  settled by G-NAMING (`number.smart_charging_soc_limit_override`,
  `sensor.smart_charging_monthly_peak_kw`, …); the config/options **read** path is independent of it
  and can proceed first.
- **ADR gate:** **G-ADR-0018/0019** — ADR-0018 fixes the direction (the Coordinator *pulls* owned
  values through the Store each cycle; entities do not push into it), ADR-0019 the home
  (`adapters/store.py`, inside the existing Resource-Access package). Both Accepted; G-NAMING and
  ADR-0013 fix the names the Store resolves against.
- **Testable on its own:** HA harness — data/options reads; owned-entity round-trip
  (write → restore-state → read) against the native names.
- **Integration checkpoint:** ⎔ Coordinator (M1) and the Clients read config/options and owned
  entities through the Store, with no direct HA-registry access outside it.

**RA4 — Notification access**
- **Service:** Resource Access, V11 (Notification Resource Access).
- **Status:** shipped — `adapters/notify.py` (`NotifyAdapter`, the `notification_target` role);
  tests in `tests/adapters/test_notify.py`.
- **Builds:** reach the HA `notify` service / mobile app to deliver a message and receive an
  actionable response.
- **Depends on:** nothing in this layer.
- **ADR gate:** none.
- **Testable on its own:** HA harness — message dispatch and simulated action response.
- **Integration checkpoint:** ⎔ Notification Manager (M3) delivers and captures a response through it.

> **⎔ Phase 1 checkpoint:** every Resource-Access class reachable through its factory/Store; no
> logic layer references a raw upstream entity directly (NF3 guard). The owned-write path builds
> against the native entity names (G-NAMING resolved).

### Phase 2 — Engines

> All Engines are **pure functions of their inputs** and perform **no I/O and call no other Engine**
> (§4 rule 4). Stateful Engines (E7, E8, and the E5 Tracker) take their cross-cycle state as a
> **parameter** threaded by the Manager. Every Engine is unit-tested with **plain pytest** (ADR-0009)
> — no HA harness. The per-Engine "integration checkpoint" is therefore realized in M1/M2/M3, where
> the Manager feeds real inputs; noted per task.

**E1 — Charging-Mode Engines (`Off`, `Solar`, `SolarOnly`, `Captar`, `Power`)**
- **Service:** Engine, V2. Home: `modes/` (ADR-0002 — no new ADR).
- **Status:** shipped — `modes/solar.py`, `modes/solar_only.py`, `modes/captar.py`,
  `modes/power.py` (plus the shared `_amp_step.py`/`_phase.py`/`_mode_state.py` helpers); tests
  under `tests/modes/`. **`Off` has no module of its own:** it computes nothing — it is a stop
  branch the Coordinator takes directly (`coordinator.py`'s dispatch checks for `MODE_OFF` before
  ever reaching the registry, so `_OffModeHandler`'s `desired_current` is never called on that
  path); the trivial `_OffModeHandler` in `coordinator_cycle.py` exists so `MODE_OFF` is still a
  registered member of ADR-0012's `ModeHandler` registry, which is what lets the dispatch guard
  accept it and lets its `is_soc_gated`/`is_solar_mode` flags participate in the same lookups the
  four computing modes use. The four modes that *do* compute a current are the four modules.
- **Builds:** desired charger current from conditioned readings + resolved SOC limit + config, one
  self-contained module per computing mode (NF2); `Off` → 0 A via the Coordinator's stop branch.
  `Solar`/`SolarOnly` surplus is
  `charger_w − net_w`, not `−net_w` (see [§6 scaffolding-plan reconciliation](#6-reconciliation-with-the-scaffolding-plan)).
- **Depends on:** the shape of conditioned readings (E7 output) and resolved SOC limit (E3) — as
  plain data types; no runtime dependency (Engines don't call Engines).
- **ADR gate:** none (ADR-0002 home). *Independently testable per mode.*
- **Testable on its own:** plain pytest per mode, incl. the closed-loop surplus regression (a mode
  must hold steady, not oscillate, when its own draw is in `net_w`); gate on `charger_status`.
- **Integration checkpoint:** ⎔ M1 dispatches to the active mode and gets a desired current.

**E2 — Profile Engines (`Manual`, `Auto`)**
- **Service:** Engine, V3. Home: `profiles/` (ADR-0002).
- **Status:** shipped — `profiles/manual.py`, `profiles/auto.py`, and `profiles/policy.py`; tests
  under `tests/profiles/`. ADR-0017 (Accepted) settled the shape the two profiles take: a
  `ModeSelectionPolicy` Protocol with `ManualPolicy`/`AutoPolicy` registered in a
  `PROFILE_POLICIES` dict keyed by the same `PROFILE_MANUAL`/`PROFILE_AUTO` values
  `select.smart_charging_profile` stores, replacing a free function plus a two-way string check in
  the Coordinator. The registry lives in `profiles/` (unlike ADR-0012's Coordinator-side
  `ModeHandler` registry, profile selection threads no per-cycle state). This fixes *how* the two
  profiles are structured; it does not change which decision E2 owns — mode selection only, with
  SOC-limit coordination staying in E3.
- **Builds:** which mode is active given observable conditions passed in — `Manual` → the user's
  selection; `Auto` → `resolution-rules.md` mode-selection (urgency, tariff, sun, surplus, **and the
  set of available modes passed in as an input**, not a Capability-Gate call — §4 rule 4).
- **Depends on:** E9 output (available modes), E3 output (the resolved active SOC limit, row 1),
  E4 output (required current, row 2), E7 output (conditioned sun/surplus, row 3), and the plain
  reserve-condition flag the Coordinator evaluates once for R9 (row 4) — all as input data only.
- **ADR gate:** none (ADR-0002 home).
- **Testable on its own:** plain pytest; `Manual` returns the selection; `Auto` reproduces the
  resolution-rules table, incl. UC05 escalation to `Captar` and UC07 decline of overnight top-up.
- **Integration checkpoint:** ⎔ M1 obtains the active mode; owned selector option-list (C2) uses the
  same capability facts via the entity-definition path.

**E3 — SOC-Target Engine**
- **Service:** Engine, V4 (cross-cutting). **ADR gate: G-ADR-0010** (package home — resolved).
- **Status:** shipped — `engines/soc_target.py`; tests in `tests/engines/test_soc_target.py`. The
  Coordinator-side gating around it (which cycle's flags feed the step-up/cap rows) lives in
  `coordinator_cycle.py`'s `SocGateResolver`/`SolarStepUpGate` per ADR-0012/ADR-0023, not in the
  engine.
- **Builds:** the single active SOC limit (reserve cap → step-up → default, R7) and its lifecycle
  transitions (R7/R8/R9); realizes UC06 (step-up row) and UC07's cap row.
- **Depends on:** ADR-0010 home; deadline inputs (E4) for the cap row (tomorrow's deadline); the
  active profile and the previous cycle's active mode (plain input flags, R8's `Auto`-only gate,
  not a Profile Engine call) — as data.
- **Testable on its own:** plain pytest — the three-row lookup and R8/R9 transitions, incl. the
  `Manual` negative case (no step-up, no cap regardless of home-day flag or forecast); `SocReached`
  must not resume on sensor noise, only a genuine limit change or reconnect (R7).
- **Integration checkpoint:** ⎔ M1 (cycle) is its only caller today. M2 (vehicle-limit sync) and M3 (UC10's
  below-limit check) consume its *resolved* output through the materialized
  `sensor.smart_charging_active_soc_limit` the Coordinator publishes, not by calling this engine —
  neither Manager holds the Coordinator-threaded step-up/reserve context the resolution composes
  (ADR-0011; system-design §5.2/§5.3).

**E4 — Deadline Engine**
- **Service:** Engine, V5 (cross-cutting). **ADR gate: G-ADR-0010** (resolved).
- **Status:** shipped — `engines/deadline.py`; tests in `tests/engines/test_deadline.py`. The
  urgency call site's own adapter reads and the `resolve_deadline_urgency` gating unit sit in
  `coordinator.py`/`coordinator_cycle.py` per ADR-0023.
- **Builds:** resolved departure deadline (today + one-day-ahead, R14), required current, whether
  urgency is in effect, and the per-profile lever set it is willing to spend (R5/R15).
- **Depends on:** ADR-0010; adapter-read deadline sources (RA2) — as data.
- **Testable on its own:** plain pytest — deadline resolution across sources; urgency threshold;
  R5 unreachable determination.
- **Integration checkpoint:** ⎔ M1 (urgency + required current), M3 (lead-time window); the
  `DeadlineUnreachableNotified` publish is M1's, subscribed by M3 (ADR-0011).

**E5 — Billing-Protection Engine + Peak-Demand Tracker**
- **Service:** Engine, V6 — a pure Engine (Billing-Protection) plus a **stateful** Engine (Peak-Demand
  Tracker). **ADR gate: G-ADR-0010** (resolved).
- **Status:** shipped — `engines/billing_protection.py` and `engines/peak_demand_tracker.py`; tests
  in `tests/engines/test_billing_protection.py` and `tests/engines/test_peak_demand_tracker.py`.
  The Tracker's monthly bookkeeping state is owned by `coordinator_cycle.py`'s `PeakDemandState`
  (ADR-0012), which is a distinct concern from the R3 clamp's own `PeakBreachTracker` breach timer.
  The published monthly peak has since gained a second, optional source: ADR-0030 adds the
  `monthly_peak_external` adapter role for a DSO-reported figure, and ADR-0032 resolves the two as
  `max(external, internal)` per cycle rather than folding one into the other's state.
- **Builds:** effective peak limit and the R3 peak clamp, skippable **only** by `Power`'s R17 opt-out
  (C3); and the Tracker accumulating monthly peak demand from net import, reset monthly, surfaced as
  `sensor.smart_charging_monthly_peak_kw`. The clamp solves from the baseline actually flowing
  (`raw_net_w − raw_charger_w`), not the requested current (see [§6](#6-reconciliation-with-the-scaffolding-plan)).
  R3's grace period ("stop only after a *sustained* breach at minimum") lives here.
- **Depends on:** ADR-0010; the Tracker's running state is threaded by M1 (never HA-held in the
  Engine). The Tracker's *write* to `sensor.smart_charging_monthly_peak_kw` is M1's via the Store, not the Engine's.
- **Testable on its own:** plain pytest — effective-limit resolution, baseline-solved clamp math with
  worked examples, urgency-driven limit raise (UC05), the grace-period tracker, and the `Power`+R17
  skip.
- **Integration checkpoint:** ⎔ M1 applies the peak clamp as a distinct call site from Grid-Safety
  (ADR-0006), and writes the Tracker's value through the Store.

**E6 — Grid-Safety Engine**
- **Service:** Engine, V7 (cross-cutting). **ADR gate: G-ADR-0010** (resolved).
- **Status:** shipped — `engines/grid_safety.py`; tests in `tests/engines/test_grid_safety.py`.
- **Builds:** the C4 grid-supply-ceiling clamp — **no opt-out**, runs every cycle; solves from the
  same baseline as E5; applied *after* the R3 grace evaluation with **no** grace period of its own
  (ADR-0006 distinction).
- **Depends on:** ADR-0010; must be a **structurally distinct** call site from E5 so the `Power`
  opt-out can never reach C4 (ADR-0006).
- **Testable on its own:** plain pytest — ceiling clamp bounds below the ceiling for a requesting-32A
  / drawing-6A case; never skipped.
- **Integration checkpoint:** ⎔ M1 calls E6 unconditionally after E5.

**E7 — Signal-Conditioning Engine** *(stateful)*
- **Service:** Engine, V8 (cross-cutting). **ADR gate: G-ADR-0010** (resolved).
- **Status:** shipped — `engines/signal_conditioning.py`; tests in
  `tests/engines/test_signal_conditioning.py`. ADR-0036 confirms the net-power-only scope below.
- **Builds:** smoothed `net_w` (R10 smoothing window; `solar_w` is read raw and never smoothed) and
  resolved supply voltage with the NF4 fallback. State (the smoothing window) is threaded by M1.
- **Depends on:** ADR-0010; raw readings from RA1 — supplied by M1.
- **Testable on its own:** plain pytest — window smoothing given a state parameter; NF4 voltage
  fallback (voltage `None` does **not** enter the fault path).
- **Integration checkpoint:** ⎔ M1 threads the smoothing state in/out each cycle.

**E8 — Cycle-Invariant Engine** *(stateful)*
- **Service:** Engine, V9 (cross-cutting). **ADR gate: G-ADR-0010** (resolved).
- **Status:** shipped — `engines/cycle_invariant.py`; tests in
  `tests/engines/test_cycle_invariant.py`.
- **Builds:** final current after R11 cooldown/hold gating and the C1 floor/cap; also the terminus of
  ADR-0007's fault path (an adapter `None`/exception routes here → force stop). State (R11 timers)
  threaded by M1; switching mode resets the incoming mode's timers (R11, wired at M1).
- **Depends on:** ADR-0010; timer state from M1.
- **Testable on its own:** plain pytest — cooldown/hold gating given state, C1 floor/cap, fault → 0 A.
- **Integration checkpoint:** ⎔ M1's `set_active_mode` resets timers; fault input forces stop + Fault
  sensor (via Store).

**E9 — Capability-Gate Engine**
- **Service:** Engine, V10 (cross-cutting). **ADR gate: G-ADR-0010** (resolved).
- **Status:** shipped — `engines/capability_gate.py`; tests in
  `tests/engines/test_capability_gate.py`.
- **Builds:** whether a given mode/behavior is available for the declared capabilities (R18) — the
  **runtime** realization. (The manual selector's option list is fixed at entity creation from the
  same capability facts — that is C2's entity-definition path, **not** a Client→Engine call.)
- **Depends on:** ADR-0010; declared capabilities from config-entry data (RA3 read) — as input.
- **Testable on its own:** plain pytest — available-mode set for a capability declaration.
- **Integration checkpoint:** ⎔ M1 passes available modes to E2 (`Auto`); C2 reuses the same facts.

> **⎔ Phase 2 checkpoint:** every Engine unit-tested in isolation with plain pytest; no Engine
> imports `homeassistant.*` or another Engine (the ADR-0009/ADR-0006 purity guard). Stateful Engines
> accept and return their state as parameters. *Met:* the purity half is enforced as an executable
> check in `tests/test_engine_purity.py` rather than by review alone.

### Phase 3 — Managers

**M1 — Charging Coordinator**
- **Service:** Manager (the control cycle, `control-cycle.md`). Home: `coordinator.py` (ADR-0002),
  a `DataUpdateCoordinator` (ADR-0006). ADR-0015 grandfathers it at the package root rather than
  moving it under `managers/` with M2/M3.
- **Status:** shipped — `coordinator.py` plus `coordinator_cycle.py`; tests in
  `tests/test_coordinator.py`, `tests/test_coordinator_cycle.py`, the per-slice end-to-end suites
  (`tests/test_solar_end_to_end.py`, `test_captar_end_to_end.py`,
  `test_deadline_soc_management_end_to_end.py`, `test_notifications_end_to_end.py`), and
  `tests/benchmarks/test_coordinator_perf.py`. Two ADRs settled its *internal* organization after
  this task was first written, without touching ADR-0006's step order or the two distinct clamp
  call sites: **ADR-0012** replaced the per-mode `if`/`elif` dispatch with a `ModeHandler` Protocol
  and registry, threaded per-cycle values through a `CycleContext` instead of loose locals, and
  extracted `PeakDemandState` and `SocGateResolver` into `coordinator_cycle.py`; **ADR-0023** then
  split the coordinator-side orchestration into differently-named methods (`_read_cycle_inputs`,
  `_resolve_deadline_and_reserve`, `_read_deadline_urgency_inputs`, `_dispatch_mode`,
  `_apply_peak_clamp`, `_apply_grid_ceiling_clamp`) plus further small pure units in
  `coordinator_cycle.py` (`SolarStepUpGate`, `resolve_solar_reserve_gate`). `_run_cycle` itself
  is still one large method calling them in order — ADR-0023's own goal of a short, literal
  sequence of named calls is only partly realized. Both ADRs are internal decomposition either
  way — the cycle still reads top-to-bottom as ADR-0006's ordered sequence.
- **Builds:** the ordered cycle from [system-design §5.1](system-design.md#51-control-cycle-realizes-uc01uc04-and-uc05uc07-in-passing):
  read (RA1 hardware **and** RA3's owned control entities, ADR-0018) → condition (E7) → resolve
  deadline (E4) → resolve SOC (E3) → required current/urgency (E4) → available modes (E9) → select
  mode (E2) → desired current (E1) → peak clamp (E5) → grid clamp (E6) → invariants (E8) → write
  (RA1). Owns and threads all stateful-Engine state; writes diagnostics
  (`sensor.smart_charging_monthly_peak_kw`, Fault/OK) through the Store (RA3). Realizes UC01–UC04 and
  UC05–UC07 in passing. **Publishes** the cycle's domain events. The ones ADR-0011 puts on the HA
  bus for a consuming Manager are the ones that ship: `ActiveSocLimitChanged` (→ M2) and
  `DeadlineUnreachableNotified` with its ADR-0024 paired `DeadlineUnreachableCleared` (→ M3).
  `ChargerCurrentSet` and `ActiveSocLimitReached` remain domain events of the cycle
  (`control-cycle.md`) with no cross-Manager consumer, so ADR-0011's criterion gives them no bus
  event to publish.
- **Depends on:** RA1, RA3 (owned-entity + config read, diagnostic write), all Engines E1–E9. Reads
  owned control-entity values through the Store — stubbable until C2.
- **ADR gate:** G-ADR-0011 (event-publish step; resolved) and G-ADR-0018/0019 (the owned-entity read
  path's direction and the Store's home; resolved). The compute pipeline was never gated.
- **Testable on its own:** HA harness (ADR-0009 — pipeline is HA-coupled): full-cycle regression per
  UC01–UC04; the two-distinct-clamps ordering (ADR-0006); fault → force-0A + Fault sensor (ADR-0007);
  `set_active_mode` timer reset (R11).
- **Integration checkpoint:** ⎔ driven by C1 (timer) and reading C2 (owned entities); one end-to-end
  cycle writes `charger_current` from a mocked hardware state.

**M2 — Vehicle-Limit Manager**
- **Service:** Manager (bidirectional vehicle charge-limit sync, V12). Home: `managers/` (ADR-0015).
- **Status:** shipped — `managers/vehicle_limit.py`; tests in `tests/managers/test_vehicle_limit.py`.
  It publishes `VehicleChargeLimitSynced` / `ManualChargeLimitAdopted` /
  `VehicleChargeLimitReset` and registers its own state-change listeners (see C6).
- **Builds:** [system-design §5.2](system-design.md#52-vehicle-charge-limit-sync-uc09) — write on
  SOC-limit change, adopt manual (vehicle-side) changes with an echo guard, reset to default on
  disconnect (R6/C2). Realizes UC09.
- **Depends on:** RA3 (vehicle_charge_limit adapter — see RA note below), RA1 (`car_home`,
  `charger_status`), RA3 Store (write `number.smart_charging_soc_limit_override`; read the resolved
  active SOC limit from `sensor.smart_charging_active_soc_limit` — the Coordinator's published
  resolution, not an E3 call, per ADR-0011; the sensor itself is C3, written by M1 — stubbable until
  C3); its triggers are
  adapter-observed state changes / the `ActiveSocLimitChanged` signal whose event-vs-rederive
  treatment **G-ADR-0011** settled.
- **ADR gate:** G-ADR-0011 (trigger mechanism) and G-ADR-0015 (package home) — both resolved.
- **Testable on its own:** HA harness — the three branches (system-initiated write with echo guard;
  vehicle-side adoption; disconnect reset).
- **Integration checkpoint:** ⎔ subscribes per ADR-0011; writes `vehicle_charge_limit` and
  `number.smart_charging_soc_limit_override` through adapter/Store; no direct call to/from M1.

> **RA note:** the `vehicle_charge_limit` (r/w) adapter role is consumed only by M2. It is built as a
> small extension of RA1's protocol at the start of M2 (labelled **RA1-VL**) rather than in Phase 1,
> since no earlier service needs it — this keeps Phase 1 to the roles the Coordinator requires while
> still building the adapter before its only caller. It is one more adapter role on RA1's factory,
> not a service of its own; no service is dropped. *Shipped as `ROLE_VEHICLE_CHARGE_LIMIT` in
> `adapters/factory.py`.*

**M3 — Notification Manager**
- **Service:** Manager (notification & prompting, V11). Home: `managers/` (ADR-0015).
- **Status:** shipped — `managers/notification_manager.py` (plus `notification_state.py` for the
  persisted de-dup/latch state); tests in `tests/managers/test_notification_manager.py`,
  `tests/test_notification_state.py`, and `tests/test_notifications_end_to_end.py`.
- **Builds:** [system-design §5.3](system-design.md#53-notification-plug-in-reminder-uc10--evening-prompt-uc08) —
  UC10 plug-in reminder (de-dup on departure window), UC08 evening home-day prompt (writes the
  home-day flag on "yes"), and delivery of R5's deadline-unreachable notice (subscribing to M1's
  `DeadlineUnreachableNotified`, and re-arming its once-per-occasion latch on the paired
  `DeadlineUnreachableCleared` per ADR-0024). Realizes UC08, UC10.
- **Depends on:** RA4 (Notification access), RA1/RA2 (`car_home`, `charger_status`, `solar_forecast`,
  `home_day_external`), RA3 Store (owned config + home-day flag write; read the resolved active SOC
  limit from `sensor.smart_charging_active_soc_limit` for UC10's below-limit check — the
  Coordinator's published resolution, not an E3 call, per ADR-0011; the sensor itself is C3, written
  by M1 — stubbable until C3), E4 (Deadline).
- **ADR gate:** G-ADR-0011 (trigger mechanism, refined by ADR-0024) and G-ADR-0015 (package home) —
  both resolved.
- **Testable on its own:** HA harness — UC10 reminder gating + de-dup; UC08 prompt + response capture;
  R5 delivery on the subscribed event.
- **Integration checkpoint:** ⎔ delivers via RA4, writes the home-day flag via Store, receives M1's
  event; no direct M1↔M3 call.

> **⎔ Phase 3 checkpoint:** all three Managers exercised against the HA harness; Manager↔Manager
> coordination happens **only** through the ADR-0011 event mechanism (assert no direct cross-Manager
> import/call). *Partially met:* all three Managers have HA-harness suites, and M2/M3 reach M1 only
> via bus events. The no-direct-call half is currently held by review and by `managers/`'s existence
> as the place to check it (ADR-0015's stated payoff), **not** by an executable guard — unlike the
> Engine purity half, which `tests/test_engine_purity.py` enforces. An import-guard test for
> `managers/` (extended to `coordinator.py`, the grandfathered Manager) is the outstanding piece.

### Phase 4 — Clients

**C1 — Control-interval timer**
- **Service:** Client. **Builds:** fires M1 every control interval (interval from options, ADR-0005).
- **Status:** shipped — the coordinator's own `update_interval` (`coordinator.py`), seeded from the
  ADR-0005 option and re-seeded on the ADR-0008 reload; the sibling `async_track_time_interval` in
  `__init__.py` drives M3's periodic evaluation on the same interval.
- **Depends on:** M1. **ADR gate:** none. **Testable on its own:** HA harness — interval fires the
  coordinator; interval change (options) re-schedules (ADR-0008 reload).
- **Integration checkpoint:** ⎔ a tick triggers exactly one M1 cycle.

**C2 — Owned control entities**
- **Service:** Client, V14. **ADR gate:** none blocking (G-NAMING resolved by ADR-0004 + ADR-0013).
- **Status:** shipped — `entity.py` base classes plus `select.py`, `number.py`, `time.py`,
  `switch.py`; tests in `tests/test_select.py`, `test_number.py`, `test_time.py`, `test_switch.py`,
  `test_entity.py`, `test_entity_labels.py`. Two structural details settled after this task was
  first written: each owned entity pins an explicit `object_id` suffix (ADR-0013) rather than
  inheriting one derived from its translated name, and capability-gated entities are disabled at the
  **registry** level rather than not created at all — `_attr_entity_registry_enabled_default` on
  first registration plus a setup-time `sync_disabled_by` for the reconfigure case (`entity.py`),
  which never overrides a user's own enable/disable choice. The second is ADR-0028, whose code has
  shipped while the ADR itself is still **Proposed** — the one place in this plan where the
  ADR-before-build rule was not met in order; it is a record to reconcile in `docs/adl/`, not a gate
  that still blocks C2.
- **Builds:** the user-set entities — active profile/mode, default SOC limit, `Power` target current,
  departure times, home-day flag (`entity.py` base classes, ADR-0002; platform files
  `select`/`number`/`time`/`switch`). The `select.smart_charging_mode` selector's option list is fixed at
  creation from declared capabilities (the E9-facts entity-definition path, **not** a runtime
  Client→Engine call).
- **Depends on:** RA3 (Store owned-read/write path — the Coordinator *pulls* these values each cycle
  per ADR-0018; the entities do not push into it).
- **Testable on its own:** HA harness — entity creation, restore-state round-trip, capability-limited
  option list.
- **Integration checkpoint:** ⎔ M1 reads owned values through the Store (replacing C2 stubs used in M1's tests).

**C3 — Diagnostic output entities**
- **Service:** owned entities the Coordinator **writes** (not the user), V13/V14. system-design §3
  classifies these as *owned entities written through the Store, **not Clients***; they are listed
  under Phase 4 for **build-order** reasons only (they depend on M1 the writer),
  not reclassified as Clients. **ADR gate:** none blocking (G-NAMING resolved).
- **Status:** shipped — `sensor.py`; tests in `tests/test_sensor.py`. The population has grown past
  the four this task originally named, each addition decided by its own ADR and all following the
  same written-through-the-Store shape: the dashboard-prerequisite read-outs
  (`active_soc_limit`, `solar_surplus_w`, `peak_headroom_a`, `time_to_full`), the adapter-readings
  diagnostic (ADR-0021), the config-mirror sensors (ADR-0031, disabled by default), and the
  dedicated charger-status sensor (ADR-0034, with ADR-0035's unmatched-state default).
- **Builds:** `sensor.smart_charging_monthly_peak_kw`, the Fault/OK status sensor (ADR-0007), and resolved
  read-outs the dashboard surfaces (`sensor.smart_charging_active_mode`,
  `sensor.smart_charging_effective_peak_limit`, and the diagnostics named under Status above).
  Written by M1 via the Store, consumed read-only by the dashboard.
- **Depends on:** M1 (writer), RA3 (Store).
- **Testable on its own:** HA harness — M1 write appears on the entity; Fault sensor reflects the
  ADR-0007 path.
- **Integration checkpoint:** ⎔ dashboard (C5) reads these read-only.

**C4 — Install-time config flow / options flow**
- **Service:** Client, V14 (ADR-0003/0005).
- **Status:** shipped — `config_flow.py`; tests in `tests/test_config_flow.py` and
  `tests/test_config_flow_translations.py`. Its step structure was decided after this task was
  written: ADR-0027 (superseding ADR-0025) organizes the flow into topic steps rather than one
  monolithic form. That is a shape decision inside C4; the buckets it writes (data vs options,
  ADR-0005) and the reload it triggers (ADR-0008) are unchanged.
- **Builds:** maps adapter roles, declares capabilities,
  sets install-time thresholds (data); tunes options anytime; triggers reload on change (ADR-0008).
  Holds no orchestration — writes only through the Store.
- **Depends on:** RA3 (Store data/options write), RA1 factory (role list to map). **ADR gate:** none
  new (its owned-entity *creation* is C2's concern; C4 writes config buckets).
- **Testable on its own:** HA harness — a full flow produces a valid config entry; an options change
  reloads the entry (ADR-0008).
- **Integration checkpoint:** ⎔ the entry C4 writes drives RA1's factory and the Store's data/options
  reads on setup.

**C5 — Runtime dashboard (UC11)**
- **Service:** Client, no service of its own (R19).
- **Status:** shipped — `dashboard.py`, registered from `async_setup_entry` after the platforms and
  wrapped so a frontend/Lovelace failure can never take the control loop down; tests in
  `tests/test_dashboard.py`.
- **Builds:** observes charging status + every
  runtime-classified entity and edits them in place, touching **only the Store** and adapter
  read-backs — no dashboard-specific logic per new entity (R19).
- **Depends on:** C2 (owned control entities), C3 (diagnostics), RA1/RA2 (read-backs), RA3 (Store).
- **ADR gate:** **G-ADR-0022** — ADR-0022 (Accepted) fixes the delivery mechanism: a locked,
  YAML-mode dashboard registered programmatically and regenerated idempotently on every setup.
  Otherwise inherits C2/C3's settled native names.
- **Testable on its own:** HA harness / Lovelace config — edits flow to the same entities other UCs
  consume; renders read-backs read-only.
- **Integration checkpoint:** ⎔ an edit in the dashboard changes an owned entity that M1 then reads.

**C6 — External-event wiring**
- **Service:** Client (external event sources). **Builds:** wires charger connect/disconnect
  transitions, user-made vehicle-limit changes, and mobile-app notification actions to M2/M3 per the
  ADR-0011 mechanism (state-change observation vs published event, as ADR-0011 decides).
- **Status:** shipped, but **not as a separate module** — this task has no code of its own. Each
  Manager registers its own subscriptions (`vehicle_limit.register_listeners` /
  `prime_status` for the charger-status and vehicle-limit state changes;
  `notification_manager.register_listeners` for the deadline bus events, plus `NotifyAdapter`'s own
  mobile-action listener), and `__init__.py` owns only the *ordering* of those registrations
  relative to platform setup and the first refresh — deliberately, since each ordering constraint is
  a property of the Manager being registered. system-design §3's "External event sources" Client is
  therefore realized as the subscription surface of M2/M3 rather than as a module of its own — the
  Client→Manager call direction it names is honoured either way (each trigger reaches exactly one
  Manager, and no Manager reaches another). C6 survives here as a build-order and
  integration-checkpoint entry, not as an unbuilt task.
- **Depends on:** M2, M3, and the ADR-0011 decision.
- **ADR gate:** inherits G-ADR-0011 (resolved).
- **Testable on its own:** HA harness — each external trigger reaches its Manager.
- **Integration checkpoint:** ⎔ a simulated connect/disconnect and a vehicle-side limit change each
  drive the correct Manager branch end-to-end.

> **⎔ Phase 4 / system checkpoint:** the full loop runs — timer → coordinator → clamps → write;
> owned entities editable via dashboard and config flow; notifications and vehicle-limit sync fire on
> their triggers — validated end-to-end against every UC01–UC11 acceptance criterion. *Met per
> slice:* the end-to-end suites (`tests/test_solar_end_to_end.py`, `test_captar_end_to_end.py`,
> `test_deadline_soc_management_end_to_end.py`, `test_notifications_end_to_end.py`) each validate
> their slice's use-cases against the assembled loop; there is no single suite asserting UC01–UC11
> coverage in one place.

---

## 6. Reconciliation with the scaffolding plan

A scaffolding plan drafted **2026-07-04**, before this design phase existed, proposed a 16-task TDD
sequence for the same ground. It referenced the ADRs directly rather than a project plan, was
organized **functionally** (config flow → adapters → coordinator → the five modes → `Manual`
profile → owned entities), and was scoped to UC01–UC04 (`Off`/`Solar`/`SolarOnly`/`Captar`/`Power` +
`Manual`), deferring `Auto`, R5, R6, R8, R9, R12/R13 with `TODO(UCnn)` markers. It was never merged;
`docs/plans/` holds no such document. This section is kept because two of its substantive
corrections are cited as test anchors elsewhere in this plan, and because it records why the
functional sequence was not the one adopted.

**Decision: this project plan supersedes the scaffolding plan as the authoritative build sequence;
the scaffolding plan's task-level *content* is folded into the matching tasks here as implementation
reference.** Rationale:

- The scaffolding plan's functional ordering is not wrong, but it is not *derived from* the
  volatility decomposition — this plan's phase order (Resource Access → Engines → Managers → Clients)
  is, and it makes the ADR gates and cross-Manager event boundary explicit, which the scaffolding
  plan predates.
- The scaffolding plan's substantive corrections are **retained** and mapped onto tasks here, so no
  review value is lost:
  - the `charger_w − net_w` surplus formula and the closed-loop no-oscillation regression → **E1**;
  - the baseline-solved (`raw_net_w − raw_charger_w`) clamp math and worked-example tests → **E5/E6**;
  - the R3 grace-period `PeakBreachTracker` → **E5**; the C4-after-grace, no-cooldown distinction → **E6**;
  - `set_active_mode` timer reset (R11) and the `SocReached`-noise guard (R7) → **E8/E3**;
  - `charger_status` gating on every mode → **E1**; the config-flow status-map key fix → **C4/RA1**.
- Its UC01–UC04-only scope maps cleanly onto a **first implementation slice** of this plan:
  RA1 + E1(`Off`/`Solar`/`SolarOnly`/`Captar`/`Power`) + E2(`Manual`) + E5/E6/E7/E8 + M1 + C2/C4.
  `Auto` (E2), E3/E4/E9, M2, M3, and C3/C5/C6 are the later slices, matching its deferrals.

**Disposition:** the scaffolding plan was retired in favour of this document, which carries the
authoritative sequence; its corrections survive via the mapping above. Implementation then proceeded
as a series of per-slice specs and TDD plans under `docs/plans/` (the `Power` MVP first, then
`Captar`, `Solar`/`SolarOnly`, deadline/SOC management, the vehicle-limit Manager, notifications,
the RA3 Store, the config flow, and the dashboard), each derived from the tasks above rather than
from the retired functional sequence.

---

## 7. Self-check

- **Build order obeys the static diagram.** Every task depends only on services below it in §4's
  call directions (Resource Access/Engines → Managers → Clients); no task requires a caller of its
  own to exist first. Engines depend on no lower layer (§4 rule 4); Managers depend on no other
  Manager (§4 rule 5) — reflected in M1/M2/M3 having no mutual ordering edge. M2 and M3 reading the
  resolved active SOC limit from `sensor.smart_charging_active_soc_limit` (C3, written by M1) is not
  an exception: the read is Resource Access through the Store, not a call on M1 or on C3, so the
  direction still runs Manager → Resource Access. It is a *runtime* rather than a build-order
  dependency — both are stubbable until C3 exists, as their task lines say.
- **Every ADR-worthy decision has a task line before its dependent.** G-ADR-0010 (ADR-0010) precedes
  E3–E9; G-ADR-0011 (ADR-0011, refined by ADR-0024) precedes M1's publish step, M2, M3, C6;
  G-ADR-0015 (ADR-0015) precedes M2 and M3; G-ADR-0018/0019 (ADR-0018, ADR-0019) precedes RA3 and
  M1's owned-entity read path; G-NAMING (ADR-0004 with ADR-0013) precedes C2, C3, and RA3's
  owned-write path; G-ADR-0022 (ADR-0022) precedes C5. All six are closed, so no task below is
  blocked by a structural-decision gate. **One exception to "before, not after":** ADR-0028's
  registry-level capability disabling (C2) shipped while that ADR is still Proposed — recorded at
  C2 rather than smoothed over.
- **Every service in `system-design.md` §3 appears in exactly one task, none duplicated:**
  Adapters V1 → RA1/RA2 (+RA1-VL in M2); Notification access V11 → RA4; Store V13 → RA3;
  5 Charging-Mode Engines → E1; 2 Profile Engines → E2; SOC-Target → E3; Deadline → E4;
  Billing-Protection + Peak-Demand Tracker → E5; Grid-Safety → E6; Signal-Conditioning → E7;
  Cycle-Invariant → E8; Capability-Gate → E9; Charging Coordinator → M1; Vehicle-Limit Manager → M2;
  Notification Manager → M3; Control-interval timer → C1; Owned control entities → C2; Diagnostic
  outputs → C3; Config/options flow → C4; Dashboard (UC11) → C5; External-event sources → C6.
  Resources are external and built by no task (noted in §2). Two mappings are one-task-to-no-module
  rather than one-task-to-one-module, and say so at the task: `Off` (part of E1) is a Coordinator
  stop branch, and C6 is realized as M2/M3's own subscription surface. Neither drops a service or
  duplicates one.
- **Every task's Status reflects the shipped tree**, checked against
  `custom_components/smart_charging/` and `tests/`: all four Resource-Access tasks, all nine Engine
  tasks, all three Manager tasks, and all six Client tasks have shipped. Two checkpoints are only
  partially met and are marked as such: the Phase 3 no-cross-Manager-call assertion (no executable
  guard) and the Phase 4 UC01–UC11 end-to-end validation (per-slice, not one suite).
- **Independently testable.** Each task names its unit boundary per ADR-0009 (pure Engines → plain
  pytest; Resource Access + Managers + Clients → HA harness) and an integration checkpoint proving
  it is wired to its callers before the next task depends on it.
- **Derived, not designed.** No service, call direction, or volatility is introduced here that is not
  already in `system-design.md`; the only additions are *sequence*, *ADR gates*, and *checkpoints*.
