# UC3 — Captar Mode

## Description & goal

Charge the EV at the maximum current that keeps net grid import at or below
the effective peak limit, but only during cost-efficient windows. Suppress
charging outside cheap-tariff hours unless urgency (R5) demands it.
If the peak available capacity falls below the minimum charging current, the
charger stops and enters a configurable cooldown period.

---

## Actors & entities

| Actor / Entity | Role |
| --- | --- |
| `input_select.sc_active_profile` | Read: must be `Captar` for this use case to be active |
| `sensor.sc_charger_status` | Read: determines whether a vehicle is present and able to charge |
| `input_number.sc_captar_cooldown_minutes` | Read: cooldown duration in minutes after a peak-limit stop (default 10) |
| `input_boolean.sc_wfh_tomorrow` | Read: WFH reservation flag — suppresses cheap-tariff charging at night when `on` |
| `sun.sun` | Read: determines whether the WFH suppression window is active (`below_horizon`) |
| `sensor.sc_ev_soc` | Read: current EV state of charge — used by urgency calculation |
| `input_number.sc_active_soc` | Read: target SOC — used by urgency calculation |
| `input_datetime.sc_departure_time_weekday` | Read: weekday departure time — used by urgency calculation |
| `input_datetime.sc_departure_time_weekend` | Read: weekend departure time — used by urgency calculation |
| `input_number.sc_ev_battery_capacity_kwh` | Read: usable battery capacity — used by urgency calculation |
| EV charger | Written: receives the current set-point in amperes |

---

## Preconditions & triggers

**Preconditions:**

- `input_select.sc_active_profile` is set to `Captar`
- The current time is within a cheap-tariff window:
  - **Weekdays (Mon–Fri):** 22:00–07:00
  - **Weekends (Sat–Sun):** all day
- WFH suppression is not blocking the cycle:
  - Suppression is active when `input_boolean.sc_wfh_tomorrow` is `on` and
    `sun.sun` is `below_horizon`
  - When suppression is active, compute urgency (R5) — energy needed to reach the
    active SOC limit by the configured departure time
  - If the car **can** meet the deadline without charging → flow does not proceed
    (charger set to 0 A)
  - If urgency is active (car **cannot** meet the deadline) → carry `floor_amps`
    (R5 minimum current) into the main flow and proceed
- The effective peak available capacity (`max_amps`) has been determined (UC9 / UC10)

**Trigger:**

Each coordinator control cycle.

---

## Main flow

1. If `sensor.sc_charger_status` is `disconnected` → set the charger to 0 A and return.
2. If the system is within the cooldown (`sc_captar_cooldown_minutes`) following a stop
   → set the charger to 0 A and return. The cooldown runs to full completion and may
   not be shortened — not by gate conditions changing, not by the active profile
   cycling away from Captar and back (R7).
3. If `max_amps < 6`, the minimum charging current would breach the effective peak
   limit → go to **A1**.
4. `target_amps = max(max_amps, floor_amps)` where `floor_amps` is 0 unless urgency
   was computed in the preconditions.
5. Enforce C1: `target_amps` must be 0 or 6–32 A. Clamp any 1–5 A value to 6 A.
6. Set the charger to `target_amps`.

---

## Alternative flows

### A1 — Peak limit breached at minimum current

When `max_amps < 6` (triggered from main flow step 3):

1. Set the charger to 0 A immediately — no hold period (Captar stop is always
   immediate, R7).
2. Start the cooldown (`sc_captar_cooldown_minutes`).

*The effective peak limit (C3) is never violated.*

### A2 — Entity unavailable

If `sensor.sc_charger_status` is unavailable or cannot be read:

1. Log a warning identifying the missing entity.
2. Return 0 A — the charger is stopped rather than left at an unknown set-point.

---

## Acceptance criteria

- When inside a cheap-tariff window, no WFH suppression is active, no cooldown
  is running, and `max_amps ≥ 6`, the charger outputs a non-zero current within
  one control cycle.
- The charger is set to `max_amps`.
- When outside the cheap-tariff window, the charger is set to 0 A.
- When `sc_wfh_tomorrow` is `on`, `sun.sun` is `below_horizon`, and the car can
  meet its departure deadline without charging, the charger is set to 0 A.
- When `sc_wfh_tomorrow` is `on` but urgency is active, the charger runs at the
  minimum current required to meet the deadline (`floor_amps`), subject to C3.
  The WFH cap is not bypassed — urgency only escalates current to reach the active
  SOC limit (which may be the 60 % night cap), not the default target.
- When `max_amps < 6`, the charger is set to 0 A immediately and the
  cooldown (`sc_captar_cooldown_minutes`) starts.
- The cooldown (`sc_captar_cooldown_minutes`) runs to full completion before any
  restart; a gate condition changing mid-cooldown does not shorten it.
- If `sensor.sc_charger_status` is unavailable, the charger is set to 0 A
  and a warning is logged.

---

Requirements: R3 (peak ceiling, UC9/UC10), R4, R5 (urgency), R7, C1, C3
