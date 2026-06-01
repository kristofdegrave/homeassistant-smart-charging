# Smart Charging — Use Cases

Use cases derived from [smart-charging.requirements.md](smart-charging.requirements.md).

---

## Charging Mode Execution

### UC1 — Solar Mode
Charge from solar surplus ≥ 150 W. Adjust current each cycle to maximise self-consumption (net import ≤ 0 W). Fall back to minimum 6A grid current when surplus drops below the threshold. Hold at 6A for 5 minutes before stopping to ride out cloud cover.

*Requirements: R1 (Solar row), R7*

---

### UC2 — Solar-Only Mode
Charge only when solar surplus ≥ 1300 W. Adjust current each cycle to maximise self-consumption. Stop immediately when surplus drops below 1300 W — no grid fallback, no hold period.

*Requirements: R1 (SolarOnly row), R7*

---

### UC3 — Captar Mode
Charge within the monthly peak limit. Prefer cheap-tariff windows (weekdays 22:00–07:00, weekends all day). Stop immediately when net import at the current set-point would breach the effective peak limit. Enforce a 10-minute cooldown after each stop.

*Requirements: R3, R4, R7*

---

### UC4 — Power Mode
Charge at a fixed configured current. No solar tracking, no peak rules.

*Requirements: NF2 (Power module)*

---

### UC5 — Off Mode
Set charger to 0A. No charging.

*Requirements: NF2 (Off state in `sc_active_profile`)*

---

## SOC Management

### UC6 — Solar SOC Step-Up
When solar charging is active and the car's SOC comes within 2% of the current charge limit, raise the limit by 5 percentage points (up to `sc_max_solar_soc`). Enforce a 10-minute cooldown between consecutive step-ups. Revert to the default target when the car disconnects or the mode switches to Captar.

*Requirements: R2b*

---

### UC7 — Work-From-Home Night Cap
When the user confirms WFH tomorrow and the solar forecast for tomorrow exceeds 12 kWh, cap night charging at 60% SOC from sunset until sunrise. Suppress cheap-tariff grid charging during the cap. Lift the cap during the day so normal solar logic applies.

*Requirements: R2c*

---

### UC8 — Resolve Active SOC Limit
Determine the effective charge limit at any moment by applying priority order: WFH night cap (60%) → solar step-up value → default target (`sc_active_soc`).

*Requirements: R2d*

---

## Safety & Protection

### UC9 — Peak Protection
Before applying any current set-point, verify using raw (unsmoothed) sensor values that `net_w + charger_w_delta` will not exceed the effective peak limit. If the minimum current (6A) would still breach the limit, stop the charger immediately (0A).

*Requirements: R3, C3*

---

### UC10 — Deadline Override
When the car cannot reach its active SOC limit by the configured departure time at the current charging rate, calculate the minimum current needed to meet the deadline and escalate to that value. Never exceed peak headroom (C3). Emit a warning if even 6A cannot meet the deadline.

*Requirements: R5*

---

### UC11 — Hysteresis & Rapid Cycling Prevention
Enforce mode-specific hold periods and cooldowns to prevent Tesla charging errors from rapid start/stop cycles. Reset all timers when the active profile changes.

*Requirements: R7*

---

## Sensing & Input

### UC12 — Sensor Smoothing
Apply a 4-reading rolling average (~40 s) to `net_w` and `solar_w` before using them in current calculations. Bypass smoothing for peak protection decisions (UC9).

*Requirements: R6*

---

### UC13 — Configurable Departure Times
Read the weekday departure time, weekend departure time, and EV battery capacity from HA helpers. Use the weekday time Monday–Friday and the weekend time on Saturday and Sunday.

*Requirements: R9*

---

## Notifications

### UC14 — Plug-In Reminder
Send a single mobile notification when the car is home, not connected to the charger, below its active SOC target, and within 8 hours of the configured departure time. Do not repeat the notification until the car has been connected and disconnected again.

*Requirements: R8*

---

### UC15 — WFH Evening Notification
At 18:00 each evening, send an actionable mobile notification asking whether the user will work from home tomorrow. Set `input_boolean.sc_wfh_tomorrow` to `on` on a yes response. If no response within 2 hours (by 20:00), treat as `off`. Reset the flag at midnight.

*Requirements: R2c*
