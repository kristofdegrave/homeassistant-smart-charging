# ADR-0011: Cross-Manager coordination via domain events

Date: 2026-07-18
Status: Accepted

## Context

`docs/design/system-design.md` §4 rule 5 fixes the *pattern* by which the three Managers
(Charging Coordinator, Vehicle-Limit, Notification) coordinate: **they never call each
other**; cross-Manager coordination is publish/subscribe on domain events, which the DDD
convention in CLAUDE.md requires to map one-to-one onto Home Assistant automation triggers.
The design deliberately does **not** invent the concrete event vocabulary — it flags that as
candidate ADR-0011 (§8 follow-up) and settles only the pattern, not the names.

Four cross-Manager triggers are named across the design and the analysis docs, each currently
in a different state:

1. **`DeadlineUnreachableNotified`** (UC05) — the *only* cross-Manager edge that already rests
   on a defined, published domain event. The Charging Coordinator (via the Deadline Engine's
   determination) publishes it; the Notification Manager subscribes to deliver R5's
   deadline-unreachable notice.
2. **`charger_status` connect/disconnect** — today an adapter-observed Home Assistant state
   change. The Vehicle-Limit Manager needs the disconnect transition (UC09: reset the
   vehicle's charge limit, R6); the Notification Manager needs connect/disconnect (UC10:
   re-arm the plug-in reminder).
3. **`vehicle_charge_limit` change** — today an adapter-observed Home Assistant state change.
   The Vehicle-Limit Manager needs a vehicle-side change to adopt as the new default SOC
   limit (UC09, `ManualChargeLimitAdopted`).
