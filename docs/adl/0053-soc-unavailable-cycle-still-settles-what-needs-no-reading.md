# ADR-0053: A state-of-charge-unavailable cycle still settles what needs no reading (narrows ADR-0042)

Date: 2026-09-27
Status: Accepted

## Summary

In the context of a control cycle on which state of charge is unavailable, facing an ADR-0042
that says such a cycle establishes nothing while R5 requires it to act on the clock and on the
pursued date's departure time, we decided to narrow ADR-0042 to what needs a reading,
so that the record and R5 agree on when the deadline events fire, accepting that the no-reading
path now has three outcomes it must declare established, and one it forgets fails silently.

## Context

- **R5 settles some outcomes without a reading.** On a cycle with no state of charge that does
  not [fault](../analysis/system-overview.md#ubiquitous-language),
  [`requirements.md`](../analysis/requirements.md) R5,
  [`resolution-rules.md`](../analysis/resolution-rules.md) and UC05's State model say the
  missed-deadline hold begins when the pursued occurrence elapses, its backstop ends it, and a
  pursued occurrence that has not yet elapsed follows its own date's departure time, and is
  released when that date resolves to "no deadline". Each fires the events any exit or entry
  fires. What needs a required current (the handback, and crossing between `Urgent` and
  `Unreachable`) waits for a reading, and a fault cycle decides nothing. On a no-reading cycle
  mid-hold, UC05's State model says no event fires, while the glossary and UC05's Domain events
  say the onset re-fires as a level signal; the human partner ruled for the level signal.
- **[ADR-0042](0042-soc-unavailable-cycle-holds-the-unreachable-clear.md) says otherwise.** Its
  Decision says that state of charge being unavailable "establishes nothing", and its exit
  table's row for that case says it fires nothing. Its mechanism is unaffected: the edge
  detector is told whether the cycle established an outcome, and holds its prior flag when it
  did not.
- **Two code tasks build to the rule.** One gives the no-reading path the "established"
  declaration ADR-0042 calls for. The other adds the release on the pursued date resolving to "no deadline". As
  written, ADR-0042 rejects both.
- **ADR-0042 is immutable** (ADR-0001), so its text cannot be corrected in place.

## Considered options

### Option A — Keep ADR-0042 and read "establishes nothing" as "nothing a reading settles"

- Pro: no record. ADR-0042's own sentence — the clear "fires only on a control cycle that
  established" the deadline is no longer unreachable — and its durable rule that the detector must
  be told which meaning a short-circuit carries both allow that reading.
- Con: ADR-0042 says "establishes nothing" and "fires nothing" in so many words. A reviewer
  holding either code task to it has to reject what R5 requires, and the reading that would stop
  them lives in no record.

### Option B — Narrow ADR-0042 to what needs a reading

Name the outcomes the clock and the pursued date's departure-deadline resolution settle, and
keep ADR-0042's rule for everything else.

- Pro: the record agrees with R5 and UC05, and both code tasks have one rule to build to.
- Pro: ADR-0042's mechanism survives unchanged. Only which cycles count as having established
  an outcome changes.
- Con: the no-reading path has three outcomes to declare established rather than none. A future
  edit that forgets one fails silently, as a missing notice or as a clear that never fires.
- Con: one rule is spread across ADR-0024, ADR-0042 and this record.

### Option C — Supersede ADR-0042 with one record that states the whole rule

- Pro: one record to read for when a no-reading cycle fires the deadline events.
- Con: ADR-0042's reasoning still holds: the outcome flag's two meanings, the further input that
  separates them, and its durable rule. A full supersede is for a decision whose reasoning has
  failed (the boundary ADR-0033 draws), and it would retire the record the code builds to.

### Option D — Bring R5 back to ADR-0042: a no-reading cycle decides nothing

- Pro: ADR-0042 stays true as written, and the no-reading path only ever holds.
- Con: it overturns R5's Must criteria. A hold would outlive its backstop for as long as the
  reading stays away, a missed deadline under `Power` or `Off` would go unnotified until the
  reading returns, and a changed departure time would be ignored. An ADR would be settling
  requirement-level behaviour against the analysis.

## Decision

**Option B.** Option A leaves a record that rejects what R5 requires (its Con). Option C
retires reasoning that still holds, and Option D overturns R5.

This narrows two clauses of ADR-0042. ADR-0042 stays `Accepted` and its text is untouched.

1. **Its Decision's "state of charge being unavailable establishes nothing"** now reads
   "establishes nothing that needs a reading".
2. **Its exit-table row for state of charge unavailable while the car stays connected** is
   replaced by these rows. They hold on a cycle that does not fault. A fault cycle still decides
   nothing, and an outcome settled during a fault lands on the first later cycle that
   does not fault.

| On a cycle with no reading | Outcome | Fires | Established |
| --- | --- | --- | --- |
| The pursued occurrence lies in the past: it elapsed, or its departure time moved to a moment already past | The missed-deadline hold begins, or continues while its backstop has not passed; `Unreachable` | `DeadlineUnreachableNotified`, the level signal, on every such cycle. A notice is sent only when the hold begins an occasion (R5) | Yes |
| A hold is in effect and its backstop passes | The hold ends; `Normal` | `DeadlineUnreachableCleared` + `DeadlineUrgencyReverted` | Yes |
| A pursued occurrence that has not yet elapsed has its own date resolve to "no deadline" | Released; `Normal` | `DeadlineUrgencyReverted`, and `DeadlineUnreachableCleared` from `Unreachable` | Yes |
| That occurrence's date resolves to a departure time still ahead | The occurrence moves, and the state is held | Nothing | No |
| Anything that needs a required current: the handback, a crossing between `Urgent` and `Unreachable`, state of charge reaching the active SOC limit | The state is held | Nothing | No |

The *Established* column is ADR-0042's further input to `DeadlineUnreachableEdge`. The detector
records the hold's `True`, fires the clear on the two releases when its prior flag was `True`,
and holds its prior flag on the other two rows. An exit that does not turn on state of charge,
such as the deadline capability becoming absent (R18), is not in the table and keeps the terms
R5 and UC05 give it.

Everything else in ADR-0042 stands, with "established" read as above: its disconnect row, the
reach of its fault-cycle hold rule, and its durable rule.

## Consequences

- **ADL:** ADR-0042's row is annotated in this record's PR.
- **Code:** the no-reading early return reports the deadline unreachable while the held
  occurrence lies in the past, so the fire site's level signal fires as on any cycle in a hold, and
  it declares the three rows marked *Established* as established. That
  belongs to the task building ADR-0042's detector input. The move and the release on the
  pursued date belong to the no-reading task of the slice that makes a pursued occurrence follow
  its own departure time; that task needs the first one's detector input.
- **Tests:** a no-reading cycle holding an occurrence already past now reports the deadline
  unreachable, so the unit test that pins `unreachable is False` for that case flips.
- **Design:** `system-design.md`'s ADR table gains a row for this record, and its ADR-0042 row
  stops saying such a cycle publishes no clear unconditionally.
- **Analysis:** within a hold, this record follows the glossary's rule that the onset
  re-fires on every cycle its condition holds; a no-reading cycle that holds `Unreachable` with no
  hold fires nothing (the table's last row). UC05's State model and diagram note say no event
  fires mid-hold, and only that clause is brought into line (a `uc` follow-up).
- **Harder:** one no-reading cycle can now fire `DeadlineUnreachableCleared` and
  `DeadlineUrgencyReverted` together, so a test of that path can no longer assert that no event
  fired.

**Blast radius.** Run from the repository root:

`rg -n 'DeadlineUnreachableEdge|_unreachable_edge|deadline_resolvable|EVENT_DEADLINE_UNREACHABLE_NOTIFIED|required\.unreachable|re-fires|ADR-0042|establish(es|ed)? nothing|ends no occasion|needs? no reading|needing no reading|with or without a (state-of-charge )?reading|never a state-of-charge reading' custom_components/ docs/ tests/ .claude/ .github/ CLAUDE.md`

— 247 hits, 45 of them in this record. It is wide enough because it is keyed on:
- the detector, by class and attribute, and the guard predicate whose early return this record
  rules on;
- the onset event's constant, the flag its fire site reads, and the prose stating that it
  re-fires, so every producer, consumer and test of the level signal is reached;
- every citation of the record it narrows;
- the prose the narrowed clause is stated in, and the prose R5 and UC05 state the carve-out in.

The dot-directories are named because a root sweep skips them. They return no hits.

| Site | Today | Follow-up |
| --- | --- | --- |
| `custom_components/smart_charging/coordinator_cycle.py:689` | The no-reading early return reports `unreachable=False` whatever the held occurrence, and neither follows nor releases it on its own date | Report the hold, and declare the three established rows (code) |
| `custom_components/smart_charging/coordinator_cycle.py:690`, `:696`, `:698` | Its comment: such a cycle "establishes nothing about the deadline" | Say what it still establishes (code) |
| `custom_components/smart_charging/coordinator_cycle.py:471` | `DeadlineUnreachableEdge.resolve` takes `unreachable` alone | Take the *Established* input (code) |
| `custom_components/smart_charging/coordinator.py:845` | Fires the clear off `unreachable` alone | Pass the *Established* fact in (code) |
| `tests/test_coordinator_cycle.py:1318`, `:1320`, `:1321`, `:1325`, `:1333`, `:1338` | Pins `unreachable is False` for a held occurrence an hour past, as "establishes nothing" | Assert the hold is reported (code) |
| `tests/test_coordinator.py:4677` | Its docstring: a no-reading cycle "establishes nothing about the deadline" | Say what it still establishes (code) |
| UC05, `docs/analysis/use-cases/UC05-guarantee-ready-by-departure.md:101`, `:175` | The `Unreachable` row and the state diagram's note: on a no-reading cycle mid-hold, no event fires | Say the onset re-fires while the hold continues (analysis) |
| `docs/design/system-design.md:872` | ADR-0042's row: such a cycle publishes no `DeadlineUnreachableCleared`, unqualified | Qualify it, and add this record's row (design) |

117 other hits conform:
- `coordinator.py`'s other 22: the detector's import and construction, the two fault returns
  that hold its flag, the guard's computation and its uses by the reserve gate,
  `is_soc_gated`'s citations of ADR-0042, and the onset's fire site, which fires on the flag
  and so re-fires through a no-reading hold once the early return reports it.
- `coordinator_cycle.py`'s other 6: a module docstring, `is_soc_gated`'s citation, a mention, the
  guard's field and docstring, and `urgent` read off the flag.
- `const.py`'s 2 and `notification_manager.py`'s 4: the onset's constant, and its consumer, which
  sends one notice per occasion however often the onset re-fires.
- `test_coordinator_cycle.py`'s other 26: the detector's own tests, and the guard's and the
  flag's other uses, including the disconnect release and the no-reading backstop release.
- `test_coordinator.py`'s other 13, `test_deadline_soc_management_end_to_end.py`'s 6,
  `test_init.py`'s 6 and `test_notification_manager.py`'s 15: the disconnect and capability
  exits, fault cycles holding the flag, the no-reading backstop release, no second notice for a
  no-reading cycle mid-hold, and the onset's listeners and consumer.
- The 11 in `requirements.md`, `resolution-rules.md`, `system-overview.md` and UC05's other
  lines, which state this rule, including the glossary's re-fire rule.
- `system-design.md:382` and `:859`: the level signal, and ADR-0024's row.
- The ADL's 3: ADR-0024's row, ADR-0042's row, which names this record, and this record's own row.
- `ai-authoring.md:119`, which cites ADR-0042's Context as an example of clutter.

Out of scope:
- `engines/deadline.py:319` and the four in `tests/engines/test_deadline.py` keep saying the
  detector "keys on that flag alone": a with-reading release, whose correction ADR-0042 already
  assigns.
- UC04's one keeps describing the active-SOC-limit stop, a different rule.
- ADR-0024's ten, ADR-0042's 24, and the one each in ADR-0016, ADR-0036 and ADR-0046, are
  immutable and keep stating their decisions; the ADL rows carry the narrowing.
- The 26 in `docs/plans/` record what was planned at their date.
- This record's own 45, which state the decision.
