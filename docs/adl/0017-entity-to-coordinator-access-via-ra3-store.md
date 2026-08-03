# ADR-0017: Entity-to-coordinator access via RA3's Store (pull-based read, Manager-initiated write)

Date: 2026-08-03
Status: Proposed

## Context

ADR-0016 decided that the eight owned control entities writable from outside the
coordinator (`active_mode`, `active_profile`, `target_current`, `soc_limit_override`,
`home_day_flag`, `departure_dow_defaults`, `departure_holiday_override`,
`departure_home_day_override`) should reach the coordinator by firing an entry-scoped HA
event, with the coordinator subscribing via a synchronous `@callback` listener. That
decision, and ADR-0014 before it (a held coordinator reference plus a setter method), both
frame this as a **push** problem: how does an entity's write reach the coordinator's
field? Neither ADR's Considered Options ever examined the alternative framing — that the
coordinator does not need to be pushed to at all, if it can simply **read** each owned
entity's current value itself, the same way it already reads external hardware state
(`charger_status`, `grid_voltage`, `ev_soc`, …) through ADR-0003's adapters every cycle.

That pull framing is not new to this decision — it is already specified.
`docs/design/project-plan.md`'s Resource-Access phase names a fourth adapter-like class,
**RA3 — Config/State Store access**, symmetric to ADR-0003's hardware adapters but scoped
to config-entry data/options and to owned-entity state via HA's entity/restore-state
registry: "reads **and writes** of owned-entity state … No custom persistence layer"
(project-plan.md, RA3). The Coordinator (M1) is specified to consume it by reading, not by
being written to: "Reads owned control-entity values through the Store — stubbable until
C2" (M1, Depends on) and "M1 reads owned values through the Store (replacing C2 stubs used
in M1's tests)" (C2, Integration checkpoint). `docs/design/system-design.md` corroborates
the same shape at the architecture level: owned entities are "written through the Store,
not Clients" and the static architecture diagram shows `Coord -->|reads/writes config,
state, diagnostics| Store`. The Store's write side is not Coordinator-only either — two
Managers not yet built are already specified to write through it on their own: M2 (Vehicle-
Limit) writes `number.smart_charging_soc_limit_override` "through adapter/Store", and M3
(Notification) writes the home-day flag "via Store" as the outcome of UC08's evening
prompt.

No `Store` class exists anywhere in `custom_components/` today. Neither ADR-0014 nor
ADR-0016 cite RA3, project-plan.md, or system-design.md anywhere in their Context or
Considered Options — both proceeded as though the only question were *which push
mechanism*, never *whether push is the right direction at all*. ADR-0016's own
implementation spec (the migration of `select.py`/`number.py`/`time.py`/`switch.py`/
`coordinator.py` to fired events) was never merged, and the four fields PR #452 was adding
(`home_day_flag`, `departure_dow_defaults`, `departure_holiday_override`,
`departure_home_day_override`) were never wired past draft on either ADR-0014's or
ADR-0016's shape. So this decision is a one-time choice of mechanism before any of the
eight fields have working code in either push shape, not a migration away from a mechanism
already in production.

This ADR therefore corrects the axis ADR-0014 and ADR-0016 solved on, using the mechanism
the design docs already specify, rather than inventing a third push variant.

## Considered options

### Option A — Status quo: ADR-0016's per-field HA event, entity → coordinator (push)

Each owned control entity fires an entry-scoped `EVENT_*_CHANGE_REQUESTED` event on
`hass.bus`; the coordinator subscribes with a synchronous `@callback` listener per field,
applies the value, and requests a refresh.

- Pro: Already has a written decision and a partial implementation spec (ADR-0016, #474 —
  closed unmerged but not discarded for technical reasons); no further design work needed
  to pick a mechanism, only to finish building it.
- Pro: Narrows entity→coordinator coupling to "one event name plus a payload" (ADR-0016's
  own stated advantage over ADR-0014), which genuinely is a smaller contract than a held
  reference.
- Con: Solves a problem the design layer had already decided differently. RA3 and its
  Coordinator/Manager read-through-Store shape predate ADR-0016 in `project-plan.md`, so
  building the event mechanism produces a second, parallel access path (push via events)
  for state the design already routes through a single pull-based Store — the two would
  have to be reconciled later regardless, at higher cost than choosing correctly now.
- Con: Still push-shaped, so it inherits the two mechanics ADR-0016 itself had to invent
  and enforce by discipline rather than get for free — entry-id scoping on every payload,
  and synchronous-`@callback`-only listeners — neither of which a pull read needs, since
  the coordinator reads its own entry's Store on its own cycle.

### Option B — RA3's Store: Coordinator reads owned-entity state each cycle; a Manager writes through the same Store on its own behalf

A `Store` class (RA3), living alongside `adapters/` (ADR-0002/ADR-0003's package layout),
wraps HA's entity/restore-state registry for owned-entity values plus config-entry
data/options. The Coordinator's read step (already an existing pipeline stage — ADR-0006's
read phase, currently only reading ADR-0003's hardware adapters) additionally reads all
eight owned-entity values through the Store each cycle, the same way it reads
`charger_status`/`grid_voltage`/etc. through the hardware adapters. No entity pushes
anything to the coordinator; the entity's own HA platform code (`async_select_option`,
`async_set_native_value`, …) continues to update its own displayed/restored state exactly
as today, and the coordinator simply observes that state on its next cycle. Separately, a
Manager that needs to set an owned entity's value on the user's behalf (M2 syncing
`soc_limit_override` from the vehicle; M3 setting `home_day_flag` from UC08's prompt)
writes through the same Store's write side, rather than calling a coordinator setter or
firing an event of its own.

- Pro: Matches the design layer already on record (RA3, M1, C2 in project-plan.md;
  system-design.md's Store row) — no new design decision is being made, only a
  formalization of one already made and cross-checked against use-cases.
- Pro: Symmetric with ADR-0003's existing, working pattern — the coordinator already
  reads hardware state through adapters every cycle and tolerates a `None`/stale value the
  same way (ADR-0007); owned-entity reads become one more adapter-shaped source rather
  than a second, differently-shaped access path.
- Pro: Removes both of ADR-0016's invented mechanics as concerns for this path. There is
  no cross-entry leakage risk to guard, because the Store is instantiated per config entry
  and the coordinator only ever reads its own entry's Store — no `entry_id` payload
  discipline needed. There is no apply-before-refresh ordering to protect with a
  synchronous-callback requirement, because the read happens synchronously inside the
  coordinator's own cycle, which it already controls.
- Con: The coordinator's read of a just-changed owned entity is only as fresh as its next
  scheduled cycle (C1's control interval, ADR-0005), not immediate the way a push
  mechanism can be if it also triggers `async_request_refresh()` on the spot. A user
  action (e.g. toggling `home_day_flag`) does not take effect until the coordinator's next
  tick, whereas both ADR-0014's setter and ADR-0016's event trigger an immediate refresh
  today.
- Con: A `Store` class does not exist yet in either shape (unlike Option A, which at least
  has a partially-written implementation spec) — this is new code in both directions, read
  and write, with its own implementation spec and TDD plan still to author.

## Decision

Option B. ADR-0016 (and, transitively, ADR-0014) picked the wrong axis: both treated
"how does an entity's write reach the coordinator" as a push-mechanism question, when
`project-plan.md`'s RA3 and `system-design.md` had already specified a pull-based Store for
exactly this access, cross-checked against the Coordinator (M1) and the owned entities
(C2) that depend on it. Option A's only real advantage — a partially-written
implementation (ADR-0016/#474) — is not load-bearing: that PR was closed unmerged
precisely because it would have built a second, parallel access path alongside the Store
the design already specifies, which is more expensive to reconcile later than choosing the
already-specified mechanism now, before either of the eight fields has working code on
either push shape. Option A's narrower-coupling Pro over ADR-0014 is real but moot once the
coordinator does not need a *push contract* of any shape — reading its own entry's Store
each cycle is a narrower coupling still, since the entity code and the coordinator's read
step do not reference each other at all.

Option B's freshness Con (up to one control-interval's delay before a user's change is
observed) is accepted: R14/UC06's existing deadline-override and step-up flows already
tolerate coordinator-cycle-granularity latency for every other input (hardware state,
solar forecast, tariff), and the control interval (ADR-0005) is already short enough that
this project's use-cases have never required sub-cycle responsiveness for a user-set
value. If a future use-case needs sub-cycle responsiveness for a specific owned-entity
change, that is a new decision to make against that use-case, not a reason to reject the
Store now.

**Scope: all eight fields, uniformly**, for the same reason ADR-0016 gave for its own
uniform scope — running the Store's read path for four fields and some other mechanism for
the other four would leave every future owned control entity asking "which pattern does
this one use?" with no principled answer. This ADR therefore **supersedes ADR-0016 in
full** (and, transitively, ADR-0014, which ADR-0016 already superseded): the
`EVENT_*_CHANGE_REQUESTED` constants and the entry-id-scoping/synchronous-callback
discipline ADR-0016 specified are retired before any of them were built, and no
coordinator setter methods (ADR-0014's shape) are added for the four fields still
outstanding from PR #452. ADR-0004's decision that owned-entity state persists via HA's
own restore-state mechanism, with no custom persistence layer, is unaffected — the Store
wraps that same registry access, it does not replace it with new storage.

**Scope: both the Store's read half and its write half are decided here.** The read half
(Coordinator, M1) is needed immediately — it is what unblocks issue #402. The write half
(a Manager writing to an owned entity on the user's behalf, e.g. M2/M3) has no caller yet,
since neither Manager is built. Deciding only the read half now and leaving the write half
for a later ADR would risk the same mistake this ADR is correcting: a later, narrower
decision made without the full RA3 shape in view, that then has to be reconciled against
this one. Recording both halves now, against the read/write shape RA3 already specifies,
costs nothing extra (project-plan.md already specifies the shape; this ADR is not inventing
it) and removes that risk. This does not commit the *implementation* of the write half to
land in the same spec/PR as the read half — that sequencing question belongs to the
implementation spec (Task B), which may build the read half first since it is the half with
a caller today.

## Consequences

- **This ADR decides the shape; it implements nothing.** An implementation spec / TDD plan
  is needed to build the `Store` class (RA3) and wire the Coordinator's existing read step
  to consume all eight owned-entity values through it, replacing the coordinator-held
  fields and setter methods PR #452 was building on ADR-0014's/ADR-0016's now-retired
  shape.
- **ADR-0016 is superseded in full.** Its Status becomes `Superseded by ADR-0017` and its
  ADL row is updated; its own Context/options/Decision text is left untouched, per the
  immutability rule. ADR-0014 remains `Superseded by ADR-0016` — its row is not rewritten
  to point at this ADR, since ADR-0016 is what superseded it and that fact does not change.
- **PR #452's diff is not reusable.** It wires the four new fields on ADR-0014's/ADR-0016's
  push shape (a held coordinator reference and setter-style methods). Once the
  implementation spec above is approved and built, PR #452 should be closed for good
  rather than rebased — a fresh PR realizes issue #402 against the Store instead.
- **A follow-up decision is needed only if a future use-case requires sub-cycle
  responsiveness** for a specific owned-entity change (the Decision's accepted Con) — this
  ADR does not preclude that, but does not attempt to solve it pre-emptively either.
- **Harder:** there is no synchronous "your value was clamped" feedback path from this
  decision either, same as both prior ADRs already noted — an owned entity's own displayed
  value (e.g. `TargetCurrentNumber`'s `native_min_value`/`native_max_value`) and the
  coordinator's own clamp on its Store-read value remain two independent enforcements of
  the same config-derived bound, not one call, exactly as ADR-0016 already recorded for its
  own shape.
- **Easier:** entity platform code (`select.py`, `number.py`, `time.py`, `switch.py`)
  needs no coordinator reference and no event-firing code at all for the write direction —
  it only manages its own HA-native state, which HA's restore-state mechanism already
  persists (ADR-0004). The coordinator's read step gains one more Store-shaped source
  alongside its existing hardware adapters (ADR-0003), rather than a second access
  mechanism to reason about.