4. **"resolved active SOC limit changed"** — not defined as an event anywhere. The
   Vehicle-Limit Manager needs it to write the new [active SOC limit](../analysis/system-overview.md#ubiquitous-language)
   to the vehicle when it changes while connected at home (UC09, `VehicleChargeLimitSynced`).
   The resolved value is computed inside the Coordinator's cycle by composing the (pure)
   SOC-Target Engine with the active profile and the step-up/reserve context the Coordinator
   threads (UC06/UC07).

For each trigger the structural choice is the same: **publish a new domain event** — which
then needs a home in a producing flow plus a glossary entry, and (to satisfy the "maps to an
HA automation trigger" rule) an entity the trigger can fire on — versus **re-derive the
condition per control cycle** in the consuming Manager, minting no event.

Three forces constrain the choice:

- **The DDD convention scopes what a domain event *is*.** CLAUDE.md defines a domain event as
  a past-tense, PascalCase *domain state transition* mapped to an HA automation trigger — not
  as a synonym for "some entity changed value." Minting an event for a raw reading the charger
  or vehicle already exposes would stretch the convention to cover pass-through state.
- **NF3 already routes external state through adapters.** `charger_status` and
  `vehicle_charge_limit` are values owned *outside* the integration (the charger, the
  vehicle), reached only through their adapter roles (`entity-catalog.md`). Every Manager that
  cares about them already reads them through Resource Access; Home Assistant's own
  state-change bus already provides the "trigger."
- **NF1's single-ownership *principle*.** NF1 itself is narrower — it forbids the Coordinator
  from holding mode-selection logic, so a *mode* decision lives in exactly one place. Its
  underlying principle (one decision, one owner) applies by analogy here: the active-SOC-limit
  resolution is owned by the SOC-Target Engine as composed by the Coordinator. The SOC-Target
  Engine is pure and already a shared edge any Manager may call (system-design §3/§4); what a
  second Manager cannot obtain without duplication is not the engine call but the Coordinator's
  *input composition* — the active profile plus the step-up/reserve context threaded across cycles
  (UC06/UC07) — and the per-cycle change-detection over it.

## Considered options

### Option A — Publish a domain event for every cross-Manager trigger

Mint events uniformly: keep `DeadlineUnreachableNotified`, and add `ChargerConnected` /
`ChargerDisconnected`, `VehicleChargeLimitChanged`, and `ActiveSocLimitChanged`. Every
cross-service trigger becomes a named, greppable domain event with a producing flow and a
glossary entry.

- Pro: One uniform mechanism — a contributor never has to decide *how* a Manager learns of a
  trigger; it is always "subscribe to an event." Every cross-service edge is discoverable by
  grepping for a PascalCase name, and each maps to an HA automation trigger.
- Con: It mints events for `charger_status` and `vehicle_charge_limit`, which are **external
  states already reached through an adapter** (NF3) and already broadcast by HA's state-change
  bus. The resulting `ChargerDisconnected` / `VehicleChargeLimitChanged` events own no
  integration-computed transition — they re-wrap a raw reading, stretching the DDD convention
  (a domain event should be a domain *transition*, not any value change) and adding
  pass-through names to the glossary and a producing flow that merely relays what the adapter
  read.

### Option B — Re-derive every cross-Manager trigger, mint no new events

Each Manager observes or recomputes every condition itself each cycle. The Notification
Manager re-runs the Deadline Engine to decide "unreachable"; the Vehicle-Limit Manager
recomputes the resolved active SOC limit from inputs and compares it to what it last wrote;
both observe `charger_status` / `vehicle_charge_limit` through their own adapters.

- Pro: No new events at all; each Manager is self-sufficient and the glossary/producing flows
  are untouched. For the two external-state triggers this is exactly the natural shape.
- Con: For the resolved active SOC limit, re-deriving does *not* mean merely re-calling the
  pure SOC-Target Engine (that edge is shared and already allowed — system-design §5.2 shows
  the Vehicle-Limit Manager doing exactly that). It means **reconstructing the Coordinator's
  input composition** — the active profile plus the step-up/reserve
  context the Coordinator threads across cycles (UC06/UC07) — and running the per-cycle
  change-detection over it, inside a second Manager. That spreads the ownership of one
  computed decision across two services, the single-ownership smear NF1's principle argues
  against. It also discards the one already-defined, load-bearing event
  (`DeadlineUnreachableNotified`), forcing the Notification Manager to re-run the Deadline
  Engine's urgency computation to re-derive a transition the Coordinator already determined.

### Option C — Criterion-based split: event for an integration-computed transition, re-derive for an external adapter state

Apply one rule per trigger: **publish a domain event iff the trigger is an
integration-computed domain transition the consumer cannot observe without duplicating the
producer's computation; re-derive (observe the adapter) iff the trigger is an external HA
state the consumer already reads through Resource Access.**

- Pro: Matches the DDD convention (events name domain *transitions*, not raw value changes)
  and NF3 (external states cross an adapter, not an event); keeps each *computed* domain
  decision single-owned per NF1; adds no pass-through events. It retains the one load-bearing
  event and introduces exactly one new one, where it earns its keep.
- Con: Not a single uniform mechanism — a contributor must apply the criterion per trigger and
  know which side of the line a new trigger falls on. It introduces exactly one new event
  (`ActiveSocLimitChanged`) whose "maps to an HA trigger" requirement drags in follow-up
  analysis work: a glossary entry, a home in a producing flow, and materializing the resolved
  active SOC limit as an owned diagnostic entity for the trigger to fire on.

## Decision

**Option C.** Coordinate via a domain event **only** where the trigger is a domain transition
the integration itself computes and the consumer could not observe without duplicating the
producer's logic; everywhere the trigger is an external Home Assistant state already reached
through an adapter, the consuming Manager **re-derives** it by observing that adapter — no
event is minted.

Applied to the four triggers:

| Trigger | Producer → Consumer | Resolution | Why |
| --- | --- | --- | --- |
| **`DeadlineUnreachableNotified`** (UC05) | Coordinator → Notification Manager | **Keep the published event** | Genuine integration-computed transition (the Deadline Engine's urgency determination) with notify-once semantics; the consumer cannot re-derive it without re-running that determination. Confirmed unchanged. |
| **`charger_status` connect/disconnect** | *charger (external)* → Vehicle-Limit + Notification | **Re-derive** (observe the adapter) | Not a Manager→Manager edge at all — the producer is the charger, an external state reached through the `charger_status` adapter (NF3) and already broadcast by HA. The adapter's raw→canonical translation is mechanics, not an integration-computed domain transition (system-design §4). Each Manager observes the transition through its own read; a `ChargerDisconnected` event would only re-wrap that reading. |
| **`vehicle_charge_limit` change** | *vehicle (external)* → Vehicle-Limit | **Re-derive** (observe the adapter) | Likewise external, reached through the `vehicle_charge_limit` adapter, and consumed by a **single** Manager observing its own resource (with the existing echo-guard); not cross-Manager, so no event is warranted. |
| **"resolved active SOC limit changed"** | Coordinator → Vehicle-Limit Manager | **Publish a new event `ActiveSocLimitChanged`** | The decisive case: the resolved value is an integration-computed composition (the pure SOC-Target Engine fed the active profile and the Coordinator-threaded step-up/reserve context, UC06/UC07). The Vehicle-Limit Manager can call SOC-Target (a shared edge) but cannot reconstruct that Coordinator-owned input composition and change-detection without duplicating it (Option B's cost); a single unifying event gives one clean trigger, independent of which rule caused the change. |

Option C is chosen over Option A because A's uniformity is bought by minting
`ChargerDisconnected` / `VehicleChargeLimitChanged` events that own no integration-computed
transition — pass-through re-wraps of adapter reads that the DDD convention (event = domain
*transition*) and NF3 (external state crosses an adapter) both argue against. It is chosen
over Option B because B's "no new events" is bought by reconstructing the Coordinator's
active-SOC-limit input composition (active profile + threaded step-up/reserve context) and its
change-detection inside the Vehicle-Limit Manager — the cross-service smear of one decision's
ownership that NF1's single-ownership principle argues against — and by throwing away the
already-defined `DeadlineUnreachableNotified`, forcing the Notification Manager to re-run the
Deadline Engine. The criterion keeps the existing load-bearing event, adds exactly one where
it removes real duplication, and leaves the two external-state triggers as the adapter reads
they already are.

This **refines** system-design §5.2, which shows the Vehicle-Limit Manager calling the
SOC-Target Engine for the resolved active SOC limit. Post-ADR, the Vehicle-Limit Manager
obtains that value by **reading the materialized owned diagnostic entity** the
`ActiveSocLimitChanged` event fires on — the Coordinator's single published resolution — rather
than reconstructing the Coordinator's threaded input composition to recompute it. The shared
`VLM → SOC-Target` edge remains available; it is simply not the source of the *cross-cycle
change* signal.

`ActiveSocLimitChanged` follows the DDD convention (past-tense PascalCase). It is distinct
from the existing `ActiveSocLimitReached` (SOC *reached* the limit) — it fires when the
resolved limit *value* changes, subsuming the cause-specific `SolarStepUpApplied` /
`SolarStepUpCleared` / `SolarReserveCapEngaged` / `SolarReserveCapLifted` and a default-limit
edit into one consumer contract, so the Vehicle-Limit Manager subscribes once rather than to
every cause. To satisfy the "maps to an HA automation trigger" rule, the resolved active SOC
limit is materialized as an owned diagnostic entity the event fires on — the same treatment
the effective peak limit already received (`sensor.smart_charging_effective_peak_limit`); the
resolved active SOC limit today has no such entity (see `entity-catalog.md`'s Notes).

## Consequences

- The cross-Manager coordination vocabulary is now fixed: **two** genuine Manager→Manager
  edges, both event-based (`DeadlineUnreachableNotified` unchanged; `ActiveSocLimitChanged`
  new), and the two remaining "candidate" triggers reclassified as **external adapter-state
  observations**, not cross-Manager events. This unblocks building the Notification and
  Vehicle-Limit Managers against a settled contract.
- A future cross-Manager trigger is decided by the criterion, not case-by-case: is it an
  integration-computed domain transition (→ event) or an external state reached through an
  adapter (→ re-derive)? This is the durable rule ADR-0011 adds on top of the design's pattern.
- **Follow-up analysis work (not done in this branch, per the issue-first + write-requirement
  flow).** Introducing `ActiveSocLimitChanged` requires:
  - a glossary entry for the event and (if not already precise enough) the resolved active SOC
    limit as the value it fires on, in `system-overview.md`;
  - listing it under "Domain events produced" in the flow that owns the resolution — the
    Coordinator's cycle (`control-cycle.md`) and/or the active-SOC-limit rule
    (`resolution-rules.md`), with UC09 recording it as the trigger it consumes;
  - a materialized owned diagnostic entity for the resolved active SOC limit (e.g.
    `sensor.smart_charging_active_soc_limit`) in `entity-catalog.md`, mirroring how the
    effective peak limit was surfaced, so the event maps to an HA state-change trigger.
  Each of these is an analysis-doc change gated by its own issue and review; this ADR opens
  none of them, it only records that they follow.
- No existing ADR is superseded. This ADR settles the second of the two system-design §8
  follow-ups (the first, engine placement, was ADR-0010); with it, both design-surfaced
  candidate ADRs are resolved.
- What becomes harder: a contributor adding a cross-Manager trigger must classify it against
  the criterion rather than reaching for a uniform "always publish an event" or "always
  re-derive" habit. The per-trigger table above is the worked precedent for that judgment.
