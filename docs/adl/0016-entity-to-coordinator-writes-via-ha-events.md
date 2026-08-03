# ADR-0016: Entity-to-coordinator writes via Home Assistant events

Date: 2026-08-02
Status: Superseded by ADR-0017

## Context

Two owned control entities that let the user set a value the coordinator consumes —
`ModeSelect`/`ProfileSelect` (`select.py:63,67,91,95`) and `TargetCurrentNumber`/
`SocLimitOverrideNumber` (`number.py:54,58,92,96`) — hold `self._coordinator = coordinator`
for the entity's whole lifetime, passed in at construction by their platform's
`async_setup_entry` (which reads it out of `hass.data[DOMAIN][entry.entry_id]`), and call a
coordinator method directly on every change, followed by
`await self._coordinator.async_request_refresh()`: `set_active_mode`, `set_active_profile`,
`set_target_current`, `set_soc_limit_override`.

`SmartChargingDepartureTime` (`time.py`) and `HomeDaySwitch` (`switch.py`) already exist as
owned control entities for `home_day_flag`, `departure_dow_defaults`,
`departure_holiday_override` and `departure_home_day_override`, but their coordinator wiring
is in-flight work-in-progress, not yet landed here: it is being built against the same
held-reference-plus-setter shape (`activate_home_day`/`deactivate_home_day`,
`configure_weekday_departure`, `override_holiday_departure`, `override_home_day_departure`),
which is exactly what prompts this decision now, before that wiring lands, rather than after.

That is eight externally-writable coordinator fields meant to be reached the same way. ADR-0014 settled
the *method* half of that shape (mutate through a method the coordinator owns, not a bare
attribute assignment) for the first four fields, and generalized it forward: "any future
field added to the coordinator's externally-writable surface follows this same rule … rather
than needing its own ADR." It deliberately did **not** examine the *reference* half. Its
Option B was rejected in part because swapping the coordinator's identity per write "would
break every entity's stored reference and re-open how ADR-0006 wires the coordinator into
HA" — a scope ADR-0014 declined to take on. (That characterization is ADR-0014's own;
ADR-0006 itself decides only the ten-step internal cycle and says nothing about how an
entity writes into the coordinator. Nothing in ADR-0006 constrains this decision.)

Four forces now bear on the reference half:

- **Coupling width.** What each of these entities conceptually needs is "one field of mine
  has a new value." What it holds is a live handle on the coordinator's entire public
  surface — every setter, `async_request_refresh`, and every public attribute — for the
  entity's whole lifetime. That is a much wider contract than the write requires, and it is
  the surface every entity test has to construct or mock.
- **The read direction does not need the reference.** `SmartChargingEntity` (`entity.py`) is
  a plain `Entity`, not a `CoordinatorEntity`. For these eight write paths the coordinator
  reference exists *only* to push a value inward and to request a refresh; it is not used
  for coordinator→entity state sync. The read direction is a separate, already-different
  mechanism — `sensor.py`'s five diagnostic sensors (`ChargingStatusSensor`,
  `ActiveModeSensor`, `MonthlyPeakSensor`, `EffectivePeakLimitSensor`,
  `ActiveSocLimitSensor`) all subclass `CoordinatorEntity` and legitimately need the
  reference for it. Only the write path is in question here.
- **The codebase already has a working event bus, but ADR-0011's criterion doesn't reach
  this case.** ADR-0011 decided *when* to mint a domain event versus re-derive a condition:
  publish one **iff** the trigger is an integration-*computed* domain transition the consumer
  cannot observe without duplicating the producer's logic (its Option C). Every event that
  criterion produced — `EVENT_ACTIVE_SOC_LIMIT_CHANGED`, `EVENT_DEADLINE_UNREACHABLE_NOTIFIED`
  — is Coordinator→Manager: a past-tense notification that a computed transition already
  happened, fired outward to a peer service that must not call the producer directly. What is
  proposed here is a different shape entirely: an entity firing a **request to change
  state**, inward, to its own coordinator, before anything has been computed or transitioned.
  That is not a transition ADR-0011's criterion would ever classify — it is a UI input, not a
  domain event by CLAUDE.md's own definition. So ADR-0011 is precedent that `hass.bus` works
  as a mechanism in this codebase; it is not precedent that this particular use already
  satisfies its criterion, and this decision does not claim it does.
