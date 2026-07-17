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

Three structural decisions `system-design.md` surfaces bear on build order. Two — **G-ADR-0010** and
**G-ADR-0011** — are **not yet decided** and each **blocks** specific tasks; per CLAUDE.md and the
`write-adr` cycle, the ADR is opened and approved **before** the first task that depends on it —
never retrofitted, with opening it (via `write-adr`, with its own tracking issue) the first step of
the phase that would otherwise be blocked. The third, **G-NAMING**, is now **resolved** (see its row)
and blocks nothing further.

| Gate | Decision | Blocks |
| --- | --- | --- |
| **G-ADR-0010** | *Package home for the eight cross-cutting Engines* — an `engines/` subpackage vs top-level modules. ADR-0002 gives `adapters/`, `modes/`, `profiles/` homes but no home for SOC-Target, Deadline, Billing-Protection, Grid-Safety, Signal-Conditioning, Cycle-Invariant, Capability-Gate, Peak-Demand Tracker (system-design §8 follow-up). | Tasks **E3–E9** (the cross-cutting Engines; the eight engines map to E3–E9 because E5 bundles Billing-Protection + the Peak-Demand Tracker). Does **not** block E1 (`modes/`) or E2 (`profiles/`) — those already have ADR-0002 homes. |
| **G-ADR-0011** | *Cross-Manager coordination via domain events* — fix the publish/subscribe pattern (no direct Manager→Manager calls) and decide, per trigger, between publishing a new domain event and re-deriving the condition per cycle (system-design §4 rule 5). | Tasks **M2** (Vehicle-Limit Manager) and **M3** (Notification Manager), and the event-publish step of **M1** (Coordinator). |
| **G-NAMING** *(resolved)* | *Owned-entity naming — settled.* ADR-0004 makes owned entities **native platform entities** under the `smart_charging_` prefix (`select.smart_charging_profile`, `number.smart_charging_soc_limit_override`, `select.smart_charging_mode`, `sensor.smart_charging_monthly_peak_kw`, …). The conflict is now resolved the "keep native naming" way: `entity-catalog.md` was conformed to ADR-0004's native names via the analysis review cycle, so **ADR-0004 stands unchanged and no new ADR was needed**. The tasks below cite those native names directly. (The install-time/tuning `sc_`-prefixed *helper* rows are a separate concern deferred to a future catalog reconciliation — not owned control/diagnostic entities, out of scope for this gate.) | **Nothing — resolved.** C2 (owned control entities), C3 (diagnostic output entities), and RA3's owned-entity write path now build against the settled native names. |

---

## 4. Build order overview

