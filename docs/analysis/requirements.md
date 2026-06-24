# Smart Charging v3 — Requirements

Requirements written fresh from the idea. Each requirement describes *what* the system must do — never *how*.

**Priority key:** Must = non-negotiable for launch / Should = important but not blocking / Could = nice to have / Won't = explicitly out of scope for this version

---

## Functional requirements

### R1 — Solar-first charging

**Priority:** Must
**What:** When solar mode is active and surplus solar power is available, the system charges the car from that surplus and prefers solar over grid power at all times.

**Acceptance criteria:**
- [ ] Charging starts within one control cycle once smoothed solar surplus reaches at least 150 W and no stop or cooldown condition applies.
- [ ] The charger current is set to the highest value that keeps net grid import at or below 0 W, rounded down to a whole ampere.
- [ ] When surplus drops to 0 W, the charger holds at the minimum current for 5 minutes before stopping, riding out brief cloud cover.
- [ ] Net grid import never stays above 0 W for longer than one reading cycle while charging in this mode.
- [ ] The system never lowers charger current below what solar surplus supports in order to draw the difference from the grid.

---

### R2 — Solar-only charging

**Priority:** Must
**What:** When solar-only mode is active, the system charges the car exclusively from solar surplus and never draws supplementary power from the grid.

**Acceptance criteria:**
- [ ] Charging starts within one control cycle once smoothed solar surplus reaches at least 1300 W and no stop or cooldown condition applies.
- [ ] The charger current is set to the highest value that keeps net grid import at or below 0 W, rounded down to a whole ampere.
- [ ] When smoothed solar surplus falls below 1300 W, the charger stops within one control cycle with no hold period.
- [ ] The car is never charged from the grid while in this mode; net grid import attributable to charging never exceeds 0 W beyond one reading cycle of sensor noise.

---

### R3 — CapTar peak protection

**Priority:** Must
**What:** The system limits charging so that charging never raises the monthly grid peak above the effective peak limit.

**Acceptance criteria:**
- [ ] In every control cycle, the chosen charger current keeps net grid import at or below the effective peak limit — the lower of the current monthly peak demand and 4 kW.
- [ ] This check uses the most recent raw (unsmoothed) sensor readings so that a breach cannot persist for the duration of a smoothing window.
- [ ] When even the minimum charging current would push net import above the effective peak limit, the charger is stopped within the same control cycle.
- [ ] Headroom created by other household appliances switching off is not consumed by the charger beyond the effective peak limit.

---

### R4 — Cost-efficient grid charging

**Priority:** Must
**What:** When grid power is needed to charge, the system charges during the cheapest available tariff window and avoids peak-tariff charging unless a deadline forces it.

**Acceptance criteria:**
- [ ] Grid charging only occurs when no solar surplus is available to cover the session.
- [ ] During cheap-tariff windows (weekdays 22:00–07:00 and all day at weekends), grid charging is permitted up to the effective peak limit.
- [ ] Outside cheap-tariff windows, the system does not charge from the grid unless a departure deadline (R5) requires it.
- [ ] When no permitted charging source is available, the charger outputs 0 A.

---

### R5 — Departure deadline guarantee

**Priority:** Must
**What:** When the car would otherwise not reach its target charge by the configured departure time, the system raises the charging rate to the lowest level that still meets the deadline.

**Acceptance criteria:**
- [ ] When the projected charge at the current rate would fall short of the active SOC target by departure time, the charger current increases to the minimum rate that closes the gap before departure.
- [ ] Peak-tariff charging is permitted while meeting a deadline.
- [ ] The effective peak limit is never exceeded, even while meeting a deadline.
- [ ] The active SOC target itself is never raised by deadline logic — when a lower target is in force (for example the work-from-home night cap), the system only accelerates toward that lower target.
- [ ] When even continuous charging cannot meet the deadline, the system charges at the maximum permitted rate and raises a warning that the deadline is unreachable.

---

### R6 — Configurable SOC target

**Priority:** Must
**What:** The car is charged up to a target state of charge that the user can configure, and charging stops once that target is reached.

**Acceptance criteria:**
- [ ] The default charge target is user-configurable within a 50–100% range.
- [ ] Charging stops when the car reaches the currently active SOC target.
- [ ] At any moment a single active SOC target applies, resolved by a defined priority order across the default target, any solar step-up, and the work-from-home night cap.
- [ ] Charging does not resume above the active target until the target changes or the car is unplugged and replugged.

---

### R7 — Solar SOC step-up

**Priority:** Should
**What:** While charging on solar, the system raises the charge target in steps so that abundant free solar energy is stored rather than wasted.

**Acceptance criteria:**
- [ ] When solar charging is active and the car's charge reaches within 2 percentage points of the active target, the target rises by 5 percentage points.
- [ ] The stepped-up target never exceeds a user-configurable maximum (80–100%, default 100%); a step that would overshoot it clamps to the maximum.
- [ ] Consecutive step-ups are at least 10 minutes apart.
- [ ] The stepped-up target reverts to the default target when the car disconnects or when charging switches to CapTar mode.
- [ ] Switching between solar and solar-only mode does not revert the stepped-up target.

---

### R8 — Work-from-home night charging cap

**Priority:** Should
**What:** When the user will work from home the next day and sufficient solar is forecast, the system caps overnight charging so daytime solar energy can be used instead.

