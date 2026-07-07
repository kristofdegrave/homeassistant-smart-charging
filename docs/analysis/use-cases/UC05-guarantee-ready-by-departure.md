# UC05 — Guarantee the car is ready by departure

**Primary actor:** EV driver

**Stakeholders & interests:**

- EV driver — wants confidence the car reaches its active SOC limit by departure even if that means charging at high tariff or a higher monthly peak, and an unmistakable warning on the rare occasion even that cannot save the deadline.
- Household energy manager — accepts that cost optimisation and peak protection step aside during urgency, but only as far as needed to meet the deadline, and never beyond the configured maximum peak.

**Scope / level:** sea-level, but cross-cutting — this is the `«extend»` use-case (UML terminology). It modifies [UC01](UC01-charge-from-solar-surplus.md) (`Solar`), [UC02](UC02-charge-from-solar-only.md) (`SolarOnly`), [UC03](UC03-charge-from-grid-within-captar-limit.md) (`Captar`), and [UC04](UC04-charge-at-a-user-set-current.md) (`Power`) rather than running as an independent charging session — it has no charging mode of its own.

## Preconditions

- One of UC01, UC02, UC03, or UC04 is the active mode's own use-case in progress: the car is connected at home ([charger status](../system-overview.md#ubiquitous-language) is `connected` or `charging`) and state of charge is below the [active SOC limit](../system-overview.md#ubiquitous-language) (resolved per `resolution-rules.md`).
- A [departure deadline](../system-overview.md#ubiquitous-language) is resolved for today — not "no deadline" (`resolution-rules.md`).

## Trigger

A [control cycle](../system-overview.md#ubiquitous-language) determines that, at the charger current the active mode has just requested for this cycle, the projected charge by the departure deadline would fall short of the active SOC limit — [deadline urgency](../system-overview.md#ubiquitous-language) (R5) — computed from the EV battery capacity (R15), current state of charge, the active SOC limit, and the time remaining until the deadline.

## Main success scenario

1. **Given** a departure deadline is resolved for today, the car is connected at home below the active SOC limit, and the active mode (UC01, UC02, UC03, or UC04) has computed its own desired current for this cycle.
2. **When** a control cycle determines that charging at that desired current from now until the departure deadline would not reach the active SOC limit, **then** the System is in deadline urgency (R5) and computes the lowest charger current that would close the gap in time, using the EV battery capacity, current state of charge, the active SOC limit, and the time remaining.
3. **And** the System raises the [effective peak limit](../system-overview.md#ubiquitous-language) ceiling to the [maximum peak](../system-overview.md#ubiquitous-language) (`resolution-rules.md`), which raises the [maximum permitted rate](../system-overview.md#ubiquitous-language) (R5) — the highest current deliverable this cycle once the coordinator's peak-protection clamp (`control-cycle.md`) has fitted it to the [peak headroom](../system-overview.md#ubiquitous-language) under that raised ceiling, further bounded by the [maximum charging current](../system-overview.md#ubiquitous-language) (C1) and the grid-supply-ceiling clamp (C4) — so peak protection cannot block the required current unless the required current itself exceeds this maximum permitted rate. (The one exception is `Power` mode with its own peak-protection option disabled — [UC04](UC04-charge-at-a-user-set-current.md) — where the peak clamp does not run at all this cycle, by that mode's own configuration rather than by this override, and the maximum permitted rate is bounded only by C1 and C4.)
4. **And**, whenever the active mode's own desired current is below the required current, the System raises the desired current toward the required current — permitting high-tariff charging — never above the maximum permitted rate, so the car reaches the active SOC limit by the deadline whenever the required current is at or below the maximum permitted rate.

## Alternate flows

**4a — Auto profile realises the override by mode escalation** — branches from step 4.
Given the `Auto` profile is active and deadline urgency (step 2) holds
When the next control cycle runs
Then Auto mode-selection (`resolution-rules.md`, row 2) switches the active mode to `Captar`, whose own set-point rule always requests the maximum charging current ([UC03](UC03-charge-from-grid-within-captar-limit.md)); the coordinator's peak clamp fits that request to the maximum permitted rate under the raised ceiling (step 3). This reliably delivers at least the required current whenever the required current is at or below the maximum permitted rate — but because `Captar` always requests the maximum current rather than exactly the required current, this realization does not minimise the achieved peak to the lowest rate that closes the gap the way the direct override (4b) does; `Auto` trades that cost-minimality for reusing `Captar`'s existing rule instead of computing a bespoke rate-limited escalation.

**4b — Manual profile realises the override in place** — branches from step 4.
Given the `Manual` profile is active and deadline urgency (step 2) holds
When a control cycle runs
Then the System overrides the currently active mode's own desired current in place, without changing which mode is active, setting it to exactly the required current whenever that is at or below the maximum permitted rate — the lowest rate that still closes the gap, as described in step 4.

## Exception flows

**The required current exceeds the maximum permitted rate.**
Given deadline urgency is in effect (step 2) and the required current computed there exceeds the maximum permitted rate (step 3) — even with the effective peak limit raised to the maximum peak
When the System applies the override (4a or 4b)
Then the System delivers the maximum permitted rate — bounded by C1 and C4, never bypassing the peak-protection clamp (C3) — and notifies the user that the departure deadline is unreachable at the current rate.

## Postconditions

- While deadline urgency holds, the delivered charger current is at least the active mode's own desired current and, whenever achievable, at least the required current computed for that cycle — bounded above by the maximum permitted rate (the peak clamp's output under the raised ceiling, itself bounded by C1 and C4); high-tariff charging is permitted for as long as urgency holds.
- The effective peak limit in force is the maximum peak while urgency holds (`resolution-rules.md`); net import still stays at or below that ceiling minus the safety margin (C3), and this override never bypasses the coordinator's peak-protection clamp (`control-cycle.md`), under either realization (4a/4b). The one exception is `Power` mode with its own peak-protection option disabled ([UC04](UC04-charge-at-a-user-set-current.md)), where that clamp does not run at all — by the mode's own configuration, not by this override — and only the grid-supply-ceiling clamp (C4) bounds delivery, as it would without urgency.
- The active SOC limit itself is never raised by this override (R7) — a lower limit already in force (e.g. the solar-reserve cap, R9) still bounds how far charging accelerates.
- When the required current exceeds the maximum permitted rate, the System delivers the maximum permitted rate and has sent the user a notification that the deadline is unreachable.
- Once deadline urgency no longer holds, the override lifts and the extended use-case's own cost policy governs the requested current again from the next control cycle.

## State model

Deadline urgency is itself a re-evaluated-every-cycle condition, not a value the System stores between cycles (mirrors the Auto mode-selection escalation/revert pattern in `resolution-rules.md`): each cycle the System recomputes the required current and the maximum permitted rate, so a change in conditions (SOC catching up, the deadline receding, the deadline resolving to "no deadline," or a sudden jump in the required current) can move the System directly between any two states on the very next cycle, without a dedicated timer. The three states below describe this observable behaviour; the `stateDiagram-v2` is authoritative for the state set and its transitions.

- **Normal** — the required current is at or below the active mode's own desired current; no override applies, and the effective peak limit resolves normally (`min(monthly peak demand, maximum peak)`).
- **Urgent** — the required current exceeds the active mode's own desired current but is at or below the maximum permitted rate; the override in step 4 applies and the effective peak limit is raised to the maximum peak. Under the direct override (4b, `Manual`), the delivered current is exactly the required current — the lowest rate that closes the gap. Under Auto's Captar escalation (4a), the delivered current is `Captar`'s own maximum-current request as clamped to the maximum permitted rate, which can exceed the required current.
- **Unreachable** — the required current exceeds the maximum permitted rate; the System delivers the maximum permitted rate and has notified the user.

A disconnect (charger status leaving `connected`/`charging`) breaks the "car connected" precondition and exits this use-case's scope from any state, returning to Normal on reconnect; the active SOC limit resets to the default at that point (R7), independently of this use-case. Reaching the active SOC limit, or the departure deadline resolving to "no deadline," also returns the System to Normal from any state, since urgency is only ever defined relative to a deadline that still applies.

| State | Delivered current | Leaves when |
| --- | --- | --- |
| Normal | Active mode's own desired current, unmodified | required current > active mode's desired current, ≤ maximum permitted rate → Urgent · required current > maximum permitted rate → Unreachable |
| Urgent | Required current (`Manual`, 4b) or `Captar`'s maximum-current request clamped to the maximum permitted rate (`Auto`, 4a) — either way ≤ maximum permitted rate; effective peak limit raised to the maximum peak | required current ≤ active mode's desired current → Normal (revert) · required current > maximum permitted rate → Unreachable |
| Unreachable | Maximum permitted rate; user notified | required current ≤ maximum permitted rate → Urgent · required current ≤ active mode's desired current → Normal |

## Domain events produced

- `DeadlineUrgencyEngaged` — the required current now exceeds the active mode's own desired current; the override (Urgent) takes effect (Normal → Urgent).
- `DeadlineUrgencyReverted` — the active mode's own desired current now meets or exceeds the required current; the override lifts (Urgent/Unreachable → Normal).
- `DeadlineUnreachableNotified` — the required current exceeds the maximum permitted rate; the System delivered the maximum permitted rate and notified the user (Normal/Urgent → Unreachable, or re-fires while remaining in Unreachable).

## Diagram

```mermaid
stateDiagram-v2
    [*] --> Normal
    Normal --> Urgent: required current > active mode's<br/>desired current, ≤ maximum permitted rate
    Normal --> Unreachable: required current ><br/>maximum permitted rate
    Urgent --> Normal: required current ≤ active mode's<br/>desired current (revert)
    Urgent --> Unreachable: required current ><br/>maximum permitted rate
    Unreachable --> Urgent: required current ≤<br/>maximum permitted rate
    Unreachable --> Normal: required current ≤ active mode's<br/>desired current
    note right of Urgent
        Effective peak limit raised to maximum
        peak (resolution-rules.md). Delivered
        current ≤ maximum permitted rate (the
        peak clamp's output under that ceiling,
        bounded by C1 and C4): exactly the
        required current under Manual (4b);
        Captar's own maximum-current request,
        clamped, under Auto (4a).
    end note
    note right of Unreachable
        Delivered current = maximum permitted
        rate; user notified the deadline is
        unreachable (DeadlineUnreachableNotified).
    end note
```

## Requirements satisfied

- **R5** — Departure deadline guarantee (urgency detection; current escalation to exactly the lowest sufficient rate under the direct-override realization (`Manual`, 4b); high-tariff permission; raising the effective peak limit up to the maximum peak; never raising the active SOC limit; and the deadline-unreachable notification, triggered against the maximum permitted rate).

Inherited from the shared mechanism (referenced, not restated): the departure-deadline resolution (R14) and the effective-peak-limit resolution (`resolution-rules.md`), the active-SOC-limit resolution (R7, which this use-case never raises), the peak-protection (R3, C3) and grid-supply-ceiling (C4) clamps (`control-cycle.md`), and the EV battery capacity configuration parameter (R15, `requirements.md`) that feeds the deadline calculation.

## Relationships

- **Extends [UC01](UC01-charge-from-solar-surplus.md), [UC02](UC02-charge-from-solar-only.md), [UC03](UC03-charge-from-grid-within-captar-limit.md), and [UC04](UC04-charge-at-a-user-set-current.md)** — each of those use-cases documents its own "Extended by UC05" relationship; this document is the single home for the urgency-escalation logic they all defer to, so it is never duplicated per mode.
- **Realised differently by profile, with different cost-minimality**: under `Manual`, by directly overriding the active mode's own desired current with exactly the required current — the lowest rate that closes the gap (this document, 4b). Under `Auto`, via the mode-selection escalation to `Captar` and its automatic revert (`resolution-rules.md`, Auto mode-selection rows 2–4); because `Captar`'s own set-point rule always requests the maximum charging current, this realization delivers up to the maximum permitted rate rather than the exact required current — a deliberate trade of cost-minimality for reusing `Captar`'s existing rule instead of a bespoke rate-limited mode. Both paths are bounded by the same maximum permitted rate (C1, C4, and the raised effective peak limit) and never raise the active SOC limit (R7).
- **Never raises the active SOC limit (R7)** — including a solar-reserve cap (R9) `Auto` may have applied; urgency only accelerates toward whichever limit is already resolved.
- Consumes the departure-deadline and effective-peak-limit rules in `resolution-rules.md`, and runs on the `control-cycle.md` coordinator spine (its override is applied to the desired current the dispatched mode module returns, before the peak-protection clamp).
