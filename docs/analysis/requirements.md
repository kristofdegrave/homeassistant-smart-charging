# Smart Charging v3 — Requirements

Requirements written fresh from the idea. Each requirement describes *what* the system must do — never *how*.

**Priority key:** Must = non-negotiable for launch / Should = important but not blocking / Could = nice to have / Won't = explicitly out of scope for this version

---

## Functional requirements

### R1 — Solar-first charging

**Priority:** Must
**What:** When `Solar` mode is active and surplus solar power is available, the system charges the car from that surplus and prefers solar over grid power at all times.

**Acceptance criteria:**

- [ ] Charging starts within one control cycle once smoothed solar surplus reaches at least a configurable threshold (default 150 W) and no stop or cooldown condition applies — immediately, except when a threshold crossing while waiting in `Idle` is subject to the restart debounce (R11).
- [ ] While surplus sustains at least the minimum charging current, the charger current is set by rounding up to the next whole ampere (amp-step rounding, round up — fixed for this mode, not configurable), so all available solar surplus is used and a bounded net grid import (less than one amp-step) fills the gap.
- [ ] When smoothed surplus is at or above the start threshold but below the minimum charging current, the charger holds at the minimum charging current and draws the shortfall from the grid (grid fallback), accepting a positive net import.
- [ ] When smoothed surplus falls below the start threshold (default 150 W), the charger holds at the minimum charging current for a configurable period (default 5 minutes) before stopping, riding out brief cloud cover.
- [ ] Outside grid fallback and the post-surplus hold, net grid import while charging in this mode stays bounded to less than one amp-step (the amp-step rounding gap), except for single-cycle sensor-noise transients.

---

### R2 — Solar-only charging

**Priority:** Must
**What:** When `SolarOnly` mode is active, the system charges the car from solar surplus and never draws supplementary power from the grid, save for a brief, bounded hold at the minimum charging current to ride out a passing cloud rather than stopping outright.

**Acceptance criteria:**

- [ ] Charging starts within one control cycle once smoothed solar surplus reaches at least a configurable threshold (default 1300 W, chosen so the minimum charging current can be met from solar alone) and no stop or cooldown condition applies — immediately, except when a threshold crossing while waiting in `Idle` is subject to the restart debounce (R11).
- [ ] The whole-ampere set-point is computed using a configurable amp-step rounding strategy: `round down` (default — the highest whole ampere that keeps net grid import at or below 0 W, no grid import), `round up` (the next whole ampere, accepting a bounded net grid import of less than one amp-step to use all surplus), or `round to nearest` (whichever whole ampere is closer to the ideal value, using a configurable midpoint, default 50 %, which may oscillate between the two amp steps when surplus hovers at the midpoint).
- [ ] When smoothed solar surplus falls below the start threshold (default 1300 W), the charger holds at the minimum charging current for a configurable period (default 1 minute) before stopping, riding out brief cloud cover; if surplus recovers to the start threshold within that period, charging resumes at the recovered rate and the hold is cancelled.
- [ ] This hold is the one exception to this mode's zero-grid-import guarantee: while holding, any shortfall between available solar and the minimum charging current is drawn from the grid, bounded to the hold period. If surplus has not recovered to the start threshold once the hold elapses, the charger stops (0 A) and the solar-mode cooldown begins (R11).
- [ ] Outside the hold, under the default `round down` strategy, the car is never charged from the grid while in this mode; net grid import attributable to charging never exceeds 0 W beyond one control cycle of sensor noise. Under `round up` or `round to nearest`, net grid import attributable to charging stays bounded to less than one amp-step.

---

### R3 — CapTar peak protection

**Priority:** Must
**What:** The system limits charging so that charging never raises the monthly grid peak above the effective peak limit, keeping a configurable safety margin (default 250 W) below it.

**Acceptance criteria:**

- [ ] In every control cycle, the chosen charger current keeps net grid import at or below the effective peak limit minus the safety margin.
- [ ] This check uses the most recent raw (unsmoothed) sensor readings so that a breach cannot persist for the duration of a smoothing window.
- [ ] When net import would exceed the effective peak limit minus the safety margin, the charger current is first reduced — within the same control cycle — to the highest whole ampere that keeps net import at or below that target.
- [ ] The charger stops (0 A) only when it is already at the minimum charging current and net import still exceeds the effective peak limit minus the safety margin continuously for a configurable grace period (default 2 minutes); a momentary breach does not stop charging.
- [ ] The charger may use all headroom up to the effective peak limit minus the safety margin, including capacity freed when other household appliances switch off.
- [ ] The effective peak limit's monthly-peak-demand operand never falls below a configurable peak floor (default 2.5 kW), and the floor never raises the effective peak limit above the configured maximum peak.

---

### R4 — Captar mode grid charging

**Priority:** Must
**What:** When `Captar` mode is active, the system charges the car from the grid up to the effective peak limit whenever the car is connected below the active SOC limit — charging as fast as the grid safely allows, independent of tariff and of why the active SOC limit is set where it is (e.g. a solar-reserve cap `Auto` may have applied — R9). Preferring low-tariff timing and reserving capacity for solar are concerns of the `Auto` profile's mode selection and SOC-limit coordination (R16), not of `Captar` mode itself; deadline urgency can supersede this behaviour (see R5). Unlike `Power` mode (R17), which also ignores tariff but charges at a user-chosen target current instead of always the maximum, `Captar` always defers to solar surplus first and never breaches the CapTar peak limit (R3) — `Power` may optionally skip that peak protection too.

