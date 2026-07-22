# Smart Charging v3 — Requirements

Requirements written fresh from the idea. Each requirement describes *what* the system must do — never *how*.

**Priority key:** Must = non-negotiable for launch / Should = important but not blocking / Could = nice to have / Won't = explicitly out of scope for this version

---

## Functional requirements

### R1 — Solar-first charging

**Priority:** Must
**What:** When `Solar` mode is active and surplus solar power is available, the system charges the car from that surplus and prefers solar over grid power at all times.

**Acceptance criteria:**

- [ ] Charging starts within one control cycle once smoothed solar surplus reaches at least a configurable threshold (default 150 W) and no stop or cooldown condition applies.
- [ ] While surplus sustains at least the minimum charging current, the charger current is set by rounding up to the next whole ampere (amp-step rounding, round up — fixed for this mode, not configurable), so all available solar surplus is used and a bounded net grid import (less than one amp-step) fills the gap.
- [ ] When smoothed surplus is at or above the start threshold but below the minimum charging current, the charger holds at the minimum charging current and draws the shortfall from the grid (grid fallback), accepting a positive net import.
- [ ] When smoothed surplus falls below the start threshold (default 150 W), the charger holds at the minimum charging current for a configurable period (default 5 minutes) before stopping, riding out brief cloud cover.
- [ ] Outside grid fallback and the post-surplus hold, net grid import while charging in this mode stays bounded to less than one amp-step (the amp-step rounding gap), except for single-cycle sensor-noise transients.

---

### R2 — Solar-only charging

**Priority:** Must
**What:** When `SolarOnly` mode is active, the system charges the car exclusively from solar surplus and never draws supplementary power from the grid.

**Acceptance criteria:**

- [ ] Charging starts within one control cycle once smoothed solar surplus reaches at least a configurable threshold (default 1300 W, chosen so the minimum charging current can be met from solar alone) and no stop or cooldown condition applies.
- [ ] The whole-ampere set-point is computed using a configurable amp-step rounding strategy: `round down` (default — the highest whole ampere that keeps net grid import at or below 0 W, no grid import), `round up` (the next whole ampere, accepting a bounded net grid import of less than one amp-step to use all surplus), or `round to nearest` (whichever whole ampere is closer to the ideal value, using a configurable midpoint, default 50 %, which may oscillate between the two amp steps when surplus hovers at the midpoint).
- [ ] When smoothed solar surplus falls below the start threshold (default 1300 W), the charger stops within one control cycle with no hold period.
- [ ] Under the default `round down` strategy, the car is never charged from the grid while in this mode; net grid import attributable to charging never exceeds 0 W beyond one control cycle of sensor noise. Under `round up` or `round to nearest`, net grid import attributable to charging stays bounded to less than one amp-step.

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
**What:** As a cross-cutting override above the active mode's normal cost policy (e.g. the R3 peak clamp a `Captar` session otherwise respects), when the car would otherwise not reach its active SOC limit by the configured departure time, the system relaxes that restriction by raising the peak it is willing to create — and, only under the `Auto` profile, by additionally escalating current draw to the maximum charging current. High-tariff charging is accepted throughout.

**Acceptance criteria:**

- [ ] When the projected charge at the current rate would fall short of the active SOC limit by departure time, the system raises the effective peak limit it is willing to create, up to the configured maximum peak (default 4 kW) — accepting a higher monthly peak demand. This is the only lever available under the `Manual` profile: it never raises what the active mode itself requests, so meeting the deadline depends on whether that mode's own request, once unclamped, is enough.
- [ ] Under the `Auto` profile only, and when the CapTar capability is present (R18), the system additionally escalates current draw to the maximum charging current for as long as the deadline is at risk, reverting once it is no longer needed. When the CapTar capability is absent, `Auto` instead escalates to the `Power` mode's configured target current (R17) — a best-effort measure, not a guarantee, since it does not adapt to how urgent the deadline is; if that is still insufficient, the unreachable-deadline notification below applies.
- [ ] High-tariff charging is permitted while meeting a deadline — this is R5's primary purpose: cost optimisation yields to the deadline.
- [ ] The safety margin is always respected: net import stays at or below the effective peak limit in force minus the safety margin, even while meeting a deadline.
- [ ] The active SOC limit itself is never raised by deadline logic — when a lower limit is in force (e.g. a solar step-up not yet reset), the system only accelerates toward that lower limit. This never involves the solar-reserve cap (R9): a departure deadline and that cap are mutually exclusive.
- [ ] When even charging at the maximum permitted rate cannot meet the deadline, the system charges at that maximum and sends the user a notification that the deadline is unreachable.

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
**What:** When the `Auto` profile is active and, for the next day, the home-day flag is set, the solar forecast is high enough, and no departure deadline is resolved for that day, `Auto` caps the overnight active SOC limit so the next day's solar energy can be used instead, and does not itself opportunistically top up from the grid overnight. A departure deadline resolved for the next day takes priority over the cap (R14) — the two are mutually exclusive. This is `Auto`'s own coordination decision (R16) — it does not apply under `Manual`, and it is not a rule the modes `Auto` selects (e.g. `Captar`, R4) enforce themselves; they simply charge to whichever active SOC limit is currently resolved (R7).

