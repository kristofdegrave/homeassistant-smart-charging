# Resolution rules

The shared, priority-ordered lookups that several use-cases and the
[coordinator](system-overview.md#ubiquitous-language) consume. They are collected here so no
use-case restates them: a use-case references a rule by name ("resolve the active SOC limit")
and this document is authoritative for the priority order and the requirement each rule
satisfies. These are **lookups, not mechanism** — the order of operations within a control
cycle lives in `control-cycle.md`; entity bindings live in `entity-catalog.md`.

Most rules below are decision tables evaluated top-to-bottom: **the first row whose condition
holds wins.** Every row carries a **name** as well as a priority number, and that name is how the
row is cited — here and throughout `docs/analysis/` — so that re-ordering a table never silently
changes what a citation elsewhere refers to. (`docs/design/` and `docs/adl/` still cite some rows
by ordinal as of this writing; ADR bodies are immutable and cannot be updated retroactively, and
the design docs are a separate reconciliation pass.) The required-current rule is a shared formula
instead, since it has no priority order to evaluate. Every rule is re-evaluated every control cycle, so a change in conditions
changes the result on the next cycle. Three of the inputs these rules read are not values observable
*this* cycle but flags the coordinator threads across cycles for the current connected session:
whether a [solar step-up](system-overview.md#ubiquitous-language) is in effect (R7/R8), whether
[deadline urgency](system-overview.md#ubiquitous-language) is latched on (R5), and whether a
[missed-deadline hold](system-overview.md#ubiquitous-language) is in effect (R5). All three are
called out where the rule that reads them is defined.

---

## Active SOC limit (R7)

Resolves the single [active SOC limit](system-overview.md#ubiquitous-language) in force at any
moment. Priority order: [solar-reserve cap](system-overview.md#ubiquitous-language) →
[solar step-up](system-overview.md#ubiquitous-language) → default. Whichever mode is active simply
charges to this resolved value — it has no opinion on *why* the limit is where it is.

| Priority | Row | Condition | Active SOC limit |
| --- | --- | --- | --- |
| 1 | *Solar-reserve cap* | The `Auto` profile is active, the [home-day flag](system-overview.md#ubiquitous-language) is set, the [sun is down](system-overview.md#ubiquitous-language), the next-day [solar forecast](system-overview.md#ubiquitous-language) exceeds its threshold (default 12 kWh), the departure-deadline rule below, evaluated one day ahead, resolves to "no deadline" for tomorrow, and no [missed-deadline hold](system-overview.md#ubiquitous-language) is in effect (R5, below) | The solar-reserve cap (default 60 %) |
| 2 | *Solar step-up* | A solar step-up is in effect (a step has been applied while the `Auto` profile is active and charging in a solar mode, R8) | The stepped-up value, clamped to `max_solar_soc` (default 100 %) |
| 3 | *Default limit* | Otherwise | The default `number.smart_charging_soc_limit_override` (default 80 %) |

- **The solar-reserve cap is an `Auto`-only coordination decision (R9).** Reserving overnight
  capacity for tomorrow's solar is `Auto` weighing tonight's grid top-up against tomorrow's solar
  yield — an optimisation, not a hard constraint — so it applies only while `Auto` is the active
  profile. Under `Manual`, *Solar-reserve cap* never matches regardless of the home-day flag or forecast: the
  user's own mode choice is not second-guessed by this policy (mirrors R16's "no automatic
  changes under `Manual`"). The mode `Auto` selects (typically `Captar`, via Auto mode-selection's
  *Overnight top-up* row below) does not
  itself evaluate the home-day flag or forecast; it only ever sees the resolved limit.
- **Row 1 is deliberately not conditioned on the car being connected**, unlike row 2's step-up
  (below), which only ever applies while charging. The cap is a nightly resolution — it answers
  "what ceiling is in force right now" regardless of whether a car is plugged in, the same way
  every row here does — and the resolved value simply goes unused until one is
  ([UC07](use-cases/UC07-reserve-capacity-for-tomorrow.md)'s Relationships section has the full
  rationale).
- **The solar step-up is also an `Auto`-only coordination decision (R8), like the reserve cap
  above.** Under `Manual`, *Solar step-up* never matches regardless of which solar mode is charging or how
  close the SOC is to the active SOC limit — a manually selected solar session simply charges to
  whichever limit *Default limit* resolves, with no automatic raise.
- **Lifecycle and reset are governed by R7** (and applied by UC06): a step-up survives a switch
  between `Solar` and `SolarOnly`, is cleared when the active mode is no longer a solar mode,
  and resets to the default on disconnect. This table resolves the *current* value only.
- Deadline urgency's own levers (R5 — the peak-limit raise and `Auto`'s mode escalation) never raise
  the active SOC limit; they only accelerate toward whichever limit this table returns. **The
  *Solar-reserve cap* row has two deadline preconditions, and the cap is mutually exclusive with
  each (R9):**
  - *A departure deadline resolved for tomorrow* — the deadline takes priority, so that row never
    matches while one is resolved for tomorrow, which is what the cap exists to protect: the cap's
    purpose is to leave room overnight for the following day.
  - *A missed-deadline hold in effect* (R5, below) — that first precondition is about tomorrow's date
    only, so this second one is what keeps the cap out of the way of a deadline resolved for *today*
    and since missed. Without it, the cap could lower the active SOC limit below the SOC of a session
    the driver is actively waiting on.

  A deadline resolved for *today* and **still ahead of now** is the one case neither precondition
  speaks to, and the cap deliberately tolerates it: such a deadline is not competing for tomorrow's
  reserve. Elsewhere, where the two are called simply "mutually exclusive"
  ([UC05](use-cases/UC05-guarantee-ready-by-departure.md),
  [UC07](use-cases/UC07-reserve-capacity-for-tomorrow.md), R9), that is shorthand for these two
  preconditions. When either takes hold while the cap was already active, the cap lifts from the next
  cycle and the active SOC limit resolves without it — R9's own priority rule, not urgency reaching
  into R7. Without the deadline capability (R18) no deadline is ever resolved and no hold can arise,
  so both preconditions are always satisfied and the cap turns on its remaining conditions alone.
- Without the solar capability (R18), the *Solar-reserve cap* and *Solar step-up* rows are inert:
  no solar mode ever runs (so no
  step-up), and the solar-reserve inputs are not configured, so the table returns the default.

**Satisfies:** R7 · **Consumed by:** UC01, UC02, UC03, UC04, UC05, UC06, UC07, UC09, UC10.

---

## Departure deadline (R14)

Resolves the [departure deadline](system-overview.md#ubiquitous-language) — the next moment at
which the car must be ready. Two steps: the table below resolves a **departure time for a given
calendar date** (priority order: external sensor → public-holiday / home-day override →
day-of-week default), and the **Next occurrence** rule underneath it picks which date's resolution
is the deadline in force. **Any row may resolve to "no deadline,"** in which case that date imposes
no deadline of its own.

**This rule is evaluated only while the [deadline capability](system-overview.md#ubiquitous-language)
is present (R18).** When it is absent none of the inputs below is configured at all, the rule does
not run, and no deadline is ever resolved — for today or for any day ahead. Every consumer then
behaves exactly as it does under "no deadline": the required-current rule computes nothing, so
deadline urgency never engages and the effective-peak-limit rule never takes its *Urgency raise* row (R5);
Auto mode-selection's *Deadline urgency* row never matches (R16); the plug-in reminder never fires (R12); and the
solar-reserve cap's one-day-ahead "no deadline" precondition is always satisfied (R9).

| Priority | Row | Condition (evaluated for the date being resolved) | Departure time for that date |
| --- | --- | --- | --- |
| 1 | *External sensor* | An external departure-time sensor is configured (NF3) | The sensor's current value, read as a time-of-day and applied to the date being resolved (may be "no deadline") |
| 2 | *Public holiday* | That date is a recognised public holiday (from a configured holiday source, NF3) | The public-holiday override (default no deadline) |
| 3 | *Home day* | The home-day flag applies to that date | The home-day override (default no deadline) |
| 4 | *Day-of-week default* | Otherwise | That date's day-of-week default (defaults: 06:00 Mon–Fri; no deadline Sat–Sun) |

- If a date is **both** a public holiday and a home day, *Public holiday* wins (public-holiday precedence).

**Next occurrence.** The departure deadline in force is:

1. **today's** resolution combined with today's date — but only while that moment is *strictly
   after* now; otherwise
2. **tomorrow's** resolution combined with tomorrow's date — the table re-evaluated in full for
   tomorrow's date, not today's resolved time shifted by 24 hours, since tomorrow may resolve a
   different time (a different day-of-week default, a public holiday, a home day) or no departure
   time at all.

When neither step yields a moment — today's resolution is "no deadline" or already reached, *and*
tomorrow's is "no deadline" — no deadline applies: R5 forces no charging of its own and R12 sends
no reminder. The lookahead stops after tomorrow: a departure time further out than tomorrow's
occurrence is not yet a deadline and becomes one only as the days roll over. One day covers both
consumers — R5 concerns the deadline the current charging session must meet, and R12's lead time
(default 8 h) is assumed shorter than a day, so a lead time configured at 24 h or more is outside
what this lookahead serves.

- Because the deadline is always strictly in the future, the time remaining to it (below) is always
  positive: a departure time whose time-of-day has already passed today never yields a deadline in
  the past, and so never makes a deadline look unreachable (R5) on that basis alone. This rule always
  rolls forward, with no exception: what changes when a deadline elapses while the car is still short
  of its active SOC limit is not the resolution but what urgency does with it — see the
  [missed-deadline hold](system-overview.md#ubiquitous-language) in the required-current rule below.
- The resolved deadline feeds the deadline guarantee (R5) and the plug-in reminder (R12), and is
  the [departure window](system-overview.md#ubiquitous-language) R12 de-dups against.
- **The same table, evaluated one day ahead** (tomorrow's day-of-week default, tomorrow's
  public-holiday status, and the home-day flag, which refers to the reserved day for as long as the
  solar-reserve cap's own trigger conditions are being checked) feeds the solar-reserve cap's
  precondition (R9, [UC07](use-cases/UC07-reserve-capacity-for-tomorrow.md)): the cap only
  activates, and stays active, while this evaluation resolves to "no deadline" for that day — one of
  the cap's two deadline preconditions, the other being that no missed-deadline hold is in effect
  (below), which this table does not resolve. That
  precondition is deliberately fixed on tomorrow's calendar date — it asks about the day whose solar
  yield is being reserved for — and is therefore independent of which date the *Next occurrence*
  rule selects for the deadline in force.

**Satisfies:** R14 · **Consumed by:** UC05, UC07, UC10.

---

## Required current for the departure deadline (R5, R15)

Computes the current the System would need to sustain, from now until the departure deadline
above, to close the projected gap to the [active SOC limit](system-overview.md#ubiquitous-language)
— the shared input the effective-peak-limit rule (below) and Auto mode-selection (below) both
consume to decide whether [deadline urgency](system-overview.md#ubiquitous-language) (R5)
applies. The **missed-deadline hold** at the end of this rule is the second, and only other, way
urgency comes to be in effect.

- **Energy needed** = EV battery capacity (R15, sensed or configured) × (active SOC limit −
  current state of charge) ÷ 100.
- **Time remaining** = the departure deadline above − now. Since that deadline is the *next future
  occurrence* of the resolved departure time (above), the time remaining is always strictly
  positive: it shrinks as the deadline approaches and, once the deadline passes, jumps to the
  interval to the following occurrence rather than going negative. When the departure deadline has
  resolved to "no deadline" — or the deadline capability is absent, so no deadline is resolved at
  all (R18) — no required current is computed and deadline urgency never applies.
- **[Required current](system-overview.md#ubiquitous-language)** = energy needed ÷ time
  remaining, converted to amperes via the resolved supply voltage (NF4).
- **[Escalated maximum permitted rate](system-overview.md#ubiquitous-language)** = the
  [maximum permitted rate](system-overview.md#ubiquitous-language) that *would* be in force if
  deadline urgency were engaged — that is, with the effective peak limit at the maximum peak
  (the effective-peak-limit rule's *Urgency raise* row, below). It is computed every cycle from
  the household baseline and the peak/ceiling bounds alone, **whether or not urgency is actually
  in effect**, so the engage test below does not move the moment it fires. Comparing against the
  rate currently in force instead would be self-cancelling: engaging urgency raises that rate,
  which would immediately make the deadline look comfortable again, reverting and re-escalating
  every cycle.

### Engaging urgency: the slack test (R5)

[Deadline urgency](system-overview.md#ubiquitous-language) **engages** on the cycle at which the
deadline stops having comfortable slack — the point beyond which escalating any later would no
longer meet it:

    required current > escalated maximum permitted rate ÷ (1 + deadline urgency margin)

with the [deadline urgency margin](system-overview.md#ubiquitous-language) fixed at 25%.
Equivalently, and this is the reading to hold in mind: urgency engages once the time needed to
close the gap at the escalated rate, plus a quarter of itself as slack, no longer fits in the time
remaining. An 8 h charge therefore engages with about 10 h left, a 2 h charge with about 2½ h left.

The test compares the required current against **what escalation could deliver**, never against
what the [baseline mode](system-overview.md#ubiquitous-language) happens to want on this cycle.
That distinction is the whole point of the rule: urgency's levers exist to widen a ceiling and
to override a cost policy, so they are warranted only when the deadline is genuinely at risk —
not merely because the baseline policy is, for now, asking for nothing. Judging against the
baseline's own desired current would make urgency fire unconditionally in every window where that
policy resolves to `Off` (after sunset and before the low tariff opens, under `Auto`), which is
the normal state of most evenings rather than an exception, and would ratchet the tracked monthly
peak (R11) up on each one.

**The deadline is *unreachable*** when the required current exceeds the escalated maximum
permitted rate outright — the same comparison with no margin. Because that threshold is strictly
above the engage threshold, `Unreachable` is always a strict subset of urgency and the
Normal → Urgent → Unreachable ordering of [UC05](use-cases/UC05-guarantee-ready-by-departure.md)'s
state model holds by construction. The rate is a *ceiling*, not a promise the active mode will
request that much: under `Auto` without the CapTar capability the escalation is to `Power`'s
configured target current (R17), which may be lower, which is exactly why R5 calls that path
best-effort rather than a guarantee.

### Clearing urgency: the handback test (R5)

Once engaged, urgency **latches**: it stays in effect across cycles rather than being re-derived
from the slack test, which charging at the escalated rate would otherwise falsify within one
cycle (the gap closes faster than the window does). It **clears** when any of these holds:

- the baseline mode's own [desired charger current](system-overview.md#ubiquitous-language) is at
  or above the required current, **on a cycle on which the slack test above does not itself hold**
  — the **handback**: the ordinary policy is now willing to do the job unaided, so there is nothing
  left for urgency's levers to add. Under `Manual` that is the
  manually selected mode's own desired current (`Manual` never escalates the mode, so this is
  simply the active mode itself); under `Auto`, that of whichever mode Auto mode-selection's
  baseline rows (below) would select on their own. The baseline is evaluated fresh every cycle
  from those rows alone, so the test is unaffected by `Captar` already being dispatched from the
  escalation — reading the escalated mode's own (always-maximum) desired current instead would
  clear urgency the instant it engages.
- state of charge is at or above the active SOC limit (the required current is then zero, so the
  handback holds trivially for any baseline);
- the car disconnects; the departure deadline resolves to "no deadline"; or the deadline
  capability becomes absent (R18);
- a [missed-deadline hold](system-overview.md#ubiquitous-language) clears (below). Neither test
  runs while a hold is in effect, so the latch that occurrence set would otherwise never be handed
  back. Three of the hold's four clear conditions are already urgency clears in their own right;
  the fourth — the backstop, the *following* occurrence elapsing — is not, and without this the
  latch would outlive the hold indefinitely against a baseline of `Off`, defeating the backstop's
  own "a hold never outlives one deadline cycle".

**The slack test takes precedence over the handback where both hold on the same cycle**, and they
genuinely can: a [desired charger current](system-overview.md#ubiquitous-language) is what a mode
*asks for*, before any clamp, so a baseline mode can want more than the escalated rate could ever
deliver — a baseline `Captar` desiring 32 A satisfies the handback against a required current of
20 A on a cycle whose escalated rate is only 15 A, while the slack test plainly holds. Letting the
handback win there would clear urgency, re-engage it next cycle, and alternate
`DeadlineUrgencyReverted`/`DeadlineUrgencyEngaged` indefinitely — the churn the latch exists to
prevent. One consequence is worth naming: since a required current above the escalated rate implies
the slack test holds, the handback can never clear urgency straight out of
[UC05](use-cases/UC05-guarantee-ready-by-departure.md)'s `Unreachable` state. The deadline must
first become reachable again (`Unreachable` to `Urgent`); only then can it be handed back.

Under a baseline of `Off`, the handback can only be satisfied by state of charge reaching the
active SOC limit — so urgency, once engaged, charges through to that limit. That is deliberate: it
is what makes R5 a guarantee rather than a duty cycle. When the low tariff opens mid-urgency the
baseline is already delivering, so the handback is graceful — mode selection returns to its own
row and charging continues uninterrupted.

**Deadline urgency is additionally in effect, regardless of both tests, for as long as a
[missed-deadline hold](system-overview.md#ubiquitous-language) is in effect (below).** Every
consumer that asks "is deadline urgency in effect" therefore needs no special case of its own.

### Missed-deadline hold (R5)

A departure time is a **target, not a cutoff** — the driver may leave a little later than planned —
so the System does not stop trying the moment a deadline is missed. The hold **engages** at the
moment the resolved departure deadline elapses while, on that same cycle:

1. the car is connected and its state of charge is still **below** the active SOC limit as resolved
   for that cycle, **and**
2. deadline urgency was in effect on the last cycle before that moment — the `Urgent` or
   `Unreachable` state of [UC05](use-cases/UC05-guarantee-ready-by-departure.md) — on that
   occurrence's *own* merits, i.e. because the slack test engaged urgency for it and no handback
   had yet cleared it, not because a previous hold was pinning urgency on.

While it holds, the deadline is **unreachable by definition** — time has run out on it — so urgency
is in effect and the System is pinned to `Unreachable`, with exactly that state's own behaviour: the
effective-peak-limit rule takes its *Urgency raise* row, `Auto` mode-selection takes its *Deadline
urgency* row, and delivery is
whatever those levers yield, bounded above by the [maximum permitted
rate](system-overview.md#ubiquitous-language). **No required current is computed while the hold is in
effect**, and neither the slack test nor the handback test runs, so the following occurrence's
longer time remaining cannot end the hold by making the deadline look comfortable again.

It **clears** when the car's state of charge is at or above the active SOC limit, when the car
disconnects, when the deadline capability becomes absent (R18), or — as a backstop — when the
*following* occurrence itself elapses, so a hold never outlives one deadline cycle. Nothing else the
departure-deadline rule resolves clears it: the hold is anchored to the occurrence already missed,
not to the next one, so it survives that next occurrence resolving to "no deadline" or to a different
time. From the cycle after it clears, the required current above governs normally again, and the urgency latch clears with it (see that rule's clear list above).

- **Evaluation order, so the hold and the cap above are not circular.** The hold is updated once per
  cycle, *after* the active SOC limit has been resolved for that cycle (so condition 1 reads the
  resolved value) and *before* the mode and peak decisions that consume urgency
  (`control-cycle.md`, step 4). The active-SOC-limit table's *Solar-reserve cap* row therefore reads the hold as it
  stood entering the cycle: on the very cycle a hold engages the cap may still have been in force,
  and it lifts from the next cycle onward — the same one-cycle settling any other precondition
  lapsing has ([UC07](use-cases/UC07-reserve-capacity-for-tomorrow.md)).
- **A car that connects only after a deadline has already elapsed is never held.** Condition 2 fails
  — urgency never engaged for that occurrence — so a session begun at, say, 08:00 with a 06:00
  deadline behind it resolves forward to tomorrow's occurrence by the ordinary rule (R14) and starts
  from `Normal`, exactly as before.
- **The hold excludes the solar-reserve cap** (the active-SOC-limit table's *Solar-reserve cap* row above, R9): the
  cap would otherwise lower the active SOC limit out from under a session the driver is waiting on.
  The mirror-image consequence is deliberate and worth naming: if the cap *was* in force when the
  hold engages, the active SOC limit rises back to what it resolves to without the cap, extending the
  target the hold then pursues. That is R9's own priority rule doing what it already does when a
  deadline appears for tomorrow (R7/R9), not urgency's levers raising the limit — those never do
  (R5).
- **A baseline mode that requests little or no current still latches the hold.** Under `Manual` with
  `Off`, or a solar mode after dark, urgency engages once the slack test fires and then cannot hand
  back — a 0 A baseline never reaches the required current — while nothing is actually charging; the
  hold then engages at the deadline and holds the effective peak limit at the maximum peak to no
  benefit, since `Manual` has no second lever
  ([UC05](use-cases/UC05-guarantee-ready-by-departure.md), 3b). The clear-at-the-following-occurrence
  backstop above bounds this rather than special-casing it: the user's own mode choice is not
  second-guessed (R16). The slack test bounds it further than the old baseline comparison did: such
  a session now spends only the run-up to the deadline in this state, not the whole night.
- **Not preserved across a restart.** Engagement is an edge — the moment a deadline elapses — so a
  restart spanning that moment leaves no hold, and the ordinary next-occurrence resolution governs.
  Deliberate: no analysis-layer state survives a restart (`entity-catalog.md`).

**Satisfies:** R5, R15 · **Consumed by:** the effective-peak-limit rule below, Auto mode-selection
below, the active-SOC-limit rule above (the *Solar-reserve cap* row's own preconditions), UC05, UC07.

---

## Effective peak limit

Resolves the [effective peak limit](system-overview.md#ubiquitous-language) — the ceiling on
net import that charging must stay below. Priority order: deadline urgency raises the limit;
otherwise it is the lesser of the configured maximum and the billed peak — itself raised to the
[external monthly-peak reading](system-overview.md#ubiquitous-language) when one is mapped and
higher — floored so a low or not-yet-established billed peak can't push the limit down too far
(the *Normal* row).

| Priority | Row | Condition | Effective peak limit |
| --- | --- | --- | --- |
| 1 | *Urgency raise* | Deadline [urgency](system-overview.md#ubiquitous-language) is in effect (R5 — possible only while the [deadline capability](system-overview.md#ubiquitous-language) is present, R18) | The [maximum peak](system-overview.md#ubiquitous-language) (default 4 kW) |
| 2 | *Normal* | Otherwise (normal operation) | `min(max(max(`[monthly peak demand](system-overview.md#ubiquitous-language)`, `[external monthly-peak reading](system-overview.md#ubiquitous-language)`), `[peak floor](system-overview.md#ubiquitous-language)`), maximum peak)` |

- This rule resolves the **ceiling** only, and is the *entire* deadline-urgency response under
  `Manual` (except when the CapTar capability is absent, where it is a no-op — see below):
  raising the ceiling never itself raises what a mode requests, but a mode whose own
  request was previously clamped below the old ceiling (e.g. `Captar` or `Power`) can now draw
  more, up to whatever it already requests, C1, and C4 — bounded above by the [maximum permitted
  rate](system-overview.md#ubiquitous-language). A mode whose own request does not depend on
  peak headroom at all (e.g. `Solar`, `SolarOnly`) draws no differently, so meeting the deadline
  under `Manual` depends entirely on the active mode's own appetite for current, not on this
  rule alone. Under `Auto`, this same ceiling raise combines with a second lever — Auto
  mode-selection escalating to `Captar` when the CapTar capability is present, or to `Power` when
  it is absent (its *Deadline urgency* row, below, R18) — so `Auto` meets far more deadlines than `Manual` can.
  `Captar` always requests the maximum charging current, a guarantee; `Power` requests only its
  configured target current, a best-effort substitute when `Captar` is unavailable.
- Charging always targets the [safety margin](system-overview.md#ubiquitous-language) *below*
  this limit (`effective peak limit − safety margin`); the margin is applied by the peak clamp
  in `control-cycle.md`, not by this rule.
- The [peak floor](system-overview.md#ubiquitous-language) (*Normal* row) is applied with `max()`
  before the `min()` with the maximum peak, so it can raise but never push the effective peak
  limit above the maximum peak — see the glossary term for why the floor exists.
- The [external monthly-peak reading](system-overview.md#ubiquitous-language) (*Normal* row), when
  mapped and available, is merged with `max()` against the internally-tracked
  [monthly peak demand](system-overview.md#ubiquitous-language) (tracked per R21) before the
  peak-floor `max()` and the maximum-peak `min()` are applied — so it too can
  raise but never push the effective peak limit above the maximum peak (R3). The merge is
  recomputed fresh every control cycle from both sources; it never overwrites the
  internally-tracked monthly peak demand, so a live spike this integration observes between
  external-sensor refreshes is not discarded. When unmapped or unavailable, this operand is
  simply the internally-tracked monthly peak demand.
- The limit never exceeds the maximum peak, even under urgency (C3).
- **When the CapTar [capability](system-overview.md#ubiquitous-language) is absent (R18), nothing
  consults this rule's result.** The peak clamp is the sole control-decision consumer of the
  effective peak limit, and it does not run at all on such an installation (R3, `control-cycle.md`
  step 5); the value still resolves by the *Normal* row and is still surfaced read-only for observability, but
  no charging decision turns on it. This rule therefore needs no capability branch of its own — it
  degrades by simply not being reached. The consequence for R5 is that the ceiling raise (*Urgency raise*)
  becomes a no-op there, leaving `Manual` with no working deadline lever at all and `Auto` with only
  its escalation to `Power` (Auto mode-selection, below).
- When the required current exceeds the [escalated maximum permitted
  rate](system-overview.md#ubiquitous-language) even so — regardless of
  profile — the System delivers the maximum permitted rate and notifies the user that the
  deadline is unreachable (R5). The notification fires on the same terms while a missed-deadline hold
  is in effect (above), where no required current is computed and the deadline is unreachable by
  definition.

**Realizes:** the *effective peak limit* glossary term · **Supports:** R3, R5, C3 ·
**Consumed by:** `control-cycle.md`, UC03, UC04, UC05.

---

## Auto mode-selection (R16)

Under the [`Auto` profile](system-overview.md#ubiquitous-language), resolves which
[mode](system-overview.md#ubiquitous-language) is active from observable conditions. Priority
order below; the first matching row wins and is re-evaluated every control cycle, which is how
escalation and revert happen automatically. The *Solar session*, *Overnight top-up*, and
*Fallback* rows are collectively the **baseline rows** — the ones that select a mode absent any
deadline escalation; the mode they resolve is the [baseline
mode](system-overview.md#ubiquitous-language) the required-current rule's handback test compares
against, and the mode this row reverts to.

| Priority | Row | Condition | Active mode |
| --- | --- | --- | --- |
| 1 | *Target met* | State of charge is at or above the active SOC limit (nothing to charge) | `Off` |
| 2 | *Deadline urgency* | Deadline urgency is in effect (the required-current rule's slack test has engaged it and its handback test has not yet cleared it — or a [missed-deadline hold](system-overview.md#ubiquitous-language) is in effect, which pins urgency on regardless, R5) | `Captar` (`Auto`'s second urgency lever, alongside the effective-peak-limit raise, above — high tariff and `Captar`'s own maximum-current request); `Power` instead when the CapTar capability is absent (R18, see below) |
| 3 | *Solar session* | The solar capability is present (R18), the sun is up, and solar surplus is sufficient to start a solar session (per UC01) | `Solar` (solar-first, grid fallback allowed) |
| 4 | *Overnight top-up* | The sun is down, the low-tariff flag is active (always the case on a single-tariff installation — see the glossary), and `Auto`'s own solar-reserve conditions (R9: home-day flag set, next-day forecast above threshold, no departure deadline resolved for tomorrow, and no missed-deadline hold in effect) do not hold | `Captar` (cost-efficient overnight grid top-up — the tariff preference and the reserve decision both belong to this selection, not to `Captar` mode itself, R4) |
| 5 | *Fallback* | Otherwise | `Off` |

- **The *Solar session* row's "sufficient to start" is the raw eligibility condition, not
  UC01's internal timing.** It means smoothed solar surplus is at or above the solar start threshold — the same condition
  that gates `Idle → Charging` in UC01/UC02 — regardless of whether UC01/UC02's own restart
  debounce (R11) is currently being waited out inside that mode. `Auto` does not deselect `Solar`
  merely because its internal debounce is pending; deselecting on every debounce would reset the
  mode-switch timers (`control-cycle.md`) and could prevent the debounce from ever completing.
- **The *Target met* row compares against the *resolved* active SOC limit.** During a solar session the solar
  step-up (R8) keeps the limit ahead of the rising state of charge, so that row does not prematurely
  stop solar storage. When the target is already met with no step-up in effect, it resolves to
  `Off` by design: a step-up extends an active solar session, it does not restart a completed one
  (R7/R8).
- **Escalation (Solar→Captar):** when *Deadline urgency* begins to hold during a solar session, Auto
  switches to `Captar` so the deadline can be met from the grid — emits
  `DeadlineUrgencyEngaged` (see UC05). The switch selects the mode; it does not clear a
  rapid-cycling cooldown already running from an earlier stop, which keeps blocking the restart
  until it elapses (R11, `control-cycle.md`) — a bounded delay to this lever, accepted so that a
  routine, system-initiated mode switch can never be a way around R11.
- **Revert:** when *Deadline urgency* stops holding — the handback test clears it, i.e. the
  [baseline mode](system-overview.md#ubiquitous-language) alone would now meet
  the deadline — the next cycle falls through to *Solar session* or *Overnight top-up*, returning
  to a solar mode (or `Off`) once grid charging for the deadline is no longer required (R16), and
  emits `DeadlineUrgencyReverted` (see UC05). Two properties of the required-current rule keep this
  stable rather than reverting the cycle after it engages: urgency latches, so the slack test is
  not re-asked once it has fired; and the handback compares against the non-escalated baseline
  rather than `Captar`'s own (already-maximum) desired current.
- **Reserve:** while `Auto`'s own solar-reserve conditions hold (R9), `Auto` both lowers the
  active SOC limit (R7's *Solar-reserve cap* row) *and* declines to match *Overnight top-up*, so it does not start baseline grid
  charging overnight either — two separate effects of the same `Auto` decision, not a rule that
  `Captar` itself enforces. Because two of those conditions are "no departure deadline resolved for
  tomorrow" and "no missed-deadline hold in effect," the reserve decision is mutually exclusive both
  with a deadline resolved for tomorrow and with one already missed today (R9, see UC05), so
  *Deadline urgency* never holds on either account while the cap is in force. A deadline resolved for *today* and still
  ahead of now is the one remaining case, which neither precondition speaks to.
- **Unavailable modes are skipped (R18).** When the solar capability is absent, *Solar session* never
  matches, so Auto falls through to `Captar`/`Off`. `Power` and `Off` are always available
  regardless of capabilities; `Captar` additionally requires the CapTar capability. When it is
  absent, *Overnight top-up* never matches — there is no deadline forcing a grid session,
  so Auto simply forgoes the opportunistic top-up and falls through to *Fallback* (`Off`), same as
  when the low-tariff flag itself does not hold. *Deadline urgency* is the one exception:
  see the `Power` carve-out below.
- **Deadline-urgency carve-out: `Auto` selects `Power` when `Captar` is unavailable (R5, R16,
  R18).** `SolarOnly` and `Power` are otherwise never Auto-selected — they are deliberate user
  intents (near-zero-grid and charge-now) that conflict with `Auto`'s cost/deadline balancing, so
  they are normally reachable only under the `Manual` profile. *Deadline urgency* is the sole exception: when
  deadline urgency holds and the CapTar capability is absent, `Auto` has no grid mode left that
  can request more than its baseline desired current, so it selects `Power` instead of falling
  through to `Off` — requesting the configured [Power target current](system-overview.md#ubiquitous-language)
  is a best-effort measure, not a guarantee: unlike `Captar`'s maximum-current request, it does
  not adapt to how urgent the deadline is and may still leave it unmet, in which case R5's
  unreachable-deadline notification still applies. Reverts the same way *Deadline urgency* always does, once
  urgency no longer holds.
- **Without the deadline capability, *Deadline urgency* never matches (R18).** No deadline is ever resolved, so
  no required current is computed and no missed-deadline hold can be in effect (it clears the moment
  the capability goes absent), and urgency cannot arise; Auto selection falls straight through
  to the baseline rows, and the `Power` carve-out above — which exists only for that row — is unreachable. This
  is independent of the CapTar capability: `Auto` simply never has a deadline to escalate for.
- **`Manual` needs no table:** under `Manual` the active mode is whatever the user or an
  external source sets directly (R16, NF1); this rule does not apply.

**Satisfies:** R16 · **Consumed by:** the `Auto` profile.

---

## Requirements satisfied

- **R5** — Departure deadline guarantee (the required-current computation above; the missed-deadline
  hold; the effective-peak-limit raise, `Auto`'s and `Manual`'s shared lever — a no-op when the
  CapTar capability is absent, leaving `Manual` with none, as the effective-peak-limit rule above
  records; Auto mode-selection's
  *Deadline urgency* row, `Auto`'s second lever; the deadline-unreachable notification). R15 (EV battery capacity) feeds
  the required-current computation as a configuration parameter, not a behaviour of its own — R18
  AC8's R15 clause follows directly: absent the deadline capability there is no required-current
  computation for it to feed, so it has no remaining effect.
- **R7** — Active SOC limit resolution.
- **R14** — Departure deadline resolution.
- **R16** — `Auto` profile mode-selection.

Partially satisfies [R18](requirements.md#r18--configurable-installation-capabilities) — the
`Auto`-selection half of AC2 (*Solar session* never matches while the solar capability is absent, so `Auto`
falls through to `Captar`/`Off`) and of AC5 (*Overnight top-up*'s opportunistic top-up never matches while the
CapTar capability is absent, and *Deadline urgency*'s escalation selects `Power` instead of `Captar`); and the
mode-selection portion of AC7 (no deadline is ever resolved and *Deadline urgency* never matches while the
deadline capability is absent, which is why the `Power` carve-out is unreachable) — the
input-suppression portion of AC7 is R14/[UC12](use-cases/UC12-configure-installation-through-guided-flow.md)'s,
and the notification-suppression portion is
[UC05](use-cases/UC05-guarantee-ready-by-departure.md)'s/[UC10](use-cases/UC10-remind-to-plug-in.md)'s.
The manual-selection half of AC2/AC5 (the mode selector's own option list) is
[UC11](use-cases/UC11-monitor-and-manage-charging-configuration.md)'s, not a resolution rule.
Also the R15 clause of AC8 (R15 has no remaining effect once the deadline capability is absent,
above) — the solar-reserve half of AC8 is
[UC07](use-cases/UC07-reserve-capacity-for-tomorrow.md)'s.

Also realizes the *effective peak limit* glossary term (supporting R3, R5, C3). NF1 holds
throughout: these are lookups the profile and coordinator consume, not mode logic. NF2 holds too:
neither urgency lever ever touches a mode's own logic — the peak-limit raise only widens an
existing clamp, and `Auto`'s mode-selection is already NF1's job, not the mode's.