**Acceptance criteria:**

- [ ] While `Captar` mode is active, the car is connected below the (currently resolved) active SOC limit, and no `Captar` cooldown is in effect, grid charging is permitted up to the effective peak limit minus the safety margin.
- [ ] `Captar` mode's charging behaviour does not depend on the low-tariff flag, nor on why the active SOC limit is set where it is — it simply charges to whichever active SOC limit is currently resolved (R7).
- [ ] Any solar surplus is netted off first and self-consumed; the grid supplies only the remainder needed to reach the requested current.
- [ ] Unlike `Power` mode, `Captar` never disables the CapTar peak-protection clamp (R3) — net import always stays at or below the effective peak limit minus the safety margin.
- [ ] When no condition above permits charging (state of charge at or above the active SOC limit, or a cooldown is in effect), the charger defaults to 0 A.

---

### R5 — Departure deadline guarantee

**Priority:** Must
**What:** As a cross-cutting override above the active mode's normal cost policy (e.g. the R3 peak clamp a `Captar` session otherwise respects), when the car would otherwise not reach its active SOC limit by the configured departure time, the system relaxes that restriction by raising the peak it is willing to create — and, only under the `Auto` profile, by additionally escalating current draw to the maximum charging current. High-tariff charging is accepted throughout. Because a departure time is a target rather than a cutoff, this does not stop the moment a deadline is missed: it continues until the car's state of charge reaches the active SOC limit, the car is disconnected, or the deadline capability is withdrawn (R18). Applies only while the deadline capability is present (R18).

**Acceptance criteria:**

- [ ] This requirement applies only while the deadline capability is present (R18). When it is absent, no deadline urgency ever arises: the effective peak limit is never raised, `Auto` never escalates for a deadline, and no unreachable-deadline notification is ever sent — every criterion below is vacuous.
- [ ] When the projected charge at the current rate would fall short of the active SOC limit by departure time, the system raises the effective peak limit it is willing to create, up to the configured maximum peak (default 4 kW) — accepting a higher monthly peak demand. This is the only lever available under the `Manual` profile: it never raises what the active mode itself requests, so meeting the deadline depends on whether that mode's own request, once unclamped, is enough.
- [ ] Under the `Auto` profile only, and when the CapTar capability is present (R18), the system additionally escalates current draw to the maximum charging current for as long as the deadline is at risk, reverting once it is no longer needed. When the CapTar capability is absent, `Auto` instead escalates to the `Power` mode's configured target current (R17) — a best-effort measure, not a guarantee, since it does not adapt to how urgent the deadline is; if that is still insufficient, the unreachable-deadline notification below applies.
- [ ] High-tariff charging is permitted while meeting a deadline — this is R5's primary purpose: cost optimisation yields to the deadline.
- [ ] The safety margin is always respected: net import stays at or below the effective peak limit in force minus the safety margin, even while meeting a deadline.
- [ ] The active SOC limit itself is never raised by deadline urgency's own levers (the peak-limit raise and `Auto`'s mode escalation) — when a lower limit is in force (e.g. a solar step-up not yet reset), the system only accelerates toward that lower limit. Separately, and by R9's own priority rule rather than by these levers, a departure deadline resolved for the next day and a missed-deadline hold (below) are each a precondition against the solar-reserve cap, so the cap is never in force alongside deadline urgency; when either arises while the cap was active, the cap lifts and the active SOC limit resolves without it — which may raise it (R7, R9).
- [ ] When even charging at the maximum permitted rate cannot meet the deadline, the system charges at that maximum and sends the user a notification that the deadline is unreachable.
- [ ] A single notification is sent per **occasion** on which the deadline is unreachable — an occasion being an unbroken spell in which it stays unreachable — and no further notification is sent for as long as that occasion lasts, however many control cycles it spans.
- [ ] No further notification is sent for the same occasion unless the condition clears in between and the deadline later becomes unreachable again. The notification re-arms the moment the condition clears — the required current falls back within the maximum permitted rate, the car is disconnected, the resolved deadline becomes "no deadline" (including the deadline capability becoming absent, R18), or a missed-deadline hold clears — so that later, distinct occasion sends a further notification within the same run of the system, without an intervening restart or reload. A control cycle on which state of charge is unavailable ends no occasion: no required current can be computed on it, so the system holds the notification state it already had and neither notifies nor re-arms.
- [ ] The deadline every criterion above is judged against is the next occurrence of the departure deadline (R14) — never an occurrence that has already passed today. A departure time earlier in the day than the current time therefore never engages urgency or the unreachable notification on that basis alone; it is judged as the next day's occurrence, with the full time remaining until then. The one exception is the missed-deadline hold below, which continues to pursue the occurrence that has just elapsed.
- [ ] **Missed-deadline hold.** When a resolved departure deadline elapses while the car is still connected below its active SOC limit and urgency was in effect on the preceding control cycle on that occurrence's own merits, urgency stays in effect — the deadline is unreachable by definition, so the system keeps charging as hard as the levers above allow — until state of charge is at or above the active SOC limit, the car is disconnected, the deadline capability becomes absent (R18), or, as a backstop, the following occurrence elapses in turn. A departure time is a *target*, not a cutoff: the driver may leave later than planned. While the hold is in effect the system computes no required current, so the deadline's resolution rolling forward to the next occurrence (R14) does not end it, nor does that next occurrence resolving to "no deadline" — the hold is anchored to the occurrence already missed.
- [ ] A car that connects only *after* a departure deadline has already elapsed, with urgency never having engaged for that occurrence, is never held: the deadline it is judged against is the next occurrence (R14) and it starts from normal operation. A hold is likewise not preserved across a restart spanning the moment the deadline elapsed.

