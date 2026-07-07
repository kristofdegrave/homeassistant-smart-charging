# UC07 — Reserve capacity for tomorrow's solar

**Primary actor:** Household energy manager

**Stakeholders & interests:**

- Household energy manager — wants tonight's overnight grid top-up skipped when tomorrow's solar
  can fill the battery instead, so solar self-consumption stays high and unnecessary grid cost
  (and CapTar exposure) is avoided.
- EV driver — still wants the car ready for a departure deadline even on a night the cap applies;
  accepts a lower overnight limit in exchange for it being refilled by solar the next day.

**Scope / level:** sea-level (a single `Auto`-profile coordination goal), realized entirely
through two existing resolution rules rather than a mode's own behaviour or a dedicated
coordinator step: the active-SOC-limit rule's row 1 (`resolution-rules.md`) and Auto
mode-selection's row 4 (`resolution-rules.md`). Neither lever touches
[UC01](UC01-charge-from-solar-surplus.md), [UC02](UC02-charge-from-solar-only.md), or
[UC03](UC03-charge-from-grid-within-captar-limit.md)'s own set-point logic (NF2) — whichever mode
`Auto` selects simply charges to whichever active SOC limit is currently resolved. This document
has no charging mode of its own.

## Preconditions

- The `Auto` profile is active.
- The [home-day flag](../system-overview.md#ubiquitous-language) is set for tomorrow — sourced
  from UC08's evening prompt or an external source (calendar, presence) per NF3.
- The next-day [solar forecast](../system-overview.md#ubiquitous-language) exceeds its configured
  threshold (default 12 kWh).

## Trigger

The [sun goes down](../system-overview.md#ubiquitous-language) while the preconditions above
hold — or, if the sun is already down, the moment the last of the three preconditions becomes
true.

## Main success scenario

1. **Given** the `Auto` profile is active, the home-day flag is set for tomorrow, and the
   next-day solar forecast exceeds its threshold.
2. **When** the sun is down, **then** the active-SOC-limit rule's row 1 (`resolution-rules.md`,
   R7) resolves the active SOC limit to the [solar-reserve cap](../system-overview.md#ubiquitous-language)
   (default 60%) instead of any solar step-up or the default limit.
3. **And** Auto mode-selection's row 4 (`resolution-rules.md`, R16) does not match, so `Auto` does
   not select a mode for the sake of opportunistic overnight grid top-up — the same `Auto`
   decision that lowered the limit in step 2 also withholds baseline overnight charging.
4. **And** the next morning, once the sun is up, the cap lifts (Postconditions) and the active SOC
   limit resolves normally again — so whichever solar mode `Auto` now selects charges from the
   reserved headroom up to that normal (uncapped) limit, which is the reserve's purpose: tonight's
   grid top-up was skipped so tomorrow's solar has genuine room to fill.

## Alternate flows

**1a — `Manual` profile is active** — branches from step 1.
Given the `Manual` profile is active, regardless of the home-day flag or the solar forecast
When a control cycle runs
Then the active-SOC-limit rule's row 1 never matches and Auto mode-selection does not run at all
(R16 does not apply under `Manual`) — the active SOC limit resolves as if this use-case were not
coordinating it, and the user's manually selected mode is never second-guessed.

**3a — A departure deadline is at risk while the cap is still active (sun still down)** —
branches from step 3.
Given deadline urgency (R5, [UC05](UC05-guarantee-ready-by-departure.md)) is in effect while the
cap is active
When a control cycle runs
Then Auto mode-selection's row 2 still escalates to `Captar` and the effective peak limit still
rises to the maximum peak (both per `resolution-rules.md`), so the car may still charge — but only
up to the capped active SOC limit from step 2, never beyond it, since deadline urgency never
raises the active SOC limit (R7). This differs from step 4: here the sun is still down and the cap
is still in force, so the ceiling the deadline may charge up to is the lower, capped value, not
the normal limit.

## Exception flows

None — resolving the active SOC limit to the solar-reserve cap and withholding baseline overnight
charging cannot themselves fail; the only way the goal is not achieved is a precondition not
holding, which is covered by 1a and the Postconditions reset.

## Postconditions

- While the cap is active, the active SOC limit in force is the solar-reserve cap (not the
  default or any solar step-up), and `Auto` has not started a mode for baseline overnight grid
  top-up.
- A departure deadline may still charge the car up to the capped limit (3a) but never beyond it.
- When the sun comes up, or the `Auto` profile is no longer active, the cap lifts on the next
  control cycle: the active-SOC-limit rule falls through to row 2 (solar step-up) or row 3
  (default), and Auto mode-selection is no longer withheld by row 4's reserve condition — the
  reserved headroom is then available for a solar mode to fill (step 4).

## State model

The reserve decision is itself a re-evaluated-every-cycle condition, not a value the System
stores between cycles (mirrors deadline urgency's Normal/Urgent pattern in
[UC05](UC05-guarantee-ready-by-departure.md)): each cycle the coordinator re-checks the profile,
the sun position, the home-day flag, and the forecast, so a change in any of them moves the System
directly between the two states below on the very next cycle.

- **Normal** — the active-SOC-limit rule's row 1 does not match; the limit resolves to a solar
  step-up or the default (R7), and Auto mode-selection's row 4 is free to select `Captar` for
  overnight top-up (R16).
- **Reserved** — the `Auto` profile is active, the sun is down, the home-day flag is set, and the
  forecast exceeds its threshold; the limit resolves to the solar-reserve cap (R7 row 1) and Auto
  mode-selection's row 4 is withheld (R16). Deadline urgency (3a) may still escalate `Captar`
  within this state, but never raises the limit.

| State | Active SOC limit | Leaves when |
| --- | --- | --- |
| Normal | Solar step-up or default (R7 rows 2–3) | `Auto` active, sun down, home-day flag set, forecast above threshold → Reserved |
| Reserved | Solar-reserve cap (R7 row 1) | `Auto` no longer active, sun up, home-day flag clear, or forecast at/below threshold → Normal |

## Domain events produced

These events mark the reserve decision's own transitions; there is no dedicated coordinator step,
since they correspond to the active-SOC-limit rule's row 1 and Auto mode-selection's row 4 in
`resolution-rules.md` switching in and out.

- `SolarReserveCapEngaged` — the sun is down and the home-day flag and solar-forecast preconditions
  hold: the active SOC limit resolves to the solar-reserve cap and `Auto` withholds baseline
  overnight grid top-up (Normal → Reserved).
- `SolarReserveCapLifted` — the sun comes up, the home-day flag is no longer set, the forecast no
  longer exceeds its threshold, or the `Auto` profile is no longer active: the active SOC limit
  resolves normally again and Auto mode-selection's row 4 is re-enabled (Reserved → Normal).

## Diagram

```mermaid
stateDiagram-v2
    [*] --> Normal
    Normal --> Reserved: Auto active, sun down,<br/>home-day flag set,<br/>forecast > threshold<br/>(SolarReserveCapEngaged)
    Reserved --> Normal: Auto inactive, sun up,<br/>home-day flag clear, or<br/>forecast ≤ threshold<br/>(SolarReserveCapLifted)
    note right of Reserved
        Active SOC limit = solar-reserve
        cap (R7 row 1). Auto mode-selection
        withholds row-4 overnight top-up
        (R16). Deadline urgency (3a) may
        still escalate Captar, but never
        raises the limit beyond the cap.
    end note
    note right of Normal
        Active SOC limit resolves to a
        solar step-up or the default
        (R7 rows 2-3). Row 4 is free to
        select Captar for overnight
        top-up (R16).
    end note
```

## Requirements satisfied

- **R9** — Solar-reserve overnight cap (the cap's activation conditions; resolving the active SOC
  limit to the solar-reserve cap while the sun is down; withholding `Auto`'s own opportunistic
  overnight grid top-up; inapplicability under `Manual`; the deadline exception that charges up to
  but never beyond the capped limit; and the reset when the sun rises or `Auto` is no longer
  active).

Inherited from the shared mechanism (referenced, not restated): the active-SOC-limit resolution
(R7, `resolution-rules.md`) and Auto mode-selection (R16, `resolution-rules.md`); the departure
deadline, required-current, and EV-battery-capacity computations that feed deadline urgency (R5,
R14, R15, `resolution-rules.md`); and the home-day flag itself, set by
[UC08](UC08-plan-tomorrow-home-day.md) or an external source (NF3).

## Relationships

- **Consumes the home-day flag set by [UC08](UC08-plan-tomorrow-home-day.md)** (the evening prompt)
  or an external source (calendar, presence) per NF3 — this use-case only reads the flag, it never
  sets it.
- **Constrains [UC05](UC05-guarantee-ready-by-departure.md)'s reach, and is in turn bounded by it.**
  A departure deadline may still escalate charging while the cap is active, but never raises the
  active SOC limit beyond the (capped) value (R7); see alternate flow 3a. Neither use-case
  restates the other's mechanism — they share the R7 active-SOC-limit resolution as their common
  ceiling.
- **Realized entirely by two existing resolution rules, not by a mode.** Whichever solar or
  overnight mode `Auto` selects — [UC01](UC01-charge-from-solar-surplus.md),
  [UC02](UC02-charge-from-solar-only.md), or [UC03](UC03-charge-from-grid-within-captar-limit.md) —
  simply charges to whichever active SOC limit is currently resolved (R7); none of them evaluate
  the home-day flag or solar forecast themselves.
- **Never applies under `Manual`** (1a) — mirrors R16's "no automatic changes under `Manual`": the
  user's own mode choice is not second-guessed by this policy.
