# ADR-0024: Paired clear event to re-arm the deadline-unreachable notice per occasion

Date: 2026-08-13
Status: Accepted

## Context

ADR-0011 settled the cross-Manager coordination vocabulary and confirmed
`DeadlineUnreachableNotified` (Charging Coordinator M1 → Notification Manager M3, UC05) as a
genuine, kept domain event, describing it as carrying **"notify-once semantics"**. What ADR-0011
did not anticipate is what signals the *resolution* of the underlying condition — and the
implementation has now run into exactly that gap.

The producer fires the event as a **level signal, not an edge**. `coordinator.py` fires
`EVENT_DEADLINE_UNREACHABLE_NOTIFIED` on **every** control cycle for which the Deadline Engine's
`RequiredCurrentResult.unreachable` is `True` (`engines/deadline.py`:
`unreachable = required_a > maximum_permitted_rate_a`), not only on the cycle the condition first
holds. Two documents record this as deliberate rather than incidental: Task 5.2's test docstring in
`docs/plans/2026-07-21-deadline-soc-management.md`:958-962 ("published every cycle …
`unreachable` flag is True — including re-firing on a later cycle that is still Unreachable, not
only on the Normal/Urgent -> Unreachable transition edge"), and UC05's own domain-events section
(`docs/analysis/use-cases/UC05-guarantee-ready-by-departure.md`:96, "or re-fires while remaining in
Unreachable"). The rationale is that the consumer must not have to catch one exact tick, and that
the payload's required current stays fresh. There is no counterpart fired when `unreachable` goes
back to `False`.

The consumer therefore has to supply the once-ness ADR-0011 attributes to the event.
`NotificationManager._deadline_unreachable_notified` latches on the first delivery and suppresses
every later one for the lifetime of the Manager instance. That stops the spam (one push per 10 s
default cycle would otherwise reach the user), but it makes the notice **once per Manager instance**
rather than **once per occasion**: a deadline that becomes unreachable, resolves (the car
disconnects, state of charge catches up, the deadline capability is withdrawn — R18, or the
missed-deadline hold clears), and later becomes unreachable again delivers only the first notice
until the next reload or restart. R5's acceptance criterion ("when even charging at the maximum
permitted rate cannot meet the deadline … sends the user a notification that the deadline is
unreachable") reads as a per-occasion obligation, and `NotificationManager`'s class docstring
already carries this as a declared known gap rather than as intended behaviour.

Four forces bear on the fix:

- **ADR-0011's criterion is the governing rule.** Publish a domain event **iff** the trigger is an
  integration-computed domain transition the consumer cannot observe without duplicating the
  producer's computation; re-derive (observe the adapter) **iff** the trigger is external state
  already reached through an adapter. `unreachable` is **not** external adapter state — it is
  computed inside the Coordinator's cycle by the Deadline Engine from the resolved deadline, state
  of charge, the active SOC limit, the EV battery capacity (R15) and the maximum permitted rate.
  Both its onset **and** its clearing fall on the *event* side of that criterion.
- **UC05 already models the exit as a first-class transition.** Its state model gives `Unreachable`
  explicit exits (required current back within the maximum permitted rate → `Urgent`; within the
  baseline's desired current → `Normal`; and, while a missed-deadline hold is in effect, state of
  charge reaching the active SOC limit, a disconnect, the deadline capability becoming absent, or
  the following occurrence elapsing → `Normal`). Its "Domain events produced" section names
  `DeadlineUrgencyReverted` for the `Urgent`/`Unreachable` → `Normal` edge — but **nothing** for
  `Unreachable` → `Urgent`, the exit where the deadline stops being unreachable while remaining at
  risk. The analysis layer has a hole exactly where the consumer needs a boundary.
- **Producer-side edge detection is already the established shape.** `SocGateResolver` in
  `coordinator_cycle.py` resolves the active SOC limit and returns `(value, changed)`, with the
  Coordinator firing `ActiveSocLimitChanged` off that flag (ADR-0012 keeps the detection pure,
  ADR-0009/0010 keep the `hass.bus` call coordinator-side). Whatever is chosen here has a worked
  precedent to follow or to depart from deliberately.
- **R5 is a Must, and delivery robustness is part of it.** Whatever replaces the current latch must
  not make the single most important delivery — the first notice of an at-risk departure — depend on
  the consumer happening to be listening during one 10 s cycle.

## Considered options

### Option A — Do nothing: keep the once-per-Manager-instance latch

Accept the current behaviour, leave `NotificationManager`'s known-gap docstring as the record, and
close #546 as won't-fix.

- Pro: Zero cost and zero risk. The behaviour is already safe (no spam) and honest (documented, not
  silently wrong), and the gap only bites an HA instance that experiences the unreachable condition
  more than once between restarts — plausibly rare for a single-car household with a stable
  departure time.
- Con: It leaves a Must requirement partially unmet in exactly the situation R5 exists for: a driver
  whose departure is genuinely at risk on a *second* occasion gets no warning at all, silently, with
  no way to tell a suppressed notice from a resolved condition. The gap also grows with instance
  uptime, so the deployments least likely to be restarted are the ones most likely to miss a notice.

### Option B — Publish a paired clear event on the `True` → `False` edge

Add one domain event — `DeadlineUnreachableCleared` — fired by the Coordinator on the cycle
`unreachable` transitions from `True` to `False` — including the two guard paths that reach
`unreachable=False` without computing a required current at all: `deadline_resolvable` going false
(a disconnect, or `ev_soc` becoming `None`), and `deadline_today` resolving to `None` (a withdrawn
deadline capability, R18). `DeadlineUnreachableNotified` keeps its level semantics unchanged; M3
re-arms `_deadline_unreachable_notified` on the clear event.

- Pro: Faithful to ADR-0011's criterion — the clearing is an integration-computed domain transition
  the consumer cannot observe without re-running the Deadline Engine's determination — and it fills
  the exact hole UC05's state model leaves on the `Unreachable` → `Urgent` exit. It touches no
  landed producer contract (Task 5.2's per-cycle fire and its tests stand), so the notice keeps the
  level signal's robustness: a Manager that starts mid-condition still delivers on the next cycle.
  It needs no new entity surface, because a bus event maps directly to an HA `event:` trigger, as
  `DeadlineUnreachableNotified` already does. Detection has a precedent to copy in `SocGateResolver`.
- Con: The R5 vocabulary ends up with two events of **asymmetric** semantics on one edge — one
  repeating every cycle while the condition holds, one firing only on its boundary — so a
  contributor (or a user writing an automation) must know which is which; ADR-0011's uniform "an
  event is a transition" mental model no longer describes both halves. The notify-once state also
  stays in the consumer, so M3 keeps a latch; the ADR buys per-occasion correctness, not the removal
  of consumer-side lifecycle state.

### Option C — Materialize `unreachable` as coordinator/owned state and let M3 observe it

Surface `required.unreachable` as observable state — a dedicated owned diagnostic entity, or an
attribute on the ADR-0021 adapter-readings sensor — and have the Notification Manager read it from
its own tick, dropping reliance on the fired event to scope the latch.

- Pro: Mints no new event at all, and gives the condition a visible surface a user could put on a
  dashboard or trigger their own automation from — genuinely useful independent of this decision, and
  the same materialization treatment ADR-0011 chose for the resolved active SOC limit.
- Con: It only *superficially* resembles ADR-0011's "re-derive" branch. That branch is reserved for
  **external state already reached through an adapter** (NF3); `unreachable` is integration-computed,
  so routing it through a polled state read applies the criterion's shape without its justification.
  Worse operationally: M3's tick is its own UC08 evaluation cadence, not the Coordinator's control
  cycle, so polling introduces a second cadence that can straddle a whole short-lived occasion —
  becoming unreachable and resolving between two of M3's reads would be observed as *nothing
  happened*, losing both the notice and the re-arm. And unlike Option B it does require an
  `entity-catalog.md` addition and an owned-entity object_id decision (ADR-0004/ADR-0013) to carry a
  signal only one consumer needs.

### Option D — Move notify-once to the producer: fire `DeadlineUnreachableNotified` on the edge only

Reverse Task 5.2: fire the event only on the cycle `unreachable` first becomes `True`, making it a
true edge event, and delete M3's latch entirely. Re-entry after a resolution then re-fires naturally
with no clear event needed.

- Pro: The cleanest conceptual result and the one that makes ADR-0011's own words literally true —
  "notify-once semantics" would live in the event itself rather than in a consumer workaround. One
  event, no asymmetry, no consumer lifecycle state, and the producer owns the edge detection, which
  is exactly where `ActiveSocLimitChanged` already puts it.
- Con: It trades a correctness gap for a delivery gap on the same Must requirement. With no level
  signal, a consumer that is not listening on that one cycle — M3 reloaded, HA restarted, or the
  integration set up while a deadline is already unreachable — never learns of the occasion at all,
  and nothing re-offers it for as long as the condition persists; the driver's departure is at risk
  and the system stays silent. It also discards the per-cycle refresh of the payload's required
  current and rewrites a deliberately-chosen, landed producer contract plus its coordinator tests,
  for a benefit that Option B obtains without that regression.

### Option E — Re-arm on the already-specified `DeadlineUrgencyReverted`

Mint nothing new: implement UC05's existing (documented but not yet built) `DeadlineUrgencyReverted`
event and have M3 re-arm its latch on that.

- Pro: Uses a transition the analysis layer has already named, specified and reviewed, so the
  glossary and UC05's event list need no new entry, and it implements a documented event that is
  currently absent from the code anyway.
- Con: It is the wrong boundary. `DeadlineUrgencyReverted` fires on
  `Urgent`/`Unreachable` → `Normal` — it does **not** fire on `Unreachable` → `Urgent`, so a
  deadline that becomes reachable-but-still-urgent and later slips back to unreachable would still be
  suppressed: #546's bug survives in the case most likely to occur, since partial recovery is more
  common than full recovery. Re-arming an *unreachable* latch off an *urgency* transition also
  conflates two distinct state boundaries, leaving the consumer's suppression window defined by a
  condition it does not otherwise care about.

## Decision

**Option B.** The Coordinator publishes a paired clear event, `DeadlineUnreachableCleared`, on the
control cycle `RequiredCurrentResult.unreachable` transitions from `True` to `False`;
`DeadlineUnreachableNotified` keeps its existing per-cycle level semantics unchanged, and the
Notification Manager re-arms `_deadline_unreachable_notified` on the clear event so R5's notice is
delivered once **per occasion** rather than once per Manager instance.

ADR-0011's criterion decides the option *class* before anything else: `unreachable` is computed by
the Deadline Engine inside the Coordinator's cycle, not read through an adapter, so its clearing is
an integration-computed domain transition and belongs on the event side of the criterion. That
disqualifies Option C, whose apparent thrift is the criterion's "re-derive" shape applied without
its NF3 justification — and which additionally pays an `entity-catalog.md` surface and an
independent polling cadence that can miss a whole short occasion, the one failure mode a
notification must not have.

Between the two event-side options, B is chosen over D because D's conceptual cleanliness is bought
by making the *first* notice of an at-risk departure contingent on the consumer being subscribed
during one 10 s cycle — trading #546's "second occasion is silent" for "any occasion spanning a
reload or restart is silent", on the same Must requirement, and discarding both the payload refresh
and a deliberately-chosen landed producer contract. B accepts D's real cost instead, and states it:
the R5 edge now carries two events with asymmetric semantics, and M3 keeps a latch. Option A is
rejected because the gap it preserves is a silent failure of R5 that grows with uptime, and Option E
because `DeadlineUrgencyReverted`'s `→ Normal`-only boundary leaves the partial-recovery case — the
likeliest one — still suppressed.

This **refines** ADR-0011 and supersedes nothing. ADR-0011's per-trigger table row for
`DeadlineUnreachableNotified` and its Option-C criterion both stand exactly as written; this ADR
settles what ADR-0011 left open on that same Coordinator → Notification Manager edge, which now
carries an onset event *and* a clear event rather than one event alone. In ADR-0011's own table
shape, the added trigger reads:

| Trigger | Producer → Consumer | Resolution | Why |
| --- | --- | --- | --- |
| **`DeadlineUnreachableCleared`** (UC05) | Coordinator → Notification Manager | **Publish a new event** | The clearing of `RequiredCurrentResult.unreachable` is an integration-computed transition, on the same side of ADR-0011's criterion as the onset: the Deadline Engine derives it inside the Coordinator's cycle from the resolved deadline, state of charge, the active SOC limit, the EV battery capacity (R15) and the maximum permitted rate — never read through an adapter (NF3), so the consumer cannot observe it without re-running that determination. Pairs with the level-signal onset event so the consumer's notify-once state can be scoped to the occasion. |

The durable rule it adds:
**when a published event is a level signal — fired every cycle a condition holds, so a consumer
need not catch the transition tick — the producer must also publish the clearing edge, so consumers
can scope once-per-occasion state to the occasion rather than to their own lifetime.** ADR-0011's
"notify-once semantics" is thereby a property of the event *pair*, not of the onset event alone.

`DeadlineUnreachableCleared` follows the DDD convention (past-tense PascalCase) and the repo's
existing `*Cleared`/`*Lifted` pairing precedent (`SolarStepUpApplied`/`SolarStepUpCleared`,
`SolarReserveCapEngaged`/`SolarReserveCapLifted`). It fires on **every** exit from `Unreachable`,
which is precisely what makes "occasion" mean what the user means by it. Three distinct code paths
reach `unreachable=False`, and the edge check must sit downstream of all of them — on
`RequiredCurrentResult.unreachable` itself, not on any one guard:

| Exit | Mechanism in code today | Fires |
| --- | --- | --- |
| Required current falls back within the maximum permitted rate (→ `Urgent`, or → `Normal` if it also falls within the baseline's desired current) | `resolve_required_current` (`engines/deadline.py`) computes `unreachable = required_a > maximum_permitted_rate_a` and it is now `False` | `DeadlineUnreachableCleared`; additionally `DeadlineUrgencyReverted` on the `→ Normal` exit |
| Car disconnects, or `ev_soc` becomes `None` | `deadline_resolvable = status in CHARGEABLE_STATES and ev_soc is not None` (`coordinator.py`:518) goes false, so `resolve_deadline_urgency` returns its early `RequiredCurrentResult(required_a=None, urgent=False, unreachable=False)` without calling the engine | `DeadlineUnreachableCleared` |
| Deadline capability withdrawn (R18) — every R14 row resolves to "no deadline" | `deadline_resolvable` may still be `True`; instead `_read_deadline_urgency_inputs` yields `deadline_today = None` (`resolve_departure_deadline` returning `None`), and `resolve_required_current`'s own `if deadline is None` guard returns `unreachable=False` | `DeadlineUnreachableCleared` |

The second and third rows are **different** mechanisms, not one: a withdrawn capability does not make
`deadline_resolvable` false — that predicate reads only charger status and `ev_soc`. It is distinct
from `DeadlineUrgencyReverted`, which fires only on the `→ Normal` exit and remains UC05's
urgency-level event.

**Fault cycles hold the prior state.** Both of `_run_cycle`'s fault early-returns — the
required-adapter fault (`coordinator.py`:354-369) and the `ev_soc` fault (:410-432) — return before
the deadline-urgency block runs, so neither the onset fire nor this ADR's edge check is reached on a
fault cycle. The prior-cycle `unreachable` flag the detector owns must therefore be **left
unchanged** on such a cycle, not reset to `False`: resetting it would emit a spurious clear (and
re-arm M3) on a cycle that established nothing about the deadline, and would then re-notify on the
next healthy cycle. Holding is the same rule already applied to `adapter_readings_at` for exactly
these two returns (#648): a fault cycle is not a successful cycle, so it does not advance state. The
detector is consequently a plain "compare against last *evaluated* cycle" — fault cycles are
invisible to it — and a clear fires on the first healthy cycle that genuinely resolves.

## Consequences

- **Analysis-doc follow-ups**, each gated by its own issue and fresh-agent review per CLAUDE.md's
  review protocol; this ADR opens none of them:
  - `docs/analysis/use-cases/UC05-guarantee-ready-by-departure.md` — add
    `DeadlineUnreachableCleared` to "Domain events produced", annotate every `Unreachable` exit in
    the state-model table and the `stateDiagram-v2` with it, and state its relationship to
    `DeadlineUrgencyReverted` (which fires only on the `→ Normal` exit, so the two co-fire there and
    only the clear event fires on `Unreachable` → `Urgent`).
  - `docs/analysis/system-overview.md` — a glossary entry for the event, mirroring the shape of the
    existing `ActiveSocLimitChanged` entry; and a sharpening of the `maximum permitted rate` and
    `required current` entries' "the deadline-unreachable notification (R5) fires when…" wording to
    say once per occasion.
  - `docs/analysis/requirements.md` — R5's notification acceptance criterion currently says only
    "sends the user a notification that the deadline is unreachable"; per `write-requirement` it
    needs a SMART criterion pinning **once per occasion, re-armed when the condition clears**, so
    the obligation this ADR implements is testable at the requirement level.
  - `docs/analysis/entity-catalog.md` — **no change required**, and worth recording why: unlike
    `ActiveSocLimitChanged`, which needed the resolved value materialized as
    `sensor.smart_charging_active_soc_limit` for its HA trigger, both deadline events map directly to
    an HA `event:` trigger and need no owned entity.
  - `docs/analysis/control-cycle.md` — no change: its "Domain events produced" list deliberately
    omits the deadline events (they live in UC05); if a future edit lists them there, it must list
    the pair, not the onset alone.
- **Plan-doc follow-ups**: `docs/plans/2026-07-21-deadline-soc-management-design.md` §10 and
  `docs/plans/2026-07-21-notifications-design.md` §0/§9/§7 both enumerate the events their slice
  emits and consumes and both name `DeadlineUnreachableNotified` as the sole R5 event; each needs the
  clear event added on its own side of the edge, plus a task for the work below.
- **Implementation this unblocks** (the follow-up #546's "Scope for a follow-up" asks for, now
  decided): an `EVENT_DEADLINE_UNREACHABLE_CLEARED` constant in
  `custom_components/smart_charging/const.py`; producer-side edge detection in
  `custom_components/smart_charging/coordinator_cycle.py` shaped like `SocGateResolver` — pure
  `(unreachable, cleared)` detection owning the prior-cycle flag, with the `hass.bus.async_fire`
  staying in `coordinator.py` per ADR-0009/0010, alongside the existing `unreachable` fire site;
  with the detector holding its prior flag across the two fault early-returns per the Decision above;
  and re-arming `_deadline_unreachable_notified` in
  `custom_components/smart_charging/managers/notification_manager.py`, which also deletes that
  Manager's second "Known gaps" bullet and the module docstring's "producer-side signal not yet
  implemented" note. Tests land in `tests/test_coordinator_cycle.py` (detection), and
  `tests/test_coordinator.py` + `tests/managers/test_notification_manager.py` (fire and re-arm) per
  ADR-0009's harness split. Those tests cover the exit paths that exist in the code today — required
  current falling back within the maximum permitted rate, a disconnect (`deadline_resolvable` false),
  and the deadline capability absent (`deadline_today` `None`) — plus a fault cycle not emitting a
  clear. A reload resets the producer's edge flag and the consumer's latch together, so no missed
  re-arm is introduced at the seam.
- **Forward obligation on the missed-deadline hold.** R5's missed-deadline hold and UC05's
  corresponding `Unreachable` exits (state of charge reaching the active SOC limit, a disconnect, the
  deadline capability becoming absent, the following occurrence elapsing) are **analysis-only today**
  — there is no hold in `custom_components/smart_charging/`, so none of those exits can be built or
  tested against current code. This ADR therefore places the obligation on whichever future slice
  implements the hold: each hold-exit it adds must also clear `unreachable` through the same
  `RequiredCurrentResult` the edge check reads (or fire the clear event itself), and must land a test
  per exit path pinning that. Because the detection sits on `unreachable` rather than on any one
  guard, a hold that ends by making `unreachable` false gets the clear for free; a hold implemented
  as a separate latch *outside* `RequiredCurrentResult` would not, and that is the trap the slice must
  avoid.
- **What becomes harder.** Every future exit path added to the `Unreachable` state must result in the
  clear event firing, or the consumer's latch silently stays armed — a coupling the level-signal onset
  event does not have. Contributors reading the two events side by side also see one level signal and
  one edge signal on the same edge, which the ADR's durable rule above exists to explain.
- **What this forecloses.** `DeadlineUnreachableNotified` is confirmed to stay a level signal, so any
  future consumer must dedupe for itself rather than assume one delivery per occasion; and the
  Notification Manager stays event-driven, never polling Coordinator-computed state, so no
  `unreachable` entity surface is added by this decision.