---

### R6 — Configurable SOC limit

**Priority:** Must
**What:** The car is charged up to a configurable active SOC limit. The system keeps this limit synchronised with the vehicle's own charge-limit setting in both directions: it writes the active limit to the vehicle, and it adopts any limit the user sets directly on the vehicle as a manual change.

**Acceptance criteria:**

- [ ] The default SOC limit is user-configurable within a 50–100% range (default 80%).
- [ ] While the car is plugged in at home, the system writes the active SOC limit to the vehicle (when the vehicle exposes a settable charge limit) so it stops at that SOC independently of charger-current control.
- [ ] When the car is unplugged while at home, the system resets the vehicle's charge limit to the default SOC limit (default 80%).
- [ ] The vehicle's charge limit is never changed while the car is away from home (C2).
- [ ] A change to the vehicle's charge limit that the system did not initiate (e.g. set by the user in the car or its app) is adopted as a manual update to the default SOC limit, rather than being overwritten.
- [ ] Charging stops when the car reaches the active SOC limit.

---

### R7 — Active SOC limit resolution & lifecycle

**Priority:** Must
**What:** At any moment a single active SOC limit is in force, resolved from the configured default and any active modifiers; this requirement defines how it is resolved and when it resets.

**Acceptance criteria:**

- [ ] At any moment exactly one active SOC limit applies, resolved in priority order: the solar-reserve cap (R9) first, then any solar step-up (R8), otherwise the default SOC limit (R6).
- [ ] A solar step-up raises the active SOC limit only under the `Auto` profile, while charging in a solar mode (`Solar` or `SolarOnly`, R8); switching between those two preserves an in-effect step-up.
- [ ] When the active mode is no longer a solar mode, any solar step-up is cleared and the active SOC limit returns to the default limit.
- [ ] On disconnect, the active SOC limit resets to the default limit (any solar step-up is cleared).
- [ ] Charging does not resume above the active SOC limit until the limit changes or the car is unplugged and replugged.

---

### R8 — Solar SOC step-up

**Priority:** Should
**What:** While the `Auto` profile is active and charging in a solar mode, the system raises the active SOC limit in steps so that abundant free solar energy is stored rather than wasted. (Its scope and reset are governed by R7.) This is `Auto`'s own coordination decision (R16), like R9 — it does not apply under `Manual`, at least for now; a manually selected solar-mode session charges to whichever active SOC limit is currently resolved (R7) without stepping it up.

**Acceptance criteria:**

- [ ] The step-up activates only under the `Auto` profile.
- [ ] When solar charging is active under `Auto` and the car's SOC reaches within a configurable threshold (default 2 pp) of the active SOC limit, the limit rises by a configurable step (default 5 pp).
- [ ] The stepped-up limit never exceeds a user-configurable maximum (50–100%, default 100%); a step that would overshoot it clamps to the maximum.
- [ ] Under `Manual`, no step-up ever applies, regardless of which solar mode is selected or how close the SOC is to the active SOC limit.

---

### R9 — Solar-reserve overnight cap

**Priority:** Should
**What:** When the `Auto` profile is active and, for the next day, the home-day flag is set, the solar forecast is high enough, and no departure deadline is resolved for that day, `Auto` caps the overnight active SOC limit so the next day's solar energy can be used instead, and does not itself opportunistically top up from the grid overnight. A departure deadline resolved for the next day takes priority over the cap (R14), and so does a missed-deadline hold still in force from a deadline already elapsed (R5) — these two preconditions are what makes the cap and deadline urgency mutually exclusive. This is `Auto`'s own coordination decision (R16) — it does not apply under `Manual`, and it is not a rule the modes `Auto` selects (e.g. `Captar`, R4) enforce themselves; they simply charge to whichever active SOC limit is currently resolved (R7).

**Acceptance criteria:**

- [ ] The cap activates only under the `Auto` profile, and only when the home-day flag is set for tomorrow (R13), the next-day solar-forecast yield, read from a configured forecast sensor (NF3), exceeds a configurable threshold (default 12 kWh), and the departure-deadline resolution (R14), evaluated one day ahead, resolves to "no deadline" for tomorrow, and no missed-deadline hold (R5) is in effect — both deadline conditions being trivially satisfied while the deadline capability is absent (R18), since no deadline is ever resolved then and no hold can arise.
- [ ] While active, the overnight active SOC limit resolves to a configurable value (default 60%) while the sun is down (R7).
- [ ] While active, `Auto` does not select a mode for the sake of opportunistic overnight grid top-up (Auto mode-selection row 4, `resolution-rules.md`).
- [ ] Under `Manual`, this cap never applies, regardless of the home-day flag or forecast — the active SOC limit resolves as if `Auto` were not coordinating it at all.
- [ ] A departure deadline resolved for tomorrow (R14), or a missed-deadline hold in effect (R5), each takes priority over the cap: the cap does not activate, and if it was already active when either appears, it lifts on the next control cycle. These two preconditions are what "the cap and deadline urgency are mutually exclusive" means; a deadline resolved for *today* and still ahead of now is not excluded, since it is not competing for tomorrow's reserve.
- [ ] When the sun comes up, `Auto` is no longer active, a departure deadline becomes resolved for tomorrow, or a missed-deadline hold engages, the cap lifts and the active SOC limit resolves normally.