**Acceptance criteria:**
- [ ] The cap activates only when the user has confirmed working from home tomorrow and the forecast solar yield for tomorrow exceeds 12 kWh.
- [ ] While active, the overnight charge target is capped at 60% from sunset until sunrise.
- [ ] Cheap-tariff grid charging is suppressed while the cap is active.
- [ ] A departure deadline (R5) may charge up to the 60% cap but never beyond it.
- [ ] At sunrise the cap lifts and normal solar charging resumes.

---

### R9 — Sensor smoothing

**Priority:** Must
**What:** The system bases charging-rate decisions on smoothed power readings so that momentary fluctuations do not cause the charging rate to change.

**Acceptance criteria:**
- [ ] Net grid power and solar power readings are averaged over the most recent 4 readings before being used to set the charging rate.
- [ ] A power spike lasting a single control cycle does not change the charger set-point.
- [ ] A power change sustained across 4 control cycles changes the charger set-point within the following control cycle.
- [ ] Peak-protection decisions (R3) are exempt and use raw, unsmoothed readings.

---

### R10 — Rapid cycling prevention

**Priority:** Must
**What:** The system prevents the charger from starting and stopping in quick succession so the car never enters a charging error state.

**Acceptance criteria:**
- [ ] After charging stops, it does not restart until a mode-specific cooldown has fully elapsed (2 minutes for solar modes, 10 minutes for CapTar).
- [ ] A cooldown, once started, always runs to completion and is not shortened by a change in conditions.
- [ ] The charger current is never set to a value between 1 A and 5 A.
- [ ] Switching the active mode resets all hold and cooldown timers so the incoming mode starts fresh.

---

### R11 — Plug-in reminder notification

**Priority:** Should
**What:** The system notifies the user to plug in the car when it is home, unplugged, and below target with limited time before departure.

**Acceptance criteria:**
- [ ] A single notification is sent when the car is home, disconnected, below the active SOC target, and within 8 hours of the next departure time.
- [ ] No further reminder is sent for the same departure window unless the charger is connected and then disconnected again.
- [ ] No reminder is sent when the car is already connected or already at or above the active SOC target.

---

### R12 — WFH evening notification

**Priority:** Should
**What:** Each evening the system asks the user whether they will work from home the next day so overnight charging can be planned accordingly.

**Acceptance criteria:**
- [ ] An actionable yes/no notification is sent at 18:00 each evening.
- [ ] Answering "yes" records that the user will work from home tomorrow.
- [ ] If no answer is given within 2 hours, the system treats the answer as "no".
- [ ] The recorded answer resets each day at midnight.

---

### R13 — Configurable departure times

**Priority:** Must
**What:** The user can configure separate departure times for weekdays and weekends, and the system applies the correct one for each day.

**Acceptance criteria:**
- [ ] Separate weekday and weekend departure times are user-configurable (defaults 06:00 and 10:00).
- [ ] The weekday departure time is applied Monday through Friday.
- [ ] The weekend departure time is applied on Saturday and Sunday.
- [ ] The active departure time feeds the deadline guarantee (R5) and plug-in reminder (R11).

---

### R14 — Configurable EV battery capacity

**Priority:** Must
**What:** The user can configure the car's usable battery capacity so charging-time estimates reflect the actual vehicle.

**Acceptance criteria:**
- [ ] The usable battery capacity is user-configurable in kWh (default 75 kWh).
- [ ] The configured capacity is used when calculating the energy and time needed to meet a departure deadline (R5).
- [ ] Changing the configured capacity changes the deadline calculation accordingly within the next control cycle.

---

## Non-functional requirements

### NF1 — Mode selection owned by HA, not the integration

**Priority:** Must
**What:** The integration executes whichever charging mode it is told is active and contains no logic deciding when to switch modes.

**Acceptance criteria:**
- [ ] The active mode is supplied to the integration from outside it, and the integration acts on that value alone.
- [ ] The integration contains no rules that select or change the active mode based on time, solar forecast, SOC, or departure.
- [ ] Changing the active mode externally changes the integration's behaviour within the next control cycle.

---

### NF2 — One module per charging mode

**Priority:** Must
**What:** Each charging mode is implemented in its own self-contained unit with no logic belonging to another mode.

**Acceptance criteria:**
- [ ] There is exactly one unit of logic per charging mode (Solar, SolarOnly, CapTar, Power).
- [ ] No mode's logic references or branches on another mode's behaviour.
- [ ] Mode behaviour can be changed or replaced one mode at a time without altering the others.

---

### NF3 — All sensor access via sc_ wrapper entities

**Priority:** Must
**What:** All charging logic reads its inputs through the integration's own namespaced wrapper entities rather than raw device entities.

**Acceptance criteria:**
- [ ] Every sensor value used by the charging logic is read from an `sc_`-prefixed wrapper entity.
- [ ] No charging logic references a raw device or third-party integration entity directly.
- [ ] Replacing the underlying device requires changing only the wrapper entity, not the charging logic.

---

## Constraints

These are hard rules that must never be violated, regardless of mode or circumstance.

| ID | Constraint |
|----|-----------|
| C1 | The charging current is always either 0 A or in the 6–32 A range; values of 1–5 A are never sent because they cause Tesla charging errors. |
| C2 | The charge limit is changed only while the car is at home; no charge-limit change is made remotely. |
| C3 | Net grid import is never allowed to exceed the effective peak limit — the lower of the current monthly peak demand and 4 kW, with a 3.5 kW floor during deadline urgency. |