**Acceptance criteria:**

- [ ] The cap activates only under the `Auto` profile, and only when the home-day flag is set for tomorrow (R13), the next-day solar-forecast yield, read from a configured forecast sensor (NF3), exceeds a configurable threshold (default 12 kWh), and the departure-deadline resolution (R14), evaluated one day ahead, resolves to "no deadline" for tomorrow.
- [ ] While active, the overnight active SOC limit resolves to a configurable value (default 60%) while the sun is down (R7).
- [ ] While active, `Auto` does not select a mode for the sake of opportunistic overnight grid top-up (Auto mode-selection row 4, `resolution-rules.md`).
- [ ] Under `Manual`, this cap never applies, regardless of the home-day flag or forecast — the active SOC limit resolves as if `Auto` were not coordinating it at all.
- [ ] A departure deadline resolved for tomorrow (R14) takes priority over the cap: the cap does not activate, and if it was already active when such a deadline appears, it lifts on the next control cycle — a deadline and this cap are mutually exclusive.
- [ ] When the sun comes up, `Auto` is no longer active, or a departure deadline becomes resolved for tomorrow, the cap lifts and the active SOC limit resolves normally.

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
**What:** The system prevents the charger from starting and stopping in quick succession so the car never enters a charging error state.

**Acceptance criteria:**

- [ ] After charging stops, it does not restart until a mode-specific cooldown has fully elapsed (configurable; defaults: 2 minutes for solar modes, 10 minutes for `Captar`).
- [ ] A cooldown, once started, always runs to completion and is not shortened by a change in conditions.
- [ ] The charger current is only ever 0 A or at least the minimum charging current, never in between (per C1).
- [ ] Switching the active mode resets all hold and cooldown timers so the incoming mode starts fresh.

---

### R12 — Plug-in reminder notification

**Priority:** Could
**What:** The system notifies the user to plug in the car when it is home, unplugged, and below the active SOC limit with limited time before departure.

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
- [ ] When the home-day flag is set for tomorrow, it feeds the solar-reserve cap (R9) and the departure-time override (R14).
- [ ] When no configured mechanism has set the flag, tomorrow is treated as not a home day.
- [ ] The home-day flag resets each day at midnight.

---

### R14 — Configurable departure times

**Priority:** Must
**What:** The system targets a departure time for the current day, resolved from a per-day-of-week default, optional public-holiday and home-day overrides, or an external sensor. Any of these may resolve to "no deadline".

**Acceptance criteria:**