| Phase | Services (system-design §3) | Gate | Tasks |
| --- | --- | --- | --- |
| **0 — Gate** | — | Open/approve ADR-0010, ADR-0011 (owned-entity naming already settled via G-NAMING) | G-ADR-0010, G-ADR-0011 |
| **1 — Resource Access** (V1, V11, V13) | Adapter roles; Notification access; Config/State Store | — | RA1, RA2, RA3, RA4 |
| **2 — Engines** (V2–V10) | 5 Charging-Mode; 2 Profile; SOC-Target; Deadline; Billing-Protection; Peak-Demand Tracker; Grid-Safety; Signal-Conditioning; Cycle-Invariant; Capability-Gate | E3–E9 need ADR-0010 | E1, E2, E3, E4, E5, E6, E7, E8, E9 |
| **3 — Managers** | Charging Coordinator; Vehicle-Limit Manager; Notification Manager | M2/M3 (and M1's publish step) need ADR-0011 | M1, M2, M3 |
| **4 — Clients** (V14 + triggers) | Control-interval timer; Owned control entities; Diagnostic outputs; Config/options flow; Dashboard (UC11); External-event wiring | — (G-NAMING resolved) | C1, C2, C3, C4, C5, C6 |

Each phase ends with an **integration checkpoint** (⎔) proving the phase is wired to its callers
before the next phase depends on it.

---

## 5. Task list

Each task states: **Service** (system-design §3 role + volatility) · **Builds** · **Depends on**
(what must exist/be stubbed first) · **ADR gate** · **Testable on its own** (the unit boundary,
per ADR-0009) · **Integration checkpoint** (what proves it is wired to its callers).

### Phase 0 — Structural-decision gate

- **G-ADR-0010 — Engines package home.** Run `write-adr`; decide `engines/` subpackage vs top-level
  modules extending ADR-0002. *Blocks E3–E9.*
- **G-ADR-0011 — Cross-Manager domain events.** Run `write-adr`; fix the pub/sub pattern and the
  per-trigger event-vs-rederive decision. *Blocks M1 (publish step), M2, M3.*
- **G-NAMING — Owned-entity naming (resolved).** Settled the "keep native naming" way:
  `entity-catalog.md` was conformed to ADR-0004's native-entity names via the analysis review cycle,
  so ADR-0004 stands unchanged and no new ADR was needed. C2, C3, and RA3's owned-write path build
  against those native names directly — no gate remains.

### Phase 1 — Resource Access

**RA1 — Adapter protocol + config-driven adapter factory + control-cycle read/write adapters**
- **Service:** Resource Access, V1 (adapter roles) — the core of ADR-0003.
- **Builds:** the shared `Adapter` protocol (`async read()` / `async write(value)`, ADR-0003) in
  `adapters/`; the factory that instantiates one adapter per role from config-entry **data** role
  mappings; and the control-cycle roles: `charger_current` (r/w), `charger_power`, `charger_status`
  (with the raw→canonical translation table), `ev_soc`, `battery_capacity`, `net_power`,
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
- **Builds:** `solar_forecast`, `low_tariff`, `car_home`, `departure_external`, `home_day_external`
  — the roles consumed by the Deadline, Profile, and Notification services rather than the raw
  set-point path.
- **Depends on:** RA1 (protocol + factory).
- **ADR gate:** none.
- **Testable on its own:** HA harness; same edge-case matrix as RA1.
- **Integration checkpoint:** ⎔ all thirteen non-vehicle-limit roles resolve through the factory.

**RA3 — Config/State Store access**
- **Service:** Resource Access, V13 (Config/State Store).
- **Builds:** reads of config-entry **data** (role mappings, translation tables, capabilities) and
  **options** (tunable thresholds, control interval, ADR-0005); reads **and writes** of owned-entity
  state via HA's entity/restore-state registry (ADR-0004). No custom persistence layer.
- **Depends on:** RA1 (data shape). The owned-entity write path targets the native names settled by
  G-NAMING (`number.smart_charging_soc_limit_override`, `sensor.smart_charging_monthly_peak_kw`, …);
  the config/options **read** path is independent of it and can proceed first.
- **ADR gate:** none (G-NAMING resolved).
- **Testable on its own:** HA harness — data/options reads; owned-entity round-trip
  (write → restore-state → read) against the native names.
- **Integration checkpoint:** ⎔ Coordinator (M1) and the Clients read config/options and owned
  entities through the Store, with no direct HA-registry access outside it.

**RA4 — Notification access**
- **Service:** Resource Access, V11 (Notification Resource Access).
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
- **Builds:** desired charger current from conditioned readings + resolved SOC limit + config, one
  self-contained module per mode (NF2); `Off` → 0 A. `Solar`/`SolarOnly` surplus is
  `charger_w − net_w`, not `−net_w` (see [§6 scaffolding-plan reconciliation](#6-reconciliation-with-the-scaffolding-plan)).
- **Depends on:** the shape of conditioned readings (E8 output) and resolved SOC limit (E3) — as
  plain data types; no runtime dependency (Engines don't call Engines).
- **ADR gate:** none (ADR-0002 home). *Independently testable per mode.*
- **Testable on its own:** plain pytest per mode, incl. the closed-loop surplus regression (a mode
  must hold steady, not oscillate, when its own draw is in `net_w`); gate on `charger_status`.
- **Integration checkpoint:** ⎔ M1 dispatches to the active mode and gets a desired current.

**E2 — Profile Engines (`Manual`, `Auto`)**
- **Service:** Engine, V3. Home: `profiles/` (ADR-0002).
- **Builds:** which mode is active given observable conditions passed in — `Manual` → the user's
  selection; `Auto` → `resolution-rules.md` mode-selection (urgency, tariff, sun, surplus, **and the
  set of available modes passed in as an input**, not a Capability-Gate call — §4 rule 4).
- **Depends on:** E9 output (available modes) and E4/E8 outputs — as input data only.
- **ADR gate:** none (ADR-0002 home).
- **Testable on its own:** plain pytest; `Manual` returns the selection; `Auto` reproduces the
  resolution-rules table, incl. UC05 escalation to `Captar` and UC07 decline of overnight top-up.
- **Integration checkpoint:** ⎔ M1 obtains the active mode; owned selector option-list (C2) uses the
  same capability facts via the entity-definition path.

**E3 — SOC-Target Engine**
- **Service:** Engine, V4 (cross-cutting). **ADR gate: G-ADR-0010** (package home).
- **Builds:** the single active SOC limit (reserve cap → step-up → default, R7) and its lifecycle
  transitions (R7/R8/R9); realizes UC06 (step-up row) and UC07's cap row.
- **Depends on:** ADR-0010 home; deadline inputs (E4) for the cap row (tomorrow's deadline) — as data.
- **Testable on its own:** plain pytest — the three-row lookup and R8/R9 transitions; `SocReached`
  must not resume on sensor noise, only a genuine limit change or reconnect (R7).
- **Integration checkpoint:** ⎔ consumed by M1 (cycle), M2 (vehicle-limit sync), M3 (below-limit check).

**E4 — Deadline Engine**
- **Service:** Engine, V5 (cross-cutting). **ADR gate: G-ADR-0010.**
- **Builds:** resolved departure deadline (today + one-day-ahead, R14), required current, whether
  urgency is in effect, and the per-profile lever set it is willing to spend (R5/R15).
- **Depends on:** ADR-0010; adapter-read deadline sources (RA2) — as data.
- **Testable on its own:** plain pytest — deadline resolution across sources; urgency threshold;
  R5 unreachable determination.
- **Integration checkpoint:** ⎔ M1 (urgency + required current), M3 (lead-time window); the
  `DeadlineUnreachableNotified` publish is M1's, subscribed by M3 (ADR-0011).

**E5 — Billing-Protection Engine + Peak-Demand Tracker**
- **Service:** Engine, V6 — a pure Engine (Billing-Protection) plus a **stateful** Engine (Peak-Demand
  Tracker). **ADR gate: G-ADR-0010.**
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
- **Service:** Engine, V7 (cross-cutting). **ADR gate: G-ADR-0010.**
- **Builds:** the C4 grid-supply-ceiling clamp — **no opt-out**, runs every cycle; solves from the
  same baseline as E5; applied *after* the R3 grace evaluation with **no** grace period of its own
  (ADR-0006 distinction).
- **Depends on:** ADR-0010; must be a **structurally distinct** call site from E5 so the `Power`
  opt-out can never reach C4 (ADR-0006).
- **Testable on its own:** plain pytest — ceiling clamp bounds below the ceiling for a requesting-32A
  / drawing-6A case; never skipped.
- **Integration checkpoint:** ⎔ M1 calls E6 unconditionally after E5.

**E7 — Signal-Conditioning Engine** *(stateful)*
- **Service:** Engine, V8 (cross-cutting). **ADR gate: G-ADR-0010.**
- **Builds:** smoothed `net_w`/`solar_w` (R10 smoothing window) and resolved supply voltage with the
  NF4 fallback. State (the smoothing window) is threaded by M1.
- **Depends on:** ADR-0010; raw readings from RA1 — supplied by M1.
- **Testable on its own:** plain pytest — window smoothing given a state parameter; NF4 voltage
  fallback (voltage `None` does **not** enter the fault path).
- **Integration checkpoint:** ⎔ M1 threads the smoothing state in/out each cycle.

**E8 — Cycle-Invariant Engine** *(stateful)*
- **Service:** Engine, V9 (cross-cutting). **ADR gate: G-ADR-0010.**
- **Builds:** final current after R11 cooldown/hold gating and the C1 floor/cap; also the terminus of
  ADR-0007's fault path (an adapter `None`/exception routes here → force stop). State (R11 timers)
  threaded by M1; switching mode resets the incoming mode's timers (R11, wired at M1).
- **Depends on:** ADR-0010; timer state from M1.
- **Testable on its own:** plain pytest — cooldown/hold gating given state, C1 floor/cap, fault → 0 A.
- **Integration checkpoint:** ⎔ M1's `set_active_mode` resets timers; fault input forces stop + Fault
  sensor (via Store).

**E9 — Capability-Gate Engine**
- **Service:** Engine, V10 (cross-cutting). **ADR gate: G-ADR-0010.**
- **Builds:** whether a given mode/behavior is available for the declared capabilities (R18) — the
  **runtime** realization. (The manual selector's option list is fixed at entity creation from the
  same capability facts — that is C2's entity-definition path, **not** a Client→Engine call.)
- **Depends on:** ADR-0010; declared capabilities from config-entry data (RA3 read) — as input.
- **Testable on its own:** plain pytest — available-mode set for a capability declaration.
- **Integration checkpoint:** ⎔ M1 passes available modes to E2 (`Auto`); C2 reuses the same facts.

> **⎔ Phase 2 checkpoint:** every Engine unit-tested in isolation with plain pytest; no Engine
> imports `homeassistant.*` or another Engine (the ADR-0009/ADR-0006 purity guard). Stateful Engines
> accept and return their state as parameters.

### Phase 3 — Managers

**M1 — Charging Coordinator**
- **Service:** Manager (the control cycle, `control-cycle.md`). Home: `coordinator.py` (ADR-0002),
  a `DataUpdateCoordinator` (ADR-0006).
- **Builds:** the ordered cycle from [system-design §5.1](system-design.md#51-control-cycle-realizes-uc01uc04-and-uc05uc07-in-passing):
  read (RA1) → condition (E7) → resolve deadline (E4) → resolve SOC (E3) → required current/urgency
  (E4) → available modes (E9) → select mode (E2) → desired current (E1) → peak clamp (E5) → grid
  clamp (E6) → invariants (E8) → write (RA1). Owns and threads all stateful-Engine state; writes
  diagnostics (`sensor.smart_charging_monthly_peak_kw`, Fault/OK) through the Store (RA3). Realizes UC01–UC04 and
  UC05–UC07 in passing. **Publishes** `ChargerCurrentSet` / `ActiveSocLimitReached` /
  `DeadlineUnreachableNotified` — the publish step is gated on **G-ADR-0011**.
- **Depends on:** RA1, RA3 (read + diagnostic write), all Engines E1–E9. Reads owned control-entity
  values through the Store — stubbable until C2.
- **ADR gate:** G-ADR-0011 (event-publish step only; the compute pipeline is unblocked).
- **Testable on its own:** HA harness (ADR-0009 — pipeline is HA-coupled): full-cycle regression per
  UC01–UC04; the two-distinct-clamps ordering (ADR-0006); fault → force-0A + Fault sensor (ADR-0007);
  `set_active_mode` timer reset (R11).
- **Integration checkpoint:** ⎔ driven by C1 (timer) and reading C2 (owned entities); one end-to-end
  cycle writes `charger_current` from a mocked hardware state.

**M2 — Vehicle-Limit Manager**
- **Service:** Manager (bidirectional vehicle charge-limit sync, V12). **ADR gate: G-ADR-0011.**
- **Builds:** [system-design §5.2](system-design.md#52-vehicle-charge-limit-sync-uc09) — write on
  SOC-limit change, adopt manual (vehicle-side) changes with an echo guard, reset to default on
  disconnect (R6/C2). Realizes UC09.
- **Depends on:** RA3 (vehicle_charge_limit adapter — see RA note below), RA1 (`car_home`,
  `charger_status`), RA3 Store (write `number.smart_charging_soc_limit_override`), E3 (SOC-Target); its triggers are
  adapter-observed state changes / an SOC-limit-changed signal whose event-vs-rederive treatment is
  **G-ADR-0011**.
- **ADR gate:** G-ADR-0011.
- **Testable on its own:** HA harness — the three branches (system-initiated write with echo guard;
  vehicle-side adoption; disconnect reset).
- **Integration checkpoint:** ⎔ subscribes per ADR-0011; writes `vehicle_charge_limit` and
  `number.smart_charging_soc_limit_override` through adapter/Store; no direct call to/from M1.

> **RA note:** the `vehicle_charge_limit` (r/w) adapter role is consumed only by M2. It is built as a
> small extension of RA1's protocol at the start of M2 (labelled **RA1-VL**) rather than in Phase 1,
> since no earlier service needs it — this keeps Phase 1 to the roles the Coordinator requires while
> still building the adapter before its only caller. It is the fourteenth adapter role; no service is
> dropped.

**M3 — Notification Manager**
- **Service:** Manager (notification & prompting, V11). **ADR gate: G-ADR-0011.**
- **Builds:** [system-design §5.3](system-design.md#53-notification-plug-in-reminder-uc10--evening-prompt-uc08) —
  UC10 plug-in reminder (de-dup on departure window), UC08 evening home-day prompt (writes the
  home-day flag on "yes"), and delivery of R5's deadline-unreachable notice (subscribing to M1's
  `DeadlineUnreachableNotified`). Realizes UC08, UC10.
- **Depends on:** RA4 (Notification access), RA1/RA2 (`car_home`, `charger_status`, `solar_forecast`,
  `home_day_external`), RA3 Store (owned config + home-day flag write), E4 (Deadline), E3 (SOC-Target).
- **ADR gate:** G-ADR-0011.
- **Testable on its own:** HA harness — UC10 reminder gating + de-dup; UC08 prompt + response capture;
  R5 delivery on the subscribed event.
- **Integration checkpoint:** ⎔ delivers via RA4, writes the home-day flag via Store, receives M1's
  event; no direct M1↔M3 call.

> **⎔ Phase 3 checkpoint:** all three Managers exercised against the HA harness; Manager↔Manager
> coordination happens **only** through the ADR-0011 event mechanism (assert no direct cross-Manager
> import/call).

### Phase 4 — Clients

**C1 — Control-interval timer**
- **Service:** Client. **Builds:** fires M1 every control interval (interval from options, ADR-0005).
- **Depends on:** M1. **ADR gate:** none. **Testable on its own:** HA harness — interval fires the
  coordinator; interval change (options) re-schedules (ADR-0008 reload).
- **Integration checkpoint:** ⎔ a tick triggers exactly one M1 cycle.

**C2 — Owned control entities**
- **Service:** Client, V14. **ADR gate:** none (G-NAMING resolved — native names are settled).
- **Builds:** the user-set entities — active profile/mode, default SOC limit, `Power` target current,
  departure times, home-day flag (`entity.py` base classes, ADR-0002; platform files
  `select`/`number`/`time`/`switch`). The `select.smart_charging_mode` selector's option list is fixed at
  creation from declared capabilities (the E9-facts entity-definition path, **not** a runtime
  Client→Engine call).
- **Depends on:** RA3 (Store owned-write path). M1 reads these through the Store.
- **Testable on its own:** HA harness — entity creation, restore-state round-trip, capability-limited
  option list.
- **Integration checkpoint:** ⎔ M1 reads owned values through the Store (replacing C2 stubs used in M1's tests).

**C3 — Diagnostic output entities**
- **Service:** owned entities the Coordinator **writes** (not the user), V13/V14. system-design §3
  classifies these as *owned entities written through the Store, **not Clients***; they are listed
  under Phase 4 for **build-order** reasons only (they depend on M1 the writer),
  not reclassified as Clients. **ADR gate:** none (G-NAMING resolved).
- **Builds:** `sensor.smart_charging_monthly_peak_kw`, the Fault/OK status sensor (ADR-0007), and resolved
  read-outs the dashboard surfaces (`sensor.smart_charging_active_mode`,
  `sensor.smart_charging_effective_peak_limit`). Written by M1
  via the Store, consumed read-only by the dashboard.
- **Depends on:** M1 (writer), RA3 (Store).
- **Testable on its own:** HA harness — M1 write appears on the entity; Fault sensor reflects the
  ADR-0007 path.
- **Integration checkpoint:** ⎔ dashboard (C5) reads these read-only.

**C4 — Install-time config flow / options flow**
- **Service:** Client, V14 (ADR-0003/0005). **Builds:** maps adapter roles, declares capabilities,
  sets install-time thresholds (data); tunes options anytime; triggers reload on change (ADR-0008).
  Holds no orchestration — writes only through the Store.
- **Depends on:** RA3 (Store data/options write), RA1 factory (role list to map). **ADR gate:** none
  new (its owned-entity *creation* is C2's concern; C4 writes config buckets).
- **Testable on its own:** HA harness — a full flow produces a valid config entry; an options change
  reloads the entry (ADR-0008).
- **Integration checkpoint:** ⎔ the entry C4 writes drives RA1's factory and the Store's data/options
  reads on setup.

**C5 — Runtime dashboard (UC11)**
- **Service:** Client, no service of its own (R19). **Builds:** observes charging status + every
  runtime-classified entity and edits them in place, touching **only the Store** and adapter
  read-backs — no dashboard-specific logic per new entity (R19).
- **Depends on:** C2 (owned control entities), C3 (diagnostics), RA1/RA2 (read-backs), RA3 (Store).
- **ADR gate:** none (inherits C2/C3's settled native names).
- **Testable on its own:** HA harness / Lovelace config — edits flow to the same entities other UCs
  consume; renders read-backs read-only.
- **Integration checkpoint:** ⎔ an edit in the dashboard changes an owned entity that M1 then reads.

**C6 — External-event wiring**
- **Service:** Client (external event sources). **Builds:** wires charger connect/disconnect
  transitions, user-made vehicle-limit changes, and mobile-app notification actions to M2/M3 per the
  ADR-0011 mechanism (state-change observation vs published event, as ADR-0011 decides).
- **Depends on:** M2, M3, and the ADR-0011 decision.
- **ADR gate:** inherits G-ADR-0011.
- **Testable on its own:** HA harness — each external trigger reaches its Manager.
- **Integration checkpoint:** ⎔ a simulated connect/disconnect and a vehicle-side limit change each
  drive the correct Manager branch end-to-end.

> **⎔ Phase 4 / system checkpoint:** the full loop runs — timer → coordinator → clamps → write;
> owned entities editable via dashboard and config flow; notifications and vehicle-limit sync fire on
> their triggers — validated end-to-end against every UC01–UC11 acceptance criterion.

---

## 6. Reconciliation with the scaffolding plan

The pre-existing scaffolding plan `docs/plans/2026-07-04-smart-charging-scaffolding.md` is a 16-task
TDD plan authored **2026-07-04**, before this design phase existed. It references the ADRs directly
rather than a project plan, is organized **functionally** (config flow → adapters → coordinator →
the five modes → `Manual` profile → owned entities), and is scoped to UC01–UC04 (`Off`/`Solar`/
`SolarOnly`/`Captar`/`Power` + `Manual`), deferring `Auto`, R5, R6, R8, R9, R12/R13 with
`TODO(UCnn)` markers.

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

**Disposition:** the scaffolding plan is retired in favor of this document, which now carries the
authoritative sequence; its corrections survive via the mapping above. Its open review branch is
either closed with a pointer to this plan or repurposed as the first implementation slice (RA1→M1) —
a VCS housekeeping choice recorded in that branch's own thread, not here. It is not merged as-is.

---

## 7. Self-check

- **Build order obeys the static diagram.** Every task depends only on services below it in §4's
  call directions (Resource Access/Engines → Managers → Clients); no task requires a caller of its
  own to exist first. Engines depend on no lower layer (§4 rule 4); Managers depend on no other
  Manager (§4 rule 5) — reflected in M1/M2/M3 having no mutual ordering edge.
- **Every ADR-worthy decision has a task line before its dependent.** G-ADR-0010 precedes E3–E9;
  G-ADR-0011 precedes M1's publish step, M2, M3, C6; G-NAMING (now resolved) was settled before
  C2, C3, and RA3's owned-write path build against the native names. None retrofitted.
- **Every service in `system-design.md` §3 appears in exactly one task, none duplicated:**
  Adapters V1 → RA1/RA2 (+RA1-VL in M2); Notification access V11 → RA4; Store V13 → RA3;
  5 Charging-Mode Engines → E1; 2 Profile Engines → E2; SOC-Target → E3; Deadline → E4;
  Billing-Protection + Peak-Demand Tracker → E5; Grid-Safety → E6; Signal-Conditioning → E7;
  Cycle-Invariant → E8; Capability-Gate → E9; Charging Coordinator → M1; Vehicle-Limit Manager → M2;
  Notification Manager → M3; Control-interval timer → C1; Owned control entities → C2; Diagnostic
  outputs → C3; Config/options flow → C4; Dashboard (UC11) → C5; External-event sources → C6.
  Resources are external and built by no task (noted in §2).
- **Independently testable.** Each task names its unit boundary per ADR-0009 (pure Engines → plain
  pytest; Resource Access + Managers + Clients → HA harness) and an integration checkpoint proving
  it is wired to its callers before the next task depends on it.
- **Derived, not designed.** No service, call direction, or volatility is introduced here that is not
  already in `system-design.md`; the only additions are *sequence*, *ADR gates*, and *checkpoints*.
