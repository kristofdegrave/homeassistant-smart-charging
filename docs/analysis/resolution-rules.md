# Resolution rules

The shared, priority-ordered lookups that several use-cases and the
[coordinator](system-overview.md#ubiquitous-language) consume. They are collected here so no
use-case restates them: a use-case references a rule by name ("resolve the active SOC limit")
and this document is authoritative for the priority order and the requirement each rule
satisfies. These are **lookups, not mechanism** — the order of operations within a control
cycle lives in `control-cycle.md`; entity bindings live in `entity-catalog.md`.

Most rules below are decision tables evaluated top-to-bottom: **the first row whose condition
holds wins.** The required-current rule is a shared formula instead, since it has no priority
order to evaluate. Every rule is re-evaluated every control cycle, so a change in conditions
changes the result on the next cycle. Two of the inputs these rules read are not values observable
*this* cycle but flags the coordinator threads across cycles for the current connected session:
whether a [solar step-up](system-overview.md#ubiquitous-language) is in effect (R7/R8) and whether a
[missed-deadline hold](system-overview.md#ubiquitous-language) is in effect (R5). Both are called out
where the rule that reads them is defined.

---

## Active SOC limit (R7)

Resolves the single [active SOC limit](system-overview.md#ubiquitous-language) in force at any
moment. Priority order: [solar-reserve cap](system-overview.md#ubiquitous-language) →
[solar step-up](system-overview.md#ubiquitous-language) → default. Whichever mode is active simply
charges to this resolved value — it has no opinion on *why* the limit is where it is.

| Priority | Condition | Active SOC limit |
| --- | --- | --- |
| 1 | The `Auto` profile is active, the [home-day flag](system-overview.md#ubiquitous-language) is set, the [sun is down](system-overview.md#ubiquitous-language), the next-day [solar forecast](system-overview.md#ubiquitous-language) exceeds its threshold (default 12 kWh), the departure-deadline rule below, evaluated one day ahead, resolves to "no deadline" for tomorrow, and no [missed-deadline hold](system-overview.md#ubiquitous-language) is in effect (R5, below) | The solar-reserve cap (default 60 %) |
| 2 | A solar step-up is in effect (a step has been applied while the `Auto` profile is active and charging in a solar mode, R8) | The stepped-up value, clamped to `max_solar_soc` (default 100 %) |
| 3 | Otherwise | The default `number.smart_charging_soc_limit_override` (default 80 %) |

- **The solar-reserve cap is an `Auto`-only coordination decision (R9).** Reserving overnight
  capacity for tomorrow's solar is `Auto` weighing tonight's grid top-up against tomorrow's solar
  yield — an optimisation, not a hard constraint — so it applies only while `Auto` is the active
  profile. Under `Manual`, row 1 never matches regardless of the home-day flag or forecast: the
  user's own mode choice is not second-guessed by this policy (mirrors R16's "no automatic
  changes under `Manual`"). The mode `Auto` selects (typically `Captar`, row 4 below) does not
  itself evaluate the home-day flag or forecast; it only ever sees the resolved limit.
- **The solar step-up is also an `Auto`-only coordination decision (R8), like the reserve cap
  above.** Under `Manual`, row 2 never matches regardless of which solar mode is charging or how
  close the SOC is to the active SOC limit — a manually selected solar session simply charges to
  whichever limit row 3 resolves, with no automatic raise.
- **Lifecycle and reset are governed by R7** (and applied by UC06): a step-up survives a switch
  between `Solar` and `SolarOnly`, is cleared when the active mode is no longer a solar mode,
  and resets to the default on disconnect. This table resolves the *current* value only.
- Deadline urgency's own levers (R5 — the peak-limit raise and `Auto`'s mode escalation) never raise
  the active SOC limit; they only accelerate toward whichever limit this table returns. **Row 1 has
  two deadline preconditions, and the cap is mutually exclusive with each (R9):**
  - *A departure deadline resolved for tomorrow* — the deadline takes priority, so row 1 never
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
- Without the solar capability (R18), rows 1–2 are inert: no solar mode ever runs (so no
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
deadline urgency never engages and the effective-peak-limit rule never takes its urgency row (R5);
Auto mode-selection row 2 never matches (R16); the plug-in reminder never fires (R12); and the
solar-reserve cap's one-day-ahead "no deadline" precondition is always satisfied (R9).

| Priority | Condition (evaluated for the date being resolved) | Departure time for that date |
| --- | --- | --- |
| 1 | An external departure-time sensor is configured (NF3) | The sensor's current value, read as a time-of-day and applied to the date being resolved (may be "no deadline") |
| 2 | That date is a recognised public holiday (from a configured holiday source, NF3) | The public-holiday override (default no deadline) |
| 3 | The home-day flag applies to that date | The home-day override (default no deadline) |
| 4 | Otherwise | That date's day-of-week default (defaults: 06:00 Mon–Fri; no deadline Sat–Sun) |

- If a date is **both** a public holiday and a home day, row 2 wins (public-holiday precedence).

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
- Deadline urgency is in effect for as long as the required current exceeds the desired current
  of the **baseline mode** — the mode that would run absent any deadline-driven mode escalation:
  under `Manual`, the manually selected mode's own desired current (`Manual` never escalates the
  mode, so this is simply the active mode itself); under `Auto`, whichever mode Auto
  mode-selection's rows 3–5 (below) would select on their own. The baseline is evaluated fresh
  every cycle from rows 3–5 alone, so the comparison is unaffected by `Captar` already being
  dispatched from a prior escalation — comparing against `Captar`'s own (always-maximum) desired
  current instead would make urgency look satisfied the instant it engages, reverting and
  re-escalating every cycle.
- **Deadline urgency is additionally in effect, regardless of that comparison, for as long as a
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
   occurrence's *own* merits, i.e. because the required current exceeded the baseline mode's desired
   current, not because a previous hold was pinning urgency on.

While it holds, the deadline is **unreachable by definition** — time has run out on it — so urgency
is in effect and the System is pinned to `Unreachable`, with exactly that state's own behaviour: the
effective-peak-limit rule takes its urgency row, `Auto` mode-selection takes row 2, and delivery is
whatever those levers yield, bounded above by the [maximum permitted
rate](system-overview.md#ubiquitous-language). **No required current is computed while the hold is in
effect**, and the comparison against the baseline mode does not run, so the following occurrence's
longer time remaining cannot end the hold by making the deadline look comfortable again.

It **clears** when the car's state of charge is at or above the active SOC limit, when the car
disconnects, when the deadline capability becomes absent (R18), or — as a backstop — when the
*following* occurrence itself elapses, so a hold never outlives one deadline cycle. Nothing else the
departure-deadline rule resolves clears it: the hold is anchored to the occurrence already missed,
not to the next one, so it survives that next occurrence resolving to "no deadline" or to a different
time. From the cycle after it clears, the required current above governs normally again.

- **Evaluation order, so the hold and the cap above are not circular.** The hold is updated once per
  cycle, *after* the active SOC limit has been resolved for that cycle (so condition 1 reads the
  resolved value) and *before* the mode and peak decisions that consume urgency
  (`control-cycle.md`, step 4). Row 1 of the active-SOC-limit table therefore reads the hold as it
  stood entering the cycle: on the very cycle a hold engages the cap may still have been in force,
  and it lifts from the next cycle onward — the same one-cycle settling any other precondition
  lapsing has ([UC07](use-cases/UC07-reserve-capacity-for-tomorrow.md)).
- **A car that connects only after a deadline has already elapsed is never held.** Condition 2 fails
  — urgency never engaged for that occurrence — so a session begun at, say, 08:00 with a 06:00
  deadline behind it resolves forward to tomorrow's occurrence by the ordinary rule (R14) and starts
  from `Normal`, exactly as before.
- **The hold excludes the solar-reserve cap** (row 1 of the active-SOC-limit table above, R9): the
  cap would otherwise lower the active SOC limit out from under a session the driver is waiting on.
  The mirror-image consequence is deliberate and worth naming: if the cap *was* in force when the
  hold engages, the active SOC limit rises back to what it resolves to without the cap, extending the
  target the hold then pursues. That is R9's own priority rule doing what it already does when a
  deadline appears for tomorrow (R7/R9), not urgency's levers raising the limit — those never do
  (R5).
- **A baseline mode that requests little or no current still latches the hold.** Under `Manual` with
  `Off`, or a solar mode after dark, urgency can be in effect (any required current exceeds a 0 A
  baseline) while nothing is actually charging; the hold then engages and holds the effective peak
  limit at the maximum peak to no benefit, since `Manual` has no second lever
  ([UC05](use-cases/UC05-guarantee-ready-by-departure.md), 3b). The clear-at-the-following-occurrence
  backstop above bounds this rather than special-casing it: the user's own mode choice is not
  second-guessed (R16).
- **Not preserved across a restart.** Engagement is an edge — the moment a deadline elapses — so a
  restart spanning that moment leaves no hold, and the ordinary next-occurrence resolution governs.
  Deliberate: no analysis-layer state survives a restart (`entity-catalog.md`).

**Satisfies:** R5, R15 · **Consumed by:** the effective-peak-limit rule below, Auto mode-selection
below, the active-SOC-limit rule above (the cap's row-1 precondition), UC05, UC07.

---

## Effective peak limit

Resolves the [effective peak limit](system-overview.md#ubiquitous-language) — the ceiling on
net import that charging must stay below. Priority order: deadline urgency raises the limit;
otherwise it is the lesser of the billed peak and the configured maximum.

| Priority | Condition | Effective peak limit |
| --- | --- | --- |
| 1 | Deadline [urgency](system-overview.md#ubiquitous-language) is in effect (R5 — possible only while the [deadline capability](system-overview.md#ubiquitous-language) is present, R18) | The [maximum peak](system-overview.md#ubiquitous-language) (default 4 kW) |
| 2 | Otherwise (normal operation) | `min(max(`[monthly peak demand](system-overview.md#ubiquitous-language)`, `[peak floor](system-overview.md#ubiquitous-language)`), maximum peak)` |

- This rule resolves the **ceiling** only, and is the *entire* deadline-urgency response under
  `Manual`: raising the ceiling never itself raises what a mode requests, but a mode whose own
  request was previously clamped below the old ceiling (e.g. `Captar` or `Power`) can now draw
  more, up to whatever it already requests, C1, and C4 — bounded above by the [maximum permitted
  rate](system-overview.md#ubiquitous-language). A mode whose own request does not depend on
  peak headroom at all (e.g. `Solar`, `SolarOnly`) draws no differently, so meeting the deadline
  under `Manual` depends entirely on the active mode's own appetite for current, not on this
  rule alone. Under `Auto`, this same ceiling raise combines with a second lever — Auto
  mode-selection escalating to `Captar` when the CapTar capability is present, or to `Power` when
  it is absent (row 2, below, R18) — so `Auto` meets far more deadlines than `Manual` can.
  `Captar` always requests the maximum charging current, a guarantee; `Power` requests only its
  configured target current, a best-effort substitute when `Captar` is unavailable.
- Charging always targets the [safety margin](system-overview.md#ubiquitous-language) *below*
  this limit (`effective peak limit − safety margin`); the margin is applied by the peak clamp
  in `control-cycle.md`, not by this rule.
- The [peak floor](system-overview.md#ubiquitous-language) (row 2) exists so that a low or
  not-yet-established monthly peak demand — early in a billing month, or right after the
  monthly reset — does not itself resolve the effective peak limit down to near 0 kW and block
  `Captar`/`Power` charging; `max()` with the floor is applied before the `min()` with the
  maximum peak, so the floor can never raise the effective peak limit above the maximum peak.
- The limit never exceeds the maximum peak, even under urgency (C3).
- When the required current exceeds the maximum permitted rate even so — regardless of
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
escalation and revert happen automatically.

| Priority | Condition | Active mode |
| --- | --- | --- |
| 1 | State of charge is at or above the active SOC limit (nothing to charge) | `Off` |
| 2 | Deadline urgency is in effect (required current, above, exceeds the desired current of whichever mode rows 3–5 below would otherwise select — or a [missed-deadline hold](system-overview.md#ubiquitous-language) is in effect, which pins urgency on regardless, R5) | `Captar` (`Auto`'s second urgency lever, alongside the effective-peak-limit raise, above — high tariff and `Captar`'s own maximum-current request); `Power` instead when the CapTar capability is absent (R18, see below) |
| 3 | The solar capability is present (R18), the sun is up, and solar surplus is sufficient to start a solar session (per UC01) | `Solar` (solar-first, grid fallback allowed) |
| 4 | The sun is down, the low-tariff flag is active (always the case on a single-tariff installation — see the glossary), and `Auto`'s own solar-reserve conditions (R9: home-day flag set, next-day forecast above threshold, no departure deadline resolved for tomorrow, and no missed-deadline hold in effect) do not hold | `Captar` (cost-efficient overnight grid top-up — the tariff preference and the reserve decision both belong to this selection, not to `Captar` mode itself, R4) |
| 5 | Otherwise | `Off` |

- **Row 1 compares against the *resolved* active SOC limit.** During a solar session the solar
  step-up (R8) keeps the limit ahead of the rising state of charge, so row 1 does not prematurely
  stop solar storage. When the target is already met with no step-up in effect, row 1 resolves to
  `Off` by design: a step-up extends an active solar session, it does not restart a completed one
  (R7/R8).
- **Escalation (Solar→Captar):** when row 2 begins to hold during a solar session, Auto
  switches to `Captar` so the deadline can be met from the grid — emits
  `DeadlineUrgencyEngaged` (see UC05).
- **Revert:** when row 2 stops holding — i.e. the rows-3–5 baseline mode alone would now meet
  the deadline — the next cycle falls through to row 3 or 4, returning to a solar mode (or
  `Off`) once grid charging for the deadline is no longer required (R16), and emits
  `DeadlineUrgencyReverted` (see UC05). Because row 2 always compares the required current
  against that non-escalated baseline rather than `Captar`'s own (already-maximum) desired
  current, the decision is stable while genuinely needed rather than reverting the cycle after
  it engages.
- **Reserve:** while `Auto`'s own solar-reserve conditions hold (R9), `Auto` both lowers the
  active SOC limit (R7 row 1) *and* declines to match row 4, so it does not start baseline grid
  charging overnight either — two separate effects of the same `Auto` decision, not a rule that
  `Captar` itself enforces. Because two of those conditions are "no departure deadline resolved for
  tomorrow" and "no missed-deadline hold in effect," the reserve decision is mutually exclusive both
  with a deadline resolved for tomorrow and with one already missed today (R9, see UC05), so row 2
  never holds on either account while the cap is in force. A deadline resolved for *today* and still
  ahead of now is the one remaining case, which neither precondition speaks to.
- **Unavailable modes are skipped (R18).** When the solar capability is absent, row 3 never
  matches, so Auto falls through to `Captar`/`Off`. `Power` and `Off` are always available
  regardless of capabilities; `Captar` additionally requires the CapTar capability. When it is
  absent, row 4 (overnight top-up) never matches — there is no deadline forcing a grid session,
  so Auto simply forgoes the opportunistic top-up and falls through to row 5 (`Off`), same as
  when the low-tariff flag itself does not hold. Row 2 (deadline urgency) is the one exception:
  see the `Power` carve-out below.
- **Deadline-urgency carve-out: `Auto` selects `Power` when `Captar` is unavailable (R5, R16,
  R18).** `SolarOnly` and `Power` are otherwise never Auto-selected — they are deliberate user
  intents (near-zero-grid and charge-now) that conflict with `Auto`'s cost/deadline balancing, so
  they are normally reachable only under the `Manual` profile. Row 2 is the sole exception: when
  deadline urgency holds and the CapTar capability is absent, `Auto` has no grid mode left that
  can request more than its baseline desired current, so it selects `Power` instead of falling
  through to `Off` — requesting the configured [Power target current](system-overview.md#ubiquitous-language)
  is a best-effort measure, not a guarantee: unlike `Captar`'s maximum-current request, it does
  not adapt to how urgent the deadline is and may still leave it unmet, in which case R5's
  unreachable-deadline notification still applies. Reverts the same way row 2 always does, once
  urgency no longer holds.
- **Without the deadline capability, row 2 never matches (R18).** No deadline is ever resolved, so
  no required current is computed and no missed-deadline hold can be in effect (it clears the moment
  the capability goes absent), and urgency cannot arise; Auto selection falls straight through
  to rows 3–5, and the `Power` carve-out above — which exists only for row 2 — is unreachable. This
  is independent of the CapTar capability: `Auto` simply never has a deadline to escalate for.
- **`Manual` needs no table:** under `Manual` the active mode is whatever the user or an
  external source sets directly (R16, NF1); this rule does not apply.

**Satisfies:** R16 · **Consumed by:** the `Auto` profile.

---

## Requirements satisfied

- **R5** — Departure deadline guarantee (the required-current computation above; the missed-deadline
  hold; the effective-peak-limit raise, `Auto`'s and `Manual`'s shared lever; Auto mode-selection
  row 2, `Auto`'s second lever; the deadline-unreachable notification). R15 (EV battery capacity) feeds
  the required-current computation as a configuration parameter, not a behaviour of its own.
- **R7** — Active SOC limit resolution.
- **R14** — Departure deadline resolution.
- **R16** — `Auto` profile mode-selection.

Also realizes the *effective peak limit* glossary term (supporting R3, R5, C3). NF1 holds
throughout: these are lookups the profile and coordinator consume, not mode logic. NF2 holds too:
neither urgency lever ever touches a mode's own logic — the peak-limit raise only widens an
existing clamp, and `Auto`'s mode-selection is already NF1's job, not the mode's.