- **Two mechanics the direct reference gets for free.** (a) *Entry scoping* — the HA event
  bus is global to the instance, while `hass.data[DOMAIN][entry.entry_id]` gives each entity
  a handle on its **own** config entry's coordinator. With two config entries, an event-based
  write must carry enough identity for each coordinator to ignore the other's entities; the
  existing `EVENT_*` payloads carry no `entry_id` today, so this is new ground.
  (b) *Ordering* — an entity today calls the setter and then awaits
  `async_request_refresh()`, so the coordinator's field is guaranteed to be updated before
  the refresh it triggers. Under an event, that guarantee holds only if the coordinator's
  listener runs synchronously inside `async_fire`, which HA does for a `@callback`-decorated
  listener but not for a coroutine listener (scheduled as a separate task).

There is also a data-consistency property worth naming, because it is the one ADR-0014 was
originally about. `set_target_current` and `set_soc_limit_override` clamp to a config-driven
range (`[CONF_MIN_CURRENT, CONF_MAX_CURRENT]` and
`[SOC_LIMIT_OVERRIDE_MIN, SOC_LIMIT_OVERRIDE_MAX]`). A fire-and-forget event has no return
value, so an entity cannot learn from the event that its value was clamped. Today's entities
already write `self._attr_native_value = value` **before** calling the setter and never read
back the clamped result, so the entity's displayed value can already diverge from the
coordinator's field — the question is whether an event model makes that worse, or merely
makes an existing property explicit.

## Considered options

### Option A — Status quo: every write-capable entity holds a coordinator reference and calls a setter (ADR-0014's shape, extended to all eight fields)