---

### R10 — Sensor smoothing

**Priority:** Must
**What:** The system bases charging-rate decisions on smoothed power readings so that momentary fluctuations do not cause the charging rate to change.

**Acceptance criteria:**

- [ ] Net grid power and solar power are each sampled once per control cycle, and the most recent *N* samples (configurable, default 4 — i.e. `N × control interval` in real time) are averaged before being used to set the charging rate.
- [ ] A power spike lasting a single control cycle does not change the charger set-point.
- [ ] A power change sustained across the full smoothing window changes the charger set-point within the following control cycle.
- [ ] Peak-protection decisions (R3) are exempt and use raw, unsmoothed readings.

---

### R11 — Rapid cycling prevention

**Priority:** Must
**What:** The system prevents the charger from starting and stopping in quick succession, and, for a mode's own ordinary stop conditions, from cutting current straight to 0 A the instant one first arises, so the car never enters a charging error state.

**Acceptance criteria:**

- [ ] For a mode's own stop condition (the post-surplus hold, R1/R2, when smoothed surplus falls below the solar start threshold; `Captar`'s own peak-breach grace period, R3), the charger holds at the minimum charging current for that mode-specific hold period before actually cutting to 0 A — a momentary or quickly-recovering condition is ridden out rather than triggering an immediate stop. This criterion is about *when a mode's own logic decides to stop*; it does not apply to the C4 grid-supply-ceiling clamp (a hard safety limit that cuts immediately) or to reaching the active SOC limit (an intentional stop, not a fluctuating condition).
- [ ] After charging stops, it does not restart until a mode-specific cooldown has fully elapsed (configurable; defaults: 2 minutes for solar modes, 10 minutes for `Captar`).
- [ ] A cooldown, once started, always runs to completion and is not shortened by a change in conditions.
- [ ] In `Solar` and `SolarOnly`, once the has-charged flag is set for the current connection, a start-threshold crossing (from below to at/above the threshold) while dwelling in `Idle` must hold continuously for a configurable restart debounce period (default 1 minute, shared by both modes) before charging actually starts — a single-cycle blip while waiting in `Idle` does not restart charging only to immediately need to stop again. This only gates a *crossing*: if the start threshold is already met at the moment the System enters `Idle` — whether `Idle` was reached because a cooldown elapsed or because the active SOC limit changed — there is no crossing to debounce and charging starts immediately, with no additional wait. Before the has-charged flag is first set — the connection's very first start — `Idle` starts charging as soon as the start threshold is met, with no debounce either. `Captar` and `Power` have no restart debounce, since their own start conditions do not depend on a fluctuating sensor reading.
- [ ] The has-charged flag is set the first time a solar mode actually starts charging on the current connection, and is cleared only on disconnect or a coordinator restart — not by a mode switch, a cooldown elapsing, or reaching the active SOC limit.
- [ ] The charger current is only ever 0 A or at least the minimum charging current, never in between (per C1).
- [ ] Switching the active mode resets all hold, cooldown, and restart-debounce timers so the incoming mode starts fresh; the has-charged flag is unaffected, since it is scoped to the connection, not the active mode.

---

### R12 — Plug-in reminder notification

**Priority:** Could
**What:** The system notifies the user to plug in the car when it is home, unplugged, and below the active SOC limit with limited time before departure. Applies only while the deadline capability is present (R18).

**Acceptance criteria:**

- [ ] A single notification is sent when the car is home, disconnected, below the active SOC limit, and within a configurable lead time (default 8 hours) of the next departure time (R14).
- [ ] No further reminder is sent for the same departure window unless the charger is connected and then disconnected again.
- [ ] No reminder is sent when the car is already connected or already at or above the active SOC limit.

---

### R13 — Home-day indication

**Priority:** Could
**What:** The system provides a way to indicate that the car will be home during the next day, so the solar-reserve cap (R9) and departure-time override (R14) can be planned — independent of the specific mechanism used to set it (e.g. a manual input, a notification prompt, or an external calendar/presence source, NF3).

**Acceptance criteria:**

- [ ] The home-day flag for tomorrow can be set through at least one configured mechanism, whether a system-provided input or an external source (NF3).
- [ ] When the home-day flag is set for tomorrow, it feeds the solar-reserve cap (R9) and — while the deadline capability is present (R18) — the departure-time override (R14).
- [ ] When no configured mechanism has set the flag, tomorrow is treated as not a home day.
- [ ] The home-day flag resets each day at midnight.

---

### R14 — Configurable departure times

**Priority:** Must
**What:** The system targets the next occurrence of the departure time, resolved from a per-day-of-week default, optional public-holiday and home-day overrides, or an external sensor. The resolution is per calendar date, and the deadline in force is the next occurrence still ahead of the current time — today's while it has not yet arrived, otherwise tomorrow's. Any of these may resolve to "no deadline". Applies only while the deadline capability is present (R18).

**Acceptance criteria:**