- [ ] A default departure time is user-configurable for each day of the week (defaults: 06:00 Mon–Fri; no deadline Sat–Sun).
- [ ] Public-holiday and home-day (home-day flag, R13) departure times can each be configured and override the day-of-week default; both default to no deadline. If a day is both, the public-holiday override takes precedence.
- [ ] Public holidays are recognised from a configured source (e.g. a holiday calendar sensor, NF3).
- [ ] When an external departure-time sensor is configured (NF3), its value takes precedence over all configured values.
- [ ] Any resolved departure time may be "no deadline", in which case no deadline applies that day and R5 does not force charging.
- [ ] The active departure time is resolved in priority order — external sensor, then public-holiday / home-day override, then day-of-week default — and feeds the deadline guarantee (R5) and plug-in reminder (R12).
- [ ] The same resolution, evaluated one day ahead (tomorrow's day-of-week, holiday status, and home-day flag), feeds the solar-reserve cap's precondition (R9): a deadline resolved for tomorrow takes priority over the cap.

---

### R15 — Configurable EV battery capacity

**Priority:** Must
**What:** The car's usable battery capacity is configurable so charging-time estimates reflect the actual vehicle; it may alternatively be read from a sensor when one is available.

**Acceptance criteria:**

- [ ] The usable battery capacity is user-configurable in kWh (default 75 kWh).
- [ ] When a capacity sensor is configured (NF3), its value is used in preference to the configured number, falling back to the configured value if the sensor is unavailable.
- [ ] The effective capacity (sensed or configured) is used when calculating the energy and time needed to meet a departure deadline (R5).
- [ ] Changing the effective capacity changes the deadline calculation accordingly within the next control cycle.

---

### R16 — Auto profile

**Priority:** Must
**What:** The active profile is chosen by the user (`Manual` or `Auto`); under `Auto` the system selects the active mode over time from observable conditions, so the user need not switch modes by hand.

**Acceptance criteria:**

- [ ] The active profile is selected via a single profile selector; the built-in profiles are `Manual` and `Auto`. A profile sets the active mode and is not itself a mode.
- [ ] Under `Manual`, the system makes no automatic mode changes — the active mode is whatever the user or an external source sets (NF1).
- [ ] Under `Auto`, the system sets the active mode from observable conditions (time of day, low-tariff flag, solar availability and forecast, CapTar availability, SOC, departure deadline, home-day flag).
- [ ] Under `Auto`, `Captar` is selected for cost-efficient overnight grid top-up only while the low-tariff flag is active (Auto mode-selection row 4, `resolution-rules.md`); the low-tariff preference belongs to this selection, not to `Captar` mode itself (R4) — a manually selected `Captar` session charges regardless of tariff.
- [ ] Under `Auto`, when its own solar-reserve conditions hold (R9), `Auto` also lowers the active SOC limit (R7) and declines to select a mode for opportunistic overnight top-up — coordinating the limit alongside the mode is `Auto`'s job, not a rule the selected mode enforces; under `Manual` this coordination never happens.
- [ ] Under `Auto`, a mode that is unavailable given the installation's capabilities (R18) is never selected.
- [ ] Under `Auto`, the system escalates from a solar mode to `Captar` when a departure deadline would otherwise be missed (R5), and reverts to a solar mode once grid charging is no longer required. When the CapTar capability is absent, `Auto` escalates to `Power` instead (R18) — a deliberate, deadline-only exception to `Power` otherwise never being Auto-selected — and still reverts once the deadline is no longer at risk.
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
**What:** The available charging modes and the solar-dependent behaviours adapt to the hardware and billing arrangement the installation actually has, declared as configurable capabilities, so the system remains fully usable, under both `Manual` and `Auto`, on an installation without a solar array or without capacity-tariff billing. Without the solar capability alone, a grid mode (`Captar`) is still reachable under `Auto`, since the CapTar capability is unaffected. Without the CapTar capability, `Auto`'s deadline-urgency escalation (R5) falls back to `Power` instead of `Captar` (R16) — a deliberate, deadline-only exception to `Power` otherwise never being Auto-selected — while `Auto`'s opportunistic overnight top-up (R16 row 4) simply does not occur, since there is no deadline forcing it; this also applies when both capabilities are absent.

**Acceptance criteria:**

- [ ] The presence of a solar installation (the solar capability) is user-configurable, defaulting to present.
- [ ] When the solar capability is absent, the `Solar` and `SolarOnly` modes are not offered for manual selection and are never chosen by the `Auto` profile (R16); the `Captar` (subject to the CapTar capability), `Power`, and `Off` modes remain available.
- [ ] When the solar capability is absent, the solar SOC step-up (R8) and the solar-reserve overnight cap (R9) do not apply, and the solar-specific inputs (solar power, solar forecast) are not required to be configured.
- [ ] Whether the installation bills against a capacity tariff (the CapTar capability) is user-configurable, defaulting to present.
- [ ] When the CapTar capability is absent, the `Captar` mode is not offered for manual selection; the `Solar` (subject to the solar capability), `SolarOnly` (subject to the solar capability), `Power`, and `Off` modes remain available for manual selection. `Auto` never chooses `Captar` for opportunistic overnight top-up in this case (R16 row 4 simply does not occur), but does select `Power` — otherwise never an `Auto`-chosen mode — as a best-effort deadline-urgency escalation (R5, R16).
- [ ] Changing a capability takes effect within the next control cycle.
- [ ] The capability model is extensible: additional hardware or billing capabilities (e.g. a home battery) can be added later, each gating the modes and behaviours that depend on it, without altering existing modes (NF2). Capabilities beyond solar and CapTar are out of scope this release.

---

### R19 — Runtime dashboard

**Priority:** Should
**What:** The system presents a dashboard for day-to-day use, showing current charging status and every [runtime configuration](system-overview.md#ubiquitous-language) input the household adjusts routinely (e.g. active profile, active mode, default SOC limit, departure times, home-day flag). [Install-time configuration](system-overview.md#ubiquitous-language) is set up once, through the integration's own configuration flow, and is not part of this dashboard.

**Acceptance criteria:**

- [ ] The dashboard shows current charging status: charger status (connected/charging/disconnected), active profile, active mode, active SOC limit, and current charger current.
- [ ] The dashboard shows the current solar surplus and net import, so the household can see whether charging is currently drawing from solar or from the grid.
- [ ] Every entity classified as runtime configuration in `entity-catalog.md` (`config`-role, or a `state`-role entity the user sets directly, e.g. the active mode selector) is both visible and settable from the dashboard.
- [ ] No entity classified as install-time configuration is presented on the dashboard; install-time configuration is reachable only through the integration's configuration flow.
- [ ] Adding a new entity to `entity-catalog.md` and classifying it as runtime requires no dashboard-specific logic change for it to appear.

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
| C3 | Net grid import is never allowed to exceed the effective peak limit (which rises to the maximum peak only during deadline urgency), and charging targets a safety margin below it. |
| C4 | Net grid import (all household load plus charging) never exceeds the grid supply ceiling; the charger targets a configurable grid safety offset below the ceiling, checked against raw (unsmoothed) readings so a sudden swing cannot trip the main fuse before the next control cycle reacts. This hard limit applies in every mode, including `Power` mode with CapTar peak protection disabled (R17). |