- Pro: It is Home Assistant's own overwhelmingly common idiom — an entity holds the
  coordinator, writes, and requests a refresh — so a contributor arriving from any other
  integration reads it without explanation. Zero indirection: the write is one call, its
  effect is synchronous, ordering against `async_request_refresh()` is guaranteed by the
  language, and nothing has to be re-derived about how `DataUpdateCoordinator` is wired into
  HA (exactly the cost ADR-0014's Option B declined to pay).
- Pro: The clamp has a synchronous return path available if it is ever wanted — the setter
  could return the applied value, letting the entity display what the coordinator actually
  holds. Nothing in the current code uses that, but the shape permits it; an event does not.
- Con: The coupling is far wider than the write needs. Each entity holds the coordinator's
  whole public surface for its lifetime, so "this entity can set one field" is not something
  the type system or a reader can see — only a grep of the call sites tells you. Any test
  for any of these entities has to stand up or fake a coordinator object.
- Con: It fixes the direction of knowledge the wrong way round for a UI input: the entity
  must know which coordinator method corresponds to its field, so adding a field means the
  entity and the coordinator change together, in lockstep, in two files.
- Con: It offers no path for a second consumer. Anything else that wants to react to "the
  user changed the target current" (a Manager, an automation, a future diagnostic) has to be
  reached by adding another call inside the coordinator's setter, because the write leaves no
  trace on any bus.

### Option B — Entity fires an entry-scoped Home Assistant event per changed field; the coordinator subscribes with a synchronous `@callback` listener

Each owned control entity's write handler fires an event on `hass.bus` carrying the config
entry's id and the new value, and stops holding a coordinator reference. The coordinator
registers `@callback` listeners via `hass.bus.async_listen` at setup, filters on its own
`entry_id`, and applies the value through the same field-owning code ADR-0014's setters
already contain (including the two range clamps). The refresh the entity previously awaited
is requested by the coordinator's own listener, not by the entity.

Two sub-shapes exist for the vocabulary, and the choice matters:

- *One event type per field* (eight `EVENT_*` constants, e.g.
  `EVENT_TARGET_CURRENT_CHANGE_REQUESTED`): each event names one domain concept, listeners
  are narrow, and a bad payload is a typing question rather than a dispatch question.
- *One generic "owned control entity changed" event* carrying a field identifier plus the
  value: one constant, one listener, but the field identifier becomes a stringly-typed
  dispatch key inside the coordinator and the payload's type varies by field
  (`str` / `float` / `bool` / `time`), which the project's no-magic-strings rule pushes back
  on and which no existing `EVENT_*` payload does.

- Pro: The coupling narrows to exactly what the write needs. An entity's outbound contract
  becomes "one event name plus a payload," which is a value, not an object graph — testable
  by asserting a fired event, with no coordinator to construct.
- Pro: It puts entity→coordinator writes on the same bus the project already uses for
  cross-service coordination (ADR-0011), with the same `EVENT_*`-in-`const.py` naming
  convention, so there is one coordination mechanism in the codebase rather than two.
- Pro: The write becomes observable. Any second consumer — another Manager, a diagnostic, a
  user automation — can subscribe without the coordinator's setter growing a call to it.
- Con: It is not HA's common idiom for this direction, so it needs the reasoning recorded
  (this ADR) and the two mechanics above enforced deliberately rather than for free:
  **entry-id scoping** (a global bus with two config entries silently cross-talks unless
  every payload carries `entry_id` and every listener filters on it — a bug class the direct
  reference cannot have) and **synchronous dispatch** (the listener must be a plain
  `@callback`, never a coroutine, or the "apply then refresh" ordering the current code
  relies on is lost to task scheduling).
- Con: It is fire-and-forget, so there is no return path for "your value was clamped." This
  does not regress today's behavior — the entity already writes its own displayed value
  before the setter runs and never reads the clamp back — but it forecloses the cheap
  synchronous fix Option A leaves open. Under an event the two clamps become genuinely
  independent: the entity clamps for its own display via its `native_min_value`/
  `native_max_value`, the coordinator clamps for its own field in the listener, and keeping
  the two bounds agreeing becomes a property maintained by construction (both read the same
  config) rather than by a shared call.
- Con: A real, if bounded, migration: five source files (`select.py`, `number.py`,
  `time.py`, `switch.py`, `coordinator.py`) plus new constants, plus listener teardown on
  entry unload, plus the existing entity tests, which today assert against a coordinator
  double.

## Decision

**Option B**, for all eight externally-writable coordinator fields, in the per-field event
sub-shape.

Option A's decisive weakness is its first Con: the reference an entity holds is wide enough
to reach the whole coordinator, for a job that is one field's new value. Its Pros are real —
familiarity and the still-open synchronous clamp return path — but neither is load-bearing
today: nothing currently reads a setter's result back into the entity's display, and the
familiarity argument is weakest exactly where ADR-0011 has already taught this codebase to
coordinate over `hass.bus`.

Scope is **all eight fields, not only the two new platforms**. The alternative — leaving
`select.py`/`number.py` on ADR-0014's held reference and putting only `time.py`/`switch.py`
on events — would run two different wiring patterns for the same kind of write, so every
future control entity would start with a question that has no principled answer ("which
pattern does this one use?"). One consistent mental model for "an owned control entity tells
the coordinator its value changed" is worth the larger diff. This ADR therefore
**supersedes ADR-0014 in full**, including its generalization that any future
externally-writable field simply gets a setter method without its own ADR: the rule going
forward is an event, not a setter call from a held reference. ADR-0014's underlying
principle survives — the coordinator's field is still mutated only by code the coordinator
owns, and the two range clamps still live there — it is the *caller's* access path that
changes, from a held object reference to a subscription.

Two mechanics are decided here rather than deferred, because Option B's Cons show both are
correctness constraints, not implementation taste:

1. **Every payload carries the config entry's id, and every listener filters on it.** The
   event bus is instance-global; the direct reference scoped writes to one entry for free
   and an event does not. This extends the existing `EVENT_*` payload convention, whose
   current members carry no `entry_id` because they have only ever had one producer per
   instance in practice.
2. **The coordinator's listeners are synchronous `@callback` functions**, registered with
   `hass.bus.async_listen` and unsubscribed on entry unload — never coroutines. This is what
   preserves the "field applied before the refresh it triggers" ordering the current
   setter-then-`async_request_refresh` sequence gets from the language.

The per-field event vocabulary is chosen over one generic event with a field discriminator
because the generic shape reintroduces stringly-typed dispatch inside the coordinator and a
union-typed payload, trading the narrow coupling this decision is buying for a single
constant.

The clamp question raised in Context is resolved as: the coordinator's listener clamps its
own field exactly as `set_target_current`/`set_soc_limit_override` do today; the entity
continues to bound its own displayed value with its own `native_min_value`/
`native_max_value`. These are now two independent enforcements of the same config-derived
bound rather than one call. This is not a new divergence — the entity already writes its
display before the coordinator sees the value — but it is now an explicit, named property of
the design rather than an accident of call order.

## Consequences

- **This ADR decides the shape; it implements nothing.** An implementation spec / TDD plan is
  needed to carry out the migration across `select.py`, `number.py`, `time.py`, `switch.py`
  and `coordinator.py`, and to update the entity tests that currently assert against a
  coordinator double so they assert on fired events instead.
- **ADR-0014 is superseded in full.** Its Status becomes `Superseded by ADR-0016` and its ADL
  row is updated; its own Context/options/Decision text is left untouched, per the
  immutability rule. Its forward-looking rule ("any future externally-writable field gets a
  setter method rather than its own ADR") no longer applies — the rule is now this ADR's
  event path.
- **New `EVENT_*` constants in `const.py`** — one per externally-writable field, using the
  same `smart_charging_*` snake_case HA event-type shape ADR-0011's constants use
  (`EVENT_ACTIVE_SOC_LIMIT_CHANGED`, …), plus the payload-key `ATTR_*` constants they need
  (including the shared entry-id key). These are **not** ADR-0011-criterion domain events
  (they name a requested change, not a past-tense computed transition), so they should be
  named accordingly (e.g. a `*ChangeRequested` shape) rather than reusing PascalCase
  transition names that would misrepresent them as ADR-0011 events. Naming the exact set is
  the implementation spec's job; this ADR fixes only that they exist and are per-field.
- **The in-flight departure-time/home-day platform work implements the now-superseded
  pattern.** Its coordinator wiring is what prompted this decision. Per CLAUDE.md's rule that
  a decision is captured before the work depending on it is committed, that work is expected
  to be reworked onto this ADR's event shape before it merges, rather than landing the
  superseded pattern and migrating later.
- **Out of scope: the read direction.** `sensor.py`'s `CoordinatorEntity` subclasses keep
  their coordinator reference for coordinator→entity state sync. This decision covers only
  the write path of owned *control* entities.
- **Harder:** debugging a write is now a two-hop trace (fired event → subscribed listener)
  instead of a call site, and the two new mechanics have to be honored by every future
  control entity — a payload missing `entry_id` cross-talks between config entries, and a
  listener written as `async def` silently loses the apply-before-refresh ordering. Both
  deserve an explicit test.
- **Easier:** an entity's write becomes independently testable without a coordinator; a new
  owned control entity is added by firing one event rather than by extending the
  coordinator's public method surface; and a second consumer of any user-set value can
  subscribe without the coordinator knowing it exists.