- [ ] When the deadline capability is absent (R18), none of the departure-time inputs below is offered or required to be configured, and no departure deadline is ever resolved — for today or for any day ahead. This is distinct from every day resolving to "no deadline": the configuration surface itself is not present.
- [ ] A default departure time is user-configurable for each day of the week (defaults: 06:00 Mon–Fri; no deadline Sat–Sun).
- [ ] Public-holiday and home-day (home-day flag, R13) departure times can each be configured and override the day-of-week default; both default to no deadline. If a day is both, the public-holiday override takes precedence.
- [ ] Public holidays are recognised from a configured source (e.g. a holiday calendar sensor, NF3).
- [ ] When an external departure-time sensor is configured (NF3), its value takes precedence over all configured values; it is read as a time-of-day and applied to whichever calendar date is being resolved.
- [ ] Any resolved departure time may be "no deadline", in which case that date imposes no deadline and R5 does not force charging.
- [ ] The departure time for a given calendar date is resolved in priority order — external sensor, then public-holiday / home-day override, then day-of-week default.
- [ ] The departure deadline in force is the next occurrence of that resolution still ahead of the current time: today's resolved departure time while it is strictly in the future, otherwise the same priority order re-evaluated for tomorrow's calendar date — re-evaluated, not today's time shifted by 24 hours, so a different day-of-week default, public-holiday status, or home-day flag for tomorrow is honoured. This resolved deadline feeds the deadline guarantee (R5) and plug-in reminder (R12).
- [ ] A departure time whose time-of-day has already passed today never yields a deadline in the past: at or after that moment the deadline resolves to tomorrow's occurrence, so the time remaining to the deadline is always positive and no deadline is reported unreachable (R5) purely because its time-of-day has passed. This resolution always rolls forward, with no exception — a deadline that elapses while the car is still short of its active SOC limit is handled by R5's missed-deadline hold, which changes what deadline urgency does with the resolution while the hold is in force, not the resolution itself.
- [ ] The lookahead extends one day only: when today's remaining occurrence and tomorrow's both resolve to "no deadline", no deadline applies — a departure time further out becomes the deadline only once the days roll over. One day covers both consumers: R5 concerns the deadline the current charging session must meet, and R12's lead time (default 8 hours) is assumed to be shorter than a day — a lead time configured at 24 hours or more is outside what this lookahead serves.
- [ ] The same per-date resolution, evaluated one day ahead (tomorrow's day-of-week, holiday status, and home-day flag), feeds one of the solar-reserve cap's two deadline preconditions (R9): a deadline resolved for tomorrow takes priority over the cap, as does a missed-deadline hold (R5, the cap's other deadline precondition, which this resolution does not feed). That precondition is always evaluated for tomorrow's calendar date, independently of which date the next-occurrence resolution above selects.

---

### R15 — Configurable EV battery capacity

**Priority:** Must
**What:** The car's usable battery capacity is configurable so charging-time estimates reflect the actual vehicle; it may alternatively be read from a sensor when one is available. The deadline calculation (R5) is its only consumer, so while the deadline capability is absent (R18) the capacity still resolves but affects no charging behaviour.

**Acceptance criteria:**

- [ ] The usable battery capacity is user-configurable in kWh (default 75 kWh).
- [ ] When a capacity sensor is configured (NF3), its value is used in preference to the configured number, falling back to the configured value if the sensor is unavailable.
- [ ] The effective capacity (sensed or configured) is used when calculating the energy and time needed to meet a departure deadline (R5).
- [ ] Changing the effective capacity changes the deadline calculation accordingly within the next control cycle.

---

### R16 — Auto profile

**Priority:** Must
**What:** The active [profile](system-overview.md#ubiquitous-language) is chosen by the user (`Manual` or `Auto`); under `Auto` the system selects the active mode over time from observable conditions, so the user need not switch modes by hand.

**Acceptance criteria:**

- [ ] The active profile is selected via a single profile selector; the built-in profiles are `Manual` and `Auto`. A profile sets the active mode and is not itself a mode.
- [ ] Under `Manual`: mode selection is a pass-through of the user's own selection (no automatic mode changes, NF1); SOC-limit coordination never engages — no solar step-up (R8), and the solar-reserve cap never applies, so the overnight active SOC limit is never capped (R9); no mode-escalation levers are available (the R5 peak-limit raise remains available, as it does under every profile).
- [ ] Under `Auto`, mode selection sets the active mode from observable conditions (time of day, low-tariff flag, solar availability and forecast, CapTar availability, SOC, departure deadline, home-day flag).
- [ ] Under `Auto`, mode selection chooses `Captar` for cost-efficient overnight grid top-up only while the low-tariff flag is active (Auto mode-selection row 4, `resolution-rules.md`); the low-tariff preference belongs to this selection, not to `Captar` mode itself (R4) — a manually selected `Captar` session charges regardless of tariff.
- [ ] Under `Auto`, SOC-limit coordination raises the active SOC limit via the solar step-up (R8) while charging in a solar mode, and, when its own solar-reserve conditions hold (R9), lowers the active SOC limit and declines to select a mode for opportunistic overnight top-up — coordinating the limit alongside the mode is `Auto`'s job, not a rule the selected mode enforces.
- [ ] Under `Auto`, mode selection never selects a mode that is unavailable given the installation's capabilities (R18).
- [ ] Under `Auto`, and while the deadline capability is present (R18), `Auto`'s mode-escalation levers switch from a solar mode to `Captar` when a departure deadline would otherwise be missed (R5), and revert to a solar mode once grid charging is no longer required. When the CapTar capability is absent, the levers escalate to `Power` instead (R18) — a deliberate, deadline-only exception to `Power` otherwise never being Auto-selected — and still revert once the deadline is no longer at risk.
- [ ] A change of profile, or an `Auto`-driven change of mode, takes effect within the next control cycle.

---

### R17 — Power mode

**Priority:** Should
**What:** When `Power` mode is active, the system charges at a user-configured [Power target current](system-overview.md#ubiquitous-language), ignoring solar surplus and tariff, for when the user wants direct control over the charging rate rather than the system's cost/solar optimisation.

**Acceptance criteria:**

- [ ] While `Power` mode is active, the charger current is set to the configurable Power target current (default 10 A, user-adjustable within the minimum–maximum charging current range), regardless of solar surplus or the low-tariff flag.
- [ ] A configurable option determines whether `Power` mode respects CapTar peak protection: when enabled (default), net import stays at or below the effective peak limit minus the safety margin (R3); when disabled, charging may breach the CapTar peak but is still bounded by the grid supply ceiling (C4).
- [ ] The charger current always obeys C1 (either 0 A or within the minimum–maximum charging range), regardless of the peak-protection option or the configured Power target current.
- [ ] The active SOC limit (R7) still applies; charging stops when it is reached.

---

### R18 — Configurable installation capabilities

**Priority:** Should
**What:** The available charging modes and the behaviours that depend on them adapt to the hardware, the billing arrangement, and the deadline policy the installation actually has, declared as configurable capabilities, so the system remains fully usable, under both `Manual` and `Auto`, on an installation without a solar array, without capacity-tariff billing, with no interest in departure deadlines at all, or with no wish to be contacted by notification at all. Without the solar capability alone, a grid mode (`Captar`) is still reachable under `Auto`, since the CapTar capability is unaffected. Without the CapTar capability, `Auto`'s deadline-urgency escalation (R5) falls back to `Power` instead of `Captar` (R16) — a deliberate, deadline-only exception to `Power` otherwise never being Auto-selected — while `Auto`'s opportunistic overnight top-up (R16 row 4) simply does not occur, since there is no deadline forcing it; this also applies when both capabilities are absent. The solar, CapTar, and deadline capabilities each default to *present*, because each records a fact about the installation that is already true of it; the requirements they gate — including the Must ones (R5, R14) — therefore hold in full on a default installation, save for the notifications that R5, R12, and R13 cannot deliver on one (below). The notifications capability is the one deliberate exception and defaults to *absent*: sending notifications is not an installation fact but a preference for the system to contact the household unprompted, something a household opts into rather than out of, so a household that never answers the question is left un-notified. Its only Must-requirement consequence is R5's unreachable-deadline notice; at Could level, R12's plug-in reminder and R13's evening home-day prompt are equally undelivered on a default installation. R5's charging levers (the peak-limit raise and `Auto`'s escalation) are unaffected, but a default installation has no notification target mapped, so none of those three notifications can be delivered until the household declares the capability present. Beyond that, a capability only ever subtracts behaviour the household has declared it does not have or does not want.

**Acceptance criteria:**

- [ ] The presence of a solar installation (the solar capability) is user-configurable, defaulting to present.
- [ ] When the solar capability is absent, the `Solar` and `SolarOnly` modes are not offered for manual selection and are never chosen by the `Auto` profile (R16); the `Captar` (subject to the CapTar capability), `Power`, and `Off` modes remain available.
- [ ] When the solar capability is absent, the solar SOC step-up (R8) and the solar-reserve overnight cap (R9) do not apply, and the solar-specific inputs (solar power, solar forecast) are not required to be configured.
- [ ] Whether the installation bills against a capacity tariff (the CapTar capability) is user-configurable, defaulting to present.
- [ ] When the CapTar capability is absent, the `Captar` mode is not offered for manual selection; the `Solar` (subject to the solar capability), `SolarOnly` (subject to the solar capability), `Power`, and `Off` modes remain available for manual selection. `Auto` never chooses `Captar` for opportunistic overnight top-up in this case (R16 row 4 simply does not occur), but does select `Power` — otherwise never an `Auto`-chosen mode — as a best-effort deadline-urgency escalation (R5, R16). The peak-protection clamp itself (R3) still **runs** whether this capability is present or absent — its runtime behaviour is not gated by the capability, subject only to R17's `Power`-mode peak-protection option, which can switch the clamp off in that mode — and a non-CapTar installation runs it on its default thresholds. What *is* gated is its configurability: the maximum peak, safety margin, peak floor, and peak-breach grace period, together with the `Power`-mode peak-protection option (R17), are presented by the installation flow (R20) only while the CapTar capability is present, so a non-CapTar installation has no way to tune them through the flow. This resolves the tension [UC12](use-cases/UC12-configure-installation-through-guided-flow.md)'s step model surfaced: these thresholds belong with the billing arrangement that motivates tuning them, while the protection of the grid connection that is genuinely ungated is the grid supply ceiling clamp (C4), whose fields the flow presents regardless of any capability declaration.
- [ ] Whether the household wants departure deadlines managed at all (the deadline capability) is user-configurable, defaulting to present.
- [ ] When the deadline capability is absent, the departure-time inputs (R14) and the plug-in reminder's lead time (R12) are neither offered nor required, no departure deadline is ever resolved, deadline urgency never engages and no unreachable-deadline notification is sent (R5), and no plug-in reminder is ever sent (R12). The charging modes offered for manual selection are unaffected — the deadline capability gates behaviour, not the mode menu. It does, however, make `Auto`'s deadline-only `Power` carve-out unreachable (R16), since that carve-out exists solely to serve a deadline.
- [ ] When the deadline capability is absent, both of the solar-reserve overnight cap's deadline preconditions (R9) — no departure deadline resolved for tomorrow, and no missed-deadline hold in effect — are always satisfied, so the cap depends only on its remaining conditions. The EV battery capacity (R15) still resolves as configured, but has no remaining effect on charging behaviour, since it feeds only the deadline calculation.
- [ ] Whether the household wants the system to send notifications at all (the notifications capability) is user-configurable, defaulting to **absent** — the one deliberate exception to the default-present convention above. The other three capabilities each record a fact about the installation that is already true of it, whereas sending notifications is a preference for the system to contact the household unprompted, something a household opts into rather than out of; a household that never answers the question is therefore left un-notified.
- [ ] When the notifications capability is absent, the notification configuration surface is neither offered nor required: the notification-target mapping, the evening home-day prompt's enable flag and time, and the prompt timeout (R20, [UC12](use-cases/UC12-configure-installation-through-guided-flow.md)). With no notification target mapped, the notifications themselves are undeliverable, not merely unconfigurable: R5's unreachable-deadline notice (Must), R12's plug-in reminder (Could), and R13's evening home-day prompt (Could) are not sent at all. No charging behaviour falls away with them — the capability gates no charging mode and no clamp, R5's charging levers (the peak-limit raise and `Auto`'s escalation) still apply, and the home-day flag's own mechanism (R13) still accepts its other configured inputs. The plug-in reminder's lead time (R12) stays a field of the deadline capability rather than of this one, but with no target mapped no reminder is sent whatever that lead time says.
- [ ] Changing a capability takes effect within the next control cycle.
- [ ] The capability model is extensible: additional hardware, billing, or policy capabilities (e.g. a home battery) can be added later, each gating the modes and behaviours that depend on it, without altering existing modes (NF2). Capabilities beyond solar, CapTar, deadline management, and notifications are out of scope this release.

---

### R19 — Runtime dashboard

**Priority:** Should
**What:** The system presents a dashboard for day-to-day use, showing current charging status and every [runtime configuration](system-overview.md#ubiquitous-language) input the household adjusts routinely (e.g. active profile, active mode, default SOC limit, departure times, home-day flag). [Install-time configuration](system-overview.md#ubiquitous-language) is set up once, through the integration's own [configuration flow](system-overview.md#ubiquitous-language) (R20), and is not part of this dashboard.

**Acceptance criteria:**

- [ ] The dashboard shows current charging status: charger status (connected/charging/disconnected), active profile, active mode, active SOC limit, and current charger current.
- [ ] The dashboard shows the current solar surplus and net import, so the household can see whether charging is currently drawing from solar or from the grid.
- [ ] Every entity classified as runtime configuration in `entity-catalog.md` (`config`-role, or a `state`-role entity the user sets directly, e.g. the active mode selector) is both visible and settable from the dashboard.
- [ ] A runtime entity gated by a capability that is absent (R18) is not shown at all — in particular, the departure-time rows are not shown when the deadline capability is absent, exactly as the solar-dependent runtime entities are not shown when the solar capability is absent.
- [ ] No entity classified as install-time configuration is presented on the dashboard; install-time configuration is reachable only through the integration's configuration flow.
- [ ] Adding a new entity to `entity-catalog.md` and classifying it as runtime requires no dashboard-specific logic change for it to appear.

---

### R20 — Guided installation configuration

**Priority:** Should
**What:** The system presents the installation's [configuration flow](system-overview.md#ubiquitous-language) as steps grouped by concern — one installation topic per step — showing only the capability-gated fields the declared [capabilities](system-overview.md#ubiquitous-language) (R18) call for, and validating each step before the next one is shown. That an installation's configuration is captured at all is required elsewhere — R18 (the capability declarations), R19 (install-time configuration is reachable only through this flow), and NF3 (every adapter-role mapping); R20 owns only the guided, step-grouped, step-validated *quality* of that flow.

**Acceptance criteria:**

- [ ] On first setup, the first step presents the installation's capability declarations — solar, CapTar, and deadline each defaulting to present, notifications defaulting to absent (R18) — so that which of the later steps apply is settled before any of them is shown; the mappings and thresholds every installation needs are grouped onto the always-shown topic steps that follow (the concrete grouping is stated in [UC12](use-cases/UC12-configure-installation-through-guided-flow.md)). Each amendment path (AC7) presents only its own half of that model, so neither necessarily opens on the capability declarations.
- [ ] On first setup, each capability declared present contributes exactly one further step of its own, presented in a fixed, documented order that is stable across sessions and installations (the concrete order is stated in [UC12](use-cases/UC12-configure-installation-through-guided-flow.md)); a capability declared absent contributes no step at all. On an amendment path (AC7) the same counting applies to that path's own half of the model only, so a step whose every field belongs to the other half is absent there whatever the declaration says.
- [ ] No field belonging to a capability declared absent is ever presented — in particular, no departure-time or reminder field when the deadline capability is absent (R14, R18), no solar field when the solar capability is absent, and no notification field when the notifications capability is absent (R18). An optional mapping that no capability gates — notably the vehicle's own settable charge limit (R6) — is instead presented on its always-shown topic step and may simply be left blank; declining it is a field-level choice on that step, not a separate declaration made earlier in the flow.
- [ ] A field that more than one capability depends on — the EV state-of-charge mapping, needed by both solar and CapTar — is presented exactly once, on its own always-shown topic step, and is presented there whatever the capability declarations, including when neither of those capabilities is declared present. No field is ever presented on two steps.
- [ ] Every ungated field the flow presents — for example the grid supply ceiling and grid safety offset (C4), which bound net import in every mode regardless of any capability declaration — appears in a step of its own concern, regardless of which capabilities are declared. This criterion governs *where* a presented ungated field appears, not which values are asked: a value the flow never presents on a given path and defaults instead (e.g. the control interval, asked only when amending thresholds and defaults) is outside its scope. One further exception is named deliberately in [UC12](use-cases/UC12-configure-installation-through-guided-flow.md): the external home-day flag mapping is ungated in itself — it also drives the solar-reserve cap (R9) — yet is presented only on the deadline-gated step, so a household that declares the deadline capability absent is never asked for it. That value is withheld rather than defaulted, and is the sole ungated field the flow places on a gated step.
- [ ] Every field is validated on the step that presents it: a value that does not fit the [adapter role](system-overview.md#ubiquitous-language) it maps (NF3), or a required field left blank, is reported on that step and the same step is re-shown; a requiredness that follows from a capability declaration is never reported only after the final step.
- [ ] The user can amend an existing installation's mappings and capability declarations without re-entering its thresholds and defaults, and amend its thresholds and defaults without re-entering its mappings; each path presents its own fields prefilled from the current configuration and leaves every value belonging to the *other* path unchanged. Within a path, a submitted answer may still change a value it did not itself present — in particular, declaring a previously present capability absent drops that capability's own mapping fields — but no value of the other path is ever touched.
- [ ] Abandoning the flow before its final step leaves the installation exactly as it was: nothing is created on first setup, and nothing is amended afterwards.
- [ ] A capability added in a later release (R18's extensibility clause) adds exactly one step of its own — appended after the existing capability-gated steps — without changing the fields or order of any existing step.

---

## Non-functional requirements

### NF1 — Coordinator executes modes; profiles select them

**Priority:** Must
**What:** The coordinator executes whichever charging mode is currently active and contains no logic for deciding which mode should be active. Choosing the mode is the responsibility of the active profile.

**Acceptance criteria:**

- [ ] The coordinator reads the active mode and dispatches to the matching mode module; it contains no rules that choose or change the active mode.
- [ ] The active mode is set either by the user / an external source (the `Manual` profile) or by the `Auto` profile (R16).
- [ ] Changing the active mode changes the coordinator's behaviour within the next control cycle.

---

### NF2 — One self-contained unit per mode and per profile

**Priority:** Must
**What:** Each charging mode — and each profile — is implemented in its own self-contained unit with no logic belonging to another.

**Acceptance criteria:**

- [ ] There is exactly one unit of logic per charging mode (`Solar`, `SolarOnly`, `Captar`, `Power`, `Off`) and one per profile (`Manual`, `Auto`).
- [ ] No mode's or profile's logic references or branches on another mode's or profile's internals.
- [ ] A mode or profile can be changed, replaced, or added one at a time without altering the others.

---

### NF3 — All device I/O via adapter roles

**Priority:** Must
**What:** All charging logic reads its inputs and issues its outputs through the integration's own internal adapter roles rather than raw device entities.

**Acceptance criteria:**

- [ ] Every sensor value used by the charging logic is read through an adapter role, not a raw upstream entity.
- [ ] Every command the logic issues — setting charger current, starting/stopping charging, writing the vehicle charge limit — is issued through an adapter role, not a raw device entity or service.
- [ ] No charging logic references a raw device or third-party integration entity directly, for input or output.
- [ ] Replacing the underlying charger or vehicle requires re-mapping only the affected adapter role, not changing the charging logic.

---

### NF4 — Voltage-aware power conversion

**Priority:** Should
**What:** The system converts between charging current and power using the measured supply voltage when a healthy reading is available, and falls back to a configurable nominal voltage when it is not.

**Acceptance criteria:**

- [ ] When a healthy supply-voltage reading is available, current↔power conversions use that measured value, taking effect within the next control cycle.
- [ ] When no healthy supply-voltage reading is available, conversions use a user-configurable nominal voltage (default 230 V).
- [ ] Current-derived thresholds (such as the minimum charging current and any threshold expressed in amperes) remain correct as the measured supply voltage varies.

---

## Constraints

These are hard rules that must never be violated, regardless of mode or circumstance.

| ID | Constraint |
| --- | --- |
| C1 | The charging current is always either 0 A or between the minimum and maximum charging current (reference setup: 6–32 A); values below the minimum charging current are never sent, as many vehicles/chargers fault on them. |
| C2 | The vehicle charge limit is changed only while the car is at home; no charge-limit change is made remotely. |
| C3 | Net grid import is never allowed to exceed the effective peak limit (which rises to the maximum peak only during deadline urgency), and charging targets a safety margin below it. This limit admits exactly one exception: `Power` mode with CapTar peak protection disabled (R17), which may breach the CapTar peak and is then bounded only by the grid supply ceiling (C4). It applies in every other mode, and in `Power` mode itself while that option is enabled (the default). |
| C4 | Net grid import (all household load plus charging) never exceeds the grid supply ceiling; the charger targets a configurable grid safety offset below the ceiling, checked against raw (unsmoothed) readings so a sudden swing cannot trip the main fuse before the next control cycle reacts. This hard limit applies in every mode, including `Power` mode with CapTar peak protection disabled (R17). |
