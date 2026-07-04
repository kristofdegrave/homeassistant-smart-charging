# Resolution rules

The shared, priority-ordered lookups that several use-cases and the
[coordinator](system-overview.md#ubiquitous-language) consume. They are collected here so no
use-case restates them: a use-case references a rule by name ("resolve the active SOC limit")
and this document is authoritative for the priority order and the requirement each rule
satisfies. These are **lookups, not mechanism** — the order of operations within a control
cycle lives in `control-cycle.md`; entity bindings live in `entity-catalog.md`.

Each rule is a decision table evaluated top-to-bottom: **the first row whose condition holds
wins.** Every rule is re-evaluated every control cycle, so a change in conditions changes the
result on the next cycle.

---

## Active SOC limit (R7)

Resolves the single [active SOC limit](system-overview.md#ubiquitous-language) in force at any
moment. Priority order: [solar-reserve cap](system-overview.md#ubiquitous-language) →
[solar step-up](system-overview.md#ubiquitous-language) → default.

| Priority | Condition | Active SOC limit |
| --- | --- | --- |
| 1 | The [home-day flag](system-overview.md#ubiquitous-language) is set, the [sun is down](system-overview.md#ubiquitous-language), and the next-day [solar forecast](system-overview.md#ubiquitous-language) exceeds its threshold (default 12 kWh) | The solar-reserve cap (default 60 %) |
| 2 | A solar step-up is in effect (a step has been applied while charging in a solar mode) | The stepped-up value, clamped to `sc_max_solar_soc` (default 100 %) |
| 3 | Otherwise | The default `input_number.sc_active_soc` (default 80 %) |

- **Lifecycle and reset are governed by R7** (and applied by UC06): a step-up survives a switch
  between `Solar` and `SolarOnly`, is cleared when the active mode is no longer a solar mode,
  and resets to the default on disconnect. This table resolves the *current* value only.
- Deadline urgency (R5) never raises the active SOC limit — it only accelerates toward
  whichever limit this table returns.
- Without the solar capability (R18), rows 1–2 are inert: no solar mode ever runs (so no
  step-up), and the solar-reserve inputs are not configured, so the table returns the default.

**Satisfies:** R7 · **Consumed by:** UC01, UC02, UC03, UC04, UC05, UC06, UC07, UC09, UC10.

---

## Departure deadline (R14)

Resolves the [departure deadline](system-overview.md#ubiquitous-language) for the current day.
Priority order: external sensor → public-holiday / home-day override → day-of-week default.
**Any row may resolve to "no deadline,"** in which case no deadline applies that day (R5 forces
no charging and R12 sends no reminder).

| Priority | Condition | Departure deadline |
| --- | --- | --- |
| 1 | An external departure-time sensor is configured (NF3) | The sensor's value (may be "no deadline") |
| 2 | Today is a recognised public holiday (from a configured holiday source, NF3) | The public-holiday override (default no deadline) |
| 3 | The home-day flag is set for today | The home-day override (default no deadline) |
| 4 | Otherwise | The day-of-week default (defaults: 06:00 Mon–Fri; no deadline Sat–Sun) |

- If a day is **both** a public holiday and a home day, row 2 wins (public-holiday precedence).
- The resolved value feeds the deadline guarantee (R5) and the plug-in reminder (R12).

**Satisfies:** R14 · **Consumed by:** UC05, UC10.

---

## Effective peak limit

Resolves the [effective peak limit](system-overview.md#ubiquitous-language) — the ceiling on
net import that charging must stay below. Priority order: deadline urgency raises the limit;
otherwise it is the lesser of the billed peak and the configured maximum.

| Priority | Condition | Effective peak limit |
| --- | --- | --- |
| 1 | Deadline [urgency](system-overview.md#ubiquitous-language) is in effect (R5) | The [maximum peak](system-overview.md#ubiquitous-language) (default 4 kW) |
| 2 | Otherwise (normal operation) | `min(`[monthly peak demand](system-overview.md#ubiquitous-language)`, maximum peak)` |

- This rule resolves the **ceiling** only. Urgency raises the ceiling to the maximum peak; it
  does not by itself raise the charger to that level. The actual current is the lowest rate that
  still meets the deadline (R5), clamped below the safety target — so the achieved monthly peak
  demand is only ever as high as the deadline math requires, never beyond the maximum peak.
- Charging always targets the [safety margin](system-overview.md#ubiquitous-language) *below*
  this limit (`effective peak limit − safety margin`); the margin is applied by the peak clamp
  in `control-cycle.md`, not by this rule.
- The limit never exceeds the maximum peak, even under urgency (C3).

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
| 2 | Deadline urgency is in effect: the car would miss the active SOC limit by the departure deadline at the current charger output (R5) | `Captar` (carries the R5 override — high tariff and the raised peak limit) |
| 3 | The solar capability is present (R18), the sun is up, and solar surplus is sufficient to start a solar session (per UC01) | `Solar` (solar-first, grid fallback allowed) |
| 4 | The sun is down, the low-tariff flag is active (always the case on a single-tariff installation — see the glossary), and the solar-reserve cap is not suppressing grid charging (R9) | `Captar` (cost-efficient overnight grid top-up — the tariff preference belongs to this selection, not to `Captar` mode itself, R4) |
| 5 | Otherwise | `Off` |

- **Row 1 compares against the *resolved* active SOC limit.** During a solar session the solar
  step-up (R8) keeps the limit ahead of the rising state of charge, so row 1 does not prematurely
  stop solar storage. When the target is already met with no step-up in effect, row 1 resolves to
  `Off` by design: a step-up extends an active solar session, it does not restart a completed one
  (R7/R8).
- **Escalation (Solar→Captar):** when row 2 begins to hold during a solar session, Auto
  switches to `Captar` so the deadline can be met from the grid.
- **Revert:** when row 2 stops holding, the next cycle falls through to row 3 or 4, returning to
  a solar mode (or `Off`) once grid charging for the deadline is no longer required (R16).
- **Suppression:** while the solar-reserve cap is active (R9), row 4 does not match, so Auto
  does not start baseline grid charging overnight (regardless of tariff); row 2 (urgency) can
  still escalate up to the cap.
- **Unavailable modes are skipped (R18).** When the solar capability is absent, row 3 never
  matches, so Auto falls through to `Captar`/`Off`; `Captar`, `Power`, and `Off` are always
  available regardless of capabilities.
- **`SolarOnly` and `Power` are never Auto-selected.** They are deliberate user intents —
  strictly-no-grid and charge-now — that conflict with Auto's cost/deadline balancing, so they
  are reachable only under the `Manual` profile.
- **`Manual` needs no table:** under `Manual` the active mode is whatever the user or an
  external source sets directly (R16, NF1); this rule does not apply.

**Satisfies:** R16 · **Consumed by:** the `Auto` profile.

---

## Requirements satisfied

- **R7** — Active SOC limit resolution.
- **R14** — Departure deadline resolution.
- **R16** — `Auto` profile mode-selection.

Also realizes the *effective peak limit* glossary term (supporting R3, R5, C3). NF1 holds
throughout: these are lookups the profile and coordinator consume, not mode logic.
