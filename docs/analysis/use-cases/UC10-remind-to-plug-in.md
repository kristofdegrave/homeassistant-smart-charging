# UC10 — Remind me to plug in

**Primary actor:** EV driver

**Stakeholders & interests:**

- EV driver — wants a timely nudge to plug in whenever the car is left unplugged and would otherwise miss its active SOC limit by departure, but no repeated pestering for a departure the driver has already been warned about.
- Household energy manager — indirectly benefits: a plugged-in car is a car [UC01](UC01-charge-from-solar-surplus.md)–[UC05](UC05-guarantee-ready-by-departure.md) can actually charge, so this reminder protects the deadline guarantee (R5) without this use-case doing any charging itself.

**Scope / level:** sea-level (single EV-driver goal): notify, don't charge. This use-case never sets the active mode or the charger current — it only observes whether the car is home, [charger status](../system-overview.md#ubiquitous-language), state of charge against the [active SOC limit](../system-overview.md#ubiquitous-language), and the next [departure deadline](../system-overview.md#ubiquitous-language) (R14), and sends a notification. Whichever charging use-case ends up running once the car is plugged in (UC01–UC05) is entirely independent of this one.

## Preconditions

- The car is home (`car_home`).
- [Charger status](../system-overview.md#ubiquitous-language) is `disconnected`.
- State of charge is below the [active SOC limit](../system-overview.md#ubiquitous-language) (resolved per `resolution-rules.md`, R7).
- The next departure time is resolved to an actual deadline, not "no deadline" (`resolution-rules.md`'s Departure deadline rule, R14 — which may fall on a later day than today, e.g. an evening reminder ahead of tomorrow's departure).

## Trigger

The current time enters the configurable lead time (`input_number.sc_reminder_lead_h`, default 8 hours) before the next departure time (R14), while every precondition above still holds — evaluated every control cycle.

## Main success scenario

1. **Given** the car is home, disconnected, below the active SOC limit, and the next departure time is resolved to an actual deadline.
2. **When** the current time comes within the configured lead time of that departure time, **then** the System sends a single notification asking the driver to plug in.
3. **And** no further reminder is sent for the same [departure window](../system-overview.md#ubiquitous-language) unless the charger is connected and then disconnected again (a connect/disconnect cycle re-arms the reminder).

## Alternate flows

**3a — Connect/disconnect cycle re-arms the reminder** — branches from step 3.
Given a reminder has already been sent for the current departure window
When charger status transitions from `disconnected` to `connected` and then back to `disconnected`
Then the System is ready to send a reminder again for that same window, subject to every precondition and the trigger still holding.

**3b — Next departure time changes** — branches from step 3.
Given a reminder has already been sent for the current departure window
When the next departure time passes (so a later day's resolved deadline becomes the next one) or the resolved deadline is otherwise updated (e.g. an external departure-time sensor changing)
Then the System is ready to send a reminder again for that new departure window, subject to every precondition and the trigger still holding — independently of whether a connect/disconnect cycle (3a) also occurred.

## Exception flows

**Car already connected.**
Given the car is home and within the lead time of the next departure time
When charger status is `connected` or `charging`
Then the System sends no reminder — the car is already in the state this reminder exists to prevent.

**State of charge already at or above the active SOC limit.**
Given the car is home, disconnected, and within the lead time of the next departure time
When state of charge is at or above the active SOC limit
Then the System sends no reminder — there is nothing left for the driver to plug in for.

**No upcoming departure deadline.**
Given the car is home, disconnected, and below the active SOC limit
When the next departure time resolves to "no deadline" for every day the resolution rule considers (`resolution-rules.md`, R14)
Then the System sends no reminder — there is no departure to be ready for.

## Postconditions

- The driver has been notified in time to plug in and let whichever charging use-case is active (UC01–UC05) reach the active SOC limit by the next departure time.
- No further reminder is sent for the same departure window unless the charger has since gone through a connect/disconnect cycle, or the departure window itself has changed (3b).
- No reminder is ever sent while the car is connected or already at or above the active SOC limit — the reminder tracks only the case where the driver still needs to act.

## State model

A light state model tracks only whether a reminder has already fired for the current departure window, so the System does not repeat itself every control cycle while the preconditions continue to hold. The two states below describe this de-dup behaviour; the `stateDiagram-v2` is authoritative for the state set and its transitions.

- **Armed** — no reminder has been sent for the current departure window; each control cycle, the System evaluates the preconditions and trigger and sends a reminder the moment they are all met.
- **Sent** — a reminder has been sent for the current departure window; the System sends no further reminder while in this state, even though the preconditions may continue to hold every cycle.

Transitions:

- Armed → Sent: the preconditions hold and the current time enters the lead time of the next departure time (the trigger fires).
- Sent → Armed (3a): charger status transitions from `disconnected` to `connected` and back to `disconnected` again (a connect/disconnect cycle), re-arming the reminder for the same departure window.
- Sent → Armed (3b): the departure window changes — the next departure time passes and a later day's resolved deadline becomes the next one, or the resolved deadline is otherwise updated — re-arming the reminder for the new window.

This state is scoped to the EV driver's plug-in decision only; it is unrelated to any charging use-case's own state (UC01–UC05), which starts fresh once the car is actually plugged in.

## Domain events produced

- `PlugInReminderSent` — the System sent the plug-in reminder (Armed → Sent).
- `PlugInReminderRearmed` — a connect/disconnect cycle (or a new departure window) reset the reminder so it can fire again (Sent → Armed).

## Diagram

```mermaid
stateDiagram-v2
    [*] --> Armed
    Armed --> Sent: preconditions hold AND<br/>within lead time of next departure time
    Sent --> Armed: connect, then disconnect again<br/>(same departure window, 3a)
    Sent --> Armed: departure window changes<br/>(next departure time passes or<br/>resolved deadline updated, 3b)
    note right of Sent
        No further reminder sent
        for this departure window.
        PlugInReminderSent fired
        on entry.
    end note
```

## Requirements satisfied

- **R12** — Plug-in reminder notification (all three acceptance criteria: the single notification within the configured lead time of the next departure time; the connect/disconnect de-dup rule for the same departure window; and no reminder while already connected or already at/above the active SOC limit).

Inherited from the shared mechanism (referenced, not restated): the departure-deadline resolution and its next-departure-time note (R14, `resolution-rules.md`), the active-SOC-limit resolution (R7, `resolution-rules.md`), and `charger status`'s canonical values (`system-overview.md`).

## Relationships

- **Independent of which charging use-case ends up running.** This use-case only ever notifies; it never sets the active mode or the charger current. Once the driver plugs in, whichever of UC01–UC05 the active profile and conditions select does the actual charging — this use-case has no opinion on which.
- Consumes the departure-deadline resolution rule (R14) shared with [UC05](UC05-guarantee-ready-by-departure.md) — both read the same resolved deadline, `resolution-rules.md`, but for different purposes (UC05 escalates charging; UC10 notifies the driver before the car is even plugged in).
- Consumes the active-SOC-limit resolution rule (R7, `resolution-rules.md`) to determine whether state of charge is still below the limit.
