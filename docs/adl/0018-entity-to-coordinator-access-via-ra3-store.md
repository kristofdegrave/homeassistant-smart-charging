# ADR-0018: Entity-to-coordinator access via RA3's Store (pull-based read, Manager-initiated write)

Date: 2026-08-03
Status: Accepted

## Context

ADR-0016 decided that the eight owned control entities writable from outside the coordinator
(`active_mode`, `active_profile`, `target_current`, `soc_limit_override`, `home_day_flag`,
`departure_dow_defaults`, `departure_holiday_override`, `departure_home_day_override`) should
reach the coordinator by firing an entry-scoped HA event, with the coordinator subscribing via a
synchronous `@callback` listener. That decision, and ADR-0014 before it (a held coordinator
reference plus a setter method), both frame this as a **push** problem: how does an entity's
write reach the coordinator's field? Neither ADR's Considered Options ever examined the
alternative framing — that the coordinator does not need to be pushed to at all, if it can
simply **read** each owned entity's current value itself, the same way it already reads external
hardware state (`charger_status`, `grid_voltage`, `ev_soc`, …) through ADR-0003's adapters every
cycle.

That pull framing is not new to this decision. `docs/design/project-plan.md`'s Resource-Access
phase names a third Resource-Access class, **RA3 — Config/State Store access**, symmetric to
ADR-0003's hardware adapters but scoped to config-entry data/options and to owned-entity state via
HA's entity/restore-state registry: "reads **and writes** of owned-entity state … No custom
persistence layer" (project-plan.md, RA3). The Coordinator (M1) is specified to consume it by
reading, not by being written to: "Reads owned control-entity values through the Store —
stubbable until C2" (M1, Depends on) and "M1 reads owned values through the Store (replacing C2
stubs used in M1's tests)" (C2, Integration checkpoint).

`docs/design/system-design.md` — revised specifically to settle this question — now corroborates
the same shape at the architecture level, unambiguously. Its static diagram routes the owned
control entities through the Store (`Owned --> Store`), not to the Coordinator directly; its
call-direction rule 1 reserves `Client → Manager` for genuine trigger sources (the control-interval
timer, the Notification Manager's own reminder/evening-time checks, external events) and treats the
owned control entities as touching only the Store, exactly like the dashboard and config flow; and
its §5.1 control-cycle sequence diagram now shows the Coordinator reading every owned control
entity's current value through the Store each cycle, before it reads hardware through the Adapters.
That revision records, as an explicit unresolved item, that ADR-0016 decides the opposite mechanism
and needs its own superseding ADR — this is that ADR.

No `Store` class exists anywhere in `custom_components/` today, and neither ADR-0014 nor ADR-0016
cite RA3, `project-plan.md`, or `system-design.md` anywhere in their Context or Considered
Options — both proceeded as though the only question were *which push mechanism*, never *whether
push is the right direction at all*. That said, this is not a choice made before any code exists.
Four of the eight fields already have merged code on ADR-0014's shape: `select.py`'s
`ModeSelect`/`ProfileSelect` and `number.py`'s `TargetCurrentNumber`/`SocLimitOverrideNumber` each
hold `self._coordinator` and call `set_active_mode`/`set_active_profile`/`set_target_current`/
`set_soc_limit_override` (defined on `SmartChargingCoordinator`) followed by
`await self._coordinator.async_request_refresh()`. Only the remaining four fields (`home_day_flag`
and the three departure fields) are unwired — the in-flight work ADR-0016's own Context describes,
never landed on either ADR-0014's or ADR-0016's shape. So this decision is not free: it is a
genuine migration for the four already-merged fields, not only a one-time mechanism choice for the
four still-unwired ones.

This ADR therefore corrects the axis ADR-0014 and ADR-0016 solved on, using the mechanism the
design layer now specifies unambiguously in both `project-plan.md` and `system-design.md`.

## Considered options

### Option A — Status quo: ADR-0016's per-field HA event, entity → coordinator (push)

Each owned control entity fires an entry-scoped `EVENT_*_CHANGE_REQUESTED` event on `hass.bus`; the
coordinator subscribes with a synchronous `@callback` listener per field, applies the value, and
requests a refresh.

- Pro: Already has a written decision and a partial implementation spec (ADR-0016) that was never
  merged for reasons unrelated to its own technical soundness; no further design work needed to
  pick a mechanism, only to finish building it.
- Pro: Narrows entity→coordinator coupling to "one event name plus a payload" (ADR-0016's own
  stated advantage over ADR-0014), which genuinely is a smaller contract than a held reference.
- Con: Contradicts `system-design.md`'s revised static architecture, which routes owned control
  entities through the Store and reserves `Client → Manager` for genuine trigger sources. Building
  the event mechanism now would mean this integration's code diverges from its own approved
  system design on a structural call-direction question, not just an implementation detail.
- Con: Still push-shaped, so it inherits the two mechanics ADR-0016 itself had to invent and
  enforce by discipline rather than get for free — entry-id scoping on every payload, and
  synchronous-`@callback`-only listeners — neither of which a pull read needs, since the
  coordinator reads its own entry's Store on its own cycle.

### Option B — RA3's Store: Coordinator reads owned-entity state each cycle; a Manager writes through the same Store on its own behalf

A `Store` class (RA3) wraps HA's entity/restore-state registry for owned-entity values plus
config-entry data/options; its package home is not decided here (ADR-0002's layout has no Store
slot, the same open question this project already gave its own ADR for the non-mode/profile
Engines and for the Managers — a follow-up, not part of this decision). The
Coordinator's read step (already an existing pipeline stage — ADR-0006's read phase, currently only
reading ADR-0003's hardware adapters) additionally reads all eight owned-entity values through the
Store each cycle, the same way it reads `charger_status`/`grid_voltage`/etc. through the hardware
adapters — exactly as `system-design.md`'s revised §5.1 sequence now shows. No entity pushes
anything to the coordinator; the entity's own HA platform code (`async_select_option`,
`async_set_native_value`, …) continues to update its own displayed/restored state exactly as
today, and the coordinator simply observes that state on its next cycle. Separately, a Manager
that needs to set an owned entity's value on the user's behalf (M2 syncing `soc_limit_override`
from the vehicle; M3 setting `home_day_flag` from UC08's prompt) writes through the same Store's
write side, rather than calling a coordinator setter or firing an event of its own.

- Pro: Matches the design layer now on record in both `project-plan.md` (RA3, M1, C2) and the
  revised `system-design.md` (`Owned --> Store`, rule 1, §5.1) — this ADR formalizes a decision the
  design layer already makes, rather than making a new one.
- Pro: Symmetric with ADR-0003's existing, working pattern — the coordinator already reads
  hardware state through adapters every cycle and tolerates a `None`/stale value the same way
  (ADR-0007); owned-entity reads become one more adapter-shaped source rather than a second,
  differently-shaped access path.
- Pro: Removes both of ADR-0016's invented mechanics as concerns for this path. There is no
  cross-entry leakage risk to guard: like the hardware adapters (ADR-0003), one Store instance is
  built per config entry, so the coordinator only ever reads its own entry's data — no `entry_id`
  payload discipline needed. There is no apply-before-refresh ordering to protect with a
  synchronous-callback requirement, because the read happens synchronously inside the
  coordinator's own cycle, which it already controls.
- Con: The coordinator's read of a just-changed owned entity is only as fresh as its next scheduled
  cycle (C1's control interval, ADR-0005), not immediate the way a push mechanism can be if it also
  triggers `async_request_refresh()` on the spot. A user action (e.g. toggling `home_day_flag`)
  does not take effect until the coordinator's next tick, whereas ADR-0014's setter — the shape
  four of the eight fields use today — triggers an immediate refresh.
- Con: A `Store` class does not exist yet in either shape (unlike Option A, which at least has a
  partially-written implementation spec) — this is new code in both directions, read and write,
  with its own implementation spec and TDD plan still to author.
- Con: This is a real migration, not only new code for the unwired fields. The four already-merged
  fields (`active_mode`, `active_profile`, `target_current`, `soc_limit_override`) lose their
  held `self._coordinator` reference, their four coordinator setters, and the immediate
  `async_request_refresh()` their `async_set_native_value`/`async_select_option` handlers call
  today — all of it replaced by a Store read the Coordinator performs on its own cycle. Their
  existing entity tests, which assert against a coordinator double, need rewriting too.

### Option C — Coordinator subscribes to HA state-change events on the owned entities, still reading current values through the Store

The Store remains the Coordinator's source of truth (as in Option B), but the Coordinator also
registers `hass.helpers.event.async_track_state_change_event` on the owned entities' `entity_id`s
at setup, and calls `async_request_refresh()` when one fires — recovering Option A's immediate
response without an entity ever holding a coordinator reference or firing a custom event.

- Pro: Dissolves Option B's only real Con. A user's change takes effect immediately, the same as
  today's ADR-0014 behavior, while every entity write still only ever touches its own HA-native
  state — no entity-side code references the Coordinator at all, so `system-design.md`'s
  `Owned --> Store` edge and rule 1 hold exactly as written.
- Con: A second access mechanism to reason about, which is what Option B's Consequences (below)
  specifically buys against. The Coordinator would own both a per-cycle Store read *and* a
  standing state-change subscription with its own setup/teardown lifecycle (registered at entry
  setup, unregistered at unload — the same discipline ADR-0016 needed for its event listeners),
  for a benefit (up to one control interval's latency) no use-case in this design currently needs.

## Decision

Option B. `system-design.md`'s revision settles the axis ADR-0014 and ADR-0016 got wrong: both
treated "how does an entity's write reach the coordinator" as a push-mechanism question, when the
design layer specifies a pull-based Store for exactly this access. Option A's real advantages —
an existing written decision and narrower coupling than ADR-0014 — are not load-bearing against a
design layer that now explicitly excludes push for this call direction: building the event
mechanism would put this integration's code in open contradiction with its own approved system
design, which is a structural cost neither Pro outweighs. Option A's migration cost is also no
longer smaller than Option B's: four fields already have merged code, so *some* migration happens
regardless of which push-vs-pull direction wins.

Option C is rejected because its Pro (immediate responsiveness) buys back exactly the Con Option B
accepts deliberately, at the cost of the second access mechanism Option B's Consequences are
written to avoid — a standing subscription with its own setup/teardown lifecycle, alongside the
per-cycle Store read, for a benefit no use-case in this design currently needs (see below). If a
future use-case needs sub-cycle responsiveness for a specific owned-entity change, Option C becomes
the candidate to revisit — that is a new decision to make against that use-case, not a reason to
build it pre-emptively now.

Option B's freshness Con (up to one control-interval's delay before a user's change is observed) is
accepted, for the same reason `system-design.md`'s own revision accepts it: R14/UC06's existing
deadline-override and step-up flows already tolerate coordinator-cycle-granularity latency for
every other input (hardware state, solar forecast, tariff), NF1 already requires the coordinator to
hold none of this state itself, and R11's mode-switch timer reset keys off the *active mode* the
Profile Engine returns each cycle — which the coordinator already diffs against the prior cycle —
not off a push notification.

**ADR-0006.** Adding the Store read as a new input to the Coordinator's existing read step is not
the step-order change ADR-0006 reserves for a superseding ADR — the ten-step cycle's first step
("read raw values") gains an additional source alongside the hardware adapters, but its position
in the sequence and every step after it are unchanged. ADR-0006 is not superseded.

**ADR-0011.** M2/M3 writing an owned entity through the Store is not cross-Manager coordination —
it is a Manager reaching Resource Access directly for its own output, the same as the Coordinator
writing diagnostic entities through the Store today. ADR-0011's publish/subscribe criterion, which
governs Manager→Manager signaling, is not engaged.

**Scope: all eight fields, uniformly**, for the same reason ADR-0016 gave for its own uniform
scope — running the Store's read path for four fields and some other mechanism for the other four
would leave every future owned control entity asking "which pattern does this one use?" with no
principled answer. This ADR therefore **supersedes ADR-0016 in full** (and, transitively,
ADR-0014, which ADR-0016 already superseded): the `EVENT_*_CHANGE_REQUESTED` constants and the
entry-id-scoping/synchronous-callback discipline ADR-0016 specified are retired before any of them
were built, and no coordinator setter methods (ADR-0014's shape) are added for the four fields
still unwired. ADR-0004's decision that owned-entity state persists via HA's own
restore-state mechanism, with no custom persistence layer, is unaffected — the Store wraps that
same registry access, it does not replace it with new storage.

**Scope: both the Store's read half and its write half are decided here.** The read half
(Coordinator, M1) is needed immediately — it is what the still-unwired departure/home-day fields
are waiting on. The write half (a
Manager writing to an owned entity on the user's behalf, e.g. M2/M3) has no caller yet, since
neither Manager is built. Deciding only the read half now and leaving the write half for a later
ADR would risk the same mistake this ADR is correcting: a later, narrower decision made without the
full RA3 shape in view, that then has to be reconciled against this one. Recording both halves now,
against the read/write shape RA3 and the revised `system-design.md` already specify, costs nothing
extra and removes that risk. This does not commit the *implementation* of the write half to land in
the same spec/PR as the read half — that sequencing question belongs to the implementation spec
(a separate, later step), which may build the read half first since it is the half with a caller
today.

## Consequences

- **This ADR decides the shape; it implements nothing.** An implementation spec / TDD plan is
  needed to build the `Store` class (RA3) and wire the Coordinator's existing read step to consume
  all eight owned-entity values through it — migrating the four already-merged fields off their
  held coordinator reference and setter methods, and wiring the four still-unwired fields directly
  against the Store rather than against either retired push shape.
- **ADR-0016 is superseded in full.** Its Status becomes `Superseded by ADR-0018` and its ADL row
  is updated; its own Context/options/Decision text is left untouched, per the immutability rule.
  ADR-0014 remains `Superseded by ADR-0016` — its row is not rewritten to point at this ADR, since
  ADR-0016 is what superseded it and that fact does not change.
- **Existing push-shape wiring is replaced, not adapted.** The four already-merged fields' held
  `self._coordinator` references, their four coordinator setters, and their entity tests (which
  assert against a coordinator double) are all superseded by the implementation spec above, not
  incrementally migrated. The four still-unwired fields are built directly against the Store.
- **A follow-up decision is needed only if a future use-case requires sub-cycle responsiveness**
  for a specific owned-entity change (the Decision's accepted Con) — this ADR does not preclude
  that, but does not attempt to solve it pre-emptively either.
- **Harder:** there is no synchronous "your value was clamped" feedback path from this decision
  either, same as both prior ADRs already noted — an owned entity's own displayed value (e.g.
  `TargetCurrentNumber`'s `native_min_value`/`native_max_value`) and the coordinator's own clamp on
  its Store-read value remain two independent enforcements of the same config-derived bound, not
  one call, exactly as ADR-0016 already recorded for its own shape.
- **Easier:** entity platform code (`select.py`, `number.py`, `time.py`, `switch.py`) needs no
  coordinator reference and no event-firing code at all for the write direction — it only manages
  its own HA-native state, which HA's restore-state mechanism already persists (ADR-0004). The
  coordinator's read step gains one more Store-shaped source alongside its existing hardware
  adapters (ADR-0003), rather than a second access mechanism to reason about.
